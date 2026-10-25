"""A small, local store of personal notes the duck remembers.

Lives in the user's home directory by default, NOT in the repo — it is personal
data, so it is never committed, and never sent anywhere except, as conversation
context, to the configured model provider.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


class MemoryStore:
    """A JSON-backed list of remembered notes. Tolerant of a missing/bad file."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path).expanduser()

    def all(self) -> list[str]:
        memories = self._load()
        return memories if memories is not None else []

    def _load(self) -> list[str] | None:
        """The stored notes; [] if there is no file, None if the file exists but is unusable."""
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        except (OSError, UnicodeDecodeError):
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        memories = data.get("memories") if isinstance(data, dict) else None
        if not isinstance(memories, list):
            return None
        return [m for m in memories if isinstance(m, str)]

    def _load_for_write(self) -> list[str]:
        """Load before a write. An unusable file is moved aside, never overwritten, so the
        notes in it can still be recovered by hand."""
        memories = self._load()
        if memories is None:
            aside = self._path.with_name(f"{self._path.name}.corrupt-{int(time.time())}")
            os.replace(self._path, aside)
            return []
        return memories

    def add(self, note: str) -> None:
        note = note.strip()
        if not note:
            return
        memories = self._load_for_write()
        memories.append(note)
        self._save(memories)

    def remove_matching(self, text: str) -> int:
        needle = text.strip().lower()
        memories = self._load_for_write()
        kept = [m for m in memories if needle not in m.lower()]
        removed = len(memories) - len(kept)
        if removed:
            self._save(kept)
        return removed

    def clear(self) -> None:
        self._save([])

    def _save(self, memories: list[str]) -> None:
        # Write a temp file and rename it over the old one, so a crash mid-write cannot leave
        # a half-written (unreadable) memory file.
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(f".{self._path.name}.tmp")
        tmp.write_text(json.dumps({"memories": memories}, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)
