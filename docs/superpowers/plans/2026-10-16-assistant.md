# Assistant Subsystem Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the owner/sudo users an assistant (on the assistant bot) that can generate and find images, run host commands, research the web, and remember facts, driven by a pluggable OpenAI-compatible model and gated by a risk-tiered safety model with a full audit trail.

**Architecture:** A framework-free core (`assistant/_agent_core.py`) owns the model client, the tool registry, the agent loop, budgets, and audit; a second pure core (`assistant/_memory_core.py`) owns per-user memory; each capability is an isolated module under `assistant/tools/` that declares its own risk tier and takes its side-effecting primitives by injection. The Telethon glue (`assistant/assistant.py`) only loads config, builds the registry, gates access, renders cards, and posts results — it contains no agent logic. Reuses the abliterix blueprint: pure core + thin glue + fake-package tests.

**Tech Stack:** Python 3.10+ (repo runs 3.14), stdlib `unittest` for tests, `asyncio` subprocesses, `aiohttp` (already a dependency) for HTTP, `udB` for config/memory persistence, Telethon event layer via the existing `asst_cmd`/`callback` decorators and `get_string`/`get_help` conventions.

**Spec:** `docs/superpowers/specs/2026-10-16-assistant-design.md`

## Global Constraints

- Owner/sudo gating on every handler via `@asst_cmd(..., owner=True)` and `@callback(..., owner=True)`.
- The core and every module under `assistant/tools/` import **only** the standard library and `aiohttp`; never `telethon`, `CythonX`, or the `assistant` package. They must load standalone from their file path in tests.
- `assistant/assistant.py` is the only file that imports Telethon/`udB`/`CythonX`, and it contains no agent logic (no loop, no tool dispatch decisions).
- Tool arguments are untrusted data: validated against the tool's declared JSON schema before the handler runs. A malformed or invalid call is an error *result* handed back to the model, never a crash.
- Risk tiers: `auto` runs immediately and is audited; `confirm` pauses for an inline ✅/✖️ approval that shows exactly what will run. v1 `confirm` tools: only `shell.run_command`.
- Shell runs in a real host shell by explicit operator choice: exact command shown before execution, `cwd` defaults to `AI_WORKDIR`, whole process group killed at `AI_SHELL_TIMEOUT`, output capped (spilled to a file when larger), `sudo` refused unless `AI_ALLOW_SUDO`, child inherits the bot's environment.
- Secrets (model key, image key) are never echoed to chat, and are redacted from audit records and from error text surfaced to the user.
- Config is read from `udB` first with an environment fallback, resolved at call time; malformed numeric values fall back to the default rather than breaking plugin load (spec §13).
- Tools return data, never chat side effects: files are returned as paths in `ToolResult.files` and sent by the glue.
- No new dependency is added to `requirements.txt`; image generation requires an operator-configured provider and is a clear "not configured" error otherwise.
- Tests live in `tests/` and are **gitignored** by project convention (`.gitignore` has `test*`); run them locally and commit only source/strings/docs.
- Commit messages: no backticks, lines ≤ 88 chars.

## File Structure

| File | Responsibility |
|---|---|
| `assistant/_agent_core.py` (create) | Pure logic: data types, `Settings`, argument validation, redaction, `AuditLog`, `OpenAICompatibleClient`, `Agent` loop, message assembly. stdlib + aiohttp only. |
| `assistant/_memory_core.py` (create) | Pure per-user fact store (`Fact`, `MemoryStore`) over an injected backend. stdlib only. |
| `assistant/tools/__init__.py` (create) | Marks the tools subpackage (empty). |
| `assistant/tools/shell.py` (create) | `run_command` tool (risk `confirm`), process-group timeout, output cap, sudo refusal. |
| `assistant/tools/memory.py` (create) | `remember` / `forget` tools bound to a `MemoryStore`. |
| `assistant/tools/web.py` (create) | `fetch_url` / `web_search` tools over injected fetch/search callables. |
| `assistant/tools/images.py` (create) | `image_search` / `image_generate` tools over injected search/download/generate callables. |
| `assistant/assistant.py` (create) | Config loading, registry wiring, gating, plain-text/command handlers, confirm card + callback, audit sink, help/doc. |
| `strings/strings/en.yml` (modify) | `help_assistant` + `assistant_*` message keys. |
| `README.md` (modify) | Operator setup: brain keys, image provider, workdir, shell/env-inheritance and sudo notices. |
| `tests/test_agent_core.py` (create, local) | Unit tests for client + loop + audit + assembly. |
| `tests/test_memory_core.py` (create, local) | Unit tests for the fact store. |
| `tests/test_tools.py` (create, local) | Unit tests for the four tool modules with injected collaborators. |
| `tests/test_assistant_command.py` (create, local) | Glue tests with a fake `assistant` package and `FakeEvent`/`FakeClient`. |

## Review Focus

The spec implies these behaviours that no happy-path test exercises; each gets a test in its owning task.

1. **Unconfirmed shell never runs** — a `confirm` tool must not execute during `step`; execution only happens after an approved `resume` (Task 5, Task 13).
2. **Decline is honoured** — a declined callback never runs the handler and the loop still ends cleanly with a reply (Task 5, Task 13).
3. **Timeout kills the group** — after `AI_SHELL_TIMEOUT` the command's whole process group is gone, not orphaned (Task 7).
4. **Secrets never leak** — the model/image keys never appear in audit records or in chat text (Task 1, Task 4, Task 13).
5. **Budget stops the loop** — a model that keeps calling tools is cut off at `max_steps` / `turn_timeout`, and the turn ends (Task 5).
6. **Hostile arguments are data** — schema-invalid or shell-metacharacter arguments are handled as data, validated, and never trusted (Task 1, Task 4).
7. **Unauthorized sender** — a non-owner/sudo sender receives nothing and triggers no tool (Task 12).

---

### Task 1: Core data types, settings, validation, redaction, audit

**Files:**
- Create: `assistant/_agent_core.py`
- Test: `tests/test_agent_core.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `@dataclass ToolCall(id: str, name: str, arguments: dict)`
  - `@dataclass LLMReply(text: str | None = None, tool_calls: list[ToolCall] = field(default_factory=list))`
  - `@dataclass ToolResult(text: str, files: list[str] = field(default_factory=list), error: bool = False)`
  - `@dataclass ToolContext(user_id: int, chat_id: int, workdir: str, allow_sudo: bool = False)`
  - `@dataclass Tool(name, description, parameters, risk, handler, summarize)`; `risk` is `"auto"` or `"confirm"`; `handler` is `async (arguments: dict, ctx: ToolContext) -> ToolResult`; `summarize` is `(arguments: dict) -> str`.
  - `class ToolRegistry` with `register(tool)`, `get(name) -> Tool | None`, `names() -> list[str]`, `schemas() -> list[dict]`, `validate(name, arguments) -> str | None`.
  - `validate_arguments(schema: dict, arguments: dict) -> str | None` (returns `None` when valid).
  - `@dataclass Settings(base_url="", api_key="", model="", temperature=0.7, max_steps=6, turn_timeout=120.0, workdir="./assistant_work", enabled=False, allow_sudo=False, tools=(), system_prompt="")`.
  - `redact(text: str, secrets: Iterable[str]) -> str`.
  - `class AuditLog(path: str, secrets: Iterable[str] = (), sink=None)` with `record(**fields) -> dict`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_agent_core.py
def test_tool_result_defaults_are_independent():
    a, b = core.ToolResult("x"), core.ToolResult("y")
    a.files.append("p"); assert b.files == []

def test_registry_schemas_uses_openai_function_shape():
    # register a tool; schemas()[0]["type"] == "function"
    # and ["function"]["name"] == tool.name

def test_registry_get_unknown_returns_none():
    assert core.ToolRegistry().get("nope") is None

def test_validate_arguments_accepts_valid():
    schema = {"type": "object", "properties": {"q": {"type": "string"}},
              "required": ["q"]}
    assert core.validate_arguments(schema, {"q": "hi"}) is None

def test_validate_arguments_rejects_missing_and_wrong_type():
    schema = {"type": "object", "properties": {"n": {"type": "integer"}},
              "required": ["n"]}
    assert core.validate_arguments(schema, {}) is not None
    assert core.validate_arguments(schema, {"n": "x"}) is not None

def test_validate_arguments_rejects_non_dict():
    assert core.validate_arguments({"type": "object"}, "boom") is not None

def test_redact_removes_every_secret_and_blanks_short_ones():
    out = core.redact("key=sk-abc123 sudo", ["sk-abc123"])
    assert "sk-abc123" not in out and "***" in out
    # a 2-char secret is not redacted by substring (guard against nuking text)

def test_audit_appends_jsonl_and_redacts(tmpdir):
    # AuditLog(path, secrets=["sk-abc123"]).record(uid=1, chat=2,
    #   tool="shell.run_command", args={"command": "echo sk-abc123"},
    #   decision="approved", exit=0, ms=5)
    # read the file: one JSON object; "sk-abc123" not in the raw text

def test_audit_calls_sink_with_record():
    # sink captures the same dict that was written

def test_settings_defaults_match_spec():
    s = core.Settings()
    assert (s.max_steps, s.turn_timeout, s.workdir, s.enabled) == (
        6, 120.0, "./assistant_work", False)
```

- [ ] **Step 2: Run tests, verify they fail** — `python3 tests/test_agent_core.py -v` → import/attribute errors.

- [ ] **Step 3: Implement the data types, `validate_arguments`, `redact`, `AuditLog`.**

`validate_arguments` rules: `arguments` must be a `dict`; every `required` key present; each declared property's value matches its JSON type (`string`, `number`, `integer`→`int` not `bool`, `boolean`, `array`, `object`); unknown extra keys are allowed. Return a short human message on the first violation.

`redact` replaces each secret (length ≥ 4) everywhere with `***`, then returns the text; also redact obvious bearer tokens (`sk-...`) by a light regex. `AuditLog.record` sets `ts` if absent, redacts the JSON-serialised `args` and any free text, appends one JSON line to `path` (creating parent dirs), and calls `sink(record)` if given. `sink` failures are swallowed.

- [ ] **Step 4: Run tests, verify they pass.**
- [ ] **Step 5: `python -m py_compile` on both interpreters; commit** — `git add assistant/_agent_core.py` / `git commit -m "feat(assistant): add core types, settings, validation and audit"`

---

### Task 2: The pluggable model client

**Files:**
- Modify: `assistant/_agent_core.py`
- Test: `tests/test_agent_core.py`

**Interfaces:**
- Consumes: `LLMReply`, `ToolCall`.
- Produces:
  - `class BrainError(Exception)`.
  - `class LLMClient(Protocol)` with `async complete(messages: list[dict], tools: list[dict]) -> LLMReply`.
  - `class OpenAICompatibleClient(base_url, api_key, model, temperature=0.7, timeout=60.0, session=None)` with `async complete(messages, tools) -> LLMReply` and `async aclose()`.

- [ ] **Step 1: Write failing tests** with a fake session/response:

```python
def test_client_parses_text_reply():
    # response json: {"choices":[{"message":{"content":"hi"}}]}
    # -> LLMReply(text="hi", tool_calls=[])

def test_client_parses_tool_calls_with_json_arguments():
    # message.content = None; tool_calls=[{id, function:{name, arguments:'{"q":"x"}'}}]
    # -> LLMReply(text=None, tool_calls=[ToolCall(id, "web.web_search", {"q":"x"})])

def test_client_tolerates_malformed_tool_arguments():
    # arguments "not json" -> ToolCall(arguments={}) and does not raise

def test_client_raises_brain_error_on_non_200():
    # status 500 -> BrainError, message includes the status code, not the key

def test_client_sends_bearer_key_and_model():
    # assert the request URL endswith /chat/completions, header Authorization
    # == "Bearer <key>", body model == configured model, tools passed through
```

- [ ] **Step 2: Run tests, verify they fail.**

- [ ] **Step 3: Implement `OpenAICompatibleClient`.** `base_url` is normalised (strip trailing `/`); the request goes to `{base_url}/chat/completions` with `Authorization: Bearer {api_key}` and JSON body `{model, messages, tools, temperature}`. Response parsing: take `choices[0].message`; `text = message.get("content") or None`; for each tool call build `ToolCall(id=..., name=function["name"], arguments=parsed-or-{})` where a JSON parse failure yields `{}`. Missing/unexpected keys yield `LLMReply(None, [])`. A non-2xx status raises `BrainError(f"brain returned HTTP {status}")`. The `session` is created lazily via `aiohttp.ClientSession` if not injected, and `aclose()` closes only a session it created.

- [ ] **Step 4: Run tests, verify they pass.**
- [ ] **Step 5: py_compile; commit** — `git commit -m "feat(assistant): add OpenAI-compatible model client"`

---

### Task 3: Memory core

**Files:**
- Create: `assistant/_memory_core.py`
- Test: `tests/test_memory_core.py`

**Interfaces:**
- Produces:
  - `@dataclass Fact(id: str, text: str, created_at: float)`.
  - `class MemoryStore(backend, max_facts=100, max_len=500, now=time.time)` with `list(uid) -> list[Fact]`, `add(uid, text) -> Fact`, `edit(uid, fact_id, text) -> bool`, `forget(uid, fact_id) -> bool`, `render(uid) -> str`.
  - Backend protocol: `get(uid: int) -> str | None`, `set(uid: int, value: str) -> None`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_memory_core.py
# a DictBackend: dict with get/set(json string)
def test_add_returns_fact_with_id_and_persists():
    # fact.id startswith "mf-"; new backend reads it back

def test_users_are_isolated():
    # add for 1 and 2; list(1) has only 1's fact

def test_edit_changes_text_and_returns_false_for_unknown():
def test_forget_removes_and_returns_false_when_absent():
def test_cap_drops_oldest_but_keeps_newest():
    # max_facts=2: add 3; list has #2 and #3
def test_text_is_truncated_to_max_len():
def test_render_is_empty_string_when_no_facts():
def test_render_lists_facts_with_ids():
    # contains the fact text and its id
def test_corrupt_backend_value_resets_to_empty():
    # backend get returns "{not json" -> list(uid) == []
```

- [ ] **Step 2: Run tests, verify they fail.**

- [ ] **Step 3: Implement `MemoryStore`.** Values are a JSON list of `{id, text, created_at}` on the backend; corrupt/absent values reset to `[]`. `add` truncates to `max_len`, drops the oldest past `max_facts`, generates `"mf-" + secrets.token_hex(3)`. `render` returns `""` when empty, else a `"Things to remember:\n- [id] text"` block.

- [ ] **Step 4: Run tests, verify they pass.**
- [ ] **Step 5: py_compile; commit** — `git add assistant/_memory_core.py` / `git commit -m "feat(assistant): add per-user memory store"`

---

### Task 4: Agent loop — auto tools, multi-step, errors, audit

**Files:**
- Modify: `assistant/_agent_core.py`
- Test: `tests/test_agent_core.py`

**Interfaces:**
- Consumes: `LLMClient`, `ToolRegistry`, `Settings`, `AuditLog`, `ToolContext`, `ToolResult`.
- Produces:
  - `@dataclass PendingAction(id: str, tool_call: ToolCall, messages: list[dict], user_id: int, chat_id: int)`
  - `@dataclass TurnResult(status: str, reply_text: str | None, pending: PendingAction | None = None, tool_results: list[ToolResult] = field(default_factory=list))`; `status` in `{"done", "awaiting_confirm", "budget"}`.
  - `class Agent(client, registry, settings, audit=None, *, now=time.time)` with `async step(messages, *, user_id, chat_id) -> TurnResult` and `async resume(pending, approved: bool) -> TurnResult` (full behaviour completed in Task 5).
  - Module helpers `assistant_tool_calls_message(reply) -> dict` and `tool_message(call_id, text) -> dict`.

- [ ] **Step 1: Write failing tests** with a `FakeLLMClient` that returns a queued list of `LLMReply`:

```python
# A FakeLLMClient(replies=[...]) pops one reply per complete() call.
def test_final_text_ends_turn_with_done():
    # one text reply -> TurnResult("done", "hello", None, [])

def test_auto_tool_runs_then_model_replies():
    # reply1 = tool call to an auto tool whose handler returns ToolResult("42");
    # reply2 = text "the answer is 42"
    # status "done", reply "the answer is 42", one tool_result "42"
    # the messages passed on the 2nd call contain a {"role":"tool",...} message

def test_multiple_tool_calls_run_in_order():
def test_unknown_tool_becomes_error_result_not_crash():
def test_invalid_arguments_become_error_result_and_skip_handler():
def test_tool_exception_becomes_error_result():
    # handler raises -> ToolResult(error=True), turn still completes
def test_auto_tool_is_audited_with_redacted_args(tmpdir):
    # audit file has one record; no secret in it
```

- [ ] **Step 2: Run tests, verify they fail.**

- [ ] **Step 3: Implement `Agent.step`.** Set `deadline = now() + turn_timeout`. Loop up to `max_steps` times: call `client.complete(messages, registry.schemas())`; if no tool calls, return `TurnResult("done", reply.text, None, tool_results)`. Otherwise append `assistant_tool_calls_message(reply)` and, for each call **in order**: resolve via `registry.get`; unknown → append an error tool message; `registry.validate` failing → append an error tool message; else run the handler with a `ToolContext(user_id, chat_id, workdir=settings.workdir, allow_sudo=settings.allow_sudo)`, catching exceptions into an error `ToolResult`, append `tool_message(call.id, result.text)`, collect it, and write an audit record (`decision="auto"`, `exit=None`, elapsed ms). `resume` is a stub in this task (`raise NotImplementedError`) and is completed in Task 5.

- [ ] **Step 4: Run tests, verify they pass.**
- [ ] **Step 5: py_compile; commit** — `git commit -m "feat(assistant): add agent loop with auto tools and audit"`

---

### Task 5: Agent confirmation and budgets

**Files:**
- Modify: `assistant/_agent_core.py`
- Test: `tests/test_agent_core.py`

**Interfaces:**
- Consumes: `Agent` from Task 4.
- Produces: completed `Agent.resume(pending, approved) -> TurnResult` and budget enforcement.

- [ ] **Step 1: Write failing tests**

```python
def test_confirm_tool_pauses_without_running():
    # a confirm tool whose handler records a call flag
    # step -> status "awaiting_confirm", pending.tool_call.name == tool name
    # handler flag is still False

def test_resume_approved_runs_then_finishes():
    # resume(pending, True) -> handler ran; model's next reply text is the result

def test_resume_declined_does_not_run_and_continues():
    # resume(pending, False) -> handler flag False; a "declined" tool message is
    # sent to the model; final status "done"

def test_max_steps_budget_stops_runaway_model():
    # FakeLLMClient always returns the same auto tool call; status "budget"
    # and complete() was called at most max_steps times

def test_turn_timeout_yields_budget():
    # inject now() so the deadline is exceeded after the first call

def test_empty_reply_ends_turn():
    # LLMReply(None, []) -> status "done", reply_text is None
```

- [ ] **Step 2: Run tests, verify they fail.**

- [ ] **Step 3: Implement.** Split the loop body into a private `_run(messages, user_id, chat_id)`; `step` delegates to it. On a `confirm` tool call, build a `PendingAction(id="pa-"+token_hex(3), tool_call, messages=<history incl. the assistant tool-call message>, user_id, chat_id)` and return `TurnResult("awaiting_confirm", reply.text, pending, tool_results)`. `resume` starts a fresh deadline, appends either the executed result (audited with `decision="approved"`) or a `tool_message(call_id, "user declined")` (audited with `decision="declined"`), then calls `_run` on the extended history. When the loop exhausts `max_steps` or `now() > deadline`, return `TurnResult("budget", <last text or None>, None, tool_results)`.

- [ ] **Step 4: Run tests, verify they pass.**
- [ ] **Step 5: py_compile; commit** — `git commit -m "feat(assistant): add confirmation flow and turn budgets"`

---

### Task 6: Conversation assembly and history trimming

**Files:**
- Modify: `assistant/_agent_core.py`
- Test: `tests/test_agent_core.py`

**Interfaces:**
- Produces:
  - `trim_history(history: list[dict], max_chars: int) -> list[dict]`
  - `assemble_messages(system_prompt: str, facts_text: str, history: list[dict], user_text: str, max_chars: int = 8000) -> list[dict]`

- [ ] **Step 1: Write failing tests**

```python
def test_assemble_orders_system_then_facts_then_history_then_user():
def test_assemble_omits_empty_facts_block():
def test_trim_drops_oldest_and_inserts_summary_note():
    # history over budget -> first element is a system note mentioning summary
def test_trim_keeps_recent_turns():
def test_assemble_respects_max_chars():
```

- [ ] **Step 2: Run tests, verify they fail.**

- [ ] **Step 3: Implement.** `trim_history` walks from the newest message backwards accumulating character cost; when the budget is exceeded it stops and prepends `{"role": "system", "content": "Summary of earlier conversation (truncated): ..."}` built from the drop count (v1 uses a count-based note, not an LLM summary). `assemble_messages` returns `[{"role":"system","content": system_prompt}]`, plus a `system` facts message when `facts_text` is non-empty, plus the trimmed history, plus `{"role":"user","content": user_text}`.

- [ ] **Step 4: Run tests, verify they pass.**
- [ ] **Step 5: py_compile; commit** — `git commit -m "feat(assistant): add message assembly and history budget"`

---

### Task 7: Shell tool

**Files:**
- Create: `assistant/tools/__init__.py` (empty)
- Create: `assistant/tools/shell.py`
- Test: `tests/test_tools.py`

**Interfaces:**
- Consumes: `Tool`, `ToolResult`, `ToolContext`.
- Produces:
  - `terminate_tree(proc) -> None` (kill the process group, tolerate races).
  - `async run_shell(command: str, *, workdir: str, timeout: float, allow_sudo: bool, cap: int = 4000, output_dir: str | None = None) -> ToolResult`
  - `build_shell_tools(*, workdir: str, timeout: float, allow_sudo: bool, runner=run_shell) -> list[Tool]` returning one tool named `shell.run_command`, risk `confirm`.

- [ ] **Step 1: Write failing tests** with an injected `runner` and, for the real `run_shell`, a fake process:

```python
# tests/test_tools.py
def test_shell_tool_is_confirm_and_summarize_is_the_command():
def test_shell_handler_returns_runner_output():
    # injected runner returns ToolResult("ok"); arguments {"command":"echo ok"}
def test_run_shell_refuses_sudo_when_not_allowed():
    # run_shell("sudo rm -rf /", allow_sudo=False) -> error result, no spawn
def test_run_shell_allows_sudo_when_enabled():
def test_run_shell_reports_nonzero_exit():
def test_run_shell_timeout_kills_the_group():
    # a fake proc records terminate_tree; timeout -> result reports timeout
def test_run_shell_spills_large_output_to_a_file(tmpdir):
    # output > cap -> ToolResult.files has one path inside output_dir
def test_run_shell_passes_cwd(tmpdir):
```

- [ ] **Step 2: Run tests, verify they fail.**

- [ ] **Step 3: Implement.** `run_shell` refuses when `re.search(r"\bsudo\b", command)` and not `allow_sudo`, returning `ToolResult("sudo is disabled (set AI_ALLOW_SUDO)", error=True)`. Otherwise `asyncio.create_subprocess_shell(command, cwd=workdir, stdout=PIPE, stderr=STDOUT, start_new_session=True)`, `await asyncio.wait_for(proc.communicate(), timeout)`; on `TimeoutError` call `terminate_tree(proc)` and return a timeout result. Decode output, prefix "exit N" for non-zero, cap at `cap` by writing the full text to `output_dir/out-<token>.txt` and returning that path in `files`. `terminate_tree` calls `os.killpg(os.getpgid(proc.pid), SIGKILL)` guarded by `ProcessLookupError`/`OSError`, then awaits `proc.wait()`. The tool's `summarize` returns the command verbatim.

- [ ] **Step 4: Run tests, verify they pass.**
- [ ] **Step 5: py_compile; commit** — `git add assistant/tools/` / `git commit -m "feat(assistant): add shell tool with timeout and output cap"`

---

### Task 8: Memory tool

**Files:**
- Create: `assistant/tools/memory.py`
- Test: `tests/test_tools.py`

**Interfaces:**
- Consumes: `MemoryStore`, `Tool`, `ToolResult`, `ToolContext`.
- Produces: `build_memory_tools(store: MemoryStore) -> list[Tool]` returning `memory.remember` and `memory.forget` (both risk `auto`).

- [ ] **Step 1: Write failing tests**

```python
def test_remember_stores_for_the_calling_user():
def test_forget_removes_and_reports_unknown():
def test_memory_tools_are_auto():
```

- [ ] **Step 2: Run tests, verify they fail.**

- [ ] **Step 3: Implement.** `memory.remember` takes `{"text": string}` (required), calls `store.add(ctx.user_id, text)`, returns a short confirmation including the new id. `memory.forget` takes `{"id": string}` (required), calls `store.forget`, returns removed / not-found.

- [ ] **Step 4: Run tests, verify they pass.**
- [ ] **Step 5: py_compile; commit** — `git commit -m "feat(assistant): add memory tools"`

---

### Task 9: Web tool

**Files:**
- Create: `assistant/tools/web.py`
- Test: `tests/test_tools.py`

**Interfaces:**
- Produces:
  - `strip_html(text: str) -> str` (drop tags/scripts, collapse whitespace).
  - `build_web_tools(fetch, search) -> list[Tool]` returning `web.fetch_url` and `web.web_search`, both risk `auto`, where `fetch` is `async (url: str) -> str` and `search` is `async (query: str, n: int) -> list[dict]` with `{title, url, snippet}`.

- [ ] **Step 1: Write failing tests**

```python
def test_fetch_rejects_non_http_scheme():
    # file:///etc/passwd -> error result, fetch not called
def test_fetch_strips_tags_and_caps():
    # fetch returns <html>...10000 chars... -> result <= cap, no "<"
def test_search_formats_results():
    # two results -> text contains both titles and urls
def test_web_tools_are_auto():
```

- [ ] **Step 2: Run tests, verify they fail.**

- [ ] **Step 3: Implement.** `web.fetch_url` validates `url` starts with `http://`/`https://`, calls `fetch`, runs `strip_html`, caps at ~8000 chars with a truncation note. `web.web_search` takes `{"query": string, "n": integer (default 5)}`, calls `search(query, n)`, renders a numbered list. The glue supplies real `fetch`/`search` (aiohttp + the repo's `async_searcher`/`GSEARCH`), so this module stays network-free in tests.

- [ ] **Step 4: Run tests, verify they pass.**
- [ ] **Step 5: py_compile; commit** — `git commit -m "feat(assistant): add web fetch and search tools"`

---

### Task 10: Images tool

**Files:**
- Create: `assistant/tools/images.py`
- Test: `tests/test_tools.py`

**Interfaces:**
- Produces: `build_image_tools(search, download, generate=None) -> list[Tool]` returning `images.image_search` and `images.image_generate` (both risk `auto`), where `search` is `async (query, n) -> list[str]` (URLs), `download` is `async (url) -> str` (local path), and `generate` is `async (prompt) -> str | None` (local path).

- [ ] **Step 1: Write failing tests**

```python
def test_image_search_downloads_and_returns_files():
def test_image_search_reports_when_nothing_found():
def test_image_generate_returns_file_when_configured():
def test_image_generate_without_provider_is_error():
    # generate=None -> error result mentioning configuration
def test_image_tools_are_auto():
```

- [ ] **Step 2: Run tests, verify they fail.**

- [ ] **Step 3: Implement.** `images.image_search` takes `{"query": string, "n": integer}` (default 4), calls `search`, downloads each URL, returns their paths in `ToolResult.files` with a short caption. `images.image_generate` takes `{"prompt": string}`; when `generate` is `None` returns `ToolResult("image generation is not configured (set AI_IMAGE_API_KEY)", error=True)`; otherwise calls it and returns the path in `files` (or an error result when it returns `None`).

- [ ] **Step 4: Run tests, verify they pass.**
- [ ] **Step 5: py_compile; commit** — `git commit -m "feat(assistant): add image search and generation tools"`

---

### Task 11: Message strings

**Files:**
- Modify: `strings/strings/en.yml`
- Test: `tests/test_assistant_command.py`

**Interfaces:**
- Produces the keys the glue (Tasks 12–13) consumes: `help_assistant`, `assistant_disabled`, `assistant_not_configured`, `assistant_brain_error`, `assistant_thinking`, `assistant_tool_running`, `assistant_confirm_prompt`, `assistant_confirm_button`, `assistant_cancel_button`, `assistant_confirm_expired`, `assistant_declined`, `assistant_budget`, `assistant_shell_timeout`, `assistant_output_spilled`, `assistant_sudo_refused`, `assistant_memory_list`, `assistant_memory_empty`, `assistant_memory_added`, `assistant_memory_forgotten`, `assistant_memory_unknown`, `assistant_config_shown`, `assistant_config_updated`, `assistant_enabled`, `assistant_reset`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assistant_command.py
REQUIRED = [ ...the key list above... ]
PLACEHOLDERS = {"{value}", "{id}", "{count}", "{name}", "{query}", "{cmd}",
                "{n}", "{when}"}

def test_all_assistant_keys_present():
    for key in REQUIRED:
        assert key in DATA, key

def test_placeholder_keys_format_without_error():
    # .format(**{p: "x" for p in PLACEHOLDERS}) must not raise
```

- [ ] **Step 2: Run the test, verify it fails** with the missing-key list.
- [ ] **Step 3: Add `help_assistant` and the `assistant_*` keys** to `strings/strings/en.yml`, each ≤ 88 chars per line, using only the listed placeholders.
- [ ] **Step 4: Validate YAML and run the test** — `python3 -c "import yaml;yaml.safe_load(open('strings/strings/en.yml'))"` then `python3 tests/test_assistant_command.py -v`.
- [ ] **Step 5: Commit** — `git add strings/strings/en.yml` / `git commit -m "feat(assistant): add message strings and help entry"`

---

### Task 12: Glue — config, registry wiring, gating, commands, plain-text turn

**Files:**
- Create: `assistant/assistant.py`
- Test: `tests/test_assistant_command.py` (extend with the fake-package harness)

**Interfaces:**
- Consumes: everything in `_agent_core`, `_memory_core`, `assistant/tools/*`, and the `assistant` package names `asst_cmd`, `callback`, `LOGS`, `udB`, `Button`, `get_string` (via `from . import *`) plus `get_help` (via `from strings import get_help`).
- Produces: module-level `_settings() -> Settings`, `_memory() -> MemoryStore`, `_registry() -> ToolRegistry`, `_agent() -> Agent`, `_audit_sink`; handlers for plain text/`/ask`, `/ai on|off`, `/aiconfig`, `/reset`, `/help_ai`; `__doc__ = get_help("help_assistant")`.

- [ ] **Step 1: Build the fake-package harness** (mirroring `tests/test_api_command.py`): a `types.ModuleType("assistant")` with `__path__`, `LOGS`, `get_string`, `HNDLR`, an `asst_cmd`/`callback` that record registrations, and a `udB` fake over a dict; load `_agent_core`, `_memory_core`, `tools/*`, then `assistant/assistant.py` from file path. Add `FakeEvent` (records `edit`/`reply`, has `sender_id`, `text`, `chat_id`) and `FakeClient`.

- [ ] **Step 2: Write failing tests**

```python
def test_non_owner_sender_is_ignored():
    # sender_id not in owner_and_sudos() -> no edit, no tool call
    # (the fake asst_cmd applies the owner gate before calling the handler)
def test_ai_on_off_toggles_the_db_key():
def test_aiconfig_masks_the_keys():
    # output contains *** and never the raw key
def test_plain_text_turn_posts_a_thinking_placeholder_then_edits_it():
def test_ask_is_equivalent_to_plain_text():
def test_disabled_assistant_replies_with_the_disabled_string():
def test_reset_clears_history():
def test_module_doc_is_the_help_string():
```

- [ ] **Step 3: Implement.** `_settings` reads `AI_*` keys from `udB` with `os.environ` fallback and safe int/float parsing. `_registry` builds the tool list: memory tools bound to `_memory()`; web tools bound to real `fetch` (aiohttp GET + `strip_html`) and `search` (the repo's existing search plumbing, e.g. `async_searcher`/`GSEARCH`); image tools bound to the existing Google/Unsplash search + a downloader, and `generate` only when `AI_IMAGE_API_KEY` is set; the shell tool with `workdir`, `AI_SHELL_TIMEOUT`, `AI_ALLOW_SUDO`. `AI_TOOLS` filters the registry. Per-user history lives in `_HISTORY: dict[int, list[dict]]`. The turn handler runs `_agent().step(assemble_messages(...), user_id=..., chat_id=...)`: posts `assistant_thinking`, edits it to `reply_text`, and sends any `ToolResult.files`. History is appended after the turn. Owner gating comes from `asst_cmd(owner=True)`.

- [ ] **Step 4: Run tests, verify they pass.**
- [ ] **Step 5: py_compile on both interpreters; commit** — `git add assistant/assistant.py` / `git commit -m "feat(assistant): wire config, commands and conversational turns"`

---

### Task 13: Glue — confirm card, callback, audit delivery, memory commands, docs

**Files:**
- Modify: `assistant/assistant.py`
- Modify: `README.md`
- Test: `tests/test_assistant_command.py`

**Interfaces:**
- Consumes: `TurnResult.status == "awaiting_confirm"`, `PendingAction`, `Agent.resume`.
- Produces: a `@callback(owner=True, data=re.compile(r"^ai(ok|no):"))` handler, a pending store `_PENDING: dict[str, PendingAction]`, an expiry sweep, the `AI_AUDIT_LOG` sink wiring, `/memory`, `/img`, `/imgfind`, `/run`, and an `AuditLog` writing `<AI_WORKDIR>/audit.jsonl`.

- [ ] **Step 1: Write failing tests**

```python
def test_confirm_tool_posts_a_card_and_waits():
    # a turn yielding awaiting_confirm posts the card with the command text;
    # the shell runner was NOT called
def test_approve_callback_runs_the_tool_and_edits_the_card():
def test_decline_callback_does_not_run_the_tool():
def test_confirm_expiry_is_treated_as_declined():
    # injected now() past AI_CONFIRM_TIMEOUT -> the pending is dropped
def test_audit_file_is_written_under_workdir(tmpdir):
def test_audit_lines_never_contain_the_key(tmpdir):
def test_memory_command_lists_and_forgets():
def test_img_and_imgfind_and_run_direct_commands():
def test_run_command_still_confirms():
```

- [ ] **Step 2: Run tests, verify they fail.**

- [ ] **Step 3: Implement.** On `awaiting_confirm`, store the pending, render `assistant_confirm_prompt` with `tool.summarize(args)`, and post inline ✅/✖️ buttons (`aiok:<id>` / `aino:<id>`). The callback (owner-gated) resolves the pending, edits the card to the outcome, and continues the turn via `Agent.resume`; unknown/expired ids answer with `assistant_confirm_expired`. Direct commands build a one-tool-call turn or call the tool directly (still confirmed for `/run`). `AuditLog(path=<workdir>/audit.jsonl, secrets=[AI_API_KEY, AI_IMAGE_API_KEY], sink=<send to AI_AUDIT_LOG if set>)`. Add the README section: brain keys, image provider, `AI_WORKDIR`, the shell timeout/output cap, that the child inherits the bot's environment, and the `AI_ALLOW_SUDO` warning.

- [ ] **Step 4: Run tests, verify they pass.**
- [ ] **Step 5: py_compile on both interpreters; commit** — `git add assistant/assistant.py README.md` / `git commit -m "feat(assistant): add confirmation, audit delivery and operator docs"`

---

## Self-Review

- **Spec coverage:** §4 file layout → File Structure; §5 client → Task 2; §6 loop/budgets → Tasks 4–5; §7 framework → Task 1; §8 tools → Tasks 7–10; §9 memory → Tasks 3, 8, 13; §10 history → Task 6; §11 data flow → Tasks 12–13; §12 safety → Tasks 1, 7, 12, 13; §13 config → Tasks 12–13; §14 commands → Tasks 12–13; §15 strings → Task 11; §16 failure modes → covered across Tasks 2, 4, 5, 7, 10, 12; §17 testing → every task; §18 phasing → v1 = all tasks.
- **Placeholder scan:** no `TBD`/`TODO`; every interface names exact symbols and signatures.
- **Type consistency:** tool names are dotted (`shell.run_command`, `memory.remember`, `web.fetch_url`, `web.web_search`, `images.image_search`, `images.image_generate`); `TurnResult.status` values are `done`/`awaiting_confirm`/`budget` throughout; `ToolResult.files` is the single channel for outbound files.
- **Line/commit conventions:** ≤ 88 chars, no backticks in messages, tests gitignored and not committed.
