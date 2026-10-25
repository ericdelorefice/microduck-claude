from __future__ import annotations

import pytest

from microduck_claude.robot import SOUND_TAGS, FakeRobot, RobotInterface


def test_satisfies_interface() -> None:
    assert isinstance(FakeRobot(), RobotInterface)


def test_records_calls_in_order() -> None:
    robot = FakeRobot()
    robot.set_head(head_pitch=0.2)
    robot.play_sound("greet")
    assert [c.method for c in robot.calls] == ["set_head", "play_sound"]
    assert robot.calls[1].kwargs == {"tag": "greet"}


def test_do_behavior_accepts_known_rejects_unknown() -> None:
    robot = FakeRobot()
    assert robot.do_behavior("sit_toggle") is True
    assert robot.do_behavior("teleport") is False


def test_play_sound_rejects_unknown_tag() -> None:
    robot = FakeRobot()
    with pytest.raises(ValueError):
        robot.play_sound("kaboom")
    assert "kaboom" not in SOUND_TAGS


def test_set_mouth_range_validated() -> None:
    robot = FakeRobot()
    robot.set_mouth(0.5)
    with pytest.raises(ValueError):
        robot.set_mouth(1.5)


def test_state_and_battery() -> None:
    robot = FakeRobot()
    state = robot.get_state()
    assert {"battery", "head", "pose", "behaviors"} <= set(state)
    assert 0.0 <= robot.get_battery() <= 1.0


def test_drive_for_records_a_single_intent_then_stops() -> None:
    # In-process: no deadman to beat, so one drive + stop (the duration is a live-body concern).
    robot = FakeRobot()
    robot.drive_for(0.4, 0.0, 0.0, duration=2.5)
    assert [c.method for c in robot.calls] == ["drive", "stop"]
    assert robot.calls[0].kwargs == {"vx": 0.4, "vy": 0.0, "vyaw": 0.0}


def test_capture_frame_returns_the_configured_frame() -> None:
    assert FakeRobot().capture_frame() is None  # no camera by default
    assert FakeRobot(camera_frame=b"PNGBYTES").capture_frame() == b"PNGBYTES"
