from __future__ import annotations

import threading
from typing import Any

import pytest

from microduck_claude.assembly import build_registry
from microduck_claude.brain import SYSTEM_PROMPT, Brain, LLMResponse
from microduck_claude.robot import FakeRobot
from microduck_claude.safety import Dispatcher
from microduck_claude.voice import (
    BargeInController,
    InterruptibleSayTTS,
    SpeechReactor,
    VoiceConfirmer,
    VoiceLoop,
)
from microduck_claude.voice import bargein as bargein_mod
from tests.fakes import FakeLLM, FakeSTT, FakeTTS


class _SlowSpeaker:
    """Simulates interruptible playback: blocks until stopped."""

    def __init__(self) -> None:
        self.spoken: list[str] = []

    def speak(self, text: str, stop: threading.Event) -> None:
        self.spoken.append(text)
        stop.wait(2.0)  # "plays" until interrupted


class _InstantSpeaker:
    def __init__(self) -> None:
        self.spoken: list[str] = []

    def speak(self, text: str, stop: threading.Event) -> None:
        self.spoken.append(text)  # finishes immediately


class _FiringDetector:
    def wait_for_speech(self, stop: threading.Event) -> bool:
        return True  # speech detected immediately


class _SilentDetector:
    def wait_for_speech(self, stop: threading.Event) -> bool:
        stop.wait(2.0)
        return False


def test_barge_in_interrupts_on_speech() -> None:
    speaker = _SlowSpeaker()
    assert BargeInController(speaker, _FiringDetector()).speak("hello") is True
    assert speaker.spoken == ["hello"]


def test_barge_in_not_interrupted_when_silent() -> None:
    speaker = _InstantSpeaker()
    assert BargeInController(speaker, _SilentDetector()).speak("hello") is False


class _ScriptedBarger:
    """A Barger that interrupts after a particular reply."""

    def __init__(self, interrupt_after: str) -> None:
        self._interrupt_after = interrupt_after
        self.spoken: list[str] = []

    def speak(self, text: str) -> bool:
        self.spoken.append(text)
        return text == self._interrupt_after


def test_voice_loop_barge_in_skips_remaining_replies() -> None:
    robot = FakeRobot()
    registry = build_registry(robot)
    stt = FakeSTT(["hi"])
    tts = FakeTTS()
    llm = FakeLLM([LLMResponse(texts=["first", "second"])])
    dispatcher = Dispatcher(registry, VoiceConfirmer(stt, tts))
    brain = Brain(llm, registry, dispatcher, system=SYSTEM_PROMPT)
    barger = _ScriptedBarger(interrupt_after="first")

    VoiceLoop(brain, stt, tts, SpeechReactor(robot), barge_in=barger).run()

    assert barger.spoken == ["first"]  # "second" was skipped due to barge-in


def test_interruptible_say_never_reads_a_reply_as_an_option(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started: list[list[str]] = []

    class _Proc:
        def __init__(self, cmd: list[str]) -> None:
            started.append(cmd)

        def poll(self) -> int:
            return 0

        def wait(self, timeout: float | None = None) -> int:
            return 0

    def fake_popen(cmd: list[str], *args: Any, **kwargs: Any) -> _Proc:
        return _Proc(cmd)

    monkeypatch.setattr(bargein_mod.subprocess, "Popen", fake_popen)
    InterruptibleSayTTS(voice="Daniel").speak("- First, a nod.", threading.Event())
    assert started == [["say", "-v", "Daniel", "--", "- First, a nod."]]
