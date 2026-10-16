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
        """Ask the model for the next reply, text or tool calls."""

        session = self._ensure_session()
        body = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "temperature": self.temperature,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}

        async with session.post(
            f"{self.base_url}/chat/completions", json=body, headers=headers
        ) as response:
            if not 200 <= response.status < 300:
                raise BrainError(f"brain returned HTTP {response.status}")
            payload = await response.json()
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
