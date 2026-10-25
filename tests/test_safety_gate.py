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


def test_confirm_when_gates_only_the_consequential_call() -> None:
    registry = ToolRegistry()
    registry.register(
        FunctionTool(
            "act",
            "desc",
            Risk.ACTION,
            _EMPTY_SCHEMA,
            lambda _a: ToolResult("did it"),
            confirm_when=lambda a: a.get("kind") == "risky",
        )
    )
    confirmer = RecordingConfirmer(answer=False)
    dispatcher = Dispatcher(registry, confirmer, trust=True)
    assert dispatcher.dispatch("act", {"kind": "benign"}).outcome is Outcome.EXECUTED
    assert confirmer.prompts == []  # a benign call auto-approves under trust
    assert dispatcher.dispatch("act", {"kind": "risky"}).outcome is Outcome.DECLINED_BY_USER
    assert confirmer.prompts  # the consequential call is confirmed even under trust


def test_confirm_when_error_requires_confirmation() -> None:
    def boom(_a: dict[str, object]) -> bool:
        raise RuntimeError("predicate blew up")

    registry = ToolRegistry()
    registry.register(
        FunctionTool(
            "act",
            "desc",
            Risk.ACTION,
            _EMPTY_SCHEMA,
            lambda _a: ToolResult("did it"),
            confirm_when=boom,
        )
    )
    confirmer = RecordingConfirmer(answer=False)
    dispatcher = Dispatcher(registry, confirmer, trust=True)
    result = dispatcher.dispatch("act", {})
    assert result.outcome is Outcome.DECLINED_BY_USER  # fail-safe: a broken predicate → confirm
    assert confirmer.prompts


def test_locomotion_tools_are_confirm_always() -> None:
    registry = build_registry(FakeRobot())
    for name in ("explore", "turn"):
        tool = registry.get(name)
        assert tool is not None
        assert getattr(tool, "confirm_always", False) is True


def test_acrobatic_gesture_is_confirmed_even_under_trust() -> None:
    robot = FakeRobot()
    confirmer = RecordingConfirmer(answer=False)  # would decline if ever asked
    dispatcher = Dispatcher(build_registry(robot), confirmer, trust=True)
    # a benign gesture still auto-approves under trust
    assert dispatcher.dispatch("perform_gesture", {"gesture": "nod"}).outcome is Outcome.EXECUTED
    # a trained trick (roulade) is gated per-call, so it is confirmed even under trust
    result = dispatcher.dispatch("perform_gesture", {"gesture": "roulade"})
    assert result.outcome is Outcome.DECLINED_BY_USER
    assert not any(c.method == "do_behavior" for c in robot.calls)  # the trick never ran
    assert confirmer.prompts  # it asked before the trick


def test_turn_confirmation_names_the_angle_the_duck_will_turn() -> None:
    # The duck turns at most 180 degrees, so the prompt must not ask about 720.
    confirmer = RecordingConfirmer(answer=False)
    dispatcher = Dispatcher(build_registry(FakeRobot()), confirmer)
    cases = [(720, "180° to the left"), (-1000, "180° to the right"), (90, "90° to the left")]
    for degrees, expected in cases:
        dispatcher.dispatch("turn", {"degrees": degrees})
        assert expected in confirmer.prompts[-1]
    assert not any("720" in prompt or "1000" in prompt for prompt in confirmer.prompts)
