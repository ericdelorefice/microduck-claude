from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from microduck_claude.voice import MacSayWavRenderer, SshDuckAudio, SshDuckTTS, SshTarget
from microduck_claude.voice.ssh_audio import aplay_command, arecord_command


def test_aplay_command() -> None:
    target = SshTarget("duck.local", "plughw:aic3104", "microduck")
    assert aplay_command(target) == [
        "ssh",
        "microduck@duck.local",
        "aplay",
        "-q",
        "-D",
        "plughw:aic3104",
    ]


def test_arecord_command() -> None:
    cmd = arecord_command(SshTarget("h"), 4)
    assert cmd[:3] == ["ssh", "microduck@h", "arecord"]
    assert "16000" in cmd
    assert "S16_LE" in cmd
    assert cmd[-1] == "4"


def test_ssh_duck_audio_play_and_record() -> None:
    calls: list[tuple[list[str], bytes | None]] = []

    def runner(cmd: Sequence[str], stdin: bytes | None) -> bytes:
        calls.append((list(cmd), stdin))
        return b"AUDIO"

    audio = SshDuckAudio(SshTarget("h"), runner=runner)
    audio.play_wav(b"WAV")
    assert calls[0][0][2] == "aplay"
    assert calls[0][1] == b"WAV"
    assert audio.record_wav(3) == b"AUDIO"
    assert calls[1][0][2] == "arecord"


def test_mac_say_wav_renderer_reads_rendered_file() -> None:
    def runner(cmd: Sequence[str]) -> None:
        out = cmd[cmd.index("-o") + 1]
        Path(out).write_bytes(b"RIFFfake")

    assert MacSayWavRenderer(runner=runner).render("hello") == b"RIFFfake"


def test_ssh_duck_tts_renders_then_plays() -> None:
    stdins: list[bytes | None] = []

    class _Renderer:
        def render(self, text: str) -> bytes:
            return b"W" + text.encode()

    def runner(cmd: Sequence[str], stdin: bytes | None) -> bytes:
        stdins.append(stdin)
        return b""

    SshDuckTTS(_Renderer(), SshDuckAudio(SshTarget("h"), runner=runner)).speak("hi")
    assert stdins == [b"Whi"]
