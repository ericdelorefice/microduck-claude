"""The core, safe, non-personal tools shipped with the open project.

Deliberately minimal: a clock, the gesture catalogue, robot status (all read-only),
and one action (`perform_gesture`). Personal integrations (calendars, chats) are
NOT here — they belong in a private tool provider (see plugins/), never the core.
"""

from __future__ import annotations

import http.client
import json
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any

from ..expressions import (
    GestureUnavailableError,
    UnknownGestureError,
    gesture_catalog,
    gesture_names,
    is_consequential_gesture,
    perform_gesture,
)
from ..robot import JsonRpcError
from ..robot.interface import RobotInterface
from .base import FunctionTool, Risk, Tool, ToolResult

_NO_ARGS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


_MAX_FRAME_BYTES = 5 * 1024 * 1024  # the Anthropic per-image limit; a real frame is far smaller

# Magic bytes for the image formats the vision models accept. The camera endpoint is untrusted
# plumbing — a 200 can carry an HTML error page or an MJPEG multipart stream — so we verify the
# payload really is a supported image before handing it to the model.
_IMAGE_MAGIC: tuple[bytes, ...] = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF8")

# Turning is a gait, not an instant pivot: the walk policy needs the yaw intent SUSTAINED to
# engage (a brief command barely moves, and robotd's deadman zeros the twist between commands).
# So a turn streams for a startup runway plus an angle-proportional time, with a floor so even a
# small turn actually pivots. Rates are approximate — the model sees the result and can turn again.
_TURN_START_S = 1.2  # gait startup before meaningful rotation
_TURN_DEG_PER_S = 20.0  # effective yaw rate once engaged (at |vyaw|=1.0)
_TURN_MIN_S = 2.5  # minimum sustained turn, so the gait always engages


def _looks_like_image(data: bytes) -> bool:
    """True if ``data`` begins with the magic bytes of a model-supported image format."""
    if any(data.startswith(sig) for sig in _IMAGE_MAGIC):
        return True
    return data[:4] == b"RIFF" and data[8:12] == b"WEBP"  # WEBP


def _capture_camera_png(url: str, *, timeout: float = 4.0) -> bytes | None:
    """GET a single camera frame, or None if it is unavailable or not a usable image.

    Returns bytes only for a genuine, supported image within the model's per-image size limit.
    A non-image 200 (an HTML error page, an MJPEG stream), an oversized frame, or a truncated /
    dropped response all yield None — so a bad frame never becomes an image block that would 400
    the API and poison the conversation; the caller just reports that no camera is available.
    """
    if not url:
        return None
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            if getattr(response, "status", 200) != 200:
                return None
            data: bytes = response.read(_MAX_FRAME_BYTES + 1)  # one extra byte flags oversize
    except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException):
        return None
    if not data or len(data) > _MAX_FRAME_BYTES:
        return None  # missing, or larger than the model will accept
    if not _looks_like_image(data):
        return None  # a 200 that is not actually a supported image
    return data


def build_core_tools(
    robot: RobotInterface,
    *,
    gesture_pace: float = 0.0,
    camera_url: str = "",
    stream_velocity: bool = False,
) -> list[Tool]:
    """Build the core tool set, bound to a particular robot.

    ``gesture_pace`` holds each motion step for that many seconds so it is visible on a real
    body (0 = instant, for the FakeRobot and tests). ``stream_velocity`` resends drive intents
    at 10 Hz so the walk policy actually engages on a live body — this is a property of the
    transport (the real robotd expires an intent ~500 ms after commands stop), NOT of pacing, so
    it is passed explicitly, not inferred from ``gesture_pace``. ``camera_url`` is the duck's
    camera snapshot endpoint for the vision tools (empty = no camera).
    """

    def _get_time(_: dict[str, Any]) -> ToolResult:
        return ToolResult(datetime.now().astimezone().strftime("%A %Y-%m-%d %H:%M:%S %Z"))

    def _list_gestures(_: dict[str, Any]) -> ToolResult:
        lines = [f"- {name}: {desc}" for name, desc in gesture_catalog()]
        return ToolResult("Available gestures:\n" + "\n".join(lines))

    def _robot_status(_: dict[str, Any]) -> ToolResult:
        return ToolResult(json.dumps(robot.get_state(), default=str, sort_keys=True))

    def _camera_result(got: str, missing: str) -> ToolResult:
        """Capture a frame and return it as the view, or an honest 'no camera' result."""
        png = _capture_camera_png(camera_url)
        if png is None:
            return ToolResult(missing, ok=False)
        return ToolResult(got, image_png=png)

    def _sustain_drive(*, vx: float, vy: float, vyaw: float, seconds: float) -> None:
        # Drive the body and always stop. On a live body resend the twist at 10 Hz for
        # `seconds` so the walk policy engages (robotd's deadman zeros an intent ~500 ms after
        # commands stop); otherwise record a single intent (FakeRobot / tests).
        try:
            if stream_velocity:
                deadline = time.monotonic() + seconds
                while time.monotonic() < deadline:
                    robot.drive(vx=vx, vy=vy, vyaw=vyaw)
                    time.sleep(0.1)
            else:
                robot.drive(vx=vx, vy=vy, vyaw=vyaw)
        finally:
            robot.stop()

    def _see(_: dict[str, Any]) -> ToolResult:
        return _camera_result(
            "Here is what the duck's camera sees right now.",
            "no camera is available right now (run the sim with a camera, e.g. "
            "DUCK_SIM_CAMERAS=a, or check the duck's camera is streaming)",
        )

    def _look_around(_: dict[str, Any]) -> ToolResult:
        # Looking is perception, not a gated action — the head movement is just how the duck
        # looks around (like turning to see), so this stays read-only, like `see`.
        for head_yaw in (-0.5, 0.0, 0.5):
            robot.set_head(head_yaw=head_yaw, head_pitch=-0.2)  # sweep, gaze lifted off the floor
            if gesture_pace:
                time.sleep(gesture_pace)
        robot.set_head(head_pitch=-0.2)  # settle facing forward, looking up a little
        if gesture_pace:
            time.sleep(gesture_pace)
        return _camera_result(
            "I looked around — here's the view ahead after sweeping left and right.",
            "I looked around, but my camera isn't available right now "
            "(run the sim with DUCK_SIM_CAMERAS=a, or check the camera is streaming).",
        )

    def _perform_gesture(arguments: dict[str, Any]) -> ToolResult:
        name = arguments.get("gesture")
        if not isinstance(name, str):
            return ToolResult("missing required string argument 'gesture'", ok=False)
        try:
            gesture = perform_gesture(robot, name, pace=gesture_pace)
        except UnknownGestureError:
            return ToolResult(
                f"unknown gesture {name!r}; call list_gestures for valid names", ok=False
            )
        except GestureUnavailableError:
            return ToolResult(
                f"the duck can't do {name!r} on this body — it declined the move", ok=False
            )
        except (JsonRpcError, OSError) as exc:
            return ToolResult(f"couldn't reach the duck to do {name!r}: {exc}", ok=False)
        return ToolResult(f"performed gesture: {gesture.name}")

    def _gesture_preview(arguments: dict[str, Any]) -> str:
        return f"do a little {arguments.get('gesture')}"

    def _explore(_: dict[str, Any]) -> ToolResult:
        # A bounded, safe autonomous roam: two short forward legs, looking between them. The
        # caps live here (not with the model) and the duck always stops at the end. Sim-safe as
        # written; a physical robot needs hardware limits (speed cap, tilt/bump stop, a kill)
        # first — see PLAN §6.
        try:
            for _leg in range(2):
                _sustain_drive(vx=0.45, vy=0.0, vyaw=0.0, seconds=2.5)
                robot.set_head(head_pitch=-0.2)  # look ahead after the leg
                if gesture_pace:
                    time.sleep(gesture_pace)
        finally:
            robot.stop()  # never leave the duck driving
        return _camera_result(
            "I roamed forward a little on my own, pausing to look — here's where I ended up.",
            "I had a short roam around, but my camera isn't available to show what I "
            "found (run the sim with DUCK_SIM_CAMERAS=a).",
        )

    def _explore_preview(_: dict[str, Any]) -> str:
        return "roam around a little on my own to see what's here"

    def _turn(arguments: dict[str, Any]) -> ToolResult:
        # Rotate roughly in place to face a new direction, then report the new view. Bounded
        # (|angle| <= 180) and always stops. Positive = left (CCW), negative = right. The yaw
        # intent is sustained via _sustain_drive so the walk policy actually pivots on a real body.
        raw = arguments.get("degrees", 60)
        try:
            degrees = max(-180.0, min(180.0, float(raw)))
        except (TypeError, ValueError):
            return ToolResult("'degrees' must be a number between -180 and 180", ok=False)
        if abs(degrees) < 1.0:  # no meaningful turn requested — just report the current view
            return _camera_result(
                "I'm already facing that way — here's what's in front of me.",
                "I didn't need to turn, but my camera isn't available "
                "(run the sim with DUCK_SIM_CAMERAS=a).",
            )
        vyaw = 1.0 if degrees > 0 else -1.0
        duration = max(_TURN_MIN_S, _TURN_START_S + abs(degrees) / _TURN_DEG_PER_S)
        _sustain_drive(vx=0.0, vy=0.0, vyaw=vyaw, seconds=duration)
        robot.set_head(head_pitch=-0.1)  # settle, gaze roughly level
        if gesture_pace:
            time.sleep(gesture_pace)
        side = "left" if degrees > 0 else "right"
        return _camera_result(
            f"I turned about {abs(int(degrees))}° to the {side} — here's what's "
            "in front of me now.",
            f"I turned about {abs(int(degrees))}° to the {side}, but my camera isn't "
            "available (run the sim with DUCK_SIM_CAMERAS=a).",
        )

    def _turn_preview(arguments: dict[str, Any]) -> str:
        return f"turn to look a different way ({arguments.get('degrees', 60)}°)"

    turn_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "degrees": {
                "type": "number",
                "minimum": -180,
                "maximum": 180,
                "description": "Degrees to turn in place; positive = left, negative = right.",
            }
        },
        "required": ["degrees"],
        "additionalProperties": False,
    }

    gesture_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "gesture": {
                "type": "string",
                "enum": gesture_names(),
                "description": "Which gesture to perform.",
            }
        },
        "required": ["gesture"],
        "additionalProperties": False,
    }

    return [
        FunctionTool(
            "get_time",
            "Get the current local date and time.",
            Risk.READ_ONLY,
            _NO_ARGS_SCHEMA,
            _get_time,
        ),
        FunctionTool(
            "list_gestures",
            "List the gestures/expressions the duck can perform.",
            Risk.READ_ONLY,
            _NO_ARGS_SCHEMA,
            _list_gestures,
        ),
        FunctionTool(
            "get_robot_status",
            "Get the duck's current state: battery, head/body pose, and recent activity.",
            Risk.READ_ONLY,
            _NO_ARGS_SCHEMA,
            _robot_status,
        ),
        FunctionTool(
            "see",
            "Look through the duck's own camera at what is in front of it right now.",
            Risk.READ_ONLY,
            _NO_ARGS_SCHEMA,
            _see,
        ),
        FunctionTool(
            "look_around",
            "Look around (sweep the head left and right) and report what the duck sees — "
            "use it to get your bearings or when asked what's nearby.",
            Risk.READ_ONLY,
            _NO_ARGS_SCHEMA,
            _look_around,
        ),
        FunctionTool(
            "perform_gesture",
            "Make the duck perform a named physical gesture to match the conversation.",
            Risk.ACTION,
            gesture_schema,
            _perform_gesture,
            preview=_gesture_preview,
            # A nod can auto-run under trust, but a dynamic trick (roulade/kick) is
            # consequential and must be confirmed even under trust (CLAUDE.md #4).
            confirm_when=lambda a: is_consequential_gesture(a.get("gesture")),
        ),
        FunctionTool(
            "explore",
            "Roam a little on your own — a short, bounded forward wander, pausing to look — and "
            "report what you find. Use when asked to explore or go see what's around.",
            Risk.ACTION,
            _NO_ARGS_SCHEMA,
            _explore,
            preview=_explore_preview,
            confirm_always=True,  # free locomotion: confirmed even under trust (CLAUDE.md #4)
        ),
        FunctionTool(
            "turn",
            "Turn in place to face a new direction (positive degrees = left, negative = right), "
            "then report what the duck now sees. Use it to look toward a different wall or object "
            "before walking to it or examining it.",
            Risk.ACTION,
            turn_schema,
            _turn,
            preview=_turn_preview,
            confirm_always=True,  # free locomotion (a walking pivot): confirmed even under trust
        ),
    ]
