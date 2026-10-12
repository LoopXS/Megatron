"""
✘ Commands Available

• `{i}usage`
    Get the complete system & database usage report.

• `{i}usage sys`
    Get system resource usage (CPU, RAM, Disk, Network).

• `{i}usage db`
    Get database storage usage.
"""

import shutil

from . import (
    LOGS,
    get_pstring,
    humanbytes,
    udB,
    heartless_cmd,
)

try:
    import psutil
except ImportError:
    psutil = None

# Approximate storage quota per database engine, expressed in MiB.
DB_LIMITS_MB = {
    "Mongo": 512,
    "Redis": 30,
    "SQL": 20,
    "LocalDB": 512,
}

_BAR_WIDTH = 10


def _bar(percent, width=_BAR_WIDTH):
    """Render a compact text progress bar for ``percent``."""
    percent = max(0.0, min(100.0, float(percent)))
    filled = round(width * percent / 100)
    return "█" * filled + "░" * (width - filled)


def _gauge(label, icon, percent):
    """Format a single labelled metric together with a progress bar."""
    return f"<b>{icon} {label}</b>  <code>{_bar(percent)}</code>  <b>{percent:.1f}%</b>\n"


def system_usage():
    """Build a report of the overall system resource usage."""
    if psutil is None:
        return (
            "<b>⚠️ Missing dependency</b>\n"
            "The <code>psutil</code> package is required to read system stats.\n"
            "Install it with <code>pip install psutil</code>"
        )

    total, used, free = shutil.disk_usage("/")
    disk_pct = used / total * 100
    cpu_pct = psutil.cpu_percent()
    mem_pct = psutil.virtual_memory().percent
    net = psutil.net_io_counters()

    return (
        "<b>🖥️ System Usage</b>\n"
        f"{_gauge('CPU', '⚙️', cpu_pct)}"
        f"{_gauge('RAM', '🧠', mem_pct)}"
        f"{_gauge('Disk', '💾', disk_pct)}\n"
        f"Total <code>{humanbytes(total)}</code> • "
        f"Used <code>{humanbytes(used)}</code> • "
        f"Free <code>{humanbytes(free)}</code>\n\n"
        "<b>📡 Network</b>\n"
        f"⬆ Upload&nbsp;&nbsp;<code>{humanbytes(net.bytes_sent)}</code>\n"
        f"⬇ Download&nbsp;<code>{humanbytes(net.bytes_recv)}</code>"
    )


def db_usage():
    """Build a report of the database storage usage."""
    name = udB.name
    limit_mb = DB_LIMITS_MB.get(name, 512)
    total = limit_mb * (2 ** 20)
    used = udB.usage
    percent = (used / total * 100) if total else 0.0

    return (
        "<b>🗄️ Database Usage</b>\n"
        f"Engine&nbsp;&nbsp;&nbsp;<code>{name}</code>\n"
        f"Storage&nbsp;&nbsp;&nbsp;<code>{humanbytes(used)}</code> / "
        f"<code>{humanbytes(total)}</code>\n"
        f"<code>{_bar(percent)}</code>  <b>{percent:.2f}%</b>"
    )


def full_usage():
    """Combine the system and database reports into a single output."""
    return f"{system_usage()}\n\n{db_usage()}"


@heartless_cmd(pattern="usage")
async def usage_finder(event):
    x = await event.eor(get_pstring("com_1", "load"))
    try:
        opt = ""
        try:
            opt = event.text.split(" ", maxsplit=1)[1].strip().lower()
        except IndexError:
            pass

        if opt == "db":
            output = db_usage()
        elif opt == "sys":
            output = system_usage()
        else:
            output = full_usage()

        await x.edit(output, parse_mode="html")
    except Exception as er:
        LOGS.exception(er)
        await x.edit(f"<b>❌ Error:</b> <code>{er}</code>", parse_mode="html")
