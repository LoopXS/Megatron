"""Inline multiplayer quiz game for Megatron/CythonX.

Usage:
    @AssisXBot quiz

The inline creation panel is English-only. The quiz itself can be English or
Persian. Quiz state is stored in Redis and protected by a per-game distributed
lock. Active games are indexed in Redis so their timers can be restored after
process restarts.
"""
from __future__ import annotations

import asyncio
import html
import json
import math
import random
import re
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

from telethon import Button
from telethon.errors import FloodWaitError, MessageNotModifiedError
from telethon.tl.types import InputBotInlineMessageID, InputBotInlineMessageID64

from CythonX import LOGS, asst, udB
from CythonX._misc import SUDO_M
from CythonX._misc._assistant import callback, in_pattern

PREFIX = "cythonx:quiz:v3:"
DRAFT_TTL = 20 * 60
GAME_TTL = 6 * 60 * 60
LOCK_TTL_MS = 120_000
LOCK_REFRESH_MS = 20_000
TOKEN_RE = re.compile(r"^[A-Za-z0-9_]{8,24}$")
ROOT = Path(__file__).resolve().parent.parent / "resources" / "quiz"

CATEGORIES = {
    "general": ("🌎", "General Knowledge", "اطلاعات عمومی"),
    "science": ("🔬", "Science", "علوم"),
    "history": ("📜", "History", "تاریخ"),
    "geography": ("🗺", "Geography", "جغرافیا"),
    "technology": ("💻", "Technology", "فناوری"),
    "movies": ("🎬", "Movies & TV", "فیلم و سریال"),
    "games": ("🎮", "Video Games", "بازی‌های ویدیویی"),
    "sports": ("⚽", "Sports", "ورزش"),
    "music": ("🎵", "Music", "موسیقی"),
    "space": ("🚀", "Space", "فضا"),
    "animals": ("🐾", "Animals", "حیوانات"),
    "literature": ("📚", "Literature", "ادبیات"),
    "inventions": ("💡", "Inventions", "اختراعات"),
    "culture": ("🏛", "Culture & Art", "فرهنگ و هنر"),
    "psychology": ("🧠", "Psychology", "روان‌شناسی"),
}
CATEGORY_ORDER = list(CATEGORIES)
LANGUAGES = {"en": "🇬🇧 English", "fa": "🇮🇷 Persian"}
DIFFICULTIES = {"easy": "🟢 Easy", "medium": "🟡 Medium", "hard": "🔴 Hard", "mixed": "🎲 Mixed"}
QUESTION_CHOICES = (5, 10, 15, 20, 30, 40, 50, 60, 80, 100, 120, 160, 200, 240)
TIME_CHOICES = (5, 10, 15, 20, 30)
MIN_PLAYERS = 2
MIN_QUESTIONS = 5
MAX_QUESTIONS = 240
MAX_NAME = 40
TERMINAL = {"finished", "cancelled", "closed"}

_LOCAL_LOCKS = {}
_LOCAL_LOCK_REFS = {}
_LOCAL_LOCKS_GUARD = asyncio.Lock()
_GAME_TASKS = {}
_RECOVERY_STARTED = False
_RECOVERY_TASK = None
RECOVERY_INTERVAL = 30


class BusyQuizError(Exception):
    pass


class LockLostError(Exception):
    pass


def _redis():
    client = getattr(udB, "db", None)
    required = ("get", "set", "delete", "eval", "sadd", "srem", "smembers")
    if client is None or any(not hasattr(client, x) for x in required):
        raise RuntimeError("Quiz requires the project's Redis database")
    return client


def _decode(raw):
    return raw.decode("utf-8") if isinstance(raw, bytes) else raw


def _key(kind, token):
    return f"{PREFIX}{kind}:{token}"


def _index_key():
    return f"{PREFIX}active"


def _token():
    return secrets.token_urlsafe(12).replace("-", "_").replace("/", "_")[:18]


def _esc(value):
    return html.escape(str(value), quote=False)


def _clean_name(user):
    value = getattr(user, "first_name", None) or getattr(user, "username", None) or "Player"
    return str(value).replace("\n", " ").replace("\r", " ").strip()[:MAX_NAME] or "Player"


def _owner_id():
    try:
        value = getattr(SUDO_M, "owner", None) or udB.get_key("OWNER_ID")
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _authorized(uid):
    try:
        return uid is not None and int(uid) in set(SUDO_M.owner_and_sudos())
    except Exception:
        return False


async def _get_json(key):
    def read():
        raw = _redis().get(key)
        return None if raw is None else json.loads(_decode(raw))
    return await asyncio.to_thread(read)


async def _set_json(key, value, ttl, nx=False):
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return await asyncio.to_thread(lambda: bool(_redis().set(key, payload, ex=ttl, nx=nx)))


async def _delete(key):
    await asyncio.to_thread(lambda: _redis().delete(key))


async def _index_add(token):
    await asyncio.to_thread(lambda: _redis().sadd(_index_key(), token) if hasattr(_redis(), "sadd") else None)


async def _index_remove(token):
    await asyncio.to_thread(lambda: _redis().srem(_index_key(), token) if hasattr(_redis(), "srem") else None)


async def _lock(token, value):
    return await asyncio.to_thread(lambda: bool(_redis().set(_key("lock", token), value, nx=True, px=LOCK_TTL_MS)))


async def _unlock(token, value):
    script = """
    if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) end
    return 0
    """
    await asyncio.to_thread(lambda: _redis().eval(script, 1, _key("lock", token), value))


async def _refresh_lock(token, value):
    script = """
    if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('pexpire', KEYS[1], ARGV[2]) end
    return 0
    """
    return bool(await asyncio.to_thread(lambda: _redis().eval(script, 1, _key("lock", token), value, str(LOCK_TTL_MS))))


async def _heartbeat(token, value, stop):
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), LOCK_REFRESH_MS / 1000)
        except asyncio.TimeoutError:
            if not await _refresh_lock(token, value):
                LOGS.error("Quiz Redis lock lost: %s", token)
                return


@asynccontextmanager
async def _guard(token):
    async with _LOCAL_LOCKS_GUARD:
        lock = _LOCAL_LOCKS.setdefault(token, asyncio.Lock())
        _LOCAL_LOCK_REFS[token] = _LOCAL_LOCK_REFS.get(token, 0) + 1
    try:
        async with lock:
            value = secrets.token_urlsafe(20)
            if not await _lock(token, value):
                raise BusyQuizError
            stop = asyncio.Event()
            heartbeat = asyncio.create_task(_heartbeat(token, value, stop))
            try:
                yield value
            finally:
                stop.set()
                heartbeat.cancel()
                try:
                    await heartbeat
                except asyncio.CancelledError:
                    pass
                try:
                    await _unlock(token, value)
                except Exception:
                    LOGS.exception("Quiz lock release failed: %s", token)
    finally:
        async with _LOCAL_LOCKS_GUARD:
            refs = _LOCAL_LOCK_REFS.get(token, 1) - 1
            if refs <= 0:
                _LOCAL_LOCK_REFS.pop(token, None)
                _LOCAL_LOCKS.pop(token, None)
            else:
                _LOCAL_LOCK_REFS[token] = refs


def _as_int(value):
    return int(value)


def _player_ids(g):
    return [_as_int(uid) for uid in g.get("players", [])]


def _has_player(g, uid):
    return _as_int(uid) in _player_ids(g)


def _question_seconds(g):
    try:
        return max(1, int(g.get("time", 15)))
    except (TypeError, ValueError):
        return 15


def _arm_question(g):
    """Arm a full per-question timer starting now."""
    now = time.time()
    seconds = _question_seconds(g)
    g["started_at"] = now
    g["deadline"] = now + seconds
    return seconds


def _remaining_seconds(g):
    try:
        return max(0.0, float(g.get("deadline", 0.0)) - time.time())
    except (TypeError, ValueError):
        return 0.0



def _elapsed_seconds(g, now=None):
    now = time.time() if now is None else float(now)
    started = g.get("started_at")
    if started is None:
        try:
            started = float(g.get("deadline", now)) - _question_seconds(g)
        except (TypeError, ValueError):
            started = now
    return max(0.0, min(now - float(started), float(_question_seconds(g))))


def _draft_defaults(uid, name):
    return {
        "token": _token(), "owner_id": int(uid), "owner_name": name,
        "max_players": None, "question_count": 5, "time": 15,
        "difficulty": "mixed", "category": "general", "language": "en",
        "created_at": time.time(),
    }


def _bank_pool(lang, category, difficulty):
    categories = CATEGORY_ORDER if category == "mixed" else [category]
    pool = []
    for cat in categories:
        path = ROOT / lang / f"{cat}.json"
        if not path.is_file():
            raise ValueError(f"Question bank is missing: {lang}/{cat}.json")
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if data.get("language") != lang or data.get("category") != cat:
            raise ValueError(f"Invalid question bank metadata: {path.name}")
        questions = data.get("questions")
        if not isinstance(questions, list):
            raise ValueError(f"Invalid question list: {path.name}")
        pool.extend(questions)
    if difficulty != "mixed":
        pool = [q for q in pool if q.get("difficulty") == difficulty]
    return pool


def _max_available_questions(lang, category, difficulty):
    return len(_bank_pool(lang, category, difficulty))


def _validate_settings(d):
    # Player count is unlimited — any number of players may join a lobby.
    d["max_players"] = None
    if int(d["time"]) not in TIME_CHOICES:
        raise ValueError("Invalid question timer.")
    if d["difficulty"] not in DIFFICULTIES or d["language"] not in LANGUAGES:
        raise ValueError("Invalid quiz setting.")
    if d["category"] != "mixed" and d["category"] not in CATEGORIES:
        raise ValueError("Invalid category.")
    available = _max_available_questions(d["language"], d["category"], d["difficulty"])
    maximum = min(MAX_QUESTIONS, available)
    if maximum < MIN_QUESTIONS:
        raise ValueError(f"This selection has only {available} usable questions; at least {MIN_QUESTIONS} are required.")
    if not MIN_QUESTIONS <= int(d["question_count"]) <= maximum:
        raise ValueError(f"This selection has {available} usable questions. Choose between {MIN_QUESTIONS} and {maximum}.")


def _draft_text(d):
    cat = "Mixed" if d["category"] == "mixed" else CATEGORIES[d["category"]][1]
    return (
        "🧠 <b>Quiz Battle</b>\n\nConfigure your game before creating the lobby.\n\n"
        f"❓ <b>Questions:</b> {d['question_count']}\n"
        f"⏱ <b>Time / Question:</b> {d['time']}s\n"
        f"🎯 <b>Difficulty:</b> {DIFFICULTIES[d['difficulty']]}\n"
        f"📚 <b>Category:</b> {cat}\n"
        f"🌐 <b>Game Language:</b> {LANGUAGES[d['language']]}"
    )


def _draft_buttons(d):
    t = d["token"]
    return [
        [Button.inline("❓ Questions", data=f"q2:d:q:{t}"), Button.inline("⏱ Time", data=f"q2:d:t:{t}")],
        [Button.inline("🎯 Difficulty", data=f"q2:d:f:{t}"), Button.inline("📚 Category", data=f"q2:d:c:{t}")],
        [Button.inline("🌐 Language", data=f"q2:d:l:{t}")],
        [Button.inline("🚀 Create Game", data=f"q2:d:x:{t}")],
        [Button.inline("✖️ Cancel", data=f"q2:d:e:{t}")],
    ]


def _choice_buttons(kind, token, draft=None):
    if kind == "q":
        available = MAX_QUESTIONS
        if draft is not None:
            try:
                available = min(MAX_QUESTIONS, _max_available_questions(draft["language"], draft["category"], draft["difficulty"]))
            except Exception:
                available = MIN_QUESTIONS - 1
        choices = [x for x in QUESTION_CHOICES if x <= available]
        rows = [[Button.inline(str(x), data=f"q2:s:q:{token}:{x}") for x in choices]] if choices else []
        rows += [[Button.switch_inline("🔢 Custom", query=f"quizset {token} questions ", same_peer=True)]]
    elif kind == "t":
        rows = [[Button.inline(f"{x}s", data=f"q2:s:t:{token}:{x}") for x in TIME_CHOICES]]
    elif kind == "f":
        rows = [[Button.inline("🟢 Easy", data=f"q2:s:f:{token}:easy"), Button.inline("🟡 Medium", data=f"q2:s:f:{token}:medium")], [Button.inline("🔴 Hard", data=f"q2:s:f:{token}:hard"), Button.inline("🎲 Mixed", data=f"q2:s:f:{token}:mixed")]]
    else:
        rows = [[Button.inline("🇬🇧 English", data=f"q2:s:l:{token}:en"), Button.inline("🇮🇷 Persian", data=f"q2:s:l:{token}:fa")]]
    rows.append([Button.inline("↩️ Back", data=f"q2:d:b:{token}")])
    return rows


def _category_buttons(token):
    rows, row = [], []
    for key in CATEGORY_ORDER:
        icon, name, _ = CATEGORIES[key]
        row.append(Button.inline(f"{icon} {name}", data=f"q2:s:c:{token}:{key}"))
        if len(row) == 2:
            rows.append(row); row = []
    if row: rows.append(row)
    rows += [[Button.inline("🎲 Mixed", data=f"q2:s:c:{token}:mixed")], [Button.inline("↩️ Back", data=f"q2:d:b:{token}")]]
    return rows


def _lobby_text(g):
    lines = []
    for uid in g["players"]:
        prefix = "👑" if uid == g["host_id"] else "👤"
        lines.append(f"{prefix} <b>{_esc(g['names'].get(str(uid), 'Player'))}</b>")
    cat = "Mixed" if g["category"] == "mixed" else CATEGORIES[g["category"]][1]
    return (
        "🧠 <b>Quiz Lobby</b>\n\n"
        f"👥 <b>Players:</b> {len(g['players'])}\n\n" + "\n".join(lines) +
        "\n\n━━━━━━━━━━━━━━\n"
        f"❓ <b>Questions:</b> {g['question_count']}\n"
        f"⏱ <b>Time:</b> {g['time']}s / question\n"
        f"🎯 <b>Difficulty:</b> {DIFFICULTIES[g['difficulty']]}\n"
        f"📚 <b>Category:</b> {cat}\n"
        f"🌐 <b>Language:</b> {LANGUAGES[g['language']]}\n\n"
        "Any number of players can join. The host can start once at least 2 players are ready."
    )


def _lobby_buttons(g):
    t = g["token"]
    return [[Button.inline("➕ Join Game", data=f"q2:j:{t}")], [Button.inline("🚀 Start Quiz", data=f"q2:srt:{t}")], [Button.inline("🚪 Leave", data=f"q2:lve:{t}"), Button.inline("✖️ Cancel", data=f"q2:cnl:{t}")]]


def _game_text(g, final=False):
    fa = g["language"] == "fa"
    if final or g["status"] == "finished":
        ranked = sorted(g["scores"].items(), key=lambda kv: (-int(kv[1]), g["names"].get(str(kv[0]), "").lower()))
        title = "🏆 <b>پایان مسابقه</b>" if fa else "🏆 <b>Quiz Finished</b>"
        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, (uid, score) in enumerate(ranked):
            prefix = medals[i] if i < 3 else f"{i + 1}."
            name = _esc(g["names"].get(str(uid), "Player"))
            circles = _result_circles(g, uid)
            lines.append(f"{prefix} <b>{name}</b> — {int(score)}")
            if circles:
                lines.append(circles)
        legend = "🟢 درست · 🔴 نادرست · ⚪ بی‌پاسخ" if fa else "🟢 correct · 🔴 wrong · ⚪ not answered"
        body = "\n".join(lines) if lines else ""
        return (
            title + "\n\n" + body +
            f"\n\n{legend}\n"
            f"👥 {'بازیکنان' if fa else 'Players'}: {len(g['players'])}\n"
            f"❓ {'سؤال' if fa else 'Questions'}: {len(g['questions'])}"
        )
    q = g["questions"][g["current"]]
    limit = _question_seconds(g)
    title = f"🧠 <b>سؤال {g['current'] + 1} از {len(g['questions'])}</b>" if fa else f"🧠 <b>Question {g['current'] + 1}/{len(g['questions'])}</b>"
    text = title + "\n\n<b>" + _esc(q["question"]) + "</b>\n\n"
    marks = ["🔴", "🔵", "🟢", "🟡"]
    for i, option in enumerate(q["options"]):
        text += f"{marks[i]} <b>{_esc(option)}</b>\n"
    answered = len(g.get("answers") or {})
    total = len(_player_ids(g))
    if fa:
        text += f"\n⏱ <b>مهلت:</b> {limit} ثانیه\n👥 پاسخ داده‌اند: {answered}/{total}"
    else:
        text += f"\n⏱ <b>Time limit:</b> {limit}s\n👥 Answered: {answered}/{total}"
    return text


def _record_round_results(g):
    """Append per-player correct/wrong/skip markers for the current question."""
    questions = g.get("questions") or []
    current = int(g.get("current", 0))
    if not questions or current < 0 or current >= len(questions):
        return
    correct = int(questions[current]["answer"])
    answers = g.get("answers") or {}
    log = g.setdefault("answer_log", {})
    for uid in _player_ids(g):
        key = str(uid)
        log.setdefault(key, [])
        ans = answers.get(key)
        if not ans:
            log[key].append("skip")
        else:
            try:
                log[key].append("correct" if int(ans["choice"]) == correct else "wrong")
            except (TypeError, ValueError, KeyError):
                log[key].append("skip")


def _result_circles(g, uid):
    markers = {"correct": "🟢", "wrong": "🔴", "skip": "⚪"}
    seq = (g.get("answer_log") or {}).get(str(uid), [])
    if not seq:
        # Fallback for older games without a log: one white per question.
        n = len(g.get("questions") or [])
        return "⚪" * n if n else ""
    return "".join(markers.get(item, "⚪") for item in seq)


def _choice_feedback(g, choice):
    """Immediate alert text for a player's answer."""
    fa = g.get("language") == "fa"
    q = g["questions"][int(g["current"])]
    correct = int(q["answer"])
    correct_text = str(q["options"][correct])
    if int(choice) == correct:
        return "✅ پاسخ درست!" if fa else "✅ Correct!"
    if fa:
        return f"❌ پاسخ نادرست!\nپاسخ صحیح: {correct_text}"
    return f"❌ Incorrect!\nCorrect answer: {correct_text}"


def _remember_message(g, event):
    """Persist the editable message target.

    Inline quiz messages MUST be edited via InputBotInlineMessageID(64).
    Numeric chat/message ids reconstructed by Telethon for inline callbacks
    do not work with asst.edit_message(), which is why background timers
    previously looked frozen until someone pressed a button (event.edit).
    """
    query = getattr(event, "query", None)
    msg_id = getattr(query, "msg_id", None) if query is not None else None
    if isinstance(msg_id, (InputBotInlineMessageID, InputBotInlineMessageID64)):
        g["inline_msg"] = msg_id.to_dict()
        g.pop("message_chat_id", None)
        g.pop("message_id", None)
        return
    chat_id = getattr(event, "chat_id", None)
    message_id = getattr(event, "message_id", None)
    if chat_id is not None and message_id is not None and not isinstance(message_id, (InputBotInlineMessageID, InputBotInlineMessageID64)):
        try:
            g["message_chat_id"] = int(chat_id)
            g["message_id"] = int(message_id)
            g.pop("inline_msg", None)
        except (TypeError, ValueError):
            pass


def _inline_entity(g):
    data = g.get("inline_msg")
    if not isinstance(data, dict):
        return None
    kind = data.get("_")
    try:
        if kind == "InputBotInlineMessageID64":
            return InputBotInlineMessageID64(
                dc_id=int(data["dc_id"]),
                owner_id=int(data["owner_id"]),
                id=int(data["id"]),
                access_hash=int(data["access_hash"]),
            )
        if kind == "InputBotInlineMessageID":
            return InputBotInlineMessageID(
                dc_id=int(data["dc_id"]),
                id=int(data["id"]),
                access_hash=int(data["access_hash"]),
            )
    except (KeyError, TypeError, ValueError):
        return None
    return None


def _answer_buttons(g):
    t = g["token"]; q = g["questions"][g["current"]]; marks = ["🔴", "🔵", "🟢", "🟡"]
    resign = "🏳️ انصراف" if g["language"] == "fa" else "🏳️ Resign"
    return [[Button.inline(f"{marks[i]} {str(opt)[:24]}", data=f"q2:a:{t}:{i}")] for i, opt in enumerate(q["options"])] + [[Button.inline(resign, data=f"q2:rsg:{t}")]]


def _terminal_buttons(g):
    t = g["token"]
    return [[Button.inline("🔄 Rematch", data=f"q2:rem:{t}")], [Button.inline("✖️ End Game", data=f"q2:end:{t}")]]


def _make_questions(g):
    pool = _bank_pool(g["language"], g["category"], g["difficulty"])
    count = int(g["question_count"])
    if len(pool) < count:
        raise ValueError(f"Only {len(pool)} questions are available for this selection.")
    selected = random.sample(pool, count)
    prepared = []
    for source in selected:
        q = dict(source)
        options = list(q["options"])
        answer = int(q["answer"])
        if not 0 <= answer < len(options) or len(options) != 4:
            raise ValueError(f"Invalid question format: {q.get('id', 'unknown')}")
        correct = options[answer]
        random.shuffle(options)
        q["options"] = options
        q["answer"] = options.index(correct)
        prepared.append(q)
    return prepared


async def _save(g, lock_value):
    g["updated_at"] = time.time()
    payload = json.dumps(g, ensure_ascii=False, separators=(",", ":"))
    script = """
    if redis.call('get', KEYS[1]) ~= ARGV[1] then return 0 end
    redis.call('set', KEYS[2], ARGV[2], 'EX', ARGV[3])
    return 1
    """
    ok = await asyncio.to_thread(lambda: _redis().eval(script, 2, _key("lock", g["token"]), _key("game", g["token"]), lock_value, payload, str(GAME_TTL)))
    if not ok:
        raise LockLostError


async def _load(token):
    return await _get_json(_key("game", token))


async def _render(event, g, final=False):
    buttons = _terminal_buttons(g) if final or g["status"] == "finished" else _answer_buttons(g)
    # Keep the inline target fresh on every user interaction.
    _remember_message(g, event)
    try:
        await event.edit(_game_text(g, final), buttons=buttons, parse_mode="html", link_preview=False)
    except MessageNotModifiedError:
        pass


async def _render_lobby(event, g):
    _remember_message(g, event)
    try:
        await event.edit(_lobby_text(g), buttons=_lobby_buttons(g), parse_mode="html", link_preview=False)
    except MessageNotModifiedError:
        pass


async def _answer(event, text, alert=False):
    try:
        await event.answer(str(text), cache_time=0, alert=alert)
    except Exception:
        pass


def _valid(token):
    return bool(TOKEN_RE.fullmatch(token or ""))


def _settle_round(g):
    """Score the current question and either finish or arm the next timer."""
    questions = g.get("questions") or []
    current = int(g.get("current", 0))
    if not questions or current < 0 or current >= len(questions):
        g["status"] = "finished"
        g["finished_at"] = time.time()
        return True

    _record_round_results(g)
    q = questions[current]
    for uid, answer in list((g.get("answers") or {}).items()):
        if answer.get("scored"):
            continue
        try:
            choice = int(answer["choice"])
            correct = int(q["answer"])
        except (TypeError, ValueError, KeyError):
            answer["scored"] = True
            continue
        if choice == correct:
            elapsed = min(float(answer.get("elapsed", _question_seconds(g))), float(_question_seconds(g)))
            bonus = max(0, int(round(5 * (1 - elapsed / max(1, _question_seconds(g))))))
            g["scores"][str(uid)] = int(g["scores"].get(str(uid), 0)) + 10 + bonus
        answer["scored"] = True

    if current + 1 >= len(questions):
        g["status"] = "finished"
        g["finished_at"] = time.time()
        return True

    g["current"] = current + 1
    g["answers"] = {}
    _arm_question(g)
    return False


async def _render_saved(g, final=False):
    buttons = _terminal_buttons(g) if final or g.get("status") == "finished" else _answer_buttons(g)
    text = _game_text(g, final)
    inline = _inline_entity(g)
    try:
        if inline is not None:
            await asst.edit_message(
                inline,
                text,
                buttons=buttons,
                parse_mode="html",
                link_preview=False,
            )
            return True
        chat_id = g.get("message_chat_id")
        message_id = g.get("message_id")
        if chat_id is None or message_id is None:
            LOGS.warning("Quiz %s has no editable message target", g.get("token"))
            return False
        await asst.edit_message(
            int(chat_id),
            int(message_id),
            text,
            buttons=buttons,
            parse_mode="html",
            link_preview=False,
        )
        return True
    except MessageNotModifiedError:
        return True
    except FloodWaitError as exc:
        LOGS.warning("Quiz edit flood wait %ss for %s", getattr(exc, "seconds", "?"), g.get("token"))
        try:
            await asyncio.sleep(min(int(getattr(exc, "seconds", 1)) + 1, 8))
        except Exception:
            pass
        return False
    except Exception:
        LOGS.exception("Quiz message edit failed: %s", g.get("token"))
        return False


async def _advance_if_due(token):
    """Settle the current question once its deadline has passed. Returns (game, finished|None).

    finished is None when nothing changed; True/False after a successful settle.
    """
    try:
        async with _guard(token) as lock:
            g = await _load(token)
            if not g or g.get("status") != "playing":
                return g, None
            if _remaining_seconds(g) > 0.05:
                return g, None
            question_index = int(g.get("current", 0))
            finished = _settle_round(g)
            await _save(g, lock)
            if finished:
                await _index_remove(token)
            # Guard against double-advance races: only one settle per call.
            if not finished and int(g.get("current", -1)) == question_index:
                LOGS.error("Quiz settle did not advance question for %s", token)
            return g, finished
    except BusyQuizError:
        return None, None


async def _scheduler(token):
    """Wait for each question deadline and auto-advance without live UI ticks."""
    try:
        while True:
            try:
                g = await _load(token)
                if not g or g.get("status") != "playing":
                    return

                question_index = int(g.get("current", 0))
                deadline = float(g.get("deadline", 0.0))

                # Wait until this question's deadline. Re-check periodically so
                # early advances (everyone answered) are picked up, but do NOT
                # edit the message on each tick (that caused FloodWait).
                while True:
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        break
                    await asyncio.sleep(min(1.0, remaining))
                    latest = await _load(token)
                    if not latest or latest.get("status") != "playing":
                        return
                    if int(latest.get("current", -1)) != question_index:
                        break
                    new_deadline = float(latest.get("deadline", 0.0))
                    if abs(new_deadline - deadline) > 0.01:
                        deadline = new_deadline

                latest = await _load(token)
                if not latest or latest.get("status") != "playing":
                    return
                if int(latest.get("current", -1)) != question_index:
                    continue

                g, finished = await _advance_if_due(token)
                if finished is None:
                    await asyncio.sleep(0.2)
                    continue

                await _render_saved(g, final=bool(finished))
                if finished:
                    return
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGS.exception("Quiz scheduler iteration failed: %s", token)
                await asyncio.sleep(1.0)
    finally:
        task = _GAME_TASKS.get(token)
        current = asyncio.current_task()
        if task is current:
            _GAME_TASKS.pop(token, None)


def _client_loop():
    try:
        return asst.loop
    except Exception:
        return asyncio.get_running_loop()


def _ensure_scheduler(token):
    task = _GAME_TASKS.get(token)
    if task and not task.done():
        return
    try:
        loop = _client_loop()
        _GAME_TASKS[token] = loop.create_task(_scheduler(token))
    except RuntimeError:
        _GAME_TASKS.pop(token, None)


async def _recover_games():
    """Attach local schedulers to persisted playing games. Safe to repeat."""
    redis = _redis()
    if not hasattr(redis, "smembers"):
        return
    raw_tokens = await asyncio.to_thread(redis.smembers, _index_key())
    for raw in raw_tokens or []:
        token = _decode(raw)
        if not _valid(token):
            continue
        try:
            game = await _load(token)
            if not game:
                await _index_remove(token)
                continue
            if game.get("status") == "playing":
                _ensure_scheduler(token)
            elif game.get("status") in TERMINAL:
                await _index_remove(token)
        except Exception:
            LOGS.exception("Quiz recovery failed for game: %s", token)

async def _recovery_watchdog():
    while True:
        try:
            await _recover_games()
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGS.exception("Quiz recovery watchdog failed")
        await asyncio.sleep(RECOVERY_INTERVAL)

def _start_recovery():
    global _RECOVERY_STARTED, _RECOVERY_TASK
    if _RECOVERY_STARTED:
        return
    try:
        loop = _client_loop()
    except Exception:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
    _RECOVERY_STARTED = True
    _RECOVERY_TASK = loop.create_task(_recovery_watchdog())


@in_pattern(re.compile(r"^quiz(?:\s+.*)?$"), owner=True)
async def quiz_inline(event):
    _start_recovery()
    uid = event.sender_id
    if uid is None:
        return await event.answer([], cache_time=0)
    query = (getattr(event, "text", "") or "").strip()
    if query.lower() != "quiz":
        return await event.answer([], cache_time=0)
    try:
        draft = _draft_defaults(uid, _clean_name(await event.get_sender()))
        await _set_json(_key("draft", draft["token"]), draft, DRAFT_TTL, nx=True)
        result = await event.builder.article(title="🧠 Quiz Battle", description="Configure a multiplayer quiz", text=_draft_text(draft), parse_mode="html", buttons=_draft_buttons(draft))
        await event.answer([result], cache_time=0, private=True)
    except Exception:
        LOGS.exception("Quiz inline failed")
        await event.answer([], cache_time=0)


@callback(data=re.compile(r"q2:d:([pqtflcxb]):([A-Za-z0-9_]{8,24})"))
async def quiz_draft_menu(event):
    kind, token = event.data_match.group(1).decode(), event.data_match.group(2).decode()
    draft = await _get_json(_key("draft", token))
    if not draft or event.sender_id != int(draft["owner_id"]):
        return await _answer(event, "Only the quiz creator can change these settings.", True)
    if kind == "x":
        try:
            _validate_settings(draft)
        except ValueError as exc:
            return await _answer(event, str(exc), True)
        g = {**draft, "status": "lobby", "host_id": int(draft["owner_id"]), "host_name": draft["owner_name"], "players": [int(draft["owner_id"])], "names": {str(draft["owner_id"]): draft["owner_name"]}, "scores": {str(draft["owner_id"]): 0}, "questions": [], "current": 0, "answers": {}, "deadline": 0.0, "updated_at": time.time(), "max_players": None}
        if await _set_json(_key("game", token), g, GAME_TTL, nx=True):
            await _index_add(token)
            await _delete(_key("draft", token))
            return await _render_lobby(event, g)
        return await _answer(event, "Could not create the game. Please try again.", True)
    if kind == "e":
        await _delete(_key("draft", token))
        return await event.edit("❌ <b>Quiz creation cancelled.</b>", buttons=[], parse_mode="html")
    if kind == "b":
        return await event.edit(_draft_text(draft), buttons=_draft_buttons(draft), parse_mode="html")
    if kind == "c":
        return await event.edit("📚 <b>Choose a category</b>", buttons=_category_buttons(token), parse_mode="html")
    labels = {"q": "❓ Number of Questions", "t": "⏱ Time per Question", "f": "🎯 Difficulty", "l": "🌐 Game Language"}
    if kind == "p":
        return await _answer(event, "Player limit is disabled — anyone can join.", True)
    await event.edit(f"<b>{labels[kind]}</b>", buttons=_choice_buttons(kind, token, draft), parse_mode="html")


@callback(data=re.compile(r"q2:c:([A-Za-z0-9_]{8,24}):(q)"))
async def quiz_custom(event):
    token, kind = event.data_match.group(1).decode(), event.data_match.group(2).decode()
    draft = await _get_json(_key("draft", token))
    if not draft or event.sender_id != int(draft["owner_id"]):
        return await _answer(event, "Only the quiz creator can set custom values.", True)
    available = min(MAX_QUESTIONS, _max_available_questions(draft["language"], draft["category"], draft["difficulty"]))
    text = f"<b>Custom Questions</b>\n\nType this in the inline query:\n<code>@AssisXBot quizset {token} questions 10</code>\n\nAllowed: {MIN_QUESTIONS}-{available}."
    await event.edit(text, buttons=[[Button.inline("↩️ Back", data=f"q2:d:b:{token}")]], parse_mode="html")


@in_pattern(re.compile(r"^quizset\s+[A-Za-z0-9_]{8,24}\s+(questions)\s+\d+$"), owner=True)
async def quiz_custom_inline(event):
    parts = (getattr(event, "text", "") or "").split()
    if len(parts) != 4:
        return await event.answer([], cache_time=0)
    token, setting = parts[1], parts[2].lower()
    try:
        value = int(parts[3])
    except ValueError:
        return await event.answer([], cache_time=0)
    draft = await _get_json(_key("draft", token))
    if not draft or int(draft["owner_id"]) != int(event.sender_id):
        return await event.answer([], cache_time=0)
    if setting != "questions":
        return await event.answer([], cache_time=0)
    available = min(MAX_QUESTIONS, _max_available_questions(draft["language"], draft["category"], draft["difficulty"]))
    if available < MIN_QUESTIONS or not MIN_QUESTIONS <= value <= available:
        return await event.answer([], cache_time=0)
    draft["question_count"] = value
    draft["max_players"] = None
    await _set_json(_key("draft", token), draft, DRAFT_TTL)
    result = await event.builder.article(title="🧠 Quiz Settings Updated", description="Your custom value was applied", text=_draft_text(draft), parse_mode="html", buttons=_draft_buttons(draft))
    await event.answer([result], cache_time=0, private=True)


@callback(data=re.compile(r"q2:s:([pq tflc]):([A-Za-z0-9_]{8,24}):([A-Za-z0-9_]+)".replace(" ", "")))
async def quiz_set(event):
    kind, token, value = event.data_match.group(1).decode(), event.data_match.group(2).decode(), event.data_match.group(3).decode()
    draft = await _get_json(_key("draft", token))
    if not draft or event.sender_id != int(draft["owner_id"]):
        return await _answer(event, "Only the quiz creator can change settings.", True)
    if kind == "p":
        draft["max_players"] = None
    elif kind == "q": draft["question_count"] = int(value)
    elif kind == "t": draft["time"] = int(value)
    elif kind == "f": draft["difficulty"] = value
    elif kind == "l": draft["language"] = value
    elif kind == "c": draft["category"] = value
    draft["max_players"] = None
    if kind in {"q", "l", "f", "c"}:
        available = _max_available_questions(draft["language"], draft["category"], draft["difficulty"])
        if available < MIN_QUESTIONS:
            return await _answer(event, f"This selection has only {available} usable questions. Choose another category, language, or difficulty.", True)
        draft["question_count"] = min(int(draft["question_count"]), min(MAX_QUESTIONS, available))
    try:
        _validate_settings(draft)
    except ValueError as exc:
        return await _answer(event, str(exc), True)
    await _set_json(_key("draft", token), draft, DRAFT_TTL)
    await event.edit(_draft_text(draft), buttons=_draft_buttons(draft), parse_mode="html")


@callback(data=re.compile(r"q2:j:([A-Za-z0-9_]{8,24})"))
async def quiz_join(event):
    token = event.data_match.group(1).decode(); uid = _as_int(event.sender_id)
    try:
        async with _guard(token) as lock:
            g = await _load(token)
            if not g or g.get("status") != "lobby":
                return await _answer(event, "This quiz is no longer accepting players.", True)
            if _has_player(g, uid):
                return await _answer(event, "You are already in this lobby.", True)
            # No player cap — any number of players may join.
            g["max_players"] = None
            user = await event.get_sender()
            g["players"] = _player_ids(g) + [uid]
            g["names"][str(uid)] = _clean_name(user)
            g["scores"][str(uid)] = 0
            _remember_message(g, event)
            await _save(g, lock)
            await _render_lobby(event, g)
            await _answer(event, "You joined the quiz.")
    except BusyQuizError:
        await _answer(event, "The lobby is busy. Please try again.", True)
    except Exception:
        LOGS.exception("Quiz join failed: %s", token)
        await _answer(event, "Could not join the quiz.", True)


@callback(data=re.compile(r"q2:srt:([A-Za-z0-9_]{8,24})"))
async def quiz_start(event):
    token = event.data_match.group(1).decode()
    try:
        async with _guard(token) as lock:
            g = await _load(token)
            if not g or g.get("status") != "lobby":
                return await _answer(event, "This quiz is no longer waiting to start.", True)
            if _as_int(event.sender_id) != _as_int(g["host_id"]):
                return await _answer(event, "Only the game creator can start the quiz.", True)
            g["players"] = _player_ids(g)
            if len(g["players"]) < MIN_PLAYERS:
                return await _answer(event, "At least 2 players are required.", True)
            g["questions"] = _make_questions(g)
            g["status"] = "playing"
            g["current"] = 0
            g["answers"] = {}
            g["answer_log"] = {str(uid): [] for uid in g["players"]}
            g["scores"] = {str(uid): int(g.get("scores", {}).get(str(uid), 0)) for uid in g["players"]}
            _arm_question(g)
            _remember_message(g, event)
            if not g.get("inline_msg") and g.get("message_chat_id") is None:
                LOGS.warning("Quiz %s started without a message edit target", token)
            await _save(g, lock)
            await _render(event, g)
            # Persist inline target again in case render refreshed it.
            _remember_message(g, event)
            try:
                await _save(g, lock)
            except LockLostError:
                pass
        _ensure_scheduler(token)
        await _answer(event, "Quiz started! Good luck.")
    except ValueError as exc:
        await _answer(event, str(exc), True)
    except BusyQuizError:
        await _answer(event, "The quiz is being updated. Try again.", True)
    except Exception:
        LOGS.exception("Quiz start failed: %s", token)
        await _answer(event, "Could not start the quiz.", True)


@callback(data=re.compile(r"q2:lve:([A-Za-z0-9_]{8,24})"))
async def quiz_leave(event):
    token = event.data_match.group(1).decode(); uid = _as_int(event.sender_id)
    try:
        async with _guard(token) as lock:
            g = await _load(token)
            if not g or g.get("status") != "lobby":
                return await _answer(event, "Leaving is only available before the quiz starts.", True)
            if uid == _as_int(g["host_id"]):
                return await _answer(event, "The host cannot leave. Cancel the game instead.", True)
            if not _has_player(g, uid):
                return await _answer(event, "You are not in this lobby.", True)
            g["players"] = [p for p in _player_ids(g) if p != uid]
            g["names"].pop(str(uid), None); g["scores"].pop(str(uid), None)
            await _save(g, lock); await _render_lobby(event, g); await _answer(event, "You left the lobby.")
    except Exception:
        LOGS.exception("Quiz leave failed: %s", token)
        await _answer(event, "Could not leave the lobby.", True)


@callback(data=re.compile(r"q2:cnl:([A-Za-z0-9_]{8,24})"))
async def quiz_cancel(event):
    token = event.data_match.group(1).decode()
    try:
        async with _guard(token) as lock:
            g = await _load(token)
            if not g or g.get("status") != "lobby":
                return await _answer(event, "This lobby is no longer active.", True)
            if int(event.sender_id) != int(g["host_id"]) and int(event.sender_id) != _owner_id():
                return await _answer(event, "Only the host or bot owner can cancel this game.", True)
            g["status"] = "cancelled"
            await _save(g, lock)
            await _index_remove(token)
            await event.edit("❌ <b>Quiz cancelled.</b>", buttons=[], parse_mode="html")
    except Exception:
        LOGS.exception("Quiz cancel failed: %s", token)
        await _answer(event, "Could not cancel the quiz.", True)


@callback(data=re.compile(r"q2:a:([A-Za-z0-9_]{8,24}):([0-3])"))
async def quiz_answer(event):
    token = event.data_match.group(1).decode(); choice = int(event.data_match.group(2).decode()); uid = _as_int(event.sender_id)
    try:
        async with _guard(token) as lock:
            g = await _load(token)
            if not g or g.get("status") != "playing":
                return await _answer(event, "This quiz is not active.", True)
            if not _has_player(g, uid):
                return await _answer(event, "You are not a player in this quiz.", True)
            now = time.time()
            if now >= float(g.get("deadline", 0.0)):
                # Answer before edit — event.edit() auto-answers and would
                # swallow a later callback answer.
                await _answer(event, "Time is up for this question.")
                finished = _settle_round(g)
                _remember_message(g, event)
                await _save(g, lock)
                if finished:
                    await _index_remove(token)
                else:
                    _ensure_scheduler(token)
                await _render(event, g, finished)
                return
            key = str(uid)
            if key in (g.get("answers") or {}):
                return await _answer(event, "You already answered this question.", True)
            feedback = _choice_feedback(g, choice)
            g.setdefault("answers", {})
            g["answers"][key] = {
                "choice": choice,
                "elapsed": _elapsed_seconds(g, now),
                "scored": False,
            }
            # Feedback must be sent before event.edit(); Telethon's edit()
            # answers the callback automatically.
            await _answer(event, feedback)
            if len(g["answers"]) >= len(_player_ids(g)):
                finished = _settle_round(g)
                _remember_message(g, event)
                await _save(g, lock)
                if finished:
                    await _index_remove(token)
                else:
                    _ensure_scheduler(token)
                await _render(event, g, finished)
                return
            _remember_message(g, event)
            await _save(g, lock)
            _ensure_scheduler(token)
            await _render(event, g)
    except BusyQuizError:
        await _answer(event, "The quiz is being updated. Try again.", True)
    except LockLostError:
        await _answer(event, "The game state changed. Try again.", True)
    except Exception:
        LOGS.exception("Quiz answer failed: %s", token)
        await _answer(event, "Could not record your answer.", True)


@callback(data=re.compile(r"q2:rsg:([A-Za-z0-9_]{8,24})"))
async def quiz_resign(event):
    token = event.data_match.group(1).decode(); uid = _as_int(event.sender_id)
    try:
        async with _guard(token) as lock:
            g = await _load(token)
            if not g or g.get("status") != "playing":
                return await _answer(event, "This quiz is not active.", True)
            if not _has_player(g, uid):
                return await _answer(event, "You are not a player.", True)
            g["players"] = [p for p in _player_ids(g) if p != uid]
            g["names"].pop(str(uid), None)
            g["scores"].pop(str(uid), None)
            g.get("answers", {}).pop(str(uid), None)
            if len(g["players"]) < MIN_PLAYERS:
                g["status"] = "finished"; g["finished_at"] = time.time()
                await _save(g, lock); await _index_remove(token); await _render(event, g, True)
            else:
                _remember_message(g, event)
                await _save(g, lock); await _render(event, g)
            await _answer(event, "You left the quiz.")
    except Exception:
        LOGS.exception("Quiz resign failed: %s", token)
        await _answer(event, "Could not leave the quiz.", True)


@callback(data=re.compile(r"q2:end:([A-Za-z0-9_]{8,24})"))
async def quiz_end(event):
    token = event.data_match.group(1).decode()
    try:
        async with _guard(token) as lock:
            g = await _load(token)
            if not g or g.get("status") not in TERMINAL:
                return await _answer(event, "End Game is available after the quiz has finished or been cancelled.", True)
            if int(event.sender_id) != int(g["host_id"]) and int(event.sender_id) != _owner_id():
                return await _answer(event, "Only the game creator or bot owner can close this quiz.", True)
            await _delete(_key("game", token)); await _index_remove(token)
            await event.edit("🔒 <b>Quiz Closed</b>\n\nThis quiz has been permanently closed.", buttons=[], parse_mode="html")
    except Exception:
        LOGS.exception("Quiz end failed: %s", token)
        await _answer(event, "Could not close the quiz.", True)


@callback(data=re.compile(r"q2:rem:([A-Za-z0-9_]{8,24})"))
async def quiz_rematch(event):
    token = event.data_match.group(1).decode()
    try:
        async with _guard(token) as lock:
            old = await _load(token)
            if not old or old.get("status") != "finished":
                return await _answer(event, "The quiz is not finished.", True)
            if int(event.sender_id) != int(old["host_id"]):
                return await _answer(event, "Only the original host can start a rematch.", True)
            if len(old["players"]) < MIN_PLAYERS:
                return await _answer(event, "At least 2 players are required for a rematch.", True)
            new = dict(old)
            new["token"] = _token(); new["status"] = "lobby"; new["questions"] = []; new["current"] = 0; new["answers"] = {}; new["answer_log"] = {}; new["deadline"] = 0.0; new["scores"] = {str(uid): 0 for uid in old["players"]}; new["updated_at"] = time.time(); new["max_players"] = None
            if not await _set_json(_key("game", new["token"]), new, GAME_TTL, nx=True):
                raise RuntimeError("Could not persist rematch")
            await _index_add(new["token"]); await _delete(_key("game", token)); await _index_remove(token); await _render_lobby(event, new); await _answer(event, "Rematch lobby created.")
    except Exception:
        LOGS.exception("Quiz rematch failed: %s", token)
        await _answer(event, "Could not create the rematch.", True)


_start_recovery()
