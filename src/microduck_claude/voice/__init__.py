"""Host voice loop: swappable STT/TTS, speech reactions, and the orchestrator."""

from __future__ import annotations

from .backends import MacSayTTS, PrintTTS, StdinSTT
from .confirm import VoiceConfirmer
from .interfaces import SpeechToText, TextToSpeech, Utterance
from .loop import VoiceLoop
from .reactions import SpeechReactor
from .ssh_audio import MacSayWavRenderer, SshDuckAudio, SshDuckTTS, SshTarget

__all__ = [
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
    "VoiceConfirmer",
    "VoiceLoop",
]
