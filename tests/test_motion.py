"""Closed-loop motion: turning by heading, walking with a distance stop — on a simulated body."""

from __future__ import annotations

import math

from microduck_claude.robot import FakeRobot
from microduck_claude.robot.motion import STOP_AT_M, TURN_TOLERANCE_DEG, turn_by, walk


class _Clock:
    """Fake time: sleeping advances the body instead of waiting."""

    def __init__(self, body: _Body) -> None:
        self.t = 0.0
        self.body = body

    def now(self) -> float:
        return self.t

    def sleep(self, dt: float) -> None:
        self.t += dt
        self.body.advance(dt)


class _Body:
    """A duck with the sim gait's quirks: arcs turn at full yaw (faster to the right), the
    walk curves right, and the turn coasts a little after a stop. Wall straight ahead."""

    def __init__(
        self,
        *,
        wall_m: float = 3.0,
        coast_s: float = 0.15,
        sensors: bool = True,
        stuck: bool = False,
        curve_dps: float = -6.0,
    ) -> None:
        self.yaw = 0.0  # radians, + = left
        self.ahead = wall_m
        self.coast_s = coast_s
        self.sensors = sensors
        self.stuck = stuck
        self.curve_dps = curve_dps
        self.cmd: tuple[float, float] | None = None
        self.coast_left = 0.0
        self.last_rate = 0.0
        self.calls: list[str] = []

    def heading(self) -> float | None:
        return self.yaw if self.sensors else None

    def range_ahead(self) -> float | None:
        return self.ahead if self.sensors else None

    def drive(self, vx: float, vy: float, vyaw: float) -> None:
        self.cmd = (vx, vyaw)
        self.calls.append("drive")

    def stop(self) -> None:
        self.cmd = None
        self.coast_left = self.coast_s
        self.calls.append("stop")

    def drive_for(self, vx: float, vy: float, vyaw: float, *, duration: float) -> None:
        self.calls.append("drive_for")

    def advance(self, dt: float) -> None:
        if self.cmd is None:  # stopped: keep turning at the last rate for the coast, then halt
            span = min(dt, max(self.coast_left, 0.0))
            self.yaw += math.radians(self.last_rate) * span
            self.coast_left -= dt
            if self.coast_left <= 0:
                self.last_rate = 0.0
            return
        rate = 0.0  # deg/s
        if not self.stuck:
            vx, vyaw = self.cmd
            if abs(vyaw) >= 0.99 and vx > 0:  # a full-yaw arc
                rate = 32.0 if vyaw > 0 else -41.0
            else:  # walking: steering is proportional, on top of the gait's rightward curve
                rate = vyaw * 25.0 + self.curve_dps
            self.ahead = max(0.0, self.ahead - vx * 0.42 * dt)
        self.last_rate = rate
        self.yaw += math.radians(rate) * dt


def test_a_turn_lands_on_the_requested_angle_both_ways() -> None:
    for degrees in (90.0, -45.0, 30.0, -150.0):
        body = _Body()
        clock = _Clock(body)
        result = turn_by(body, degrees, now=clock.now, sleep=clock.sleep)  # type: ignore[arg-type]
        assert result.closed_loop
        actual = math.degrees(body.yaw)
        assert abs(actual - degrees) <= TURN_TOLERANCE_DEG, (degrees, actual)
        assert result.turned_deg is not None and abs(result.turned_deg - actual) < 1.0
        assert body.calls[-1] == "stop"


def test_a_turn_that_cannot_move_gives_up_and_stops() -> None:
    body = _Body(stuck=True)
    clock = _Clock(body)
    result = turn_by(body, 90.0, now=clock.now, sleep=clock.sleep)  # type: ignore[arg-type]
    assert clock.t < 10.0  # time-capped, never spins forever
    assert result.turned_deg is not None and abs(result.turned_deg) < 1.0  # reports the truth
    assert body.calls[-1] == "stop"


def test_without_a_heading_a_turn_is_one_timed_move() -> None:
    robot = FakeRobot()
    result = turn_by(robot, 60.0)
    assert not result.closed_loop and result.turned_deg is None
    assert [c.method for c in robot.calls] == ["drive", "stop"]  # the fake's drive_for


def test_a_walk_stops_short_of_the_wall() -> None:
    body = _Body(wall_m=1.5)
    clock = _Clock(body)
    result = walk(body, 20.0, now=clock.now, sleep=clock.sleep)  # type: ignore[arg-type]
    assert result.blocked
    assert STOP_AT_M - 0.1 <= body.ahead <= STOP_AT_M
    assert clock.t < 20.0 and body.calls[-1] == "stop"


def test_a_walk_does_not_start_into_something_close() -> None:
    body = _Body(wall_m=0.3)
    clock = _Clock(body)
    result = walk(body, 3.0, now=clock.now, sleep=clock.sleep)  # type: ignore[arg-type]
    assert result.blocked and "drive" not in body.calls


def test_a_walk_holds_its_heading_against_the_gaits_curve() -> None:
    body = _Body(wall_m=50.0, curve_dps=-12.0)
    clock = _Clock(body)
    result = walk(body, 5.0, now=clock.now, sleep=clock.sleep)  # type: ignore[arg-type]
    assert not result.blocked
    assert abs(math.degrees(body.yaw)) < 4.0  # open-loop trim alone would leave a steady curve


def test_without_sensors_a_walk_is_one_timed_move() -> None:
    robot = FakeRobot()
    result = walk(robot, 2.5)
    assert not result.blocked and result.range_m is None
    assert [c.method for c in robot.calls] == ["drive", "stop"]


def test_a_blocked_turn_stops_pushing_quickly() -> None:
    class Jammed(_Body):
        def advance(self, dt: float) -> None:
            super().advance(dt)
            self.yaw = min(self.yaw, math.radians(40))  # pressed against a wall at 40°

    body = Jammed()
    clock = _Clock(body)
    result = turn_by(body, 120.0, now=clock.now, sleep=clock.sleep)  # type: ignore[arg-type]
    assert result.turned_deg is not None and abs(result.turned_deg - 40) < 1
    assert clock.t < 4.0  # gave up on the stall, not at the time cap
    assert body.calls[-1] == "stop"
