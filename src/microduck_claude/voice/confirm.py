"""A Confirmer that asks and listens by voice, bridging voice I/O to the safety gate."""

from __future__ import annotations

import re

from .interfaces import SpeechToText, TextToSpeech

_AFFIRMATIVE_WORDS = frozenset(
    {"yes", "yeah", "yep", "yup", "sure", "ok", "okay", "affirmative", "confirm", "confirmed"}
)
_AFFIRMATIVE_PHRASES = frozenset({"go ahead", "do it", "please do"})
_NEGATIVE_WORDS = frozenset(
    {"no", "nope", "nah", "cancel", "stop", "negative", "don't", "dont", "never"}
)


class VoiceConfirmer:
    """Confirms an action by speaking the prompt and listening for a spoken yes/no.

    It consults ONLY the live microphone — the user's voice channel — so a "yes" in
    the model's output or inside a tool result can never authorise an action. It confirms
    only on a clear affirmation with no negation present: any "no"/"cancel"/etc. declines
    (fail-safe), which also means the mic picking up the duck's own spoken "...yes or no"
    prompt is heard as a decline, not a self-confirmation.

    Residual risk: the microphone is a shared channel, so ambient audio could in
    principle answer. Mitigations (wake word, speaker verification, a physical
    confirm button) are future work; see docs/PLAN.md.
    """

    def __init__(self, stt: SpeechToText, tts: TextToSpeech) -> None:
        self._stt = stt
        self._tts = tts

    def confirm(self, prompt: str) -> bool:
        self._tts.speak(f"{prompt} Please answer yes or no.")
        utterance = self._stt.listen()
        if utterance is None:
            return False
        answer = utterance.text.strip().lower().rstrip(".!?")
        words = set(re.findall(r"[a-z']+", answer))
        if words & _NEGATIVE_WORDS:
            return False  # any negation present -> decline (also defeats the prompt echo)
        return answer in _AFFIRMATIVE_PHRASES or bool(words & _AFFIRMATIVE_WORDS)
