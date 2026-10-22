"""Host voice loop: swappable STT/TTS, speech reactions, and the orchestrator."""

from __future__ import annotations

from .backends import MacSayTTS, PrintTTS, StdinSTT, pick_say_voice
from .bargein import BargeInController, InterruptibleSayTTS, MicSpeechDetector
from .confirm import VoiceConfirmer
from .interfaces import SpeechToText, TextToSpeech, Utterance
from .loop import VoiceLoop
from .reactions import SpeechReactor
from .ssh_audio import MacSayWavRenderer, SshDuckAudio, SshDuckTTS, SshTarget
from .stt_whisper import FasterWhisperSTT

__all__ = [
    "BargeInController",
    "FasterWhisperSTT",
    "InterruptibleSayTTS",
    "MicSpeechDetector",
    "MacSayTTS",
    "MacSayWavRenderer",
    "PrintTTS",
    "SpeechReactor",
    "SpeechToText",
    "SshDuckAudio",
    "SshDuckTTS",
    "SshTarget",
    "StdinSTT",
    "TextToSpeech",
    "Utterance",
    "pick_say_voice",
    "VoiceConfirmer",
    "VoiceLoop",
]
