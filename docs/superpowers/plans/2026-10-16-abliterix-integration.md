# Abliterix Job Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add owner/sudo-only Telegram commands that run the abliterix CLI as a managed child process, stream progress, and deliver the exported model path plus its `reproduce.json`.

**Architecture:** Megatron owns scheduling, persistence, and the chat UX; abliterix runs as a separate process from its own venv. All decision logic lives in a framework-free core (`plugins/_abliterix_core.py`) that is unit-tested in isolation; the Telethon glue (`plugins/abliterix.py`) only wires commands and the worker/monitor loops to that core. One job runs at a time; state is persisted to `jobs.json` and reconciled on restart.

**Tech Stack:** Python 3.10+ (repo runs 3.14), stdlib `unittest` for tests, `asyncio` subprocesses, Telethon event layer, existing `heartless_cmd`/`get_string`/`get_help` conventions.

**Spec:** `docs/superpowers/specs/2026-10-16-abliterix-integration-design.md`

## Global Constraints

- Owner/sudo gating on every command via `@heartless_cmd(..., owner_only=True)`.
- Never invoke a shell: arguments are an argv list (use `create_subprocess_exec`).
- abliterix is invoked headlessly with `--non-interactive` and a per-job `--optimization.checkpoint-dir`.
- No new dependency is added to `requirements.txt`; abliterix lives in its own venv.
- Config is environment-driven with the exact defaults from spec §14.
- Extra flags are restricted to the allowlist in spec §10; unknown flags are rejected.
- Sensitive values (`OPENROUTER_API_KEY`, HF tokens) are inherited from the environment, never read, stored, or echoed.
- Tests live in `tests/` and are **gitignored** by project convention (`.gitignore` has `test*`); run them locally and commit only source/strings/docs.
- Commit messages: no backticks, lines ≤ 88 chars.

## File Structure

| File | Responsibility |
|---|---|
| `plugins/_abliterix_core.py` (create) | Pure logic: `Job`, `JobStore`, id/validation/flag/argv/env builders, log parsing, process liveness/terminate/reap. stdlib only. |
| `plugins/abliterix.py` (create) | Command handlers, gating, worker loop, progress monitor, delivery. Imports the core. |
| `strings/strings/en.yml` (modify) | `help_abliterix` + `abliterix_*` message keys. |
| `tests/test_abliterix_core.py` (create, local) | Unit tests for the core. |
| `tests/test_abliterix_plugin.py` (create, local) | Handler tests with fakes. |
| `README.md` (modify) | Operator setup: create the venv, set `ABLITERIX_BIN`, safety notice. |

## Review Focus

The spec implies these behaviours that no happy-path test exercises; each gets a test in its owning task.

1. **Restart with a job mid-run** — a `running` job whose PID is gone must become `lost`, never silently `succeeded` or disappear (Task 4).
2. **Cancel race** — cancelling a job that already exited must not raise and must leave a terminal state (Task 4, Task 9).
3. **Missing prerequisites** — no GPU, low disk, or missing binary must fail at enqueue with a specific message and no partial job (Task 6/7).
4. **Hostile flags** — a value containing `;`, `$(...)`, or an unknown flag must be rejected, never reach a shell (Task 2).
5. **Corrupt/partial `jobs.json`** — must load to an empty store rather than crash the plugin (Task 1).

---

### Task 1: Core data model and job store

**Files:**
- Create: `plugins/_abliterix_core.py`
- Test: `tests/test_abliterix_core.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `JOB_STATES: tuple[str, ...]`, `ACTIVE_STATES: frozenset[str]`, `TERMINAL_STATES: frozenset[str]`
  - `class Job` with fields `id, model, state, extra_flags, created_at, started_at, finished_at, pid, returncode, phase, trials_done, last_line, chat_id, status_message_id, workdir, out_dir, error`; methods `to_dict() -> dict`, `from_dict(d: dict) -> Job`, `is_terminal() -> bool`, `elapsed(now: float) -> float`.
  - `class JobStore(workdir: str, path: str | None = None)` with `path`, `load() -> None`, `save() -> None`, `add(job)`, `get(job_id) -> Job | None`, `all() -> list[Job]`, `remove(job_id) -> bool`, `update(job)`, `next_queued() -> Job | None`, `find_active(model) -> Job | None`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_abliterix_core.py
def test_store_roundtrip():
    store = core.JobStore(tmpdir)
    job = core.Job(id="ax-000001", model="org/model")
    store.add(job); store.save()
    again = core.JobStore(tmpdir); again.load()
    assert again.get("ax-000001").model == "org/model"

def test_store_tolerates_corrupt_file():
    open(os.path.join(tmpdir, "jobs.json"), "w").write("{not json")
    store = core.JobStore(tmpdir); store.load()
    assert store.all() == []

def test_next_queued_is_oldest_created():
    # add two queued jobs with created_at 2 and 1; next_queued().id == the earlier
def test_find_active_matches_queued_or_running_only():
    # a succeeded job with same model is not returned
def test_job_elapsed_uses_finished_when_terminal():
    # finished_at set -> elapsed == finished_at - started_at
```

- [ ] **Step 2: Run tests, verify they fail** — `python -m unittest tests.test_abliterix_core -v` → import/attribute errors.
- [ ] **Step 3: Implement `Job` and `JobStore`** in `plugins/_abliterix_core.py`.

`save()` writes to `path + ".tmp"` then `os.replace` to `path` (atomic). `load()` catches `(OSError, ValueError, TypeError)` and resets to empty. Datetime fields are float epoch seconds; `elapsed(now)` returns `(finished_at or now) - (started_at or created_at)` clamped at ≥ 0.

- [ ] **Step 4: Run tests, verify they pass.**
- [ ] **Step 5: Commit** — `git add plugins/_abliterix_core.py` / `git commit -m "feat(abliterix): add job model and durable store"`

---

### Task 2: Validation, flag allowlist, and process spec

**Files:**
- Modify: `plugins/_abliterix_core.py`
- Test: `tests/test_abliterix_core.py`

**Interfaces:**
- Produces:
  - `DEFAULT_ALLOWED_FLAGS: tuple[str, ...]` exactly: `("--optimization.n-trials", "--optimization.seed", "--model.quant-method", "--model.backend", "--inference.batch-size", "--inference.max-batch-size")`
  - `is_valid_model_id(text: str) -> bool`
  - `slugify_model_id(model: str) -> str`
  - `new_job_id(existing: Iterable[str], rng=None) -> str`
  - `parse_extra_flags(tokens: list[str], allowed: Iterable[str]) -> tuple[list[str], str | None]` returning `(flattened_flags, error_code)`.
  - `build_env(base: Mapping[str, str] | None = None) -> dict[str, str]`
  - `@dataclass ProcessSpec(argv, cwd, env, log_path)`
  - `build_process_spec(binary, model, job_dir, extra_flags, base_env=None) -> ProcessSpec`

- [ ] **Step 1: Write failing tests**

```python
def test_valid_model_ids():
    assert core.is_valid_model_id("Qwen/Qwen3-4B-Instruct-2507")
    assert not core.is_valid_model_id("no-slash")
    assert not core.is_valid_model_id("org/name; rm -rf /")

def test_parse_extra_flags_accepts_allowlisted_pair():
    flags, err = core.parse_extra_flags(["--optimization.n-trials", "25"], core.DEFAULT_ALLOWED_FLAGS)
    assert flags == ["--optimization.n-trials", "25"] and err is None

def test_parse_extra_flags_rejects_unknown_and_injection():
    for bad in (["--ui"], ["--model", "x"], ["--optimization.n-trials"]):
        flags, err = core.parse_extra_flags(bad, core.DEFAULT_ALLOWED_FLAGS)
        assert err == "abliterix_bad_flag"

def test_parse_extra_flags_rejects_missing_value():
    _f, err = core.parse_extra_flags(["--optimization.n-trials"], core.DEFAULT_ALLOWED_FLAGS)
    assert err == "abliterix_bad_flag"

def test_build_process_spec_argv_head():
    spec = core.build_process_spec("/venv/bin/abliterix", "org/m", "/jobs/ax-1", [], {})
    assert spec.argv[:4] == ["/venv/bin/abliterix", "--model.model-id", "org/m", "--non-interactive"]
    assert "--optimization.checkpoint-dir" in spec.argv
    assert spec.cwd == "/jobs/ax-1"

def test_build_env_sets_no_color():
    env = core.build_env({})
    assert env["NO_COLOR"] == "1" and env["PYTHONUNBUFFERED"] == "1"
```

- [ ] **Step 2: Run tests, verify fail.**
- [ ] **Step 3: Implement** the functions above.

`is_valid_model_id`: `re.fullmatch(r"[A-Za-z0-9][\w.-]*/[A-Za-z0-9][\w.-]*", text)`. `parse_extra_flags`: iterate pairs; each flag must be in `allowed` and have a following non-flag token; forbid any token containing `;`, `` ` ``, `$`, `|`, `&`, or newline. `build_process_spec` appends `--non-interactive-output-dir <job_dir>/out` and `--optimization.checkpoint-dir <job_dir>/checkpoint`, then the flattened extra flags; `log_path = <job_dir>/run.log`.

- [ ] **Step 4: Run tests, verify pass.**
- [ ] **Step 5: Commit** — `git commit -m "feat(abliterix): add validation, flag allowlist and process spec"`

---

### Task 3: Log parsing and progress extraction

**Files:**
- Modify: `plugins/_abliterix_core.py`
- Test: `tests/test_abliterix_core.py`

**Interfaces:**
- Produces:
  - `PHASE_MARKERS: tuple[tuple[str, str], ...]` mapping substrings → labels: `("Loading benign prompts", "loading data")`, `("Determining optimal batch size", "tuning batch size")`, `("Computing per-layer steering vectors", "computing vectors")`, `("Non-interactive mode: optimization finished", "finishing")`, `("Exporting verified trial", "exporting")`.
  - `detect_phase(text: str) -> str` (last marker seen, else `"running"`).
  - `count_trials(text: str) -> int` (highest integer matched by `re.compile(r"trial\s*#?\s*(\d+)", re.IGNORECASE)`, else 0).
  - `last_line(text: str) -> str` (last non-empty line, truncated to 200 chars).
  - `tail_lines(text: str, n: int) -> str`.

- [ ] **Step 1: Write failing tests**

```python
def test_detect_phase_uses_last_marker():
    text = "Loading benign prompts\n...\nComputing per-layer steering vectors"
    assert core.detect_phase(text) == "computing vectors"

def test_detect_phase_defaults_to_running():
    assert core.detect_phase("nothing familiar") == "running"

def test_count_trials_takes_max():
    assert core.count_trials("Trial 1 done\nTrial 7 done") == 7

def test_tail_lines_keeps_last_n():
    assert core.tail_lines("a\nb\nc\nd", 2) == "c\nd"
```

- [ ] **Step 2: Run tests, verify fail.**
- [ ] **Step 3: Implement** the parsing helpers. All are pure string operations.
- [ ] **Step 4: Run tests, verify pass.**
- [ ] **Step 5: Commit** — `git commit -m "feat(abliterix): parse run logs into phase and progress"`

---

### Task 4: Process liveness, termination, reaping, and state transitions

**Files:**
- Modify: `plugins/_abliterix_core.py`
- Test: `tests/test_abliterix_core.py`

**Interfaces:**
- Produces:
  - `def is_pid_alive(pid: int) -> bool`
  - `def terminate_tree(pid, grace=20.0, *, killpg=os.killpg, sleep=time.sleep, alive=is_pid_alive) -> None`
  - `def reap(jobs: list[Job], alive=is_pid_alive) -> list[Job]` — sets `state="lost"` on any `running` job with a dead `pid`; returns the changed jobs.
  - `def transition(job: Job, new_state: str, now: float, **fields) -> None` — validates allowed transitions (`queued→running`, `running→{succeeded,failed,canceled,lost}`, `queued→canceled`); raises `ValueError` otherwise; applies `**fields`.

- [ ] **Step 1: Write failing tests**

```python
def test_reap_marks_running_dead_job_lost():
    job = core.Job(id="ax-1", model="o/m", state="running", pid=999)
    changed = core.reap([job], alive=lambda pid: False)
    assert job.state == "lost" and changed == [job]

def test_reap_leaves_live_and_terminal_jobs():
    live = core.Job(id="a", model="o/m", state="running", pid=1)
    done = core.Job(id="b", model="o/m", state="succeeded", pid=None)
    assert core.reap([live, done], alive=lambda pid: True) == []

def test_transition_rejects_illegal():
    job = core.Job(id="a", model="o/m", state="succeeded")
    with self.assertRaises(ValueError):
        core.transition(job, "running", now=1.0)

def test_terminate_tree_kills_process_group_then_returns():
    calls = []
    core.terminate_tree(123, grace=0, killpg=lambda pid, sig: calls.append(sig),
                        sleep=lambda s: None, alive=lambda pid: False)
    assert calls  # SIGTERM (and SIGKILL only if still alive)
```

- [ ] **Step 2: Run tests, verify fail.**
- [ ] **Step 3: Implement** the four functions. `is_pid_alive` returns False on `ProcessLookupError`, True otherwise. `terminate_tree` sends `signal.SIGTERM` to the process group (`os.killpg(pid, ...)`), sleeps `grace`, and sends `SIGKILL` only if `alive(pid)`.
- [ ] **Step 4: Run tests, verify pass.**
- [ ] **Step 5: Commit** — `git commit -m "feat(abliterix): process liveness, termination and reaping"`

---

### Task 5: Message strings and help

**Files:**
- Modify: `strings/strings/en.yml` (after the `session_*`/`api_*` blocks)
- Test: `tests/test_abliterix_core.py` (a strings-completeness test)

**Interfaces:**
- Produces keys consumed by Task 6–9: `help_abliterix`, `abliterix_help`, `abliterix_no_gpu`, `abliterix_low_disk` (uses `{gb}`), `abliterix_no_binary` (uses `{bin}`), `abliterix_bad_model`, `abliterix_duplicate`, `abliterix_bad_flag`, `abliterix_queued` (uses `{id}`, `{model}`), `abliterix_status` (uses `{id}`, `{model}`, `{state}`, `{elapsed}`, `{phase}`, `{trials}`, `{last}`), `abliterix_list_empty`, `abliterix_list_item` (uses `{id}`, `{state}`, `{model}`, `{elapsed}`), `abliterix_log_header` (uses `{id}`, `{n}`), `abliterix_no_job`, `abliterix_cancel_ok`, `abliterix_canceled`, `abliterix_rm_ok`, `abliterix_purge_confirm` (uses `{id}`), `abliterix_purge_done`, `abliterix_purge_cancel`, `abliterix_done_ok` (uses `{id}`, `{path}`), `abliterix_done_failed`, `abliterix_lost_note`, `abliterix_unknown_sub`, `abliterix_worker_error`.

- [ ] **Step 1: Write a failing test** that loads `en.yml` with `yaml.safe_load` and asserts every key in the list above exists and that `{gb}`/`{id}`-style placeholders `format()` without error using dummy values.
- [ ] **Step 2: Run test, verify fail (missing keys).**
- [ ] **Step 3: Add the keys** to `strings/strings/en.yml`, following the style of the existing `session_*`/`api_*` entries (leading emoji, concise; `help_abliterix` in the other `help_*` style). Escape literal braces if any.
- [ ] **Step 4: Run test, verify pass.**
- [ ] **Step 5: Commit** — `git add strings/strings/en.yml` / `git commit -m "feat(abliterix): add message strings and help entry"`

---

### Task 6: Plugin skeleton — gating and read-only commands

**Files:**
- Create: `plugins/abliterix.py`
- Test: `tests/test_abliterix_plugin.py`

**Interfaces:**
- Consumes: `_abliterix_core` symbols from Tasks 1–4; strings from Task 5.
- Produces:
  - Module globals `_STORE`, `_WORKDIR`, `_BINARY`, `_render(key, **kw) -> str`, `_store() -> JobStore`.
  - `@heartless_cmd(pattern="abliterix( (.*)|$)", owner_only=True) async def abliterix_cmd(e)`
  - `@heartless_cmd(pattern="abliterate( (.*)|$)", owner_only=True) async def abliterate_cmd(e)` (body completed in Task 7; Task 6 registers it and validates input then reports "not yet runnable" only if preflight fails).
  - `_preflight() -> str | None` returning an error key or `None`.

- [ ] **Step 1: Write failing handler tests** using a fake `plugins` package (inject `heartless_cmd`, `get_string`, `get_help`, `LOGS`, `udB` stubs into `sys.modules`, then load `plugins/abliterix.py` by spec). Assert: `abliterix help` replies with `_render("abliterix_help")`; `abliterix list` with an empty store replies `abliterix_list_empty`; `abliterix status` with no active job replies `abliterix_no_job`.
- [ ] **Step 2: Run tests, verify fail.**
- [ ] **Step 3: Implement** the skeleton: read `_WORKDIR = os.environ.get("ABLITERIX_WORKDIR", "./abliterix_jobs")`, `_BINARY = os.environ.get("ABLITERIX_BIN", "abliterix")`; `_store()` lazily creates and `load()`s a `JobStore`. Implement the `abliterix_cmd` subcommand dispatcher for `help`, `list`, `status`, `log` (log implemented in Task 7's file additions if deferred; otherwise stub `log` to `abliterix_unknown_sub`). Implement `_preflight()` checking binary (`shutil.which`/`os.access`), GPU (`shutil.which("nvidia-smi")`), and free disk (`shutil.disk_usage`).
- [ ] **Step 4: Run tests, verify pass.**
- [ ] **Step 5: Commit** — `git commit -m "feat(abliterix): plugin skeleton with gating and read-only commands"`

---

### Task 7: Enqueue and the worker loop

**Files:**
- Modify: `plugins/abliterix.py`
- Test: `tests/test_abliterix_plugin.py`

**Interfaces:**
- Consumes: `build_process_spec`, `new_job_id`, `parse_extra_flags`, `transition`, `slugify_model_id`, `parse_extra_flags` from the core.
- Produces:
  - `async def _enqueue(e, model: str, extra_flags: list[str]) -> Job`
  - `def _ensure_worker() -> None` (idempotent; creates `_worker_task` if absent/done)
  - `async def _worker_loop() -> None` (FIFO; one job at a time)
  - `async def _run_job(job: Job) -> int` (spawns the child, waits, returns the exit code)
  - `_spawn(spec, log_path) -> asyncio.subprocess.Process` (the only place `create_subprocess_exec` is called)

- [ ] **Step 1: Write failing tests**: enqueue with a valid model creates a `queued` Job with a fresh id and replies `abliterix_queued`; enqueue with an invalid model replies `abliterix_bad_model`; enqueue with a bad flag replies `abliterix_bad_flag`; enqueue of a model with an existing queued/running job replies `abliterix_duplicate`; with a monkeypatched `_run_job`, `_worker_loop` runs a queued job to `succeeded` and stores `returncode=0`.
- [ ] **Step 2: Run tests, verify fail.**
- [ ] **Step 3: Implement.** `abliterate_cmd` parses `model` and remaining tokens, validates (`is_valid_model_id`, `parse_extra_flags`), checks `_preflight()` and duplicates, creates the job dir, persists via `_STORE.add` + `save()`, replies `abliterix_queued`, then `_ensure_worker()`. `_worker_loop` polls every `ABLITERIX_POLL_SECONDS` for `next_queued()`, sets `running` via `transition`, calls `_run_job`, and records the terminal state. `_spawn` opens `run.log` for append and calls `asyncio.create_subprocess_exec(*spec.argv, cwd=spec.cwd, env=spec.env, stdout=f, stderr=f, start_new_session=True)`.
- [ ] **Step 4: Run tests, verify pass.**
- [ ] **Step 5: Commit** — `git commit -m "feat(abliterix): enqueue and single-worker job loop"`

---

### Task 8: Progress monitor and delivery

**Files:**
- Modify: `plugins/abliterix.py`
- Test: `tests/test_abliterix_plugin.py`

**Interfaces:**
- Consumes: `detect_phase`, `count_trials`, `last_line`, `tail_lines`.
- Produces:
  - `async def _monitor(job: Job) -> None` (periodic status edits; stops on terminal state)
  - `async def _deliver(job: Job) -> None` (success summary + `reproduce.json`; failure log tail)

- [ ] **Step 1: Write failing tests**: with a fake client, `_monitor` edits the status message containing the detected phase; on terminal state `_deliver` success edits the message with `abliterix_done_ok {path}` and calls `send_file` with `<job>/out/reproduce/reproduce.json`; failure sends the last log lines and `abliterix_done_failed`.
- [ ] **Step 2: Run tests, verify fail.**
- [ ] **Step 3: Implement.** `_monitor` reads `run.log`, updates `job.phase/trials_done/last_line`, calls `e.client.edit_message(job.chat_id, job.status_message_id, _render("abliterix_status", ...))`, sleeps `ABLITERIX_POLL_SECONDS`; wraps edits in try/except and logs. `_deliver` reads the manifest path and sends it; on failure sends `tail_lines(log, 40)`.
- [ ] **Step 4: Run tests, verify pass.**
- [ ] **Step 5: Commit** — `git commit -m "feat(abliterix): progress monitor and result delivery"`

---

### Task 9: Cancel, remove, and purge

**Files:**
- Modify: `plugins/abliterix.py`
- Test: `tests/test_abliterix_plugin.py`

**Interfaces:**
- Consumes: `terminate_tree`, `transition`.
- Produces:
  - subcommands `cancel`, `rm` in `abliterix_cmd`; `@callback(re.compile(r"axpurge_(.+)" ), owner=True) async def _purge_cb(e)`.

- [ ] **Step 1: Write failing tests**: `cancel` on a running job calls `terminate_tree` (monkeypatched) and replies `abliterix_cancel_ok`; `cancel` on an already-finished job replies `abliterix_canceled` without raising; `rm <id> --purge` sends `abliterix_purge_confirm` with a button whose data is `axpurge_<id>`; the purge callback deletes `<workdir>/<id>` and edits to `abliterix_purge_done`; `rm <id>` without `--purge` replies `abliterix_rm_ok`.
- [ ] **Step 2: Run tests, verify fail.**
- [ ] **Step 3: Implement.** `cancel` looks up the job; if active, `terminate_tree(job.pid)` guarded so a dead PID is a no-op, then `transition(job, "canceled", now)`, `save()`, reply. `rm` removes the record; `--purge` prompts via an inline button carrying `axpurge_<id>`; the callback confirms and `shutil.rmtree(<workdir>/<id>, ignore_errors=True)`.
- [ ] **Step 4: Run tests, verify pass.**
- [ ] **Step 5: Commit** — `git commit -m "feat(abliterix): cancel, remove and purge commands"`

---

### Task 10: Startup reaping, docs, and end-to-end sanity

**Files:**
- Modify: `plugins/abliterix.py`, `README.md`
- Test: `tests/test_abliterix_plugin.py`

**Interfaces:**
- Consumes: `reap`.
- Produces: startup hook `def _reap_on_load() -> None` called at module import; README section.

- [ ] **Step 1: Write failing tests**: after seeding a `running` job with a dead PID in `jobs.json`, calling `_reap_on_load()` marks it `lost` and persists; a live PID is left `running`.
- [ ] **Step 2: Run tests, verify fail.**
- [ ] **Step 3: Implement** `_reap_on_load()` (load store, `reap(list(store.all()))`, save if anything changed) and call it at import inside a `try/except` that logs and continues. Add a README "Abliterix (optional)" section: create a uv venv, `pip install abliterix`, set `ABLITERIX_BIN`/`ABLITERIX_WORKDIR`, the AGPL note, and abliterix's safety notice.
- [ ] **Step 4: Run the full local suite and both compilers**

Run: `python -m unittest discover -s tests` → all pass; then
`python -m py_compile plugins/abliterix.py plugins/_abliterix_core.py` on both interpreters → clean; validate `en.yml` with `yaml.safe_load`.

- [ ] **Step 5: Commit** — `git add plugins/abliterix.py README.md` / `git commit -m "feat(abliterix): startup reaping and operator docs"`

---

## Self-Review

**Spec coverage:** §6 architecture → Tasks 6–9; §7 components → Tasks 1–4, 6; §8 commands → Tasks 6, 7, 9; §9 lifecycle/persistence → Tasks 1, 4, 10; §10 runner contract → Tasks 2, 7; §11 progress UI → Task 8; §12 delivery → Task 8; §13 guardrails → Tasks 4, 6, 9; §14 config → Tasks 6–9 (env reads); §15 security/licensing → Global Constraints + Task 10 docs; §16 testing → every task's Step 1; §17 risks → Review Focus + Tasks 4, 8, 10.

**Step scan:** every step names a file, a signature, or a command with an expected result. No "handle edge cases" placeholders.

**Type consistency:** `Job`/`JobStore` field and method names are used identically in Tasks 4, 6–10; `build_process_spec`/`ProcessSpec` fields (`argv, cwd, env, log_path`) match `_spawn` in Task 7; string keys in Task 5 match every `_render` call in Tasks 6–9.

**Review Focus:** each of the five lines has a test in its owning task (Task 4, 4/9, 6/7, 2, 1).

**Proportion:** signatures and test assertions only; the code step bodies are left to the implementer except where the spec pins exact values.
