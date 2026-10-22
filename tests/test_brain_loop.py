from __future__ import annotations

from microduck_claude.assembly import build_registry
from microduck_claude.brain import SYSTEM_PROMPT, Brain
from microduck_claude.robot import FakeRobot
from microduck_claude.safety import CallbackConfirmer, Dispatcher, Outcome
from tests.fakes import FakeLLM, llm_refusal, llm_text, llm_tool


def _brain(llm: FakeLLM, *, confirm: bool = True) -> tuple[Brain, FakeRobot, Dispatcher]:
    robot = FakeRobot()
    registry = build_registry(robot)
    dispatcher = Dispatcher(registry, CallbackConfirmer(lambda _p: confirm))
    return Brain(llm, registry, dispatcher, system=SYSTEM_PROMPT), robot, dispatcher


def test_plain_text_turn() -> None:
    brain, _robot, _dispatcher = _brain(FakeLLM([llm_text("Quack! Hello.")]))
    turn = brain.send("hi")
    assert turn.texts == ["Quack! Hello."]
    assert turn.refused is False


def test_readonly_tool_turn_runs_and_returns_followup() -> None:
    llm = FakeLLM([llm_tool("t1", "get_time", {}), llm_text("It is that time already.")])
    brain, _robot, dispatcher = _brain(llm)
    turn = brain.send("what time is it?")
    assert turn.texts == ["It is that time already."]
    assert any(e.name == "get_time" and e.outcome is Outcome.EXECUTED for e in dispatcher.audit)


def test_confirmed_action_moves_the_robot() -> None:
    llm = FakeLLM(
        [llm_tool("t1", "perform_gesture", {"gesture": "happy"}), llm_text("There you go!")]
    )
    brain, robot, _dispatcher = _brain(llm, confirm=True)
    brain.send("do something happy")
    assert any(c.method == "play_sound" for c in robot.calls)


def test_system_prompt_and_tools_reach_the_llm() -> None:
    llm = FakeLLM([llm_text("ok")])
    brain, _robot, _dispatcher = _brain(llm)
    brain.send("hi")
    assert llm.started is not None
    assert llm.started["system"] == SYSTEM_PROMPT
    assert any(spec["name"] == "perform_gesture" for spec in llm.started["tools"])


def test_refusal_sets_the_flag() -> None:
    brain, _robot, _dispatcher = _brain(FakeLLM([llm_refusal()]))
    turn = brain.send("something disallowed")
    assert turn.refused is True
