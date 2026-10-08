import asyncio
import os
import random
import requests
import sys
from logging import Formatter

from telethon.tl.custom.message import CustomMarkdown

from .version import __version__

run_as_module = __package__ in sys.argv or sys.argv[0] == "-m"


class ULTConfig:
    lang = "en"
    thumb = "resources/extras/heartless.jpg"


if run_as_module:
    import time

    from .configs import Var
    from .fns.helper import async_searcher
    from .startup import *
    from .startup._database import HeartlessDB
    from .startup.BaseClient import heartlessClient
    from .startup.connections import validate_session, vc_connection
    from .startup.funcs import _version_changes, autobot, enable_inline, update_envs
    from .version import heartless_version

    if not os.path.exists("./plugins"):
        LOGS.error(
            "'plugins' folder not found!\nMake sure that, you are on correct path."
        )
        exit()

    start_time = time.time()
    _ult_cache = {}
    _ignore_eval = []

    udB = HeartlessDB()
    update_envs()

    LOGS.info(f"Connecting to {udB.name}...")
    if udB.ping():
        LOGS.info(f"Connected to {udB.name} Successfully!")

    BOT_MODE = udB.del_key("BOTMODE")
    DUAL_MODE = udB.get_key("DUAL_MODE")

    USER_MODE = udB.get_key("USER_MODE")
    if USER_MODE:
        DUAL_MODE = False
    # if BOT_MODE:
    # if DUAL_MODE:
    # udB.del_key("DUAL_MODE")
    # DUAL_MODE = False
    # heartless_bot = None

    # if not udB.get_key("BOT_TOKEN"):
    # LOGS.critical(
    # '"BOT_TOKEN" not Found! Please add it, in order to use "BOTMODE"'
    # )

    # sys.exit()
    else:
        heartless_bot = heartlessClient(
            validate_session(Var.SESSION, LOGS),
            udB=udB,
            app_version=heartless_version,
            device_model="DarkPentester",
        )
        heartless_bot.run_in_loop(autobot())
        
    #-------------SPOTLOGS LOGGER-------------#
    SPOTLOGS = getLogger("CythonX:")
    SPOTLOGS.propagate = False

    class CustomFormatter(Formatter):
        def format(self, record):
            record.levelname = "SPOTIFY"
            return super().format(record)

    spot_formatter = CustomFormatter(
        "%(asctime)s | %(name)s [%(levelname)s] : %(message)s", datefmt="%m/%d/%Y, %H:%M:%S"
    )

    spot_handler = StreamHandler()
    spot_handler.setFormatter(spot_formatter)

    spot_file_handler = FileHandler(file)
    spot_file_handler.setLevel(INFO)
    spot_file_handler.setFormatter(spot_formatter)
    
    SPOTLOGS.addHandler(spot_file_handler)
    SPOTLOGS.addHandler(spot_handler)
    #-------------SPOTLOGS LOGGER-------------#
    
    if USER_MODE:
        asst = heartless_bot
    else:
        asst = heartlessClient("asst", bot_token=udB.get_key("BOT_TOKEN"), udB=udB)

    # if BOT_MODE:
    # heartless_bot = asst
    # if udB.get_key("OWNER_ID"):
    # try:
    # heartless_bot.me = heartless_bot.run_in_loop(
    # heartless_bot.get_entity(udB.get_key("OWNER_ID"))
    # )
    # except Exception as er:
    # LOGS.exception(er)
    # elif not asst.me.bot_inline_placeholder and asst._bot:
    # heartless_bot.run_in_loop(enable_inline(heartless_bot, asst.me.username))

    vcClient = vc_connection(udB, heartless_bot)
    _version_changes(udB)

    HNDLR = udB.get_key("HNDLR") or "."
    DUAL_HNDLR = udB.get_key("DUAL_HNDLR") or "/"
    SUDO_HNDLR = udB.get_key("SUDO_HNDLR") or HNDLR

    # ================= HF KEEP ALIVE ================= #

    HUGGING_TOKEN = udB.get_key("hf")

    async def hfv(api_url, timeout=10):
        try:
            headers = {
                "Authorization": f"Bearer {HUGGING_TOKEN}",
                "Content-Type": "application/json",
            }
            response = await async_searcher(
                api_url,
                headers=headers,
                re_json=True
            )
            return response.get("message", "ded")
        except requests.exceptions.RequestException as e:
            print("Error occurred:", e)
            return False

    async def periodic_hfv(api_url, interval_range):
        while True:
            result = await hfv(api_url)
            print(result)
            interval = random.randint(*interval_range)
            await asyncio.sleep(interval)

    heartless_bot.loop.create_task(
        periodic_hfv(
            "https://rootux-userx.hf.space/status",
            (2 * 3600, 4 * 3600)
        )
    )

    # ---------------- END ---------------- #

else:
    print("CythonX")

    from logging import getLogger

    LOGS = getLogger("CythonX")

    heartless_bot = asst = udB = vcClient = None
    
if heartless_bot:
    heartless_bot.parse_mode = CustomMarkdown() 
