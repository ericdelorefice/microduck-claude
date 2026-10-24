from __future__ import annotations

from microduck_claude.assembly import build_registry
from microduck_claude.brain import SYSTEM_PROMPT, Brain
from microduck_claude.robot import FakeRobot
from microduck_claude.safety import CallbackConfirmer, Dispatcher
from microduck_claude.voice import FasterWhisperSTT, SpeechReactor, VoiceLoop
from tests.fakes import FakeLLM, FakeTTS, llm_text


def test_listen_returns_transcribed_utterance() -> None:
    stt = FasterWhisperSTT(recorder=lambda: "AUDIO", transcriber=lambda _a: "hello there")
    utterance = stt.listen()
    assert utterance is not None
    assert utterance.text == "hello there"


def test_listen_none_when_recorder_stops() -> None:
    stt = FasterWhisperSTT(recorder=lambda: None, transcriber=lambda _a: "x")
    assert stt.listen() is None


def test_empty_transcript_is_an_empty_utterance_not_end_of_session() -> None:
    # None ends the voice session, so a noise that transcribes to nothing must not return it.
    stt = FasterWhisperSTT(recorder=lambda: "AUDIO", transcriber=lambda _a: "   ")
    utterance = stt.listen()
    assert utterance is not None
    assert utterance.text == ""


def test_voice_loop_keeps_listening_after_an_empty_transcript() -> None:
    clips = iter(["AUDIO", "AUDIO"])  # then None: the mic stops
    transcripts = iter(["", "hello duck"])  # a cough, then real speech
    stt = FasterWhisperSTT(
        recorder=lambda: next(clips, None), transcriber=lambda _a: next(transcripts)
    )
    tts = FakeTTS()
    robot = FakeRobot()
    registry = build_registry(robot)
    dispatcher = Dispatcher(registry, CallbackConfirmer(lambda _p: False))
    brain = Brain(FakeLLM([llm_text("Quack!")]), registry, dispatcher, system=SYSTEM_PROMPT)
    VoiceLoop(brain, stt, tts, SpeechReactor(robot)).run()
    assert tts.spoken == ["Quack!"]  # the cough did not end the session
