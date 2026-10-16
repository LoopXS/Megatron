"""Framework-free core for the abliterix job runner.

This module holds every decision the plugin makes — job records, durable
state, input validation, the argv/env for the abliterix child process, log
parsing and process control — using only the standard library.  It imports
nothing from CythonX/Telethon so it can be loaded and unit-tested in
isolation (see ``tests/test_abliterix_core.py``).  The Telethon glue lives
in ``plugins/abliterix.py``.
"""

import json
import os
import random
import re
import string
from dataclasses import asdict, dataclass, field

JOB_STATES = ("queued", "running", "succeeded", "failed", "canceled", "lost")
ACTIVE_STATES = frozenset({"queued", "running"})
TERMINAL_STATES = frozenset({"succeeded", "failed", "canceled", "lost"})

# Extra flags an operator may pass on top of the headless defaults.  Anything
# outside this list is rejected so a typo or an injected shell metacharacter
# can never reach the child process.
DEFAULT_ALLOWED_FLAGS = (
    "--optimization.n-trials",
    "--optimization.seed",
    "--model.quant-method",
    "--model.backend",
    "--inference.batch-size",
    "--inference.max-batch-size",
)

_MODEL_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*")
_FORBIDDEN_RE = re.compile(r"[;`$|&\n\r]")
_ID_ALPHABET = string.hexdigits.lower()[:16]


@dataclass
class Job:
    """One abliterix run and everything the chat needs to report on it."""

    id: str
    model: str
    state: str = "queued"
    extra_flags: list = field(default_factory=list)
    created_at: float = 0.0
    started_at: float | None = None
    finished_at: float | None = None
    pid: int | None = None
    returncode: int | None = None
    phase: str = ""
    trials_done: int = 0
    last_line: str = ""
    chat_id: int | None = None
    status_message_id: int | None = None
    workdir: str = ""
    out_dir: str = ""
    error: str = ""

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        known = set(cls.__dataclass_fields__)
        return cls(**{key: value for key, value in data.items() if key in known})

    def is_terminal(self):
        return self.state in TERMINAL_STATES

    def elapsed(self, now):
        start = self.started_at if self.started_at is not None else self.created_at
        end = self.finished_at if self.finished_at is not None else now
        return max(0.0, end - start)


class JobStore:
    """A tiny durable collection of :class:`Job` records.

    ``save`` writes atomically (temp file + ``os.replace``) so a crash mid
    write cannot corrupt the store; ``load`` is forgiving and treats any
    unreadable file as an empty store.
    """

    def __init__(self, workdir, path=None):
        self.workdir = workdir
        self.path = path or os.path.join(workdir, "jobs.json")
        self._jobs = {}

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as handle:
                raw = json.load(handle)
            items = raw if isinstance(raw, list) else raw.get("jobs", [])
            self._jobs = {
                item["id"]: Job.from_dict(item)
                for item in items
                if isinstance(item, dict) and "id" in item
            }
        except (OSError, ValueError, TypeError, KeyError):
            self._jobs = {}

    def save(self):
        os.makedirs(self.workdir, exist_ok=True)
        tmp = self.path + ".tmp"
        payload = [job.to_dict() for job in self._jobs.values()]
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        os.replace(tmp, self.path)

    def add(self, job):
        self._jobs[job.id] = job

    def get(self, job_id):
        return self._jobs.get(job_id)

    def all(self):
        return list(self._jobs.values())

    def remove(self, job_id):
        return self._jobs.pop(job_id, None) is not None

    def update(self, job):
        self._jobs[job.id] = job

    def next_queued(self):
        queued = [job for job in self._jobs.values() if job.state == "queued"]
        if not queued:
            return None
        return min(queued, key=lambda job: job.created_at)

    def find_active(self, model):
        for job in self._jobs.values():
            if job.model == model and job.state in ACTIVE_STATES:
                return job
        return None


@dataclass
class ProcessSpec:
    """Everything needed to launch one abliterix run."""

    argv: list
    cwd: str
    env: dict
    log_path: str


def is_valid_model_id(text):
    """A Hugging Face model id: ``owner/name`` with safe characters."""
    return bool(_MODEL_ID_RE.fullmatch(text or ""))


def slugify_model_id(model):
    """A filesystem-safe directory name derived from a model id."""
    return re.sub(r"[^a-z0-9._-]+", "-", model.lower().replace("/", "__"))


def new_job_id(existing, rng=None):
    """A short ``ax-`` id that is not already in ``existing``."""
    rng = rng or random
    seen = set(existing)
    while True:
        job_id = "ax-" + "".join(rng.choice(_ID_ALPHABET) for _ in range(6))
        if job_id not in seen:
            return job_id


def parse_extra_flags(tokens, allowed):
    """Validate ``--flag value`` pairs against ``allowed``.

    Returns ``(flattened_flags, error_key)``; on any problem the flags list
    is empty and ``error_key`` is ``"abliterix_bad_flag"``.
    """
    allowed = set(allowed)
    result = []
    index = 0
    while index < len(tokens):
        flag = tokens[index]
        if flag not in allowed:
            return [], "abliterix_bad_flag"
        if index + 1 >= len(tokens):
            return [], "abliterix_bad_flag"
        value = tokens[index + 1]
        if value.startswith("--") or _FORBIDDEN_RE.search(value):
            return [], "abliterix_bad_flag"
        result.extend((flag, value))
        index += 2
    return result, None


def build_env(base=None):
    """Child environment: inherit ``base`` (or ``os.environ``) and force
    non-interactive, unbuffered, colourless output."""
    env = dict(os.environ if base is None else base)
    env.update(
        {
            "NO_COLOR": "1",
            "PYTHONUNBUFFERED": "1",
            "TERM": "dumb",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    return env


def build_process_spec(binary, model, job_dir, extra_flags, base_env=None):
    """Assemble the argv, cwd, env and log path for one run.

    ``--non-interactive`` is mandatory: without it abliterix ends in a
    ``questionary`` menu that would block a headless worker.
    """
    argv = [
        binary,
        "--model.model-id",
        model,
        "--non-interactive",
        "--optimization.checkpoint-dir",
        os.path.join(job_dir, "checkpoint"),
        "--non-interactive-output-dir",
        os.path.join(job_dir, "out"),
    ]
    argv.extend(extra_flags)
    return ProcessSpec(
        argv=argv,
        cwd=job_dir,
        env=build_env(base_env),
        log_path=os.path.join(job_dir, "run.log"),
    )


# Stable substrings abliterix prints as it advances through a run.  The last
# one seen in the log wins, so the order here does not matter.
PHASE_MARKERS = (
    ("Loading benign prompts", "loading data"),
    ("Determining optimal batch size", "tuning batch size"),
    ("Computing per-layer steering vectors", "computing vectors"),
    ("Non-interactive mode: optimization finished", "finishing"),
    ("Exporting verified trial", "exporting"),
)

_TRIAL_RE = re.compile(r"trial\s*#?\s*(\d+)", re.IGNORECASE)


def detect_phase(text):
    """The latest known phase label found in ``text`` (or ``"running"``)."""
    best_index = -1
    best_label = "running"
    for marker, label in PHASE_MARKERS:
        index = text.rfind(marker)
        if index > best_index:
            best_index = index
            best_label = label
    return best_label


def count_trials(text):
    """The highest trial number mentioned in ``text`` (or ``0``)."""
    numbers = [int(match) for match in _TRIAL_RE.findall(text)]
    return max(numbers) if numbers else 0


def last_line(text):
    """The final non-empty line of ``text``, truncated to 200 chars."""
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line:
            return line[:200]
    return ""


def tail_lines(text, n):
    """The last ``n`` lines of ``text`` joined with newlines."""
    if n <= 0:
        return ""
    return "\n".join(text.splitlines()[-n:])
