"""A small, local store of personal notes the duck remembers.

Lives in the user's home directory by default, NOT in the repo — it is personal
data, so it is never committed, and never sent anywhere except, as conversation
context, to the configured model provider.
"""

from __future__ import annotations

import json
from pathlib import Path


class MemoryStore:
    """A JSON-backed list of remembered notes. Tolerant of a missing/bad file."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path).expanduser()

    def all(self) -> list[str]:
        try:
            raw = self._path.read_text(encoding="utf-8")
        except OSError:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        memories = data.get("memories") if isinstance(data, dict) else None
        if not isinstance(memories, list):
            return []
        return [m for m in memories if isinstance(m, str)]

    def add(self, note: str) -> None:
        note = note.strip()
        if not note:
            return
        memories = self.all()
        memories.append(note)
        self._save(memories)

    def remove_matching(self, text: str) -> int:
        needle = text.strip().lower()
        memories = self.all()
        kept = [m for m in memories if needle not in m.lower()]
        removed = len(memories) - len(kept)
        if removed:
            self._save(kept)
        return removed

    def clear(self) -> None:
        self._save([])

    def _save(self, memories: list[str]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps({"memories": memories}, indent=2), encoding="utf-8")
