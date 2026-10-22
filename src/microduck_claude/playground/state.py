"""Fold the duck's intent stream into a small renderable state for the UI."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from ..robot import RobotCall


@dataclass
class DuckState:
    """A JSON-serializable snapshot of the duck, built from its robot calls."""

    neck_pitch: float = 0.0
    head_pitch: float = 0.0
    head_yaw: float = 0.0
    head_roll: float = 0.0
    body_z: float = 0.0
    body_roll: float = 0.0
    body_pitch: float = 0.0
    mouth: float = 0.0
    driving: bool = False
    last_sound: str | None = None
    last_behavior: str | None = None
    events: int = 0

    def apply(self, call: RobotCall) -> None:
        """Fold one robot call into the state."""
        self.events += 1
        kw = call.kwargs
        if call.method == "set_head":
            self.neck_pitch = _f(kw.get("neck_pitch"))
            self.head_pitch = _f(kw.get("head_pitch"))
            self.head_yaw = _f(kw.get("head_yaw"))
            self.head_roll = _f(kw.get("head_roll"))
        elif call.method == "set_pose":
            self.body_z = _f(kw.get("z"))
            self.body_roll = _f(kw.get("roll"))
            self.body_pitch = _f(kw.get("pitch"))
        elif call.method == "set_mouth":
            self.mouth = _f(kw.get("open_fraction"))
        elif call.method == "play_sound":
            tag = kw.get("tag")
            self.last_sound = tag if isinstance(tag, str) else None
        elif call.method == "do_behavior":
            skill = kw.get("skill")
            self.last_behavior = skill if isinstance(skill, str) else None
        elif call.method == "drive":
            self.driving = any(_f(kw.get(axis)) != 0.0 for axis in ("vx", "vy", "vyaw"))
        elif call.method == "stop":
            self.driving = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _f(value: object) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0
