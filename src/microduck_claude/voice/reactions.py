"""Expressive, bounded duck reactions tied to speech.

A reaction uses only head/mouth/sound primitives — never ``drive()`` or
``do_behavior()`` — so it is *embodiment* (like a speech wobble), not a gated action.
Anything with a real-world side effect still goes through the tool + confirmation gate.

While a reply plays, :meth:`SpeechReactor.animate` runs on a background thread (started
by the voice loop) so the duck visibly bobs its head and works its beak *during* the
audio. In the MuJoCo walk sim the jaw is passive, so the head bob is what reads as
"talking"; on real hardware the beak moves too.

Every robot call here is best-effort: expression must never crash the conversation, so a
transport hiccup is skipped (and warned once), not raised.
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from typing import Any

from ..robot.interface import RobotInterface


class SpeechReactor:
    """Drives small expressive movements around listening and speaking."""

    def __init__(self, robot: RobotInterface, *, period: float = 0.13) -> None:
        self._robot = robot
        self._period = period
        self._warned = False

    def _safe(self, method: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """Run a best-effort expressive robot call; never let it break the conversation.

        Expression is embodiment, not a critical action — if the robot link hiccups
        (e.g. an rpc socket drop) we skip the motion rather than crash the voice loop or
        silently kill the animation thread.
        """
        try:
            method(*args, **kwargs)
        except Exception as exc:  # expression must never be fatal to the conversation
            if not self._warned:
                print(f"(duck expression skipped: {exc})", file=sys.stderr)
                self._warned = True

    def on_listening(self) -> None:
        self._safe(self._robot.set_head, head_pitch=-0.08)  # perk up, attentive

    def on_speaking(self, text: str) -> None:
        """Called once as a reply begins: a short chirp (beak motion is animate()'s job)."""
        self._safe(self._robot.play_sound, "coo")

    def animate(self, stop: threading.Event) -> None:
        """Bob the head and work the beak until ``stop`` is set — runs during the audio.

        The head bob is the visible "talking" cue in the sim (the walk policy leaves
        the jaw passive); the mouth command animates the beak on real hardware.
        """
        down = False
        while not stop.is_set():
            self._safe(self._robot.set_mouth, 0.6 if down else 0.1)
            self._safe(self._robot.set_head, head_pitch=0.04 if down else -0.12)
            down = not down
            if stop.wait(self._period):
                break

    def on_idle(self) -> None:
        self._safe(self._robot.set_mouth, 0.0)
        self._safe(self._robot.set_head)
