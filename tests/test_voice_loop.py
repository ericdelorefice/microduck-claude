from __future__ import annotations

from microduck_claude.assembly import build_registry
from microduck_claude.brain import SYSTEM_PROMPT, Brain
from microduck_claude.robot import FakeRobot
from microduck_claude.safety import Dispatcher
from microduck_claude.voice import SpeechReactor, VoiceConfirmer, VoiceLoop
from tests.fakes import FakeLLM, FakeSTT, FakeTTS, llm_text, llm_tool


def _run(stt: FakeSTT, tts: FakeTTS, llm: FakeLLM) -> FakeRobot:
    robot = FakeRobot()
    registry = build_registry(robot)
    dispatcher = Dispatcher(registry, VoiceConfirmer(stt, tts))
    brain = Brain(llm, registry, dispatcher, system=SYSTEM_PROMPT)
    VoiceLoop(brain, stt, tts, SpeechReactor(robot)).run()
    return robot


def test_voice_loop_speaks_reply_and_reacts() -> None:
    stt = FakeSTT(["hello there"])
    tts = FakeTTS()
    robot = _run(stt, tts, FakeLLM([llm_text("Quack, hi!")]))
    assert tts.spoken == ["Quack, hi!"]
    assert any(c.method == "play_sound" and c.kwargs.get("tag") == "coo" for c in robot.calls)
    assert any(c.method == "set_mouth" for c in robot.calls)


def test_voice_action_runs_on_spoken_yes() -> None:
    stt = FakeSTT(["do a happy dance", "yes"])  # request, then the spoken confirmation
    tts = FakeTTS()
    llm = FakeLLM([llm_tool("t1", "perform_gesture", {"gesture": "happy"}), llm_text("Yay!")])
    robot = _run(stt, tts, llm)
    # 'happy' plays the 'wheee' sound only if the gesture actually ran.
    assert any(c.method == "play_sound" and c.kwargs.get("tag") == "wheee" for c in robot.calls)
    assert "Yay!" in tts.spoken


def test_voice_action_blocked_on_spoken_no() -> None:
    stt = FakeSTT(["do a happy dance", "no"])
    tts = FakeTTS()
    llm = FakeLLM(
        [llm_tool("t1", "perform_gesture", {"gesture": "happy"}), llm_text("Okay, maybe later.")]
    )
    robot = _run(stt, tts, llm)
    assert not any(c.method == "play_sound" and c.kwargs.get("tag") == "wheee" for c in robot.calls)
    assert "Okay, maybe later." in tts.spoken
