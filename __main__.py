import glob
import asyncio
import logging
import time
import os
import sys
import importlib
import re
from pathlib import Path


logging.basicConfig(
    level=logging.INFO,
    datefmt="%d/%m/%Y %H:%M:%S",
    format="[%(asctime)s][%(name)s][%(levelname)s] ==> %(message)s",
    handlers=[logging.StreamHandler(stream=sys.stdout),
              logging.FileHandler("heartless.log", mode="a", encoding="utf-8")],)


ppath = "CythonX/*.py"
files = glob.glob(ppath)

loop = asyncio.get_event_loop()


async def start_services():
    logging.info('------------- Importing Plugins ------------')
    for name in files:
        with open(name) as a:
            patt = Path(a.name)
            plugin_name = patt.stem.replace(".py", "")
            plugins_dir = Path(f"CythonX/{plugin_name}.py")
            import_path = ".{}".format(plugin_name)
            spec = importlib.util.spec_from_file_location(import_path, plugins_dir)
            load = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(load)
            sys.modules["CythonX." + plugin_name] = load
            logging.info("Imported => " + plugin_name)
    logging.info('----------- UserBot is Ready to Use ------------')


if __name__ == '__main__':        
    try:
        loop.run_until_complete(start_services())
    except KeyboardInterrupt:
        pass
    except Exception as err:
        logging.error(err.with_traceback(None))
    finally:
        loop.stop()
        logging.info("--------- Service Stopped ---------")
