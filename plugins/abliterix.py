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

import asyncio
import contextlib
import os
import re
import shutil
import time

from telethon import Button

from . import _abliterix_core as core
from . import LOGS, callback, get_help, get_string, heartless_bot, heartless_cmd

__doc__ = get_help("abliterix")

_WORKDIR = os.environ.get("ABLITERIX_WORKDIR", "./abliterix_jobs")
_BINARY = os.environ.get("ABLITERIX_BIN", "abliterix")
_MIN_FREE_GB = float(os.environ.get("ABLITERIX_MIN_FREE_GB", "40"))
_POLL_SECONDS = float(os.environ.get("ABLITERIX_POLL_SECONDS", "20"))
_KILL_GRACE = float(os.environ.get("ABLITERIX_KILL_GRACE", "20"))
_MAX_RUNTIME = os.environ.get("ABLITERIX_MAX_RUNTIME")
_MAX_RUNTIME = float(_MAX_RUNTIME) if _MAX_RUNTIME else None
_ALLOWED_FLAGS = tuple(
    flag.strip()
    for flag in os.environ.get(
        "ABLITERIX_ALLOWED_FLAGS", ",".join(core.DEFAULT_ALLOWED_FLAGS)
    ).split(",")
    if flag.strip()
)

_STORE = None
_WORKER_TASK = None
_ADOPTED = set()


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


async def _terminate(pid):
    """Stop a process group off the event loop (``terminate_tree`` sleeps)."""
    if pid:
        await asyncio.to_thread(core.terminate_tree, pid, _KILL_GRACE)


async def _cancel(e, rest):
    job_id = rest.split()[0] if rest.split() else ""
    if not job_id:
        await e.reply(_render("abliterix_help"))
        return
    job = _store().get(job_id)
    if job is None:
        await e.reply(_render("abliterix_no_job", id=job_id))
        return
    if job.state not in core.ACTIVE_STATES:
        await e.reply(_render("abliterix_canceled", id=job_id))
        return
    # Mark the job canceled *before* signalling the process: the worker may
    # observe the child exiting at any moment and must not then stamp the job
    # ``failed`` over the user's cancellation.
    pid = job.pid if job.state == "running" else None
    core.transition(job, "canceled", now=time.time())
    _store().save()
    await e.reply(_render("abliterix_cancel_ok", id=job_id))
    if pid:
        await _terminate(pid)


async def _rm(e, rest):
    tokens = rest.split()
    if not tokens:
        await e.reply(_render("abliterix_help"))
        return
    job_id = tokens[0]
    purge = "--purge" in tokens[1:]
    job = _store().get(job_id)
    if job is None:
        await e.reply(_render("abliterix_no_job", id=job_id))
        return
    if job.state in core.ACTIVE_STATES:
        await e.reply(_render("abliterix_rm_active", id=job_id))
        return
    if purge:
        buttons = [
            [
                Button.inline(
                    _render("abliterix_purge_btn_yes"),
                    f"axpurge_yes_{job_id}".encode(),
                ),
                Button.inline(
                    _render("abliterix_purge_btn_no"),
                    f"axpurge_no_{job_id}".encode(),
                ),
            ]
        ]
        await e.reply(_render("abliterix_purge_confirm", id=job_id), buttons=buttons)
        return
    _store().remove(job_id)
    _store().save()
    await e.reply(_render("abliterix_rm_ok", id=job_id))


@callback(re.compile(r"axpurge_(yes|no)_(.+)"), owner=True)
async def _purge_cb(e):
    data = e.data.decode() if isinstance(e.data, bytes) else str(e.data)
    match = re.match(r"axpurge_(yes|no)_(.+)", data)
    if not match:
        return
    await e.answer()
    action, job_id = match.group(1), match.group(2)
    job = _store().get(job_id)
    if action == "no" or job is None:
        await e.edit(_render("abliterix_purge_cancel", id=job_id))
        return
    if job.workdir:
        shutil.rmtree(job.workdir, ignore_errors=True)
    _store().remove(job_id)
    _store().save()
    await e.edit(_render("abliterix_purge_done", id=job_id))


@heartless_cmd(pattern="abliterix( (.*)|$)", owner_only=True)
async def abliterix_cmd(e):
    _ensure_adopted()
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
    elif sub == "cancel":
        await _cancel(e, rest)
    elif sub == "rm":
        await _rm(e, rest)
    else:
        await e.reply(_render("abliterix_unknown_sub"))


async def _spawn(spec):
    """Launch one abliterix run, appending both streams to its log file."""
    handle = open(spec.log_path, "ab")
    try:
        return await asyncio.create_subprocess_exec(
            *spec.argv,
            cwd=spec.cwd,
            env=spec.env,
            stdout=handle,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )
    finally:
        handle.close()


async def _run_job(job):
    """Run one job to completion and return the child's exit code."""
    os.makedirs(job.workdir, exist_ok=True)
    spec = core.build_process_spec(
        _BINARY, job.model, job.workdir, job.extra_flags, os.environ
    )
    process = await _spawn(spec)
    job.pid = process.pid
    _store().save()
    if job.state != "running":
        # Cancelled while we were spawning: stop the fresh process group now.
        await _terminate(process.pid)
    monitor = asyncio.ensure_future(_monitor(job))
    try:
        if _MAX_RUNTIME:
            try:
                code = await asyncio.wait_for(process.wait(), timeout=_MAX_RUNTIME)
            except asyncio.TimeoutError:
                await _terminate(process.pid)
                with contextlib.suppress(Exception):
                    await process.wait()
                raise RuntimeError(
                    f"exceeded ABLITERIX_MAX_RUNTIME ({int(_MAX_RUNTIME)}s)"
                )
        else:
            code = await process.wait()
    finally:
        job.pid = None
        monitor.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await monitor
    return code


def _refresh_progress(job):
    """Update ``job``'s phase/trials/last-line from its run log."""
    if not job.workdir:
        return
    try:
        with open(
            os.path.join(job.workdir, "run.log"), encoding="utf-8", errors="replace"
        ) as handle:
            text = handle.read()
    except OSError:
        return
    job.phase = core.detect_phase(text)
    job.trials_done = core.count_trials(text)
    job.last_line = core.last_line(text)


async def _safe_edit(client, job, text):
    """Edit the job's status message, ignoring any Telegram error."""
    if not job.chat_id or not job.status_message_id:
        return
    try:
        await client.edit_message(job.chat_id, job.status_message_id, text)
    except Exception as err:  # noqa: BLE001 - progress edits are best-effort
        LOGS.info(f"abliterix: status edit failed for {job.id}: {err}")


async def _monitor(job, client=None, interval=None, stop=None):
    """Refresh the status message while ``stop()`` (default: terminal) is false."""
    client = client or heartless_bot
    interval = _POLL_SECONDS if interval is None else interval
    stop = stop or job.is_terminal
    while not stop():
        _refresh_progress(job)
        await _safe_edit(client, job, _status_text(job))
        await asyncio.sleep(interval)


def _find_manifest(out_dir):
    """Locate the reproduce.json manifest under a job's output directory."""
    if not out_dir or not os.path.isdir(out_dir):
        return None
    preferred = os.path.join(out_dir, "reproduce", "reproduce.json")
    if os.path.isfile(preferred):
        return preferred
    for root, _dirs, files in os.walk(out_dir):
        if "reproduce.json" in files:
            return os.path.join(root, "reproduce.json")
    return None


async def _deliver(job, client=None):
    """Report a finished job and attach its manifest when there is one."""
    client = client or heartless_bot
    if job.state == "succeeded":
        await _safe_edit(
            client, job, _render("abliterix_done_ok", id=job.id, path=job.out_dir)
        )
        manifest = _find_manifest(job.out_dir)
        if manifest and job.chat_id:
            try:
                await client.send_file(job.chat_id, manifest)
            except Exception as err:  # noqa: BLE001 - delivery is best-effort
                LOGS.info(f"abliterix: manifest delivery failed for {job.id}: {err}")
    elif job.state == "canceled":
        await _safe_edit(client, job, _render("abliterix_canceled_note", id=job.id))
    elif job.state == "lost":
        await _safe_edit(client, job, _render("abliterix_lost_note", id=job.id))
    else:
        tail = ""
        if job.workdir:
            try:
                with open(
                    os.path.join(job.workdir, "run.log"),
                    encoding="utf-8",
                    errors="replace",
                ) as handle:
                    tail = core.tail_lines(handle.read(), 40)
            except OSError:
                tail = ""
        text = _render("abliterix_done_failed", id=job.id, code=job.returncode)
        await _safe_edit(client, job, f"{text}\n\n{tail}" if tail else text)


async def _worker_loop():
    """Drain the queue one job at a time, newest work last."""
    global _WORKER_TASK
    try:
        while True:
            job = _store().next_queued()
            if job is None:
                break
            try:
                core.transition(job, "running", now=time.time())
            except ValueError:
                _store().save()
                continue
            _store().save()
            try:
                code = await _run_job(job)
                if job.state == "running":
                    core.transition(
                        job,
                        "succeeded" if code == 0 else "failed",
                        now=time.time(),
                        returncode=code,
                    )
            except Exception as err:  # noqa: BLE001 - record any failure
                LOGS.exception(err)
                if job.state == "running":
                    core.transition(job, "failed", now=time.time(), error=str(err))
            _store().save()
            try:
                await _deliver(job)
            except Exception as err:  # noqa: BLE001 - delivery is best-effort
                LOGS.exception(err)
    finally:
        _WORKER_TASK = None


def _ensure_worker():
    """Start the worker if it is not already running."""
    global _WORKER_TASK
    if _WORKER_TASK is None or _WORKER_TASK.done():
        _WORKER_TASK = asyncio.ensure_future(_worker_loop())


async def _enqueue(e, model, extra_tokens):
    """Validate, preflight and persist a new job; reply with the outcome."""
    if not core.is_valid_model_id(model):
        await e.reply(_render("abliterix_bad_model"))
        return None
    flags, error = core.parse_extra_flags(extra_tokens, _ALLOWED_FLAGS)
    if error:
        await e.reply(_render(error))
        return None
    store = _store()
    active = store.find_active(model)
    if active is not None:
        await e.reply(_render("abliterix_duplicate", id=active.id))
        return None
    problem = _preflight()
    if problem:
        await e.reply(_preflight_message(problem))
        return None

    job_id = core.new_job_id([job.id for job in store.all()])
    workdir = os.path.join(_WORKDIR, job_id)
    os.makedirs(workdir, exist_ok=True)
    job = core.Job(
        id=job_id,
        model=model,
        state="queued",
        extra_flags=flags,
        created_at=time.time(),
        chat_id=e.chat_id,
        workdir=workdir,
        out_dir=os.path.join(workdir, "out"),
    )
    store.add(job)
    store.save()
    message = await e.reply(_render("abliterix_queued", id=job_id, model=model))
    if message is not None and getattr(message, "id", None):
        job.status_message_id = message.id
        store.save()
    _ensure_worker()
    return job


@heartless_cmd(pattern="abliterate( (.*)|$)", owner_only=True)
async def abliterate_cmd(e):
    arg = (e.pattern_match.group(1) or "").strip()
    tokens = arg.split()
    if not tokens:
        await e.reply(_render("abliterix_help"))
        return
    await _enqueue(e, tokens[0], tokens[1:])


async def _watch_adopted(job):
    """Follow a job whose process survived a restart.

    We did not spawn this child, so its exit code is unknowable; when the pid
    disappears the job is resolved by whether it produced a manifest
    (``succeeded``) or not (``lost``).  This keeps such a job from sticking as
    ``running`` forever and blocking a re-run of the same model.
    """
    try:
        while job.pid and core.is_pid_alive(job.pid):
            _refresh_progress(job)
            await _safe_edit(heartless_bot, job, _status_text(job))
            await asyncio.sleep(_POLL_SECONDS)
    finally:
        _ADOPTED.discard(job.id)
    state = "succeeded" if _find_manifest(job.out_dir) else "lost"
    try:
        core.transition(job, state, now=time.time())
    except ValueError:
        return
    _store().save()
    try:
        await _deliver(job)
    except Exception as err:  # noqa: BLE001 - delivery is best-effort
        LOGS.exception(err)


def _ensure_adopted():
    """Start watchers for live ``running`` jobs left over by a restart."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    for job in _store().all():
        if (
            job.state == "running"
            and job.pid
            and job.id not in _ADOPTED
            and core.is_pid_alive(job.pid)
        ):
            _ADOPTED.add(job.id)
            asyncio.ensure_future(_watch_adopted(job))


def _reap_on_load():
    """Resolve jobs left ``running`` by a restart.

    A job whose pid is gone is stale and marked ``lost``; a job whose process
    is still alive is re-adopted for monitoring (spec: never silently drop a
    run, never let a stale ``running`` block a model forever).
    """
    store = _store()
    changed = core.reap(list(store.all()))
    if changed:
        store.save()
    _ensure_adopted()
    return changed


try:
    _reap_on_load()
except Exception as _err:  # noqa: BLE001 - never block plugin loading
    LOGS.exception(_err)
