"""Local microphone speech-to-text via faster-whisper (the optional ``[voice]`` extra).

Captures one utterance from the mic with simple silence endpointing, then transcribes
it with faster-whisper (MIT; no torch; prebuilt Apple-Silicon wheels; bundled FFmpeg;
built-in Silero VAD). The capture and transcription steps are injectable, so the
``listen()`` orchestration is unit-tested without audio or models; the real mic and
transcription path is **validate-with-a-microphone**. Install: ``pip install '.[voice]'``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .interfaces import Utterance

# Capture one utterance's audio (returns None to stop), and transcribe audio to text.
Recorder = Callable[[], Any]
Transcriber = Callable[[Any], str]

_SAMPLE_RATE = 16_000


class FasterWhisperSTT:
    """A SpeechToText backed by the microphone + faster-whisper."""

    def __init__(
        self,
        model_size: str = "base.en",
        *,
        recorder: Recorder | None = None,
        transcriber: Transcriber | None = None,
        samplerate: int = _SAMPLE_RATE,
        compute_type: str = "int8",
    ) -> None:
        self._recorder = recorder if recorder is not None else _mic_recorder(samplerate)
        self._transcriber = (
            transcriber
            if transcriber is not None
            else _whisper_transcriber(model_size, compute_type)
        )

    def listen(self) -> Utterance | None:
        audio = self._recorder()
        if audio is None:
            return None
        text = self._transcriber(audio).strip()
        return Utterance(text) if text else None


def _mic_recorder(samplerate: int) -> Recorder:
    """Build a recorder that captures one utterance (speech then ~0.8 s of silence)."""

    def record() -> Any:
        import numpy as np
        import sounddevice as sd

        block = max(1, int(samplerate * 0.03))  # 30 ms frames
        chunks: list[Any] = []
        spoke = False
        silent = 0.0
        try:
            with sd.InputStream(
                samplerate=samplerate, channels=1, dtype="float32", blocksize=block
            ) as stream:
                while True:
                    buf, _overflow = stream.read(block)
                    mono = buf[:, 0]
                    if float(np.sqrt(np.mean(mono**2))) >= 0.015:
                        spoke, silent = True, 0.0
                        chunks.append(mono)
                    elif spoke:
                        silent += 0.03
                        chunks.append(mono)
                        if silent >= 0.8:
                            return np.concatenate(chunks)
        except KeyboardInterrupt:
            return None

    return record


def _whisper_transcriber(model_size: str, compute_type: str) -> Transcriber:
    """Build a transcriber that lazily loads a faster-whisper model on first use."""

    holder: dict[str, Any] = {}

    def transcribe(audio: Any) -> str:
        if "model" not in holder:
            from faster_whisper import WhisperModel

            holder["model"] = WhisperModel(model_size, device="cpu", compute_type=compute_type)
        segments, _info = holder["model"].transcribe(
            audio, language="en", beam_size=1, vad_filter=True
        )
        return " ".join(segment.text.strip() for segment in segments).strip()

    return transcribe
