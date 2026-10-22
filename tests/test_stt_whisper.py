from __future__ import annotations

from microduck_claude.voice import FasterWhisperSTT


def test_listen_returns_transcribed_utterance() -> None:
    stt = FasterWhisperSTT(recorder=lambda: "AUDIO", transcriber=lambda _a: "hello there")
    utterance = stt.listen()
    assert utterance is not None
    assert utterance.text == "hello there"


def test_listen_none_when_recorder_stops() -> None:
    stt = FasterWhisperSTT(recorder=lambda: None, transcriber=lambda _a: "x")
    assert stt.listen() is None


def test_listen_none_on_empty_transcript() -> None:
    stt = FasterWhisperSTT(recorder=lambda: "AUDIO", transcriber=lambda _a: "   ")
    assert stt.listen() is None
