"""
✘ Commands Available

• `{i}zip [reply to file/folder] [-n NAME] [-p PASSWORD] [-f FORMAT]`
    Create an archive.
    `-n NAME`  custom archive name (without extension)
    `-p PASSWORD`  password-protect the archive (AES)
    `-f FORMAT`  `zip` (default), `tar` or `gz` (tar.gz)
    A bare argument still sets the password (backwards compatible).
    Without a reply, the argument is treated as a local file/folder path.

• `{i}unzip [reply to archive] [-p PASSWORD] [-l]`
    Extract an archive (`zip`, `tar`, `tar.gz` are auto-detected).
    `-p PASSWORD`  password for protected archives
    `-l`  list the archive contents instead of extracting

• `{i}azip [reply to file]`
    Add a file to the batch folder.

• `{i}dozip [-n NAME] [-p PASSWORD] [-f FORMAT]`
    Archive the whole batch folder gathered via `{i}azip`.
"""

import os
import shutil
import shlex
import tarfile
import tempfile
import time
import zipfile

from . import (
    HNDLR,
    ULTConfig,
    downloader,
    get_all_files,
    get_pstring,
    get_string,
    heartless_cmd,
    humanbytes,
    uploader,
)

try:
    import pyzipper
except ImportError:
    pyzipper = None

# Directory used to stage files added via `{i}azip` before `{i}dozip`.
_BATCH_DIR = "zip_batch"

_FORMATS = ("zip", "tar", "gz")
_FORMAT_EXT = {"zip": ".zip", "tar": ".tar", "gz": ".tar.gz"}

# Long-form option name for each accepted short/long flag.
_FLAG_ALIASES = {
    "n": "name",
    "name": "name",
    "p": "password",
    "password": "password",
    "f": "format",
    "format": "format",
    "l": "list",
    "list": "list",
}


def _parse_args(text):
    """Parse ``-n value``, ``-n=value``, ``--name value``, ``--name=value``
    and boolean flags (``-l`` / ``--list``) from a command argument string.

    Returns ``(options, positional)``.
    """
    options, positional = {}, []
    if not text:
        return options, positional
    try:
        tokens = shlex.split(text)
    except ValueError:
        tokens = text.split()
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token.startswith("-"):
            if "=" in token:
                key, _, value = token.partition("=")
                key = key.lstrip("-").lower()
                if key in _FLAG_ALIASES:
                    options[_FLAG_ALIASES[key]] = value
                i += 1
                continue
            key = token.lstrip("-").lower()
            if key in ("l", "list"):
                options["list"] = True
                i += 1
                continue
            if key in _FLAG_ALIASES and i + 1 < len(tokens):
                options[_FLAG_ALIASES[key]] = tokens[i + 1]
                i += 2
                continue
        positional.append(token)
        i += 1
    return options, positional


def _archive_name(name, source, fmt):
    """Build the final archive path, deriving a name when none is given."""
    if not name:
        if os.path.isfile(source):
            name = os.path.splitext(os.path.basename(source))[0]
        else:
            name = os.path.basename(os.path.abspath(source)) or "archive"
    for ext in (".tar.gz", ".tgz", ".zip", ".tar", ".gz"):
        if name.lower().endswith(ext):
            name = name[: -len(ext)]
            break
    return name + _FORMAT_EXT[fmt]


def _add_to_zip(zf, source):
    """Add a file or a whole directory tree to an open ``ZipFile``."""
    if os.path.isfile(source):
        zf.write(source, os.path.basename(source))
        return
    for root, _dirs, files in os.walk(source):
        for fname in files:
            full = os.path.join(root, fname)
            zf.write(full, os.path.relpath(full, source))


def _make_zip(source, archive_path, password=None):
    """Create a ``.zip`` archive, AES-encrypted when a password is set."""
    if password:
        if pyzipper is None:
            raise RuntimeError(
                "Password-protected archives require 'pyzipper'.\n"
                "Install it with `pip install pyzipper`"
            )
        with pyzipper.AESZipFile(
            archive_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            encryption=pyzipper.WZ_AES,
        ) as zf:
            zf.setpassword(password.encode())
            _add_to_zip(zf, source)
    else:
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
            _add_to_zip(zf, source)


def _make_tar(source, archive_path, gz=False):
    """Create a ``.tar`` or ``.tar.gz`` archive."""
    with tarfile.open(archive_path, "w:gz" if gz else "w") as tf:
        if os.path.isfile(source):
            tf.add(source, arcname=os.path.basename(source))
        else:
            for root, _dirs, files in os.walk(source):
                for fname in files:
                    full = os.path.join(root, fname)
                    tf.add(full, arcname=os.path.relpath(full, source))


def _detect_format(path):
    """Detect the archive type from the extension or magic bytes."""
    lower = path.lower()
    if lower.endswith(".zip"):
        return "zip"
    if lower.endswith((".tar", ".tar.gz", ".tgz", ".gz")):
        return "tar"
    with open(path, "rb") as fh:
        head = fh.read(262)
    if head[:2] == b"PK":
        return "zip"
    if len(head) > 262 and head[257:262] == b"ustar":
        return "tar"
    return "zip"


def _open_zip(path):
    """Return the right ``ZipFile`` class, preferring AES support."""
    return (pyzipper.AESZipFile if pyzipper is not None else zipfile.ZipFile)(path)


def _extract_zip(path, dest, password=None):
    try:
        with _open_zip(path) as zf:
            if password:
                zf.setpassword(password.encode())
            zf.extractall(dest)
    except (RuntimeError, NotImplementedError, zipfile.BadZipFile) as er:
        hint = ""
        if pyzipper is None:
            hint = "\nAES-encrypted archives need 'pyzipper' (`pip install pyzipper`)."
        raise RuntimeError(f"Failed to extract: {er}.{hint}")


def _extract_tar(path, dest):
    with tarfile.open(path) as tf:
        try:
            tf.extractall(dest, filter="data")
        except TypeError:
            tf.extractall(dest)


def _extract_archive(path, dest, password=None):
    fmt = _detect_format(path)
    if fmt == "zip":
        _extract_zip(path, dest, password)
    else:
        _extract_tar(path, dest)


def _list_archive(path, password=None):
    """Return ``(listing_text, item_count)`` for an archive."""
    fmt = _detect_format(path)
    lines = []
    if fmt == "zip":
        with _open_zip(path) as zf:
            if password:
                zf.setpassword(password.encode())
            for info in zf.infolist():
                if info.is_dir():
                    continue
                lines.append(
                    f"{info.filename}  ({humanbytes(info.file_size)}, "
                    f"compressed {humanbytes(info.compress_size)})"
                )
    else:
        with tarfile.open(path) as tf:
            for member in tf.getmembers():
                if member.isfile():
                    lines.append(f"{member.name}  ({humanbytes(member.size)})")
    return "\n".join(lines), len(lines)


async def _download_reply(reply, xx, t):
    """Download a replied media message and return the local file path."""
    if hasattr(reply.media, "document"):
        safe = os.path.basename(reply.file.name or "file")
        result = await downloader(
            safe, reply.media.document, xx, t, get_pstring("com_5", "load")
        )
        return result.name
    return await reply.download_media()


@heartless_cmd(pattern="zip( (.*)|$)")
async def zipp(event):
    options, positional = _parse_args(event.pattern_match.group(1))
    reply = await event.get_reply_message()
    t = time.time()

    password = options.get("password")
    name = options.get("name")
    fmt = (options.get("format") or "zip").lower()

    if fmt not in _FORMATS:
        await event.eor(f"Unknown format `{fmt}`. Use `zip`, `tar` or `gz`.")
        return

    source = None
    downloaded = False

    # Backwards compatible: a bare argument sets the password when replying,
    # otherwise it is treated as a local file/folder path.
    if positional:
        if reply:
            password = password or positional[0]
        else:
            source = positional[0]

    if reply and getattr(reply, "media", None):
        xx = await event.eor(get_pstring("com_1", "load"))
        source = await _download_reply(reply, xx, t)
        downloaded = True
    else:
        if not source:
            await event.eor(get_string("zip_1"))
            return
        xx = await event.eor(get_pstring("com_1", "load"))

    if not (os.path.isfile(source) or os.path.isdir(source)):
        await xx.edit(f"Source not found: `{source}`")
        return

    archive_path = _archive_name(name, source, fmt)
    try:
        if fmt == "zip":
            _make_zip(source, archive_path, password)
        elif fmt == "tar":
            _make_tar(source, archive_path, gz=False)
        else:
            _make_tar(source, archive_path, gz=True)
    except Exception as er:
        await xx.edit(f"Failed to create archive: `{er}`")
        if downloaded:
            os.remove(source)
        return

    k = time.time()
    uploaded = await uploader(archive_path, archive_path, k, xx, get_pstring("com_6", "load"))
    await event.client.send_file(
        event.chat_id,
        uploaded,
        force_document=True,
        thumb=ULTConfig.thumb,
        caption=f"`{archive_path}`",
        reply_to=reply,
    )
    os.remove(archive_path)
    if downloaded:
        os.remove(source)
    await xx.delete()


@heartless_cmd(pattern="unzip( (.*)|$)")
async def unzipp(event):
    options, positional = _parse_args(event.pattern_match.group(1))
    reply = await event.get_reply_message()
    t = time.time()

    password = options.get("password")
    list_only = bool(options.get("list"))

    archive = None
    downloaded = False

    if positional and not reply:
        archive = positional[0]

    if reply and getattr(reply, "media", None):
        xx = await event.eor(get_pstring("com_1", "load"))
        archive = await _download_reply(reply, xx, t)
        downloaded = True
    else:
        if not archive:
            await event.eor(get_string("zip_1"))
            return
        xx = await event.eor(get_pstring("com_1", "load"))

    if not os.path.isfile(archive):
        await xx.edit(f"Archive not found: `{archive}`")
        return

    try:
        if list_only:
            listing, count = _list_archive(archive, password)
            await xx.edit(
                f"<b>📦 Contents of</b> <code>{os.path.basename(archive)}</code>"
                f" <b>({count} files)</b>\n\n<code>{listing}</code>",
                parse_mode="html",
            )
        else:
            dest = tempfile.mkdtemp(prefix="unzip_")
            _extract_archive(archive, dest, password)
            files = get_all_files(dest)
            if not files:
                await xx.edit("Nothing was extracted from the archive.")
                return
            for path in files:
                k = time.time()
                uploaded = await uploader(
                    path,
                    os.path.relpath(path, dest).replace(os.sep, "_"),
                    k,
                    xx,
                    get_pstring("com_6", "load"),
                )
                await event.client.send_file(
                    event.chat_id,
                    uploaded,
                    force_document=True,
                    thumb=ULTConfig.thumb,
                    caption=f"`{os.path.basename(path)}`",
                )
            shutil.rmtree(dest, ignore_errors=True)
            await xx.delete()
    except Exception as er:
        await xx.edit(f"`{er}`")
    finally:
        if downloaded:
            os.remove(archive)


@heartless_cmd(pattern="(azip|addzip)$")
async def azipp(event):
    reply = await event.get_reply_message()
    t = time.time()
    if not (reply and getattr(reply, "media", None)):
        await event.eor(get_string("zip_1"))
        return
    xx = await event.eor(get_pstring("com_1", "load"))
    os.makedirs(_BATCH_DIR, exist_ok=True)
    if hasattr(reply.media, "document"):
        safe = os.path.basename(reply.file.name or "file")
        result = await downloader(
            os.path.join(_BATCH_DIR, safe),
            reply.media.document,
            xx,
            t,
            get_pstring("com_5", "load"),
        )
        file = result.name
    else:
        file = await reply.download_media(_BATCH_DIR)
    await xx.edit(
        f"✅ Added `{os.path.basename(file)}` to the batch.\n"
        f"Reply to more files to add, then run `{HNDLR}dozip` to archive them all."
    )


@heartless_cmd(pattern="dozip( (.*)|$)")
async def do_zip(event):
    options, _positional = _parse_args(event.pattern_match.group(1))
    password = options.get("password")
    name = options.get("name")
    fmt = (options.get("format") or "zip").lower()

    if not os.path.isdir(_BATCH_DIR):
        await event.eor(get_string("zip_2").format(HNDLR, HNDLR))
        return
    if not get_all_files(_BATCH_DIR):
        await event.eor(
            f"The batch folder is empty. Add files with `{HNDLR}azip` first."
        )
        return

    xx = await event.eor(get_pstring("com_1", "load"))

    if fmt not in _FORMATS:
        await xx.edit(f"Unknown format `{fmt}`. Use `zip`, `tar` or `gz`.")
        return

    archive_path = _archive_name(name, _BATCH_DIR, fmt)
    try:
        if fmt == "zip":
            _make_zip(_BATCH_DIR, archive_path, password)
        elif fmt == "tar":
            _make_tar(_BATCH_DIR, archive_path, gz=False)
        else:
            _make_tar(_BATCH_DIR, archive_path, gz=True)
    except Exception as er:
        await xx.edit(f"Failed to create archive: `{er}`")
        return

    k = time.time()
    uploaded = await uploader(archive_path, archive_path, k, xx, get_pstring("com_6", "load"))
    await event.client.send_file(
        event.chat_id,
        uploaded,
        force_document=True,
        thumb=ULTConfig.thumb,
        caption=f"`{archive_path}`",
    )
    shutil.rmtree(_BATCH_DIR, ignore_errors=True)
    os.remove(archive_path)
    await xx.delete()
