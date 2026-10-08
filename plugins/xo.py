"""Production-grade two-player inline Tic-Tac-Toe for CythonX.

Usage:
    @AssisXBot xo
    @AssisXBot xo @username

The inline-query sender becomes Player X. Public games accept the first
different user who presses Join. Private games accept only the resolved target
user. State is persisted in Redis and protected by per-game distributed locks.
Timeouts are timestamp-based, so they remain valid after process restarts.
"""

from __future__ import annotations

import asyncio
import html
import json
import re
import secrets
import time
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from typing import Optional

from telethon import Button
from telethon.errors import MessageNotModifiedError

from CythonX import LOGS, udB
from CythonX._misc import SUDO_M
from CythonX._misc._assistant import callback, in_pattern


_PREFIX = "cythonx:xo:v2:"
_GAME_TTL = 30 * 60
_WAITING_TIMEOUT = 15 * 60
_PLAYING_TIMEOUT = 10 * 60
_LOCK_TTL_MS = 120_000
_LOCK_REFRESH_MS = 20_000
_TOKEN_BYTES = 9
_MAX_NAME = 32
_MAX_USERNAME = 32

_EMPTY = "·"
_X = "❌"
_O = "⭕"

_TERMINAL_STATUSES = {"won", "draw", "resigned", "cancelled", "expired"}
_VALID_STATUSES = {"waiting", "playing", *list(_TERMINAL_STATUSES), "archived"}

_LOCAL_LOCKS: dict[str, asyncio.Lock] = {}
_LOCAL_LOCK_REFS: dict[str, int] = {}
_LOCAL_LOCKS_GUARD = asyncio.Lock()


class BusyGameError(Exception):
    """Raised when another worker currently owns the game's Redis lock."""


class LockLostError(Exception):
    """Raised when the current worker no longer owns the game's Redis lock."""


@dataclass(slots=True)
class Game:
    token: str
    player_x: int
    player_x_name: str
    board: list[Optional[str]]
    player_o: Optional[int] = None
    player_o_name: str = ""
    private_target: Optional[int] = None
    private_target_username: str = ""
    turn: str = "X"
    status: str = "waiting"
    winner: Optional[str] = None
    updated_at: float = 0.0
    version: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> "Game":
        if not isinstance(data, dict):
            raise ValueError("Invalid XO state")

        board = data.get("board")
        if not isinstance(board, list) or len(board) != 9:
            raise ValueError("Invalid XO board")
        if any(cell not in (None, "X", "O") for cell in board):
            raise ValueError("Invalid XO board cells")

        token = str(data.get("token") or "")
        if not token or len(token) > 32:
            raise ValueError("Invalid XO token")

        player_x = int(data["player_x"])
        player_o = data.get("player_o")
        if player_o is not None:
            player_o = int(player_o)
            if player_o == player_x:
                raise ValueError("Invalid XO players")

        private_target = data.get("private_target")
        if private_target is not None:
            private_target = int(private_target)
            if private_target == player_x:
                raise ValueError("Invalid XO private target")

        turn = str(data.get("turn") or "X")
        status = str(data.get("status") or "waiting")
        winner = data.get("winner")

        if turn not in {"X", "O"} or status not in _VALID_STATUSES:
            raise ValueError("Invalid XO state")
        if winner not in (None, "X", "O"):
            raise ValueError("Invalid XO winner")
        if status in {"playing", "won", "draw", "resigned"} and player_o is None:
            raise ValueError("Invalid XO player state")

        return cls(
            token=token,
            player_x=player_x,
            player_x_name=str(data.get("player_x_name") or "Player X")[:_MAX_NAME],
            board=board,
            player_o=player_o,
            player_o_name=str(data.get("player_o_name") or "")[:_MAX_NAME],
            private_target=private_target,
            private_target_username=str(
                data.get("private_target_username") or ""
            )[:_MAX_USERNAME],
            turn=turn,
            status=status,
            winner=winner,
            updated_at=float(data.get("updated_at") or 0),
            version=max(0, int(data.get("version") or 0)),
        )


def _redis():
    client = getattr(udB, "db", None)
    required = ("get", "set", "delete", "eval")
    if client is None or any(not hasattr(client, attr) for attr in required):
        raise RuntimeError("XO requires the project's Redis database")
    return client


def _game_key(token: str) -> str:
    return f"{_PREFIX}game:{token}"


def _lock_key(token: str) -> str:
    return f"{_PREFIX}lock:{token}"


def _new_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES).replace("-", "_").replace("/", "_")[:16]


def _lock_value() -> str:
    return secrets.token_urlsafe(24)


def _decode_redis_value(raw):
    return raw.decode("utf-8") if isinstance(raw, bytes) else raw


async def _redis_get(token: str) -> Optional[Game]:
    def read():
        raw = _redis().get(_game_key(token))
        if raw is None:
            return None
        return Game.from_dict(json.loads(_decode_redis_value(raw)))

    return await asyncio.to_thread(read)


async def _redis_create(game: Game) -> bool:
    payload = json.dumps(asdict(game), ensure_ascii=False, separators=(",", ":"))

    def create():
        return bool(_redis().set(_game_key(game.token), payload, ex=_GAME_TTL, nx=True))

    return await asyncio.to_thread(create)


async def _redis_save(game: Game, lock_value: str) -> None:
    payload = json.dumps(asdict(game), ensure_ascii=False, separators=(",", ":"))
    script = """
    if redis.call('get', KEYS[1]) ~= ARGV[1] then
        return 0
    end
    redis.call('set', KEYS[2], ARGV[2], 'EX', ARGV[3])
    return 1
    """
    result = await asyncio.to_thread(
        lambda: _redis().eval(
            script,
            2,
            _lock_key(game.token),
            _game_key(game.token),
            lock_value,
            payload,
            str(_GAME_TTL),
        )
    )
    if not result:
        raise LockLostError(f"XO lock ownership was lost for {game.token}")


async def _redis_delete(token: str) -> None:
    await asyncio.to_thread(lambda: _redis().delete(_game_key(token)))


async def _redis_lock(token: str, value: str) -> bool:
    return await asyncio.to_thread(
        lambda: bool(_redis().set(_lock_key(token), value, nx=True, px=_LOCK_TTL_MS))
    )


async def _redis_unlock(token: str, value: str) -> None:
    script = """
    if redis.call('get', KEYS[1]) == ARGV[1] then
        return redis.call('del', KEYS[1])
    end
    return 0
    """
    await asyncio.to_thread(lambda: _redis().eval(script, 1, _lock_key(token), value))


async def _redis_refresh_lock(token: str, value: str) -> bool:
    script = """
    if redis.call('get', KEYS[1]) == ARGV[1] then
        return redis.call('pexpire', KEYS[1], ARGV[2])
    end
    return 0
    """
    result = await asyncio.to_thread(
        lambda: _redis().eval(
            script, 1, _lock_key(token), value, str(_LOCK_TTL_MS)
        )
    )
    return bool(result)


async def _lock_heartbeat(token: str, value: str, stop: asyncio.Event) -> None:
    try:
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), _LOCK_REFRESH_MS / 1000)
            except asyncio.TimeoutError:
                if not await _redis_refresh_lock(token, value):
                    LOGS.error("XO Redis lock was lost for game %s", token)
                    return
    except asyncio.CancelledError:
        raise
    except Exception:
        LOGS.exception("XO Redis lock heartbeat failed for game %s", token)


@asynccontextmanager
async def _game_guard(token: str):
    async with _LOCAL_LOCKS_GUARD:
        local = _LOCAL_LOCKS.setdefault(token, asyncio.Lock())
        _LOCAL_LOCK_REFS[token] = _LOCAL_LOCK_REFS.get(token, 0) + 1

    try:
        async with local:
            lock_value = _lock_value()
            if not await _redis_lock(token, lock_value):
                raise BusyGameError

            stop = asyncio.Event()
            heartbeat = asyncio.create_task(_lock_heartbeat(token, lock_value, stop))
            try:
                yield lock_value
            finally:
                stop.set()
                heartbeat.cancel()
                try:
                    await heartbeat
                except asyncio.CancelledError:
                    pass
                except Exception:
                    LOGS.exception("XO lock heartbeat cleanup failed for %s", token)
                try:
                    await _redis_unlock(token, lock_value)
                except Exception:
                    LOGS.exception("Failed to release XO Redis lock for %s", token)
    finally:
        async with _LOCAL_LOCKS_GUARD:
            refs = _LOCAL_LOCK_REFS.get(token, 0) - 1
            if refs <= 0:
                _LOCAL_LOCK_REFS.pop(token, None)
                _LOCAL_LOCKS.pop(token, None)
            else:
                _LOCAL_LOCK_REFS[token] = refs


def _name(user) -> str:
    if user is None:
        return "Player"
    name = getattr(user, "first_name", None) or getattr(user, "title", None)
    if not name:
        name = getattr(user, "username", None)
    return (
        str(name or "Player")
        .replace("\n", " ")
        .replace("\r", " ")
        .strip()[:_MAX_NAME]
        or "Player"
    )


def _safe_name(name: str) -> str:
    return html.escape(name, quote=False)


def _safe_username(username: str) -> str:
    return html.escape(username.lstrip("@")[:_MAX_USERNAME], quote=False)


def _symbol(value: Optional[str]) -> str:
    return _X if value == "X" else _O if value == "O" else _EMPTY


def _winner(board: list[Optional[str]]) -> Optional[str]:
    for a, b, c in (
        (0, 1, 2), (3, 4, 5), (6, 7, 8),
        (0, 3, 6), (1, 4, 7), (2, 5, 8),
        (0, 4, 8), (2, 4, 6),
    ):
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    return None


def _timeout_for(game: Game) -> int:
    return _WAITING_TIMEOUT if game.status == "waiting" else _PLAYING_TIMEOUT


def _expired(game: Game, now: Optional[float] = None) -> bool:
    if game.status not in {"waiting", "playing"}:
        return False
    if game.updated_at <= 0:
        return False
    return (now or time.time()) - game.updated_at >= _timeout_for(game)


async def _expire_if_needed(game: Game, lock_value: str) -> bool:
    if not _expired(game):
        return False
    game.status = "expired"
    game.winner = None
    await _save(game, lock_value)
    return True


def _remaining(game: Game) -> int:
    if game.status not in {"waiting", "playing"}:
        return 0
    remaining = _timeout_for(game) - int(max(0, time.time() - game.updated_at))
    return max(0, remaining)


def _format_duration(seconds: int) -> str:
    minutes, seconds = divmod(max(0, seconds), 60)
    return f"{minutes:02d}:{seconds:02d}"


def _board_buttons(game: Game):
    rows = []
    for row in range(3):
        buttons = []
        for col in range(3):
            index = row * 3 + col
            value = game.board[index]
            prefix = "m" if value is None and game.status == "playing" else "n"
            buttons.append(
                Button.inline(
                    _symbol(value),
                    data=f"xo:{prefix}:{game.token}:{index}",
                )
            )
        rows.append(buttons)
    return rows


def _buttons(game: Game):
    if game.status == "waiting":
        return _board_buttons(game) + [
            [Button.inline("🎮 Join Game", data=f"xo:j:{game.token}")],
            [Button.inline("✖️ Cancel Game", data=f"xo:c:{game.token}")],
        ]

    if game.status == "playing":
        return _board_buttons(game) + [
            [Button.inline("🏳️ Resign", data=f"xo:q:{game.token}")]
        ]

    if game.status in _TERMINAL_STATUSES:
        if game.status == "expired":
            return [
                [Button.inline("🔄 New Game", data=f"xo:r:{game.token}")],
                [Button.inline("✖️ End Game", data=f"xo:e:{game.token}")],
            ]
        return [
            [Button.inline("🔄 Rematch", data=f"xo:r:{game.token}")],
            [Button.inline("✖️ End Game", data=f"xo:e:{game.token}")],
        ]

    return []


def _text(game: Game) -> str:
    x = _safe_name(game.player_x_name)
    o = _safe_name(game.player_o_name) if game.player_o_name else "Waiting for opponent..."

    if game.status == "waiting":
        privacy = (
            f"🔒 <b>Private:</b> @{_safe_username(game.private_target_username)}"
            if game.private_target
            else "🌐 <b>Public game</b>"
        )
        return (
            "🎮 <b>Tic-Tac-Toe</b>\n\n"
            f"❌ <b>X:</b> {x}\n"
            f"⭕ <b>O:</b> {o}\n"
            f"{privacy}\n\n"
            f"⏳ Join within <b>{_format_duration(_remaining(game))}</b>.\n"
            "Press <b>🎮 Join Game</b> to start."
        )

    if game.status == "playing":
        current = x if game.turn == "X" else o
        mark = _X if game.turn == "X" else _O
        privacy = (
            f"\n🔒 <b>Private:</b> @{_safe_username(game.private_target_username)}"
            if game.private_target
            else ""
        )
        return (
            "🎮 <b>Tic-Tac-Toe</b>\n\n"
            f"❌ <b>X:</b> {x}\n"
            f"⭕ <b>O:</b> {o}{privacy}\n\n"
            f"🎯 Turn: {mark} <b>{current}</b>\n"
            f"⏳ Time left: <b>{_format_duration(_remaining(game))}</b>"
        )

    if game.status == "won":
        winner_name = x if game.winner == "X" else o
        winner_mark = _X if game.winner == "X" else _O
        return (
            "🏆 <b>Game Over!</b>\n\n"
            f"❌ <b>X:</b> {x}\n"
            f"⭕ <b>O:</b> {o}\n\n"
            f"🎉 Winner: {winner_mark} <b>{winner_name}</b>"
        )

    if game.status == "draw":
        return (
            "🤝 <b>Draw!</b>\n\n"
            f"❌ <b>X:</b> {x}\n"
            f"⭕ <b>O:</b> {o}\n\n"
            "The board is full."
        )

    if game.status == "resigned":
        winner_name = x if game.winner == "X" else o
        winner_mark = _X if game.winner == "X" else _O
        return (
            "🏳️ <b>Game ended by resignation.</b>\n\n"
            f"❌ <b>X:</b> {x}\n"
            f"⭕ <b>O:</b> {o}\n\n"
            f"🏆 Winner: {winner_mark} <b>{winner_name}</b>"
        )

    if game.status == "expired":
        return (
            "⏰ <b>Game Expired</b>\n\n"
            f"❌ <b>X:</b> {x}\n"
            f"⭕ <b>O:</b> {o}\n\n"
            "The game expired because the required action was not made in time."
        )

    if game.status == "cancelled":
        return (
            "❌ <b>Game Cancelled</b>\n\n"
            f"❌ <b>X:</b> {x}\n"
            f"⭕ <b>O:</b> {o}"
        )

    return "❌ <b>Game unavailable.</b>"


def _end_confirmation_text(game: Game) -> str:
    return (
        "⚠️ <b>End Game?</b>\n\n"
        "Are you sure you want to permanently close this Tic-Tac-Toe game?\n\n"
        "The current game state will be removed from Redis and its buttons "
        "will no longer be usable."
    )


def _confirmation_buttons(token: str):
    return [
        [
            Button.inline("❌ End Game", data=f"xo:y:{token}"),
            Button.inline("↩️ Back", data=f"xo:b:{token}"),
        ]
    ]


async def _sender(event):
    try:
        return await event.get_sender()
    except Exception:
        return None


async def _answer(event, text: str, alert: bool = False):
    try:
        await event.answer(text, alert=alert)
    except Exception:
        pass


async def _render(event, game: Game) -> None:
    try:
        await event.edit(
            _text(game),
            buttons=_buttons(game),
            parse_mode="html",
            link_preview=False,
        )
    except MessageNotModifiedError:
        pass


async def _render_confirmation(event, game: Game) -> None:
    try:
        await event.edit(
            _end_confirmation_text(game),
            buttons=_confirmation_buttons(game.token),
            parse_mode="html",
            link_preview=False,
        )
    except MessageNotModifiedError:
        pass


async def _render_closed(event) -> None:
    try:
        await event.edit(
            "🔒 <b>Game Closed</b>\n\n"
            "This Tic-Tac-Toe game has been permanently closed.\n"
            "Start a new game with <code>@AssisXBot xo</code>.",
            buttons=[],
            parse_mode="html",
            link_preview=False,
        )
    except MessageNotModifiedError:
        pass


async def _load(token: str) -> Optional[Game]:
    try:
        return await _redis_get(token)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        LOGS.exception("Invalid persisted XO state: %s", token)
        await _redis_delete(token)
        return None
    except Exception:
        LOGS.exception("Failed to load XO game: %s", token)
        raise


async def _save(game: Game, lock_value: str) -> None:
    game.updated_at = time.time()
    game.version += 1
    await _redis_save(game, lock_value)


async def _load_locked(token: str, lock_value: str) -> Optional[Game]:
    game = await _load(token)
    if game is not None:
        await _expire_if_needed(game, lock_value)
    return game


def _valid_token(token: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_]{8,32}", token))


def _callback_token(event) -> Optional[str]:
    try:
        token = event.data_match.group(1).decode("utf-8")
    except Exception:
        return None
    return token if _valid_token(token) else None


async def _resolve_private_target(event, username: str):
    username = username.lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9_]{5,32}", username):
        raise ValueError("Invalid username")

    try:
        entity = await event.client.get_entity(username)
    except Exception as exc:
        raise LookupError("The target user could not be resolved.") from exc

    target_id = getattr(entity, "id", None)
    if target_id is None:
        raise LookupError("The target is not a valid Telegram user.")

    return int(target_id), username


def _join_allowed(game: Game, uid: Optional[int]) -> bool:
    if uid is None or uid == game.player_x:
        return False
    if game.private_target is not None and uid != game.private_target:
        return False
    return True


@in_pattern(re.compile(r"^xo(?:\s+(@[A-Za-z0-9_]{5,32}))?$"), owner=True)
async def xo_inline(event):
    player = await _sender(event)
    player_id = event.sender_id
    if player_id is None:
        return await event.answer([], cache_time=0)

    target_username = None
    private_target = None
    try:
        match = event.pattern_match
        if match:
            target_username = match.group(1)
        if target_username:
            private_target, target_username = await _resolve_private_target(
                event, target_username
            )

        if private_target == int(player_id):
            raise ValueError("You cannot create a private game with yourself.")

        _redis()
        game = None
        for _ in range(5):
            token = _new_token()
            candidate = Game(
                token=token,
                player_x=int(player_id),
                player_x_name=_name(player),
                board=[None] * 9,
                private_target=private_target,
                private_target_username=(target_username or "").lstrip("@"),
                updated_at=time.time(),
            )
            if await _redis_create(candidate):
                game = candidate
                break

        if game is None:
            raise RuntimeError("Could not allocate a unique XO token")

        description = (
            f"Private game for @{game.private_target_username}."
            if game.private_target
            else "Public two-player inline Tic-Tac-Toe. You are Player X."
        )
        result = await event.builder.article(
            title="🎮 Tic-Tac-Toe",
            description=description,
            text=_text(game),
            parse_mode="html",
            buttons=_buttons(game),
        )
        await event.answer([result], cache_time=0, private=True)
    except (ValueError, LookupError) as exc:
        await event.answer([], cache_time=0)
        LOGS.info("XO inline request rejected: %s", exc)
    except Exception:
        LOGS.exception("Failed to create XO game")
        await event.answer([], cache_time=0)


@callback(data=re.compile(r"xo:j:([A-Za-z0-9_]{8,32})"))
async def xo_join(event):
    token = _callback_token(event)
    user = await _sender(event)
    uid = event.sender_id
    if not token:
        return await _answer(event, "Invalid game reference.", True)

    try:
        async with _game_guard(token) as lock_value:
            game = await _load_locked(token, lock_value)
            if game is None:
                return await _answer(event, "This game no longer exists or has expired.", True)
            if game.status == "expired":
                await _render(event, game)
                return await _answer(event, "This game has expired.", True)
            if game.status != "waiting":
                return await _answer(event, "This game has already started.", True)
            if uid is None:
                return await _answer(event, "Your user identity could not be verified.", True)
            if not _join_allowed(game, uid):
                if uid == game.player_x:
                    message = "The game creator cannot join as Player O."
                else:
                    message = "This is a private game for another user."
                return await _answer(event, message, True)

            game.player_o = int(uid)
            game.player_o_name = _name(user)
            game.status = "playing"
            game.turn = "X"
            await _save(game, lock_value)
            await _render(event, game)
            await _answer(event, "You joined the game. Player X goes first.")
    except BusyGameError:
        await _answer(event, "This game is being updated. Please try again.", True)
    except LockLostError:
        await _answer(event, "The game state changed remotely. Please try again.", True)
    except Exception:
        LOGS.exception("XO join failed: %s", token)
        await _answer(event, "An error occurred while joining the game.", True)


async def _move(event, token: str, index: int):
    uid = event.sender_id
    try:
        async with _game_guard(token) as lock_value:
            game = await _load_locked(token, lock_value)
            if game is None:
                return await _answer(event, "This game no longer exists or has expired.", True)
            if game.status == "expired":
                await _render(event, game)
                return await _answer(event, "Your time expired. The game is over.", True)
            if game.status != "playing":
                return await _answer(event, "This game is no longer active.", True)

            mark = "X" if uid == game.player_x else "O" if uid == game.player_o else None
            if mark is None:
                return await _answer(event, "You are not one of the two players.", True)
            if game.turn != mark:
                return await _answer(event, "It is not your turn.", True)
            if game.board[index] is not None:
                return await _answer(event, "That square is already occupied.", True)

            game.board[index] = mark
            winner = _winner(game.board)
            if winner:
                game.status = "won"
                game.winner = winner
            elif all(game.board):
                game.status = "draw"
            else:
                game.turn = "O" if mark == "X" else "X"

            await _save(game, lock_value)
            await _render(event, game)

            if game.status == "won":
                await _answer(event, "🏆 You won!" if game.winner == mark else "You lost this game.")
            elif game.status == "draw":
                await _answer(event, "🤝 The game is a draw!")
            else:
                await _answer(event, "Move recorded.")
    except BusyGameError:
        await _answer(event, "This game is being updated. Please try again.", True)
    except LockLostError:
        await _answer(event, "The game state changed remotely. Please try again.", True)
    except Exception:
        LOGS.exception("XO move failed: %s", token)
        await _answer(event, "An error occurred while recording your move.", True)


@callback(data=re.compile(r"xo:m:([A-Za-z0-9_]{8,32}):([0-8])"))
async def xo_move(event):
    try:
        token = event.data_match.group(1).decode("utf-8")
        index = int(event.data_match.group(2).decode("utf-8"))
    except Exception:
        return await _answer(event, "Invalid move.", True)
    await _move(event, token, index)


@callback(data=re.compile(r"xo:n:([A-Za-z0-9_]{8,32}):([0-8])"))
async def xo_occupied(event):
    token = _callback_token(event)
    if not token:
        return await _answer(event, "Invalid game reference.", True)
    await _answer(event, "That square is already occupied.", True)


@callback(data=re.compile(r"xo:c:([A-Za-z0-9_]{8,32})"))
async def xo_cancel(event):
    token = _callback_token(event)
    if not token:
        return await _answer(event, "Invalid game reference.", True)

    try:
        async with _game_guard(token) as lock_value:
            game = await _load_locked(token, lock_value)
            if game is None:
                return await _answer(event, "This game no longer exists or has expired.", True)
            if game.status == "expired":
                await _render(event, game)
                return await _answer(event, "This game has already expired.", True)
            if game.status != "waiting":
                return await _answer(event, "Only a game that has not started can be cancelled.", True)
            if event.sender_id != game.player_x:
                return await _answer(event, "Only the game creator can cancel it.", True)

            game.status = "cancelled"
            await _save(game, lock_value)
            await _render(event, game)
            await _answer(event, "Game cancelled.")
    except BusyGameError:
        await _answer(event, "This game is being updated. Please try again.", True)
    except LockLostError:
        await _answer(event, "The game state changed remotely. Please try again.", True)
    except Exception:
        LOGS.exception("XO cancel failed: %s", token)
        await _answer(event, "An error occurred while cancelling the game.", True)


@callback(data=re.compile(r"xo:q:([A-Za-z0-9_]{8,32})"))
async def xo_resign(event):
    token = _callback_token(event)
    if not token:
        return await _answer(event, "Invalid game reference.", True)

    try:
        async with _game_guard(token) as lock_value:
            game = await _load_locked(token, lock_value)
            if game is None:
                return await _answer(event, "This game no longer exists or has expired.", True)
            if game.status == "expired":
                await _render(event, game)
                return await _answer(event, "Your time expired. The game is over.", True)
            if game.status != "playing":
                return await _answer(event, "This game is not active.", True)

            if event.sender_id == game.player_x:
                game.winner = "O"
            elif event.sender_id == game.player_o:
                game.winner = "X"
            else:
                return await _answer(event, "You are not one of the players.", True)

            game.status = "resigned"
            await _save(game, lock_value)
            await _render(event, game)
            await _answer(event, "You resigned from the game.")
    except BusyGameError:
        await _answer(event, "This game is being updated. Please try again.", True)
    except LockLostError:
        await _answer(event, "The game state changed remotely. Please try again.", True)
    except Exception:
        LOGS.exception("XO resign failed: %s", token)
        await _answer(event, "An error occurred while resigning.", True)


def _owner_id() -> Optional[int]:
    try:
        value = getattr(SUDO_M, "owner", None)
        if value is None:
            value = udB.get_key("OWNER_ID")
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _can_end_game(event, game: Game) -> bool:
    uid = event.sender_id
    if uid is None:
        return False
    return uid == game.player_x or uid == _owner_id()


async def _terminal_game(event, token: str) -> tuple[Optional[Game], Optional[str]]:
    game = await _load(token)
    if game is None:
        return None, "This game has already been closed or expired."
    if game.status not in _TERMINAL_STATUSES:
        return None, "You can only manage a game after it has ended."
    if not _can_end_game(event, game):
        return None, "Only the game creator or the bot owner can close this game."
    return game, None


@callback(data=re.compile(r"xo:e:([A-Za-z0-9_]{8,32})"))
async def xo_end_game(event):
    token = _callback_token(event)
    if not token:
        return await _answer(event, "Invalid game reference.", True)

    try:
        async with _game_guard(token):
            game, error = await _terminal_game(event, token)
            if error:
                return await _answer(event, error, True)
            await _render_confirmation(event, game)
            await _answer(event, "Please confirm that you want to close the game.")
    except BusyGameError:
        await _answer(event, "This game is being updated. Please try again.", True)
    except Exception:
        LOGS.exception("XO end-game confirmation failed: %s", token)
        await _answer(event, "An error occurred while opening the confirmation.", True)


@callback(data=re.compile(r"xo:b:([A-Za-z0-9_]{8,32})"))
async def xo_end_back(event):
    token = _callback_token(event)
    if not token:
        return await _answer(event, "Invalid game reference.", True)

    try:
        async with _game_guard(token):
            game, error = await _terminal_game(event, token)
            if error:
                return await _answer(event, error, True)
            await _render(event, game)
            await _answer(event, "Close cancelled.")
    except BusyGameError:
        await _answer(event, "This game is being updated. Please try again.", True)
    except Exception:
        LOGS.exception("XO end-game back failed: %s", token)
        await _answer(event, "An error occurred while returning to the game.", True)


@callback(data=re.compile(r"xo:y:([A-Za-z0-9_]{8,32})"))
async def xo_end_confirm(event):
    token = _callback_token(event)
    if not token:
        return await _answer(event, "Invalid game reference.", True)

    try:
        async with _game_guard(token):
            game, error = await _terminal_game(event, token)
            if error:
                return await _answer(event, error, True)

            await _redis_delete(game.token)
            await _render_closed(event)
            await _answer(event, "Game closed.")
    except BusyGameError:
        await _answer(event, "This game is being updated. Please try again.", True)
    except Exception:
        LOGS.exception("XO end-game confirmation failed: %s", token)
        await _answer(event, "An error occurred while closing the game.", True)


@callback(data=re.compile(r"xo:r:([A-Za-z0-9_]{8,32})"))
async def xo_rematch(event):
    token = _callback_token(event)
    if not token:
        return await _answer(event, "Invalid game reference.", True)

    try:
        async with _game_guard(token) as lock_value:
            old = await _load(token)
            if old is None:
                return await _answer(event, "The previous game no longer exists.", True)

            if old.status not in _TERMINAL_STATUSES:
                return await _answer(event, "The current game has not finished yet.", True)

            if event.sender_id not in {old.player_x, old.player_o}:
                return await _answer(event, "Only the previous players can start a rematch.", True)

            new_token = None
            for _ in range(5):
                candidate = _new_token()
                if await _redis_get(candidate) is None:
                    new_token = candidate
                    break
            if new_token is None:
                raise RuntimeError("Could not allocate a unique XO rematch token")

            if old.player_o is None:
                game = Game(
                    token=new_token,
                    player_x=old.player_x,
                    player_x_name=old.player_x_name,
                    board=[None] * 9,
                    private_target=old.private_target,
                    private_target_username=old.private_target_username,
                    updated_at=time.time(),
                )
            else:
                game = Game(
                    token=new_token,
                    player_x=old.player_o,
                    player_x_name=old.player_o_name,
                    board=[None] * 9,
                    player_o=old.player_x,
                    player_o_name=old.player_x_name,
                    private_target=None,
                    private_target_username="",
                    turn="X",
                    status="playing",
                    updated_at=time.time(),
                )

            if not await _redis_create(game):
                raise RuntimeError("Could not persist the XO rematch")

            try:
                await _render(event, game)
            except Exception:
                await _redis_delete(game.token)
                raise

            await _redis_delete(old.token)
            await _answer(event, "🔄 Rematch started. Player X goes first.")
    except BusyGameError:
        await _answer(event, "This game is being updated. Please try again.", True)
    except LockLostError:
        await _answer(event, "The game state changed remotely. Please try again.", True)
    except Exception:
        LOGS.exception("XO rematch failed: %s", token)
        await _answer(event, "An error occurred while starting the rematch.", True)
