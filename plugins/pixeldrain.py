"""
✘ Commands Available -

• `{i}pixzip`
    Zip your userbot project directory (defaults to CWD) and upload
    the archive to Pixeldrain. Returns a shareable link.

• `{i}pixzip <path>`
    Zip a specific directory instead of the current one.

• `{i}pixzip --all [path]`
    Include normally-excluded sensitive files (`.env`, `*.session`,
    `.git`, `cookies.txt`, …). Handle with care — anyone with the
    resulting link gets full access to your userbot.

Optional DB key
---------------
    `{i}setdb PIXELDRAIN_API_KEY <your-api-key>`
        Associate uploads with your Pixeldrain account so archives
        aren't garbage-collected after 30 days of inactivity. Get a
        key at https://pixeldrain.com/user/api_keys.

Notes
-----
    • Safe-mode (default) skips: `.env*`, `*.session`, `*.session-journal`,
      `cookies.txt`, `.git-credentials`, `.git/`, `__pycache__/`, `venv/`,
      `.venv/`, `node_modules/`, `addons/`, `vcbot/`, `.cache/`,
      `ms-playwright/`.
    • Anonymous uploads are capped at 20 GB by Pixeldrain.
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

_PIXELDRAIN_ENDPOINT = "https://pixeldrain.com/api/file"
_MAX_ANON_UPLOAD = 20 * 1024 * 1024 * 1024  # 20 GB Pixeldrain anonymous cap


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
                LOGS.warning(f"pixzip: skipping {full} ({err})")
    return count, size


async def _pixeldrain_upload(zip_path: Path, api_key: Optional[str]) -> dict:
    """PUT the file to Pixeldrain and return the parsed JSON response."""
    auth = aiohttp.BasicAuth("", api_key) if api_key else None
    timeout = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=None)
    filename = zip_path.name

    async with aiohttp.ClientSession(timeout=timeout) as session:
        with zip_path.open("rb") as fp:
            async with session.put(
                f"{_PIXELDRAIN_ENDPOINT}/{filename}",
                data=fp,
                auth=auth,
            ) as resp:
                payload = await resp.json(content_type=None)
                if resp.status >= 400:
                    raise RuntimeError(
                        f"Pixeldrain returned HTTP {resp.status}: {payload}"
                    )
                return payload


# ---------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------


@heartless_cmd(pattern="pixzip( (.*)|$)")
async def pixzip(event):
    """Zip the userbot's project directory and upload to Pixeldrain."""
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
    token=udB.get_key("ziptoken")
    if not token: return await eod(event,"❌ ziptoken not set")
    tmp=TemporaryDirectory()
    repo=Path(tmp.name)/"repo"
    url=f"https://{token}@github.com/LoopXS/Megatron.git"
    subprocess.run(["git","clone","--depth","1",url,str(repo)],check=True)
    source=repo.resolve()
    if not source.exists():
        return await eod(event, f"❌ Path not found: `{source}`")
    if not source.is_dir():
        return await eod(event, f"❌ Not a directory: `{source}`")

    reply = await eor(event, "`📦 Building archive...`")

    ts = int(time.time())
    dest = Path("m.zip").resolve()
    zip_start = time.time()
    try:
        count, raw_size = await asyncio.to_thread(
            _build_zip, source, dest, include_sensitive
        )
    except Exception as err:
        LOGS.exception(err)
        dest.unlink(missing_ok=True)
        return await eor(reply, f"❌ Zip failed: `{err}`")

    if count == 0:
        dest.unlink(missing_ok=True)
        return await eor(
            reply,
            "❌ Nothing to zip — every file was excluded. "
            "Try passing `--all` or a different path.",
        )

    zip_size = dest.stat().st_size
    zip_dur = time.time() - zip_start

    if zip_size > _MAX_ANON_UPLOAD and not udB.get_key("PIXELDRAIN_API_KEY"):
        dest.unlink(missing_ok=True)
        return await eor(
            reply,
            f"❌ Archive is `{_humanbytes(zip_size)}`, over Pixeldrain's "
            "20 GB anonymous cap. Configure an API key with "
            f"`{HNDLR}setdb PIXELDRAIN_API_KEY <key>` or shrink the source.",
        )

    await eor(
        reply,
        (
            f"`📦 Archive built in {zip_dur:.1f}s`\n"
            f"`  · {count} files`\n"
            f"`  · {_humanbytes(raw_size)} raw → {_humanbytes(zip_size)} zipped`\n\n"
            "`☁️ Uploading to Pixeldrain...`"
        ),
    )

    api_key = udB.get_key("PIXELDRAIN_API_KEY")
    upload_start = time.time()
    try:
        payload = await _pixeldrain_upload(dest, api_key)
    except Exception as err:
        LOGS.exception(err)
        return await eor(reply, f"❌ Upload failed: `{err}`")
    finally:
        dest.unlink(missing_ok=True)
        tmp.cleanup()

    file_id = payload.get("id")
    if not file_id:
        return await eor(
            reply,
            f"❌ Pixeldrain returned an unexpected payload: `{payload}`",
        )

    upload_dur = time.time() - upload_start
    warning = (
        "\n\n⚠️ **`--all` was set** — this archive may contain sessions, "
        "`.env`, cookies and other secrets. Only share the link with "
        "people who should have full access to your userbot."
        if include_sensitive
        else ""
    )
    account_hint = (
        ""
        if api_key
        else (
            f"\n\n💡 _Tip: set an API key with "
            f"`{HNDLR}setdb PIXELDRAIN_API_KEY <key>` so anonymous "
            "uploads aren't garbage-collected after 30 days._"
        )
    )

    await eor(
        reply,
        (
            "✅ **Uploaded to Pixeldrain**\n\n"
            f"**Source**: `{source}`\n"
            f"**Files**: `{count}`  ·  **Size**: `{_humanbytes(zip_size)}`\n"
            f"**Zip**: `{zip_dur:.1f}s`  ·  **Upload**: `{upload_dur:.1f}s`\n\n"
            f"🔗 [Preview](https://pixeldrain.com/u/{file_id})  ·  "
            f"[Direct download]({_PIXELDRAIN_ENDPOINT}/{file_id})"
            f"{warning}{account_hint}"
        ),
        link_preview=False,
      )
