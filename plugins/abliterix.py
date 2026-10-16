"""Abliterix job runner — owner/sudo Telegram control for the abliterix CLI.

Abliterix (https://github.com/wuwangzhang1216/abliterix) removes refusal
behaviour from a model's weights and exports the result.  It pulls in torch
and transformers, so it is **never** installed into Megatron's environment:
this plugin launches it as a separate headless subprocess from its own venv.

All scheduling, persistence, validation and process logic lives in the
framework-free ``_abliterix_core`` module; this file is only the Telethon
glue (commands, the single-job worker, progress edits and result delivery).

Configuration (environment variables, read at import):

* ``ABLITERIX_BIN``         — abliterix executable (default ``abliterix``)
* ``ABLITERIX_WORKDIR``     — job directory root (default ``./abliterix_jobs``)
* ``ABLITERIX_MIN_FREE_GB`` — free-space floor before a job may start
* ``ABLITERIX_POLL_SECONDS``— worker/monitor cadence
* ``ABLITERIX_KILL_GRACE``  — SIGTERM-to-SIGKILL grace period
* ``ABLITERIX_ALLOWED_FLAGS`` — comma-separated extra-flag allowlist
* ``ABLITERIX_MAX_RUNTIME`` — optional hard per-job time limit, in seconds
"""

import os
import shutil
import time

from . import _abliterix_core as core
from . import get_help, get_string, heartless_cmd

__doc__ = get_help("abliterix")

_WORKDIR = os.environ.get("ABLITERIX_WORKDIR", "./abliterix_jobs")
_BINARY = os.environ.get("ABLITERIX_BIN", "abliterix")
_MIN_FREE_GB = float(os.environ.get("ABLITERIX_MIN_FREE_GB", "40"))
_POLL_SECONDS = float(os.environ.get("ABLITERIX_POLL_SECONDS", "20"))
_KILL_GRACE = float(os.environ.get("ABLITERIX_KILL_GRACE", "20"))
_ALLOWED_FLAGS = tuple(
    flag.strip()
    for flag in os.environ.get(
        "ABLITERIX_ALLOWED_FLAGS", ",".join(core.DEFAULT_ALLOWED_FLAGS)
    ).split(",")
    if flag.strip()
)

_STORE = None


def _render(key, **fields):
    text = get_string(key)
    if not text:
        text = key
    return text.format(**fields) if fields else text


def _store():
    global _STORE
    if _STORE is None:
        _STORE = core.JobStore(_WORKDIR)
        _STORE.load()
    return _STORE


def _binary_ok():
    if os.path.sep in _BINARY:
        return os.path.isfile(_BINARY) and os.access(_BINARY, os.X_OK)
    return shutil.which(_BINARY) is not None


def _free_gb(path):
    for candidate in (path, os.path.dirname(path) or ".", "."):
        try:
            return shutil.disk_usage(candidate).free / (1024**3)
        except OSError:
            continue
    return None


def _preflight():
    """Return the string key of the first failed precondition, or ``None``."""
    if not _binary_ok():
        return "abliterix_no_binary"
    if shutil.which("nvidia-smi") is None:
        return "abliterix_no_gpu"
    free = _free_gb(_WORKDIR)
    if free is not None and free < _MIN_FREE_GB:
        return "abliterix_low_disk"
    return None


def _preflight_message(key):
    if key == "abliterix_no_binary":
        return _render(key, bin=_BINARY)
    if key == "abliterix_low_disk":
        return _render(key, gb=int(_MIN_FREE_GB))
    return _render(key)


def _humanize(seconds):
    seconds = int(max(0, seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def _status_text(job):
    return _render(
        "abliterix_status",
        id=job.id,
        model=job.model,
        state=job.state,
        elapsed=_humanize(job.elapsed(time.time())),
        phase=job.phase or "-",
        trials=job.trials_done,
        last=job.last_line or "...",
    )


def _list_text():
    jobs = sorted(_store().all(), key=lambda job: job.created_at)
    if not jobs:
        return _render("abliterix_list_empty")
    lines = [_render("abliterix_list_header")]
    for job in jobs:
        lines.append(
            _render(
                "abliterix_list_item",
                id=job.id,
                state=job.state,
                model=job.model,
                elapsed=_humanize(job.elapsed(time.time())),
            )
        )
    return "\n".join(lines)


def _log_text(rest):
    parts = rest.split()
    if not parts:
        return None
    job_id = parts[0]
    lines = 40
    if len(parts) > 1:
        try:
            lines = max(1, int(parts[1]))
        except ValueError:
            lines = 40
    job = _store().get(job_id)
    if job is None:
        return _render("abliterix_no_job", id=job_id)
    body = ""
    if job.workdir:
        try:
            with open(
                os.path.join(job.workdir, "run.log"), encoding="utf-8", errors="replace"
            ) as handle:
                body = core.tail_lines(handle.read(), lines)
        except OSError:
            body = ""
    header = _render("abliterix_log_header", id=job_id, n=lines)
    return f"{header}\n{body or '(no output yet)'}"


@heartless_cmd(pattern="abliterix( (.*)|$)", owner_only=True)
async def abliterix_cmd(e):
    arg = (e.pattern_match.group(1) or "").strip()
    sub, _, rest = arg.partition(" ")
    sub = sub.lower()
    rest = rest.strip()

    if sub in ("", "help"):
        await e.reply(_render("abliterix_help"))
    elif sub == "list":
        await e.reply(_list_text())
    elif sub == "status":
        if not rest:
            await e.reply(_render("abliterix_help"))
        else:
            job_id = rest.split()[0]
            job = _store().get(job_id)
            if job is None:
                await e.reply(_render("abliterix_no_job", id=job_id))
            else:
                await e.reply(_status_text(job))
    elif sub == "log":
        text = _log_text(rest)
        await e.reply(text if text is not None else _render("abliterix_help"))
    else:
        await e.reply(_render("abliterix_unknown_sub"))
