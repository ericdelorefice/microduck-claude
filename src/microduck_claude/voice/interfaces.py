"""Swappable voice I/O interfaces (host-side).

STT and TTS run on the host (your Mac/server), not the robot. These are the seams
a real speech-recognition or speech-synthesis engine plugs into; the core ships
only light, dependency-free backends (see :mod:`.backends`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class Utterance:
    """A recognized spoken utterance from the user."""

    text: str


class SpeechToText(Protocol):
    """Capture one utterance. Return ``None`` to end the session (EOF / stop)."""

    def listen(self) -> Utterance | None: ...


class TextToSpeech(Protocol):
    """Speak a line of text on the host."""

    def speak(self, text: str) -> None: ...
