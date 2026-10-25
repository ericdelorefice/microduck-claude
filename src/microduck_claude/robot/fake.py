"""FakeRobot — the Milestone 1 body: in-process, deterministic, fully inspectable.

It records every intent as a :class:`RobotCall` and keeps a little state, so the
chat REPL can show what the duck did and tests can assert on it. No hardware, no
simulator process, no network. It structurally satisfies :class:`RobotInterface`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from .interface import SOUND_TAGS, STOCK_BEHAVIORS


@dataclass
class RobotCall:
    """A single recorded intent sent to the robot."""

    method: str
    kwargs: dict[str, object] = field(default_factory=dict)


class FakeRobot:
    """An in-process stand-in for a Microduck that records what it was told to do."""

    def __init__(
        self,
        on_call: Callable[[RobotCall], None] | None = None,
        *,
        camera_frame: bytes | None = None,
    ) -> None:
        self.calls: list[RobotCall] = []
        self._on_call = on_call  # optional live observer (used by the playground)
        self.camera_frame = camera_frame  # what capture_frame() returns (None = no camera)
        self._battery = 0.87
        self._behaviors: list[str] = list(STOCK_BEHAVIORS)
        self._head: dict[str, float] = {
            "neck_pitch": 0.0,
            "head_pitch": 0.0,
            "head_yaw": 0.0,
            "head_roll": 0.0,
        }
        self._pose: dict[str, float] = {"z": 0.0, "roll": 0.0, "pitch": 0.0}
        self._active = True
        self._driving = False

    def _record(self, method: str, **kwargs: object) -> None:
        call = RobotCall(method=method, kwargs=dict(kwargs))
        self.calls.append(call)
        if self._on_call is not None:
            self._on_call(call)

    # -- intents ---------------------------------------------------------------

    def do_behavior(self, skill: str) -> bool:
        accepted = skill in self._behaviors
        self._record("do_behavior", skill=skill, accepted=accepted)
        return accepted

    def drive(self, vx: float, vy: float, vyaw: float) -> None:
        self._driving = not (vx == vy == vyaw == 0.0)
        self._record("drive", vx=vx, vy=vy, vyaw=vyaw)

    def stop(self) -> None:
        self._driving = False
        self._record("stop")

    def drive_for(self, vx: float, vy: float, vyaw: float, *, duration: float) -> None:
        # In-process: no deadman to beat, so record a single intent and stop (the `duration`
        # is a real-body streaming concern). Tests see the same drive + stop as a live body.
        self.drive(vx, vy, vyaw)
        self.stop()

    def set_head(
        self,
        *,
        neck_pitch: float = 0.0,
        head_pitch: float = 0.0,
        head_yaw: float = 0.0,
        head_roll: float = 0.0,
    ) -> None:
        self._head = {
            "neck_pitch": neck_pitch,
            "head_pitch": head_pitch,
            "head_yaw": head_yaw,
            "head_roll": head_roll,
        }
        self._record(
            "set_head",
            neck_pitch=neck_pitch,
            head_pitch=head_pitch,
            head_yaw=head_yaw,
            head_roll=head_roll,
        )

    def look_at(self, x: float, y: float, z: float, *, neck_pitch: float = 0.0) -> None:
        self._record("look_at", x=x, y=y, z=z, neck_pitch=neck_pitch)

    def set_pose(
        self,
        *,
        z: float = 0.0,
        roll: float = 0.0,
        pitch: float = 0.0,
        active: bool = True,
    ) -> None:
        self._pose = {"z": z, "roll": roll, "pitch": pitch}
        self._active = active
        self._record("set_pose", z=z, roll=roll, pitch=pitch, active=active)

    def set_mouth(self, open_fraction: float) -> None:
        if not 0.0 <= open_fraction <= 1.0:
            raise ValueError("open_fraction must be within [0.0, 1.0]")
        self._record("set_mouth", open_fraction=open_fraction)

    def play_sound(self, tag: str) -> None:
        if tag not in SOUND_TAGS:
            raise ValueError(f"unknown sound tag {tag!r}; valid: {', '.join(SOUND_TAGS)}")
        self._record("play_sound", tag=tag)

    # -- read-only -------------------------------------------------------------

    def list_behaviors(self) -> list[str]:
        return list(self._behaviors)

    def capture_frame(self) -> bytes | None:
        return self.camera_frame

    def get_state(self) -> dict[str, object]:
        return {
            "battery": self._battery,
            "head": dict(self._head),
            "pose": dict(self._pose),
            "active": self._active,
            "driving": self._driving,
            "behaviors": list(self._behaviors),
            "recorded_calls": len(self.calls),
        }

    def get_battery(self) -> float:
        return self._battery
