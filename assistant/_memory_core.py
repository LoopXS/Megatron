"""Framework-free core for the assistant's durable per-user memory.

``MemoryStore`` is a tiny fact store that the assistant both learns from and is
told to keep.  It imports only the standard library, so it is loaded and
unit-tested straight from its file path (see ``tests/test_memory_core.py``); the
Telethon/``udB`` adapter is supplied by the glue in ``assistant/assistant.py``.

Facts live on the injected backend as a JSON list of
``{"id", "text", "created_at"}`` objects under whatever key the backend maps a
user id to.  A missing or corrupt value is treated as an empty list rather than
an error, so one bad write can never wedge memory.
"""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass
from typing import Protocol

# Bounds on prompt growth: a few hundred short facts per user is plenty.
DEFAULT_MAX_FACTS = 100
DEFAULT_MAX_LEN = 500


@dataclass
class Fact:
    """One remembered fact."""

    id: str  # "mf-" + 6 hex
    text: str
    created_at: float


class MemoryBackend(Protocol):
    """Durable key/value storage: a ``udB`` adapter, or a dict in tests."""

    def get(self, uid: int) -> str | None: ...

    def set(self, uid: int, value: str) -> None: ...


class MemoryStore:
    """Per-user fact store persisted as a JSON list on ``backend``."""

    def __init__(
        self,
        backend,
        max_facts=DEFAULT_MAX_FACTS,
        max_len=DEFAULT_MAX_LEN,
        now=time.time,
    ):
        self.backend = backend
        self.max_facts = max_facts
        self.max_len = max_len
        self.now = now

    def list(self, user_id: int) -> list[Fact]:
        """Return this user's facts, oldest first."""
        return self._load(user_id)

    def add(self, user_id: int, text: str) -> Fact:
        """Append a fact, truncating it and dropping the oldest past the cap."""
        facts = self._load(user_id)
        fact = Fact(
            id="mf-" + secrets.token_hex(3),
            text=text[: self.max_len],
            created_at=self.now(),
        )
        facts.append(fact)
        if len(facts) > self.max_facts:
            facts = facts[len(facts) - self.max_facts :]
        self._save(user_id, facts)
        return fact

    def edit(self, user_id: int, fact_id: str, text: str) -> bool:
        """Replace a fact's text; return False when the id is unknown."""
        facts = self._load(user_id)
        for fact in facts:
            if fact.id == fact_id:
                fact.text = text[: self.max_len]
                self._save(user_id, facts)
                return True
        return False

    def forget(self, user_id: int, fact_id: str) -> bool:
        """Remove a fact; return False when the id is unknown."""
        facts = self._load(user_id)
        kept = [fact for fact in facts if fact.id != fact_id]
        if len(kept) == len(facts):
            return False
        self._save(user_id, kept)
        return True

    def render(self, user_id: int) -> str:
        """Render the facts as a system-prompt block, or "" when empty."""
        facts = self._load(user_id)
        if not facts:
            return ""
        lines = ["Things to remember:"]
        lines.extend("- [{}] {}".format(fact.id, fact.text) for fact in facts)
        return "\n".join(lines)

    def _load(self, user_id: int) -> list[Fact]:
        raw = self.backend.get(user_id)
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        facts = []
        for item in data:
            fact = _fact_from_dict(item)
            if fact is not None:
                facts.append(fact)
        return facts

    def _save(self, user_id: int, facts: list[Fact]) -> None:
        payload = [
            {"id": fact.id, "text": fact.text, "created_at": fact.created_at}
            for fact in facts
        ]
        self.backend.set(user_id, json.dumps(payload))


def _fact_from_dict(item) -> Fact | None:
    """Coerce one stored record to a Fact, or None when it is unusable."""
    if not isinstance(item, dict):
        return None
    fact_id = item.get("id")
    text = item.get("text")
    created_at = item.get("created_at")
    if not isinstance(fact_id, str) or not isinstance(text, str):
        return None
    if not isinstance(created_at, (int, float)) or isinstance(created_at, bool):
        return None
    return Fact(id=fact_id, text=text, created_at=created_at)
