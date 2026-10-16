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
from dataclasses import asdict, dataclass, field

JOB_STATES = ("queued", "running", "succeeded", "failed", "canceled", "lost")
ACTIVE_STATES = frozenset({"queued", "running"})
TERMINAL_STATES = frozenset({"succeeded", "failed", "canceled", "lost"})


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
