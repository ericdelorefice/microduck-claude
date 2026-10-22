"""Expressive, bounded duck reactions tied to speech.

A reaction uses only head/mouth/sound primitives — never ``drive()`` or
``do_behavior()`` — so it is *embodiment* (like a speech wobble), not a gated action.
Anything with a real-world side effect still goes through the tool + confirmation gate.

While a reply plays, :meth:`SpeechReactor.animate` runs on a background thread (started
by the voice loop) so the duck visibly bobs its head and works its beak *during* the
audio. In the MuJoCo walk sim the jaw is passive, so the head bob is what reads as
"talking"; on real hardware the beak moves too.
"""

from __future__ import annotations

import threading

from ..robot.interface import RobotInterface


class SpeechReactor:
    """Drives small expressive movements around listening and speaking."""

    def __init__(self, robot: RobotInterface, *, period: float = 0.13) -> None:
        self._robot = robot
        self._period = period

    def on_listening(self) -> None:
        self._robot.set_head(head_pitch=-0.08)  # perk up, attentive

    def on_speaking(self, text: str) -> None:
        """Called once as a reply begins: a chirp and an initial beak open."""
        self._robot.play_sound("coo")
        self._robot.set_mouth(0.5)

    def animate(self, stop: threading.Event) -> None:
        """Bob the head and work the beak until ``stop`` is set — runs during the audio.

        The head bob is the visible "talking" cue in the sim (the walk policy leaves
        the jaw passive); the mouth command animates the beak on real hardware.
        """
        down = False
        while not stop.is_set():
            self._robot.set_mouth(0.6 if down else 0.1)
            self._robot.set_head(head_pitch=0.04 if down else -0.12)
            down = not down
            if stop.wait(self._period):
                break

    def on_idle(self) -> None:
        self._robot.set_mouth(0.0)
        self._robot.set_head()
