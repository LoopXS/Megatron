# Assistant Subsystem — Design Spec

- **Date:** 2026-10-16
- **Status:** Draft for review
- **Author:** Megatron maintainers (with AI assistance)
- **Repo:** `LoopXS/Megatron`
- **Depends on:** nothing new at runtime beyond `aiohttp`; the existing
  `assistant/` package, the `udB` database, and the CythonX decorators.

## 1. Context and intent

Megatron today has isolated AI-shaped features — a proxy chat client
(`plugins/gpt.py`), a legacy Google text-bison helper, image *search*, and a
dormant image-generation helper — but no assistant that can understand a
request and carry it out with tools. This spec defines that subsystem: a
conversational agent, reachable through the assistant bot (`asst`) by the owner
and sudo users, that can generate images, find images, run commands on the
host, research the web, and remember facts about you.

The intent is capability with control: it should be able to do a very broad
range of tasks, while every side-effecting action stays visible, confirmed, and
audited.

## 2. Goals

- One conversational entry point on the assistant bot plus a few explicit
  commands for direct control.
- A pluggable brain: one OpenAI-compatible client that drives a cloud API today
  and a locally served model (e.g. an abliterated model) later, unchanged.
- A small, uniform tool framework where each capability declares its own risk
  tier, so new tools are additive and independently testable.
- Risk-tiered safety: read-only and benign tools run immediately; command
  execution and anything destructive is confirmed with the exact command shown.
- Global per-user memory that the assistant both learns from and is told to
  keep.
- Full auditability and a kill switch.

## 3. Non-goals

- Voice input/output, image understanding (vision), and document analysis.
- Multi-tenant use: v1 is owner/sudo only, single trust domain.
- A hard OS sandbox. The operator chose a real host shell with confirmation,
  timeout, and audit; isolation is explicitly out of scope for v1.
- Standing up local model *serving* (that is subsystem B, its own spec). This
  spec only defines the client interface that makes it pluggable.
- Scheduling/reminders and a general file workspace tool (deferred; see §18).

## 4. Architecture overview

Two layers, with a hard rule: **the core and the tools never import Telethon;
the glue contains no agent logic.**

```
assistant/
  _agent_core.py    pure: LLMClient protocol + OpenAICompatibleClient,
                    Tool/ToolRegistry/ToolResult, Agent loop, risk routing,
                    budgets, audit records, secret redaction
  _memory_core.py   pure: per-user fact store (add/edit/forget/list)
  tools/
    web.py          fetch_url, web_search            (risk: auto)
    images.py       image_search, image_generate     (risk: auto)
    shell.py        run_command                      (risk: confirm)
    memory.py       remember, forget                 (risk: auto)
  assistant.py      glue: asst_cmd + plain-text turns, streaming edits,
                    confirm callbacks, audit writer, config + memory commands
```

Dependency direction is one-way: `assistant.py` → `_agent_core` /
`_memory_core` → (`tools/*`). Tools receive their side-effecting primitives
(an HTTP session, a shell runner, a media sender callback) by injection, which
is what makes them testable without a real network or shell.

Pure cores are loaded and tested from their file path, exactly as
`plugins/_abliterix_core.py` is, and the glue is tested against a fake
`assistant` package exactly as abliterix is tested against a fake `plugins`
package (see §17).

## 5. The LLM client (pluggable brain)

```python
@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict

@dataclass
class LLMReply:
    text: str | None
    tool_calls: list[ToolCall]

class LLMClient(Protocol):
    async def complete(self, messages: list[dict], tools: list[dict]) -> LLMReply: ...

class OpenAICompatibleClient:
    def __init__(self, base_url, api_key, model, temperature=0.7,
                 timeout=60.0, session=None): ...
    async def complete(self, messages, tools) -> LLMReply: ...
```

`OpenAICompatibleClient` posts to `{base_url}/chat/completions` using the
OpenAI tool-calling message shape and parses either `content` or
`tool_calls`. Because that shape is spoken by OpenAI, OpenRouter, Groq,
llama.cpp, Ollama, and vLLM, switching between cloud and local is a
configuration change (base URL, key, model) and nothing else. The aiohttp
session is injected so tests never hit the network.

`LLMReply.text` and `LLMReply.tool_calls` are mutually exclusive in practice,
but the core tolerates both.

## 6. The agent loop

```python
@dataclass
class PendingAction:
    id: str
    tool_call: ToolCall
    messages: list[dict]        # history to resume with, including the call
    user_id: int
    chat_id: int

@dataclass
class TurnResult:
    status: str                 # "done" | "awaiting_confirm" | "budget"
    reply_text: str | None
    pending: PendingAction | None
    tool_results: list[ToolResult]

class Agent:
    def __init__(self, client, registry, settings, audit): ...
    async def step(self, messages) -> TurnResult: ...
    async def resume(self, pending, decision, result=None) -> TurnResult: ...
```

`step` is one user turn. It calls the client, and:

- if the reply is final text, returns `status="done"`;
- if the reply has tool calls, walks them **in order**:
  - a tool whose `risk == "auto"` runs now; its `ToolResult` becomes a `tool`
    message, and the loop calls the model again;
  - a tool whose `risk == "confirm"` **stops the loop** and returns
    `status="awaiting_confirm"` with the `PendingAction` (the call plus the
    history needed to resume);
- after the batch (or if `max_steps` is reached), returns `status="done"` or
  `status="budget"`.

`resume` takes the pending action and the user's decision:

- approved → run the tool, append its result, continue the loop;
- declined → append a `tool` message saying the user declined, continue the
  loop (so the model can react sensibly).

Budget: `max_steps` (default 6) bounds model⇄tool iterations per turn; a
per-turn wall-clock cap (`AI_TURN_TIMEOUT`) is also enforced. Hitting either
ends the turn with whatever text exists and `status="budget"`.

`max_steps` counts *model calls*, so a turn that alternates model calls and
auto-tool batches cannot run away.

## 7. Tool framework

```python
@dataclass
class ToolResult:
    text: str
    files: list[str] = field(default_factory=list)   # paths for the glue to send
    error: bool = False

@dataclass
class Tool:
    name: str                    # "shell.run_command"
    description: str
    parameters: dict             # JSON schema
    risk: str                    # "auto" | "confirm"
    handler: Callable            # async (arguments, context) -> ToolResult
    summarize: Callable          # (arguments) -> str : the confirm-card preview

class ToolRegistry:
    def register(self, tool): ...
    def get(self, name) -> Tool | None: ...
    def schemas(self) -> list[dict]: ...   # for the client's `tools` argument
```

The registry is the **only** place a model-supplied name becomes executable
code; an unknown name is an error result, never a lookup miss that crashes.
Tool call **arguments are always treated as untrusted data**, validated
against each tool's declared schema before the handler runs; a tool whose
arguments fail validation returns an error result.

Tools return data, not side effects on the chat: a tool that produces an image
returns the file path in `ToolResult.files`, and the glue sends it after the
turn. This keeps tools pure enough to test and keeps all Telegram I/O in one
place.

`summarize` produces the human-readable card text for `confirm` tools (for
shell it is the exact command string).

## 8. Tools

**`web.fetch_url(url)` → text.** Fetches a URL, strips HTML to readable text,
caps at ~8 000 chars (with a note when truncated), and rejects non-http(s)
schemes. Risk `auto`.

**`web.web_search(query, n=5)` → text.** Returns top-n results (title, URL,
snippet). Uses the repository's existing search plumbing where possible
(`async_searcher` for fetching; the `GSEARCH` SerpApi key when set, with the
existing scrape fallback otherwise). Risk `auto`.

**`images.image_search(query, n=4)` → files.** Reuses the existing Google-image
and Unsplash helpers to resolve image URLs, downloads them to the workspace,
and returns their paths in `files`. Risk `auto`.

**`images.image_generate(prompt)` → files.** Calls an OpenAI-images-compatible
or configured provider endpoint (`AI_IMAGE_*`), saves the result to the
workspace, and returns its path. Risk `auto`. No provider is bundled; without
`AI_IMAGE_API_KEY` the tool returns a clear "not configured" error result.

**`shell.run_command(command)` → text.** Risk `confirm`. See §12 for the exact
execution rules. `summarize` returns the command verbatim.

**`memory.remember(text)` / `memory.forget(fact_id)` → text.** Risk `auto`.
Reads are not a tool — facts are injected into the system prompt each turn
(§9).

## 9. Memory

`_memory_core.py` is a small per-user fact store:

```python
@dataclass
class Fact:
    id: str          # "mf-" + 6 hex
    text: str
    created_at: float

class MemoryStore:
    def __init__(self, backend): ...     # backend: udB adapter or dict (tests)
    def list(self, user_id) -> list[Fact]: ...
    def add(self, user_id, text) -> Fact: ...
    def edit(self, user_id, fact_id, text) -> bool: ...
    def forget(self, user_id, fact_id) -> bool: ...
```

Facts are persisted under a db key `AI_MEMORY_<user_id>` as a JSON list (the
`udB` API already provides durable, backend-agnostic storage). Every turn,
`MemoryStore.list` is rendered into the system prompt as a "Things to remember"
block, so the model reads memory for free. The model **writes** memory by
calling the `memory` tool when the user states a durable fact or says
"remember…". `/memory` (and its callbacks) lists, edits, and forgets outside a
turn. Memory is global per user, not per chat.

Facts are capped (e.g. 100 per user, 500 chars each) to bound prompt growth;
oldest are dropped past the cap.

## 10. History

Per-user conversation history is kept in memory for the session and bounded by
a fixed budget of roughly 8 000 characters (not configurable in v1). When a
turn would exceed the budget, the oldest turns are dropped and a one-paragraph
summary of them is kept as the first system note. History is **not** persisted
across restarts in v1 (memory is the durable layer); `/reset` clears it.

## 11. Data flow

1. A DM arrives — plain text is a conversational turn; the explicit commands in
   §14 are parsed first. Glue gates to owner/sudo (others get nothing) and
   builds a `TurnContext` (user, chat, message, text, per-user history).
2. Glue assembles `messages`: system prompt (persona + safety rules + tool
   list) + a "Things to remember" block + recent history + the new message.
3. `Agent.step` runs the loop of §6.
4. On `status="done"`, glue streams the reply (edit-in-place), delivers any
   `ToolResult.files` (photos/documents), persists nothing but history, and
   writes audit records.
5. On `status="awaiting_confirm"`, glue stores the `PendingAction`, posts a
   ✅/✖️ card showing `tool.summarize(args)`, and waits. The callback (owner
   gated) calls `Agent.resume` with approve/decline; expiry means decline.
6. Tool turns show a short "🔧 running `name`…" activity line rather than raw
   tool JSON.

## 12. Safety model

**Access.** `asst_cmd(..., owner=True)` for commands and turns;
`callback(..., owner=True)` for confirm buttons. Non-owner/sudo senders are
ignored. This matches the repository's existing gating.

**Risk tiers.** `auto` tools run immediately and are audited. `confirm` tools
pause for a card that shows exactly what will run. v1 has one `confirm` tool
(`shell.run_command`); new destructive tools must declare `confirm`.

**Shell execution.** The operator explicitly chose a real host shell, so:

- executed with `create_subprocess_shell`, `start_new_session=True`, as the
  bot's OS user;
- the exact command string is shown on the confirm card **before** execution;
- `cwd` defaults to `AI_WORKDIR`; the command may `cd` elsewhere and the card
  shows that;
- `AI_SHELL_TIMEOUT` (default 60 s); on expiry the whole **process group** is
  killed, reusing the abliterix `terminate_tree` pattern;
- output is capped; larger output is written to a file in the workspace and its
  path returned in place of the body;
- `sudo`/privilege-escalation is refused unless `AI_ALLOW_SUDO` is set;
- the child inherits the bot's environment — called out in the README.

**Budgets.** `AI_MAX_STEPS`, a per-turn wall-clock cap `AI_TURN_TIMEOUT`, and a
per-user cooldown (reusing the existing `Cooldown` helper) bound cost and
runaway loops. A confirm card lives for `AI_CONFIRM_TIMEOUT` seconds.
`AI_ENABLED` is a kill switch (`/ai off`).

**Secrets.** Keys are stored as db keys, never echoed in chat, and redacted
from audit records and error text surfaced to the user.

**Audit.** Every tool call — auto or confirmed — appends one JSONL record to
`<AI_WORKDIR>/audit.jsonl`: `{ts, uid, chat, tool, args, decision, exit, ms}`,
with secrets redacted. If `AI_AUDIT_LOG` is set, a mirror line is sent to that
chat. Confirm cards expire; an unanswered card is a decline.

## 13. Configuration

All read from `udB` (db key), with an environment variable fallback, resolved
at call time so changes take effect without a restart.

| Key | Default | Purpose |
|---|---|---|
| `AI_ENABLED` | `False` | Master switch; `/ai on\|off` toggles it |
| `AI_BASE_URL` | OpenAI default | OpenAI-compatible endpoint base |
| `AI_API_KEY` | — | Brain API key (masked everywhere) |
| `AI_MODEL` | — | Model id sent to the brain |
| `AI_TEMPERATURE` | `0.7` | Sampling temperature |
| `AI_MAX_STEPS` | `6` | Model⇄tool iterations per turn |
| `AI_TURN_TIMEOUT` | `120` | Seconds before a whole turn is abandoned |
| `AI_CONFIRM_TIMEOUT` | `120` | Seconds a confirm card waits before it counts as declined |
| `AI_SHELL_TIMEOUT` | `60` | Seconds before the command's process group is killed |
| `AI_WORKDIR` | `./assistant_work` | cwd for shell; home of `audit.jsonl` and artifacts |
| `AI_ALLOW_SUDO` | `False` | Permit privilege-escalation commands |
| `AI_AUDIT_LOG` | — | Optional chat id to mirror audit lines to |
| `AI_TOOLS` | all | Comma list to enable/disable tools |
| `AI_IMAGE_PROVIDER` | — | Image-generation provider selector |
| `AI_IMAGE_API_KEY` | — | Image-generation key |
| `AI_SYSTEM_PROMPT` | built-in | Persona override (safety rules always appended) |

Malformed numeric values fall back to the default rather than breaking plugin
load (a lesson carried from the abliterix review).

## 14. Commands

| Command | Purpose |
|---|---|
| *(plain DM text)* | a conversational turn |
| `/ask <text>` | explicit conversational turn (same path as plain text) |
| `/img <prompt>` | direct image generation |
| `/imgfind <query>` | direct image retrieval |
| `/run <command>` | direct command execution (still confirmed) |
| `/memory` | list facts; `/memory forget <id>`, `/memory edit <id> <text>` |
| `/reset` | clear this user's conversation history |
| `/aiconfig` | show/set base URL, model, keys (masked), toggles |
| `/ai on\|off` | enable/disable the assistant |
| `/help_ai` | help text |

## 15. Strings

`strings/strings/en.yml` gains `help_assistant` plus an `assistant_*` block
covering: disabled, not-configured brain, brain-unreachable, tool activity,
confirm card + ✅/✖️ labels, confirm expired, declined, shell timeout, output
spilled to file, sudo-refused, budget reached, memory list/edit/forget
confirmations, config shown, and the help text. Every key with placeholders is
covered by a format test (§17).

## 16. Failure modes

| Condition | Behavior |
|---|---|
| `AI_ENABLED` off | reply "assistant is off"; `/ai on` to enable |
| Brain key/model unset | clear "not configured" message; no tool calls |
| Brain unreachable / non-200 | "brain unavailable" + log; nothing else runs |
| Model returns malformed tool call | ignored; fed back once so the model can retry |
| Unknown tool name | error result returned to the model |
| Tool arguments fail schema validation | error result returned to the model |
| Tool handler raises | error result returned to the model; logged |
| Confirm card unanswered | treated as declined after the window |
| Shell exceeds timeout | process group killed; result reports the timeout |
| Shell output too large | spilled to a workspace file; path returned |
| `sudo` without `AI_ALLOW_SUDO` | refused with a specific message |
| Step/token/wall-clock budget hit | turn ends with current text; `status="budget"` |
| Non-owner/sudo sender | ignored entirely |

## 17. Testing

The established split: pure cores loaded from file, glue against a fake
`assistant` package, no real network or shell in unit tests.

- **`tests/test_agent_core.py`** — drive `Agent` with a `FakeLLMClient`:
  text vs tool-call replies; `auto` executes and `confirm` pauses without
  executing; multi-tool order and resume; `max_steps` termination; malformed
  call tolerated; tool-exception becomes an error result; history trimming and
  per-user isolation; audit emitted with secrets redacted.
- **`tests/test_memory_core.py`** — CRUD, isolation, persistence round-trip
  (dict backend), cap enforcement, forget semantics.
- **`tests/test_tools.py`** — injected runner/session: argument + preview
  construction, `cwd`, timeout → process-group kill, output cap → file spill,
  sudo refusal, non-http scheme rejection, image "not configured" path.
- **`tests/test_assistant_command.py`** — fake `assistant` package
  (`asst_cmd`, `callback`, `get_string`, `get_help`, `LOGS`, `asst`, `udB`,
  `Button`) + real `en.yml`; `FakeEvent`/`FakeClient`: gating, plain-text
  turns, streaming edits, confirm card + callback, decline-does-not-run, audit
  persistence, config/memory commands, and a strings completeness/format test.

**Review Focus** (the failures no happy-path test covers; each gets a test):

1. **Unconfirmed shell never runs** — a `confirm` tool must not execute during
   `step`.
2. **Decline is honored** — the declined callback never runs the handler and
   the loop still terminates cleanly.
3. **Timeout kills the group** — a long command's process group is gone after
   the timeout, not orphaned.
4. **Secrets never leak** — keys do not appear in audit records or chat text.
5. **Budget stops the loop** — a model that keeps calling tools is cut off at
   `max_steps`.
6. **Wrong-shape / hostile arguments** — schema-invalid or shell-metacharacter
   arguments are handled as data, never trusted.
7. **Unauthorized sender** — a non-owner/sudo sender receives nothing and
   triggers no tool.

## 18. Phasing

**v1 (this spec):** the client, the loop, the four tool modules, memory,
history, safety/audit, commands, strings, tests.

**Deferred (separate specs or later increments):** local model **serving**
(subsystem B); a general file-workspace tool; reminders/scheduling; vision and
voice; multi-user tenancy; a stronger sandbox.

## 19. Dependencies and license

No new runtime dependencies: `aiohttp` (already used) for the brain and web
tools, `udB` for config and memory, the existing image-search helpers, and the
CythonX decorators. Image **generation** requires the operator to configure a
provider; nothing is bundled. Megatron is AGPL-3.0; this subsystem stays
within it.
