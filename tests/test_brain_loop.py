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


def test_on_text_hears_each_line_before_the_tools_it_introduces_run() -> None:
    # "Let me look around" should be said before the duck looks, not after the whole round.
    llm = FakeLLM(
        [
            llm_tool("t1", "perform_gesture", {"gesture": "happy"}, text="Watch this!"),
            llm_text("Ta-da."),
        ]
    )
    brain, robot, _dispatcher = _brain(llm, confirm=True)
    heard: list[tuple[str, int]] = []
    turn = brain.send("do something", on_text=lambda t: heard.append((t, len(robot.calls))))
    assert [t for t, _ in heard] == ["Watch this!", "Ta-da."] == turn.texts
    assert heard[0][1] == 0  # spoken before the gesture touched the robot
    assert heard[1][1] > 0


def _capped_brain(llm: FakeLLM, limit: int) -> tuple[Brain, Dispatcher]:
    registry = build_registry(FakeRobot())
    dispatcher = Dispatcher(registry, CallbackConfirmer(lambda _p: True))
    return Brain(
        llm, registry, dispatcher, system=SYSTEM_PROMPT, max_tool_iterations=limit
    ), dispatcher


def _executed(dispatcher: Dispatcher) -> list[str]:
    return [e.name for e in dispatcher.audit if e.outcome is Outcome.EXECUTED]


def test_a_call_past_the_limit_is_answered_not_dropped() -> None:
    # The duck asks for a third move with a limit of two. That move must not run, but the
    # model is told so in the same turn (not a turn later) and gets to say it in words.
    gesture = {"gesture": "happy"}
    llm = FakeLLM(
        [
            llm_tool("t1", "perform_gesture", gesture),
            llm_tool("t2", "perform_gesture", gesture),
            llm_tool("t3", "perform_gesture", gesture, text="And one more!"),
            llm_text("That's all my moves for now — I'll do it next time."),
        ]
    )
    brain, dispatcher = _capped_brain(llm, limit=2)
    turn = brain.send("dance")
    assert _executed(dispatcher) == ["perform_gesture", "perform_gesture"]  # never a third
    skipped = llm.tool_results[-1]
    assert [r.tool_call_id for r in skipped] == ["t3"]
    assert skipped[0].is_error and "not run" in skipped[0].content.lower()
    assert turn.texts[-1] == "That's all my moves for now — I'll do it next time."
    assert turn.capped is True


def test_nothing_runs_past_the_limit_even_if_the_model_keeps_asking() -> None:
    llm = FakeLLM(
        [
            llm_tool("t1", "get_time", {}),
            llm_tool("t2", "get_time", {}),
            llm_tool("t3", "perform_gesture", {"gesture": "happy"}),  # over the limit
            llm_tool("t4", "perform_gesture", {"gesture": "happy"}),  # ignores the notice
        ]
    )
    brain, dispatcher = _capped_brain(llm, limit=2)
    turn = brain.send("go")
    assert _executed(dispatcher) == ["get_time", "get_time"]
    assert turn.capped is True  # and the loop ended: the fake would raise if called again


def test_an_uncapped_turn_is_not_flagged() -> None:
    brain, _dispatcher = _capped_brain(FakeLLM([llm_text("hi")]), limit=2)
    assert brain.send("hi").capped is False


def test_refusal_sets_the_flag() -> None:
    brain, _robot, _dispatcher = _brain(FakeLLM([llm_refusal()]))
    turn = brain.send("something disallowed")
    assert turn.refused is True
