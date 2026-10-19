import os
import sys
import asyncio
from glob import glob
from typing import Any, Dict, List, Union

from CythonX import *
from CythonX.fns.tools import translate

try:
    from yaml import safe_load
except ModuleNotFoundError:
    from CythonX.fns.tools import safe_load

ULTConfig.lang = udB.get_key("language") or os.getenv("LANGUAGE", "en")

languages = {}
PATH = "strings/strings/{}.yml"


def load(file):
    if not file.endswith(".yml"):
        return
    elif not os.path.exists(file):
        file = PATH.format("en")
    code = file.split("/")[-1].split("\\")[-1][:-4]
    try:
        languages[code] = safe_load(
            open(file, encoding="UTF-8"),
        )
    except Exception as er:
        LOGS.info(f"Error in {file[:-4]} language file")
        LOGS.exception(er)


load(PATH.format(ULTConfig.lang))


def _get_string_raw(key: str, _res: bool = True) -> Any:
    """Look up a translation leaving ``{p}`` premium placeholders intact.

    Only :func:`CythonX.fns.helper.get_pstring` should use this; everything
    else wants :func:`get_string`, which neutralises ``{p}``.
    """
    lang = ULTConfig.lang or "en"
    try:
        return languages[lang][key]
    except KeyError:
        try:
            en_ = languages["en"][key]
            tr = translate(en_, lang_tgt=lang).replace("\\ N", "\n")
            if en_.count("{}") != tr.count("{}"):
                tr = en_
            if languages.get(lang):
                languages[lang][key] = tr
            else:
                languages.update({lang: {key: tr}})
            return tr
        except KeyError:
            if not _res:
                return
            return f"Warning: could not load any string with the key `{key}`"
        except TypeError:
            pass
        except Exception as er:
            LOGS.exception(er)
        if not _res:
            return None
        return languages["en"].get(key) or f"Failed to load language string '{key}'"


def get_string(key: str, _res: bool = True) -> Any:
    """Look up a translation, neutralising any premium ``{p}`` placeholder.

    ``{p}`` is resolved by :func:`CythonX.fns.helper.get_pstring`.  A caller
    that goes through plain ``get_string`` cannot resolve it, and leaving it
    in place both leaks a literal ``{p}`` to the user and makes a later
    ``str.format()`` raise ``KeyError: 'p'``.  Dropping it here makes
    ``get_string`` safe for every caller; premium emojis are still injected
    by ``get_pstring`` through :func:`_get_string_raw`.
    """
    value = _get_string_raw(key, _res)
    if isinstance(value, str) and "{p}" in value:
        return value.replace("{p}", "")
    return value


def get_help(key):
    """Load a plugin help string from languages.

    Accepts either ``"compressor"`` or ``"help_compressor"`` — plugins and
    the loader historically mixed both forms, and prefixing ``help_`` twice
    made ``__doc__ = get_help("help_…")`` resolve to a missing key.
    """
    name = str(key or "").strip()
    if name.startswith("help_"):
        name = name[5:]
    if not name:
        return None
    doc = get_string(f"help_{name}", _res=False)
    if doc:
        return get_string("cmda") + doc


def get_languages() -> Dict[str, Union[str, List[str]]]:
    for file in glob("strings/strings/*yml"):
        load(file)
    return {
        code: {
            "name": languages[code]["name"],
            "natively": languages[code]["natively"],
            "authors": languages[code]["authors"],
        }
        for code in languages
    }
