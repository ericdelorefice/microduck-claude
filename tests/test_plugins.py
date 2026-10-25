from __future__ import annotations

from microduck_claude.assembly import build_registry
from microduck_claude.plugins import discover_providers
from microduck_claude.robot import FakeRobot
from microduck_claude.safety import CallbackConfirmer, Dispatcher, Outcome
from microduck_claude.tools import FunctionTool, Risk, Tool, ToolResult

_EMPTY_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


class _Provider:
    """A stand-in private tool provider contributing one action tool."""

    def get_tools(self) -> list[Tool]:
        return [
            FunctionTool(
                "secret_action",
                "Do a private thing.",
                Risk.ACTION,
                _EMPTY_SCHEMA,
                lambda _a: ToolResult("did the private thing"),
            )
        ]


def test_core_registry_has_no_plugin_tools() -> None:
    registry = build_registry(FakeRobot())
    assert set(registry.names()) == {
        "get_time",
        "list_gestures",
        "get_robot_status",
        "see",
        "look_around",
        "perform_gesture",
        "explore",
        "turn",
    }


def test_supplied_provider_tools_are_registered() -> None:
    registry = build_registry(FakeRobot(), providers=[_Provider()])
    assert "secret_action" in registry


def test_plugin_action_is_subject_to_the_same_gate() -> None:
    robot = FakeRobot()
    registry = build_registry(robot, providers=[_Provider()])
    dispatcher = Dispatcher(registry, CallbackConfirmer(lambda _p: False))
    result = dispatcher.dispatch("secret_action", {})
    assert result.outcome is Outcome.DECLINED_BY_USER


def test_discover_providers_returns_a_list() -> None:
    # No providers are installed by default; discovery must never error.
    assert isinstance(discover_providers(), list)
