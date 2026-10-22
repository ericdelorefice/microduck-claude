from __future__ import annotations

from microduck_claude.assembly import build_registry
from microduck_claude.brain import SYSTEM_PROMPT, Brain
from microduck_claude.robot import FakeRobot
from microduck_claude.safety import CallbackConfirmer, Dispatcher, Outcome
from tests.fakes import FakeAnthropic, refusal_response, text_response, tool_response


def _brain(client: FakeAnthropic, *, confirm: bool = True) -> tuple[Brain, FakeRobot, Dispatcher]:
    robot = FakeRobot()
    registry = build_registry(robot)
    dispatcher = Dispatcher(registry, CallbackConfirmer(lambda _p: confirm))
    return Brain(client, registry, dispatcher, system=SYSTEM_PROMPT), robot, dispatcher


def test_plain_text_turn() -> None:
    brain, _robot, _dispatcher = _brain(FakeAnthropic([text_response("Quack! Hello.")]))
    turn = brain.send("hi")
    assert turn.texts == ["Quack! Hello."]
    assert turn.refused is False


def test_readonly_tool_turn_runs_and_returns_followup() -> None:
    client = FakeAnthropic(
        [
            tool_response("t1", "get_time", {}),
            text_response("It is that time already."),
        ]
    )
    brain, _robot, dispatcher = _brain(client)
    turn = brain.send("what time is it?")
    assert turn.texts == ["It is that time already."]
    assert any(e.name == "get_time" and e.outcome is Outcome.EXECUTED for e in dispatcher.audit)


def test_confirmed_action_moves_the_robot() -> None:
    client = FakeAnthropic(
        [
            tool_response("t1", "perform_gesture", {"gesture": "happy"}),
            text_response("There you go!"),
        ]
    )
    brain, robot, _dispatcher = _brain(client, confirm=True)
    brain.send("do something happy")
    assert any(c.method == "play_sound" for c in robot.calls)


def test_system_prompt_and_tools_reach_the_client() -> None:
    client = FakeAnthropic([text_response("ok")])
    brain, _robot, _dispatcher = _brain(client)
    brain.send("hi")
    call = client.messages.calls[0]
    assert call["system"] == SYSTEM_PROMPT
    assert any(spec["name"] == "perform_gesture" for spec in call["tools"])
    assert call["model"]


def test_refusal_sets_the_flag() -> None:
    brain, _robot, _dispatcher = _brain(FakeAnthropic([refusal_response()]))
    turn = brain.send("something disallowed")
    assert turn.refused is True
