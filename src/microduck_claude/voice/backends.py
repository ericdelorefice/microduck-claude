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

import os
import shutil
import subprocess
import sys
import tempfile
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


# British male voices first, for a dry "narrator" character (Stanley-Parable-adjacent;
# macOS can't do the real thing). Override with MICRODUCK_SAY_VOICE; install an Enhanced
# en-GB voice in System Settings > Spoken Content for a closer match.
_PREFERRED_VOICES = (
    "Oliver",
    "Daniel",
    "Arthur",
    "Samantha",
    "Alex",
    "Karen",
    "Moira",
    "Fred",
    "Victoria",
    "Tom",
)


def pick_say_voice(*, min_bytes: int = 2048) -> str | None:
    """Return the first macOS ``say`` voice that actually synthesizes audio, or None.

    macOS lists voices whose data is not installed; those render a near-empty file and
    play as silence. We probe candidates by rendering a tiny clip and checking its size,
    so voice mode does not fall back to a silent default voice.
    """
    for voice in _PREFERRED_VOICES:
        path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as handle:
                path = handle.name
            subprocess.run(
                ["say", "-v", voice, "-o", path, "probe"],
                check=False,
                capture_output=True,
                timeout=10,
            )
            if os.path.getsize(path) >= min_bytes:
                return voice
        except (OSError, subprocess.SubprocessError):
            continue
        finally:
            if path and os.path.exists(path):
                os.unlink(path)
    return None
