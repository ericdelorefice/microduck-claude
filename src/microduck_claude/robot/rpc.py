"""RpcRobot — drive a real Microduck (or duck-sim) over the duck-ipc-proto contract.

A drop-in for :class:`FakeRobot`: it satisfies :class:`RobotInterface`, so the
expression layer, tools, and safety gate work against it unchanged. Continuous
commands (move/head/pose/mouth/sound) are sent as JSON-RPC notifications;
discrete ones (hello/do/look/policies/health) are requests. All method names and
the request-vs-notification choice live in :mod:`.protocol` and are flagged there
for confirmation against the live contract.
"""

from __future__ import annotations

import http.client
import logging
import time
import urllib.error
import urllib.request
from typing import Any

from . import protocol as p
from .interface import SOUND_TAGS
from .transport import JsonRpcError, UnixSocketTransport

log = logging.getLogger("microduck_claude.robot.rpc")

BATTERY_UNKNOWN = -1.0

# Resend a drive twist at 10 Hz while driving for a duration: well inside robotd's ~500 ms
# deadman, which zeros the twist if notifications stop arriving.
_KEEPALIVE_INTERVAL_S = 0.1

# Camera capture: validate the payload before it leaves the robot layer. The endpoint is
# untrusted plumbing (a 200 can be an HTML error page or an MJPEG stream), and the Anthropic
# per-image limit is 5 MB, so an over-limit or non-image frame is treated as "no frame".
_MAX_FRAME_BYTES = 5 * 1024 * 1024
_IMAGE_MAGIC: tuple[bytes, ...] = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF8")


def _looks_like_image(data: bytes) -> bool:
    if any(data.startswith(sig) for sig in _IMAGE_MAGIC):
        return True
    return data[:4] == b"RIFF" and data[8:12] == b"WEBP"  # WEBP


class RpcRobot:
    """A :class:`RobotInterface` backed by a JSON-RPC transport."""

    def __init__(
        self,
        transport: UnixSocketTransport,
        *,
        api_version: int = p.API_VERSION,
        subscribe_hz: float = 2.0,
        camera_url: str = "",
    ) -> None:
        self._t = transport
        self._api_version = api_version
        self._subscribe_hz = subscribe_hz
        self._camera_url = camera_url

    def handshake(self) -> dict[str, Any] | None:
        """Perform the ``hello`` handshake and start a state subscription."""
        result = self._t.request(p.HELLO, {"api_version": self._api_version})
        if self._subscribe_hz:
            # robot.subscribe is a request; hz is an integer (frames arrive as
            # robot.state notifications thereafter).
            self._t.request(p.ROBOT_SUBSCRIBE, {"hz": int(self._subscribe_hz)})
        return result if isinstance(result, dict) else None

    def close(self) -> None:
        self._t.close()

    # -- intents ---------------------------------------------------------------

    def do_behavior(self, skill: str) -> bool:
        result = self._t.request(p.ROBOT_DO, {"skill": skill})
        return bool(result.get("accepted", False)) if isinstance(result, dict) else False

    def drive(self, vx: float, vy: float, vyaw: float) -> None:
        self._t.notify(p.ROBOT_MOVE, {"vx": vx, "vy": vy, "vyaw": vyaw})

    def stop(self) -> None:
        self._t.request(p.ROBOT_STOP)

    def drive_for(self, vx: float, vy: float, vyaw: float, *, duration: float) -> None:
        # Keep resending the twist so the walk policy stays engaged (robotd expires an intent
        # ~500 ms after notifications stop), then stop. Blocks for roughly `duration`.
        # The stop is in a finally: a Ctrl-C or a transport error mid-drive must not leave the
        # last twist standing until robotd's deadman expires it.
        deadline = time.monotonic() + duration
        try:
            while time.monotonic() < deadline:
                self.drive(vx, vy, vyaw)
                time.sleep(_KEEPALIVE_INTERVAL_S)
        finally:
            self.stop()

    def set_head(
        self,
        *,
        neck_pitch: float = 0.0,
        head_pitch: float = 0.0,
        head_yaw: float = 0.0,
        head_roll: float = 0.0,
    ) -> None:
        self._t.notify(
            p.ROBOT_HEAD,
            {
                "neck_pitch": neck_pitch,
                "head_pitch": head_pitch,
                "head_yaw": head_yaw,
                "head_roll": head_roll,
            },
        )

    def look_at(self, x: float, y: float, z: float, *, neck_pitch: float = 0.0) -> None:
        self._t.request(p.ROBOT_LOOK, {"x": x, "y": y, "z": z, "neck_pitch": neck_pitch})

    def set_pose(
        self,
        *,
        z: float = 0.0,
        roll: float = 0.0,
        pitch: float = 0.0,
        active: bool = True,
    ) -> None:
        self._t.notify(p.ROBOT_POSE, {"z": z, "roll": roll, "pitch": pitch, "active": active})

    def set_mouth(self, open_fraction: float) -> None:
        if not 0.0 <= open_fraction <= 1.0:
            raise ValueError("open_fraction must be within [0.0, 1.0]")
        self._t.notify(p.ROBOT_MOUTH, {"open": open_fraction})

    def play_sound(self, tag: str) -> None:
        if tag not in SOUND_TAGS:
            raise ValueError(f"unknown sound tag {tag!r}; valid: {', '.join(SOUND_TAGS)}")
        self._t.request(p.ROBOT_SOUND, {"tag": tag})

    # -- read-only -------------------------------------------------------------

    def list_behaviors(self) -> list[str]:
        return _extract_skills(self._t.request(p.ROBOT_POLICIES))

    def get_state(self) -> dict[str, object]:
        return self._t.latest_state() or {}

    def capture_frame(self) -> bytes | None:
        """Fetch one camera frame over HTTP and validate it (see RobotInterface).

        Returns bytes only for a genuine, supported image within the model's size limit. A
        non-image 200, an oversized frame, or a truncated/dropped response all yield None, so a
        bad frame never becomes a model image block that would 400 the API.
        """
        if not self._camera_url:
            return None
        try:
            with urllib.request.urlopen(self._camera_url, timeout=4.0) as response:
                if getattr(response, "status", 200) != 200:
                    return None
                data: bytes = response.read(_MAX_FRAME_BYTES + 1)  # one extra byte flags oversize
        except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException):
            return None
        if not data or len(data) > _MAX_FRAME_BYTES:
            return None
        if not _looks_like_image(data):
            return None
        return data

    def get_battery(self) -> float:
        """Battery level 0..1, or ``BATTERY_UNKNOWN`` (-1.0) if unavailable.

        Battery is not in ``robot.state``; it comes from ``robot.health`` as
        ``battery: {volts, percent}`` (``null`` means "not known yet", never 0).
        """
        try:
            result = self._t.request(p.ROBOT_HEALTH)
        except JsonRpcError:
            log.warning("robot.health unavailable; battery unknown")
            return BATTERY_UNKNOWN
        if isinstance(result, dict):
            battery = result.get("battery")
            if isinstance(battery, dict):
                percent = battery.get("percent")
                if isinstance(percent, (int, float)):
                    return float(percent) / 100.0
        return BATTERY_UNKNOWN


def _extract_skills(result: Any) -> list[str]:
    """Defensively pull behaviour/skill names from a ``robot.policies`` result."""
    names: list[str] = []
    if isinstance(result, list):
        return [item for item in result if isinstance(item, str)]
    if isinstance(result, dict):
        for key in ("skills", "behaviors", "slots"):
            value = result.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        names.append(item)
                    elif isinstance(item, dict):
                        name = item.get("skill") or item.get("name")
                        if isinstance(name, str):
                            names.append(name)
                break
    return names
