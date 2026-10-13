import asyncio
import nest_asyncio
import logging
from aiohttp import web

from . import *

#routes = web.RouteTableDef()

#@routes.get("/", allow_head=True)
#async def root_route_handler(request):
    #return web.json_response("running")


#async def web_server():
    #web_app = web.Application(client_max_size=30000000)
    #web_app.add_routes(routes)
    #return web_app


def main():
    import time

    from .fns.helper import bash, time_formatter  # updater
    from .startup.funcs import (
        WasItRestart,
        autopilot,
        customize,
        plug,
        ready,
        startup_stuff,
    )
    from .startup.loader import load_other_plugins

    try:
        pass
    except ImportError:
        pass

    # Option to Auto Update On Restarts..
    # if (
    #    udB.get_key("UPDATE_ON_RESTART")
    #    and os.path.exists(".git")
    #    and heartless_bot.run_in_loop(updater())
    # ):
    #    heartless_bot.run_in_loop(bash("bash installer.sh"))

    #    os.execl(sys.executable, sys.executable, "-m", "CythonX")

    heartless_bot.run_in_loop(startup_stuff())

    heartless_bot.me.phone = None

    if not heartless_bot.me.bot:
        udB.set_key("OWNER_ID", heartless_bot.uid)

    LOGS.info("Initialising...")

    heartless_bot.run_in_loop(autopilot())

    pmbot = udB.get_key("PMBOT")
    manager = udB.get_key("MANAGER")
    addons = udB.get_key("ADDONS") or Var.ADDONS
    vcbot = udB.get_key("VCBOT") or Var.VCBOT

    #nest_asyncio.apply()
    #logging.info('----------- Configuring Web App ------------')
    #app = web.AppRunner(asyncio.run(web_server())) 
    #asyncio.run(app.setup()) 
    #bind_address = "0.0.0.0"
    #asyncio.run(web.TCPSite(app, bind_address, 8080).start())

    if HOSTED_ON == "okteto":
        vcbot = False

    if (HOSTED_ON == "termux" or udB.get_key("LITE_DEPLOY")) and udB.get_key(
        "EXCLUDE_OFFICIAL"
    ) is None:
        _plugins = "autocorrect autopic audiotools compressor forcesubscribe fedutils gdrive glitch instagram nsfwfilter nightmode pdftools writer youtube"
        udB.set_key("EXCLUDE_OFFICIAL", _plugins)

    load_other_plugins(addons=addons, pmbot=pmbot, manager=manager, vcbot=vcbot)

    suc_msg = """
            ----------------------------------------------------------------------
                              userbot has been deployed!
            ----------------------------------------------------------------------
    """

    # for channel plugins
    plugin_channels = udB.get_key("PLUGIN_CHANNEL")

    # Customize CɪᴘʜᴇʀX ᴇxᴄlusivᴇ ʙᴏᴛ Assistant...
    heartless_bot.run_in_loop(customize())

    # Load Addons from Plugin Channels.
    if plugin_channels:
        heartless_bot.run_in_loop(plug(plugin_channels))

    # Send/Ignore Deploy Message..
    if not udB.get_key("LOG_OFF"):
        heartless_bot.run_in_loop(ready())
    # if AsyncIOScheduler:
    # scheduler = AsyncIOScheduler()
    # scheduler.add_job(fetch_ann, "interval", minutes=12 * 60)
    # scheduler.start()

    # Edit Restarting Message (if It's restarting)
    heartless_bot.run_in_loop(WasItRestart(udB))

    try:
        udB.re_cache()
    except BaseException:
        pass

    LOGS.info(
        f"Took {time_formatter((time.time() - start_time)*1000)} to start userbot."
    )
    LOGS.info(suc_msg)


if __name__ == "__main__":
    main()

    asst.run()
