from __future__ import annotations

import pytest

from microduck_claude.robot import FakeRobot
from microduck_claude.tools import FunctionTool, Risk, ToolRegistry, ToolResult, build_core_tools

_EMPTY_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


def _tool(name: str, risk: Risk = Risk.READ_ONLY) -> FunctionTool:
    return FunctionTool(name, "desc", risk, _EMPTY_SCHEMA, lambda _a: ToolResult("ok"))


def test_core_tools_registered() -> None:
    registry = ToolRegistry()
    for tool in build_core_tools(FakeRobot()):
        registry.register(tool)
    assert set(registry.names()) == {
        "get_time",
        "list_gestures",
        "get_robot_status",
        "see",
        "perform_gesture",
    }


def test_duplicate_registration_rejected() -> None:
    registry = ToolRegistry()
    registry.register(_tool("x"))
    with pytest.raises(ValueError):
        registry.register(_tool("x"))


def test_get_and_contains() -> None:
    registry = ToolRegistry()
    registry.register(_tool("x"))
    assert "x" in registry
    assert registry.get("x") is not None
    assert "y" not in registry
    assert registry.get("y") is None


def test_specs_have_api_shape() -> None:
    registry = ToolRegistry()
    registry.register(_tool("x"))
    spec = registry.specs()[0]
    assert set(spec) == {"name", "description", "input_schema"}
