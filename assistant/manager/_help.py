from . import *

START = """
✨ **Help Menu** ✨

✗  /start : Start The Bot
✗  /help : Get This Message

👨🏻‍💻 **T.me/DarkPentesterX**
"""

ADMINTOOLS = """✘ **AdminTools** ✘

• /pin : Pins the Replied Message
• /pinned : Get Pinned message in chat.
• /unpin : Unpin the Replied message
• /unpin all : Unpin all Pinned Messages.

• /ban (username/id/reply) : Ban the User
• /unban (username/id/reply) : UnBan the User.

• /mute (username/id/reply) : Mute the User.
• /unmute (username/id/reply) : Unmute the User.

• /tban (username/id/reply) (time) : Temporary ban a user
• /tmute (username/id/reply) (time) : temporary Mutes a User.

• /purge (purge messages)

• /setgpic (reply photo) : keep Chat Photo of Group.
• /delgpic : remove current chat Photo."""

UTILITIES = """
✘ ** Utilities ** ✘

• /info (reply/username/id) : get detailed info of user.
• /id : get chat/user id.
• /tr : Translate Languages.

• /paste (reply file/text) : paste content on Spaceb.in
• /meaning (text) : Get Meaning of that Word.
• /go (query) : Search Something on Google.

• /suggest (query/reply) : Creates a Yes / No Poll.
"""

LOCKS = """
✘ ** Locks ** ✘

• /lock (query) : lock particular content in chat.
• /unlock (query) : Unlock some content.

• All Queries
- `msgs` : for messages.
- `inlines` : for inline queries.
- `media` : for all medias.
- `games` : for games.
- `sticker` : for stickers.
- `polls` : for polls.
- `gif` : for gifs.
- `pin` : for pins.
- `changeinfo` : for change info right.
"""

MISC = """
✘  **Misc**  ✘

• /joke : Get Random Jokes.
• /decide : Decide Something.
"""

STRINGS = {"ᴀᴅᴍɪɴᴛᴏᴏʟꜱ": ADMINTOOLS, "ʟᴏᴄᴋꜱ": LOCKS, "ᴜᴛɪʟꜱ": UTILITIES, "ᴍɪꜱᴄ": MISC}

MNGE = udB.get("MNGR_EMOJI") or "•"


def get_buttons():
    BTTS = []
    keys = STRINGS.copy()
    while keys:
        BT = []
        for i in list(keys)[:2]:
            text = MNGE + " " + i + " " + MNGE
            BT.append(Button.inline(text, "hlp_" + i))
            del keys[i]
        BTTS.append(BT)
    url = "https://t.me/" + asst.me.username + "?startgroup=true"
    BTTS.append([Button.url("✗ ᴀᴅᴅ ᴍᴇ ᴛᴏ ɢʀᴏᴜᴘ ✗", url)])
    return BTTS


@asst_cmd(pattern="help")
async def helpish(event):
    if not event.is_private:
        url = "https://t.me/PentesterX_Bot?start=help"
        return await event.reply(
            "Do You Wanna Help?", buttons=Button.url("✗ ᴄʟɪᴄᴋ ᴍᴇ ꜰᴏʀ ʜᴇʟᴘ ✗", url)
        )
    if str(event.sender_id) in owner_and_sudos() and (
        udB.get("DUAL_MODE") and (udB.get("DUAL_HNDLR") == "/")
    ):
        return
    BTTS = get_buttons()
    await event.reply(START, buttons=BTTS, link_preview=False)


@callback("mngbtn", owner=True)
async def ehwhshd(e):
    buttons = get_buttons()
    buttons.append([Button.inline("≼", "open")])
    await e.edit(buttons=buttons)


@callback("mnghome")
async def home_aja(e):
    await e.edit(START, buttons=get_buttons())


@callback(re.compile("hlp_(.*)"))
async def do_something(event):
    match = event.pattern_match.group(1).decode("utf-8")
    await event.edit(STRINGS[match], buttons=Button.inline("≼", "mnghome"))
