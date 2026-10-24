"""Host-side scaffolding to speak THROUGH the duck (and capture its mic) over SSH.

The duck plays audio with ``aplay`` and records with ``arecord`` on its Linux
board, reachable over SSH — so the host can render TTS to a WAV and play it on the
duck's speaker, and capture the duck's microphone for STT, with no firmware changes.

This is **validate-on-hardware** scaffolding: the command construction is unit-tested
with injected runners, but the real device name (``plughw:aic3104`` on the prototype
board, ``default`` on the beta board), SSH access, and the single-client "takes turns
with the duck's own chirps" behaviour must be confirmed on a real board — see
docs/PLAN.md §2.4. SSH auth is the user's own (keys / ssh config); nothing here
stores or handles credentials.
"""

from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

# Runs a command (optionally feeding it stdin) and returns its stdout bytes.
Runner = Callable[[Sequence[str], bytes | None], bytes]


def _default_runner(cmd: Sequence[str], stdin: bytes | None) -> bytes:
    result = subprocess.run(list(cmd), input=stdin, stdout=subprocess.PIPE, check=False)
    return result.stdout or b""


@dataclass(frozen=True)
class SshTarget:
    host: str
    device: str = "plughw:aic3104"  # prototype codec; use "default" on the beta board
    user: str = "microduck"

    @property
    def address(self) -> str:
        return f"{self.user}@{self.host}"


def aplay_command(target: SshTarget) -> list[str]:
    return ["ssh", target.address, "aplay", "-q", "-D", target.device]


def arecord_command(target: SshTarget, seconds: float) -> list[str]:
    return [
        "ssh",
        target.address,
        "arecord",
        "-q",
        "-D",
        f"{target.device},0",
        "-f",
        "S16_LE",
        "-r",
        "16000",
        "-c",
        "1",
        "-t",
        "wav",
        "-d",
        str(int(seconds)),
    ]


class SshDuckAudio:
    """Plays audio on, and records audio from, the duck over SSH."""

    def __init__(self, target: SshTarget, *, runner: Runner | None = None) -> None:
        self._target = target
        self._runner = runner if runner is not None else _default_runner

    def play_wav(self, wav_bytes: bytes) -> None:
        self._runner(aplay_command(self._target), wav_bytes)

    def record_wav(self, seconds: float = 4.0) -> bytes:
        return self._runner(arecord_command(self._target, seconds), None)


class WavRenderer(Protocol):
    """Renders text to WAV audio bytes on the host."""

    def render(self, text: str) -> bytes: ...


class MacSayWavRenderer:
    """Renders text to WAV bytes using the macOS ``say`` command."""

    def __init__(
        self,
        voice: str | None = None,
        *,
        runner: Callable[[Sequence[str]], None] | None = None,
    ) -> None:
        self._voice = voice
        self._runner = runner if runner is not None else _run_quiet

    def render(self, text: str) -> bytes:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "speech.wav"
            cmd = ["say", "-o", str(out), "--data-format=LEI16@22050"]
            if self._voice:
                cmd += ["-v", self._voice]
            cmd += ["--", text]  # a reply starting with "-" is speech, not a `say` option
            self._runner(cmd)
            try:
                return out.read_bytes()
            except OSError:
                return b""


def _run_quiet(cmd: Sequence[str]) -> None:
    subprocess.run(list(cmd), check=False)


class SshDuckTTS:
    """A TextToSpeech that renders speech on the host and plays it on the duck."""

    def __init__(self, renderer: WavRenderer, duck_audio: SshDuckAudio) -> None:
        self._renderer = renderer
        self._duck_audio = duck_audio

    def speak(self, text: str) -> None:
        wav = self._renderer.render(text)
        if wav:
            self._duck_audio.play_wav(wav)
