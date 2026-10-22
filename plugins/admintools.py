from . import get_help

__doc__ = get_help("help_admintools")

import asyncio
import html
import inspect
import re
import secrets
import struct
import time

from telethon import Button
from telethon.errors import (
    BadRequestError,
    BotInlineDisabledError,
    BotResponseTimeoutError,
)
from telethon.errors.rpcerrorlist import ChatNotModifiedError, UserIdInvalidError
from telethon.tl.functions.channels import EditAdminRequest, GetFullChannelRequest
from telethon.tl.functions.messages import GetFullChatRequest, SetHistoryTTLRequest
from telethon.tl.types import InputMessagesFilterPinned
from telethon.utils import get_display_name

from CythonX.dB import DEVLIST
from CythonX.fns.admins import ban_time
from CythonX.fns.info import get_uinfo

from . import (
    HNDLR,
    LOGS,
    asst,
    callback,
    eod,
    eor,
    get_pstring,
    get_string,
    heartless_bot,
    heartless_cmd,
    in_pattern,
    inline_mention,
    types,
)


# ---------------------------------------------------------------------------
# Promote permission panel
# ---------------------------------------------------------------------------

PANEL_TTL = 15 * 60
MAX_PANELS = 200
PANEL_CALLBACK = "pmt"
CHECK = "✓ "
BASIC_PERMISSIONS = (("is_admin", "Administrator"),)
BROADCAST_PERMISSIONS = (
    ("post_messages", "Post Messages"),
    ("edit_messages", "Edit Messages"),
    ("change_info", "Change Info"),
    ("delete_messages", "Delete Messages"),
    ("invite_users", "Invite Users"),
    ("pin_messages", "Pin Messages"),
    ("add_admins", "Add Admins"),
    ("anonymous", "Remain Anonymous"),
    ("manage_ranks", "Edit Member Tags"),
    ("manage_stories", "Manage Stories"),
    ("manage_welcome_messages", "Manage Welcome Messages"),
)
MEGAGROUP_PERMISSIONS = (
    ("change_info", "Change Info"),
    ("delete_messages", "Delete Messages"),
    ("ban_users", "Ban Users"),
    ("invite_users", "Invite Users"),
    ("pin_messages", "Pin Messages"),
    ("add_admins", "Add Admins"),
    ("anonymous", "Remain Anonymous"),
    ("manage_call", "Manage Calls"),
    ("manage_ranks", "Edit Member Tags"),
    ("manage_stories", "Manage Stories"),
    ("manage_welcome_messages", "Manage Welcome Messages"),
)
DEFAULT_PERMISSIONS = frozenset(
    {
        "invite_users",
        "ban_users",
        "delete_messages",
        "pin_messages",
        "manage_call",
    }
)

# Telegram exposes "Manage Stories" as three separate flags.  A single panel
# button therefore maps to all three TL rights.
PERMISSION_FLAGS = {
    "manage_stories": ("post_stories", "edit_stories", "delete_stories"),
}

# Bit positions from the chatAdminRights TL constructor.  Keeping the mapping
# here lets newer rights work even with an older Telethon build.
RIGHTS_BITS = {
    "change_info": 0,
    "post_messages": 1,
    "edit_messages": 2,
    "delete_messages": 3,
    "ban_users": 4,
    "invite_users": 5,
    "pin_messages": 7,
    "add_admins": 9,
    "anonymous": 10,
    "manage_call": 11,
    "other": 12,
    "manage_topics": 13,
    "post_stories": 14,
    "edit_stories": 15,
    "delete_stories": 16,
    "manage_direct_messages": 17,
    "manage_ranks": 18,
    "manage_linked_peers": 19,
    "manage_welcome_messages": 20,
}


def _chat_admin_right_fields():
    """Fields supported by the installed Telethon ``ChatAdminRights``."""
    fields = getattr(types.ChatAdminRights, "__static_attributes__", ())
    if fields:
        return frozenset(fields)
    try:
        return frozenset(
            inspect.signature(types.ChatAdminRights.__init__).parameters
        ) - {"self"}
    except (TypeError, ValueError):
        return frozenset(RIGHTS_BITS)


ADMIN_RIGHT_FIELDS = _chat_admin_right_fields()


class CompatAdminRights:
    """Serialize chatAdminRights flags unknown to the installed Telethon.

    Telegram's constructor is a flags-only field, so the wire format is
    simply the constructor id followed by the bitmask.  This keeps newer
    rights usable on older Telethon builds instead of silently dropping them.
    """

    CONSTRUCTOR_ID = getattr(
        types.ChatAdminRights, "CONSTRUCTOR_ID", 0x5FB224D5
    )
    SUBCLASS_OF_ID = getattr(
        types.ChatAdminRights, "SUBCLASS_OF_ID", 2252195780
    )

    def __init__(self, values):
        unknown = set(values) - set(RIGHTS_BITS)
        if unknown:
            raise ValueError(f"Unknown admin rights: {', '.join(sorted(unknown))}")
        self.values = {key: bool(value) for key, value in values.items()}

    def _bytes(self):
        flags = 0
        for key, value in self.values.items():
            if value:
                flags |= 1 << RIGHTS_BITS[key]
        return struct.pack("<I", self.CONSTRUCTOR_ID) + struct.pack("<I", flags)

    def to_dict(self):
        return {key: value for key, value in self.values.items() if value}

    def __repr__(self):
        return f"CompatAdminRights({self.values!r})"


def permission_fields(key):
    """TL fields controlled by one panel permission button."""
    return PERMISSION_FLAGS.get(key, (key,))


def build_admin_rights(values):
    """Build the exact ``ChatAdminRights`` object for *values*.

    Uses Telethon's generated type when it knows every flag, otherwise falls
    back to a wire-compatible flags object (needed for manage_ranks and
    manage_welcome_messages on older Telethon releases).
    """
    unknown = set(values) - set(RIGHTS_BITS)
    if unknown:
        raise ValueError(f"Unknown admin rights: {', '.join(sorted(unknown))}")
    clean = {key: bool(value) for key, value in values.items()}
    if set(clean) <= ADMIN_RIGHT_FIELDS:
        return types.ChatAdminRights(**clean)
    return CompatAdminRights(clean)


def permissions_for_chat(chat):
    """Return the admin rights the panel can offer for *chat*.

    Telegram only supports an all-or-nothing ``is_admin`` flag for small
    groups, while broadcast channels and megagroups have different sets of
    meaningful rights.
    """
    if isinstance(chat, types.Chat):
        return BASIC_PERMISSIONS
    if isinstance(chat, types.Channel) and getattr(chat, "broadcast", False):
        return BROADCAST_PERMISSIONS
    return MEGAGROUP_PERMISSIONS


def default_selected(permissions):
    """The selection that reproduces the previous ``.promote`` defaults."""
    keys = {key for key, _label in permissions}
    if keys == {"is_admin"}:
        return {"is_admin"}
    return set(DEFAULT_PERMISSIONS) & keys


class PromotePanel:
    """One in-flight permission panel and its current selection."""

    __slots__ = (
        "key",
        "chat_id",
        "chat_title",
        "user_id",
        "user_name",
        "user_username",
        "rank",
        "permissions",
        "selected",
        "creator_id",
        "created",
    )

    def __init__(
        self,
        key,
        chat_id,
        chat_title,
        user_id,
        user_name,
        user_username,
        rank,
        permissions,
        selected=None,
        creator_id=None,
        created=None,
    ):
        self.key = key
        self.chat_id = int(chat_id)
        self.chat_title = chat_title or str(chat_id)
        self.user_id = int(user_id)
        self.user_name = user_name or f"User {user_id}"
        self.user_username = user_username
        # Telegram rejects admin ranks longer than 16 characters.
        self.rank = (rank or "Admin").strip()[:16] or "Admin"
        self.permissions = tuple(permissions)
        self.selected = (
            default_selected(self.permissions) if selected is None else set(selected)
        )
        self.creator_id = creator_id
        self.created = time.time() if created is None else created

    @property
    def is_basic(self):
        return self.permissions == BASIC_PERMISSIONS

    def has_permission(self, key):
        return any(key == permission for permission, _label in self.permissions)

    def toggle(self, key):
        """Toggle *key* and return whether it is now selected."""
        if not self.has_permission(key):
            return None
        if key in self.selected:
            self.selected.remove(key)
            return False
        self.selected.add(key)
        return True

    def select_all(self):
        self.selected = {key for key, _label in self.permissions}

    def promote_kwargs(self):
        """Exactly the checked rights, expanded to ChatAdminRights flags."""
        if self.is_basic:
            return {"is_admin": True}
        rights = {}
        for key, _label in self.permissions:
            checked = key in self.selected
            for field in permission_fields(key):
                rights[field] = checked
        return rights

    def selected_labels(self):
        return [
            label for key, label in self.permissions if key in self.selected
        ]

    def mention(self):
        return inline_mention(
            types.User(
                id=self.user_id,
                first_name=self.user_name,
                username=self.user_username,
            )
        )

    def text(self):
        return get_string("pro_3").format(
            self.mention(),
            self.chat_title,
            self.rank,
            len(self.selected),
            len(self.permissions),
        )

    def buttons(self):
        rows = []
        row = []
        for key, label in self.permissions:
            text = f"{CHECK}{label}" if key in self.selected else label
            row.append(
                Button.inline(
                    text, data=f"{PANEL_CALLBACK}:{self.key}:{key}"
                )
            )
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        rows.append(
            [
                Button.inline(
                    "Full Access", data=f"{PANEL_CALLBACK}:{self.key}:f"
                ),
                Button.inline("Confirm", data=f"{PANEL_CALLBACK}:{self.key}:c"),
            ]
        )
        return rows


class PromotePanelStore:
    """Bounded, self-expiring store of permission panels."""

    def __init__(
        self,
        ttl=PANEL_TTL,
        max_entries=MAX_PANELS,
        clock=time.time,
    ):
        self.ttl = ttl
        self.max_entries = max_entries
        self._clock = clock
        self._items = {}

    def _expired(self, panel, now):
        return self.ttl is not None and now - panel.created > self.ttl

    def _prune(self, now):
        for key in [k for k, v in self._items.items() if self._expired(v, now)]:
            self._items.pop(key, None)
        while len(self._items) > self.max_entries:
            oldest = min(self._items.values(), key=lambda panel: panel.created)
            self._items.pop(oldest.key, None)

    def add(
        self,
        chat_id,
        chat_title,
        user_id,
        user_name,
        user_username,
        rank,
        permissions,
        creator_id=None,
        select_all=False,
        selected=None,
        key=None,
    ):
        now = self._clock()
        key = key or secrets.token_hex(6)
        panel = PromotePanel(
            key=key,
            chat_id=chat_id,
            chat_title=chat_title,
            user_id=user_id,
            user_name=user_name,
            user_username=user_username,
            rank=rank,
            permissions=permissions,
            selected=selected,
            creator_id=creator_id,
            created=now,
        )
        if select_all:
            panel.select_all()
        self._items[key] = panel
        self._prune(now)
        return panel

    def get(self, key):
        panel = self._items.get(key)
        if panel is None:
            return None
        now = self._clock()
        if self._expired(panel, now):
            self._items.pop(key, None)
            return None
        return panel

    def remove(self, key):
        return self._items.pop(key, None) is not None


PANELS = PromotePanelStore()


def create_panel(chat, user, rank, creator_id, select_all=False):
    """Create a panel for *user* in *chat* and register it in :data:`PANELS`."""
    return PANELS.add(
        chat_id=chat.id,
        chat_title=get_display_name(chat) or str(chat.id),
        user_id=user.id,
        user_name=get_display_name(user) or f"User {user.id}",
        user_username=getattr(user, "username", None),
        rank=rank or "Admin",
        permissions=permissions_for_chat(chat),
        creator_id=creator_id,
        select_all=select_all,
    )


async def apply_promotion(client, panel):
    """Promote the panel's target with exactly the selected rights."""
    if panel.is_basic:
        return await client.edit_admin(
            panel.chat_id,
            panel.user_id,
            is_admin=True,
            title=panel.rank,
        )
    rights = build_admin_rights(panel.promote_kwargs())
    channel = await client.get_input_entity(panel.chat_id)
    user = await client.get_input_entity(panel.user_id)
    return await client(
        EditAdminRequest(channel, user, rights, rank=panel.rank)
    )


async def remove_admin_rights(client, chat, user_id):
    """Remove every administrator right, including newer TL flags."""
    if isinstance(chat, types.Chat):
        return await client.edit_admin(chat.id, user_id, is_admin=False)

    rights = build_admin_rights({})
    channel = await client.get_input_entity(chat.id)
    user = await client.get_input_entity(user_id)
    return await client(EditAdminRequest(channel, user, rights, rank=""))


async def delete_message_ids(client, chat_id, ids, batch_size=100):
    """Delete *ids* in server-sized batches and return the deleted count."""
    if isinstance(ids, range):
        for start in range(ids.start, ids.stop, batch_size):
            stop = min(start + batch_size, ids.stop)
            await client.delete_messages(chat_id, list(range(start, stop)))
        return len(ids)

    ids = list(ids)
    for start in range(0, len(ids), batch_size):
        await client.delete_messages(chat_id, ids[start:start + batch_size])
    return len(ids)


def _callback_text(value):
    if isinstance(value, (bytes, bytearray)):
        return value.decode("UTF-8", "replace")
    return str(value)


@heartless_cmd(
    pattern="promote( (.*)|$)",
    admins_only=True,
    manager=True,
    require="add_admins",
    fullsudo=True,
)
async def prmte(ult):
    xx = await ult.eor(get_pstring("com_1", "load"))
    if ult.is_private:
        return await xx.edit("`Use this in group/channel.`")
    user, rank = await get_uinfo(ult)
    rank = rank or "Admin"
    if not user:
        return await xx.edit(get_string("pro_1"))

    full_access = False
    if rank.split()[0] == "-f":
        try:
            rank = rank.split(maxsplit=1)[1]
        except IndexError:
            rank = "Admin"
        full_access = True

    panel = create_panel(
        ult.chat,
        user,
        rank,
        ult.sender_id,
        select_all=full_access,
    )

    try:
        username = getattr(getattr(asst, "me", None), "username", None)
        if not username:
            raise RuntimeError("assistant bot is not configured")
        results = await ult.client.inline_query(
            username, f"promote {panel.key}"
        )
        if not results:
            raise RuntimeError(get_string("pro_9"))
        await results[0].click(
            ult.chat_id,
            reply_to=ult.reply_to_msg_id,
            hide_via=False,
        )
    except BotResponseTimeoutError:
        PANELS.remove(panel.key)
        return await xx.edit(get_string("pro_7").format("assistant timed out"))
    except BotInlineDisabledError:
        PANELS.remove(panel.key)
        return await xx.edit(get_string("pro_8"))
    except Exception as ex:
        PANELS.remove(panel.key)
        LOGS.exception(ex)
        return await xx.edit(get_string("pro_7").format(str(ex)))

    try:
        await xx.delete()
    except Exception as ex:
        LOGS.exception(ex)


@in_pattern("promote", owner=True)
async def promote_inline(event):
    parts = event.text.split(maxsplit=1)
    key = parts[1].strip() if len(parts) > 1 else ""
    panel = PANELS.get(key)
    if panel is None:
        text = get_string("pro_6")
        return await event.answer(
            [
                await event.builder.article(
                    title="Panel expired",
                    description=text,
                    text=text,
                )
            ],
            cache_time=0,
        )
    article = await event.builder.article(
        title=f"Promote {panel.user_name}"[:32],
        description=f"Admin rights in {panel.chat_title}"[:100],
        text=panel.text(),
        buttons=panel.buttons(),
    )
    await event.answer([article], cache_time=0)


@callback(re.compile(r"^pmt:([0-9a-f]+):([a-z_]+)$"), owner=True)
async def promote_callback(event):
    key = _callback_text(event.pattern_match.group(1))
    action = _callback_text(event.pattern_match.group(2))
    panel = PANELS.get(key)
    if panel is None:
        return await event.answer(get_string("pro_6"), alert=True)

    if action == "c":
        if not panel.selected:
            return await event.answer(get_string("pro_4"), alert=True)
        try:
            await apply_promotion(heartless_bot, panel)
        except Exception as ex:
            LOGS.exception(ex)
            return await event.answer(f"`{str(ex)[:180]}`", alert=True)
        PANELS.remove(key)
        labels = ", ".join(panel.selected_labels()) or "None"
        text = get_string("pro_5").format(
            panel.mention(), panel.chat_title, panel.rank, labels
        )
        await event.answer(get_string("pro_13"))
        return await event.edit(text)

    if action == "f":
        all_keys = {key for key, _label in panel.permissions}
        already_all = panel.selected == all_keys
        panel.select_all()
        await event.answer(get_string("pro_14"))
        if already_all:
            # Avoid Telegram's MessageNotModifiedError when everything is
            # already selected, but still keep the answer responsive.
            return
        return await event.edit(panel.text(), buttons=panel.buttons())

    if not panel.has_permission(action):
        return await event.answer(get_string("pro_15"), alert=True)

    added = panel.toggle(action)
    await event.answer(
        get_string("pro_16") if added is not None else get_string("pro_15")
    )
    return await event.edit(panel.text(), buttons=panel.buttons())


@heartless_cmd(
    pattern="demote( (.*)|$)",
    admins_only=True,
    manager=True,
    require="add_admins",
    fullsudo=True,
)
async def dmote(ult):
    xx = await ult.eor(get_pstring("com_1", "load"))
    if ult.is_private:
        return await xx.edit("`Use this in group/channel.`")
    user, _rank = await get_uinfo(ult)
    if not user:
        return await xx.edit(get_string("de_1"))
    try:
        await remove_admin_rights(ult.client, ult.chat, user.id)
        await eod(xx, get_string("de_2").format(inline_mention(user), ult.chat.title))
    except Exception as ex:
        return await xx.edit(f"`{ex}`")


@heartless_cmd(
    pattern="ban( (.*)|$)",
    admins_only=True,
    manager=True,
    require="ban_users",
    fullsudo=True,
)
async def bban(ult):
    something = await get_uinfo(ult)
    if not something:
        return
    user, reason = something
    if not user:
        return await eod(ult, get_string("ban_1"))
    if user.id in DEVLIST:
        return await eod(ult, get_string("ban_2"))
    try:
        await ult.client.edit_permissions(ult.chat_id, user.id, view_messages=False)
    except UserIdInvalidError:
        return await eod(ult, get_string("adm_1"))
    except BadRequestError:
        return await eod(ult, get_string("ban_3"))
    senderme = inline_mention(await ult.get_sender())
    userme = inline_mention(user)
    text = get_string("ban_4").format(userme, senderme, ult.chat.title)
    if reason:
        text += get_string("ban_5").format(reason)
    await eod(ult, text)


@heartless_cmd(
    pattern="unban( (.*)|$)",
    admins_only=True,
    manager=True,
    require="ban_users",
    fullsudo=True,
)
async def uunban(ult):
    xx = await ult.eor(get_pstring("com_1", "load"))
    something = await get_uinfo(ult)
    if not something:
        return await xx.delete()
    user, reason = something
    if not user:
        return await xx.edit(get_string("unban_1"))
    try:
        await ult.client.edit_permissions(ult.chat_id, user.id, view_messages=True)
    except UserIdInvalidError:
        return await xx.edit(get_string("adm_1"))
    except BadRequestError:
        return await xx.edit(get_string("adm_2"))
    sender = inline_mention(await ult.get_sender())
    text = get_string("unban_3").format(inline_mention(user), sender, ult.chat.title)
    if reason:
        text += get_string("ban_5").format(reason)
    await xx.edit(text)


@heartless_cmd(
    pattern="kick( (.*)|$)",
    manager=True,
    require="ban_users",
    fullsudo=True,
)
async def kck(ult):
    if "kickme" in ult.text:
        return
    if ult.is_private:
        return await ult.eor("`Use this in Group/Channel.`", time=5)
    xx = await ult.eor(get_pstring("com_1", "load"))
    something = await get_uinfo(ult)
    if not something:
        return await xx.delete()
    user, reason = something
    if not user:
        return await xx.edit(get_string("adm_1"))
    if user.id in DEVLIST:
        return await xx.edit(get_string("kick_2"))
    if user.id == getattr(ult.client, "uid", None):
        return await xx.edit(get_string("kick_3"))
    try:
        await ult.client.kick_participant(ult.chat_id, user.id)
    except BadRequestError as er:
        LOGS.info(er)
        return await xx.edit(get_string("kick_1"))
    except Exception as e:
        LOGS.exception(e)
        return await xx.edit(f"`{e}`")
    text = get_string("kick_4").format(
        inline_mention(user), inline_mention(await ult.get_sender()), ult.chat.title
    )
    if reason:
        text += get_string("ban_5").format(reason)
    await xx.edit(text)


@heartless_cmd(
    pattern="tban( (.*)|$)",
    admins_only=True,
    manager=True,
    require="ban_users",
    fullsudo=True,
)
async def tkicki(e):
    if e.is_private:
        return await e.eor("`Use this in group/channel.`", time=5)
    huh = e.text.split()
    inputt = None
    try:
        tme = huh[1]
    except IndexError:
        return await e.eor(get_string("adm_3"), time=15)
    try:
        inputt = huh[2]
    except IndexError:
        if e.reply_to_msg_id:
            reply = await e.get_reply_message()
            inputt = reply.sender_id if reply else None
    if not inputt:
        return await e.eor(get_string("tban_1"))
    try:
        userid = await e.client.parse_id(inputt)
        user = await e.client.get_entity(userid)
    except Exception as ex:
        return await eor(e, f"`{ex}`")
    if user is None:
        return await e.eor(get_string("adm_1"), time=10)
    if user.id in DEVLIST:
        return await e.eor(get_string("ban_2"), time=10)
    if user.id == getattr(e.client, "uid", None):
        return await e.eor(get_string("kick_3"), time=10)
    try:
        bun = ban_time(tme)
        await e.client.edit_permissions(
            e.chat_id, user.id, until_date=bun, view_messages=False
        )
        await eod(
            e,
            get_string("tban_2").format(inline_mention(user), e.chat.title, tme),
            time=15,
        )
    except Exception as m:
        return await e.eor(str(m))


@heartless_cmd(pattern="pin$", manager=True, require="pin_messages", fullsudo=True)
async def pin(msg):
    if not msg.is_reply:
        return await eor(msg, get_string("pin_1"))
    me = await msg.get_reply_message()
    if me is None:
        return await eor(msg, get_string("pin_1"))
    if me.is_private or not me.message_link:
        text = "`Pinned.`"
    else:
        text = f"Pinned [This Message]({me.message_link}) !"
    try:
        await msg.client.pin_message(msg.chat_id, me.id, notify=False)
    except BadRequestError:
        return await eor(msg, get_string("adm_2"))
    except Exception as e:
        return await eor(msg, f"**ERROR:**`{e}`")
    await eor(msg, text)


@heartless_cmd(
    pattern="unpin($| (.*))",
    manager=True,
    require="pin_messages",
    fullsudo=True,
)
async def unp(ult):
    xx = await ult.eor(get_pstring("com_1", "load"))
    ch = ult.pattern_match.group(1).strip()
    msg = None
    if ch == "all":
        msg = None
    elif ult.is_reply:
        msg = ult.reply_to_msg_id
    else:
        return await xx.edit(get_string("unpin_1").format(HNDLR))
    try:
        await ult.client.unpin_message(ult.chat_id, msg)
    except BadRequestError:
        return await xx.edit(get_string("adm_2"))
    except Exception as e:
        return await xx.edit(f"**ERROR:**`{e}`")
    await xx.edit("`Unpinned!`")


@heartless_cmd(
    pattern="tpin( (.*)|$)",
    admins_only=True,
    manager=True,
    require="pin_messages",
    fullsudo=True,
)
async def pin_message(ult):
    match = ult.pattern_match.group(1).strip()
    if not ult.is_reply:
        return await ult.eor("`Reply to message..`", time=6)
    if not match:
        return await ult.eor("`Please provide time..`", time=8)
    msg = await ult.eor(get_pstring("com_1", "load"))
    msg_id = ult.reply_to_msg_id
    try:
        until = ban_time(match)
        seconds = max(0, until - int(time.time()))
        await ult.client.pin_message(ult.chat_id, msg_id)
        await msg.eor(f"`pinned for` `{match}`", time=8)
    except Exception as er:
        return await msg.edit(str(er))
    await asyncio.sleep(seconds)
    try:
        await ult.client.unpin_message(ult.chat_id, msg_id)
    except Exception as er:
        LOGS.exception(er)


@heartless_cmd(pattern="purge( (.*)|$)", manager=True, require="delete_messages")
async def fastpurger(purg):
    match = purg.pattern_match.group(1).strip()
    limit = None
    if match:
        try:
            limit = int(match)
        except ValueError:
            return await eor(purg, get_string("com_3"), time=5)
    if not getattr(purg.client, "_bot", False) and (
        match
        or (purg.is_reply and (purg.is_private or isinstance(purg.chat, types.Chat)))
    ):
        deleted = 0
        ids = []
        async for msg in purg.client.iter_messages(
            purg.chat_id,
            limit=limit,
            min_id=purg.reply_to_msg_id if purg.is_reply else None,
            max_id=purg.id - 1,
        ):
            ids.append(msg.id)
            if len(ids) >= 100:
                await purg.client.delete_messages(purg.chat_id, ids)
                deleted += len(ids)
                ids.clear()
        if ids:
            await purg.client.delete_messages(purg.chat_id, ids)
            deleted += len(ids)
        return await eor(purg, f"Purged {deleted} Messages! ", time=5)
    if not purg.reply_to_msg_id:
        return await eor(purg, get_string("purge_1"), time=10)
    try:
        await delete_message_ids(
            purg.client,
            purg.chat_id,
            range(purg.reply_to_msg_id, purg.id),
        )
    except Exception as er:
        LOGS.info(er)
        return await purg.eor(f"`{er}`", time=5)
    await purg.eor("__Fast purge complete!__", time=5)


@heartless_cmd(
    pattern="purgeme( (.*)|$)",
    admins_only=True,
)
async def fastpurgerme(purg):
    if num := purg.pattern_match.group(1).strip():
        try:
            nnt = int(num)
        except BaseException:
            await eor(purg, get_string("com_3"), time=5)
            return
        ids = []
        async for mm in purg.client.iter_messages(
            purg.chat_id,
            limit=nnt,
            from_user="me",
            max_id=purg.id - 1,
        ):
            ids.append(mm.id)
        mp = await delete_message_ids(purg.client, purg.chat_id, ids)
        await eor(purg, f"Purged {mp} Messages!", time=5)
        return
    elif not purg.reply_to_msg_id:
        return await eod(
            purg,
            "`Reply to a message to purge from or use it like ``purgeme <num>`",
            time=10,
        )
    chat = await purg.get_input_chat()
    ids = []
    async for msg in purg.client.iter_messages(
        chat,
        from_user="me",
        min_id=purg.reply_to_msg_id,
        max_id=purg.id - 1,
    ):
        ids.append(msg.id)
    deleted = await delete_message_ids(purg.client, chat, ids)
    await purg.eor(
        "__Fast purge complete!__\n**Purged** `" + str(deleted) + "` **messages.**",
        time=5,
    )


@heartless_cmd(
    pattern="purgeall$",
    manager=True,
    require="delete_messages",
    fullsudo=True,
)
async def _(e):
    if not e.is_reply:
        return await eod(
            e,
            get_string("purgeall_1"),
        )

    msg = await e.get_reply_message()
    if msg is None:
        return await eod(e, get_string("purgeall_1"))
    name = get_display_name(msg.sender) or str(msg.sender_id)
    try:
        deleted = 0
        ids = []
        async for target in e.client.iter_messages(
            e.chat_id,
            from_user=msg.sender_id,
            max_id=e.id - 1,
        ):
            ids.append(target.id)
            if len(ids) >= 100:
                await e.client.delete_messages(e.chat_id, ids)
                deleted += len(ids)
                ids.clear()
        if ids:
            await e.client.delete_messages(e.chat_id, ids)
            deleted += len(ids)
        await e.eor(
            get_string("purgeall_2").format(name) + f" (`{deleted}`)",
            time=5,
        )
    except Exception as er:
        return await e.eor(str(er), time=5)


@heartless_cmd(pattern="pinned", manager=True, groups_only=True)
async def djshsh(event):
    chat = await event.get_chat()
    if isinstance(chat, types.Chat):
        FChat = await event.client(GetFullChatRequest(chat.id))
    elif isinstance(chat, types.Channel):
        channel = await event.client.get_input_entity(chat.id)
        FChat = await event.client(GetFullChannelRequest(channel))
    else:
        return
    msg_id = FChat.full_chat.pinned_msg_id
    if not msg_id:
        return await event.eor(get_string("pinned_1"))
    msg = await event.client.get_messages(chat.id, ids=msg_id)
    if msg:
        await event.eor(get_string("pinned_2").format(msg.message_link))
    else:
        await event.eor(get_string("pinned_1"))


@heartless_cmd(
    pattern="mypurge$",
    admins_only=True,
)
async def mypurge(event):
    chat_id = event.chat_id
    ids = []
    async for message in heartless_bot.iter_messages(
        chat_id, max_id=event.id - 1
    ):
        if message.sender_id == event.sender_id:
            ids.append(message.id)
            if len(ids) >= 100:
                await heartless_bot.delete_messages(chat_id, ids)
                ids.clear()
    if ids:
        await heartless_bot.delete_messages(chat_id, ids)
    await eod(event, "All your messages have been deleted from this group.", time=3)

@heartless_cmd(
    pattern="listpinned$",
)
async def get_all_pinned(event):
    x = await event.eor(get_pstring("com_1", "load"))
    chat_id = str(event.chat_id)
    if chat_id.startswith("-100"):
        chat_id = chat_id[4:]
    linkable = isinstance(event.chat, types.Channel)
    chat_name = html.escape(get_display_name(event.chat) or str(event.chat_id))
    a = ""
    c = 0
    async for i in event.client.iter_messages(
        event.chat_id, filter=InputMessagesFilterPinned
    ):
        if i.message:
            t = " ".join(i.message.split()[:4])
            txt = html.escape(f"{t}....")
        else:
            txt = "Go to message."
        c += 1
        if linkable:
            a += f"{c}. <a href=https://t.me/c/{chat_id}/{i.id}>{txt}</a>\n"
        else:
            a += f"{c}. {txt}\n"

    if c == 0:
        return await eor(x, get_string("listpin_1"), time=5)
    if c == 1:
        m = f"<b>The pinned message in {chat_name}:</b>\n\n"
    else:
        m = f"<b>List of pinned message(s) in {chat_name}:</b>\n\n"

    await x.edit(m + a, parse_mode="html")


@heartless_cmd(
    pattern="autodelete( (.*)|$)",
    admins_only=True,
)
async def autodelte(ult):
    match = ult.pattern_match.group(1).strip()
    if not match or match not in ["24h", "7d", "1m", "off"]:
        return await ult.eor("`Please Use in Proper Format..`", time=5)
    if match == "24h":
        tt = 3600 * 24
    elif match == "7d":
        tt = 3600 * 24 * 7
    elif match == "1m":
        tt = 3600 * 24 * 31
    else:
        tt = 0
    try:
        peer = await ult.client.get_input_entity(ult.chat_id)
        await ult.client(SetHistoryTTLRequest(peer, period=tt))
    except ChatNotModifiedError:
        return await ult.eor(
            f"Auto Delete Setting is Already same to `{match}`", time=5
        )
    await ult.eor(f"Auto Delete Status Changed to `{match}` !")


@heartless_cmd(
    pattern=r"kickall( (.*)|$)",
    admins_only=True,
    fullsudo=True,
    require="ban_users",
)
async def kickall_cmd(ult):
    """Kick all non-admin members from the group."""
    if ult.is_private:
        return await ult.eor("`Use this In a Group.`", time=5)
    match = ult.pattern_match.group(1).strip()
    confirm = match.lower() == "confirm"
    if not confirm:
        return await ult.eor(
            f"`Are you sure? This will kick all Non-Admin members!\nUse` `{HNDLR}kickall confirm` `to proceed.`",
            time=10,
        )
    xx = await ult.eor("`Starting KickAll...`")
    kicked = 0
    failed = 0
    async for member in ult.client.iter_participants(ult.chat_id):
        participant = getattr(member, "participant", None)
        if (
            getattr(member, "bot", False)
            or member.id == getattr(ult.client, "uid", None)
            or getattr(participant, "admin_rights", None)
            or getattr(participant, "creator", False)
            or isinstance(
                participant,
                (
                    types.ChatParticipantCreator,
                    types.ChannelParticipantCreator,
                ),
            )
        ):
            continue
        try:
            await ult.client.kick_participant(ult.chat_id, member.id)
            kicked += 1
            await asyncio.sleep(0.2)
        except Exception:
            failed += 1
    await xx.edit(
        f"**KickAll Done!**\n**Kicked:** `{kicked}`\n**Failed:** `{failed}`"
    )
