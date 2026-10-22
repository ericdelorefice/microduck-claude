"""Tool primitives: risk classes, the Tool contract, and the allow-list registry."""

from __future__ import annotations

import enum
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol


class Risk(enum.Enum):
    """How much trust a tool needs.

    READ_ONLY tools have no side effects and run without friction. ACTION tools
    change something and require explicit user confirmation (see the dispatcher).
    """

    READ_ONLY = "read_only"
    ACTION = "action"


@dataclass
class ToolResult:
    """What a tool returns. ``content`` is text handed back to the model as data."""

    content: str
    ok: bool = True


class Tool(Protocol):
    """Structural contract every tool satisfies."""

    name: str
    description: str
    risk: Risk
    input_schema: dict[str, Any]

    def run(self, arguments: dict[str, Any]) -> ToolResult: ...


ToolFn = Callable[[dict[str, Any]], ToolResult]
PreviewFn = Callable[[dict[str, Any]], str]


@dataclass
class FunctionTool:
    """A tool backed by a plain function. ``preview`` renders a human confirmation line."""

    name: str
    description: str
    risk: Risk
    input_schema: dict[str, Any]
    func: ToolFn
    preview: PreviewFn | None = None

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        return self.func(arguments)


class ToolRegistry:
    """The allow-list. A tool can be dispatched only if it is registered here."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"duplicate tool name: {tool.name!r}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def specs(self) -> list[dict[str, Any]]:
        """Tool definitions in the shape the Anthropic Messages API expects."""
        return [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in self._tools.values()
        ]
