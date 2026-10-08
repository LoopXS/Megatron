import re

from . import *

STRINGS = {
    1: """HI
OK BYE
""",
}


@callback(re.compile("initft_(\\d+)"))
async def init_depl(e):
    CURRENT = int(e.data_match.group(1))
    if CURRENT == 5:
        return await e.edit(
            STRINGS[5],
            buttons=Button.inline("≼≼", "initbk_4"),
            link_preview=False,
        )

    await e.edit(
        STRINGS[CURRENT],
        buttons=[
            Button.inline("≼≼", f"initbk_{str(CURRENT - 1)}"),
            Button.inline("≽≽", f"initft_{str(CURRENT + 1)}"),
        ],
        link_preview=False,
    )


@callback(re.compile("initbk_(\\d+)"))
async def ineiq(e):
    CURRENT = int(e.data_match.group(1))
    if CURRENT == 1:
        return await e.edit(
            STRINGS[1],
            buttons=Button.inline("≽≽", "initft_2"),
            link_preview=False,
        )

    await e.edit(
        STRINGS[CURRENT],
        buttons=[
            Button.inline("≼≼", f"initbk_{str(CURRENT - 1)}"),
            Button.inline("≽≽", f"initft_{str(CURRENT + 1)}"),
        ],
        link_preview=False,
    )
