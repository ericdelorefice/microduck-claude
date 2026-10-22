"""A Confirmer that asks and listens by voice, bridging voice I/O to the safety gate."""

from __future__ import annotations

from .interfaces import SpeechToText, TextToSpeech

_AFFIRMATIVES = frozenset(
    {
        "yes",
        "yeah",
        "yep",
        "yup",
        "sure",
        "ok",
        "okay",
        "go ahead",
        "do it",
        "affirmative",
        "please do",
        "confirm",
        "confirmed",
    }
)


class VoiceConfirmer:
    """Confirms an action by speaking the prompt and listening for a spoken yes/no.

    It consults ONLY the live microphone — the user's voice channel — so a "yes" in
    the model's output or inside a tool result can never authorise an action.
    Anything that is not a clear spoken "yes" is treated as "no" (fail-safe).

    Residual risk: the microphone is a shared channel, so ambient audio could in
    principle answer. Mitigations (wake word, speaker verification, a physical
    confirm button) are future work; see docs/PLAN.md.
    """

    def __init__(self, stt: SpeechToText, tts: TextToSpeech) -> None:
        self._stt = stt
        self._tts = tts

    def confirm(self, prompt: str) -> bool:
        self._tts.speak(f"{prompt} Please say yes or no.")
        utterance = self._stt.listen()
        if utterance is None:
            return False
        answer = utterance.text.strip().lower().rstrip(".!")
        return answer in _AFFIRMATIVES or answer.startswith("yes")
