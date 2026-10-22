"""Tools that let the duck recall, remember, and forget personal notes.

``recall_memories`` is read-only; ``remember`` and ``forget`` write to the local
store and so are ACTIONs (they go through the confirmation gate). Recalled notes
come back as tool-result *data*, never as instructions.
"""

from __future__ import annotations

from typing import Any

from ..tools.base import FunctionTool, Risk, Tool, ToolResult
from .store import MemoryStore

_NO_ARGS: dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": False}


def build_memory_tools(store: MemoryStore) -> list[Tool]:
    def _recall(_: dict[str, Any]) -> ToolResult:
        memories = store.all()
        if not memories:
            return ToolResult("No memories yet.")
        return ToolResult("You remember:\n" + "\n".join(f"- {m}" for m in memories))

    def _remember(arguments: dict[str, Any]) -> ToolResult:
        note = arguments.get("note")
        if not isinstance(note, str) or not note.strip():
            return ToolResult("missing required string argument 'note'", ok=False)
        store.add(note)
        return ToolResult(f"Remembered: {note.strip()}")

    def _forget(arguments: dict[str, Any]) -> ToolResult:
        about = arguments.get("about")
        if not isinstance(about, str) or not about.strip():
            return ToolResult("missing required string argument 'about'", ok=False)
        removed = store.remove_matching(about)
        return ToolResult(f"Forgot {removed} memory(ies) about {about.strip()!r}.")

    note_schema: dict[str, Any] = {
        "type": "object",
        "properties": {"note": {"type": "string", "description": "The fact to remember."}},
        "required": ["note"],
        "additionalProperties": False,
    }
    about_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "about": {"type": "string", "description": "Text to match memories to forget."}
        },
        "required": ["about"],
        "additionalProperties": False,
    }
    return [
        FunctionTool(
            "recall_memories",
            "Recall what you remember about the person.",
            Risk.READ_ONLY,
            _NO_ARGS,
            _recall,
        ),
        FunctionTool(
            "remember",
            "Remember a fact about the person for later conversations.",
            Risk.ACTION,
            note_schema,
            _remember,
            preview=lambda a: f"remember: {a.get('note')}",
        ),
        FunctionTool(
            "forget",
            "Forget remembered facts that match some text.",
            Risk.ACTION,
            about_schema,
            _forget,
            preview=lambda a: f"forget memories about {a.get('about')!r}",
        ),
    ]
