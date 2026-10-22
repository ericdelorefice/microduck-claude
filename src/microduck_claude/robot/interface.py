"""The robot control interface — intent-level, mirroring Microduck's contract.

Callers send *intents* (nod, drive, do a behaviour), never raw motor writes. This
mirrors the real `duck-ipc-proto` JSON-RPC surface so that a FakeRobot (Milestone 1)
and a real RpcRobot (Milestone 2) are interchangeable, exactly as Reachy Mini keeps
its simulator API-identical to hardware.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

# The Microduck's fixed on-board voice bank (the only sounds `robot.sound {tag}`
# can play today — arbitrary audio is not yet possible; see docs/PLAN.md §2.4).
SOUND_TAGS: tuple[str, ...] = (
    "alarm",
    "greet",
    "inquire",
    "peck",
    "chirp",
    "coo",
    "wheee",
)

# Default stock behaviours invoked via `robot.do {skill}`. On real hardware the set
# is config-driven and advertised by the robot; this is the documented default.
STOCK_BEHAVIORS: tuple[str, ...] = (
    "ground_pick",
    "kick_left",
    "kick_right",
    "sit_toggle",
    "roulade",
)


@runtime_checkable
class RobotInterface(Protocol):
    """Intent-level control surface. Implementations must be substitutable."""

    def do_behavior(self, skill: str) -> bool:
        """Request a named behaviour. Returns whether it was accepted.

        Mirrors `robot.do` → `IntentResult{accepted}`: a refusal is a ``False``
        return, not an exception.
        """
        ...

    def drive(self, vx: float, vy: float, vyaw: float) -> None:
        """Set a continuous velocity twist (m/s, m/s, rad/s)."""
        ...

    def stop(self) -> None:
        """Command zero velocity (not 'go limp')."""
        ...

    def set_head(
        self,
        *,
        neck_pitch: float = 0.0,
        head_pitch: float = 0.0,
        head_yaw: float = 0.0,
        head_roll: float = 0.0,
    ) -> None:
        """Set head joint angles (radians)."""
        ...

    def look_at(self, x: float, y: float, z: float, *, neck_pitch: float = 0.0) -> None:
        """Gaze toward a trunk-frame point (metres); the robot runs the IK."""
        ...

    def set_pose(
        self,
        *,
        z: float = 0.0,
        roll: float = 0.0,
        pitch: float = 0.0,
        active: bool = True,
    ) -> None:
        """Set the body pose (height offset + roll/pitch)."""
        ...

    def set_mouth(self, open_fraction: float) -> None:
        """Open the beak, 0.0 (closed) .. 1.0 (open)."""
        ...

    def play_sound(self, tag: str) -> None:
        """Play a fixed voice-bank sound (one of :data:`SOUND_TAGS`)."""
        ...

    def list_behaviors(self) -> list[str]:
        """List the behaviours this robot currently advertises."""
        ...

    def get_state(self) -> dict[str, object]:
        """Return a snapshot of robot state (read-only)."""
        ...

    def get_battery(self) -> float:
        """Return the battery level, 0.0 .. 1.0 (read-only)."""
        ...
