"""Framework-free core for the assistant subsystem.

This module holds every decision the assistant makes that does not touch
Telethon: the data types exchanged with the model and tools, the settings
container, the tool registry, JSON-schema argument validation, secret
redaction and the JSONL audit log.  It imports only the standard library (and,
in later tasks, ``aiohttp``) so it can be loaded and unit-tested straight from
its file path (see ``tests/test_agent_core.py``).  The Telethon glue lives in
``assistant/assistant.py``.
"""

import json
import os
import re
import secrets
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, Protocol

# A secret shorter than this is not replaced by substring: nuking two-letter
# keys out of ordinary prose would mangle every message for no gain.
_MIN_SECRET_LEN = 4

# Obvious bearer/API tokens (``sk-...``) are scrubbed even when the operator
# did not list the exact key, so a leaked key still never reaches the log.
_TOKEN_RE = re.compile(r"sk-[A-Za-z0-9_-]{4,}")

_JSON_CHECKS = {
    "string": lambda value: isinstance(value, str),
    "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
    "number": lambda value: (
        isinstance(value, (int, float)) and not isinstance(value, bool)
    ),
    "boolean": lambda value: isinstance(value, bool),
    "array": lambda value: isinstance(value, list),
    "object": lambda value: isinstance(value, dict),
    "null": lambda value: value is None,
}


@dataclass
class ToolCall:
    """One tool invocation requested by the model."""

    id: str
    name: str
    arguments: dict


@dataclass
class LLMReply:
    """What the model returned for one completion."""

    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


class BrainError(Exception):
    """The model endpoint could not be reached or answered with an error."""


class LLMClient(Protocol):
    """The one method the agent loop needs from any model backend."""

    async def complete(
        self, messages: list[dict], tools: list[dict]
    ) -> LLMReply: ...


@dataclass
class ToolResult:
    """What a tool hands back to the loop and the chat."""

    text: str
    files: list[str] = field(default_factory=list)
    error: bool = False
    exit: int | None = None


@dataclass
class ToolContext:
    """The caller identity and workspace a tool runs against."""

    user_id: int
    chat_id: int
    workdir: str
    allow_sudo: bool = False


@dataclass
class Tool:
    """A capability the model may call, and its risk tier."""

    name: str
    description: str
    parameters: dict
    risk: str
    handler: Callable
    summarize: Callable


@dataclass
class Settings:
    """Resolved assistant configuration; see spec section 13."""

    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.7
    max_steps: int = 6
    turn_timeout: float = 120.0
    confirm_timeout: float = 120.0
    workdir: str = "./assistant_work"
    enabled: bool = False
    allow_sudo: bool = False
    tools: tuple = ()
    system_prompt: str = ""


def validate_arguments(schema: dict, arguments: dict) -> str | None:
    """Check model-supplied ``arguments`` against a tool's JSON schema.

    Arguments are untrusted data: this is the gate that runs before any
    handler.  Returns ``None`` when valid, otherwise a short human message
    describing the first violation.  Unknown extra keys are allowed (models
    routinely over-fill), and undecided/unknown schema types are not policed.
    """

    if not isinstance(arguments, dict):
        return "arguments must be a JSON object"
    if not isinstance(schema, dict):
        return "tool schema is not an object"

    required = schema.get("required") or []
    if isinstance(required, list):
        for name in required:
            if name not in arguments:
                return f"missing required argument: {name}"

    properties = schema.get("properties") or {}
    if isinstance(properties, dict):
        for name, spec in properties.items():
            if name not in arguments or not isinstance(spec, dict):
                continue
            expected = spec.get("type")
            check = _JSON_CHECKS.get(expected)
            if check is not None and not check(arguments[name]):
                return f"argument {name} must be a {expected}"
    return None


class ToolRegistry:
    """The one place a model-supplied name becomes executable code."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool):
        self._tools[tool.name] = tool

    def get(self, name):
        return self._tools.get(name)

    def names(self):
        return list(self._tools)

    def schemas(self):
        """Render the registry in the OpenAI ``tools`` argument shape."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self._tools.values()
        ]

    def validate(self, name, arguments):
        tool = self.get(name)
        if tool is None:
            return f"unknown tool: {name}"
        return validate_arguments(tool.parameters, arguments)


def redact(text: str, secrets: Iterable[str]) -> str:
    """Replace every secret and any ``sk-`` token in ``text`` with ``***``."""

    if not isinstance(text, str):
        text = str(text)
    for secret in secrets:
        if isinstance(secret, str) and len(secret) >= _MIN_SECRET_LEN:
            text = text.replace(secret, "***")
    return _TOKEN_RE.sub("***", text)


def _redact_value(value, secrets: Iterable[str]):
    """Recursively redact every string inside a JSON-shaped value."""

    if isinstance(value, str):
        return redact(value, secrets)
    if isinstance(value, dict):
        return {key: _redact_value(item, secrets) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_value(item, secrets) for item in value]
    return value


class AuditLog:
    """Append-only JSONL record of every tool call, with secrets removed."""

    def __init__(self, path: str, secrets: Iterable[str] = (), sink=None):
        self.path = path
        self.secrets = tuple(secrets)
        self.sink = sink

    def record(self, **fields) -> dict:
        """Append one redacted record and return exactly what was written."""

        record = {
            key: _redact_value(value, self.secrets) for key, value in fields.items()
        }
        record.setdefault("ts", time.time())

        line = json.dumps(record, ensure_ascii=False, default=str)
        line = redact(line, self.secrets)

        parent = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(parent, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")

        if self.sink is not None:
            try:
                self.sink(record)
            except Exception:
                pass
        return record


class OpenAICompatibleClient:
    """A chat-completions client for any OpenAI-shaped endpoint.

    OpenAI, OpenRouter, Groq, llama.cpp, Ollama and vLLM all speak this
    shape, so moving between a cloud API and a locally served model is only
    a change of base URL, key and model.  The aiohttp session is injected so
    tests never touch the network; one is created lazily otherwise, and only
    a session this client itself created is ever closed.
    """

    def __init__(
        self,
        base_url,
        api_key,
        model,
        temperature=0.7,
        timeout=60.0,
        session=None,
    ):
        # A trailing slash would otherwise produce ``//chat/completions``.
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self.session = session
        self._session = None

    def _ensure_session(self):
        """Return the injected session, or build one on first use."""

        if self.session is not None:
            return self.session
        if self._session is None:
            import aiohttp

            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
        return self._session

    async def complete(self, messages, tools) -> LLMReply:
        """Ask the model for the next reply, text or tool calls.

        Every failure mode a dead or misbehaving brain can produce is
        surfaced as ``BrainError`` so the caller handles them uniformly: a
        non-2xx status is checked before the body is parsed, a 2xx whose
        body is not JSON is an error too, and any connection, timeout or
        other transport exception is wrapped.  The API key never appears in
        the message.
        """

        session = self._ensure_session()
        body = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "temperature": self.temperature,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}

        try:
            async with session.post(
                f"{self.base_url}/chat/completions", json=body, headers=headers
            ) as response:
                if not 200 <= response.status < 300:
                    raise BrainError(f"brain returned HTTP {response.status}")
                try:
                    payload = await response.json()
                except Exception as er:
                    raise BrainError(
                        "brain response was not JSON: "
                        f"{type(er).__name__}"
                    ) from er
        except BrainError:
            raise
        except Exception as er:
            raise BrainError(
                f"brain request failed: {type(er).__name__}"
            ) from er
        return _parse_reply(payload)

    async def aclose(self):
        """Close the session, but only if this client opened it."""

        if self._session is not None:
            await self._session.close()
            self._session = None


def _parse_reply(payload) -> LLMReply:
    """Turn an OpenAI chat-completions body into an ``LLMReply``.

    Anything that is not the expected shape yields an empty reply rather
    than raising: a misbehaving endpoint must not crash the loop.
    """

    if not isinstance(payload, dict):
        return LLMReply()
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return LLMReply()
    first = choices[0]
    if not isinstance(first, dict):
        return LLMReply()
    message = first.get("message")
    if not isinstance(message, dict):
        return LLMReply()

    tool_calls = []
    raw_calls = message.get("tool_calls")
    if isinstance(raw_calls, list):
        for raw in raw_calls:
            call = _parse_tool_call(raw)
            if call is not None:
                tool_calls.append(call)
    return LLMReply(text=message.get("content") or None, tool_calls=tool_calls)


def _parse_tool_call(raw):
    """Build one ``ToolCall``, or return ``None`` for an unusable entry."""

    if not isinstance(raw, dict):
        return None
    function = raw.get("function")
    if not isinstance(function, dict):
        return None
    name = function.get("name")
    if not isinstance(name, str):
        return None

    arguments = function.get("arguments")
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError:
            arguments = {}
    if not isinstance(arguments, dict):
        arguments = {}
    return ToolCall(id=raw.get("id"), name=name, arguments=arguments)


@dataclass
class PendingAction:
    """A ``confirm`` tool call parked until the user answers the card."""

    id: str
    tool_call: ToolCall
    messages: list[dict]
    user_id: int
    chat_id: int
    # The resolution this card produced once it was decided, so a retry after
    # a failed post-resolution brain call reuses it instead of running the
    # side-effecting tool (or auditing the decline) a second time.
    outcome: ToolResult | None = None


@dataclass
class TurnResult:
    """The outcome of one user turn: final text, a wait, or a budget stop."""

    status: str  # "done" | "awaiting_confirm" | "budget"
    reply_text: str | None
    pending: PendingAction | None = None
    tool_results: list[ToolResult] = field(default_factory=list)


def assistant_tool_calls_message(reply: LLMReply) -> dict:
    """Render a tool-calling reply as an OpenAI ``assistant`` message."""

    return {
        "role": "assistant",
        "content": reply.text or None,
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(call.arguments),
                },
            }
            for call in reply.tool_calls
        ],
    }


def tool_message(call_id: str, text: str) -> dict:
    """Render one tool result as an OpenAI ``tool`` message."""

    return {"role": "tool", "tool_call_id": call_id, "content": text}


def _message_cost(message: dict) -> int:
    """The character cost of one message: its text content length.

    Tool-call ``assistant`` messages carry their payload in ``tool_calls``
    and have ``content=None``; counting only text keeps the budget simple
    and predictable (spec section 10 bounds history in characters).
    """

    content = message.get("content")
    return len(content) if isinstance(content, str) else 0


def trim_history(history: list[dict], max_chars: int) -> list[dict]:
    """Keep the newest messages that fit within ``max_chars`` of content.

    Walks from the newest message backwards accumulating character cost and
    stops at the first message that would exceed the budget, so the oldest
    turns are dropped first.  When anything is dropped, a count-based
    ``system`` note takes their place as the first element; v1 does not ask
    the model for a real summary (spec section 10).  The input list is left
    untouched.
    """

    kept: list[dict] = []
    total = 0
    for message in reversed(history):
        cost = _message_cost(message)
        if total + cost > max_chars:
            break
        kept.append(message)
        total += cost
    kept.reverse()

    dropped = len(history) - len(kept)
    if dropped:
        kept.insert(
            0,
            {
                "role": "system",
                "content": (
                    "Summary of earlier conversation (truncated): "
                    f"{dropped} earlier message(s) omitted."
                ),
            },
        )
    return kept


def assemble_messages(
    system_prompt: str,
    facts_text: str,
    history: list[dict],
    user_text: str,
    max_chars: int = 8000,
) -> list[dict]:
    """Build the ``messages`` list for one turn (spec section 11).

    Order is the system prompt, an optional "Things to remember" facts
    block (omitted when empty), the budget-trimmed history, and finally the
    new user message.
    """

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    if facts_text:
        messages.append({"role": "system", "content": facts_text})
    messages.extend(trim_history(history, max_chars))
    messages.append({"role": "user", "content": user_text})
    return messages


class Agent:
    """One user turn: a bounded model⇄tool loop over the registry.

    The model drives; the registry decides what a name means.  Every
    model-supplied argument is untrusted and passes ``registry.validate``
    before a handler runs, and any failure becomes an error ``ToolResult``
    for the model to react to rather than an exception that ends the turn.
    """

    def __init__(self, client, registry, settings, audit=None, *, now=time.time):
        self.client = client
        self.registry = registry
        self.settings = settings
        self.audit = audit
        self.now = now

    async def step(self, messages, *, user_id, chat_id) -> TurnResult:
        """Run one turn to completion, to a budget stop, or to a pause."""

        return await self._run(messages, user_id, chat_id)

    async def _run(
        self, messages, user_id, chat_id, deadline=None
    ) -> TurnResult:
        """The bounded model⇄tool loop shared by ``step`` and ``resume``.

        ``deadline`` is a wall-clock instant; when omitted it is set from
        the current time plus ``settings.turn_timeout``.  Calls run in order
        and a ``confirm`` call pauses the loop before its handler executes.
        """

        if deadline is None:
            deadline = self.now() + self.settings.turn_timeout

        tool_results: list[ToolResult] = []
        last_text: str | None = None

        for _ in range(self.settings.max_steps):
            if self.now() > deadline:
                return TurnResult("budget", last_text, None, tool_results)

            reply = await self.client.complete(
                messages, self.registry.schemas()
            )
            if reply.text is not None:
                last_text = reply.text
            if not reply.tool_calls:
                return TurnResult("done", reply.text, None, tool_results)

            assistant_message = assistant_tool_calls_message(reply)
            messages.append(assistant_message)
            for index, call in enumerate(reply.tool_calls):
                tool = self.registry.get(call.name)
                if tool is not None and tool.risk == "confirm":
                    # No ``tool_calls`` entry may be left without a matching
                    # tool response: keep the calls resolved so far plus the
                    # paused one, and drop the rest for the model to re-ask.
                    assistant_message["tool_calls"] = (
                        assistant_message["tool_calls"][: index + 1]
                    )
                    pending = PendingAction(
                        id="pa-" + secrets.token_hex(3),
                        tool_call=call,
                        messages=messages,
                        user_id=user_id,
                        chat_id=chat_id,
                    )
                    return TurnResult(
                        "awaiting_confirm", reply.text, pending, tool_results
                    )

                result = await self._run_tool(call, user_id, chat_id)
                messages.append(tool_message(call.id, result.text))
                tool_results.append(result)

        return TurnResult("budget", last_text, None, tool_results)

    async def _run_tool(
        self, call, user_id, chat_id, decision="auto"
    ) -> ToolResult:
        """Resolve, validate and execute one tool call, never raising.

        Rejected calls are audited as well, so a model probing unknown names
        or malformed arguments still leaves a trace (spec section 12).
        ``decision`` tags a successfully executed call (``auto`` from the
        loop, ``approved`` from a resumed confirm card).
        """

        started = self.now()
        tool = self.registry.get(call.name)
        if tool is None:
            self._audit(call, user_id, chat_id, "rejected", started)
            return ToolResult(
                text=f"error: unknown tool: {call.name}", error=True
            )

        problem = self.registry.validate(call.name, call.arguments)
        if problem is not None:
            self._audit(call, user_id, chat_id, "rejected", started)
            return ToolResult(text=f"error: {problem}", error=True)

        context = ToolContext(
            user_id=user_id,
            chat_id=chat_id,
            workdir=self.settings.workdir,
            allow_sudo=self.settings.allow_sudo,
        )
        try:
            result = await tool.handler(call.arguments, context)
        except Exception as exc:
            result = ToolResult(text=f"error: {exc}", error=True)
        self._audit(call, user_id, chat_id, decision, started, result)
        return result

    def _audit(self, call, user_id, chat_id, decision, started, result=None):
        """Append one redacted audit record for any tool call.

        Both executed and rejected calls are recorded; only ``decision`` and
        the (absent) exit code differ.  ``args`` is untrusted model data and
        ``AuditLog.record`` redacts it.
        """

        if self.audit is None:
            return
        self.audit.record(
            uid=user_id,
            chat=chat_id,
            tool=call.name,
            args=call.arguments,
            decision=decision,
            exit=result.exit if result is not None else None,
            ms=int((self.now() - started) * 1000),
        )

    async def resume(self, pending, approved: bool) -> TurnResult:
        """Continue a paused turn once the user approves or declines.

        A fresh wall-clock deadline is started here, so the confirm wait
        itself does not count against the turn budget.  An approved call
        runs exactly as an ``auto`` tool but is audited as ``approved``; a
        declined one is not run and its result message says so, audited as
        ``declined``.  Either way the loop then continues on the extended
        history.

        The decision is recorded on ``pending.outcome`` before the loop
        resumes, and a later retry (the glue keeps a failed resume
        retryable) reuses that recorded result instead of executing the
        tool or auditing the decision again.  A fresh copy of the history
        is extended each time so a retry rebuilds it deterministically.
        """

        deadline = self.now() + self.settings.turn_timeout
        call = pending.tool_call
        messages = list(pending.messages)
        surface = approved

        if pending.outcome is not None:
            # Already resolved on an earlier, failed attempt: do not run the
            # tool, audit, or re-evaluate the branch.
            result = pending.outcome
        else:
            if approved:
                result = await self._run_tool(
                    call,
                    pending.user_id,
                    pending.chat_id,
                    decision="approved",
                )
            else:
                started = self.now()
                self._audit(
                    call, pending.user_id, pending.chat_id, "declined", started
                )
                result = ToolResult(text="user declined")
            pending.outcome = result

        messages.append(tool_message(call.id, result.text))
        turn = await self._run(
            messages, pending.user_id, pending.chat_id, deadline
        )
        if surface:
            # Surface the approved call's result (e.g. spilled files) exactly
            # as the loop would have had it run in its own batch.
            turn.tool_results.insert(0, result)
        return turn
