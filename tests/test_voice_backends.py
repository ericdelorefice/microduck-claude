from __future__ import annotations

import json

from microduck_claude.voice import ElevenLabsTTS, MacSayTTS, PrintTTS, StdinSTT


def test_stdin_stt_reads_lines_then_stops(monkeypatch) -> None:
    pending = ["hello duck"]

    def fake_input(prompt: str = "") -> str:
        if not pending:
            raise EOFError
        return pending.pop(0)

    monkeypatch.setattr("builtins.input", fake_input)
    stt = StdinSTT()
    utt = stt.listen()
    assert utt is not None and utt.text == "hello duck"
    assert stt.listen() is None  # EOF -> stop


def test_print_tts_writes_quacky_line(capsys) -> None:
    PrintTTS().speak("hi there")
    assert '🦆 "hi there"' in capsys.readouterr().out


def test_mac_say_builds_command() -> None:
    calls: list[list[str]] = []
    MacSayTTS(runner=lambda cmd: calls.append(list(cmd))).speak("hello")
    assert calls == [["say", "--", "hello"]]


def test_mac_say_with_voice_flag() -> None:
    calls: list[list[str]] = []
    MacSayTTS(voice="Daniel", runner=lambda cmd: calls.append(list(cmd))).speak("hi")
    assert calls == [["say", "-v", "Daniel", "--", "hi"]]


def test_mac_say_available_is_bool() -> None:
    assert isinstance(MacSayTTS.available(), bool)


def test_elevenlabs_posts_text_and_plays() -> None:
    seen: dict[str, object] = {}
    played: list[bytes] = []

    def fake_fetch(url: str, data: bytes, headers: dict[str, str]) -> bytes:
        seen["url"] = url
        seen["headers"] = headers
        seen["body"] = json.loads(data)
        return b"ID3-mp3-bytes"

    ElevenLabsTTS("secret-key", "VOICE123", fetch=fake_fetch, player=played.append).speak(
        "Hello, narrator."
    )

    assert "VOICE123" in str(seen["url"])
    assert seen["headers"]["xi-api-key"] == "secret-key"  # type: ignore[index]
    assert seen["body"]["text"] == "Hello, narrator."  # type: ignore[index]
    assert played == [b"ID3-mp3-bytes"]


def test_elevenlabs_never_prints_the_key_on_failure(capsys) -> None:
    def boom(url: str, data: bytes, headers: dict[str, str]) -> bytes:
        raise OSError("network down")

    ElevenLabsTTS("super-secret", "V", fetch=boom, player=lambda _a: None).speak("hi")
    assert "super-secret" not in capsys.readouterr().err


def test_mac_say_never_reads_a_reply_as_an_option() -> None:
    # `say` parses a leading "-" as an option: "- First, a nod." fails as an invalid option
    # and "-o<path>" writes the audio to that file instead of speaking it.
    calls: list[list[str]] = []
    MacSayTTS(runner=lambda cmd: calls.append(list(cmd))).speak("-o/tmp/clobbered.aiff")
    assert calls == [["say", "--", "-o/tmp/clobbered.aiff"]]
