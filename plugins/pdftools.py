"""
✘ Commands Available -

• `{i}pdf [pages] <reply to pdf>`
    Send page(s) of a PDF as images.
    Pages: `N`, `A-B`, `A-B,C` or nothing for all pages.
    Large selections (>25 pages) are sent as a single PDF.

• `{i}pdftext [pages] <reply to pdf>`
    Extract text from page(s) into a `.txt` file.
    Same page syntax as `{i}pdf`.

• `{i}trim <range> <reply to pdf>`
    Extract a page range into a separate PDF.
    e.g. `{i}trim 50-200`, `{i}trim 420-500`, `{i}trim 1-3,7,9-12`.

• `{i}pdfinfo <reply to pdf>`
    Show page count, size, dimensions and metadata.

• `{i}pdscan <reply to image>`
    Scan, crop & send an image as a PDF.

• `{i}pdsave <reply to image/pdf>`
    Scan & save a file to the merge queue.

• `{i}pdsend [name]`
    Merge the queued files and send them as one PDF.
"""

import glob
import os
import time

import pypdf
from pypdf import PdfReader, PdfWriter

from CythonX.fns.tools import four_point_transform

from . import (
    HNDLR,
    LOGS,
    ULTConfig,
    check_filename,
    downloader,
    eor,
    get_pstring,
    get_string,
    heartless_cmd,
    humanbytes,
)

try:
    import pypdfium2 as pdfium
except ImportError:
    pdfium = None

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

# Directory holding files queued via `{i}pdsave` and freshly downloaded PDFs.
_PDF_DIR = "pdf"
os.makedirs(_PDF_DIR, exist_ok=True)

# Render pages to images only up to this many pages, then send one PDF.
_MAX_IMAGE_PAGES = 25
_RENDER_DPI = 150


# ------------------------------- helpers -------------------------------- #


def _parse_pages(spec, total):
    """Parse a page spec into a sorted list of 0-based page indices.

    Accepts ``N``, ``A-B``, ``A-B,C`` or an empty string for every page.
    """
    if not spec:
        return list(range(total))
    pages = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            low, _, high = chunk.partition("-")
            low, high = low.strip(), high.strip()
            if not (low.isdigit() and high.isdigit()):
                raise ValueError(f"invalid range: {chunk!r}")
            low, high = int(low), int(high)
        else:
            if not chunk.isdigit():
                raise ValueError(f"invalid page: {chunk!r}")
            low = high = int(chunk)
        if low < 1 or high < 1 or low > total or high > total:
            raise ValueError(f"page {chunk} is out of range (1-{total})")
        if low > high:
            raise ValueError(f"invalid range: {chunk!r} (start > end)")
        pages.extend(range(low - 1, high))
    if not pages:
        raise ValueError("no valid pages given")
    return sorted(set(pages))


async def _get_replied_pdf(event):
    """Make sure the reply is a PDF, download it.

    Returns ``(local_path, reply, xx)`` or ``(None, None, None)``.
    """
    reply = await event.get_reply_message()
    if not (
        reply
        and reply.document
        and reply.document.mime_type == "application/pdf"
    ):
        await eor(event, get_string("pdf_1"))
        return None, None, None
    xx = await event.eor(get_pstring("com_1", "load"))
    filename = os.path.basename(reply.file.name or "document.pdf")
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"
    dest = check_filename(os.path.join(_PDF_DIR, filename))
    result = await downloader(
        dest, reply.document, xx, time.time(), f"Downloading {filename}..."
    )
    return result.name, reply, xx


async def _get_replied_image(event):
    """Make sure the reply is an image, download it.

    Returns ``(local_path, reply, xx)`` or ``(None, None, None)``.
    """
    reply = await event.get_reply_message()
    if not (reply and reply.media):
        await eor(event, get_string("pdf_2"))
        return None, None, None
    name = (reply.file.name or "").lower()
    is_image = reply.photo or name.endswith(
        (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")
    )
    if not is_image:
        await eor(event, get_string("pdf_2"))
        return None, None, None
    xx = await event.eor(get_pstring("com_1", "load"))
    path = await reply.download_media()
    return path, reply, xx


def _extract_pages_to_pdf(path, pages, out=None):
    """Create a new PDF holding only the given 0-based page indices."""
    reader = PdfReader(path)
    writer = PdfWriter()
    for index in pages:
        writer.add_page(reader.pages[index])
    if out is None:
        out = check_filename("extracted.pdf")
    with open(out, "wb") as fh:
        writer.write(fh)
    return out


def _render_page(doc, index, base):
    """Render one page of an open pdfium document to a PNG file."""
    bitmap = doc[index].render(scale=_RENDER_DPI / 72)
    out = f"{base}_p{index + 1}.png"
    bitmap.to_pil().save(out)
    return out


def _scan_image(path):
    """Convert an image to a PDF, enhancing it when OpenCV is available."""
    out = check_filename("scanned.pdf")
    if cv2 is None or np is None:
        if Image is None:
            raise RuntimeError(
                "Pillow is required to scan images (`pip install Pillow`)"
            )
        with Image.open(path) as image:
            image.convert("RGB").save(out)
        return out

    image = cv2.imread(path)
    if image is None:
        if Image is None:
            raise RuntimeError(
                "Unsupported image format and Pillow is not installed."
            )
        with Image.open(path) as im:
            im.convert("RGB").save(out)
        return out

    original = image.copy()
    height, width = image.shape[:2]
    ratio = height / 500.0
    scale = 500.0 / height
    resized = cv2.resize(
        image, (int(width * scale), 500), interpolation=cv2.INTER_AREA
    )
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blurred, 50, 200, apertureSize=3)
    contours, _ = cv2.findContours(
        edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    processed = None
    if contours:
        hull = cv2.convexHull(max(contours, key=cv2.contourArea))
        polygon = cv2.approxPolyDP(
            hull, 0.01 * cv2.arcLength(hull, True), False
        )
        if len(polygon) == 4:
            cropped = four_point_transform(
                original, polygon.reshape(4, 2) * ratio
            )
            grayed = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)
            processed = cv2.adaptiveThreshold(
                grayed,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                11,
                10,
            )
    if processed is None:
        processed = cv2.detailEnhance(original, sigma_s=10, sigma_r=0.15)

    tmp = "scan_tmp.png"
    cv2.imwrite(tmp, processed)
    if Image is not None:
        with Image.open(tmp) as im:
            im.convert("RGB").save(out)
        os.remove(tmp)
    else:
        # No Pillow: let OpenCV write the PDF directly.
        if not cv2.imwrite(out, processed):
            raise RuntimeError("Failed to write the scanned PDF.")
    return out


# ------------------------------ commands -------------------------------- #


@heartless_cmd(pattern="pdf( (.*)|$)")
async def pdfseimg(event):
    spec = (event.pattern_match.group(1) or "").strip()
    path, reply, xx = await _get_replied_pdf(event)
    if not path:
        return
    try:
        total = len(PdfReader(path).pages)
        try:
            pages = _parse_pages(spec, total)
        except ValueError as er:
            await xx.edit(f"`{er}`")
            return

        base = os.path.splitext(os.path.basename(path))[0]
        if pdfium is not None and len(pages) <= _MAX_IMAGE_PAGES:
            doc = pdfium.PdfDocument(path)
            try:
                await xx.edit(get_pstring("com_6", "load"))
                for index in pages:
                    image = _render_page(doc, index, base)
                    try:
                        await event.client.send_file(
                            event.chat_id, image, reply_to=reply
                        )
                    finally:
                        os.remove(image)
            finally:
                doc.close()
        else:
            if pdfium is None:
                LOGS.info(
                    f"{__file__}: 'pypdfium2' not found, "
                    "sending pages as a PDF instead of images."
                )
            await xx.edit(get_pstring("com_6", "load"))
            out = _extract_pages_to_pdf(path, pages)
            try:
                await event.client.send_file(
                    event.chat_id,
                    out,
                    force_document=True,
                    thumb=ULTConfig.thumb,
                    caption=f"`{os.path.basename(out)}`",
                    reply_to=reply,
                )
            finally:
                os.remove(out)
    finally:
        os.remove(path)
        await xx.delete()


@heartless_cmd(pattern="pdftext( (.*)|$)")
async def pdfsetxt(event):
    spec = (event.pattern_match.group(1) or "").strip()
    path, reply, xx = await _get_replied_pdf(event)
    if not path:
        return
    try:
        reader = PdfReader(path)
        total = len(reader.pages)
        try:
            pages = _parse_pages(spec, total)
        except ValueError as er:
            await xx.edit(f"`{er}`")
            return

        base = os.path.splitext(os.path.basename(path))[0]
        if len(pages) == total:
            out = f"{base}.txt"
        elif len(pages) == 1:
            out = f"{base} (page {pages[0] + 1}).txt"
        else:
            out = f"{base} (pages {pages[0] + 1}-{pages[-1] + 1}).txt"
        out = check_filename(out)

        with open(out, "w", encoding="utf-8") as fh:
            for index in pages:
                text = reader.pages[index].extract_text() or ""
                fh.write(f"Page {index + 1}\n")
                fh.write("-" * 50 + "\n")
                fh.write(text + "\n\n")

        await event.client.send_file(
            event.chat_id,
            out,
            force_document=True,
            caption=f"`{os.path.basename(out)}`",
            reply_to=reply,
        )
        os.remove(out)
    finally:
        os.remove(path)
        await xx.delete()


@heartless_cmd(pattern="trim( (.*)|$)")
async def pdftrim(event):
    spec = (event.pattern_match.group(1) or "").strip()
    if not spec:
        await eor(event, f"Give a page range, e.g. `{HNDLR}trim 5-20`.")
        return
    path, reply, xx = await _get_replied_pdf(event)
    if not path:
        return
    try:
        total = len(PdfReader(path).pages)
        try:
            pages = _parse_pages(spec, total)
        except ValueError as er:
            await xx.edit(f"`{er}`")
            return

        base = os.path.splitext(os.path.basename(path))[0]
        out = check_filename(f"{base} (pages {pages[0] + 1}-{pages[-1] + 1}).pdf")
        _extract_pages_to_pdf(path, pages, out)

        await event.client.send_file(
            event.chat_id,
            out,
            force_document=True,
            thumb=ULTConfig.thumb,
            caption=f"`{os.path.basename(out)}`",
            reply_to=reply,
        )
        os.remove(out)
    finally:
        os.remove(path)
        await xx.delete()


@heartless_cmd(pattern="pdfinfo( (.*)|$)")
async def pdfinfo(event):
    path, reply, xx = await _get_replied_pdf(event)
    if not path:
        return
    try:
        reader = PdfReader(path)
        meta = {k.strip("/").lower(): v for k, v in (reader.metadata or {}).items()}

        def lookup(*keys):
            for key in keys:
                if meta.get(key):
                    return meta[key]
            return "—"

        page = reader.pages[0]
        width, height = float(page.mediabox.width), float(page.mediabox.height)
        info = (
            "<b>📄 PDF Info</b>\n\n"
            f"<b>File:</b> <code>{os.path.basename(path)}</code>\n"
            f"<b>Size:</b> <code>{humanbytes(os.path.getsize(path))}</code>\n"
            f"<b>Pages:</b> <code>{len(reader.pages)}</code>\n"
            f"<b>Page size:</b> <code>{width:.0f} × {height:.0f} pt</code>\n"
            f"<b>Title:</b> <code>{lookup('title')}</code>\n"
            f"<b>Author:</b> <code>{lookup('author')}</code>\n"
            f"<b>Subject:</b> <code>{lookup('subject')}</code>\n"
            f"<b>Producer:</b> <code>{lookup('producer')}</code>\n"
            f"<b>Creator:</b> <code>{lookup('creator')}</code>"
        )
        await xx.edit(info, parse_mode="html")
    finally:
        os.remove(path)


@heartless_cmd(pattern="pdscan( (.*)|$)")
async def imgscan(event):
    path, reply, xx = await _get_replied_image(event)
    if not path:
        return
    try:
        scanned = _scan_image(path)
        await event.client.send_file(
            event.chat_id,
            scanned,
            force_document=True,
            caption=f"`{os.path.basename(scanned)}`",
            reply_to=reply,
        )
        os.remove(scanned)
    finally:
        os.remove(path)
        await xx.delete()


@heartless_cmd(pattern="pdsave( (.*)|$)")
async def savepdf(event):
    reply = await event.get_reply_message()
    if not (reply and reply.media):
        await eor(event, get_string("pdf_3"))
        return
    name = (reply.file.name or "").lower()
    is_image = reply.photo or name.endswith(
        (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")
    )
    is_pdf = bool(
        reply.document and reply.document.mime_type == "application/pdf"
    )
    if not (is_image or is_pdf):
        await eor(event, get_string("pdf_3"))
        return

    xx = await event.eor(get_pstring("com_1", "load"))
    os.makedirs(_PDF_DIR, exist_ok=True)
    if is_pdf:
        filename = os.path.basename(reply.file.name or "doc.pdf")
        dest = check_filename(os.path.join(_PDF_DIR, filename))
        await reply.download_media(file=dest)
    else:
        tmp = await reply.download_media()
        try:
            scanned = _scan_image(tmp)
            dest = check_filename(os.path.join(_PDF_DIR, "page.pdf"))
            os.replace(scanned, dest)
        finally:
            os.remove(tmp)
    await xx.edit(
        f"✅ Added to the merge queue.\n"
        f"Reply more images/PDFs, then run `{HNDLR}pdsend` to merge & send."
    )


@heartless_cmd(pattern="pdsend( (.*)|$)")
async def sendpdf(event):
    name = (event.pattern_match.group(1) or "").strip()
    queued = sorted(glob.glob(os.path.join(_PDF_DIR, "*.pdf")))
    if not queued:
        await eor(
            event,
            f"The merge queue is empty. Add files with `{HNDLR}pdsave` first.",
        )
        return

    xx = await event.eor(get_pstring("com_1", "load"))
    if not name:
        name = "Merged PDF"
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    out = check_filename(name)

    writer = PdfWriter()
    for item in queued:
        writer.append(item)
    with open(out, "wb") as fh:
        writer.write(fh)

    await event.client.send_file(
        event.chat_id,
        out,
        force_document=True,
        thumb=ULTConfig.thumb,
        caption=f"`{out}`",
        reply_to=event.reply_to_msg_id,
    )
    for item in queued:
        os.remove(item)
    os.remove(out)
    await xx.delete()
