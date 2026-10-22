from __future__ import annotations

import pytest

from microduck_claude.expressions import (
    GESTURES,
    GestureUnavailableError,
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


def test_skill_gesture_invokes_a_real_behavior() -> None:
    robot = FakeRobot()
    gesture = perform_gesture(robot, "roulade")
    assert gesture.skill == "roulade"
    assert any(c.method == "do_behavior" and c.kwargs["skill"] == "roulade" for c in robot.calls)


def test_skill_gesture_raises_when_the_robot_declines() -> None:
    robot = FakeRobot()
    robot._behaviors = []  # a body that advertises no trained skills (like a fresh sim)
    with pytest.raises(GestureUnavailableError):
        perform_gesture(robot, "roulade")


def test_pace_still_runs_the_gesture_steps() -> None:
    robot = FakeRobot()
    # A tiny pace exercises the paced wrapper without slowing the test noticeably.
    perform_gesture(robot, "nod", pace=0.001)
    assert any(c.method == "set_head" for c in robot.calls)
