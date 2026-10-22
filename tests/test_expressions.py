from __future__ import annotations

import pytest

from microduck_claude.expressions import (
    GESTURES,
    UnknownGestureError,
    gesture_names,
    perform_gesture,
)
from microduck_claude.robot import SOUND_TAGS, STOCK_BEHAVIORS, FakeRobot


def test_perform_known_gesture_moves_robot() -> None:
    robot = FakeRobot()
    gesture = perform_gesture(robot, "nod")
    assert gesture.name == "nod"
    assert any(c.method == "set_head" for c in robot.calls)


def test_unknown_gesture_raises() -> None:
    with pytest.raises(UnknownGestureError):
        perform_gesture(FakeRobot(), "backflip")


def test_every_gesture_only_uses_valid_primitives() -> None:
    # Guard: a gesture must never emit a sound tag or behaviour the robot rejects.
    for name in gesture_names():
        robot = FakeRobot()
        perform_gesture(robot, name)
        for call in robot.calls:
            if call.method == "play_sound":
                assert call.kwargs["tag"] in SOUND_TAGS
            if call.method == "do_behavior":
                assert call.kwargs["skill"] in STOCK_BEHAVIORS


def test_catalog_covers_every_gesture() -> None:
    assert set(gesture_names()) == set(GESTURES)
