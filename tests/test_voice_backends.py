from __future__ import annotations

from microduck_claude.voice import MacSayTTS, PrintTTS, StdinSTT


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
    assert calls == [["say", "hello"]]


def test_mac_say_with_voice_flag() -> None:
    calls: list[list[str]] = []
    MacSayTTS(voice="Daniel", runner=lambda cmd: calls.append(list(cmd))).speak("hi")
    assert calls == [["say", "-v", "Daniel", "hi"]]


def test_mac_say_available_is_bool() -> None:
    assert isinstance(MacSayTTS.available(), bool)
