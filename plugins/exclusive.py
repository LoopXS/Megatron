"""
✘ Commands Available

Animations, ASCII art and novelty helpers. Run `.help exclusive` (or see the
`help_exclusive` string in `strings/strings/en.yml`) for the full command list.

• `{i}hyper <telegram link>`  - hyperlink a telegram link with its message id
• `{i}uglitch <reply image>`  - glitch an image into an animated gif
• `{i}dump [abc]`             - recycling-bin "dump" animation (3 chars)
• `{i}eem <text>`             - render text as a colored heart grid
• `{i}dick [emoji]`           - ASCII art, optionally drawn in another emoji
• `{i}fhack` / `{i}thack` / `{i}whack` - fake "hacking" terminal animations
• `{i}fl`                     - loading bar
• `{i}my` / `{i}hi` / `{i}lit` / `{i}solar` - animated grids / orbits
• `{i}snake` / `{i}human` / `{i}mc` / `{i}comp` - full-frame animations
• plus dozens more spinners, marquees and frame animations
"""
import asyncio
import os
from collections import deque

from telethon.errors import MessageIdInvalidError
from telethon.tl.types import MessageMediaPhoto

from . import *

try:  # optional dependency, only required by `uglitch`
    from glitch_this import ImageGlitcher
except ImportError:  # pragma: no cover
    ImageGlitcher = None

sedpath = "./heartless/"
if not os.path.isdir(sedpath):
    os.makedirs(sedpath)

DURATION = 100  # centiseconds per gif frame
LOOP = 0  # 0 = infinite loop


# ---------------------------------------------------------------------------
# animation helpers
# ---------------------------------------------------------------------------
async def _spin(event, chars, count=48, interval=0.1):
    """Rotate a deque of characters as a spinner."""
    deq = deque(list(chars))
    for _ in range(count):
        await asyncio.sleep(interval)
        await event.edit("".join(deq))
        deq.rotate(1)


async def _frames(event, frames, interval=0.7, intro=None, count=None):
    """Cycle through a list of frames, looping `count` times."""
    if intro is not None:
        await event.edit(intro)
    if count is None:
        count = len(frames)
    for i in range(count):
        await asyncio.sleep(interval)
        await event.edit(frames[i % len(frames)])


async def _seq(event, steps):
    """Show a sequence of (text, delay) steps."""
    for text, delay in steps:
        await event.edit(text)
        await asyncio.sleep(delay)


async def _scroll(event, text, field=13, hold=8):
    """Scroll text across a fixed-width field, then hold."""
    pad = "-" * field
    for shift in range(field + 1):
        await event.edit(pad[shift:] + text + pad[:shift])
    await event.edit(text)
    await asyncio.sleep(hold)


async def _rscroll(event, text, field=13, hold=8):
    """Scroll text out, then back, then hold."""
    pad = "-" * field
    for shift in range(field + 1):
        await event.edit(pad[shift:] + text + pad[:shift])
    await event.edit(text)
    for shift in range(field - 1, 0, -1):
        await event.edit(pad[shift:] + text + pad[:shift])
    await event.edit(text)
    await asyncio.sleep(hold)


async def _grow(event, char, count=9, hold=4):
    """Grow `char` across a fixed-width field, then hold."""
    for n in range(1, count + 1):
        await event.edit(char * n + " " * (count - n))
    await asyncio.sleep(hold)


_PARTIALS = "▎▍▌▊▉█"


async def _loadbar(event):
    """Render a 0-100% progress bar."""
    await event.edit("`start loading...`")
    await asyncio.sleep(1)
    await event.edit("0%")
    for n in range(1, 101):
        bar = "█" * ((n - 1) // 6) + _PARTIALS[(n - 1) % 6]
        await event.edit(f"{n}%   {bar}")
        await asyncio.sleep(0.03)
    await asyncio.sleep(0.5)
    await event.edit("`Done!`")


async def _my(event):
    """Diagonal rainbow heart rotation."""
    colors = "❤️🧡💛💚💙💜"
    n = len(colors)
    for k in range(n * 2):
        rows = [colors[(k + r) % n :] + colors[:(k + r) % n] for r in range(n)]
        await event.edit("\n".join(rows))
        await asyncio.sleep(0.2)


async def _hi(event):
    """Alternating heart rows, then a typewriter I love you."""
    a = '❤️❤️❤️❤️\n🧡🧡🧡🧡\n💛💛💛💛\n💚💚💚💚'
    b = '💙💙💙💙\n💜💜💜💜\n🖤🖤🖤🖤\n🤎🤎🤎🤎'
    text = 'ʟᴏᴅɪɴɢ ᴛʏᴘᴇ........𝑰 𝒍𝒐𝒗𝒆 𝒚𝒐𝒖'
    colors = ['❤️', '💙', '💜', '💚', '💛', '🖤', '💝', '💕', '💖', '💓', '🧡']
    for _ in range(3):
        await event.edit(a)
        await asyncio.sleep(0.2)
        await event.edit(b)
        await asyncio.sleep(0.2)
    for i in range(1, len(text) + 1):
        await event.edit(text[:i])
        await asyncio.sleep(0.08)
    for c in colors:
        await event.edit("💓💓" + text + "💓💓")
        await asyncio.sleep(0.25)
        await event.edit(c + c + text + c + c)
        await asyncio.sleep(0.25)


# ---------------------------------------------------------------------------
# animation data
# ---------------------------------------------------------------------------
COMP = [
    '**===================**\n      **CɪᴘʜᴇʀX Server Details**  \n**===================**\n\n\n**=>>>   CPU   <<<=**\n\n    **🔹current_freq:** 2500.09MHz\n    **🔹total_usage:** 10%\n\n    ●○○○○○○○○○\n\n    **🔹cpu core**\n\n        **🔹core_usage:** 5.9%\n        **🔹current_freq:** 2500.09MHz\n        |██████████▉  |\n       \n**=>>>   RAM   <<<=**\n\n    **🔹free:** 8.13GB\n    **🔹used:** 33.77GB\n    **🔹total:** 60.0GB\n    \n    ●●●●●●●○○○\n\n\n**=>>>   DISK   <<<=**\n\n   **🔹free:** 224.12GB\n    **🔹used:** 131.84GB\n    **🔹total:** 375.02GB\n    **🔹usage:** 37.0%\n\n    |████▍        |\n\n\n**=>>>   NETWORK   <<<=**\n\n    **🔹sent:** 158.98GB\n    **🔹recv:** 146.27GB\n    **🔹sent_packets:** 84518799\n    **🔹recv_packets:** 159720314\n\n\n**===================**\n',
    '**===================**\n      **CɪᴘʜᴇʀX Server Details**  \n**===================**\n\n\n**=>>>   CPU   <<<=**\n\n    **🔹current_freq:** 2500.09MHz\n    **🔹total_usage:** 30%\n\n    ●●●○○○○○○○\n\n    **🔹cpu core**\n\n        **🔹core_usage:** 20.4%\n        **🔹current_freq:** 2500.09MHz\n        |██████████▉  |\n       \n**=>>>   RAM   <<<=**\n\n    **🔹free:** 7.18GB\n    **🔹used:** 28.26GB\n    **🔹total:** 60.0GB\n    \n    ●●●●●●●●●●\n\n\n**=>>>   DISK   <<<=**\n\n   **🔹free:** 224.12GB\n    **🔹used:** 131.84GB\n    **🔹total:** 375.02GB\n    **🔹usage:** 37.0%\n\n    |████▍        |\n\n\n**=>>>   NETWORK   <<<=**\n\n    **🔹sent:** 146.27GB\n    **🔹recv:** 124.33GB\n    **🔹sent_packets:** 54635686\n    **🔹recv_packets:** 143565654\n\n\n**===================**\n',
    '**===================**\n      **CɪᴘʜᴇʀX Server Details**  \n**===================**\n\n\n**=>>>   CPU   <<<=**\n\n    **🔹current_freq:** 2500.09MHz\n    **🔹total_usage:** 60%\n\n    ●●●●●●○○○○\n\n    **🔹cpu core**\n\n        **🔹core_usage:** 60.9%\n        **🔹current_freq:** 2500.09MHz\n        |██████████▉  |\n       \n**=>>>   RAM   <<<=**\n\n    **🔹free:** 6.52GB\n    **🔹used:** 35.78GB\n    **🔹total:** 60.0GB\n    \n    ●●●○○○○○○○\n\n\n**=>>>   DISK   <<<=**\n\n   **🔹free:** 224.12GB\n    **🔹used:** 131.84GB\n    **🔹total:** 375.02GB\n    **🔹usage:** 37.0%\n\n    |████▍        |\n\n\n**=>>>   NETWORK   <<<=**\n\n    **🔹sent:** 124.33GB\n    **🔹recv:** 162.48GB\n    **🔹sent_packets:** 25655655\n    **🔹recv_packets:** 165289456\n\n\n**===================**\n',
    '**===================**\n      **CɪᴘʜᴇʀX Server Details**  \n**===================**\n\n\n**=>>>   CPU   <<<=**\n\n    **🔹current_freq:** 2500.09MHz\n    **🔹total_usage:** 100%\n\n    ●●●●●●●●●●\n\n    **🔹cpu core**\n\n        **🔹core_usage:** 100.0%\n        **🔹current_freq:** 2500.09MHz\n        |██████████▉  |\n       \n**=>>>   RAM   <<<=**\n\n    **🔹free:** 9.81GB\n    **🔹used:** 30.11GB\n    **🔹total:** 60.0GB\n    \n    ●●●●●●●●●●\n\n\n**=>>>   DISK   <<<=**\n\n   **🔹free:** 224.12GB\n    **🔹used:** 131.84GB\n    **🔹total:** 375.02GB\n    **🔹usage:** 37.0%\n\n    |████▍        |\n\n\n**=>>>   NETWORK   <<<=**\n\n    **🔹sent:** 162.48GB\n    **🔹recv:** 175.75GB\n    **🔹sent_packets:** 56565435\n    **🔹recv_packets:** 135345655\n\n\n**===================**\n',
    '**===================**\n      **CɪᴘʜᴇʀX Server Details**  \n**===================**\n\n\n**=>>>   CPU   <<<=**\n\n    **🔹current_freq:** 2500.09MHz\n    **🔹total_usage:** 70%\n\n    ●●●●●●●○○○\n\n    **🔹cpu core**\n\n        **🔹core_usage:** 80.4%\n        **🔹current_freq:** 2500.09MHz\n        |██████████▉  |\n       \n**=>>>   RAM   <<<=**\n\n    **🔹free:** 5.76GB\n    **🔹used:** 29.35GB\n    **🔹total:** 60.0GB\n    \n    ●●●●●●●○○○\n\n\n**=>>>   DISK   <<<=**\n\n   **🔹free:** 224.12GB\n    **🔹used:** 131.84GB\n    **🔹total:** 375.02GB\n    **🔹usage:** 37.0%\n\n    |████▍        |\n\n\n**=>>>   NETWORK   <<<=**\n\n    **🔹sent:** 175.75GB\n    **🔹recv:** 118.55GB\n    **🔹sent_packets:** 36547698\n    **🔹recv_packets:** 185466554\n\n\n**===================**\n',
    '**===================**\n      **CɪᴘʜᴇʀX Server Details**  \n**===================**\n\n\n**=>>>   CPU   <<<=**\n\n    **🔹current_freq:** 2500.09MHz\n    **🔹total_usage:** 60%\n\n    ●●●●●●○○○○\n\n    **🔹cpu core**\n\n        **🔹core_usage:** 62.9%\n        **🔹current_freq:** 2500.09MHz\n        |██████████▉  |\n       \n**=>>>   RAM   <<<=**\n\n    **🔹free:** 8.23GB\n    **🔹used:** 33.32GB\n    **🔹total:** 60.0GB\n    \n    ●●●●●●○○○○\n\n\n**=>>>   DISK   <<<=**\n\n   **🔹free:** 224.12GB\n    **🔹used:** 131.84GB\n    **🔹total:** 375.02GB\n    **🔹usage:** 37.0%\n\n    |████▍        |\n\n\n**=>>>   NETWORK   <<<=**\n\n    **🔹sent:** 118.55GB\n    **🔹recv:** 168.65GB\n    **🔹sent_packets:** 24786554\n    **🔹recv_packets:** 156745865\n\n\n**===================**\n',
    '**===================**\n      **CɪᴘʜᴇʀX Server Details**  \n**===================**\n\n\n**=>>>   CPU   <<<=**\n\n    **🔹current_freq:** 2500.09MHz\n    **🔹total_usage:** 30%\n\n    ●●●○○○○○○○\n\n    **🔹cpu core**\n\n        **🔹core_usage:** 30.6%\n        **🔹current_freq:** 2500.09MHz\n        |██████████▉  |\n       \n**=>>>   RAM   <<<=**\n\n    **🔹free:** 9.75GB\n    **🔹used:** 36.54GB\n    **🔹total:** 60.0GB\n    \n    ●●●●●●●●●●\n\n\n**=>>>   DISK   <<<=**\n\n   **🔹free:** 224.12GB\n    **🔹used:** 131.84GB\n    **🔹total:** 375.02GB\n    **🔹usage:** 37.0%\n\n    |████▍        |\n\n\n**=>>>   NETWORK   <<<=**\n\n    **🔹sent:** 168.65GB\n    **🔹recv:** 128.35GB\n    **🔹sent_packets:** 56565435\n    **🔹recv_packets:** 1475823589\n\n\n**===================**\n',
    '**===================**\n      **CɪᴘʜᴇʀX Server Details**  \n**===================**\n\n\n**=>>>   CPU   <<<=**\n\n    **🔹current_freq:** 2500.09MHz\n    **🔹total_usage:** 10%\n\n    ●○○○○○○○○○\n\n    **🔹cpu core**\n\n        **🔹core_usage:** 10.2%\n        **🔹current_freq:** 2500.09MHz\n        |██████████▉  |\n       \n**=>>>   RAM   <<<=**\n\n    **🔹free:** 10.20GB\n    **🔹used:** 25.40GB\n    **🔹total:** 60.0GB\n    \n    ●●●●●●○○○○\n\n\n**=>>>   DISK   <<<=**\n\n   **🔹free:** 224.12GB\n    **🔹used:** 131.84GB\n    **🔹total:** 375.02GB\n    **🔹usage:** 37.0%\n\n    |████▍        |\n\n\n**=>>>   NETWORK   <<<=**\n\n    **🔹sent:** 128.35GB\n    **🔹recv:** 108.31GB\n    **🔹sent_packets:** 54635686\n    **🔹recv_packets:** 157865426\n\n\n**===================**\n',
    '**===================**\n      **CɪᴘʜᴇʀX Server Details**  \n**===================**\n\n\n**=>>>   CPU   <<<=**\n\n    **🔹current_freq:** 2500.09MHz\n    **🔹total_usage:** 100%\n\n    ●●●●●●●●●●\n\n    **🔹cpu core**\n\n        **🔹core_usage:** 100.0%\n        **🔹current_freq:** 2500.09MHz\n        |██████████▉  |\n       \n**=>>>   RAM   <<<=**\n\n    **🔹free:** 5.25GB\n    **🔹used:** 31.14GB\n    **🔹total:** 60.0GB\n    \n    ●●●●●●●●●●\n\n\n**=>>>   DISK   <<<=**\n\n   **🔹free:** 224.12GB\n    **🔹used:** 131.84GB\n    **🔹total:** 375.02GB\n    **🔹usage:** 37.0%\n\n    |████▍        |\n\n\n**=>>>   NETWORK   <<<=**\n\n    **🔹sent:** 108.31GB\n    **🔹recv:** 167.17GB\n    **🔹sent_packets:** 84518799\n    **🔹recv_packets:** 124575356\n\n\n**===================**\n',
    '**===================**\n      **CɪᴘʜᴇʀX Server Details**  \n**===================**\n\n\n**=>>>   CPU   <<<=**\n\n    **🔹current_freq:** 2500.09MHz\n    **🔹total_usage:** 70%\n\n    ●●●●●●●○○○\n\n    **🔹cpu core**\n\n        **🔹core_usage:** 76.2%\n        **🔹current_freq:** 2500.09MHz\n        |██████████▉  |\n       \n**=>>>   RAM   <<<=**\n\n    **🔹free:** 8.01GB\n    **🔹used:** 33.27GB\n    **🔹total:** 60.0GB\n    \n    ●●●○○○○○○○\n\n\n**=>>>   DISK   <<<=**\n\n   **🔹free:** 224.12GB\n    **🔹used:** 131.84GB\n    **🔹total:** 375.02GB\n    **🔹usage:** 37.0%\n\n    |████▍        |\n\n\n**=>>>   NETWORK   <<<=**\n\n    **🔹sent:** 167.17GB\n    **🔹recv:** 158.98GB\n    **🔹sent_packets:** 36547698\n    **🔹recv_packets:** 165455856\n\n\n**===================**\n',
]
BIGOOF_INTRO = '┏━━━┓╋╋╋╋┏━━━┓ \n┃┏━┓┃╋╋╋╋┃┏━┓┃ \n┃┃╋┃┣┓┏┓┏┫┃╋┃┃ \n┃┃╋┃┃┗┛┗┛┃┃╋┃┃ \n┃┗━┛┣┓┏┓┏┫┗━┛┃ \n┗━━━┛┗┛┗┛┗━━━┛'
BIGOOF = [
    '╭━━━╮╱╱╱╭━╮ \n┃╭━╮┃╱╱╱┃╭╯ \n┃┃╱┃┣━━┳╯╰╮ \n┃┃╱┃┃╭╮┣╮╭╯ \n┃╰━╯┃╰╯┃┃┃ \n╰━━━┻━━╯╰╯ ',
    '╭━━━╮╱╱╱╱╱╱╭━╮ \n┃╭━╮┃╱╱╱╱╱╱┃╭╯ \n┃┃╱┃┣━━┳━━┳╯╰╮ \n┃┃╱┃┃╭╮┃╭╮┣╮╭╯ \n┃╰━╯┃╰╯┃╰╯┃┃┃ \n ╰━━━┻━━┻━━╯╰╯',
    '╭━━━╮╱╱╱╱╱╱╱╱╱╭━╮ \n┃╭━╮┃╱╱╱╱╱╱╱╱╱┃╭╯ \n┃┃╱┃┣━━┳━━┳━━┳╯╰╮ \n┃┃╱┃┃╭╮┃╭╮┃╭╮┣╮╭╯ \n┃╰━╯┃╰╯┃╰╯┃╰╯┃┃┃ \n╰━━━┻━━┻━━┻━━╯╰╯',
    '╭━━━╮╱╱╱╱╱╱╱╱╱╱╱╱╭━╮ \n┃╭━╮┃╱╱╱╱╱╱╱╱╱╱╱╱┃╭╯ \n┃┃╱┃┣━━┳━━┳━━┳━━┳╯╰╮ \n┃┃╱┃┃╭╮┃╭╮┃╭╮┃╭╮┣╮╭╯ \n┃╰━╯┃╰╯┃╰╯┃╰╯┃╰╯┃┃┃ \n╰━━━┻━━┻━━┻━━┻━━╯╰╯',
    '╭━━━╮╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╭━╮ \n┃╭━╮┃╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱┃╭╯ \n┃┃╱┃┣━━┳━━┳━━┳━━┳━━┳╯╰╮ \n┃┃╱┃┃╭╮┃╭╮┃╭╮┃╭╮┃╭╮┣╮╭╯ \n┃╰━╯┃╰╯┃╰╯┃╰╯┃╰╯┃╰╯┃┃┃ \n╰━━━┻━━┻━━┻━━┻━━┻━━╯╰╯',
    '╭━━━╮╱╱╱╱╱╱╱╱╱╱╱╱╭━╮ \n┃╭━╮┃╱╱╱╱╱╱╱╱╱╱╱╱┃╭╯ \n┃┃╱┃┣━━┳━━┳━━┳━━┳╯╰╮ \n┃┃╱┃┃╭╮┃╭╮┃╭╮┃╭╮┣╮╭╯ \n┃╰━╯┃╰╯┃╰╯┃╰╯┃╰╯┃┃┃ \n╰━━━┻━━┻━━┻━━┻━━╯╰╯',
    '╭━━━╮╱╱╱╱╱╱╱╱╱╭━╮ \n┃╭━╮┃╱╱╱╱╱╱╱╱╱┃╭╯ \n┃┃╱┃┣━━┳━━┳━━┳╯╰╮ \n┃┃╱┃┃╭╮┃╭╮┃╭╮┣╮╭╯ \n┃╰━╯┃╰╯┃╰╯┃╰╯┃┃┃ \n╰━━━┻━━┻━━┻━━╯╰╯',
]
THINK_INTRO = 'thinking'
THINK = [
    'THINKING',
    'THI&K#N₹',
    'T+IN@I?G',
    '¿H$NK∆NG',
    '¶H×NK&N*',
    'NGITHKIN',
    'T+I#K@₹G',
    'Thinking... 🤔',
]
SNAKE = [
    '◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️',
    '◻️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️',
    '◻️◻️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️',
    '◻️◻️◻️️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️',
    '◻️◻️◻️◻️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️',
    '\u200e◻️◻️◻️◻️◻️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️',
    '◻️◻️◻️◻️◻️\n◼️◼️◼️◼️◻️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️',
    '◻️◻️◻️◻️◻️\n◼️◼️◼️◼️◻️\n◼️◼️◼️◼️◻️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️',
    '◻️◻️◻️◻️◻️\n◼️◼️◼️◼️◻️\n◼️◼️◼️◼️◻️\n◼️◼️◼️◼️◻️\n◼️◼️◼️◼️◼️',
    '◻️◻️◻️◻️◻️\n◼️◼️◼️◼️◻️\n◼️◼️◼️◼️◻️\n◼️◼️◼️◼️◻️\n◼️◼️◼️◼️◻️',
    '◻️◻️◻️◻️◻️\n◼️◼️◼️◼️◻️\n◼️◼️◼️◼️◻️\n◼️◼️◼️◼️◻️\n◼️◼️◼️◻️◻️',
    '◻️◻️◻️◻️◻️\n◼️◼️◼️◼️◻️\n◼️◼️◼️◼️◻️\n◼️◼️◼️◼️◻️\n◼️◼️◻️◻️◻️',
    '◻️◻️◻️◻️◻️\n◼️◼️◼️◼️◻️\n◼️◼️◼️◼️◻️\n◼️◼️◼️◼️◻️\n◼️◻️◻️◻️◻️',
    '◻️◻️◻️◻️◻️\n◼️◼️◼️◼️◻️\n◼️◼️◼️◼️◻️\n◼️◼️◼️◼️◻️\n◻️◻️◻️◻️◻️',
    '◻️◻️◻️◻️◻️\n◼️◼️◼️◼️◻️\n◼️◼️◼️◼️◻️\n◻️◼️◼️◼️◻️\n◻️◻️◻️◻️◻️',
    '◻️◻️◻️◻️◻️\n◼️◼️◼️◼️◻️\n◻️◼️◼️◼️◻️\n◻️◼️◼️◼️◻️\n◻️◻️◻️◻️◻️',
    '◻️◻️◻️◻️◻️\n◻️◼️◼️◼️◻️\n◻️◼️◼️◼️◻️\n◻️◼️◼️◼️◻️\n◻️◻️◻️◻️◻️',
    '◻️◻️◻️◻️◻️\n◻️◻️◼️◼️◻️\n◻️◼️◼️◼️◻️\n◻️◼️◼️◼️◻️\n◻️◻️◻️◻️◻️',
    '◻️◻️◻️◻️◻️\n◻️◻️◻️◼️◻️\n◻️◼️◼️◼️◻️\n◻️◼️◼️◼️◻️\n◻️◻️◻️◻️◻️',
    '◻️◻️◻️◻️◻️\n◻️◻️◻️◻️◻️\n◻️◼️◼️◼️◻️\n◻️◼️◼️◼️◻️\n◻️◻️◻️◻️◻️',
    '◻️◻️◻️◻️◻️\n◻️◻️◻️◻️◻️\n◻️◼️◼️◻️◻️\n◻️◼️◼️◼️◻️\n◻️◻️◻️◻️◻️',
    '◻️◻️◻️◻️◻️\n◻️◻️◻️◻️◻️\n◻️◼️◼️◻️◻️\n◻️◼️◼️◻️◻️\n◻️◻️◻️◻️◻️',
    '◻️◻️◻️◻️◻️\n◻️◻️◻️◻️◻️\n◻️◼️◼️◻️◻️\n◻️◼️◻️◻️◻️\n◻️◻️◻️◻️◻️',
    '◻️◻️◻️◻️◻️\n◻️◻️◻️◻️◻️\n◻️◼️◼️◻️◻️\n◻️◻️◻️◻️◻️\n◻️◻️◻️◻️◻️',
    '◻️◻️◻️◻️◻️\n◻️◻️◻️◻️◻️\n◻️◻️◼️◻️◻️\n◻️◻️◻️◻️◻️\n◻️◻️◻️◻️◻️',
    '◻️◻️◻️◻️◻️\n◻️◻️◻️◻️◻️\n◻️◻️◻️◻️◻️\n◻️◻️◻️◻️◻️\n◻️◻️◻️◻️◻️',
    '◻️◻️◻️◻️◻️\n◻️◼️◻️◼️◻️\n◻️◻️◻️◻️◻️\n◻️◼️◼️◼️◻️\n◻️◻️◻️◻️◻️',
]
POLICE_INTRO = 'Police'
POLICE = [
    '🔴🔴🔴⬜⬜⬜🔵🔵🔵\n🔴🔴🔴⬜⬜⬜🔵🔵🔵\n🔴🔴🔴⬜⬜⬜🔵🔵🔵',
    '🔵🔵🔵⬜⬜⬜🔴🔴🔴\n🔵🔵🔵⬜⬜⬜🔴🔴🔴\n🔵🔵🔵⬜⬜⬜🔴🔴🔴',
    '🔴🔴🔴⬜⬜⬜🔵🔵🔵\n🔴🔴🔴⬜⬜⬜🔵🔵🔵\n🔴🔴🔴⬜⬜⬜🔵🔵🔵',
    '🔵🔵🔵⬜⬜⬜🔴🔴🔴\n🔵🔵🔵⬜⬜⬜🔴🔴🔴\n🔵🔵🔵⬜⬜⬜🔴🔴🔴',
    '🔴🔴🔴⬜⬜⬜🔵🔵🔵\n🔴🔴🔴⬜⬜⬜🔵🔵🔵\n🔴🔴🔴⬜⬜⬜🔵🔵🔵',
    '🔵🔵🔵⬜⬜⬜🔴🔴🔴\n🔵🔵🔵⬜⬜⬜🔴🔴🔴\n🔵🔵🔵⬜⬜⬜🔴🔴🔴',
    '🔴🔴🔴⬜⬜⬜🔵🔵🔵\n🔴🔴🔴⬜⬜⬜🔵🔵🔵\n🔴🔴🔴⬜⬜⬜🔵🔵🔵',
    '🔵🔵🔵⬜⬜⬜🔴🔴🔴\n🔵🔵🔵⬜⬜⬜🔴🔴🔴\n🔵🔵🔵⬜⬜⬜🔴🔴🔴',
    '🔴🔴🔴⬜⬜⬜🔵🔵🔵\n🔴🔴🔴⬜⬜⬜🔵🔵🔵\n🔴🔴🔴⬜⬜⬜🔵🔵🔵',
    '🔵🔵🔵⬜⬜⬜🔴🔴🔴\n🔵🔵🔵⬜⬜⬜🔴🔴🔴\n🔵🔵🔵⬜⬜⬜🔴🔴🔴',
    '🔴🔴🔴⬜⬜⬜🔵🔵🔵\n🔴🔴🔴⬜⬜⬜🔵🔵🔵\n🔴🔴🔴⬜⬜⬜🔵🔵🔵',
    '[Heartless](https://t.me/DarkPentester) **Police Service Here**',
]
HER_INTRO = 'loveu'
HER = [
    '😀',
    '👩\u200d🎨',
    '😁',
    '😂',
    '🤣',
    '😃',
    '😄',
    '😅',
    '😊',
    '☺',
    '🙂',
    '🤔',
    '🤨',
    '😐',
    '😑',
    '😶',
    '😣',
    '😥',
    '😮',
    '🤐',
    '😯',
    '😴',
    '😔',
    '😕',
    '☹',
    '🙁',
    '😖',
    '😞',
    '😟',
    '😢',
    '😭',
    '🤯',
    '💔',
    '❤️',
    'I Love You ❤️',
]
DONCE_INTRO = 'Connecting...'
DONCE = [
    '⠀⠀⠀⣶⣿⣶\n⠀⠀⠀⣿⣿⣿⣀\n⠀⣀⣿⣿⣿⣿⣿⣿\n⣶⣿⠛⣭⣿⣿⣿⣿\n⠛⠛⠛⣿⣿⣿⣿⠿\n⠀⠀⠀⠀⣿⣿⣿\n⠀⠀⣀⣭⣿⣿⣿⣿⣀\n⠀⠤⣿⣿⣿⣿⣿⣿⠉\n⠀⣿⣿⣿⣿⣿⣿⠉\n⣿⣿⣿⣿⣿⣿\n⣿⣿⣶⣿⣿\n⠉⠛⣿⣿⣶⣤\n⠀⠀⠉⠿⣿⣿⣤\n⠀⠀⣀⣤⣿⣿⣿\n⠀⠒⠿⠛⠉⠿⣿\n⠀⠀⠀⠀⠀⣀⣿⣿\n⠀⠀⠀⠀⣶⠿⠿⠛\n',
    '⠀⠀⠀⠀⠀⠀⠀⠀⠀⣤⣤\n⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⣿⣿\n⠀⠀⣶⠀⠀⣀⣤⣶⣤⣉⣿⣿⣤⣀\n⠤⣤⣿⣤⣿⠿⠿⣿⣿⣿⣿⣿⣿⣿⣿⣀\n⠀⠛⠿⠀⠀⠀⠀⠉⣿⣿⣿⣿⣿⠉⠛⠿⣿⣤\n⠀⠀⠀⠀⠀⠀⠀⠀⠿⣿⣿⣿⠛⠀⠀⠀⣶⠿\n⠀⠀⠀⠀⠀⠀⠀⠀⣀⣿⣿⣿⣿⣤⠀⣿⠿\n⠀⠀⠀⠀⠀⠀⠀⣶⣿⣿⣿⣿⣿⣿⣿⣿\n⠀⠀⠀⠀⠀⠀⠀⠿⣿⣿⣿⣿⣿⠿⠉⠉\n⠀⠀⠀⠀⠀⠀⠀⠉⣿⣿⣿⣿⠿\n⠀⠀⠀⠀⠀⠀⠀⠀⣿⣿⣿⠉\n⠀⠀⠀⠀⠀⠀⠀⠀⣛⣿⣭⣶⣀\n⠀⠀⠀⠀⠀⠀⠀⠀⣿⣿⣿⣿⣿\n⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⣿⠉⠛⣿\n⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⣿⠀⠀⣿⣿\n⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⣉⠀⣶⠿\n⠀⠀⠀⠀⠀⠀⠀⠀⣶⣿⠿\n⠀⠀⠀⠀⠀⠀⠀⠛⠿⠛\n',
    '⠀⠀⠀⠀⠀⠀⠀⠀⠀⣤⣶\n⠀⠀⠀⠀⠀⣀⣀⠀⣶⣿⣿⠶\n⣶⣿⠿⣿⣿⣿⣿⣿⣿⣿⣿⣤⣤\n⠀⠉⠶⣶⣀⣿⣿⣿⣿⣿⣿⣿⠿⣿⣤⣀\n⠀⠀⠀⣿⣿⠿⠉⣿⣿⣿⣿⣭⠀⠶⠿⠿\n⠀⠀⠛⠛⠿⠀⠀⣿⣿⣿⣉⠿⣿⠶\n⠀⠀⠀⠀⠀⣤⣶⣿⣿⣿⣿⣿\n⠀⠀⠀⠀⠀⣿⣿⣿⣿⣿⣿⣿⠒\n⠀⠀⠀⠀⣀⣿⣿⣿⣿⣿⣿⣿\n⠀⠀⠀⠀⠀⣿⣿⣿⠛⣭⣭⠉\n⠀⠀⠀⠀⠀⣿⣿⣭⣤⣿⠛\n⠀⠀⠀⠀⠀⠛⠿⣿⣿⣿⣭\n⠀⠀⠀⠀⠀⠀⠀⣿⣿⠉⠛⠿⣶⣤\n⠀⠀⠀⠀⠀⠀⣀⣿⠀⠀⣶⣶⠿⠿⠿\n⠀⠀⠀⠀⠀⠀⣿⠛\n⠀⠀⠀⠀⠀⠀⣭⣶\n',
    '⠀⠀⠀⠀⠀⠀⣶⣿⣶\n⠀⠀⠀⣤⣤⣤⣿⣿⣿\n⠀⠀⣶⣿⣿⣿⣿⣿⣿⣿⣶\n⠀⠀⣿⣿⣿⣿⣿⣿⣿⣿⣿\n⠀⠀⣿⣉⣿⣿⣿⣿⣉⠉⣿⣶\n⠀⠀⣿⣿⣿⣿⣿⣿⣿⣿⠿⣿\n⠀⣤⣿⣿⣿⣿⣿⣿⣿⠿⠀⣿⣶\n⣤⣿⠿⣿⣿⣿⣿⣿⠿⠀⠀⣿⣿⣤\n⠉⠉⠀⣿⣿⣿⣿⣿⠀⠀⠒⠛⠿⠿⠿\n⠀⠀⠀⠉⣿⣿⣿⠀⠀⠀⠀⠀⠀⠉\n⠀⠀⠀⣿⣿⣿⣿⣿⣶\n⠀⠀⠀⠀⣿⠉⠿⣿⣿\n⠀⠀⠀⠀⣿⣤⠀⠛⣿⣿\n⠀⠀⠀⠀⣶⣿⠀⠀⠀⣿⣶\n⠀⠀⠀⠀⠀⠀⠀⠀⠀⣭⣿⣿\n⠀⠀⠀⠀⠀⠀⠀⠀⣤⣿⣿⠉\n',
    '⠀⠀⠀⠀⠀⠀⣤⣶⣶\n⠀⠀⠀⠀⠀⠀⣿⣿⣿⣿⣀⣀\n⠀⠀⠀⠀⠀⣀⣶⣿⣿⣿⣿⣿⣿\n⣤⣶⣀⠿⠶⣿⣿⣿⠿⣿⣿⣿⣿\n⠉⠿⣿⣿⠿⠛⠉⠀⣿⣿⣿⣿⣿\n⠀⠀⠉⠀⠀⠀⠀⠀⠀⣿⣿⣿⣿⣤⣤\n⠀⠀⠀⠀⠀⠀⠀⣤⣶⣿⣿⣿⣿⣿⣿\n⠀⠀⠀⠀⠀⣀⣿⣿⣿⣿⣿⠿⣿⣿⣿⣿\n⠀⠀⠀⠀⣀⣿⣿⣿⠿⠉⠀⠀⣿⣿⣿⣿\n⠀⠀⠀⠀⣿⣿⠿⠉⠀⠀⠀⠀⠿⣿⣿⠛\n⠀⠀⠀⠀⠛⣿⣿⣀⠀⠀⠀⠀⠀⣿⣿⣀\n⠀⠀⠀⠀⠀⣿⣿⣿⠀⠀⠀⠀⠀⠿⣿⣿\n⠀⠀⠀⠀⠀⠉⣿⣿⠀⠀⠀⠀⠀⠀⠉⣿\n⠀⠀⠀⠀⠀⠀⠀⣿⠀⠀⠀⠀⠀⠀⣀⣿\n⠀⠀⠀⠀⠀⠀⣀⣿⣿\n⠀⠀⠀⠀⠤⣿⠿⠿⠿\n',
]
BRAIN = [
    'YOᑌᖇ ᗷᖇᗩIᑎ ➡️ 🧠\n\n🧠         <(^_^ <)🗑',
    'YOᑌᖇ ᗷᖇᗩIᑎ ➡️ 🧠\n\n🧠       <(^_^ <)  🗑',
    'YOᑌᖇ ᗷᖇᗩIᑎ ➡️ 🧠\n\n🧠     <(^_^ <)    🗑',
    'YOᑌᖇ ᗷᖇᗩIᑎ ➡️ 🧠\n\n🧠   <(^_^ <)      🗑',
    'YOᑌᖇ ᗷᖇᗩIᑎ ➡️ 🧠\n\n🧠 <(^_^ <)        🗑',
    'YOᑌᖇ ᗷᖇᗩIᑎ ➡️ 🧠\n\n🧠<(^_^ <)         🗑',
    'YOᑌᖇ ᗷᖇᗩIᑎ ➡️ 🧠\n\n(> ^_^)>🧠         🗑',
    'YOᑌᖇ ᗷᖇᗩIᑎ ➡️ 🧠\n\n  (> ^_^)>🧠       🗑',
    'YOᑌᖇ ᗷᖇᗩIᑎ ➡️ 🧠\n\n    (> ^_^)>🧠     🗑',
    'YOᑌᖇ ᗷᖇᗩIᑎ ➡️ 🧠\n\n      (> ^_^)>🧠   🗑',
    'YOᑌᖇ ᗷᖇᗩIᑎ ➡️ 🧠\n\n        (> ^_^)>🧠 🗑',
    'YOᑌᖇ ᗷᖇᗩIᑎ ➡️ 🧠\n\n          (> ^_^)>🧠🗑',
    'YOᑌᖇ ᗷᖇᗩIᑎ ➡️ 🧠\n\n           (> ^_^)>🗑',
    'YOᑌᖇ ᗷᖇᗩIᑎ ➡️ 🧠\n\n           <(^_^ <)🗑',
]
HUMAN = [
    '⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬜⬜⬜⬜⬜⬜⬜\n⬜⬜⬜⬜⬜⬜⬜\n🔲🔲🔲🔲🔲🔲🔲',
    '⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛🚗\n⬜⬜⬜⬜⬜⬜⬜\n⬜⬜⬜⬜⬜⬜⬜\n🔲🔲🔲🔲🔲🔲🔲',
    '⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛🚗⬛\n⬜⬜⬜⬜⬜⬜⬜\n⬜⬜⬜⬜⬜⬜⬜\n🔲🔲🔲🔲🔲🔲🔲',
    '⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛🚗⬛⬛\n⬜⬜⬜⬜⬜⬜⬜\n⬜⬜⬜⬜⬜⬜⬜\n🔲🔲🔲🔲🔲🔲🔲',
    '⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛🚗⬛⬛⬛\n⬜⬜⬜⬜⬜⬜⬜\n⬜⬜⬜⬜⬜⬜⬜\n🔲🔲🔲🔲🔲🔲🔲',
    '⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬛⬛🚗⬛⬛⬛⬛\n⬜⬜⬜⬜⬜⬜⬜\n⬜⬜⬜⬜⬜⬜⬜\n🔲🔲🔲🔲🔲🔲🔲',
    '⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬛🚗⬛⬛⬛⬛⬛\n⬜⬜⬜⬜⬜⬜⬜\n⬜⬜⬜⬜⬜⬜⬜\n🔲🔲🔲🔲🔲🔲🔲',
    '⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n🚗⬛⬛⬛⬛⬛⬛\n⬜⬜⬜⬜⬜⬜⬜\n⬜⬜⬜⬜⬜⬜⬜\n🔲🔲🔲🔲🔲🔲🔲',
    '⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬜⬜⬜⬜⬜⬜⬜\n⬜⬜⬜⬜⬜⬜⬜\n🔲🔲🔲🔲🔲🔲🔲',
    '⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬜⬜⬜😊⬜⬜⬜\n⬜⬜⬜⬜⬜⬜⬜\n🔲🔲🔲🔲🔲🔲🔲',
    '⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛😊⬛⬛⬛\n⬛⬜⬜⬜⬜⬜⬛\n⬛⬛⬛⬜⬛⬛⬛\n⬛⬛⬜⬛⬜⬛⬛\n⬛⬛⬜⬛⬜⬛⬛\n⬛⬛⬜⬛⬜⬛⬛\n🔲🔲🔲🔲🔲🔲🔲',
    '⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛😊⬛⬛⬛\n⬛⬜⬜⬜⬜⬜⬛\n⬛⬛⬛⬜⬛⬛⬛\n⬛⬛⬜⬛⬜⬛⬛\n⬛⬛⬜⬛⬛⬜⬛\n⬛⬛⬜⬛⬛⬛⬛\n🔲🔲🔲🔲🔲🔲🔲',
    '⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛😊⬛⬛⬛\n⬛⬜⬜⬜⬜⬜⬛\n⬛⬛⬛⬜⬛⬛⬛\n⬛⬛⬜⬛⬜⬛⬛\n⬛⬜⬛⬛⬛⬜⬛\n⬛⬛⬛⬛⬛⬛⬛\n🔲🔲🔲🔲🔲🔲🔲',
    '⬛⬛⬛⬛⬛⬛⬛\n⬛⬜⬛😊⬛⬜⬛\n⬛⬛⬜⬜⬜⬛⬛\n⬛⬛⬛⬜⬛⬛⬛\n⬛⬛⬜⬛⬜⬛⬛\n⬛⬜⬛⬛⬛⬜⬛\n⬛⬛⬛⬛⬛⬛⬛\n🔲🔲🔲🔲🔲🔲🔲',
    '⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛😊⬛⬛⬛\n⬛⬛⬜⬜⬜⬛⬛\n⬛⬜⬛⬜⬛⬜⬛\n⬛⬛⬜⬛⬜⬛⬛\n⬛⬛⬜⬛⬜⬛⬛\n⬛⬛⬜⬛⬜⬛⬛\n🔲🔲🔲🔲🔲🔲🔲',
    '⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬛⬛⬛⬛⬛⬛⬛\n⬜⬜⬜😊⬜⬜⬜\n⬜⬜⬜⬜⬜⬜⬜\n🔲🔲🔲🔲🔲🔲🔲',
]
MC = [
    '◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️',
    '◻️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️',
    '◼️◻️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️',
    '◼️◼️◻️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️',
    '◼️◼️◼️◻️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️',
    '◼️◼️◼️◼️◻️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️',
    '◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◻️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️',
    '◼️◼️◼️◼️◼️\n◼️◼️◼️◻️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️',
    '◼️◼️◼️◼️◼️\n◼️◼️◻️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️',
    '◼️◼️◼️◼️◼️\n◼️◻️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️',
    '◼️◼️◼️◼️◼️\n◻️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️',
    '◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◻️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️',
    '◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◻️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️',
    '◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◻️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️',
    '◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◻️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️',
    '◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◻️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️',
    '◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◻️\n◼️◼️◼️◼️◼️',
    '◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◻️◼️\n◼️◼️◼️◼️◼️',
    '◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◻️◼️◼️\n◼️◼️◼️◼️◼️',
    '◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◻️◼️◼️◼️\n◼️◼️◼️◼️◼️',
    '◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◻️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️',
    '◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◻️◼️◼️◼️◼️',
    '◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◻️◼️◼️◼️',
    '◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◻️◼️◼️',
    '◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◻️◼️',
    '◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◻️',
    '◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️◼️◼️',
    '◼️◼️◼️◼️◼️\n◼️◻️◼️◻️◼️\n◼️◼️◼️◼️◼️\n◼️◻️◻️◻️◼️\n◼️◼️◼️◼️◼️',
]
SOLAR = [
    '`◼️◼️◼️◼️◼️\n◼️◼️◼️◼️☀\n◼️◼️🌎◼️◼️\n🌕◼️◼️◼️◼️\n◼️◼️◼️◼️◼️`',
    '`◼️◼️◼️◼️◼️\n🌕◼️◼️◼️◼️\n◼️◼️🌎◼️◼️\n◼️◼️◼️◼️☀\n◼️◼️◼️◼️◼️`',
    '`◼️🌕◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️🌎◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️☀◼️`',
    '`◼️◼️◼️🌕◼️\n◼️◼️◼️◼️◼️\n◼️◼️🌎◼️◼️\n◼️◼️◼️◼️◼️\n◼️☀◼️◼️◼️`',
    '`◼️◼️◼️◼️◼️\n◼️◼️◼️◼️🌕\n◼️◼️🌎◼️◼️\n☀◼️◼️◼️◼️\n◼️◼️◼️◼️◼️`',
    '`◼️◼️◼️◼️◼️\n☀◼️◼️◼️◼️\n◼️◼️🌎◼️◼️\n◼️◼️◼️◼️🌕\n◼️◼️◼️◼️◼️`',
    '`◼️☀◼️◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️🌎◼️◼️\n◼️◼️◼️◼️◼️\n◼️◼️◼️🌕◼️`',
    '`◼️◼️◼️☀◼️\n◼️◼️◼️◼️◼️\n◼️◼️🌎◼️◼️\n◼️◼️◼️◼️◼️\n◼️🌕◼️◼️◼️`',
]
XMAS_INTRO = '😊𝓜𝓔𝓡𝓡𝓨 𝓒𝓗𝓡𝓘𝓢𝓣𝓜𝓐𝓢😁'
XMAS = [
    '😀😀                              😀😀\n😀😀😀                      😀😀😀\n😀😀😀😀            😀😀😀😀\n😀😀    😀😀    😀😀    😀😀\n😀😀        😀😀😀        😀😀\n😀😀             😀             😀😀\n😀😀                              😀😀\n😀😀                              😀😀\n😀😀                              😀😀\n😀😀                              😀😀',
    '🤩🤩🤩🤩🤩🤩🤩🤩\n🤩🤩🤩🤩🤩🤩🤩🤩\n🤩🤩\n🤩🤩\n🤩🤩🤩🤩🤩🤩\n🤩🤩🤩🤩🤩🤩\n🤩🤩\n🤩🤩\n🤩🤩🤩🤩🤩🤩🤩🤩\n🤩🤩🤩🤩🤩🤩🤩🤩',
    '😉😉😉😉😉😉😉\n😉😉😉😉😉😉😉😉\n😉😉                     😉😉\n😉😉                     😉😉\n😉😉😉😉😉😉😉😉\n😉😉😉😉😉😉😉\n😉😉    😉😉\n😉😉         😉😉\n😉😉              😉😉\n😉😉                  😉😉',
    '⭐️⭐️⭐️⭐️⭐️⭐️\n⭐️⭐️⭐️⭐️⭐️⭐️⭐️⭐️\n⭐️⭐️                     ⭐️⭐️\n⭐️⭐️                     ⭐️⭐️\n⭐️⭐️⭐️⭐️⭐️⭐️⭐️⭐️\n⭐️⭐️⭐️⭐️⭐️⭐️⭐️\n⭐️⭐️    ⭐️⭐️\n⭐️⭐️         ⭐️⭐️\n⭐️⭐️              ⭐️⭐️\n⭐️⭐️                  ⭐️⭐️',
    '💥💥                    💥💥\n   💥💥              💥💥\n      💥💥        💥💥\n         💥💥  💥💥\n            💥💥💥\n              💥💥\n              💥💥\n              💥💥\n              💥💥\n              💥💥',
    '\n     🧣🧣🧣🧣🧣🧣\n     🧣🧣🧣🧣🧣🧣🧣🧣\n   🧣🧣                      🧣🧣\n 🧣🧣\n🧣🧣\n🧣🧣\n 🧣🧣\n   🧣🧣                      🧣🧣\n     🧣🧣🧣🧣🧣🧣🧣🧣\n         🧣🧣🧣🧣🧣🧣',
    '🌟🌟                        🌟🌟\n🌟🌟                        🌟🌟\n🌟🌟                        🌟🌟\n🌟🌟                        🌟🌟\n🌟🌟🌟🌟🌟🌟🌟🌟🌟\n🌟🌟🌟🌟🌟🌟🌟🌟🌟\n🌟🌟                        🌟🌟\n🌟🌟                        🌟🌟\n🌟🌟                        🌟🌟\n🌟🌟                        🌟🌟',
    '💝💝💝💝💝💝💝\n💝💝💝💝💝💝💝💝\n💝💝                     💝💝\n💝💝                     💝💝\n💝💝💝💝💝💝💝💝\n💝💝💝💝💝💝💝\n💝💝    💝💝\n💝💝         💝💝\n💝💝              💝💝\n💝💝                  💝💝',
    '🎅🎅🎅🎅🎅🎅\n🎅🎅🎅🎅🎅🎅\n          🎅🎅\n          🎅🎅\n          🎅🎅\n          🎅🎅\n          🎅🎅\n          🎅🎅\n🎅🎅🎅🎅🎅🎅\n🎅🎅🎅🎅🎅🎅',
    '       💫💫💫💫💫\n  💫💫💫💫💫💫💫\n  💫💫                 💫💫\n💫💫\n  💫💫💫💫💫💫\n      💫💫💫💫💫💫\n                            💫💫\n💫💫                 💫💫\n  💫💫💫💫💫💫💫\n       💫💫💫💫💫',
    '✨✨✨✨✨✨✨✨\n✨✨✨✨✨✨✨✨\n               ✨✨\n               ✨✨\n               ✨✨\n               ✨✨\n               ✨✨\n               ✨✨\n               ✨✨',
    '☄️☄️                              ☄️☄️\n☄️☄️☄️                      ☄️☄️☄️\n☄️☄️☄️☄️            ☄️☄️☄️☄️\n☄️☄️    ☄️☄️    ☄️☄️    ☄️☄️\n☄️☄️        ☄️☄️☄️        ☄️☄️\n☄️☄️             ☄️             ☄️☄️\n☄️☄️                              ☄️☄️\n☄️☄️                              ☄️☄️\n☄️☄️                              ☄️☄️\n☄️☄️                              ☄️☄️',
    '\u206d\n                    🌎\n                  🌎🌎\n               🌎🌎🌎\n            🌎🌎 🌎🌎\n          🌎🌎    🌎🌎\n        🌎🌎       🌎🌎\n      🌎🌎🌎🌎🌎🌎\n     🌎🌎🌎🌎🌎🌎🌎\n   🌎🌎                 🌎🌎\n  🌎🌎                    🌎🌎\n🌎🌎                       🌎🌎',
    '       🪐🪐🪐🪐🪐\n  🪐🪐🪐🪐🪐🪐🪐\n  🪐🪐                 🪐🪐\n🪐🪐\n  🪐🪐🪐🪐🪐🪐\n      🪐🪐🪐🪐🪐🪐\n                            🪐🪐\n🪐🪐                 🪐🪐\n  🪐🪐🪐🪐🪐🪐🪐\n       🪐🪐🪐🪐🪐',
]
FHACK = [
    '`Connecting To CɪᴘʜᴇʀX Server...`',
    '`Target Selected.`',
    '`Hacking... 0%\n▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒ `\n`Looking for Telegram Data...`\nETA: 0m, 20s',
    '`Hacking... 4%\n█▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒ `\n`Found SD Directory...`\n`Looking for Telegram Data : ✅`\nETA: 0m, 10s',
    '`Hacking... 8%\n██▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒ `\n`Searching for Databases....`\n`Looking for Telegram Data : ✅`\n`Found Telegram Database Directory : ✅ `\nETA: 0m, 15s',
    '`Hacking... 20%\n█████▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒`\n`Found msgstore.db.crypt12...`\n`Looking for Telegram Data : ✅`\n`Found Telegram Database Directory : ✅ `\n`Searching for Databases : ✅ `\nETA: 0m, 09s',
    '`Hacking... 36%\n█████████▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒ `\n`Trying to Decrypt...`\n`Looking for Telegram Data : ✅`\n`Found Telegram Database Directory : ✅\n`Searching for Databases : ✅`\n`Found msgstore.db.crypt12 :  ✅`\n`⚠️ error occurred ..`\nETA: 0m, 25s',
    '`Hacking... 52%\n█████████████▒▒▒▒▒▒▒▒▒▒▒▒ `\n`Decryption successful!`\n`Looking for Telegram Data : ✅`\n`⚠️ error occurred ..`\n`Found Telegram Database Directory : ✅`\n`⚠️ Error Occurred ...`\n`Searching for Databases : ✅`\n`Found msgstore.db.crypt12 :  ✅`\nETA: 0m, 25s',
    '`Hacking... 84%\n█████████████████████▒▒▒▒ `\n`Scanning file...`\n`Looking for Telegram Data : ✅`\n`⚠️ error occurred ..`\n`Found Telegram Database Directory : ✅`\n`⚠️ Error Occurred ..`\n`⚠️ Error Occurred ...`\n`Searching for Databases : ✅`\n`Found msgstore.db.crypt12 :  ✅`\n`Scanning File :  ✅`\nETA: 0m, 16s',
    '`Hacking... 100%\n` 98% HACKED`',
    '`Targeted Account Hacked By CɪᴘʜᴇʀX`\n\n`_______________________`\n`result ... :)`\n\n`Chatlist : ✅`\n`Calls : ✅`\n`groups : ✅`\n `Contacts : ✅`\n`Channel : ✅`\n`Deleted Messages : ❌`\n`Edited Messages : ❌`\n`All API Tokens : ✅`',
]
THACK_INTRO = 'Starting CɪᴘʜᴇʀX Servers'
THACK = [
    '`Connecting To T-800 At 149.154.167.51 - IPV4 - TELEGRAM // DC-4/1`',
    '`Hacking... 0%\n▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒ `\n\n\n  TERMINAL:\nDownloading Bruteforce-Telegram-0.1.tar.gz (9.3 kB)',
    '`Hacking... 4%\n█▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒ `\n\n\n  TERMINAL:\nDownloading Bruteforce-Telegram-0.1.tar.gz (9.3 kB)\nCollecting Data Package',
    '`Hacking... 8%\n██▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒ `\n\n\n  TERMINAL:\nDownloading Bruteforce-Telegram-0.1.tar.gz (9.3 kB)\nCollecting Data Package\n  Downloading Telegram-Data-Sniffer-7.1.1-py2.py3-none-any.whl (82 kB)',
    "`Hacking... 20%\n█████▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒ `\n\n\n  TERMINAL:\nDownloading Bruteforce-Telegram-0.1.tar.gz (9.3 kB)\nCollecting Data Package\n  Downloading Telegram-Data-Sniffer-7.1.1-py2.py3-none-any.whl (82 kB)\nBuilding wheel for Tg-Bruteforcing (setup.py): finished with status 'done'",
    "`Hacking... 36%\n█████████▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒ `\n\n\n  TERMINAL:\nDownloading Bruteforce-Telegram-0.1.tar.gz (9.3 kB)\nCollecting Data Package\n  Downloading Telegram-Data-Sniffer-7.1.1-py2.py3-none-any.whl (82 kB)\nBuilding wheel for Tg-Bruteforcing (setup.py): finished with status 'done'\nCreated wheel for telegram: filename=Telegram-Data-Sniffer-0.0.1-py3-none-any.whl size=1306 sha256=cb224caad7fe01a6649188c62303cd4697c1869fa12d280570bb6ac6a88e6b7e",
    "`Hacking... 52%\n█████████████▒▒▒▒▒▒▒▒▒▒▒▒ `\n\n\n  TERMINAL:\nDownloading Bruteforce-Telegram-0.1.tar.gz (9.3 kB)\nCollecting Data Package\n  Downloading Telegram-Data-Sniffer-7.1.1-py2.py3-none-any.whl (82 kB)\nBuilding wheel for Tg-Bruteforcing (setup.py): finished with status 'done'\nCreated wheel for telegram: filename=Telegram-Data-Sniffer-0.0.1-py3-none-any.whl size=1306 sha256=cb224caad7fe01a6649188c62303cd4697c1869fa12d280570bb6ac6a88e6b7e\n  Stored in directory: /app/.cache/pip/wheels/a2/9f/b5/650dd4d533f0a17ca30cc11120b176643d27e0e1f5c9876b5b",
    "`Hacking... 84%\n█████████████████████▒▒▒▒ `\n\n\n  TERMINAL:\nDownloading Bruteforce-Telegram-0.1.tar.gz (9.3 kB)\nCollecting Data Package\n  Downloading Telegram-Data-Sniffer-7.1.1-py2.py3-none-any.whl (82 kB)\nBuilding wheel for Tg-Bruteforcing (setup.py): finished with status 'done'\nCreated wheel for telegram: filename=Telegram-Data-Sniffer-0.0.1-py3-none-any.whl size=1306 sha256=cb224caad7fe01a6649188c62303cd4697c1869fa12d280570bb6ac6a88e6b7e\n  Stored in directory: /app/.cache/pip/wheels/a2/9f/b5/650dd4d533f0a17ca30cc11120b176643d27e0e1f5c9876b5b\n\n **Successfully Hacked Telegram Server Database**",
    "`Hacking... 100%\n█████████HACKED███████████ `\n\n\n  TERMINAL:\nDownloading Bruteforce-Telegram-0.1.tar.gz (9.3 kB)\nCollecting Data Package\n  Downloading Telegram-Data-Sniffer-7.1.1-py2.py3-none-any.whl (82 kB)\nBuilding wheel for Tg-Bruteforcing (setup.py): finished with status 'done'\nCreated wheel for telegram: filename=Telegram-Data-Sniffer-0.0.1-py3-none-any.whl size=1306 sha256=cb224caad7fe01a6649188c62303cd4697c1869fa12d280570bb6ac6a88e6b7e\n  Stored in directory: /app/.cache/pip/wheels/a2/9f/b5/650dd4d533f0a17ca30cc11120b176643d27e0e1f5c9876b5b\n\n **Successfully Hacked Telegram Server Database**\n\n\n🔹Output: Generating.....",
    "`Hacked...\n\nYour account has been hacked by CɪᴘʜᴇʀX...`\n\nTERMINAL:\nDownloading Bruteforce-Telegram-0.1.tar.gz (9.3 kB)\nCollecting Data Package\n  Downloading Telegram-Data-Sniffer-7.1.1-py2.py3-none-any.whl (82 kB)\nBuilding wheel for Tg-Bruteforcing (setup.py): finished with status 'done'\nCreated wheel for telegram: filename=Telegram-Data-Sniffer-0.0.1-py3-none-any.whl size=1306 sha256=cb224caad7fe01a6649188c62303cd4697c1869fa12d280570bb6ac6a88e6b7e\n  Stored in directory: /app/.cache/pip/wheels/a2/9f/b5/650dd4d533f0a17ca30cc11120b176643d27e0e1f5c9876b5b\n\n **Successfully Hacked this Account From Telegram Database**\n\n\n🔹**Output:** Successful",
]
WHACK = [
    'Looking for WhatsApp databases in targeted person...',
    ' User online: True\nTelegram access: True\nRead Storage: True ',
    'Hacking... 0%\n[░░░░░░░░░░░░░░░░░░░░]\n`Looking for WhatsApp...`\nETA: 0m, 20s',
    'Hacking... 11.07%\n[██░░░░░░░░░░░░░░░░░░]\n`Looking for WhatsApp...`\nETA: 0m, 18s',
    'Hacking... 20.63%\n[███░░░░░░░░░░░░░░░░░]\n`Found folder C:/WhatsApp`\nETA: 0m, 16s',
    'Hacking... 34.42%\n[█████░░░░░░░░░░░░░░░]\n`Found folder C:/WhatsApp`\nETA: 0m, 14s',
    'Hacking... 42.17%\n[███████░░░░░░░░░░░░░]\n`Searching for databases`\nETA: 0m, 12s',
    'Hacking... 55.30%\n[█████████░░░░░░░░░░░]\n`Found msgstore.db.crypt12`\nETA: 0m, 10s',
    'Hacking... 64.86%\n[███████████░░░░░░░░░]\n`Found msgstore.db.crypt12`\nETA: 0m, 08s',
    'Hacking... 74.02%\n[█████████████░░░░░░░]\n`Trying to Decrypt...`\nETA: 0m, 06s',
    'Hacking... 86.21%\n[███████████████░░░░░]\n`Trying to Decrypt...`\nETA: 0m, 04s',
    'Hacking... 93.50%\n[█████████████████░░░]\n`Decryption successful!`\nETA: 0m, 02s',
    'Hacking... 100%\n[████████████████████]\n`Scanning file...`\nETA: 0m, 00s',
    'Hacking complete!\nUploading file...',
    'Targeted Account Hacked...!\n\n ✅ File has been successfully uploaded to CɪᴘʜᴇʀX server.\nWhatsApp Database:\n`./DOWNLOADS/msgstore.db.crypt12`',
]
JOON = [
    'J',
    'Joo',
    'Jooo',
    'Joooo',
    'Jooooo',
    'Joooooo',
    'Jooooooo',
    'Joooooooo',
    'Jooooooooo',
    'Joooooooooo',
    'Joooooooooon',
]
OK = [
    'ok',
    'Ok',
    'ok',
    'Ok',
    'ok',
    'Ok',
    'ok',
    'Ok',
    'ok',
    'Ok',
]
CHEART = [
    '❤️',
    '💙',
    '💛',
    '💚',
    '🧡',
    '💜',
    '🤎',
    '🖤',
    '🤍',
    '💜',
    '🤎',
    '🤍',
    '🧡',
    '💚',
    '💛',
    '💙',
    '❤️',
    '💝',
]
FINGER = [
    '🖕🏻',
    '🖕',
    '🖕🏼',
    '🖕🏽',
    '🖕🏾',
    '🖕🏿',
    '🖕🏾',
    '🖕🏽',
    '🖕🏼',
    '🖕',
    '🖕🏻',
    '🖕🏽',
    '🖕🏾',
    '🖕🏿',
    '🖕🏾',
    '🖕🏽',
    '🖕',
    '🖕🏼',
]
BILLY = [
    '👍',
    '👍🏻',
    '👍🏼',
    '👍🏽',
    '👍🏾',
    '👍🏿',
    '👍🏾',
    '👍🏽',
    '👍🏼',
    '👍🏻',
]
AGREE = [
    '👌',
    '👌🏻',
    '👌🏼',
    '👌🏽',
    '👌🏾',
    '👌🏿',
    '👌🏾',
    '👌🏽',
    '👌🏼',
    '👌🏻',
]
GOOD = [
    '.     😍😊😍😊😍😍\n 😊😍😍😍😍😊😍😊\n  😍😊                     😊😊\n 😍😍\n😍😊                😊😍😊😍\n😍😊                😍😊😊😊\n😍😊                        😊😍\n   😊😊                      😍😍\n     😍😊😍😍😍😊😊😍  \n          😊😊😊😍😍😊 ',
    '.           😍😊😊😊😍\n 😍😊😍😍😊😍😊\n   😍😊                   😊😍\n 😍😊                       😍😊\n😊😍                         😍😍\n😊😊                         😍😍\n 😊😊                       😍😍\n   😊😊                   😍😊\n      😍😍😍😍😍😍😊\n            😊😊😍😍😍',
    '.           😊😊😍😊😊\n     😊😍😍😍😊😍😊\n   😊😍                   😍😊\n 😊😊                       😍😊\n😍😍                         😍😊\n😍😍                         😊😊\n 😍😊                       😍😍\n   😊😍                   😊😊\n      😊😊😍😍😊😊😊\n            😍😊😊😊😊',
    '😊😍😊😍😊😍😊\n😍😍😍😊😍😍😍😊\n😍😊                      😊😊\n😊😊                         😊😊\n😍😊                         😊😍\n😍😍                         😊😊\n😍😊                         😊😊\n😊😍                      😍😊\n😊😍😍😍😊😊😊😊\n😊😊😊😍😍😊😍\n\n',
    '😍😊                              😍😍\n😊😍😊                      😍😊😊\n😍😊😍😊            😊😊😊😍\n😊😊    😊😊    😊😊    😊😊\n😊😊        😊😊😊        😍😍\n😊😊             😍             😍😊\n😍😊                              😍😊\n😊😍                              😊😊\n😍😍                              😊😊\n😊😊                              😍😊',
    '.           😍😊😊😊😍\n 😍😊😍😍😊😍😊\n   😍😊                   😊😍\n 😍😊                       😍😊\n😊😍                         😍😍\n😊😊                         😍😍\n 😊😊                       😍😍\n   😊😊                   😍😊\n      😍😍😍😍😍😍😊\n            😊😊😍😍😍',
    '😍😍😍😊😍😊😍\n😍😊😍😍😊😊😊😊\n😍😊                     😍😍\n😊😍                     😍😍\n😊😍😍😍😊😊😊😊\n😍😊😍😍😊😍😍\n😊😊    😍😊\n😍😍         😍😊\n😊😊              😊😊\n😊😊                  😍😊',
    '😊😍                           😍😍\n😍😍😊                       😊😍\n😊😊😍😍                 😍😊\n😍😍  😊😊               😍😊\n😍😊     😊😊            😊😊\n😊😍         😊😊        😍😊\n😊😍             😍😍    😍😍\n😊😍                 😊😍😊😊\n😍😊                     😊😍😊\n😍😊                          😊😍',
    '😊😊😊😍😊😍\n😊😍😊😍😍😍\n          😍😍\n          😍😍\n          😍😊\n          😍😊\n          😊😊\n          😊😊\n😍😊😍😊😊\n😊😍😍😊😊😊',
    '😊😍                           😍😍\n😍😍😊                       😊😍\n😊😊😍😍                 😍😊\n😍😍  😊😊               😍😊\n😍😊     😊😊            😊😊\n😊😍         😊😊        😍😊\n😊😍             😍😍    😍😍\n😊😍                 😊😍😊😊\n😍😊                     😊😍😊\n😍😊                          😊😍',
    '.     😍😊😍😊😍😍\n 😊😍😍😍😍😊😍😊\n  😍😊                     😊😊\n 😍😍\n😍😊                😊😍😊😍\n😍😊                😍😊😊😊\n😍😊                        😊😍\n   😊😊                      😍😍\n     😍😊😍😍😍😊😊😍  \n          😊😊😊😍😍😊 ',
    'GOOD MORNING ,HAVE A NICE DAY 😊',
]
TOWN = [
    '☁☁ 🌞     ☁           ☁\n       ☁  ✈         ☁    🚁    ☁    ☁         ☁          ☁     ☁   ☁\n\n🏬🏨🏫🏢🏤🏥🏦🏪🏫\n              🌲/     l🚍\\🌳👭\n           🌳/  🚘 l  🏃 \\🌴 👬                       👬  🌴/            l  🚔    \\🌲\n      🌲/   🚖     l                  🌳 🚶           |   🚍            🚴🚴\n🌴/                    |                     \\🌲',
    '☁☁  🌞    ☁           ☁\n       ☁   ✈        ☁   🚁     ☁    ☁          ☁          ☁     ☁   ☁\n\n🏬🏨🏫🏢🏤🏥🏦🏪🏫\n              🌲/     l🚍\\🌳👭\n           🌳/    l  🏃 \\🌴 👬                       👬  🌴/            l  🚔    \\🌲\n      🌲/   🚖  🚘l                    🌳 🚶          |    🚍          🚴🚴\n🌴/                    |                     \\🌲',
    '☁☁   🌞   ☁           ☁\n       ☁    ✈       ☁  🚁      ☁    ☁           ☁          ☁     ☁   ☁\n\n🏬🏨🏫🏢🏤🏥🏦🏪🏫\n              🌲/     l🚍\\🌳👭\n           🌳/    l  🏃 \\🌴 👬                       👬  🌴/            l  🚔    \\🌲\n      🌲/   🚖    l                   🌳 🚶        🚘|     🚍         🚴🚴\n🌴/                    |                     \\🌲',
    '☁☁    🌞  ☁           ☁\n       ☁     ✈      ☁ 🚁       ☁    ☁            ☁          ☁     ☁   ☁\n\n🏬🏨🏫🏢🏤🏥🏦🏪🏫\n              🌲/     l🚍\\🌳👭\n           🌳/   l  🏃 \\🌴 👬                       👬  🌴/            l  🚔    \\🌲\n      🌲/   🚖   l                    🌳 🚶        🚘|      🚍        🚴🚴\n🌴/                    |                     \\🌲',
    '☁☁     🌞 ☁           ☁\n       ☁      ✈     ☁🚁        ☁    ☁        ☁          ☁     ☁   ☁\n\n🏬🏨🏫🏢🏤🏥🏦🏪🏫\n              ??/     l🚍\\🌳👭\n           🌳/    l   🏃 \\🌴 👬                       👬  🌴/            l  🚔    \\🌲\n      🌲/         l                  🌳 🚶    🚖    |     🚍       🚴🚴\n🌴/             🚘     |                     \\🌲',
    '☁☁      🌞☁           ☁\n       ☁       ✈   ☁🚁         ☁    ☁        ☁          ☁     ☁   ☁\n\n🏬🏨🏫🏢🏤🏥🏦🏪🏫\n              🌲/     l🚍\\🌳👭\n           🌳/    l  🏃 \\🌴 👬                       👬  🌴/            l  🚔    \\🌲\n      🌲/         l                  🌳 🚶          |    🚍      🚴🚴\n🌴/         🚖  🚘     |                     \\🌲',
]
PLANE = [
    '✈-------------',
    '-✈------------',
    '--✈-----------',
    '---✈----------',
    '----✈---------',
    '-----✈--------',
    '------✈-------',
    '-------✈------',
    '--------✈-----',
    '---------✈----',
    '----------✈---',
    '-----------✈--',
    '------------✈-',
    '-------------✈',
]
LALOL = '😂\n😂\n😂\n😂\n😂😂😂😂\n\n   😂😂😂\n 😂         😂\n😂           😂\n 😂         😂\n   😂😂😂\n\n😂\n😂\n😂\n😂\n😂😂😂😂'
LMOON = '🌕🌕🌕🌕🌕🌕🌕🌕\n🌕🌕🌖🌔🌖🌔🌕🌕\n🌕🌕🌗🌔🌖🌓🌕🌕\n🌕🌕🌗🌔🌖🌓🌕🌕\n🌕🌕🌖🌓🌗🌔🌕🌕\n🌕🌕🌗🌑🌑🌓🌕🌕\n🌕🌕🌗👀🌑🌓🌕🌕\n🌕🌕🌘👄🌑🌓🌕🌕\n🌕🌕🌗🌑🌑🌒🌕🌕\n🌕🌖🌑🌑🌑🌑🌔🌕\n🌕🌘🌑🌑🌑🌑🌒🌕\n🌖🌑🌑🌑🌑🌑🌑🌔\n🌕🤜🏻🌑🌑🌑🌑🤛🏻🌕\n🌕🌖🌑🌑🌑🌑🌔🌕\n🌘🌑🌑🌑🌑🌑🌑🌒\n🌕🌕🌕🌕🌕🌕🌕🌕'
LIT = [
    '🟥🟥🟥🟥🟥🟥🟥🟥\n🟥🟧🟧🟧🟧🟧🟧🟥\n🟥🟧🟨🟨🟨🟨🟧🟥\n🟥🟧🟨🟩🟩🟨🟧🟥\n🟥🟧🟨🟩🟩🟨🟧🟥\n🟥🟧🟨🟨🟨🟨🟧🟥\n🟥🟧🟧🟧🟧🟧🟧🟥\n🟥🟥🟥🟥🟥🟥🟥🟥',
    '🟧🟧🟧🟧🟧🟧🟧🟧\n🟧🟨🟨🟨🟨🟨🟨🟧\n🟧🟨🟩🟩🟩🟩🟨🟧\n🟧🟨🟩🟥🟥🟩🟨🟧\n🟧🟨🟩🟥🟥🟩🟨🟧\n🟧🟨🟩🟩🟩🟩🟨🟧\n🟧🟨🟨🟨🟨🟨🟨🟧\n🟧🟧🟧🟧🟧🟧🟧🟧',
    '🟨🟨🟨🟨🟨🟨🟨🟨\n🟨🟩🟩🟩🟩🟩🟩🟨\n🟨🟩🟥🟥🟥🟥🟩🟨\n🟨🟩🟥🟧🟧🟥🟩🟨\n🟨🟩🟥🟥🟥🟥🟩🟨\n🟨🟩🟥🟥🟥🟥🟩🟨\n🟨🟩🟩🟩🟩🟩🟩🟨\n🟨🟨🟨🟨🟨🟨🟨🟨',
    '🟩🟩🟩🟩🟩🟩🟩🟩\n🟩🟥🟥🟥🟥🟥🟥🟩\n🟩🟥🟧🟧🟧🟧🟥🟩\n🟩🟥🟧🟨🟨🟧🟥🟩\n🟩🟥🟧🟨🟨🟧🟥🟩\n🟩🟥🟧🟧🟧🟧🟥🟩\n🟩🟥🟥🟥🟥🟥🟥🟩\n🟩🟩🟩🟩🟩🟩🟩🟩',
    '🟧🟧🟧🟧🟧🟧🟧??\n🟧🟨🟨🟨🟨🟨🟨🟧\n🟧🟨🟩🟩🟩🟩🟨🟧\n🟧🟨🟩🟥🟥🟩🟨🟧\n🟧🟨🟩🟥🟥🟩🟨🟧\n🟧🟨🟩🟩🟩🟩🟨🟧\n🟧🟨🟨🟨🟨🟨🟨🟧\n🟧🟧🟧🟧🟧🟧🟧🟧',
    '🟩🟩🟩🟩🟩🟩🟩🟩\n🟩🟥🟥🟥🟥🟥🟥🟩\n🟩🟥🟧🟧🟧🟧🟥🟩\n🟩🟥🟧🟨🟨🟧🟥🟩\n🟩🟥🟧🟨🟨🟧🟥🟩\n🟩🟥🟧🟧🟧🟧??🟩\n🟩🟥🟥🟥🟥🟥🟥🟩\n🟩🟩🟩🟩🟩🟩🟩🟩',
]
BOMBS = [
    ('▪️▪️▪️▪️ \n▪️▪️▪️▪️ \n▪️▪️▪️▪️ \n▪️▪️▪️▪️ \n▪️▪️▪️▪️ \n', 0.5),
    ('💣💣💣💣 \n▪️▪️▪️▪️ \n▪️▪️▪️▪️ \n▪️▪️▪️▪️ \n▪️▪️▪️▪️ \n', 0.5),
    ('▪️▪️▪️▪️ \n💣💣💣💣 \n▪️▪️▪️▪️ \n▪️▪️▪️▪️ \n▪️▪️▪️▪️ \n', 0.5),
    ('▪️▪️▪️▪️ \n▪️▪️▪️▪️ \n💣💣💣💣 \n▪️▪️▪️▪️ \n▪️▪️▪️▪️ \n', 0.5),
    ('▪️▪️▪️▪️ \n▪️▪️▪️▪️ \n▪️▪️▪️▪️ \n💣💣💣💣 \n▪️▪️▪️▪️ \n', 0.5),
    ('▪️▪️▪️▪️ \n▪️▪️▪️▪️ \n▪️▪️▪️▪️ \n▪️▪️▪️▪️ \n💣💣💣💣 \n', 1),
    ('▪️▪️▪️▪️ \n▪️▪️▪️▪️ \n▪️▪️▪️▪️ \n▪️▪️▪️▪️ \n💥💥💥💥 \n', 0.5),
    ('▪️▪️▪️▪️ \n▪️▪️▪️▪️ \n▪️▪️▪️▪️ \n💥💥💥💥 \n💥💥💥💥 \n', 0.5),
    ('▪️▪️▪️▪️ \n▪️▪️▪️▪️ \n▪️▪️▪️▪️ \n▪️▪️▪️▪️ \n😵😵😵😵 \n', 0.5),
    ('RIP...', 0.3),
]
GANGESTAR = [
    ('Everybody', 0.3),
    ('was', 0.2),
    ('Gangestar', 0.5),
    ('Until ', 0.2),
    ('I', 0.3),
    ('Arrived', 0.3),
    ('🔥', 0.3),
    ('Everybody was Gangestar Until I Arrived 🔥', 0.3),
]
MAIN = [
    '\u206d\n                    💖\n                  💖💖\n               💖💖💖\n            💖💖 💖💖\n          💖💖    💖💖\n        💖💖       💖💖\n      💖💖💖💖💖💖\n     💖💖💖💖💖💖💖\n   💖💖                 💖💖\n  💖💖                    💖💖\n💖💖                       💖💖\n',
    '\u206d\n💗💗💗💗💗💗💗\n💗💗💗💗💗💗💗💗\n💗💗                     💗💗\n💗💗                     💗💗\n💗💗💗💗💗💗💗💗\n💗💗💗💗💗💗💗💗\n💗💗                     💗💗\n💗💗                     💗💗\n💗💗💗💗💗💗💗💗\n💗💗💗💗💗💗💗\n',
    '\u206d\n          💛💛💛💛💛💛\n     💛💛💛💛💛💛💛💛\n   💛💛                      💛💛\n 💛💛\n💛💛\n💛💛\n 💛💛\n   💛💛                      💛💛\n     💛💛💛💛💛💛💛💛\n         💛💛💛💛💛💛\n',
    '\u206d\n💙💙💙💙💙💙💙\n💙💙💙💙💙💙💙💙\n💙💙                      💙💙\n💙💙                         💙💙\n💙💙                         💙💙\n💙💙                         💙💙\n💙💙                         💙💙\n💙💙                      💙💙\n💙💙💙💙💙💙💙💙\n💙💙💙💙💙💙💙\n',
    '\u206d\n💟💟💟💟💟💟💟💟\n💟💟💟💟💟💟💟💟\n💟💟\n💟💟\n💟💟💟💟💟💟\n💟💟💟💟💟💟\n💟💟\n💟💟\n💟💟💟💟💟💟💟💟\n💟💟💟💟💟💟💟💟\n',
    '\u206d\n💚💚💚💚💚💚💚💚\n💚💚💚💚💚💚💚💚\n💚💚\n💚💚\n💚💚💚💚💚💚\n💚💚💚💚💚💚\n💚💚\n💚💚\n💚💚\n💚💚\n',
    '\u206d\n          💜💜💜💜💜💜\n     💜💜💜💜💜💜💜💜\n   💜💜                     💜💜\n 💜💜\n💜💜                💜💜💜💜\n💜💜                💜💜💜💜\n 💜💜                        💜💜\n   💜💜                      💜💜\n     💜💜💜💜💜💜💜💜\n          💜💜💜💜💜💜\n',
    '\u206d\n💖💖                        💖💖\n💖💖                        💖💖\n💖💖                        💖💖\n💖💖                        💖💖\n💖💖💖💖💖💖💖💖💖\n💖💖💖💖💖💖💖💖💖\n💖💖                        💖💖\n💖💖                        💖💖\n💖💖                        💖💖\n💖💖                        💖💖\n',
    '\u206d\n💗💗💗💗💗💗\n💗💗💗💗💗💗\n          💗💗\n          💗💗\n          💗💗\n          💗💗\n          💗💗\n          💗💗\n💗💗💗💗💗💗\n💗💗💗💗💗💗\n',
    '\u206d\n         💛💛💛💛💛💛\n         💛💛💛💛💛💛\n                  💛💛\n                  💛💛\n                  💛💛\n                  💛💛\n💛💛          💛💛\n  💛💛       💛💛\n   💛💛💛💛💛\n      💛💛💛💛\n',
    '\u206d\n💙💙                  💙💙\n💙💙             💙💙\n💙💙        💙💙\n💙💙   💙💙\n💙💙💙💙\n💙💙 💙💙\n💙💙     💙💙\n💙💙         💙💙\n💙💙              💙💙\n💙💙                   💙💙\n',
    '\u206d\n💟💟\n💟💟\n💟💟\n💟💟\n💟💟\n💟💟\n💟💟\n💟💟\n💟💟💟💟💟💟💟💟\n💟💟💟💟💟💟💟💟\n',
    '\u206d\n💚💚                              💚💚\n💚💚💚                      💚💚💚\n💚💚💚💚            💚💚💚💚\n💚💚    💚💚    💚💚    💚💚\n💚💚        💚💚💚        💚💚\n💚💚             💚             💚💚\n💚💚                              💚💚\n💚💚                              💚💚\n💚💚                              💚💚\n💚💚                              💚💚\n',
    '\u206d\n💜💜                           💜💜\n💜💜💜                       💜💜\n💜💜💜💜                 💜💜\n💜💜  💜💜               💜💜\n💜💜     💜💜            💜💜\n💜💜         💜💜        💜💜\n💜💜             💜💜    💜💜\n💜💜                 💜💜💜💜\n💜💜                     💜💜💜\n💜💜                          💜💜\n',
    '\u206d\n           💖💖💖💖💖\n     💖💖💖💖💖💖💖\n   💖💖                   💖💖\n 💖💖                       💖💖\n💖💖                         💖💖\n💖💖                         💖💖\n 💖💖                       💖💖\n   💖💖                   💖💖\n      💖💖💖💖💖💖💖\n            💖💖💖💖💖\n',
    '\u206d\n💗💗💗💗💗💗💗\n💗💗💗💗💗💗💗💗\n💗💗                     💗💗\n💗💗                     💗💗\n💗💗💗💗💗💗💗💗\n💗💗💗💗💗💗💗\n💗💗\n💗💗\n💗💗\n💗💗\n',
    '\u206d\n           💛💛💛💛💛\n      💛💛💛💛💛💛💛\n   💛💛                    💛💛\n 💛💛                        💛💛\n💛💛                           💛💛\n💛💛              💛💛     💛💛\n 💛💛               💛💛 💛💛\n   💛💛                   💛💛\n      💛💛💛💛💛💛💛💛\n           💛💛💛💛💛   💛💛\n',
    '\u206d\n💙💙💙💙💙💙💙\n💙💙💙💙💙💙💙💙\n💙💙                     💙💙\n💙💙                     💙💙\n💙💙💙💙💙💙💙💙\n💙💙💙💙💙💙💙\n💙💙    💙💙\n💙💙         💙💙\n💙💙              💙💙\n💙💙                  💙💙\n',
    '\u206d\n       💟💟💟💟💟\n  💟💟💟💟💟💟💟\n  💟💟                 💟💟\n💟💟\n  💟💟💟💟💟💟\n      💟💟💟💟💟💟\n                            💟💟\n💟💟                 💟💟\n  💟💟💟💟💟💟💟\n       💟💟💟💟💟\n',
    '\u206d\n💚💚💚💚💚💚💚💚\n💚💚💚💚💚💚💚💚\n               💚💚\n               💚💚\n               💚💚\n               💚💚\n               💚💚\n               💚💚\n               💚💚\n',
    '\u206d\n💜💜                      💜💜\n💜💜                      💜💜\n💜💜                      💜💜\n💜💜                      💜💜\n💜💜                      💜💜\n💜💜                      💜💜\n💜💜                      💜💜\n  💜💜                  💜💜\n      💜💜💜💜💜💜\n            💜💜💜💜\n',
    '\u206d\n💖💖                              💖💖\n  💖💖                          💖💖\n    💖💖                      💖💖\n      💖💖                  💖💖\n         💖💖              💖💖\n           💖💖         💖💖\n             💖💖     💖💖\n               💖💖 💖💖\n                  💖💖💖\n                       💖\n',
    '\u206d\n💗💗                               💗💗\n💗💗                               💗💗\n💗💗                               💗💗\n💗💗                               💗💗\n💗💗              💗            💗💗\n 💗💗           💗💗          💗💗\n 💗💗        💗💗💗       💗💗\n  💗💗   💗💗  💗💗   💗💗\n   💗💗💗💗      💗💗💗💗\n    💗💗💗             💗💗💗\n',
    '\u206d\n💛💛                    💛💛\n   💛💛              💛💛\n      💛💛        💛💛\n         💛💛  💛💛\n            💛💛💛\n            💛💛💛\n         💛💛 💛💛\n      💛💛       💛💛\n   💛💛             💛💛\n💛💛                   💛💛\n',
    '\u206d\n💙💙                    💙💙\n   💙💙              💙💙\n      💙💙        💙💙\n         💙💙  💙💙\n            💙💙💙\n              💙💙\n              💙💙\n              💙💙\n              💙💙\n              💙💙\n',
    '\u206d\n 💟💟💟💟💟💟💟\n 💟💟💟💟💟💟💟\n                       💟💟\n                   💟💟\n               💟💟\n           💟💟\n       💟💟\n   💟💟\n💟💟💟💟💟💟💟\n💟💟💟💟💟💟💟\n',
    '\u206d\n       💗💗💗💗\n   💗💗💗💗💗💗\n💗💗               💗💗\n💗💗               💗💗\n💗💗               💗💗\n💗💗               💗💗\n💗💗               💗💗\n💗💗               💗💗\n   💗💗💗💗💗💗\n        💗💗💗💗\n',
    '\u206d\n          💙💙\n     💙💙💙\n💙💙 💙💙\n          💙💙\n          💙💙\n          💙💙\n          💙💙\n          💙💙\n     💙💙💙💙\n     💙💙💙💙\n',
    '\u206d\n    💟💟💟💟💟\n  💟💟💟💟💟💟\n💟💟          💟💟\n                💟💟\n             💟💟\n          💟💟\n       💟💟\n    💟💟\n  💟💟💟💟💟💟\n  💟💟💟💟💟💟\n',
    '\u206d\n     💛💛💛💛\n  💛💛💛💛💛\n💛💛         💛💛\n                   💛💛\n            💛💛💛\n            💛💛💛\n                   💛💛\n💛💛         💛💛\n  💛💛💛💛💛\n     💛💛💛💛\n',
    '\u206d\n                         💖💖\n                    💖💖💖\n              💖💖 💖💖\n          💖💖     💖💖\n     💖💖          💖💖\n💖💖               💖💖\n💖💖💖💖💖💖💖💖💖\n💖💖💖💖💖💖💖💖💖\n                         💖💖\n                         💖💖\n',
    '\u206d\n💚💚💚💚💚💚\n💚💚💚💚💚💚\n💚💚\n 💚💚💚💚💚\n   💚💚💚💚💚\n                    💚💚\n                    💚💚\n💚💚          💚💚\n  💚💚💚💚💚\n     💚💚💚💚\n',
    '\u206d\n        💜💜💜💜\n    💜💜💜💜💜\n💜💜\n\n💜💜\n💜💜💜💜💜💜\n💜💜💜💜💜💜💜\n💜💜               💜💜\n💜💜               💜💜\n    💜💜💜💜💜💜\n        💜💜💜💜\n',
    '\u206d\n💗💗💗💗💗💗💗\n💗💗💗💗💗💗💗\n                      💗💗\n                     💗💗\n                   💗💗\n                 💗💗\n               💗💗\n             💗💗\n           💗💗\n         💗💗\n',
    '\u206d\n        💙💙💙💙\n   💙💙💙💙💙💙\n💙💙               💙💙\n💙💙               💙💙\n   💙💙💙💙💙💙\n   💙💙💙💙💙💙\n💙💙               💙💙\n💙💙               💙💙\n   💙💙💙💙💙💙\n        💙💙💙💙\n',
    '\u206d\n        💟💟💟💟\n   💟💟💟💟💟💟\n💟💟               💟💟\n💟💟               💟💟\n 💟💟💟💟💟💟💟\n      💟💟💟💟💟💟\n                         💟💟\n                        💟💟\n  💟💟💟💟💟💟\n       💟💟💟💟\n',
]
LETTER = [
    'a',
    'b',
    'c',
    'd',
    'e',
    'f',
    'g',
    'h',
    'i',
    'j',
    'k',
    'l',
    'm',
    'n',
    'o',
    'p',
    'q',
    'r',
    's',
    't',
    'u',
    'v',
    'w',
    'x',
    'y',
    'z',
    '0',
    '1',
    '2',
    '3',
    '4',
    '5',
    '6',
    '7',
    '8',
    '9',
]
GAMBAR_TITIT = '\n🍆🍆\n🍆🍆🍆\n  🍆🍆🍆\n    🍆🍆🍆\n     🍆🍆🍆\n       🍆🍆🍆\n        🍆🍆🍆\n         🍆🍆🍆\n          🍆🍆🍆\n          🍆🍆🍆\n      🍆🍆🍆🍆\n 🍆🍆🍆🍆🍆🍆\n 🍆🍆🍆  🍆🍆🍆\n    🍆🍆       🍆🍆\n'
FIGCAR = '┈╱▔▔▔▔▔▔▔▔╲┈┈┈┈\n ╱▔▔▔▔▔▔▔▔╲╱┈┈┈┈\n▏┳╱╭╮┓┏┏┓▕╱▔▔╲┈\n▏┃╱┃┃┃┃┣▏▕▔▔╲╱▏\n▏┻┛╰╯╰╯┗┛▕▕▉▕╱╲\n▇▇▇▇▇▇▇▇▇▇▔▔▔╲▕\n▇▇╱▔╲▇▇▇▇▇╱▔╲▕╱\n┈┈╲▂╱┈┈┈┈┈╲▂╱▔┈'
FIGKILLER = '_/﹋\\_\n(҂`_´)\n<,︻╦╤─ ҉ - -\n_/﹋\\_\n'
TGM = '♛┈⛧┈┈•༶🦋⋇⋆✦⋆⋇🦋༶•┈┈⛧┈♛\n╱╱✨╱╱✨╱╱✨╱╱✨╱╱✨╱╱✨╱╱✨\n╔══╗────╔╗──────────╔╗\n║╔═╬═╦═╦╝║╔══╦═╦╦╦═╦╬╬═╦╦═╗\n║╚╗║╬║╬║╬║║║║║╬║╔╣║║║║║║║╬║\n╚══╩═╩═╩═╝╚╩╩╩═╩╝╚╩═╩╩╩═╬╗║\n────────────────────────╚═╝\n╱╱✨╱╱✨╱╱✨╱╱✨╱╱✨╱╱✨╱╱✨\n♛┈⛧┈┈•༶🦋⋇⋆✦⋆⋇🦋༶•┈┈⛧┈♛･'
EMAM = '⣿⣿⣿⣿⣿⡿⠋⠁⠄⠄⠄⠈⠘⠩⢿⣿⣿⣿⣿⣿\n⣿⣿⣿⣿⠃⠄⠄⠄⠄⠄⠄⠄⠄⠄⠄⠻⣿⣿⣿⣿\n⣿⣿⣿⣿⠄⠄⣀⣤⣤⣤⣄⡀⠄⠄⠄⠄⠙⣿⣿⣿\n⣿⣿⣿⣿⡀⢰⣿⣿⣿⣿⣿⢿⠄⠄⠄⠄⠄⠹⢿⣿\n⣿⣿⣿⣿⣿⡞⠻⠿⠟⠋⠉⠁⣤⡀⠄⠄⠄⠄⠄⠄\n⣿⣿⣿⣿⣿⣿⣶⢼⣷⡤⣦⣿⠛⡰⢃⠄⠐⠄⠄⢸\n⣿⣿⣿⣿⣿⣿⣿⡯⢍⠿⢾⡿⣸⣿⠰⠄⢀⠄⠄⡬\n⣿⣿⣿⣿⣿⣿⣿⣴⣴⣅⣾⣿⣿⡧⠦⡶⠃⠄⠠⢴\n⣿⣿⣿⣿⠿⠍⣿⣿⣿⣿⣿⣿⣿⢇⠟⠁⠄⠄⠄⠄\n⠟⠛⠉⠄⠄⠄⡽⣿⣿⣿⣿⣿⣯⠏⠄⠄⠄⠄⠄⠄\n⠄⠄⠄⢀⣾⣾⣿⣤⣯⣿⣿⡿⠃⠄⠄⠄⠄⠄⠄⠄\n'
TGN = '♛┈⛧┈┈•༶🦋⋇⋆✦⋆⋇🦋༶•┈┈⛧┈♛\n╱╱✨╱╱✨╱╱✨╱╱✨╱╱✨╱╱✨\n╔══╗────╔╗╔═╦╦╗─╔╗╔╗\n║╔═╬═╦═╦╝║║║║╠╬═╣╚╣╚╗\n║╚╗║╬║╬║╬║║║║║║╬║║║╔╣\n╚══╩═╩═╩═╝╚╩═╩╬╗╠╩╩═╝\n──────────────╚═╝\n╱╱✨╱╱✨╱╱✨╱╱✨╱╱✨╱╱✨╱╱✨\n♛┈⛧┈┈•༶🦋⋇⋆✦⋆⋇🦋༶•┈┈⛧┈♛･'
TNX = '.......🦋🦋........🦋🦋\n...🦋.........🦋🦋.......🦋\n...🦋............💙..........🦋\n.....🦋🅣🅗🅐🅝🅚🅢 🦋\n....... 🦋.................🦋\n..............🦋......🦋\n...................💙\n'
FIGGM = '｡♥｡･ﾟ♡ﾟ･｡♥｡･｡･｡･｡♥｡･｡♥｡･ﾟ♡ﾟ･\n╱╱╱╱╱╱╱╭╮╱╱╱╱╱╱╱╱╱╱╭╮\n╭━┳━┳━┳╯┃╭━━┳━┳┳┳━┳╋╋━┳┳━╮\n┃╋┃╋┃╋┃╋┃┃┃┃┃╋┃╭┫┃┃┃┃┃┃┃╋┃\n┣╮┣━┻━┻━╯╰┻┻┻━┻╯╰┻━┻┻┻━╋╮┃\n╰━╯╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╰━╯\n｡♥｡･ﾟ♡ﾟ･｡♥｡･｡･｡･｡♥｡･｡♥｡･ﾟ♡ﾟ･'
FIGHI = '██╗░░██╗██╗\n██║░░██║██║\n███████║██║\n██╔══██║██║\n██║░░██║██║\n╚═╝░░╚═╝╚═╝\n'
FIGGN = '｡♥｡･ﾟ♡ﾟ･｡♥｡･｡･｡･｡♥\n╱╱╱╱╱╱╱╭╮╱╱╱╭╮╱╭╮╭╮\n╭━┳━┳━┳╯┃╭━┳╋╋━┫╰┫╰╮\n┃╋┃╋┃╋┃╋┃┃┃┃┃┃╋┃┃┃╭┫\n┣╮┣━┻━┻━╯╰┻━┻╋╮┣┻┻━╯\n╰━╯╱╱╱╱╱╱╱╱╱╱╰━╯\n｡♥｡･ﾟ♡ﾟ･｡♥° ♥｡･ﾟ♡ﾟ･\n'
SPONGE = '┈┈╱▔▔▔▔▔▔▔▔▔▔▔▏\n┈╱╭▏╮╭┻┻╮╭┻┻╮╭▏ \n▕╮╰▏╯┃╭╮┃┃╭╮┃╰▏ \n▕╯┈▏┈┗┻┻┛┗┻┻┻╮▏ \n▕╭╮▏╮┈┈┈┈┏━━━╯▏\n▕╰╯▏╯╰┳┳┳┳┳┳╯╭▏ \n▕┈╭▏╭╮┃┗┛┗┛┃┈╰▏ \n▕┈╰▏╰╯╰━━━━╯┈┈▏\n'
FIGLOL = '`\n╱┏┓╱╱╱╭━━━╮┏┓╱╱╱╱ ``\n╱┃┃╱╱╱┃╭━╮┃┃┃╱╱╱╱ ``\n╱┃┗━━┓┃╰━╯┃┃┗━━┓╱ ``\n╱┗━━━┛╰━━━╯┗━━━┛╱ `'
FIGLMAO = '`\n┏┓┈╭━━╮╭━━╮╭━━╮``\n┃┃┈┃┃┃┃┃╭╮┃┃╭╮┃``\n┃┗┓┃┃┃┃┃┏┓┃┃╰╯┃``\n┗━┛┗┻┻┛┗┛┗┛╰━━╯`'
FIGHELLO = '\n╔┓┏╦━╦┓╔┓╔━━╗\n║┗┛║┗╣┃║┃║X X║\n║┏┓║┏╣┗╣┗╣╰╯║\n╚┛┗╩━╩━╩━╩━━╝'
FIGNO = '\n███╗░░██╗░█████╗░\n████╗░██║██╔══██╗\n██╔██╗██║██║░░██║\n██║╚████║██║░░██║\n██║░╚███║╚█████╔╝\n╚═╝░░╚══╝░╚════╝░'
FIGTRUMP = '\n⣿⣿⣿⣿⣿⣿⡿⠿⠛⠋⠉⡉⣉⡛⣛⠿⣿⣿⣿⣿⣿⣿⣿⣿\n⣿⣿⣿⡿⠋⠁⠄⠄⠄⠄⠄⢀⣸⣿⣿⡿⠿⡯⢙⠿⣿⣿⣿⣿\n⣿⣿⡿⠄⠄⠄⠄⠄⡀⡀⠄⢀⣀⣉⣉⣉⠁⠐⣶⣶⣿⣿⣿⣿\n⣿⣿⡇⠄⠄⠄⠄⠁⣿⣿⣀⠈⠿⢟⡛⠛⣿⠛⠛⣿⣿⣿⣿⣿\n⣿⣿⡆⠄⠄⠄⠄⠄⠈⠁⠰⣄⣴⡬⢵⣴⣿⣤⣽⣿⣿⣿⣿⣿\n⣿⣿⡇⠄⢀⢄⡀⠄⠄⠄⠄⡉⠻⣿⡿⠁⠘⠛⡿⣿⣿⣿⣿⣿\n⣿⡿⠃⠄⠄⠈⠻⠄⠄⠄⠄⢘⣧⣀⠾⠿⠶⠦⢳⣿⣿⣿⣿⣿\n⣿⣶⣤⡀⢀⡀⠄⠄⠄⠄⠄⠄⠻⢣⣶⡒⠶⢤⢾⣿⣿⣿⣿⣿\n⣿⡿⠋⠄⢘⣿⣦⡀⠄⠄⠄⠄⠄⠉⠛⠻⠻⠺⣼⣿⠟⠛⠿⣿\n⠋⠁⠄⠄⠄⢻⣿⣿⣶⣄⡀⠄⠄⠄⠄⢀⣤⣾⣿⡀⠄⠄⠄⢹\n⠄⠄⠄⠄⠄⠄⢻⣿⣿⣿⣷⡤⠄⠰⡆⠄⠄⠈⠛⢦⣀⡀⡀⠄\n⠄⠄⠄⠄⠄⠄⠈⢿⣿⠟⡋⠄⠄⠄⢣⠄⠄⠄⠄⠄⠈⠹⣿⣀\n⠄⠄⠄⠄⠄⠄⠄⠘⣷⣿⣿⣷⠄⠄⢺⣇⠄⠄⠄⠄⠄⠄⠸⣿\n⠄⠄⠄⠄⠄⠄⠄⠄⠹⣿⣿⡇⠄⠄⠸⣿⡄⠄⠈⠁⠄⠄⠄⣿\n⠄⠄⠄⠄⠄⠄⠄⠄⠄⢻⣿⡇⠄⠄⠄⢹⣧⠄⠄⠄⠄⠄⠄⠘'
FIGPUTIN = '⣿⣿⣿⣿⣻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿\n⣿⣿⣿⣵⣿⣿⣿⠿⡟⣛⣧⣿⣯⣿⣝⡻⢿⣿⣿⣿⣿⣿⣿⣿\n⣿⣿⣿⣿⣿⠋⠁⣴⣶⣿⣿⣿⣿⣿⣿⣿⣦⣍⢿⣿⣿⣿⣿⣿\n⣿⣿⣿⣿⢷⠄⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣏⢼⣿⣿⣿⣿\n⢹⣿⣿⢻⠎⠔⣛⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡏⣿⣿⣿⣿\n⢸⣿⣿⠇⡶⠄⣿⣿⠿⠟⡛⠛⠻⣿⡿⠿⠿⣿⣗⢣⣿⣿⣿⣿\n⠐⣿⣿⡿⣷⣾⣿⣿⣿⣾⣶⣶⣶⣿⣁⣔⣤⣀⣼⢲⣿⣿⣿⣿\n⠄⣿⣿⣿⣿⣾⣟⣿⣿⣿⣿⣿⣿⣿⡿⣿⣿⣿⢟⣾⣿⣿⣿⣿\n⠄⣟⣿⣿⣿⡷⣿⣿⣿⣿⣿⣮⣽⠛⢻⣽⣿⡇⣾⣿⣿⣿⣿⣿\n⠄⢻⣿⣿⣿⡷⠻⢻⡻⣯⣝⢿⣟⣛⣛⣛⠝⢻⣿⣿⣿⣿⣿⣿\n⠄⠸⣿⣿⡟⣹⣦⠄⠋⠻⢿⣶⣶⣶⡾⠃⡂⢾⣿⣿⣿⣿⣿⣿\n⠄⠄⠟⠋⠄⢻⣿⣧⣲⡀⡀⠄⠉⠱⣠⣾⡇⠄⠉⠛⢿⣿⣿⣿\n⠄⠄⠄⠄⠄⠈⣿⣿⣿⣷⣿⣿⢾⣾⣿⣿⣇⠄⠄⠄⠄⠄⠉⠉\n⠄⠄⠄⠄⠄⠄⠸⣿⣿⠟⠃⠄⠄⢈⣻⣿⣿⠄⠄⠄⠄⠄⠄⠄\n⠄⠄⠄⠄⠄⠄⠄⢿⣿⣾⣷⡄⠄⢾⣿⣿⣿⡄⠄⠄⠄⠄⠄⠄\n⠄⠄⠄⠄⠄⠄⠄⠸⣿⣿⣿⠃⠄⠈⢿⣿⣿⠄⠄⠄⠄⠄⠄⠄\n'
FIGCHINA = '⣿⣿⣿⣿⠟⠋⢁⢁⢁⢁⢁⢁⢁⢁⠈⢻⢿⣿⣿⣿⣿⣿⣿⣿\n⣿⣿⣿⣿⠃⠄⠄⠄⠄⠄⠄⠄⠄⠄⠄⠄⠈⡀⠭⢿⣿⣿⣿⣿\n⣿⣿⣿⡟⠄⢀⣾⣿⣿⣿⣷⣶⣿⣷⣶⣶⡆⠄⠄⠄⣿⣿⣿⣿\n⣿⣿⣿⡇⢀⣼⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣧⠄⠄⢸⣿⣿⣿⣿\n⣿⣿⣿⣇⣼⣿⣿⠿⠶⠙⣿⡟⠡⣴⣿⣽⣿⣧⠄⢸⣿⣿⣿⣿\n⣿⣿⣿⣿⣾⣿⣿⣟⣭⣾⣿⣷⣶⣶⣴⣶⣿⣿⢄⣿⣿⣿⣿⣿\n⣿⣿⣿⣿⣿⣿⣿⡟⣩⣿⣿⣿⡏⢻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿\n⣿⣿⣿⣿⣿⣹⡋⠘⠷⣦⣀⣠⡶⠁⠈⠁⠄⣿⣿⣿⣿⣿⣿⣿\n⣿⣿⣿⣿⣿⣍⠃⣴⣶⡔⠒⠄⣠⢀⠄⠄⠄⡨⣿⣿⣿⣿⣿⣿\n⣿⣿⣿⣿⣿⣿⣦⡘⠿⣷⣿⠿⠟⠃⠄⠄⣠⡇⠈⠻⣿⣿⣿⣿\n⣿⣿⣿⡿⠟⠋⢁⣷⣠⠄⠄⠄⠄⣀⣠⣾⡟⠄⠄⠄⠄⠉⠙⠻\n⡿⠟⠁⠄⠄⠄⢸⣿⣿⡯⢓⣴⣾⣿⣿⡟⠄⠄⠄⠄⠄⠄⠄⠄\n⠄⠄⠄⠄⠄⠄⣿⡟⣷⠄⠹⣿⣿⣿⡿⠁⠄⠄⠄⠄⠄⠄⠄⠄\n⠄⠄⠄⠄⠄⣸⣿⡷⡇⠄⣴⣾⣿⣿⠃⠄⠄⠄⠄⠄⠄⠄⠄⠄\n⠄⠄⠄⠄⠄⣿⣿⠃⣦⣄⣿⣿⣿⠇⠄⠄⠄⠄⠄⠄⠄⠄⠄⠄\n⠄⠄⠄⠄⢸⣿⠗⢈⡶⣷⣿⣿⡏⠄⠄⠄⠄⠄⠄⠄⠄⠄⠄⠄\n'
FIGTHINK = '⠀⠀⠀⠀⢀⣀⣀⣀\n⠀⠀⠀⠰⡿⠿⠛⠛⠻⠿⣷\n⠀⠀⠀⠀⠀⠀⣀⣄⡀⠀⠀⠀⠀⢀⣀⣀⣤⣄⣀⡀\n⠀⠀⠀⠀⠀⢸⣿⣿⣷⠀⠀⠀⠀⠛⠛⣿⣿⣿⡛⠿⠷\n⠀⠀⠀⠀⠀⠘⠿⠿⠋⠀⠀⠀⠀⠀⠀⣿⣿⣿⠇\n⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠉⠁\n⠀\n⠀⠀⠀⠀⣿⣷⣄⠀⢶⣶⣷⣶⣶⣤⣀\n⠀⠀⠀⠀⣿⣿⣿⠀⠀⠀⠀⠀⠈⠙⠻⠗\n⠀⠀⠀⣰⣿⣿⣿⠀⠀⠀⠀⢀⣀⣠⣤⣴⣶⡄\n⠀⣠⣾⣿⣿⣿⣥⣶⣶⣿⣿⣿⣿⣿⠿⠿⠛⠃\n⢰⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡄\n⢸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡁\n⠈⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠁\n⠀⠀⠛⢿⣿⣿⣿⣿⣿⣿⡿⠟\n'
FIGDICK = '⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\n⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⡤⠖⠲⢄\n⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡠⠞⠁⠀⠀⠀⠀⢱\n⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢠⠎⠀⠀⠀⠀⠀⠀⠀⣸\n⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⣄⠀⠀⠀⠀⢀⡠⠖⠁\n⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢠⣿⣿⣿⣿⣿⣿⠁⠀⠀\n⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣠⣯⣿⣿⣿⣿⣿⠇⠀⠀⠀\n⠀⠀⠀⠀⠀⠀⠀⠀⠀⡴⣻⣿⣿⣿⣿⣯⠏⠀⠀⠀⠀\n⠀⠀⠀⠀⠀⠀⠀⣠⠾⣽⣿⣿⣿⣿⣿⠏⠀⠀⠀⠀⠀\n⠀⠀⠀⠀⠀⢀⣴⣿⣿⣿⣿⣿⣿⣿⠋⠀⠀⠀⠀⠀⠀\n⠀⠀⠀⠀⣴⣻⣿⣿⣿⣿⣿⣿⡿⠁⠀⠀⠀⠀⠀⠀⠀\n⠀⠀⣠⢾⣿⣿⣿⣿⣿⣿⡿⠋⠀⠀⠀⠀⠀⠀⠀⠀⠀\n⠀⣼⣷⣿⣿⣿⣿⣿⣿⣟⣦⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀\n⢸⢿⣿⣿⣿⣿⣿⣿⣿⣯⣻⡟⡆⠀⠀⠀⠀⠀⠀⠀⠀\n⠸⣿⣿⣿⣿⣿⣿⣿⣿⣹⣿⡿⡇⠀⠀⠀⠀⠀⠀⠀⠀\n⠀⠹⣟⣿⣿⣿⣿⡿⣷⡿⣿⡿⠁⠀⠀⠀⠀⠀⠀⠀⠀\n⠀⠀⠈⠛⠯⣿⡯⠟⠛⠛⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\n'
FIGHAPPYFROG = '⠄⠄⠄⠄⠄⣀⣀⣤⣶⣿⣿⣶⣶⣶⣤⣄⣠⣴⣶⣿⣶⣦⣄⠄\n⠄⣠⣴⣾⣿⠿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣦\n⢠⠾⣋⣭⣄⡀⠄⠙⠻⣿⣿⡿⠛⠋⠉⠉⠉⠙⠛⠿⣿⣿⣿⣿\n⡎⡟⢻⣿⣷⠄⠄⠄⠄⡼⣡⣾⣿⣿⣦⠄⠄⠄⠄⠄⠈⠛⢿⣿\n⡇⣷⣾⣿⠟⠄⠄⠄⢰⠁⣿⣇⣸⣿⣿⠄⠄⠄⠄⠄⠄⠄⣠⣼\n⣦⣭⣭⣄⣤⣤⣴⣶⣿⣧⡘⠻⠛⠛⠁⠄⠄⠄⠄⣀⣴⣿⣿⣿\n⢉⣹⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣶⣦⣶⣶⣶⣶⣿⣿⣿⣿⣿⣿\n⡿⠛⠛⠛⠛⠻⠿⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿\n⡇⠄⠄⢀⣀⣀⠄⠄⠄⠄⠉⠉⠛⠛⠻⠿⣿⣿⣿⣿⣿⣿⣿⣿\n⠈⣆⠄⠄⢿⣿⣿⣷⣶⣶⣤⣤⣀⣀⡀⠄⠄⠉⢻⣿⣿⣿⣿⣿\n⠄⣿⡀⠄⠸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠂⠄⢠⣿⣿⣿⣿⣿\n⠄⣿⡇⠄⠄⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⠃⠄⢀⣼⣿⣿⣿⣿⣿\n⠄⣿⡇⠄⠠⣿⣿⣿⣿⣿⣿⣿⡿⠋⠄⠄⣠⣾⣿⣿⣿⣿⣿⣿\n⠄⣿⠁⠄⠐⠛⠛⠛⠉⠉⠉⠉⠄⠄⣠⣾⣿⣿⣿⣿⣿⣿⣿⣿\n⠄⠻⣦⣀⣀⣀⣀⣀⣤⣤⣤⣤⣶⣾⣿⣿⣿⣿⣿⣿⣿⣿⡿⠋\n'
FIGDEADFROG = '⣿⣿⣿⡇⠄⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿\n⣿⣿⣿⡇⠄⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿\n⣿⣿⣿⡇⠄⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿\n⣿⣿⣿⡇⠄⣿⣿⣿⡿⠋⣉⣉⣉⡙⠻⣿⣿⣿⣿⣿⣿⣿⣿⣿\n⣿⣿⣿⠃⠄⠹⠟⣡⣶⢟⣛⣛⡻⢿⣦⣩⣤⣬⡉⢻⣿⣿⣿⣿\n⣿⣿⣿⠄⢀⢤⣾⣿⣿⣿⡿⠿⠿⠿⢮⡃⣛⡻⢿⠈⣿⣿⣿⣿\n⣿⡟⢡⣴⣯⣿⣿⣿⠤⣤⣭⣶⣶⣶⣮⣔⡈⠛⢓⠦⠈⢻⣿⣿\n⠏⣠⣿⣿⣿⣿⣿⣿⣯⡪⢛⠿⢿⣿⣿⣿⡿⣼⣿⣿⣮⣄⠙⣿\n⣼⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣾⡭⠴⣶⣶⣽⣽⣛⡿⠿⠿⠇⣿\n⣿⣿⣿⣿⣿⣿⣿⠿⣿⣿⣿⣿⣿⣿⣿⣷⣝⣛⢛⢋⣥⣴⣿⣿\n⣿⣿⣿⣿⣿⢿⠱⣿⣛⠾⣭⣛⡿⢿⣿⣿⣿⣿⣿⡀⣿⣿⣿⣿\n⠑⠽⡻⢿⣮⣽⣷⣶⣯⣽⣳⠮⣽⣟⣲⠯⢭⣿⣛⡇⣿⣿⣿⣿\n⠄⠄⠈⠑⠊⠉⠟⣻⠿⣿⣿⣿⣷⣾⣭⣿⠷⠶⠂⣴⣿⣿⣿⣿\n⠄⠄⠄⠄⠄⠄⠄⠁⠙⠒⠙⠯⠍⠙⢉⣡⣶⣿⣿⣿⣿⣿⣿⣿\n⠄⠄⠄⠄⠄⠄⠄⠄⠄⠄⠄⠄⠄⠄⠙⣿⣿⣿⣿⣿⣿⣿⣿⣿\n'
FUCK = "\n...................................../´¯/) \n...................................,/¯../ \n.................................../.../ \n................................../´.¯/\n................................./´¯./\n...............................,/¯../ \n.............................../.../ \n............................../´¯./\n............................./´¯./\n...........................,/¯../ \n.........................../.../ \n........................../´¯./\n........................./´¯./\n.......................,/¯../ \n......................./.../ \n....................../´¯./\n....................,/¯../ \n.................../..../ \n............./´¯/'...'/´¯¯`·¸ \n........../'/.../..../......./¨¯\\ \n........('(...´...´.... ¯~/'...') \n.........\\.................'...../ \n..........''...\\.......... _.·´ \n............\\..............( \n..............\\.............\\..."


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

@heartless_cmd(pattern="hyper ?(.*)")
async def Hyperlink(event):
    text = event.pattern_match.group(1) or ""
    if "t.me" not in text:
        await eod(event, "Lol, Send me a telegram link 🔗", timeout=5)
        return
    url = text.split(" ", 1)[0]
    mid = text.rsplit("/", 1)[-1]
    await eor(event, f"<a href=\"{url}\">›› {mid}</a>", parse_mode="HTML", link_preview=False)

@heartless_cmd(pattern="uglitch")
async def glitch(event):
    if ImageGlitcher is None:
        await eod(event, "`glitch_this` is not installed.", timeout=5)
        return
    reply = await event.get_reply_message()
    if not reply or not reply.media:
        await eod(event, "Reply to an image to glitch.", timeout=5)
        return
    media = reply.media
    if isinstance(media, MessageMediaPhoto) or (
        getattr(media, "document", None) and "image" in media.document.mime_type.split("/")
    ):
        photo = await event.client.download_media(media, sedpath)
    else:
        await eor(event, "Reply to an image.`")
        return
    out = "./heartless/heartless.gif"
    glitcher = ImageGlitcher()
    frames = glitcher.glitch_image(photo, 2, gif=True, color_offset=True)
    frames[0].save(
        out, format="GIF", append_images=frames[1:], save_all=True,
        duration=DURATION, loop=LOOP,
    )
    await event.client.send_file(event.chat_id, out)
    await event.delete()
    for path in (out, photo):
        if path and os.path.exists(path):
            os.remove(path)

@heartless_cmd(pattern="slash")
async def _(event):
    await _frames(event, [":/", ":\\"], interval=0.3, count=14)

@heartless_cmd(pattern="para")
async def _(event):
    await _frames(event, [":)", ":("], interval=0.3, count=14)

@heartless_cmd(pattern="fl")
async def typewriter(event):
    await _loadbar(event)

@heartless_cmd(pattern="oof")
async def _(e):
    t = "Oof"
    for _ in range(15):
        t = t[:-1] + "of"
        await e.edit(t)

@heartless_cmd(pattern="motion")
async def _(event):
    await _frames(event, ["▮", "▯", "▬", "▭"], interval=0.3, count=20)

@heartless_cmd(pattern="square")
async def _(event):
    await _frames(event, ["◧", "◨"], interval=0.3, count=20)

@heartless_cmd(pattern="oop")
async def _(event):
    await _frames(event, ["╹", "╻"], interval=0.3, count=20)

@heartless_cmd(pattern="round")
async def _(event):
    await _frames(event, ["⚫", "⬤", "●", "∘"], interval=0.3, count=20)

@heartless_cmd(pattern="comp")
async def _(event):
    await _frames(event, COMP)

@heartless_cmd(pattern="joon")
async def _(event):
    await _frames(event, JOON, interval=0.2)

@heartless_cmd(pattern="bigoof")
async def _(event):
    await _frames(event, BIGOOF, interval=0.7, intro=BIGOOF_INTRO)

@heartless_cmd(pattern="ok")
async def _(event):
    await _frames(event, OK, interval=0.3)

@heartless_cmd(pattern="meme ?(.*)")
async def _(event):
    await _scroll(event, event.pattern_match.group(1) or "")

@heartless_cmd(pattern="rmeme ?(.*)")
async def _(event):
    await _rscroll(event, event.pattern_match.group(1) or "")

@heartless_cmd(pattern="think")
async def _(event):
    await _frames(event, THINK, interval=0.7, intro=THINK_INTRO)

@heartless_cmd(pattern="snake")
async def _(event):
    await _frames(event, SNAKE, interval=0.7)

@heartless_cmd(pattern="police")
async def _(event):
    await _frames(event, POLICE, interval=0.7, intro=POLICE_INTRO)

@heartless_cmd(pattern="gangestar ?(.*)")
async def _(event):
    await _seq(event, GANGESTAR)

@heartless_cmd(pattern="flower")
async def _(event):
    await _grow(event, " 🌹")

@heartless_cmd(pattern="question")
async def _(event):
    await _spin(event, '?¿?¿?¿')

@heartless_cmd(pattern="melow")
async def _(event):
    await _spin(event, '😀😃😄😀😃😄')

@heartless_cmd(pattern="cute")
async def _(event):
    await _spin(event, '🥺😢🥺😢🥺😢')

@heartless_cmd(pattern="tlol")
async def _(event):
    await _spin(event, '🤔🧐🤔🧐🤔🧐')

@heartless_cmd(pattern="teeth")
async def _(event):
    await _spin(event, '😐😬😐😬😐😬')

@heartless_cmd(pattern="gym")
async def _(event):
    await _spin(event, '🏃\u200d🏋\u200d🤸\u200d🏃\u200d🏋\u200d🤸\u200d🏃\u200d🏋\u200d🤸\u200d')

@heartless_cmd(pattern="run")
async def _(event):
    await _spin(event, '🚶🏃🚶🏃🚶🏃🚶🏃')

@heartless_cmd(pattern="candy")
async def _(event):
    await _spin(event, '🍦🍧🍩🍪🎂🍰🧁🍫🍬🍭')

@heartless_cmd(pattern="kiss")
async def _(event):
    await _spin(event, '😗😚😘😗😚😘😗😚😘')

@heartless_cmd(pattern="butterfly")
async def _(event):
    await _spin(event, '🦋✨🦋✨🦋✨🦋✨')

@heartless_cmd(pattern="box")
async def _(event):
    await _spin(event, '🟥🟧🟨🟩🟦🟪🟫⬛⬜')

@heartless_cmd(pattern="clock")
async def _(event):
    await _spin(event, '🕙🕘🕗🕖🕕🕔🕓🕒🕑🕐🕛')

@heartless_cmd(pattern="moon")
async def _(event):
    await _spin(event, '🌗🌘🌑🌒🌓🌔🌕🌖')

@heartless_cmd(pattern="earth")
async def _(event):
    await _spin(event, '🌏🌍🌎🌎🌍🌏🌍🌎')

@heartless_cmd(pattern="smile")
async def _(event):
    await _spin(event, '🙂🙃🙂🙃🙂🙃')

@heartless_cmd(pattern="laugh")
async def _(event):
    await _spin(event, '😄😁😄😁😄😁')

@heartless_cmd(pattern="cat")
async def _(event):
    await _spin(event, '😺😸😹😺😸😹😺😸😹')

@heartless_cmd(pattern="poker")
async def _(event):
    await _spin(event, '😐😑😐😑😐😑')

@heartless_cmd(pattern="wow")
async def _(event):
    await _spin(event, '😧😦😧😦😧😦')

@heartless_cmd(pattern="monkey")
async def _(event):
    await _spin(event, '🙉🙈🙉🙈🙉🙈')

@heartless_cmd(pattern="starheart")
async def _(event):
    await _spin(event, '😍🤩😍🤩😍🤩')

@heartless_cmd(pattern="wink")
async def _(event):
    await _spin(event, '😶😉😶😉😶😉')

@heartless_cmd(pattern="lip")
async def _(event):
    await _spin(event, '🙁☹️🙁☹️🙁☹️')

@heartless_cmd(pattern="angry")
async def _(event):
    await _spin(event, '😡🤬😡🤬😡🤬')

@heartless_cmd(pattern="sad")
async def _(event):
    await _spin(event, '😒😏😒😏😒😏')

@heartless_cmd(pattern="amaze")
async def _(event):
    await _spin(event, '😳😲😳😲😳😲')

@heartless_cmd(pattern="omg")
async def _(event):
    await _spin(event, '🙄😳🙄😳🙄😳')

@heartless_cmd(pattern="tongue")
async def _(event):
    await _spin(event, '😛😝😛😝😛😝')

@heartless_cmd(pattern="sun")
async def _(event):
    await _spin(event, '🔅🔆🔅🔆🔅🔆')

@heartless_cmd(pattern="speaker")
async def _(event):
    await _spin(event, '🔈🔊🔈🔊🔈🔊')

@heartless_cmd(pattern="heart")
async def _(event):
    await _spin(event, '💖💝💖💝💖💝💖💝')

@heartless_cmd(pattern="sand")
async def _(event):
    await _spin(event, '⏳⌛️⏳⌛️⏳⌛️')

@heartless_cmd(pattern="storm")
async def _(event):
    await _spin(event, '🌧⛈🌧⛈🌧⛈')

@heartless_cmd(pattern="floodwarn")
async def _(event):
    await _spin(event, '💙💛💓💘💕💜💚💝💞💟', count=64)

@heartless_cmd(pattern="rain")
async def _(event):
    await _spin(event, '☁️⛈Ř/~\\İŇ🌬⚡🌪', count=64)

@heartless_cmd(pattern="her ?(.*)")
async def _(event):
    await _frames(event, HER, interval=0.7, intro=HER_INTRO)

@heartless_cmd(pattern="donce")
async def _(event):
    await _frames(event, DONCE, interval=0.7, intro=DONCE_INTRO)

@heartless_cmd(pattern="cheart ?(.*)")
async def _(event):
    await _frames(event, CHEART, interval=0.3)

@heartless_cmd(pattern="finger ?(.*)")
async def _(event):
    await _frames(event, FINGER, interval=0.3)

@heartless_cmd(pattern="billy ?(.*)")
async def _(event):
    await _frames(event, BILLY, interval=0.6)

@heartless_cmd(pattern="agree ?(.*)")
async def _(event):
    await _frames(event, AGREE, interval=0.6)

@heartless_cmd(pattern="brain")
async def _(event):
    await _frames(event, BRAIN, interval=0.1)

@heartless_cmd(pattern="dump ?(.*)")
async def dump(message):
    obj = message.pattern_match.group(1) or ""
    inp = obj if len(obj) == 3 else "🥞🎂🍫"
    u = list(inp)
    t, g, o, s = "🗑", "<(^_^ <)", "(> ^_^)>", "⠀ "
    h = [(u[0], u[1], u[2]), (u[0], u[1], ""), (u[0], "", "")]
    frames = [
        y
        for y in (
            [
                "".join(x)
                for x in (
                    f + (s, g, s + s * f.count(""), t),
                    f + (g, s * 2 + s * f.count(""), t),
                    f[:i] + (o, f[i], s * 2 + s * f.count(""), t),
                    f[:i] + (s + s * f.count(""), o, f[i], s, t),
                    f[:i] + (s * 2 + s * f.count(""), o, f[i], t),
                    f[:i] + (s * 3 + s * f.count(""), o, t),
                    f[:i] + (s * 3 + s * f.count(""), g, t),
                )
            ]
            for i, f in enumerate(reversed(h))
        )
    ]
    for frame in reversed(frames):
        for part in frame:
            await asyncio.sleep(0.3)
            try:
                await message.edit(part)
            except MessageIdInvalidError:
                return

@heartless_cmd(pattern="good ?(.*)")
async def _(event):
    await _frames(event, GOOD, interval=0.5)

@heartless_cmd(pattern="human")
async def _(event):
    await _frames(event, HUMAN, interval=0.7)

@heartless_cmd(pattern="mc")
async def _(event):
    await _frames(event, MC, interval=0.7)

@heartless_cmd(pattern="solar")
async def _(event):
    await _frames(event, SOLAR, interval=0.7)

@heartless_cmd(pattern="lmoon")
async def _(event):
    await event.edit(LMOON)

@heartless_cmd(pattern="town")
async def _(event):
    await _frames(event, TOWN, interval=0.5)

@heartless_cmd(pattern="bombs")
async def _(event):
    await _seq(event, BOMBS)

@heartless_cmd(pattern="plane")
async def _(event):
    await _frames(event, PLANE, interval=0.3)

@heartless_cmd(pattern="lalol")
async def _(event):
    await event.edit(LALOL)

@heartless_cmd(pattern="lit")
async def _(event):
    await _frames(event, LIT, interval=0.3, count=len(LIT) * 4)

@heartless_cmd(pattern="my")
async def _(event):
    await _my(event)

@heartless_cmd(pattern="hi")
async def _(event):
    await _hi(event)

@heartless_cmd(pattern="figcar")
async def _(event):
    await event.edit(FIGCAR)

@heartless_cmd(pattern="figkiller")
async def _(event):
    await event.edit(FIGKILLER)

@heartless_cmd(pattern="tgm")
async def _(event):
    await event.edit(TGM)

@heartless_cmd(pattern="emam")
async def _(event):
    await event.edit(EMAM)

@heartless_cmd(pattern="tgn")
async def _(event):
    await event.edit(TGN)

@heartless_cmd(pattern="tnx")
async def _(event):
    await event.edit(TNX)

@heartless_cmd(pattern="figgm")
async def _(event):
    await event.edit(FIGGM)

@heartless_cmd(pattern="fighi")
async def _(event):
    await event.edit(FIGHI)

@heartless_cmd(pattern="figgn")
async def _(event):
    await event.edit(FIGGN)

@heartless_cmd(pattern="sponge")
async def _(event):
    await event.edit(SPONGE)

@heartless_cmd(pattern="figlol")
async def _(event):
    await event.edit(FIGLOL)

@heartless_cmd(pattern="figlmao")
async def _(event):
    await event.edit(FIGLMAO)

@heartless_cmd(pattern="fighello")
async def _(event):
    await event.edit(FIGHELLO)

@heartless_cmd(pattern="figno")
async def _(event):
    await event.edit(FIGNO)

@heartless_cmd(pattern="figtrump")
async def _(event):
    await event.edit(FIGTRUMP)

@heartless_cmd(pattern="figputin")
async def _(event):
    await event.edit(FIGPUTIN)

@heartless_cmd(pattern="figchina")
async def _(event):
    await event.edit(FIGCHINA)

@heartless_cmd(pattern="figthink")
async def _(event):
    await event.edit(FIGTHINK)

@heartless_cmd(pattern="figdick")
async def _(event):
    await event.edit(FIGDICK)

@heartless_cmd(pattern="fighappyfrog")
async def _(event):
    await event.edit(FIGHAPPYFROG)

@heartless_cmd(pattern="figdeadfrog")
async def _(event):
    await event.edit(FIGDEADFROG)

@heartless_cmd(pattern="fuck")
async def _(event):
    await event.edit(FUCK)

@heartless_cmd(pattern="dick ?(.*)")
async def _(e):
    emoji = e.pattern_match.group(1)
    art = GAMBAR_TITIT
    if emoji:
        art = art.replace("🍆", emoji)
    await e.edit(art)

@heartless_cmd(pattern="eem(?: |$)(.*)")
async def itachi(event):
    args = event.pattern_match.group(1)
    if not args:
        reply = await event.get_reply_message()
        args = reply.text if reply else None
    if not args:
        await eod(event, "`Give me some text...`", timeout=5)
        return
    result = "".join(
        MAIN[LETTER.index(c)] if c in LETTER else c for c in args.lower()
    )
    await event.edit(result)

@heartless_cmd(pattern="fhack")
async def _(event):
    await _frames(event, FHACK, interval=2)

@heartless_cmd(pattern="thack")
async def _(event):
    await _frames(event, THACK, interval=2, intro=THACK_INTRO)

@heartless_cmd(pattern="whack")
async def _(event):
    await _frames(event, WHACK, interval=2)

@heartless_cmd(pattern="xmas")
async def _(event):
    await _frames(event, XMAS, interval=1, intro=XMAS_INTRO)

__doc__ = get_help("exclusive") or __doc__
