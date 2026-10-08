"""
Megatron - Hugging Face Dataset project backup plugin
Copyright (C) 2026

Commands Available
------------------
• `{i}repzip`
    Zip your userbot project directory (defaults to CWD) and upload
    the archive to a Hugging Face Dataset. Returns a direct download link.

• `{i}repzip <path>`
    Zip a specific directory instead of the current one.

• `{i}repzip --all [path]`
    Include normally-excluded sensitive files (`.env`, `*.session`,
    `.git`, `cookies.txt`, …). Handle with care — anyone with the
    resulting link gets full access to your userbot.

Notes
-----
• Safe-mode (default) skips: `.env*`, `*.session`, `*.session-journal`,
  `cookies.txt`, `.git-credentials`, `.git/`, `__pycache__/`, `venv/`,
  `.venv/`, `node_modules/`, `addons/`, `vcbot/`, `.cache/`,
  `ms-playwright/`.
• Hugging Face credentials are read from udb keys: HF_TOKEN and HF_REPO.
• Each upload deletes all previous Dataset files and leaves exactly one backup.
"""

import asyncio
import os
import shlex
import time
import zipfile
from fnmatch import fnmatch
from pathlib import Path
from typing import Optional

import aiohttp

try:
    from huggingface_hub import HfApi, CommitOperationAdd, CommitOperationDelete
except ImportError:
    HfApi = None
    CommitOperationAdd = None
    CommitOperationDelete = None

from . import HNDLR, LOGS, eod, eor, udB, heartless_cmd


# ---------------------------------------------------------------------
# Exclusion rules
# ---------------------------------------------------------------------

# Directories skipped unconditionally (they either contain no useful
# state or are separately-managed clones).
_ALWAYS_SKIP_DIRS = {
    ".git",
    ".github",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "addons",
    "vcbot",
    ".cache",
    ".pytest_cache",
    ".mypy_cache",
    "ms-playwright",
    ".dockerignore",
}

# Filename globs skipped unconditionally (churny bytecode / temp files).
_ALWAYS_SKIP_FILES = (
    "*.pyc",
    "*.pyo",
    "*.log",
    ".DS_Store",
    "Thumbs.db",
)

# Files that hold credentials — skipped in safe mode (i.e. unless --all).
_SAFE_MODE_SKIP_FILES = (
    ".env",
    ".env.*",
    "*.session",
    "*.session-journal",
    "cookies.txt",
    ".git-credentials",
    "heartless.session",
    "heartless-asst.session",
)

_HF_MAX_UPLOAD = 1 * 1024 * 1024 * 1024  # 1 GB safety cap



# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _matches_any(name: str, patterns) -> bool:
    return any(fnmatch(name, p) for p in patterns)


def _humanbytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} PB"


def _iter_files(root: Path, include_sensitive: bool, self_zip: Path):
    """Yield (absolute_path, arcname) tuples for the zip."""
    skip_file_patterns = list(_ALWAYS_SKIP_FILES)
    if not include_sensitive:
        skip_file_patterns.extend(_SAFE_MODE_SKIP_FILES)

    for base, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in _ALWAYS_SKIP_DIRS]
        for fname in files:
            if _matches_any(fname, skip_file_patterns):
                continue
            full = Path(base) / fname
            # Never include the zip file we're actively writing.
            if full.resolve() == self_zip:
                continue
            arcname = str(full.relative_to(root))
            yield full, arcname


def _build_zip(source: Path, dest: Path, include_sensitive: bool) -> tuple[int, int]:
    """Build the zip on disk. Returns (file_count, uncompressed_bytes)."""
    count = size = 0
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for full, arcname in _iter_files(source, include_sensitive, dest.resolve()):
            try:
                zf.write(full, arcname)
                count += 1
                size += full.stat().st_size
            except OSError as err:
                LOGS.warning(f"repzip: skipping {full} ({err})")
    return count, size


async def _huggingface_upload(zip_path: Path, remote_name: str) -> str:
    """
    Upload the new backup to the configured Hugging Face Dataset and delete
    every previously uploaded file in the same commit, leaving exactly one
    backup file in the repository.
    """
    if HfApi is None:
        raise RuntimeError(
            "huggingface_hub is not installed. Install it with: "
            "pip install -U huggingface_hub"
        )

    token = udB.get_key("HF_TOKEN")
    repo_id = udB.get_key("HF_REPO")

    if not token:
        raise RuntimeError(
            "HF_TOKEN is not set in udb. Save your Hugging Face token first."
        )

    if not repo_id:
        raise RuntimeError(
            "HF_REPO is not set in udb. Save your Dataset repo as "
            "username/dataset-name first."
        )

    token = str(token).strip()
    repo_id = str(repo_id).strip()
    api = HfApi(token=token)

    try:
        existing_files = await asyncio.to_thread(
            api.list_repo_files,
            repo_id=repo_id,
            repo_type="dataset",
            token=token,
        )
    except Exception as err:
        raise RuntimeError(
            f"Could not access Hugging Face dataset `{repo_id}`: {err}"
        ) from err

    # Delete every existing file and add the new backup in ONE commit.
    operations = [
        CommitOperationDelete(path_in_repo=remote)
        for remote in existing_files
        if remote != remote_name
    ]
    operations.append(
        CommitOperationAdd(
            path_in_repo=remote_name,
            path_or_fileobj=str(zip_path),
        )
    )

    try:
        await asyncio.to_thread(
            api.create_commit,
            repo_id=repo_id,
            repo_type="dataset",
            token=token,
            operations=operations,
            commit_message=f"Update backup: {remote_name}",
        )
    except Exception as err:
        raise RuntimeError(
            f"Hugging Face upload/cleanup failed: {err}"
        ) from err

    return (
        f"https://huggingface.co/datasets/"
        f"{repo_id}/resolve/main/{remote_name}"
    )

@heartless_cmd(pattern="repzip( (.*)|$)")
async def repzip(event):
    """Zip the userbot's project directory and upload it to a Hugging Face Dataset."""
    raw_args = (event.pattern_match.group(1) or "").strip()

    include_sensitive = False
    source_arg = ""

    try:
        tokens = shlex.split(raw_args)
    except ValueError as err:
        return await eod(event, f"❌ Could not parse arguments: `{err}`")

    for tok in tokens:
        if tok in ("-a", "--all"):
            include_sensitive = True
        elif source_arg:
            return await eod(event, "❌ Only one path argument is supported.")
        else:
            source_arg = tok

    from tempfile import TemporaryDirectory
    import subprocess

    token = udB.get_key("ziptoken")
    if not token:
        return await eod(event, "❌ ziptoken not set")

    tmp = TemporaryDirectory()
    repo = Path(tmp.name) / "repo"

    try:
        url = f"https://{token}@github.com/LoopXS/Megatron.git"
        subprocess.run(
            ["git", "clone", "--depth", "1", url, str(repo)],
            check=True,
        )
    except Exception as err:
        tmp.cleanup()
        return await eod(event, f"❌ Git clone failed: `{err}`")

    source = repo.resolve()

    if source_arg:
        requested = Path(source_arg).expanduser()
        if not requested.is_absolute():
            requested = source / requested
        source = requested.resolve()

    if not source.exists():
        tmp.cleanup()
        return await eod(event, f"❌ Path not found: `{source}`")

    if not source.is_dir():
        tmp.cleanup()
        return await eod(event, f"❌ Not a directory: `{source}`")

    reply = await eor(event, "`📦 Building archive...`")

    ts = int(time.time())
    dest = Path(f"m_{ts}.zip").resolve()
    zip_start = time.time()

    try:
        count, raw_size = await asyncio.to_thread(
            _build_zip,
            source,
            dest,
            include_sensitive,
        )
    except Exception as err:
        LOGS.exception(err)
        dest.unlink(missing_ok=True)
        tmp.cleanup()
        return await eor(reply, f"❌ Zip failed: `{err}`")

    if count == 0:
        dest.unlink(missing_ok=True)
        tmp.cleanup()
        return await eor(
            reply,
            "❌ Nothing to zip — every file was excluded. "
            "Try passing `--all` or a different path.",
        )

    zip_size = dest.stat().st_size
    zip_dur = time.time() - zip_start

    if zip_size > _HF_MAX_UPLOAD:
        dest.unlink(missing_ok=True)
        tmp.cleanup()
        return await eor(
            reply,
            f"❌ Archive is `{_humanbytes(zip_size)}`, over Hugging Face's "
            "200 MB per-file limit.",
        )

    await eor(
        reply,
        (
            f"`📦 Archive built in {zip_dur:.1f}s`\n"
            f"`  · {count} files`\n"
            f"`  · {_humanbytes(raw_size)} raw → "
            f"{_humanbytes(zip_size)} zipped`\n\n"
            "`☁️ Uploading to Hugging Face...`"
        ),
    )

    upload_start = time.time()

    try:
        direct_url = await _huggingface_upload(dest, f"m_{ts}.zip")
    except Exception as err:
        LOGS.exception(err)
        return await eor(reply, f"❌ Upload failed: `{err}`")
    finally:
        dest.unlink(missing_ok=True)
        tmp.cleanup()

    upload_dur = time.time() - upload_start

    warning = (
        "\n\n⚠️ **`--all` was set** — this archive may contain sessions, "
        "`.env`, cookies and other secrets. Only share the link with "
        "people who should have full access to your userbot."
        if include_sensitive
        else ""
    )

    await eor(
        reply,
        (
            "✅ **Uploaded to Hugging Face Dataset**\n\n"
            f"**Source**: `{source}`\n"
            f"**Files**: `{count}`  ·  "
            f"**Size**: `{_humanbytes(zip_size)}`\n"
            f"**Zip**: `{zip_dur:.1f}s`  ·  "
            f"**Upload**: `{upload_dur:.1f}s`\n\n"
            f"🔗 [Direct download]({direct_url})"
            f"{warning}"
        ),
        link_preview=False,
    )

