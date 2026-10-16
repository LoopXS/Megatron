# Abliterix Integration — Design Spec

- **Date:** 2026-10-16
- **Status:** Draft for review
- **Author:** Megatron maintainers (with AI assistance)
- **Repo:** `LoopXS/Megatron`
- **Upstream dependency:** [`wuwangzhang1216/abliterix`](https://github.com/wuwangzhang1216/abliterix) (AGPL-3.0-or-later)

## 1. Context and intent

Abliterix is a GPU-heavy research CLI that removes refusal behaviour from
transformer models ("abliteration") and is driven either interactively or in a
headless mode. The goal is to make it usable from Megatron as a first-class,
command-driven feature: the owner (or a sudo user) sends a command naming a
Hugging Face model, and Megatron runs abliterix on that model, streams progress
into the chat, and hands back the exported model location plus its
reproducibility manifest.

The value is convenience and observability: starting, watching, and cancelling
long GPU jobs from Telegram instead of an SSH session.

## 2. Goals

- Start an abliterix run for a given Hugging Face model id from a chat command.
- Expose live progress and a clear terminal state (succeeded / failed / canceled).
- Cancel a running job cleanly (whole process group).
- Deliver the exported model directory path and the `reproduce.json` manifest.
- Keep abliterix's heavy dependencies (torch, transformers, bitsandbytes,
  optuna) **out of Megatron's own environment**.
- Restrict all control to owner and sudo users.

## 3. Non-goals (out of scope)

- Uploading results to the Hugging Face Hub.
- The abliterix Gradio Web UI (`--ui`).
- Interactive result menus, trial selection, or resume prompts.
- Multi-GPU scheduling or running more than one job at a time.
- Generating new model configs (`scripts/generate_configs.py`).
- Chatting with or serving the produced model.
- Modifying abliterix itself.

## 4. Hard constraints

1. **GPU required.** Abliterix needs a real accelerator. This feature only works
   on a host that has one; the runner must refuse cleanly otherwise.
2. **Local execution.** The Megatron bot process and the GPU are on the same
   machine (decided). No remote/SSH transport.
3. **Long-running.** A job can take minutes to hours and downloads multi-GB
   models. The design must be asynchronous and restart-tolerant, not a one-shot
   command reply.
4. **Headless only.** Abliterix's default mode ends in an interactive menu, so
   every invocation must pass `--non-interactive`.
5. **Dependency isolation.** Abliterix is installed in its own virtualenv and
   invoked by absolute path. Nothing is added to Megatron's requirements.
6. **AGPL.** Both projects are AGPL-3.0; running abliterix as a separate
   process keeps a clean boundary.

## 5. Shared understanding

### Stated by the requester
- Integrate abliterix and control it through specific commands.
- Run it where the bot already runs (same machine, local GPU).
- Restrict usage to owner and sudo users.
- Deliver results as a path on disk plus the manifest; do not push to HF or send
  the (often multi-GB) model through Telegram.
- Implement it in the main bot's plugin surface.

### Assumptions (correct these if wrong)
- `ABLITERIX_BIN` points at a console script inside a prepared venv; preparing
  that venv is an operator task documented in the README, not automated here.
- Only one job runs at a time; the GPU is dedicated to it.
- A working `abliterix` installation can run `--non-interactive` successfully on
  at least one model on the target host.
- The default evaluation is deterministic/offline; LLM-judge mode may require an
  `OPENROUTER_API_KEY` in the environment, which the operator supplies outside
  the bot.

### Success criteria
- `/abliterate Qwen/Qwen3-4B-Instruct-2507` enqueues and eventually completes a
  real abliterix run, with progress visible in the chat throughout.
- `/abliterix cancel <id>` stops a running job and frees the GPU.
- A finished job reports the `out/` path and sends `reproduce.json`.
- No new ML dependency is added to Megatron's environment.
- Non-owner, non-sudo users cannot start, view, or cancel jobs.

## 6. Architecture

A **job runner**. Megatron owns scheduling, state, and the chat UX; abliterix
owns the ML work and runs as an external child process.

```
Telegram (owner/sudo)
        │  commands
        ▼
plugins/abliterix.py  ──────────────►  progress message (edited in chat)
        │  pure calls
        ▼
plugins/_abliterix_core.py  (state machine, persistence, flag build, log parse)
        │  spawn / signal
        ▼
<ABLITERIX_BIN> --non-interactive …   (separate venv, child process group)
        │  stdout/stderr
        ▼
<workdir>/<job>/run.log  +  <job>/checkpoint  +  <job>/out
```

## 7. Components and boundaries

| File | Responsibility | Depends on |
|---|---|---|
| `plugins/abliterix.py` | Command handlers, owner/sudo gating, single-worker queue loop, progress message edits, delivery. | CythonX runtime, `_abliterix_core` |
| `plugins/_abliterix_core.py` | Pure logic: job records, state transitions, `jobs.json` read/write, allowlisted flag construction, subprocess spec, log-tail parsing, process spawn/kill wrappers behind injectable functions. | stdlib only (no Telethon/CythonX) |

The core is deliberately free of framework imports so it can be unit-tested in
isolation, matching the existing `_session_core.py` / `_api_core.py` pattern.

## 8. Command reference

All commands are owner/sudo only, via `@heartless_cmd(..., owner_only=True)`.

| Command | Behaviour |
|---|---|
| `/abliterate <hf-model-id> [safe flags…]` | Validate input, run preflight, enqueue, reply with job id and start the status message. |
| `/abliterix status [id]` | Show the active job, or the given job: state, model, elapsed, phase, trial count, output path. |
| `/abliterix list` | List jobs (id, state, model, short model slug, elapsed). |
| `/abliterix log <id> [n]` | Send the last `n` lines (default 40, max 200) of `run.log`, monospaced. |
| `/abliterix cancel <id>` | Terminate the job's process group; mark `canceled`. |
| `/abliterix rm <id> [--purge]` | Forget a finished job; `--purge` first shows an inline ✅/✖️ confirmation, then deletes its directory. |
| `/abliterix help` | Usage summary. |

Note: abliterix itself uses the `--model` shorthand for `--model.model-id`; the
bot passes the fully-qualified `--model.model-id` to avoid ambiguity.

## 9. Job lifecycle and persistence

States: `queued → running → succeeded | failed | canceled`, plus `lost`
(a `running` job whose PID no longer exists at startup).

Record fields: `id`, `model`, `state`, `extra_flags`, `created_at`,
`started_at`, `finished_at`, `pid`, `returncode`, `phase`, `trials_done`,
`chat_id`, `status_message_id`, `workdir`, `out_dir`, `error`.

- One `jobs.json` under `<workdir>`, written atomically (temp file + rename).
- IDs are short, unique, sortable (e.g. `ax-` + 6 hex).
- **Restart reaping:** on plugin load, any `running` job whose `pid` is absent is
  marked `lost`; a matching live process is re-adopted for monitoring.
- The queue is FIFO; the worker loop processes one job at a time.

## 10. Runner contract

Invocation (built by the core, never by string concatenation of user input):

```
<ABLITERIX_BIN> --model.model-id <model>
    --non-interactive
    --optimization.checkpoint-dir <workdir>/<id>/checkpoint
    --non-interactive-output-dir <workdir>/<id>/out
    [allowlisted extra flags]
```

- `cwd = <workdir>/<id>`
- `env`: `NO_COLOR=1`, `PYTHONUNBUFFERED=1`, `TERM=dumb`, `PYTHONIOENCODING=utf-8`
  (inherits the rest, including any operator-provided `OPENROUTER_API_KEY`).
- `stdout` and `stderr` are appended to `<workdir>/<id>/run.log`.
- `start_new_session=True` so cancellation signals the whole group.
- Per-job checkpoint dir avoids the shared-default collision identified in the
  probe.
- The output dir must be empty/absent; the job dir is created fresh.

**Extra-flag allowlist.** Default allowlist (configurable via
`ABLITERIX_ALLOWED_FLAGS`): `--optimization.n-trials`, `--optimization.seed`,
`--model.quant-method`, `--inference.batch-size`, `--inference.max-batch-size`,
`--model.backend`. Unknown or dangerous flags (notably `--ui`, `--reproduce`,
`--model`, `--non-interactive*`, and anything targeting a path) are rejected
with an explanatory error.

## 11. Progress UI

- On enqueue, the bot replies with a status message and remembers its id.
- A monitor task refreshes the status message on an interval
  (`ABLITERIX_POLL_SECONDS`, default 20s) and immediately on phase changes.
- The status body shows: state, model, elapsed, detected phase, completed-trial
  count, and the most recent log line.
- **Phase detection** matches stable printed substrings, e.g.
  `Loading benign prompts`, `Computing per-layer steering vectors`,
  `Determining optimal batch size`, `Non-interactive mode: optimization
  finished`. If no marker matches, the phase simply reads "running" — the UI
  degrades gracefully rather than breaking.
- Editing failures (e.g. message too old) are logged and ignored; the job is
  unaffected.

## 12. Delivery

- **Success:** edit the status message to a summary including the model slug,
  final trial metrics if parseable, and the absolute `out/` path; then send
  `<out>/reproduce/reproduce.json` as a document.
- **Failure:** send the last ~40 lines of `run.log` and the error string.
- **Canceled:** confirm and note that partial checkpoints remain in the job dir.

## 13. Guardrails and error handling

- **Preflight before enqueue:** `nvidia-smi` present/zero-exit; free disk at
  `<workdir>` ≥ `ABLITERIX_MIN_FREE_GB` (default 40); `<ABLITERIX_BIN>` exists
  and is executable. Fail fast with a specific reason.
- **Model id validation:** matches a Hugging Face `owner/name` shape; otherwise
  reject before enqueue.
- **Duplicate detection:** refuse to enqueue the same model if an identical job
  is already `queued` or `running`.
- **Cancellation:** `SIGTERM` to the process group, wait a grace period
  (`ABLITERIX_KILL_GRACE`, default 20s), then `SIGKILL`.
- **Timeouts:** optional `ABLITERIX_MAX_RUNTIME` (seconds); exceeded → cancel
  and mark `failed`.
- **Missing binary/venv:** clear message pointing at the README setup section.

## 14. Configuration

Environment variables (defaults shown), overridable later via `udB` keys:

| Variable | Default | Purpose |
|---|---|---|
| `ABLITERIX_BIN` | `abliterix` | Path to the console script in the venv. |
| `ABLITERIX_WORKDIR` | `./abliterix_jobs` | Root for job directories and `jobs.json`. |
| `ABLITERIX_MIN_FREE_GB` | `40` | Free-disk preflight threshold. |
| `ABLITERIX_POLL_SECONDS` | `20` | Status refresh interval. |
| `ABLITERIX_ALLOWED_FLAGS` | curated list | Comma-separated allowlist of pass-through flags. |
| `ABLITERIX_KILL_GRACE` | `20` | Seconds between SIGTERM and SIGKILL. |
| `ABLITERIX_MAX_RUNTIME` | unset | Optional hard cap in seconds. |

## 15. Security and licensing

- Owner/sudo gating on every command.
- No shell interpolation: arguments are passed as an `exec` argv list; user input
  never reaches a shell.
- The HF token and any judge credentials live only in the environment; the bot
  never reads, stores, or echoes them.
- `--purge` is the only filesystem-deleting path, gated by an inline
  confirmation button and confined to `<workdir>/<id>`.
- Abliterix deliberately weakens model safeguards and may produce unsafe
  content; the README must state this and cite abliterix's own safety notice.
- Both projects are AGPL-3.0; abliterix is invoked as a separate process and is
  not linked into Megatron.

## 16. Testing strategy

- **Pure core unit tests** (stdlib `unittest`, run locally, `tests/` is
  gitignored as with the existing suites): state transitions and illegal
  transitions; `jobs.json` round-trip and atomic write; flag allowlist
  accept/reject; argv construction; log-tail parsing and phase detection;
  reaping logic with a fake PID liveness function.
- **Handler tests:** fake subprocess + fake event objects to assert owner/sudo
  gating, enqueue/duplicate refusal, progress edit calls, cancel signalling,
  and delivery (manifest send).
- Follow TDD: write the failing test first for each core unit.

## 17. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Progress parsing depends on upstream strings. | Match a small set of stable substrings; fall back to "running" without erroring. |
| A job holds the GPU exclusively. | One job at a time; clear `queued` state for the rest. |
| Bot restart during a run. | Re-adopt by PID or mark `lost`; never silently drop. |
| Upstream flag/CLI changes. | Centralize the invocation in one core function; a single place to update. |
| Cancellation leaves orphaned workers (vLLM/TP). | Kill the whole process group, not just the parent. |
| Large exports fill the disk. | Free-disk preflight; `--purge` for cleanup. |

## 18. Open questions

None blocking. Assumptions in §5 are the items to confirm during review.
