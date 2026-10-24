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

import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
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


# Cap audio subprocesses so a stuck player (device held, a bad clip) cannot hang the voice loop
# forever; a spoken reply finishes well within this in practice.
_AUDIO_TIMEOUT_S = 120.0

Runner = Callable[[Sequence[str]], object]


def _default_runner(cmd: Sequence[str]) -> object:
    try:
        return subprocess.run(list(cmd), check=False, timeout=_AUDIO_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return None  # a stuck 'say' must not hang the voice loop


class MacSayTTS:
    """Speaks via the macOS ``say`` command. ``runner`` is injectable for tests."""

    def __init__(
        self, voice: str | None = None, runner: Runner | None = None, *, rate: int = 0
    ) -> None:
        self._voice = voice
        self._rate = rate
        self._runner = runner if runner is not None else _default_runner

    @staticmethod
    def available() -> bool:
        return shutil.which("say") is not None

    def speak(self, text: str) -> None:
        cmd = ["say"]
        if self._voice:
            cmd += ["-v", self._voice]
        if self._rate:
            cmd += ["-r", str(self._rate)]
        cmd += ["--", text]  # a reply starting with "-" is speech, not a `say` option
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


_ELEVEN_ENDPOINT = "https://api.elevenlabs.io/v1/text-to-speech/{voice}"
_ELEVEN_MODEL = "eleven_multilingual_v2"

Fetcher = Callable[[str, bytes, dict[str, str]], bytes]
Player = Callable[[bytes], None]


def _default_fetch(url: str, data: bytes, headers: dict[str, str]) -> bytes:
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        audio: bytes = response.read()
    return audio


def _afplay(audio: bytes) -> None:
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as handle:
        handle.write(audio)
        path = handle.name
    try:
        subprocess.run(["afplay", path], check=False, timeout=_AUDIO_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        pass  # a stuck player must not hang the voice loop
    finally:
        if os.path.exists(path):
            os.unlink(path)


class ElevenLabsTTS:
    """Speaks via ElevenLabs' cloud TTS — a rich, studio-grade narrator voice.

    Optional and cloud-based: needs ``ELEVENLABS_API_KEY`` in the environment (never
    committed or logged) and a voice id. Audio is synthesized over HTTPS and played with
    ``afplay``. ``fetch`` / ``player`` are injectable for tests.
    """

    def __init__(
        self,
        api_key: str,
        voice: str,
        *,
        model: str = _ELEVEN_MODEL,
        fetch: Fetcher | None = None,
        player: Player | None = None,
    ) -> None:
        self._api_key = api_key
        self._voice = voice
        self._model = model
        self._fetch = fetch if fetch is not None else _default_fetch
        self._player = player if player is not None else _afplay

    @staticmethod
    def player_available() -> bool:
        return shutil.which("afplay") is not None

    def speak(self, text: str) -> None:
        url = _ELEVEN_ENDPOINT.format(voice=self._voice)
        body = json.dumps(
            {
                "text": text,
                "model_id": self._model,
                "voice_settings": {"stability": 0.4, "similarity_boost": 0.85, "style": 0.35},
            }
        ).encode("utf-8")
        headers = {
            "xi-api-key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        try:
            audio = self._fetch(url, body, headers)
        except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
            # http.client.HTTPException (e.g. IncompleteRead on a dropped body) is NOT an
            # OSError, so without it a truncated reply would crash the voice loop here.
            print(f"(ElevenLabs TTS failed: {exc})", file=sys.stderr)
            return
        if audio:
            self._player(audio)
