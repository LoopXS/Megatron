"""Shell tool for the assistant: real host command execution (risk confirm).

This is the one ``confirm`` tool in v1.  Everything side-effecting is
injectable: the runner is passed into :func:`build_shell_tools` and the child
process is created through :func:`asyncio.create_subprocess_shell`, so the
module can be unit-tested without spawning anything.  Only the standard
library and the assistant core types are imported; see spec sections 8 and 12.
"""

import asyncio
import os
import re
import secrets
import signal

from .._agent_core import Tool, ToolContext, ToolResult


async def terminate_tree(proc) -> None:
    """Kill ``proc``'s whole process group and reap it, tolerating races.

    The group may already be gone (the command exited between the timeout
    firing and this call) or ``pid`` may have been reaped, so the kill is
    best-effort.  ``proc.wait`` still runs so the child is never left a
    zombie; the wait itself is expected to be immediate once the group is
    killed.
    """

    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, OSError):
        pass
    await proc.wait()


def _spill(text: str, output_dir, cap: int) -> tuple[str, str]:
    """Write ``text`` whole to a file and return a note plus its path.

    Only the returned copy is capped; the file always holds the complete
    output so the operator can inspect it.
    """

    directory = output_dir or "."
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"out-{secrets.token_hex(4)}.txt")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    note = f"output exceeded {cap} characters; full output saved to {path}\n"
    return note + text[:cap], path


async def run_shell(
    command: str,
    *,
    workdir: str,
    timeout: float,
    allow_sudo: bool,
    cap: int = 4000,
    output_dir: str | None = None,
) -> ToolResult:
    """Run ``command`` in a new session and return its capped output.

    ``sudo`` is refused before any process is spawned unless ``allow_sudo``
    is set.  On timeout the whole process group is killed and an error result
    is returned.  Output larger than ``cap`` is written whole to a file under
    ``output_dir`` (default the current directory) whose path is returned in
    ``files``.
    """

    if re.search(r"\bsudo\b", command) and not allow_sudo:
        return ToolResult("sudo is disabled (set AI_ALLOW_SUDO)", error=True)

    proc = await asyncio.create_subprocess_shell(
        command,
        cwd=workdir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )

    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        await terminate_tree(proc)
        return ToolResult(f"command timed out after {timeout}s", error=True)

    if isinstance(stdout, bytes):
        text = stdout.decode("utf-8", errors="replace")
    else:
        text = stdout or ""

    if proc.returncode:
        text = f"exit {proc.returncode}\n{text}"

    if len(text) > cap:
        note, path = _spill(text, output_dir, cap)
        return ToolResult(note, files=[path])

    return ToolResult(text)


def build_shell_tools(
    *,
    workdir: str,
    timeout: float,
    allow_sudo: bool,
    runner=run_shell,
) -> list[Tool]:
    """Build the ``shell.run_command`` tool bound to one workspace.

    ``runner`` is injected so tests can substitute a fake; the built handler
    runs with ``cap=4000`` and spills to ``workdir`` so large output lands
    next to the audit log (ruling R3).
    """

    async def handler(arguments, context: ToolContext) -> ToolResult:
        return await runner(
            arguments.get("command", ""),
            workdir=workdir,
            timeout=timeout,
            allow_sudo=allow_sudo,
            cap=4000,
            output_dir=workdir,
        )

    return [
        Tool(
            name="shell.run_command",
            description=(
                "Run a shell command on the host and return its output. "
                "The exact command is shown to the user for confirmation "
                "before it runs."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The exact shell command to run.",
                    }
                },
                "required": ["command"],
            },
            risk="confirm",
            handler=handler,
            summarize=lambda arguments: arguments.get("command", ""),
        )
    ]
