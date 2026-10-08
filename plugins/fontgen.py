"""
Megatron Font Studio
--------------------
A dependency-free Unicode text styling plugin for Telethon/Megatron.

Commands:
    .font
    .font <style> <text>
    .font <style>: <text>
    .font <style>       # when replying to a message
    .fonts               # same as .font
    .font random <text>

Notes:
- Unicode "fonts" are character styles, not real Telegram font files.
- Mathematical Unicode alphabets mainly cover Latin letters and digits.
  Persian/Arabic text has no equivalent set of Unicode mathematical alphabets,
  so decorative styles intentionally leave unsupported characters unchanged.
"""

from __future__ import annotations

import random
import re
import secrets
import unicodedata
from functools import lru_cache
from html import escape

from . import Button, asst, callback, eod, eor, in_pattern, heartless_cmd


# ---------------------------------------------------------------------------
# Unicode helpers
# ---------------------------------------------------------------------------

_ASCII = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

# Mathematical alphabets. Some Unicode alphabets have intentionally missing
# code points (especially Script/Fraktur capitals), so we use Unicode names
# first and explicit fallbacks where necessary.
_MATH_STYLES = {
    "bold": "MATHEMATICAL BOLD",
    "italic": "MATHEMATICAL ITALIC",
    "bold_italic": "MATHEMATICAL BOLD ITALIC",
    "sans": "MATHEMATICAL SANS-SERIF",
    "sans_bold": "MATHEMATICAL SANS-SERIF BOLD",
    "sans_italic": "MATHEMATICAL SANS-SERIF ITALIC",
    "sans_bold_italic": "MATHEMATICAL SANS-SERIF BOLD ITALIC",
    "monospace": "MATHEMATICAL MONOSPACE",
    "double": "MATHEMATICAL DOUBLE-STRUCK",
    "fraktur": "MATHEMATICAL FRAKTUR",
    "bold_fraktur": "MATHEMATICAL BOLD FRAKTUR",
    "script": "MATHEMATICAL SCRIPT",
    "bold_script": "MATHEMATICAL BOLD SCRIPT",
}

# Characters for the exceptional Script/Fraktur capitals.
_SCRIPT_FALLBACK = {
    "B": "ℬ", "E": "ℰ", "F": "ℱ", "H": "ℋ", "I": "ℐ",
    "L": "ℒ", "M": "ℳ", "R": "ℛ",
}
_FRAKTUR_FALLBACK = {
    "C": "ℭ", "H": "ℌ", "I": "ℑ", "R": "ℜ", "Z": "ℨ",
}
_DOUBLE_FALLBACK = {
    "C": "ℂ", "H": "ℍ", "N": "ℕ", "P": "ℙ", "Q": "ℚ",
    "R": "ℝ", "Z": "ℤ",
}

# Superscript/subscript have deliberately incomplete Unicode alphabets.
_SUPERSCRIPT = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
    "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
    "+": "⁺", "-": "⁻", "=": "⁼", "(": "⁽", ")": "⁾",
    "a": "ᵃ", "b": "ᵇ", "c": "ᶜ", "d": "ᵈ", "e": "ᵉ",
    "f": "ᶠ", "g": "ᵍ", "h": "ʰ", "i": "ⁱ", "j": "ʲ",
    "k": "ᵏ", "l": "ˡ", "m": "ᵐ", "n": "ⁿ", "o": "ᵒ",
    "p": "ᵖ", "r": "ʳ", "s": "ˢ", "t": "ᵗ", "u": "ᵘ",
    "v": "ᵛ", "w": "ʷ", "x": "ˣ", "y": "ʸ", "z": "ᶻ",
}
_SUBSCRIPT = {
    "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄",
    "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉",
    "+": "₊", "-": "₋", "=": "₌", "(": "₍", ")": "₎",
    "a": "ₐ", "e": "ₑ", "h": "ₕ", "i": "ᵢ", "j": "ⱼ",
    "k": "ₖ", "l": "ₗ", "m": "ₘ", "n": "ₙ", "o": "ₒ",
    "p": "ₚ", "r": "ᵣ", "s": "ₛ", "t": "ₜ", "u": "ᵤ",
    "v": "ᵥ", "x": "ₓ",
}

# Decorative transformations that work on arbitrary Unicode text.
_CIRCLED_LOWER = "ⓐⓑⓒⓓⓔⓕⓖⓗⓘⓙⓚⓛⓜⓝⓞⓟⓠⓡⓢⓣⓤⓥⓦⓧⓨⓩ"
_CIRCLED_UPPER = "ⒶⒷⒸⒹⒺⒻⒼⒽⒾⒿⓀⓁⓂⓃⓄⓅⓆⓇⓈⓉⓊⓋⓌⓍⓎⓏ"
_NEG_CIRCLED_LOWER = "🅐🅑🅒🅓🅔🅕🅖🅗🅘🅙🅚🅛🅜🅝🅞🅟🅠🅡🅢🅣🅤🅥🅦🅧🅨🅩"
_NEG_CIRCLED_UPPER = "🅰🅱🅲🅳🅴🅵🅶🅷🅸🅹🅺🅻🅼🅽🅾🅿🆀🆁🆂🆃🆄🆅🆆🆇🆈🆉"
_SQUARED_UPPER = "🄰🄱🄲🄳🄴🄵🄶🄷🄸🄹🄺🄻🄼🄽🄾🄿🅀🅁🅂🅃🅄🅅🅆🅇🅈🅉"
_NEG_SQUARED_UPPER = "🅰🅱🅲🅳🅴🅵🅶🅷🅸🅹🅺🅻🅼🅽🅾🅿🆀🆁🆂🆃🆄🆅🆆🆇🆈🆉"

_FULLWIDTH = {
    chr(i): chr(0xFF01 + i - 0x21) for i in range(0x21, 0x7F)
}
_FULLWIDTH[" "] = "　"

_SMALL_CAPS = {
    "a": "ᴀ", "b": "ʙ", "c": "ᴄ", "d": "ᴅ", "e": "ᴇ", "f": "ғ",
    "g": "ɢ", "h": "ʜ", "i": "ɪ", "j": "ᴊ", "k": "ᴋ", "l": "ʟ",
    "m": "ᴍ", "n": "ɴ", "o": "ᴏ", "p": "ᴘ", "q": "ǫ", "r": "ʀ",
    "s": "s", "t": "ᴛ", "u": "ᴜ", "v": "ᴠ", "w": "ᴡ", "x": "x",
    "y": "ʏ", "z": "ᴢ",
}

_UPSIDE_DOWN = str.maketrans({
    "a": "ɐ", "b": "q", "c": "ɔ", "d": "p", "e": "ǝ", "f": "ɟ",
    "g": "ƃ", "h": "ɥ", "i": "ᴉ", "j": "ɾ", "k": "ʞ", "l": "ʃ",
    "m": "ɯ", "n": "u", "o": "o", "p": "d", "q": "b", "r": "ɹ",
    "s": "s", "t": "ʇ", "u": "n", "v": "ʌ", "w": "ʍ", "x": "x",
    "y": "ʎ", "z": "z",
    "A": "∀", "B": "𐐒", "C": "Ↄ", "D": "◖", "E": "Ǝ", "F": "Ⅎ",
    "G": "פ", "H": "H", "I": "I", "J": "ſ", "K": "⋊", "L": "˥",
    "M": "W", "N": "N", "O": "O", "P": "Ԁ", "Q": "Ό", "R": "ᴚ",
    "S": "S", "T": "┴", "U": "∩", "V": "Λ", "W": "M", "X": "X",
    "Y": "⅄", "Z": "Z",
    "0": "0", "1": "Ɩ", "2": "ᄅ", "3": "Ɛ", "4": "ㄣ",
    "5": "ϛ", "6": "9", "7": "ㄥ", "8": "8", "9": "6",
    ".": "˙", ",": "'", "'": ",", "!": "¡", "?": "¿",
    "_": "‾", "&": "⅋",
})

_MIRROR = str.maketrans({
    "(": ")", ")": "(", "[": "]", "]": "[", "{": "}", "}": "{",
    "<": ">", ">": "<", "/": "\\", "\\": "/", "b": "d", "d": "b",
    "p": "q", "q": "p",
})

# Combining marks are kept intentionally lightweight. This is a decoration,
# not a "Zalgo spammer"; it adds one stable mark per printable character.
_OVERLINE = "\u0305"
_UNDERLINE = "\u0332"
_STRIKE = "\u0336"
_DOT = "\u0307"


# Extra mappings pasted as "UppercaseReplacement LowercaseReplacement" pairs,
# in A,a,B,b,... order. They are exposed as custom1, custom2, ...
CUSTOM_FONT_LINES = [
    "AᴀBʙCᴄDdEᴇFfGgHhIiJjKᴋLlMʍNnOᴏPᴩQqRrSsTᴛUuVvWwXxYyZz",
    "AᥲBδ𑀝ᥴ𑀥ɗEᥱFfᏵg𐋏ɦIiJj𐌺κ𑀉ᥣ𐌑ⲙ𐌽ᥒ𐌏᧐PρQqRr𐍃sTᴛ𐌵ᥙV᥎WᥕX᥊YyZᤁ",
    "ⲀⲁⲂⲃⲤⲥⲆⲇⲈⲉϜϝⳒⳋⲎⲏⲒⲓⳖⳗⲔⲕⳐⳑⲘⲙⲚⲛⲞⲟⲢⲣQqRʀⲊⲋⲦⲧⳘυⳲⳳⲰⲱⲬⲭⲨⲩⲌⲍ",
    "ΑαΒϸ𑀝ϲƊɗξεϜϝƓɠΗɦ𑀡ʝͿʆӃӄLɭϺϻƝηΟσϷρϘϙɌɾЅʂͲʈƲμѴѵŴωΧ𑀌ϒγζʐ",
    "ααɓɓϲϲ∂∂ϱϱƒƒɠɠɧɧɩɩʝʝƙƙɭɭɱɱɳɳσσρρʠʠɼɼѕѕʈʈυυννѡѡχχƴƴʑʑ",
    "𐌀ꤌ𐌱ꤐ𑀗ꤍ𑀥ꤤΣꤕ𐍆કᏵɠ𐋏ꤖ𐌆꤯𐌋ʆ𐌺ӄ𑀉꤈𐌑𐌌𐌽ꤙ𐌏꤀𐌛ρዓᱧ𐍂꤅𐍃᥉𐌕𑀱𐌵𐌵ս𐠨꤂ᱦꤗ𐌗𑀋𐍅γ𐌔ꤘ",
    "ɑɑᑲᑲςςᑯᑯ૯૯⨍⨍ɢɢⲏⲏɪɪᴊᴊκκʟʟⲙⲙⲛⲛ૦૦ƿƿવવʀʀઽઽ੮੮υυννਘਘⲭⲭⲩⲩⲍⲍ",
    "ᎪᴀᏴʙᏟᴄᎠdᎬᴇᎰfᏀgᎻhᏆiᎫjᏦᴋᏞlᎷʍNnᏫᴏᏢᴩᎧqᏒrᏚsᎢᴛᏌuᏙvᎳwᏡxᎩyᏃz",
    "𐌀𐌀𐌁𐌁𐌂𐌂ƊƊ𐌄𐌄𐌅𐌅GGHH𐌉𐌉𐌋𐌋𐌃𐌃𐌑𐌑NN𐌏𐌏𐌛𐌛𐌒𐌒𐌓𐌓𐍃𐍃𐌕𐌕UU𐌖𐌖WW𐌗𐌗𐍔𐍔𐌔𐌔",
    "𐌳𐌳ଓଓꤍꤍᱚᱚꤕꤕፑፑ᱙᱙ዘዘ𐌉𐌉𐌋𐌋ઝઝ𑀉𑀉ᱬᱬ𐌽𐌽ᱛᱛᱞᱞᱧᱧ𐍂𐍂ႽႽተተ𐌵𐌵𐌖𐌖ᱦᱦ𐌗𐌗𐍅𐍅ᱮᱮ",
    "𐌳𐌳𐌱𐌱𐌾𐌾DD𐌴𐌄𐍆𐍆GGHH𐌹𐌹𐍡𐍡𐌺𐌺𐍰𐍰𐌼𐌼𐌽𐌽𐌏𐌏ᖘᖘQQ𐍂𐍂𐍃𐍃𐍄𐍄𐌵𐌵𐍛𐍛𐍪𐍪𐍇𐍇𐍟𐍟𐍐𐍐",
    "𝔄𝔞𝔅𝔟ℭ𝔠𝔇𝔡𝔈𝔢𝔉𝔣𝔊𝔤ℌ𝔥𝔗𝔦𝔍𝔧𝔎𝔨𝔏𝔩𝔐𝔪𝔑𝔫𝔒𝔬𝔓𝔭𝔔𝔮ℜ𝔯𝔖𝔰ℑ𝔱𝔘𝔲𝔙𝔳𝔚𝔴𝔛𝔵ϒ𝛾ℨ𝔷",
    "𝕬𝖆𝕭𝖇𝕮𝖈𝕯𝖉𝕰𝖊𝕱𝖋𝕲𝖌𝕳𝖍𝕿𝖎𝕵𝖏𝕶𝖐𝕷𝖑𝕸𝖒𝕹𝖓𝕺𝖔𝕻𝖕𝕼𝖖𝕽𝖗𝕾𝖘𝕴𝖙𝖀𝖚𝖁𝖛𝖂𝖜𝖃𝖝𝚼𝛄𝖅𝖟",
]


def _custom_pair_style(line: str) -> dict[str, str]:
    table: dict[str, str] = {}
    for index, char in enumerate(line):
        if index % 2 == 0:
            table[chr(ord("A") + index // 2)] = char
        else:
            table[chr(ord("a") + index // 2)] = char
    return table


_CUSTOM_STYLES = {
    f"custom{i}": _custom_pair_style(line)
    for i, line in enumerate(CUSTOM_FONT_LINES, 1)
}


def _named_char(prefix: str, ch: str) -> str:
    """Return a mathematical Unicode character or the original character."""
    if not ("a" <= ch.lower() <= "z"):
        return ch
    case = "CAPITAL" if ch.isupper() else "SMALL"
    name = f"{prefix} {case} {ch.upper()}"
    try:
        return unicodedata.lookup(name)
    except KeyError:
        return ch


@lru_cache(maxsize=None)
def _math_map(style: str) -> dict[str, str]:
    prefix = _MATH_STYLES[style]
    result = {ch: _named_char(prefix, ch) for ch in _ASCII}

    if style == "script":
        result.update(_SCRIPT_FALLBACK)
    elif style == "fraktur":
        result.update(_FRAKTUR_FALLBACK)
    elif style == "double":
        result.update(_DOUBLE_FALLBACK)

    # Mathematical sans/monospace/double/etc. also provide digits.
    digit_prefix = prefix
    for d in "0123456789":
        try:
            result[d] = unicodedata.lookup(f"{digit_prefix} DIGIT {d}")
        except KeyError:
            pass
    return result


def _translate(text: str, table: dict[str, str]) -> str:
    return "".join(table.get(ch, ch) for ch in text)


def _circled(text: str, negative: bool = False) -> str:
    lo = _NEG_CIRCLED_LOWER if negative else _CIRCLED_LOWER
    up = _NEG_CIRCLED_UPPER if negative else _CIRCLED_UPPER
    out = []
    for ch in text:
        if "a" <= ch <= "z":
            out.append(lo[ord(ch) - 97])
        elif "A" <= ch <= "Z":
            out.append(up[ord(ch) - 65])
        elif ch.isdigit() and not negative:
            # 0/1/2 are the common circled digit code points; the rest use
            # parenthesized forms only where available.
            out.append({"0": "⓪", "1": "①", "2": "②", "3": "③",
                        "4": "④", "5": "⑤", "6": "⑥", "7": "⑦",
                        "8": "⑧", "9": "⑨"}.get(ch, ch))
        else:
            out.append(ch)
    return "".join(out)


def _squared(text: str, negative: bool = False) -> str:
    table = _NEG_SQUARED_UPPER if negative else _SQUARED_UPPER
    out = []
    for ch in text:
        if "a" <= ch.lower() <= "z":
            out.append(table[ord(ch.lower()) - 97])
        else:
            out.append(ch)
    return "".join(out)


def _decorate(text: str, mark: str) -> str:
    return "".join(
        ch + mark if not ch.isspace() else ch
        for ch in text
    )


def _bubble(text: str) -> str:
    # A compact "bubble" style that works for Latin text and leaves everything
    # else readable.
    return _circled(text)


def _upside_down(text: str) -> str:
    # Reverse grapheme-like code points after translating. This intentionally
    # avoids external Unicode/regex dependencies.
    return text.translate(_UPSIDE_DOWN)[::-1]


def _mirror(text: str) -> str:
    return text.translate(_MIRROR)[::-1]


@lru_cache(maxsize=None)
def _style_functions():
    funcs = {}

    for name in _MATH_STYLES:
        funcs[name] = lambda text, n=name: _translate(text, _math_map(n))

    funcs.update({
        "smallcaps": lambda t: _translate(t.lower(), _SMALL_CAPS),
        "circled": lambda t: _circled(t),
        "negative_circled": lambda t: _circled(t, negative=True),
        "squared": lambda t: _squared(t),
        "negative_squared": lambda t: _squared(t, negative=True),
        "fullwidth": lambda t: _translate(t, _FULLWIDTH),
        "superscript": lambda t: _translate(t.lower(), _SUPERSCRIPT),
        "subscript": lambda t: _translate(t.lower(), _SUBSCRIPT),
        "strikethrough": lambda t: _decorate(t, _STRIKE),
        "underline": lambda t: _decorate(t, _UNDERLINE),
        "overline": lambda t: _decorate(t, _OVERLINE),
        "dotted": lambda t: _decorate(t, _DOT),
        "upside_down": _upside_down,
        "mirrored": _mirror,
        "bubble": _bubble,
    })
    for key, table in _CUSTOM_STYLES.items():
        funcs[key] = lambda text, t=table: _translate(text, t)
    return funcs


# ---------------------------------------------------------------------------
# Public style names and aliases
# ---------------------------------------------------------------------------

DISPLAY_NAMES = {
    "bold": "𝐁𝐨𝐥𝐝",
    "italic": "𝘐𝘵𝘢𝘭𝘪𝘤",
    "bold_italic": "𝑩𝒐𝒍𝒅 𝑰𝒕𝒂𝒍𝒊𝒄",
    "sans": "𝖲𝖺𝗇𝗌",
    "sans_bold": "𝗦𝗮𝗻𝘀 𝗕𝗼𝗹𝗱",
    "sans_italic": "𝘚𝘢𝘯𝘴 𝘐𝘵𝘢𝘭𝘪𝘤",
    "sans_bold_italic": "𝙎𝙖𝙣𝙨 𝘽𝙤𝙡𝙙 𝙄𝙩𝙖𝙡𝙞𝙘",
    "monospace": "𝙼𝚘𝚗𝚘𝚜𝚙𝚊𝚌𝚎",
    "double": "𝔻𝕠𝕦𝕓𝕝𝕖",
    "fraktur": "𝔉𝔯𝔞𝔨𝔱𝔲𝔯",
    "bold_fraktur": "𝕭𝖔𝖑𝖉 𝕱𝖗𝖆𝖐𝖙𝖚𝖗",
    "script": "𝒮𝒸𝓇𝒾𝓅𝓉",
    "bold_script": "𝓑𝓸𝓵𝓭 𝓢𝓬𝓻𝓲𝓹𝓽",
    "smallcaps": "Sᴍᴀʟʟ Cᴀᴘs",
    "circled": "Ⓒⓘⓡⓒⓛⓔⓓ",
    "negative_circled": "🅽🅴🅶",
    "squared": "🅂🅀🅄🄰🅁🄴🄳",
    "negative_squared": "🅽🅴🅶 🆂🆀🆄🅰🆁🅴🅳",
    "fullwidth": "Ｆｕｌｌｗｉｄｔｈ",
    "superscript": "ˢᵘᵖᵉʳˢᶜʳⁱᵖᵗ",
    "subscript": "ₛᵤᵦₛ𝒸ᵣᵢₚₜ",
    "strikethrough": "S̶t̶r̶i̶k̶e̶",
    "underline": "U̲n̲d̲e̲r̲l̲i̲n̲e̲",
    "overline": "O̅v̅e̅r̅l̅i̅n̅e̅",
    "dotted": "Ḋȯṫṫėḋ",
    "upside_down": "uʍop ǝpᴉsd∩",
    "mirrored": "ᴙoɿɿiM",
    "bubble": "Ⓑⓤⓑⓑⓛⓔ",
}

for _i in range(1, len(CUSTOM_FONT_LINES) + 1):
    DISPLAY_NAMES[f"custom{_i}"] = f"Cᴜsᴛᴏᴍ {_i}"

ALIASES = {
    "b": "bold", "bold": "bold", "strong": "bold",
    "i": "italic", "ital": "italic", "italic": "italic",
    "bi": "bold_italic", "bolditalic": "bold_italic", "bold-italic": "bold_italic",
    "ss": "sans", "sansserif": "sans", "sans-serif": "sans",
    "sb": "sans_bold", "sansbold": "sans_bold", "sans-bold": "sans_bold",
    "si": "sans_italic", "sansitalic": "sans_italic", "sans-italic": "sans_italic",
    "sbi": "sans_bold_italic", "sansbolditalic": "sans_bold_italic",
    "mono": "monospace", "monospace": "monospace", "typewriter": "monospace",
    "ds": "double", "double": "double", "double-struck": "double",
    "frak": "fraktur", "fraktur": "fraktur",
    "bfrak": "bold_fraktur", "boldfraktur": "bold_fraktur",
    "script": "script", "cursive": "script",
    "bs": "bold_script", "boldscript": "bold_script",
    "sc": "smallcaps", "small": "smallcaps", "smallcaps": "smallcaps",
    "circle": "circled", "circled": "circled", "bubble": "bubble",
    "negcircle": "negative_circled", "negativecircle": "negative_circled",
    "square": "squared", "squared": "squared",
    "negsquare": "negative_squared", "negativesquare": "negative_squared",
    "wide": "fullwidth", "full": "fullwidth", "fullwidth": "fullwidth",
    "super": "superscript", "sup": "superscript", "superscript": "superscript",
    "sub": "subscript", "subscript": "subscript",
    "strike": "strikethrough", "strikethrough": "strikethrough",
    "line": "underline", "underline": "underline",
    "overline": "overline", "over": "overline",
    "dot": "dotted", "dotted": "dotted",
    "up": "upside_down", "upside": "upside_down", "upsidedown": "upside_down",
    "flip": "upside_down", "mirror": "mirrored", "mirrored": "mirrored",
    "random": "random",
}
for _i in range(1, len(CUSTOM_FONT_LINES) + 1):
    ALIASES[f"custom{_i}"] = f"custom{_i}"
    ALIASES[f"custom_{_i}"] = f"custom{_i}"

# Longest names first, so "bold italic" is parsed before "bold".
_STYLE_KEYS = sorted(
    set(DISPLAY_NAMES) | set(ALIASES),
    key=len,
    reverse=True,
)


def _canonical_style(name: str) -> str | None:
    key = " ".join(name.strip().lower().replace("_", " ").split())
    key_no_space = key.replace(" ", "")
    return ALIASES.get(key) or ALIASES.get(key_no_space) or (
        key.replace(" ", "_") if key.replace(" ", "_") in DISPLAY_NAMES else None
    )


def _parse_style_and_text(raw: str, reply_text: str | None):
    raw = raw.strip()

    if not raw:
        return None, reply_text

    # Explicit separators are the least ambiguous and support multi-word names.
    for sep in (":", "|"):
        if sep in raw:
            left, right = raw.split(sep, 1)
            style = _canonical_style(left)
            if style:
                return style, right.strip() or reply_text
            return None, None

    if reply_text is not None:
        # In reply mode, `.font bold` means "bold the replied message".
        style = _canonical_style(raw)
        if style:
            return style, reply_text

    # No reply: accept `.font bold hello world` by matching the longest
    # recognized style prefix.
    lowered = raw.lower()
    for key in _STYLE_KEYS:
        key_norm = key.replace("_", " ")
        if lowered == key_norm:
            style = _canonical_style(key)
            return style, reply_text
        if lowered.startswith(key_norm + " "):
            style = _canonical_style(key)
            return style, raw[len(key_norm):].strip()

    # Also allow `.font bold_italic hello`.
    for key in _STYLE_KEYS:
        if lowered.startswith(key + " "):
            style = _canonical_style(key)
            return style, raw[len(key):].strip()

    return None, None



def _all_fonts_preview(text: str) -> str:
    """Render text once with every available style and label each line."""
    lines = ["**✨ Font Studio — Preview**", ""]
    funcs = _style_functions()
    for style, display_name in DISPLAY_NAMES.items():
        func = funcs.get(style)
        try:
            converted = func(text) if func else text
        except Exception:
            converted = text
        lines.append(f"**{display_name}:** {converted}")
    return "\n".join(lines)


def _format_font_list() -> str:
    lines = [
        "**✨ Font Studio**",
        "",
        "Use: `.font <style> <text>`",
        "Or reply to a message with: `.font <style>`",
        "",
        "**Available styles:**",
    ]
    for index, key in enumerate(DISPLAY_NAMES, 1):
        lines.append(f"`{index:02}` • **{key}** — {DISPLAY_NAMES[key]}")
    lines.extend([
        "",
        "Aliases: `b`, `i`, `bi`, `mono`, `ds`, `frak`, `script`, `sc`, "
        "`circle`, `square`, `wide`, `super`, `sub`, `strike`, `up`, `mirror`",
        "",
        "Tip: `.font random <text>` picks a style automatically.",
    ])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Fully inline Font Studio panel
# ---------------------------------------------------------------------------

_FONT_STATE = {}
_FONT_PAGE_SIZE = 10


def _new_font_state(text: str, owner_id: int | None = None) -> str:
    token = secrets.token_hex(4)
    if len(_FONT_STATE) > 200:
        try:
            _FONT_STATE.pop(next(iter(_FONT_STATE)))
        except Exception:
            pass
    _FONT_STATE[token] = {
        "text": text,
        "owner_id": owner_id,
        "selected": None,
        "page": 0,
    }
    return token


def _font_text(state: dict) -> str:
    text = state.get("text", "")
    style = state.get("selected")
    if not style:
        return text
    func = _style_functions().get(style)
    try:
        return func(text) if func else text
    except Exception:
        return text


def _font_panel_text(state: dict) -> str:
    # Monospace the selected output; <code> preserves the exact glyphs.
    return f"<code>{escape(_font_text(state))}</code>"


def _font_buttons(token: str, state: dict):
    styles = list(DISPLAY_NAMES)
    page = max(0, min(int(state.get("page", 0)), max(0, (len(styles) - 1) // _FONT_PAGE_SIZE)))
    state["page"] = page
    start = page * _FONT_PAGE_SIZE
    chunk = styles[start:start + _FONT_PAGE_SIZE]
    funcs = _style_functions()
    rows = []
    for i in range(0, len(chunk), 2):
        row = []
        for style in chunk[i:i + 2]:
            try:
                text = funcs[style](state["text"])
            except Exception:
                text = state["text"]
            label = text if text else state["text"]
            if style == state.get("selected"):
                label = f"{label}✅"
            row.append(Button.inline(label, data=f"fnt_sel:{token}:{style}"))
        rows.append(row)

    last_page = max(0, (len(styles) - 1) // _FONT_PAGE_SIZE)
    nav = []
    if page > 0:
        nav.append(Button.inline("⬅️ Previous", data=f"fnt_page:{token}:{page - 1}"))
    nav.append(Button.inline(f"{page + 1}/{last_page + 1}", data=f"fnt_noop:{token}"))
    if page < last_page:
        nav.append(Button.inline("Next ➡️", data=f"fnt_page:{token}:{page + 1}"))
    rows.append(nav)
    rows.append([Button.inline("❌ Close", data=f"fnt_close:{token}")])
    return rows


def _get_font_state(token: str) -> dict | None:
    return _FONT_STATE.get(token)


async def _render_font_panel(event, token: str, *, answer: bool = False):
    state = _get_font_state(token)
    if not state:
        if answer:
            return await event.answer("Session expired. Run .font again.", alert=True)
        return
    await event.edit(_font_panel_text(state), buttons=_font_buttons(token, state), parse_mode="html")


@callback(re.compile(r"fnt_sel:([^:]+):(.+)"), owner=True)
async def _font_select_cb(e):
    token = e.data_match.group(1).decode()
    style = e.data_match.group(2).decode()
    state = _get_font_state(token)
    if not state:
        return await e.answer("Session expired. Run .font again.", alert=True)
    if style in DISPLAY_NAMES:
        state["selected"] = style
    await _render_font_panel(e, token)


@callback(re.compile(r"fnt_page:([^:]+):(\d+)"), owner=True)
async def _font_page_cb(e):
    token = e.data_match.group(1).decode()
    page = int(e.data_match.group(2).decode())
    state = _get_font_state(token)
    if not state:
        return await e.answer("Session expired. Run .font again.", alert=True)
    state["page"] = page
    await _render_font_panel(e, token)


@callback(re.compile(r"fnt_noop:([^:]+)"), owner=True)
async def _font_noop_cb(e):
    return await e.answer(cache_time=0)


@callback(re.compile(r"fnt_close:([^:]+)"), owner=True)
async def _font_close_cb(e):
    token = e.data_match.group(1).decode()
    _FONT_STATE.pop(token, None)
    try:
        await e.delete()
    except Exception:
        try:
            await e.edit("Closed.", buttons=None, parse_mode=None)
        except Exception:
            return await e.answer("Closed.", cache_time=0)


@in_pattern(r"^font(?:\s+(.*))?$", owner=True)
async def _font_inline(e):
    raw = ""
    try:
        raw = (e.pattern_match.group(1) or "").strip()
    except Exception:
        raw = ""
    text = raw or "hello"
    token = _new_font_state(text, getattr(e, "sender_id", None))
    state = _get_font_state(token)
    article = await e.builder.article(
        "Font Studio",
        text=_font_panel_text(state),
        parse_mode="html",
        buttons=_font_buttons(token, state),
        link_preview=False,
        id=token,
    )
    await e.answer([article])


__doc__ = """
**Font Studio**

• `.font` — show all available text styles.
• `.font <style> <text>` — convert text.
• `.font <style>: <text>` — same, convenient for multi-word styles.
• Reply to a message and use `.font <style>`.
• `.fonts` — alias for `.font`.
• `.font random <text>` — choose a random style.

Unicode text styles work best with Latin/ASCII characters. Persian/Arabic
letters do not have separate Unicode mathematical alphabets, so those
characters remain unchanged rather than being corrupted.
"""


@heartless_cmd(pattern=r"(?:font|fonts)(?:\s+(.+))?$")
async def font_handler(e):
    raw = (e.pattern_match.group(1) or "").strip()
    reply = await e.get_reply_message()
    reply_text = getattr(reply, "raw_text", None) if reply else None

    if not raw:
        return await e.eor(_format_font_list(), parse_mode="md")

    if raw.lower() in {"list", "help", "fonts"}:
        return await e.eor(_format_font_list(), parse_mode="md")

    # Explicit preview mode.
    if raw.lower().startswith("all ") or raw.lower().startswith("all:"):
        preview = raw[3:].lstrip(" :").strip()
        if not preview:
            return await e.eod("`Usage:` `.font all <text>`", time=8)
        return await e.eor(_all_fonts_preview(preview), parse_mode="md")

    # A bare, non-style argument opens the inline Font Studio panel.
    # Example: `.font cipherx`
    style, text = _parse_style_and_text(raw, reply_text)
    if style is None and reply_text is None:
        if getattr(e.client, "_bot", False):
            token = _new_font_state(raw, getattr(e, "sender_id", None))
            state = _get_font_state(token)
            return await e.eor(
                _font_panel_text(state),
                buttons=_font_buttons(token, state),
                parse_mode="html",
            )
        try:
            results = await e.client.inline_query(asst.me.username, f"font {raw}")
            if results:
                await results[0].click(e.chat_id, silent=True, hide_via=True)
            return await e.delete()
        except Exception as exc:
            return await e.eod(f"`Inline panel failed:` `{exc}`", time=8)

    if style == "random":
        available = list(DISPLAY_NAMES)
        style = random.choice(available)

        # `.font random` in reply mode is supported too.
        if text is None:
            text = reply_text

    if not style:
        return await e.eod(
            "`Unknown font style.`\n\n"
            "Use `.font` to see all styles, or `.font bold: your text`.",
            time=8,
        )

    if not text:
        return await e.eod(
            f"`Missing text.`\n\nUse `.font {style}: your text` "
            "or reply to a message with the command.",
            time=8,
        )

    func = _style_functions().get(style)
    if not func:
        return await e.eod("`This style is not available.`", time=8)

    try:
        result = func(text)
    except Exception:
        # A single malformed Unicode edge case should never take down the
        # plugin; returning the source text is safer than crashing.
        result = text

    if not result:
        return await e.eod("`Nothing to format.`", time=8)

    # Disable Markdown parsing so user text such as `_`, `*`, or backticks
    # survives exactly as entered.
    return await e.eor(result, parse_mode=None)
