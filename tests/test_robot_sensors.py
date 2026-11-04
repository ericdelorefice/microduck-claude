"""Reading the duck's own heading and head distance sensor from robotd / tofd messages."""

from __future__ import annotations

import math

from microduck_claude.robot import RpcRobot, UnixSocketTransport
from microduck_claude.robot.rpc import heading_from_state, range_from_tof_frame


def _tof(rows: list[list[int]], status: int = 5) -> dict[str, object]:
    flat = [d for row in rows for d in row]
    return {"rows": 8, "cols": 8, "distance_mm": flat, "status": [status] * 64, "seq": 1}


def test_heading_prefers_odometry_then_the_imu() -> None:
    assert heading_from_state({"odom": {"yaw": 1.25}}) == 1.25
    half_turn_left = [math.cos(math.pi / 4), 0.0, 0.0, math.sin(math.pi / 4)]  # 90 deg, w-first
    assert math.isclose(heading_from_state({"imu": {"quat": half_turn_left}}) or 0, math.pi / 2)
    assert heading_from_state({}) is None
    assert heading_from_state({"odom": {"yaw": "north"}}) is None


def test_range_ahead_reads_the_upper_rows_not_the_floor() -> None:
    wall, floor = 1800, 400  # the lower rows see the floor when the head is tilted down
    frame = _tof([[wall] * 8] * 3 + [[floor] * 8] * 5)
    assert range_from_tof_frame(frame) == 1.8


def test_range_ahead_ignores_invalid_zones() -> None:
    assert range_from_tof_frame(_tof([[1000] * 8] * 8, status=255)) is None
    assert range_from_tof_frame({"rows": 8, "cols": 8}) is None


def test_stale_readings_count_as_unknown() -> None:
    transport = UnixSocketTransport("/nonexistent.sock")
    robot = RpcRobot(transport, subscribe_hz=0.0)
    assert robot.heading() is None and robot.range_ahead() is None  # nothing heard yet
    transport._handle_notification({"method": "robot.state", "params": {"odom": {"yaw": 0.5}}})
    assert robot.heading() == 0.5
    transport._latest["robot.state"] = (transport._latest["robot.state"][0], -100.0)  # long ago
    assert robot.heading() is None
