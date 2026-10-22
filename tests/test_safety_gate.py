from __future__ import annotations

from microduck_claude.assembly import build_registry
from microduck_claude.robot import FakeRobot
from microduck_claude.safety import CallbackConfirmer, Dispatcher, Outcome
from microduck_claude.tools import FunctionTool, Risk, ToolRegistry, ToolResult
from tests.fakes import RecordingConfirmer

_EMPTY_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


def test_action_declined_when_not_confirmed() -> None:
    robot = FakeRobot()
    dispatcher = Dispatcher(build_registry(robot), CallbackConfirmer(lambda _p: False))
    result = dispatcher.dispatch("perform_gesture", {"gesture": "nod"})
    assert result.outcome is Outcome.DECLINED_BY_USER
    assert result.is_error
    assert robot.calls == []  # the duck never moved


def test_action_runs_when_confirmed() -> None:
    robot = FakeRobot()
    dispatcher = Dispatcher(build_registry(robot), CallbackConfirmer(lambda _p: True))
    result = dispatcher.dispatch("perform_gesture", {"gesture": "nod"})
    assert result.outcome is Outcome.EXECUTED
    assert any(c.method == "set_head" for c in robot.calls)


def test_readonly_never_consults_confirmer() -> None:
    robot = FakeRobot()
    confirmer = RecordingConfirmer(answer=False)
    dispatcher = Dispatcher(build_registry(robot), confirmer)
    result = dispatcher.dispatch("get_time", {})
    assert result.outcome is Outcome.EXECUTED
    assert confirmer.prompts == []  # a read-only tool does not touch the gate


def test_unknown_tool_refused() -> None:
    robot = FakeRobot()
    dispatcher = Dispatcher(build_registry(robot), CallbackConfirmer(lambda _p: True))
    result = dispatcher.dispatch("unlock_door", {})
    assert result.outcome is Outcome.REFUSED_UNKNOWN
    assert result.is_error


def test_tool_error_is_captured_not_raised() -> None:
    def boom(_a: dict[str, object]) -> ToolResult:
        raise RuntimeError("nope")

    registry = ToolRegistry()
    registry.register(FunctionTool("boom", "desc", Risk.READ_ONLY, _EMPTY_SCHEMA, boom))
    dispatcher = Dispatcher(registry, CallbackConfirmer(lambda _p: True))
    result = dispatcher.dispatch("boom", {})
    assert result.outcome is Outcome.ERROR
    assert result.is_error
