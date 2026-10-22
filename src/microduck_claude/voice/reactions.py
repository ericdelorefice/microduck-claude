"""Expressive, bounded duck reactions tied to speech.

A reaction uses only head/mouth/sound primitives — never ``drive()`` or
``do_behavior()`` — so it is *embodiment* (like idle breathing or a speech wobble),
not a gated action. Anything with a real-world side effect still goes through the
tool + confirmation gate.
"""

from __future__ import annotations

from ..robot.interface import RobotInterface

_MAX_MOUTH_CYCLES = 5


def _mouth_cycles(text: str) -> int:
    return max(1, min(_MAX_MOUTH_CYCLES, len(text) // 20))


class SpeechReactor:
    """Drives small expressive movements around listening and speaking."""

    def __init__(self, robot: RobotInterface) -> None:
        self._robot = robot

    def on_listening(self) -> None:
        self._robot.set_head(head_pitch=-0.08)  # perk up, attentive

    def on_speaking(self, text: str) -> None:
        self._robot.play_sound("coo")
        for _ in range(_mouth_cycles(text)):
            self._robot.set_mouth(0.6)
            self._robot.set_mouth(0.0)

    def on_idle(self) -> None:
        self._robot.set_mouth(0.0)
        self._robot.set_head()
