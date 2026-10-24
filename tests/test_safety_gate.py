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


def test_trust_mode_runs_actions_without_asking() -> None:
    robot = FakeRobot()
    confirmer = RecordingConfirmer(answer=False)  # would decline if it were ever asked
    dispatcher = Dispatcher(build_registry(robot), confirmer, trust=True)
    result = dispatcher.dispatch("perform_gesture", {"gesture": "nod"})
    assert result.outcome is Outcome.EXECUTED
    assert confirmer.prompts == []  # trust mode never consulted the confirmer
    assert dispatcher.audit[-1].auto_approved is True


def test_trust_mode_still_confirms_a_consequential_action() -> None:
    registry = ToolRegistry()
    registry.register(
        FunctionTool(
            "risky",
            "desc",
            Risk.ACTION,
            _EMPTY_SCHEMA,
            lambda _a: ToolResult("did the risky thing"),
            confirm_always=True,
        )
    )
    confirmer = RecordingConfirmer(answer=False)
    dispatcher = Dispatcher(registry, confirmer, trust=True)
    result = dispatcher.dispatch("risky", {})
    assert result.outcome is Outcome.DECLINED_BY_USER  # confirm_always overrides trust
    assert confirmer.prompts  # it still asked, even under trust


def test_tool_error_is_captured_not_raised() -> None:
    def boom(_a: dict[str, object]) -> ToolResult:
        raise RuntimeError("nope")

    registry = ToolRegistry()
    registry.register(FunctionTool("boom", "desc", Risk.READ_ONLY, _EMPTY_SCHEMA, boom))
    dispatcher = Dispatcher(registry, CallbackConfirmer(lambda _p: True))
    result = dispatcher.dispatch("boom", {})
    assert result.outcome is Outcome.ERROR
    assert result.is_error


def test_trust_mode_still_confirms_locomotion() -> None:
    # explore and turn walk the body, so they are confirmed even under trust (CLAUDE.md #4);
    # under trust alone, a model nudged by something the duck saw could walk it unprompted.
    for name, args in (("explore", {}), ("turn", {"degrees": 90})):
        robot = FakeRobot()
        confirmer = RecordingConfirmer(answer=False)
        dispatcher = Dispatcher(build_registry(robot), confirmer, trust=True)
        result = dispatcher.dispatch(name, args)
        assert result.outcome is Outcome.DECLINED_BY_USER, name
        assert confirmer.prompts, name  # it asked, even under trust
        assert not any(c.method == "drive" for c in robot.calls), name  # the duck never moved


def test_explore_session_confirmer_approves_its_own_roaming() -> None:
    # `microduck-claude explore` is the user's standing OK for that session's locomotion.
    from microduck_claude.cli import ExploreSessionConfirmer

    robot = FakeRobot()
    dispatcher = Dispatcher(build_registry(robot), ExploreSessionConfirmer(), trust=True)
    dispatcher.dispatch("turn", {"degrees": 90})
    assert any(c.method == "drive" for c in robot.calls)
    assert robot.calls[-1].method != "drive"
