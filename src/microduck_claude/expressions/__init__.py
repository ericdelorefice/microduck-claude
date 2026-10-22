"""Expression layer: map high-level gestures onto robot intents."""

from __future__ import annotations

from ..robot.interface import RobotInterface
from .gestures import GESTURES, Gesture, GestureFn


class UnknownGestureError(ValueError):
    """Raised when a gesture name is not in the vocabulary."""

    def __init__(self, name: str) -> None:
        super().__init__(f"unknown gesture {name!r}")
        self.name = name


def gesture_names() -> list[str]:
    """Return the available gesture names, sorted."""
    return sorted(GESTURES)


def gesture_catalog() -> list[tuple[str, str]]:
    """Return ``(name, description)`` pairs for every gesture, sorted by name."""
    return [(g.name, g.description) for g in sorted(GESTURES.values(), key=lambda g: g.name)]


def perform_gesture(robot: RobotInterface, name: str) -> Gesture:
    """Look up and perform a gesture by name.

    Raises :class:`UnknownGestureError` if the name is not in the vocabulary.
    """
    gesture = GESTURES.get(name)
    if gesture is None:
        raise UnknownGestureError(name)
    gesture.run(robot)
    return gesture


__all__ = [
    "GESTURES",
    "Gesture",
    "GestureFn",
    "UnknownGestureError",
    "gesture_catalog",
    "gesture_names",
    "perform_gesture",
]
