"""Barge-in for the host voice loop: let the user interrupt the duck mid-sentence.

The controller plays a reply while a detector listens; when the detector reports
SUSTAINED speech (the "confirm" that avoids cutting off on a brief noise), playback
is stopped and the loop goes back to listening. True amplitude "ducking" (lower the
volume on a candidate, then cut on confirm) needs a volume-controllable player —
macOS `say` cannot, so it's a follow-up; the confirm-before-cut behaviour is here.

The real audio parts (InterruptibleSayTTS, MicSpeechDetector) are
**validate-with-a-microphone**; the BargeInController orchestration is unit-tested
with injected fakes. Barge-in only makes sense on the host path (Mac mic + speakers)
— the SSH "through-the-duck" device is single-client / half-duplex (docs/PLAN.md §2.4).
Echo (the mic hearing the duck's own speech) can still cause a false trigger; proper
acoustic echo cancellation is future work.
"""

from __future__ import annotations

import subprocess
import threading
from typing import Protocol


class InterruptibleSpeaker(Protocol):
    """Speaks text, stopping early if the ``stop`` event is set."""

    def speak(self, text: str, stop: threading.Event) -> None: ...


class SpeechDetector(Protocol):
    """Blocks until it confirms the user is speaking (True), or ``stop`` is set (False)."""

    def wait_for_speech(self, stop: threading.Event) -> bool: ...


class Barger(Protocol):
    """Speaks a reply and reports whether the user barged in."""

    def speak(self, text: str) -> bool: ...


class BargeInController:
    """Plays a reply that the user can interrupt by speaking."""

    def __init__(self, speaker: InterruptibleSpeaker, detector: SpeechDetector) -> None:
        self._speaker = speaker
        self._detector = detector

    def speak(self, text: str) -> bool:
        """Speak ``text``; return True if the user barged in (playback cut short)."""
        stop_speaking = threading.Event()
        stop_detecting = threading.Event()
        interrupted = threading.Event()

        def _watch() -> None:
            if self._detector.wait_for_speech(stop_detecting):
                interrupted.set()
                stop_speaking.set()

        watcher = threading.Thread(target=_watch, name="barge-in-watch", daemon=True)
        watcher.start()
        try:
            self._speaker.speak(text, stop_speaking)
        finally:
            stop_detecting.set()
            watcher.join(timeout=1.0)
        return interrupted.is_set()


class InterruptibleSayTTS:
    """macOS `say` as an interruptible speaker (terminates the process on stop)."""

    def __init__(self, voice: str | None = None, *, rate: int = 0) -> None:
        self._voice = voice
        self._rate = rate

    def speak(self, text: str, stop: threading.Event) -> None:
        cmd = ["say"]
        if self._voice:
            cmd += ["-v", self._voice]
        if self._rate:
            cmd += ["-r", str(self._rate)]
        cmd += ["--", text]  # a reply starting with "-" is speech, not a `say` option
        proc = subprocess.Popen(cmd)
        try:
            while proc.poll() is None:
                if stop.wait(0.05):
                    proc.terminate()
                    break
        finally:
            try:
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                proc.kill()


class MicSpeechDetector:
    """Detects SUSTAINED microphone speech (the confirm step). Validate on hardware."""

    def __init__(
        self, *, samplerate: int = 16_000, threshold: float = 0.02, confirm_frames: int = 6
    ) -> None:
        self._sr = samplerate
        self._threshold = threshold
        self._confirm_frames = confirm_frames

    def wait_for_speech(self, stop: threading.Event) -> bool:
        import numpy as np
        import sounddevice as sd

        block = max(1, int(self._sr * 0.03))
        loud = 0
        with sd.InputStream(
            samplerate=self._sr, channels=1, dtype="float32", blocksize=block
        ) as stream:
            while not stop.is_set():
                buf, _overflow = stream.read(block)
                if float(np.sqrt(np.mean(buf[:, 0] ** 2))) >= self._threshold:
                    loud += 1
                    if loud >= self._confirm_frames:  # sustained speech -> confirm
                        return True
                else:
                    loud = 0
        return False
