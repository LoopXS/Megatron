"""Secret ("whisper") messages with reader tracking.

A secret message is created through the assistant's inline mode:

    @YourAssistantBot wspr <username|id>[,<username|id>...] <message>

Recipients are comma separated (up to :data:`MAX_RECIPIENTS`); the same
form works with the ``.wspr`` command, e.g. ``.wspr @a,@b Hello``.  The
inline result carries three buttons — *Read Message*, *Readers* and
*Delete Message*.  Secrets live in an in-memory :class:`SecretStore`
keyed by a random id, so a restart invalidates old buttons (they report
that the secret is gone), which is also what the previous implementation
did.

Every click on *Read Message* is attributed to a role:

* ``recipient`` — any intended recipient, the only ones allowed to read;
* ``author`` — the user who created the secret, exempt from the
  "unauthorized" list because they already know the content;
* ``unauthorized`` — anybody else.  Their identity is recorded (name,
  username, id, time and click count) and they get a refusal alert.

The *Readers* button immediately pops up an alert-sized report of everybody
who clicked, flagging unauthorized readers; nothing is sent to the assistant.
When a recipient reads, the original message is edited to show who has read
it.  Only the bot owner/sudos may delete a secret — the creator and the
recipients cannot.
"""

import re
import time
from secrets import token_hex

from telethon import Button
from telethon.errors.rpcerrorlist import (
    BotInlineDisabledError,
    BotResponseTimeoutError,
    MessageNotModifiedError,
)
from telethon.tl import types
from telethon.tl.functions.users import GetFullUserRequest as gu

from CythonX._misc import owner_and_sudos

from . import (
    HNDLR,
    LOGS,
    asst,
    callback,
    get_string,
    heartless_bot,
    heartless_cmd,
    in_pattern,
    inline_mention,
)

# Roles a clicker can have for a given secret.
ROLE_RECIPIENT = "recipient"
ROLE_AUTHOR = "author"
ROLE_UNAUTHORIZED = "unauthorized"

# A secret expires after a day and the store keeps at most this many.
SECRET_TTL = 24 * 60 * 60
MAX_SECRETS = 1000

# The popup length Telegram accepts for a callback answer.
ALERT_LIMIT = 200

# A secret can be addressed to at most this many recipients at once.
MAX_RECIPIENTS = 10

_KEY_RE = re.compile(r"^[0-9a-f]{6,64}$")


def new_key():
    """Return a fresh, URL/pattern safe id for a secret message."""
    return token_hex(8)


class Reader:
    """One user who clicked *Read Message* on a secret."""

    __slots__ = (
        "user_id",
        "name",
        "username",
        "first_seen",
        "last_seen",
        "clicks",
        "role",
    )

    def __init__(self, user_id, name, username, role, now):
        self.user_id = user_id
        self.name = name or f"User {user_id}"
        self.username = username
        self.role = role
        self.first_seen = now
        self.last_seen = now
        self.clicks = 1

    def touch(self, name, username, role, now):
        # Keep the freshest identity in case the user renamed themselves.
        self.name = name or self.name
        self.username = username or self.username
        self.role = role
        self.last_seen = now
        self.clicks += 1


class Recipient:
    """One intended recipient of a secret message."""

    __slots__ = ("user_id", "name", "username")

    def __init__(self, user_id, name=None, username=None):
        self.user_id = int(user_id)
        self.name = name or f"User {user_id}"
        self.username = username


class Secret:
    """A secret message and everyone who tried to open it."""

    __slots__ = (
        "key",
        "recipients",
        "author_id",
        "text",
        "created",
        "readers",
    )

    def __init__(self, key, author_id, text, recipients, now=None):
        self.key = key
        self.author_id = int(author_id)
        self.text = text
        self.recipients = {r.user_id: r for r in recipients}
        self.created = time.time() if now is None else now
        self.readers = {}

    def is_recipient(self, user_id):
        return user_id in self.recipients

    def unauthorized(self):
        return [
            reader
            for reader in self.readers.values()
            if reader.role == ROLE_UNAUTHORIZED
        ]


class SecretStore:
    """Bounded, self-expiring in-memory store of secret messages."""

    def __init__(self, ttl=SECRET_TTL, max_entries=MAX_SECRETS, clock=time.time):
        self.ttl = ttl
        self.max_entries = max_entries
        self._clock = clock
        self._items = {}

    def _expired(self, secret, now):
        return self.ttl is not None and now - secret.created > self.ttl

    def _prune(self, now):
        for key in [k for k, v in self._items.items() if self._expired(v, now)]:
            self._items.pop(key, None)
        while len(self._items) > self.max_entries:
            oldest = min(self._items.values(), key=lambda s: s.created)
            self._items.pop(oldest.key, None)

    def add(self, key, author_id, text, recipients):
        now = self._clock()
        secret = Secret(key, author_id, text, recipients, now=now)
        self._items[key] = secret
        self._prune(now)
        return secret

    def get(self, key):
        secret = self._items.get(key)
        if secret is None:
            return None
        now = self._clock()
        if self._expired(secret, now):
            self._items.pop(key, None)
            return None
        return secret

    def remove(self, key):
        return self._items.pop(key, None) is not None

    def record(self, key, user_id, name, username, role):
        secret = self.get(key)
        if secret is None:
            return None
        now = self._clock()
        reader = secret.readers.get(user_id)
        if reader is None:
            reader = Reader(user_id, name, username, role, now)
            secret.readers[user_id] = reader
        else:
            reader.touch(name, username, role, now)
        return reader


STORE = SecretStore()


def role_for(secret, user_id):
    """Classify a clicker relative to ``secret``."""
    if secret.is_recipient(user_id):
        return ROLE_RECIPIENT
    if user_id == secret.author_id:
        return ROLE_AUTHOR
    return ROLE_UNAUTHORIZED


def split_recipients_and_message(raw):
    """Split ``"@a,@b hello"`` into ``(["@a", "@b"], "hello")``.

    Recipients are comma separated; anything after the first space that is
    not part of an open (comma-terminated) list is the message.  Spaces
    after commas are tolerated, duplicates are removed and order kept.
    """
    raw = (raw or "").strip()
    if not raw:
        return [], ""
    blob, _, rest = raw.partition(" ")
    message = rest.strip()
    while blob.endswith(",") and message:
        nxt, _, message = message.partition(" ")
        blob += nxt
        message = message.strip()
    seen = set()
    targets = []
    for token in (part.strip() for part in blob.split(",")):
        if token and token not in seen:
            seen.add(token)
            targets.append(token)
    return targets, message


def _display_name(sender):
    if sender is None:
        return None
    return getattr(sender, "first_name", None) or getattr(sender, "title", None)


def _username(sender):
    return getattr(sender, "username", None) if sender is not None else None


def _mention_person(user_id, name, username=None):
    """Markdown mention for a stored (id, name, username) triple."""
    return inline_mention(
        types.User(id=user_id, first_name=name, username=username)
    )


def _popup_line(reader):
    """One compact, plain-text reader line for the callback popup."""
    who = reader.name
    if reader.username:
        who = f"{who} (@{reader.username})"
    marker = "✅" if reader.role == ROLE_RECIPIENT else "⚠️"
    return f"• {who} {marker}"


def format_readers(secret, limit=ALERT_LIMIT):
    """Render a compact, plain-text reader report sized for an alert popup.

    Telegram caps callback answers at :data:`ALERT_LIMIT` characters, so long
    lists are trimmed with an "…and N more" suffix instead of overflowing.
    """
    readers = sorted(secret.readers.values(), key=lambda r: r.first_seen)
    if not readers:
        return get_string("wspr_8")

    lines = [get_string("wspr_19").format(len(readers))]
    shown = 0
    for reader in readers:
        line = _popup_line(reader)
        remaining = len(readers) - shown - 1
        suffix = get_string("wspr_10").format(remaining).strip() if remaining else ""
        projected = "\n".join(lines + [line] + ([suffix] if suffix else []))
        if len(projected) > limit:
            break
        lines.append(line)
        shown += 1

    if shown < len(readers):
        suffix = get_string("wspr_10").format(len(readers) - shown).strip()
        while shown and len("\n".join(lines + [suffix])) > limit:
            lines.pop()
            shown -= 1
        lines.append(suffix)
    return "\n".join(lines)[:limit]


def format_secret_message(secret):
    """The message shown in chat, annotated with who has read it so far."""
    people = ", ".join(
        _mention_person(r.user_id, r.name, r.username)
        for r in secret.recipients.values()
    )
    text = get_string("wspr_1").format(people)
    readers = [
        reader
        for reader in sorted(secret.readers.values(), key=lambda r: r.first_seen)
        if reader.role == ROLE_RECIPIENT
    ]
    if readers:
        who = ", ".join(
            _mention_person(r.user_id, r.name, r.username) for r in readers
        )
        text += "\n\n" + get_string("wspr_18").format(who)
    return text


async def _update_read_status(e, secret):
    """Edit the original message to show which recipients have read it."""
    try:
        await e.edit(format_secret_message(secret), buttons=_buttons(secret.key))
    except MessageNotModifiedError:
        pass
    except Exception as er:
        LOGS.exception(er)


def _buttons(key):
    """Buttons shared by every viewer of a secret message."""
    return [
        [
            Button.inline("• Rᥱᥲɗ 𐌑ᥱssᥲgᥱ", data=f"read_{key}"),
            Button.inline(get_string("wspr_7"), data=f"readers_{key}"),
        ],
        [Button.inline("𑀥ᥱᥣᥱᴛᥱ 𐌑ᥱssᥲgᥱ", data=f"del_{key}")],
    ]


@heartless_cmd(pattern="wspr( (.*)|$)")
async def wspr_cmd(e):
    raw = (e.pattern_match.group(1) or "").strip()
    if e.reply_to_msg_id:
        reply = await e.get_reply_message()
        sender = getattr(reply, "sender", None) if reply else None
        username = getattr(sender, "username", None) if sender else None
        target = f"@{username}" if username else (reply.sender_id if reply else "")
        targets = [target] if target else []
        message = raw
    else:
        targets, message = split_recipients_and_message(raw)

    if not targets:
        return await e.eor(get_string("wspr_3"))
    if message:
        query = f"wspr {','.join(str(t) for t in targets)} {message}"
    elif len(targets) == 1:
        query = f"msg {targets[0]}"
    else:
        return await e.eor(get_string("wspr_16"))

    try:
        results = await e.client.inline_query(asst.me.username, query)
    except BotResponseTimeoutError:
        return await e.eor(get_string("help_2").format(HNDLR))
    except BotInlineDisabledError:
        return await e.eor(get_string("help_3"))
    if not results:
        return await e.eor(get_string("wspr_4").format(targets[0]))
    await results[0].click(e.chat_id, reply_to=e.reply_to_msg_id, hide_via=True)
    return await e.delete()


@in_pattern("wspr", owner=True)
async def wspr_inline(e):
    parts = e.text.split(maxsplit=1)
    raw = parts[1] if len(parts) > 1 else ""
    targets, message = split_recipients_and_message(raw)

    if not targets:
        return await e.answer(
            [
                await e.builder.article(
                    title="Give Username",
                    description="You Didn't Type Username (or) ID.",
                    text="You Didn't Type Username (or) ID.",
                )
            ]
        )
    if len(targets) > MAX_RECIPIENTS:
        text = get_string("wspr_15").format(MAX_RECIPIENTS)
        return await e.answer([await e.builder.article(title=text, text=text)])

    recipients = []
    seen = set()
    for target in targets:
        try:
            entity = await heartless_bot.get_entity(
                int(target) if target.isdigit() else target
            )
            if not isinstance(entity, types.User):
                raise ValueError("Invalid Username.")
        except Exception as er:
            LOGS.exception(er)
            text = get_string("wspr_4").format(target)
            return await e.answer([await e.builder.article(title=text, text=text)])
        if entity.id in seen:
            continue
        seen.add(entity.id)
        recipients.append(Recipient(entity.id, entity.first_name, entity.username))

    if not message:
        return await e.answer(
            [
                await e.builder.article(
                    title="ᴛʏᴘᴇ ʏᴏᴜʀ ᴍᴇssᴀɢᴇ",
                    text="ᴛʏᴘᴇ ʏᴏᴜʀ ᴍᴇssᴀɢᴇ",
                )
            ]
        )

    key = new_key()
    STORE.add(key, author_id=e.query.user_id, text=message, recipients=recipients)
    people = ", ".join(
        _mention_person(r.user_id, r.name, r.username) for r in recipients
    )
    article = await e.builder.article(
        title=recipients[0].name,
        description=message,
        text=get_string("wspr_1").format(people),
        buttons=_buttons(key),
    )
    await e.answer([article])


@in_pattern("msg", owner=True)
async def msg_inline(e):
    parts = e.text.split(maxsplit=1)
    try:
        query = parts[1]
        entity = await heartless_bot(gu(id=int(query) if query.isdigit() else query))
        user = entity.users[0]
    except IndexError:
        return await e.answer(
            [
                await e.builder.article(
                    title="Give Username",
                    description="You Didn't Type Username or id.",
                    text="You Didn't Type Username or id.",
                )
            ]
        )
    except BaseException as er:
        LOGS.exception(er)
        name = get_string("wspr_4").format(parts[1] if len(parts) > 1 else "")
        return await e.answer([await e.builder.article(title=name, text=name)])

    status = getattr(user, "status", None)
    if isinstance(status, types.UserStatusOnline):
        state = "Online"
    elif isinstance(status, types.UserStatusOffline):
        state = "Offline"
    elif isinstance(status, types.UserStatusRecently):
        state = "Last Seen Recently"
    elif isinstance(status, types.UserStatusLastMonth):
        state = "Last seen months ago"
    elif isinstance(status, types.UserStatusLastWeek):
        state = "Last seen weeks ago"
    else:
        state = "Can't Tell"

    url = (
        f"https://t.me/{user.username}"
        if user.username
        else f"tg://user?id={user.id}"
    )
    text = f"**Ⲛⲁⲙⲉ:**    `{user.first_name}`\n**ⲒⲆ:**    `{user.id}`\n"
    if user.username:
        text += f"**Ⳙⲋⲉʀⲛⲁⲙⲉ:**    `{user.username}`\n"
    else:
        text += f"**Mention:**    `{inline_mention(user)}`\n"
    about = entity.full_user.about or "—"
    text += f"**Ⲋⲧⲁⲧυⲋ:**    `{state}`\n**Ⲁⲃⲟυⲧ:**    `{about}`"

    article = await e.builder.article(
        title=user.first_name,
        description="Touch me",
        text=text,
        buttons=[
            Button.url("Privᴀᴛᴇ", url=url),
            Button.switch_inline(
                "Sᴇᴄrᴇᴛ Mᴇssᴀɢᴇ",
                query=f"wspr {query} Hello 👋",
                same_peer=True,
            ),
        ],
    )
    await e.answer([article])


def _group_text(value):
    """Telethon returns callback pattern groups as bytes; tests pass str."""
    if isinstance(value, (bytes, bytearray)):
        return value.decode("UTF-8", "replace")
    return str(value)


@callback(re.compile(r"^(readers|read|del)_(.+)$"))
async def whisper_callback(e):
    action = _group_text(e.pattern_match.group(1))
    key = _group_text(e.pattern_match.group(2))
    if not _KEY_RE.match(key):
        return await e.answer(get_string("wspr_2"), alert=True)

    secret = STORE.get(key)
    if secret is None:
        return await e.answer(get_string("wspr_2"), alert=True)

    sender = await e.get_sender()
    role = role_for(secret, e.sender_id)

    if action == "read":
        # Only "Read Message" clicks count as reads; opening the reader
        # list or deleting the secret must not show up in that list.
        STORE.record(key, e.sender_id, _display_name(sender), _username(sender), role)
        return await _handle_read(e, secret, role)
    if action == "readers":
        return await _handle_readers(e, secret)
    return await _handle_delete(e, secret)


async def _handle_read(e, secret, role):
    if role == ROLE_UNAUTHORIZED:
        return await e.answer(get_string("wspr_6"), alert=True)

    # Reveal the secret.  Answering here first also marks the callback as
    # answered, so the ``answer()`` scheduled by ``e.edit`` below is a no-op.
    if len(secret.text) <= ALERT_LIMIT:
        await e.answer(secret.text, alert=True)
    else:
        try:
            await e.client.send_message(e.sender_id, secret.text)
        except Exception as er:
            LOGS.exception(er)
            await e.answer(secret.text[:ALERT_LIMIT], alert=True)
        else:
            await e.answer(get_string("wspr_11"), alert=True)

    # Show in the original message that an intended recipient has opened it.
    # The author already knows the content and unauthorized users are refused,
    # so only recipients are reflected there.
    if role == ROLE_RECIPIENT:
        await _update_read_status(e, secret)


async def _handle_readers(e, secret):
    allowed = {secret.author_id, *owner_and_sudos()}
    if e.sender_id not in allowed:
        return await e.answer(get_string("wspr_5"), alert=True)
    # Show the statistics straight away as an inline popup; nothing is sent
    # through (or to) the assistant.
    return await e.answer(format_readers(secret), alert=True)


async def _handle_delete(e, secret):
    # Deletion is reserved for the bot owner and its sudos.  Even the user
    # who created the secret — and every recipient — is refused.
    if e.sender_id not in owner_and_sudos():
        return await e.answer(get_string("wspr_5"), alert=True)
    STORE.remove(secret.key)
    try:
        # Only the text is edited.  The secret card is an inline ("via bot")
        # message, and Telegram rejects an empty ReplyInlineMarkup for
        # ``editInlineBotMessage`` with ReplyMarkupInvalidError.  Its buttons
        # therefore stay in place, but tapping one now answers
        # "Secret Message Deleted!" because the store entry is gone.
        await e.edit(get_string("wspr_2"))
    except MessageNotModifiedError:
        pass
    except Exception as er:
        LOGS.exception(er)
