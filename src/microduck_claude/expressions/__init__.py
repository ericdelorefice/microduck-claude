"""Expression layer: map high-level gestures onto robot intents."""

from __future__ import annotations

import time
from typing import cast

from ..robot.interface import RobotInterface
from .gestures import GESTURES, Gesture, GestureFn


class UnknownGestureError(ValueError):
    """Raised when a gesture name is not in the vocabulary."""

    def __init__(self, name: str) -> None:
        super().__init__(f"unknown gesture {name!r}")
        self.name = name


class GestureUnavailableError(RuntimeError):
    """Raised when a skill-based gesture is declined by the robot.

    The sim, for instance, only advertises a few trained skills; asking for one it
    does not have must fail honestly rather than let the duck claim it happened.
    """

    def __init__(self, name: str) -> None:
        super().__init__(f"the robot declined the gesture {name!r}")
        self.name = name


def gesture_names() -> list[str]:
    """Return the available gesture names, sorted."""
    return sorted(GESTURES)


def gesture_catalog() -> list[tuple[str, str]]:
    """Return ``(name, description)`` pairs for every gesture, sorted by name."""
    return [(g.name, g.description) for g in sorted(GESTURES.values(), key=lambda g: g.name)]


class _PacedRobot:
    """Wraps a robot so each motion is held briefly.

    Gestures are written as a sequence of instant steps — fine for the FakeRobot,
    which only records them. On a real body those steps collapse into one 50 Hz frame
    and nothing is visible, so with ``pace`` > 0 we sleep after each motion command to
    let successive poses actually render.
    """

    _HELD = frozenset({"set_head", "set_pose", "set_mouth", "drive", "look_at"})

    def __init__(self, robot: RobotInterface, pace: float) -> None:
        self._robot = robot
        self._pace = pace

    def __getattr__(self, attr: str) -> object:
        target = getattr(self._robot, attr)
        if attr not in self._HELD:
            return target

        def paced(*args: object, **kwargs: object) -> object:
            result = target(*args, **kwargs)
            time.sleep(self._pace)
            return result

        return paced


def perform_gesture(robot: RobotInterface, name: str, *, pace: float = 0.0) -> Gesture:
    """Look up and perform a gesture by name.

    A ``skill`` gesture goes through ``robot.do`` and raises
    :class:`GestureUnavailableError` if the robot declines it. A primitive gesture runs
    its routine; with ``pace`` > 0 each step is held briefly so the motion is visible on
    a real body. Raises :class:`UnknownGestureError` for an unknown name.
    """
    gesture = GESTURES.get(name)
    if gesture is None:
        raise UnknownGestureError(name)
    if gesture.skill is not None:
        if not robot.do_behavior(gesture.skill):
            raise GestureUnavailableError(name)
        return gesture
    assert gesture.run is not None  # a non-skill gesture always carries a routine
    target = cast(RobotInterface, _PacedRobot(robot, pace)) if pace > 0 else robot
    gesture.run(target)
    return gesture


__all__ = [
    "GESTURES",
    "Gesture",
    "GestureFn",
    "GestureUnavailableError",
    "UnknownGestureError",
    "gesture_catalog",
    "gesture_names",
    "perform_gesture",
]
