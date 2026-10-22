"""The host voice loop: listen -> Claude -> speak, with the duck reacting.

Tool calls (including gated actions) are handled inside ``brain.send`` by the
Dispatcher, so in voice mode the Dispatcher is given a VoiceConfirmer and action
confirmations happen out loud, mid-turn. With an optional :class:`BargeInController`,
the user can interrupt the duck mid-reply.
"""

from __future__ import annotations

from ..brain import Brain
from .bargein import Barger
from .interfaces import SpeechToText, TextToSpeech
from .reactions import SpeechReactor


class VoiceLoop:
    """Drives one voice conversation until the STT backend signals stop."""

    def __init__(
        self,
        brain: Brain,
        stt: SpeechToText,
        tts: TextToSpeech,
        reactor: SpeechReactor,
        *,
        barge_in: Barger | None = None,
    ) -> None:
        self._brain = brain
        self._stt = stt
        self._tts = tts
        self._reactor = reactor
        self._barge_in = barge_in

    def run(self) -> None:
        while True:
            self._reactor.on_listening()
            utterance = self._stt.listen()
            if utterance is None:
                break
            text = utterance.text.strip()
            if not text:
                continue

            try:
                turn = self._brain.send(text)
            except Exception:  # keep the loop alive on API/transport errors
                self._tts.speak("Sorry, something went wrong.")
                self._reactor.on_idle()
                continue

            spoke = False
            for reply in turn.texts:
                self._reactor.on_speaking(reply)
                spoke = True
                if self._speak(reply):  # the user barged in
                    break
            if turn.refused and not spoke:
                self._speak("Sorry, I can't do that.")
            self._reactor.on_idle()

    def _speak(self, text: str) -> bool:
        """Speak ``text``; return True if the user barged in (where supported)."""
        if self._barge_in is not None:
            return self._barge_in.speak(text)
        self._tts.speak(text)
        return False
