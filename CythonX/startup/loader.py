import os
import subprocess
import sys
from pathlib import Path
from shutil import rmtree

from decouple import config
from git import Repo

from .. import *
from ..dB._core import HELP
from ..fns.helper import bash
from ..loader import Loader
from . import *
from .utils import load_addons


def _after_load(loader, module, plugin_name=""):
    if not module or plugin_name.startswith("_"):
        return
    from strings import get_help

    if doc_ := get_help(plugin_name) or module.__doc__:
        # Only substitute `{i}` — `.format(**)` breaks docs that mention
        # other braces (e.g. `{time}`, JSON examples).
        try:
            doc = str(doc_).replace("{i}", str(HNDLR))
        except Exception as er:
            loader._logger.exception(er)
            loader._logger.info(f"Error in {plugin_name}: {module}")
            return
        if loader.key in HELP.keys():
            update_cmd = HELP[loader.key]
            try:
                update_cmd.update({plugin_name: doc})
            except BaseException as er:
                loader._logger.exception(er)
        else:
            try:
                HELP.update({loader.key: {plugin_name: doc}})
            except BaseException as em:
                loader._logger.exception(em)


def load_other_plugins(addons=None, pmbot=None, manager=None, vcbot=None):

    # for official
    _exclude = udB.get_key("EXCLUDE_OFFICIAL") or config("EXCLUDE_OFFICIAL", None)
    _exclude = _exclude.split() if _exclude else []

    # "INCLUDE_ONLY" was added to reduce Big List in "EXCLUDE_OFFICIAL" Plugin
    _in_only = udB.get_key("INCLUDE_ONLY") or config("INCLUDE_ONLY", None)
    _in_only = _in_only.split() if _in_only else []
    Loader().load(include=_in_only, exclude=_exclude, after_load=_after_load)

    # for assistant
    if not USER_MODE and not udB.get_key("DISABLE_AST_PLUGINS"):
        _ast_exc = ["pmbot"]
        if _in_only and "games" not in _in_only:
            _ast_exc.append("games")
        Loader(path="assistant").load(
            log=False, exclude=_ast_exc, after_load=_after_load
        )

    # for addons
    if addons:
        if url := udB.get_key("ADDONS_URL"):
            subprocess.run(f"git clone -q {url} addons", shell=True)
        if os.path.exists("addons") and not os.path.exists("addons/.git"):
            rmtree("addons")
        if not os.path.exists("addons"):
            #branch = subprocess.check_output(
                #"git ls-remote --symref https://github.com/LoopXS/Megatron-addons.git HEAD | grep 'ref:' | awk '{print $2}' | sed 's@refs/heads/@@'",
                #shell=True,
                #text=True
            #).strip()
            
            #subprocess.run(
                #f"git clone -q -b {branch} https://github.com/LoopXS/Megatron-addons.git addons",
                #shell=True,
                #check=True
            #)

            subprocess.run(
                "git clone -q -b main https://github.com/LoopXS/Megatron-addons.git addons",
                shell=True,
            )
        else:
            subprocess.run("cd addons && git pull -q && cd ..", shell=True)

        if not os.path.exists("addons"):
            subprocess.run(
                "git clone -q https://github.com/LoopXS/Megatron-addons.git addons",
                shell=True,
            )
        if os.path.exists("addons/addons.txt"):
            # generally addons req already there so it won't take much time
            # Do not abort bot startup if an optional addon dep fails (e.g. no
            # Python 3.14 wheels) — plugins that need it will soft-fail later.
            pip_rc = subprocess.run(
                f"{sys.executable} -m pip install --no-cache-dir -q -r ./addons/addons.txt",
                shell=True,
            )
            if pip_rc.returncode != 0:
                LOGS.error(
                    "Some addon requirements failed to install "
                    "(see pip output). Continuing without them."
                )

        _exclude = udB.get_key("EXCLUDE_ADDONS")
        _exclude = _exclude.split() if _exclude else []
        _in_only = udB.get_key("INCLUDE_ADDONS")
        _in_only = _in_only.split() if _in_only else []

        Loader(path="addons", key="Addons").load(
            func=load_addons,
            include=_in_only,
            exclude=_exclude,
            after_load=_after_load,
            load_all=True,
        )

    if not USER_MODE:
        # group manager
        if manager:
            Loader(path="assistant/manager", key="Group Manager").load()

        # chat via assistant
        if pmbot:
            Loader(path="assistant/pmbot.py").load(log=False)

    # vc bot — NTgCalls (native) + py-tgcalls (MTProto bridge)
    if vcbot and not vcClient._bot:
        try:
            import ntgcalls  # ignore: pylint
            import pytgcalls  # ignore: pylint

            LOGS.info(
                f"VCBot deps OK — ntgcalls {getattr(ntgcalls, '__version__', '?')}, "
                f"pytgcalls {getattr(pytgcalls, '__version__', '?')}"
            )
            if os.path.exists("vcbot"):
                if os.path.exists("vcbot/.git"):
                    subprocess.run("cd vcbot && git pull", shell=True)
                else:
                    rmtree("vcbot")
            if not os.path.exists("vcbot"):
                subprocess.run(
                    "git clone https://github.com/LoopXS/VcBot vcbot", shell=True
                )
            try:
                if not os.path.exists("vcbot/downloads"):
                    subprocess.run("mkdir vcbot/downloads", shell=True)
                    # (Path("vcbot/downloads")).mkdir()
                Loader(path="vcbot", key="VCBot").load(after_load=_after_load)
            except FileNotFoundError as e:
                LOGS.error(f"{e} Skipping VCBot Installation.")
        except ModuleNotFoundError:
            LOGS.error(
                "'ntgcalls' / 'py-tgcalls' not installed!\n"
                "Install with: pip install 'ntgcalls>=3' 'py-tgcalls>=3'\n"
                "Skipping loading of VCBOT."
    )
