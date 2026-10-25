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
    """What a tool returns.

    ``content`` is text handed back to the model as data. ``image_png`` is an optional
    image (e.g. a camera frame) for a vision-capable model — text-only providers ignore it.
    """

    content: str
    ok: bool = True
    image_png: bytes | None = None


class Tool(Protocol):
    """Structural contract every tool satisfies.

    ``confirm_always`` is part of the contract so a consequential tool (and any
    plugin-supplied tool) can declare that it must be confirmed even under trust
    mode; the dispatcher honours it. A tool that does not set it defaults to False.
    """

    name: str
    description: str
    risk: Risk
    input_schema: dict[str, Any]
    confirm_always: bool

    def run(self, arguments: dict[str, Any]) -> ToolResult: ...


ToolFn = Callable[[dict[str, Any]], ToolResult]
PreviewFn = Callable[[dict[str, Any]], str]
ConfirmWhenFn = Callable[[dict[str, Any]], bool]


@dataclass
class FunctionTool:
    """A tool backed by a plain function. ``preview`` renders a human confirmation line."""

    name: str
    description: str
    risk: Risk
    input_schema: dict[str, Any]
    func: ToolFn
    preview: PreviewFn | None = None
    confirm_always: bool = False  # a consequential action: confirm even under trust mode
    # An optional per-call predicate: when it returns True for the given arguments, this
    # call is treated as confirm_always (confirmed even under trust). It lets one tool gate
    # only its consequential inputs (e.g. perform_gesture confirming an acrobatic trick but
    # not a nod) without splitting into two tools. A missing/failed predicate is fail-safe.
    confirm_when: ConfirmWhenFn | None = None

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
