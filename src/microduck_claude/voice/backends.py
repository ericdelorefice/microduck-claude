"""Host STT/TTS backends that need no heavy dependencies.

- :class:`StdinSTT` — read typed lines as stand-in "speech" (drive the loop with no
  microphone).
- :class:`PrintTTS` — print the duck's speech (headless / tests).
- :class:`MacSayTTS` — speak via the macOS ``say`` command (real audio, zero deps).

A real microphone + speech-recognition backend (e.g. faster-whisper + sounddevice)
plugs in by implementing :class:`~.interfaces.SpeechToText`; it is kept out of the
core so the package stays dependency-light and CI needs no audio hardware.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from typing import TextIO

from .interfaces import Utterance


class StdinSTT:
    """Reads typed lines from stdin as recognized utterances."""

    def __init__(self, prompt: str = "you (speak) › ") -> None:
        self._prompt = prompt

    def listen(self) -> Utterance | None:
        try:
            line = input(self._prompt)
        except EOFError:
            return None
        return Utterance(line)


class PrintTTS:
    """Prints the duck's speech instead of producing audio."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream if stream is not None else sys.stdout

    def speak(self, text: str) -> None:
        print(f'🦆 "{text}"', file=self._stream)


Runner = Callable[[Sequence[str]], object]


def _default_runner(cmd: Sequence[str]) -> object:
    return subprocess.run(list(cmd), check=False)


class MacSayTTS:
    """Speaks via the macOS ``say`` command. ``runner`` is injectable for tests."""

    def __init__(self, voice: str | None = None, runner: Runner | None = None) -> None:
        self._voice = voice
        self._runner = runner if runner is not None else _default_runner

    @staticmethod
    def available() -> bool:
        return shutil.which("say") is not None

    def speak(self, text: str) -> None:
        cmd = ["say"]
        if self._voice:
            cmd += ["-v", self._voice]
        cmd.append(text)
        self._runner(cmd)
