"""Locomotion that closes the loop on the duck's own sensors.

A timed move ("arc for 1.4 s", "walk for 2.5 s") scatters on the walk gait — a turn lands
within about 15° of what was asked — so the model spent whole rounds nudging left and right.
These read the body's own heading (robotd's IMU/odometry) and its head distance sensor (tofd),
both on the real robot, never the simulator's ground truth:

- :func:`turn_by` keeps arcing until the heading says it is there, stopping slightly early for
  the gait's coast, then makes at most one small correction.
- :func:`walk` steers back onto the heading it started on and stops when something is close.

A body that reports neither sensor (the in-process fake) gets the old single timed move. Every
move is time-capped and always ends with a stop.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass

from .interface import RobotInterface

Clock = Callable[[], float]
Sleep = Callable[[float], None]

TICK_S = 0.05  # control period: robot.state arrives at ~20 Hz

# Real time unless a caller passes its own; looked up per call so tests can swap in a fake clock.
_now: Clock = time.monotonic
_sleep: Sleep = time.sleep

# Turning is a gait, not an instant pivot. Measured on the sim walk policy: yaw with no forward
# velocity mostly does nothing (0 of 4 spins engaged), and |vyaw| below 1.0 barely rotates. Full
# yaw while stepping slowly forward — a tight arc — engaged on every one of 16 trials, with no
# start-up lag, about 32°/s to the left and 41°/s to the right (the gait leans right), drifting
# only ~0.25 m.
TURN_VX = 0.25  # forward step that lets the gait turn at all
TURN_LEFT_DEG_PER_S = 32.0  # measured arc-turn rates on the sim gait
TURN_RIGHT_DEG_PER_S = 41.0
TURN_MIN_S = 0.6  # shortest timed arc worth commanding (~20°), when there is no heading
TURN_LEAD_S = 0.1  # stop this long before arriving: the gait keeps turning briefly after a stop
# (0.2 s left every bench turn ~4° short; the duck's own heading agreed with ground truth ±2.5°)
TURN_TOLERANCE_DEG = 6.0  # close enough; a correction smaller than this overshoots anyway
TURN_SETTLE_S = 0.4  # let the coast finish before measuring
TURN_STALL_S = 0.5  # no heading progress for this long while turning: blocked, give up

# The walk gait curves right as it goes (measured), worse the faster it walks. A constant left
# yaw trim cancels most of it open-loop; with a heading, a PI term holds the start heading.
WALK_VX = 0.6  # 0.8 overshot into walls; 0.6 is controlled and faster than the old 0.45
WALK_YAW_TRIM = 0.3
WALK_HOLD_KP = 3.0  # vyaw per radian off heading
WALK_HOLD_KI = 1.5  # vyaw per radian-second, so a steady curve is trimmed out too
WALK_HOLD_TAU_S = 0.4  # smooth the heading first: each step sways the body ±7°
# The walk-to-stand shuffle kicks the heading by up to ~18° (measured), which is most of a
# walk's heading error — the path itself stays within a few cm. Slowing down first softens it
# and a closed-loop turn back afterwards removes most of the rest: on the bench, mean final
# heading error 15° plain -> 9° with the ramp -> 5° with the re-align (worst 9°).
WALK_RAMP_S = 0.5  # slow down over this long before stopping
WALK_RAMP_VX = 0.15
WALK_REALIGN = True  # after stopping, turn back onto the start heading if it slipped
STOP_AT_M = 0.55  # stop walking when something is this close ahead (head ToF)


@dataclass(frozen=True)
class TurnResult:
    turned_deg: float | None  # what the heading says actually happened, or None if unknown
    closed_loop: bool


@dataclass(frozen=True)
class WalkResult:
    blocked: bool  # stopped (or never started) because something was close ahead
    range_m: float | None  # distance ahead at the end, if the body has a distance sensor
    moved: bool = True  # False when it was already too close to start walking at all


def turn_command(degrees: float) -> tuple[float, float, float]:
    """``(vx, vyaw, duration)`` for a timed turn of about ``degrees`` (sign gives direction)."""
    left = degrees > 0
    rate = TURN_LEFT_DEG_PER_S if left else TURN_RIGHT_DEG_PER_S
    return (TURN_VX, 1.0 if left else -1.0, max(TURN_MIN_S, abs(degrees) / rate))


def _wrap(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


class _Yaw:
    """Accumulated heading change since start, unwrapped (so a 200° turn reads as 200°)."""

    def __init__(self, robot: RobotInterface, start: float) -> None:
        self._robot = robot
        self._prev = start
        self.total = 0.0  # radians, + = left

    def read(self) -> bool:
        heading = self._robot.heading()
        if heading is None:  # stale or missing this tick; the next read covers the gap
            return False
        self.total += _wrap(heading - self._prev)
        self._prev = heading
        return True


def turn_by(
    robot: RobotInterface,
    degrees: float,
    *,
    now: Clock | None = None,
    sleep: Sleep | None = None,
) -> TurnResult:
    """Turn about ``degrees`` (+ = left), by heading when the body reports one."""
    now = now or _now
    sleep = sleep or _sleep
    start = robot.heading()
    if start is None:
        vx, vyaw, duration = turn_command(degrees)
        robot.drive_for(vx, 0.0, vyaw, duration=duration)
        return TurnResult(turned_deg=None, closed_loop=False)
    yaw = _Yaw(robot, start)
    try:
        for _attempt in range(2):  # the turn, then at most one correction
            remaining = degrees - math.degrees(yaw.total)
            if abs(remaining) < TURN_TOLERANCE_DEG:
                break
            before = yaw.total
            _arc(robot, yaw, degrees, 1.0 if remaining > 0 else -1.0, now, sleep)
            sleep(TURN_SETTLE_S)
            yaw.read()
            if abs(math.degrees(yaw.total - before)) < 2.0:
                break  # it isn't turning (pressed against something?): don't keep trying
    finally:
        robot.stop()
    return TurnResult(turned_deg=math.degrees(yaw.total), closed_loop=True)


def _arc(
    robot: RobotInterface, yaw: _Yaw, target_deg: float, sign: float, now: Clock, sleep: Sleep
) -> None:
    nominal = TURN_LEFT_DEG_PER_S if sign > 0 else TURN_RIGHT_DEG_PER_S
    left_deg = abs(target_deg - math.degrees(yaw.total))
    deadline = now() + left_deg / nominal * 1.6 + 1.0  # a stuck body gives up, it never spins
    rate = nominal  # deg/s, refined from what the heading actually does
    last_t, last_total = now(), yaw.total
    moved_at, moved_total = last_t, yaw.total
    while now() < deadline:
        robot.drive(TURN_VX, 0.0, sign)
        sleep(TICK_S)
        if not yaw.read():
            continue
        t = now()
        if t > last_t:
            rate = 0.5 * rate + 0.5 * abs(math.degrees(yaw.total - last_total)) / (t - last_t)
        last_t, last_total = t, yaw.total
        if (target_deg - math.degrees(yaw.total)) * sign <= rate * TURN_LEAD_S:
            break
        if abs(math.degrees(yaw.total - moved_total)) >= 1.0:
            moved_at, moved_total = t, yaw.total
        elif t - moved_at > TURN_STALL_S:
            break  # commanding a turn and going nowhere: blocked, don't keep pushing
    robot.stop()


def walk(
    robot: RobotInterface,
    duration: float,
    *,
    vx: float = WALK_VX,
    stop_at: float = STOP_AT_M,
    now: Clock | None = None,
    sleep: Sleep | None = None,
) -> WalkResult:
    """Walk forward for up to ``duration`` seconds, straight, stopping short of obstacles."""
    now = now or _now
    sleep = sleep or _sleep
    start = robot.heading()
    ahead = robot.range_ahead()
    if start is None and ahead is None:
        robot.drive_for(vx, 0.0, WALK_YAW_TRIM, duration=duration)
        return WalkResult(blocked=False, range_m=None)
    if ahead is not None and ahead < stop_at:
        return WalkResult(blocked=True, range_m=ahead, moved=False)  # don't walk into it
    yaw = _Yaw(robot, start) if start is not None else None
    smooth_k = 1.0 - math.exp(-TICK_S / WALK_HOLD_TAU_S) if WALK_HOLD_TAU_S > 0 else 1.0
    error = integral = 0.0
    blocked = False
    deadline = now() + duration

    def step(speed: float) -> None:
        nonlocal error, integral
        vyaw = WALK_YAW_TRIM
        if yaw is not None and yaw.read():
            error += (yaw.total - error) * smooth_k
            integral += error * TICK_S
            vyaw -= WALK_HOLD_KP * error + WALK_HOLD_KI * integral
        robot.drive(speed, 0.0, max(-1.0, min(1.0, vyaw)))
        sleep(TICK_S)

    try:
        while now() < deadline:
            step(vx)
            ahead = robot.range_ahead()
            if ahead is not None and ahead < stop_at:
                blocked = True
                break
        ramp_end = now() + WALK_RAMP_S
        while now() < ramp_end:
            step(min(vx, WALK_RAMP_VX))
    finally:
        robot.stop()
    if WALK_REALIGN and yaw is not None:
        sleep(TURN_SETTLE_S)
        if yaw.read() and abs(math.degrees(yaw.total)) >= TURN_TOLERANCE_DEG:
            turn_by(robot, -math.degrees(yaw.total), now=now, sleep=sleep)
    return WalkResult(blocked=blocked, range_m=robot.range_ahead())
