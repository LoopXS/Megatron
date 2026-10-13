"""
✘ Commands Available -

• `{i}meaning <word>`
    Get the meaning of the word.

• `{i}synonym <word>`
    Get all synonyms.

• `{i}antonym <word>`
    Get all antonyms.

• `{i}ud <word>`
    Fetch word definition from urbandictionary.
"""

import io

import aiohttp

from CythonX import LOGS
from CythonX.fns.misc import get_synonyms_or_antonyms
from CythonX.fns.tools import async_searcher

from . import get_string, heartless_cmd

# Maximum synonyms/antonyms to render inline before the
# result is sent as a document instead of a message.
MAX_INLINE = 15

DICTIONARY_API = "https://api.dictionaryapi.dev/api/v2/entries/en/{}"
DATAMUSE_API = "https://api.datamuse.com/words"


def _csv(items, limit=MAX_INLINE):
    """Join up to ``limit`` items into a clean comma separated string."""
    return ", ".join(str(i) for i in items[:limit])


async def _as_file(text, name, caption, event):
    """Send ``text`` as a document (used when it exceeds 4096 chars)."""
    with io.BytesIO(str.encode(text)) as fle:
        fle.name = name
        return await event.client.send_file(
            event.chat_id,
            fle,
            force_document=True,
            caption=caption,
            reply_to=event.reply_to_msg_id or event.id,
        )


async def _fetch_meaning(word):
    """Return the formatted meaning of ``word``.

    Uses the rich dictionaryapi.dev payload when it is reachable and
    falls back to the more reliable Datamuse API otherwise.  Returns
    ``None`` when both sources error out and ``""`` when the word is
    simply unknown.
    """
    try:
        out = await async_searcher(
            DICTIONARY_API.format(word),
            re_json=True,
            retries=1,
            timeout=aiohttp.ClientTimeout(total=6),
        )
    except Exception as er:
        LOGS.info(f"dictionaryapi.dev unreachable for {word!r}: {er}")
        out = None

    if isinstance(out, list) and out:
        try:
            definition = out[0]["meanings"][0]["definitions"][0]
        except (KeyError, IndexError, TypeError):
            definition = None
        if definition:
            text = get_string("wrd_1").format(
                word,
                definition.get("definition") or "N/A",
                definition.get("example") or "None",
            )
            if definition.get("synonyms"):
                text += (
                    f"\n\n• **{get_string('wrd_5')} :** "
                    + _csv(definition["synonyms"])
                )
            if definition.get("antonyms"):
                text += (
                    f"\n\n• **{get_string('wrd_6')} :** "
                    + _csv(definition["antonyms"])
                )
            return text

    # Fallback: Datamuse (definitions + synonyms + antonyms).
    try:
        return await _datamuse_meaning(word)
    except Exception as er:
        LOGS.exception(er)
        return None


async def _datamuse_meaning(word):
    """Build a meaning from Datamuse: all definitions plus synonyms/antonyms."""
    data = await async_searcher(
        DATAMUSE_API,
        params={"sp": word, "md": "d", "max": 8},
        re_json=True,
        retries=2,
    )
    if not isinstance(data, list) or not data:
        return ""
    entry = next(
        (
            i
            for i in data
            if isinstance(i, dict) and i.get("word", "").lower() == word.lower()
        ),
        None,
    )
    if not entry:
        return ""
    raw = entry.get("defs") or []
    if not raw:
        return ""

    meanings = []
    for item in raw:
        pos, _, definition = item.partition("\t")
        meanings.append(f"{pos}: {definition}".strip() if pos else definition)
    text = get_string("wrd_11").format(word, "\n".join(f"{i}. {m}" for i, m in enumerate(meanings, 1)))

    try:
        synonyms = await get_synonyms_or_antonyms(word, "synonyms")
    except Exception:
        synonyms = []
    try:
        antonyms = await get_synonyms_or_antonyms(word, "antonyms")
    except Exception:
        antonyms = []
    if synonyms:
        text += f"\n\n• **{get_string('wrd_5')} :** {_csv(synonyms)}"
    if antonyms:
        text += f"\n\n• **{get_string('wrd_6')} :** {_csv(antonyms)}"
    return text


@heartless_cmd(pattern="meaning( (.*)|$)")
async def meaning(event):
    word = event.pattern_match.group(1).strip()
    if not word:
        return await event.eor(get_string("wrd_4"))
    text = await _fetch_meaning(word)
    if text is None:
        return await event.eor(get_string("com_7"))
    if not text:
        return await event.eor(get_string("wrd_9").format(word))
    if len(text) > 4096:
        await _as_file(text, f"{word}-meanings.txt", f"Meanings of {word}", event)
        return await event.try_delete()
    await event.eor(text)


@heartless_cmd(pattern="(syno|anto)nym( (.*)|$)")
async def syn_ant(event):
    task = event.pattern_match.group(1) + "nyms"
    word = (event.pattern_match.group(2) or "").strip()
    if not word:
        return await event.eor(get_string("wrd_10"))
    no_result = get_string("wrd_7" if task == "synonyms" else "wrd_8")
    try:
        results = await get_synonyms_or_antonyms(word, task)
    except Exception as er:
        LOGS.exception(er)
        return await event.eor(get_string("com_7"))
    if not results:
        return await event.eor(no_result.format(word))
    text = get_string("wrd_2" if task == "synonyms" else "wrd_3").format(word)
    text += "\n".join(f"**{i}.** `{w}`\n" for i, w in enumerate(results, 1))
    if len(text) > 4096:
        await _as_file(text, f"{word}-{task}.txt", f"{task} of {word}", event)
        return await event.try_delete()
    await event.eor(text)


@heartless_cmd(pattern="ud( (.*)|$)")
async def ud(event):
    word = event.pattern_match.group(1).strip()
    if not word:
        return await event.eor(get_string("wrd_10"))
    try:
        out = await async_searcher(
            "https://api.urbandictionary.com/v0/define",
            params={"term": word},
            re_json=True,
            retries=2,
        )
    except Exception as er:
        LOGS.exception(er)
        return await event.eor(get_string("com_7"))
    entries = (out or {}).get("list") or []
    if not entries:
        return await event.eor(get_string("wrd_9").format(word))
    first = entries[0]
    text = get_string("wrd_1").format(
        first.get("word") or word,
        first.get("definition") or "N/A",
        first.get("example") or "None",
    )
    if len(text) > 4096:
        await _as_file(text, f"{word}-ud.txt", f"Urban definition of {word}", event)
        return await event.try_delete()
    await event.eor(text)
