"""
❍ Commands Available

• `{i}game` <game code>",
    examples: .game `ttt`, `ttf`, `ex`, `cf`, `rps`, `rpsls`, `rr`, `c`, `pc`

•    Tic-Tac-Toe
•    Tic-Tac-Four
•    Elephant XO
•    Connect Four
•    Rock-Paper-Scissors
•    Rock-Paper-Scissors-Lizard-Spock
•    Russian Roulette
•    Checkers
•    Pool Checkers

"""

import asyncio

from bs4 import BeautifulSoup
from markdown import markdown

from . import *

game_code = ["ttt", "ttf", "ex", "cf", "rps", "rpsls", "rr", "c", "pc"]
game_name = [
    "Tic-Tac-Toe",
    "Tic-Tac-Four",
    "Elephant XO",
    "Connect Four",
    "Rock-Paper-Scissors",
    "Rock-Paper-Scissors-Lizard-Spock",
    "Russian Roulette",
    "Checkers",
    "Pool Checkers",
]

game = dict(zip(game_code, game_name))
category = ["classic", "kids", "party", "hot", "mixed"]


def pastetext(text_to_print, pastetype=None, extension=None):
    if pastetype is not None:
        return {"error": "something went wrong"}


def md_to_text(md):
    html = markdown(md)
    soup = BeautifulSoup(html, features="html.parser")
    return soup.get_text()


async def paste_message(text, pastetype="p", extension=None, markdown=True):
    if markdown:
        text = md_to_text(text)
    response = await pastetext(text, pastetype, extension)
    if "url" in response:
        return response["url"]
    return "Error while pasting text to site"


async def edit_delete(event, text, time=None, parse_mode=None, link_preview=None):
    parse_mode = parse_mode or "md"
    link_preview = link_preview or False
    time = time or 10
    reply_to = await event.get_reply_message()
    solevent = (
        await reply_to.reply(text, link_preview=link_preview, parse_mode=parse_mode)
        if reply_to
        else await event.reply(text, link_preview=link_preview, parse_mode=parse_mode)
    )
    await asyncio.sleep(time)
    return await solevent.delete()


async def reply_id(event):
    return event.reply_to_msg_id if event.reply_to_msg_id else None


@heartless_cmd(
    pattern="game(?:\\s|$)([\\s\\S]*)",
)
async def igame(event):
    reply_to_id = await reply_id(event)
    input_str = event.pattern_match.group(1)
    game_list = "".join(
        f"**{i}.** `{item}` :- __{game[item]}__\n"
        for i, item in enumerate(game, start=1)
    )
    if not input_str:
        await edit_delete(
            event, f"**Available Game Codes & Names :-**\n\n{game_list}", time=60
        )
        return
    if input_str not in game_code:
        catevent = await event.eor("`Give me a correct game code...`", time=5)
        await asyncio.sleep(1)
        await edit_delete(
            catevent, f"**Available Game Codes & Names :-**\n\n{game_list}", time=60
        )
    else:
        await event.eor(
            f"**Game code `{input_str}` is selected for game:-** __{game[input_str]}__",
        )
        await asyncio.sleep(1)
        bot = "@inlinegamesbot"
        results = await event.client.inline_query(bot, input_str)
        await results[game_code.index(input_str)].click(
            event.chat_id, reply_to=reply_to_id
        )
        await event.delete()
