"""The core, safe, non-personal tools shipped with the open project.

Deliberately minimal: a clock, the gesture catalogue, robot status (all read-only),
and one action (`perform_gesture`). Personal integrations (calendars, chats) are
NOT here — they belong in a private tool provider (see plugins/), never the core.
"""

from __future__ import annotations

import json
import time
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


# Turning is a gait, not an instant pivot. Measured on the sim walk policy: yaw with no forward
# velocity mostly does nothing (0 of 4 spins engaged), and |vyaw| below 1.0 barely rotates. Full
# yaw while stepping slowly forward — a tight arc — engaged on every one of 16 trials, with no
# start-up lag, about 32°/s to the left and 41°/s to the right (the gait leans right), drifting
# only ~0.25 m. So a turn is a full-yaw arc, its length set by the angle and the side. The result
# scatters by ~15°, so the model sees where it ended up and corrects from there.
_TURN_VX = 0.25  # forward step that lets the gait turn at all
_TURN_LEFT_DEG_PER_S = 32.0  # measured arc-turn rates on the sim gait
_TURN_RIGHT_DEG_PER_S = 41.0
_TURN_MIN_S = 0.6  # shortest arc worth commanding (~20°)

# The sim walk gait curves to the RIGHT as it walks forward (measured), worse the faster it goes. A
# constant small LEFT yaw while driving cancels that, so the duck walks roughly straight and reaches
# the piece it faces instead of veering into a pillar. Faster than the old timid 0.45 (~0.35 m/s and
# straight). Calibrated on the sim; the gait is noisy, so this corrects, not cures.
_WALK_VX = 0.6  # 0.8 overshot into walls; 0.6 is controlled and faster than old 0.45
_WALK_YAW_TRIM = 0.3  # constant left yaw that cancels the gait's rightward curve at _WALK_VX


def _turn_command(degrees: float) -> tuple[float, float, float]:
    """Pick ``(vx, vyaw, duration)`` for a turn of about ``degrees`` (sign gives direction).

    A tight full-yaw arc — the sim gait does not turn on the spot or at lower |vyaw| — held for as
    long as that side's measured rate needs. Small requests clamp to ``_TURN_MIN_S``.
    """
    left = degrees > 0
    rate = _TURN_LEFT_DEG_PER_S if left else _TURN_RIGHT_DEG_PER_S
    duration = max(_TURN_MIN_S, abs(degrees) / rate)
    return (_TURN_VX, 1.0 if left else -1.0, duration)


def build_core_tools(robot: RobotInterface, *, gesture_pace: float = 0.0) -> list[Tool]:
    """Build the core tool set, bound to a particular robot.

    ``gesture_pace`` holds each motion step for that many seconds so it is visible on a real
    body (0 = instant, for the FakeRobot and tests). The robot owns camera capture and the drive
    keep-alive (``robot.capture_frame`` / ``robot.drive_for``), so the tools here are
    backend-agnostic — they never do their own HTTP or velocity streaming.
    """

    def _get_time(_: dict[str, Any]) -> ToolResult:
        return ToolResult(datetime.now().astimezone().strftime("%A %Y-%m-%d %H:%M:%S %Z"))

    def _list_gestures(_: dict[str, Any]) -> ToolResult:
        lines = [f"- {name}: {desc}" for name, desc in gesture_catalog()]
        return ToolResult("Available gestures:\n" + "\n".join(lines))

    def _robot_status(_: dict[str, Any]) -> ToolResult:
        return ToolResult(json.dumps(robot.get_state(), default=str, sort_keys=True))

    def _camera_result(got: str, missing: str) -> ToolResult:
        """Return the duck's current camera view, or an honest 'no camera' result."""
        png = robot.capture_frame()
        if png is None:
            return ToolResult(missing, ok=False)
        return ToolResult(got, image_png=png)

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
                robot.drive_for(_WALK_VX, 0.0, _WALK_YAW_TRIM, duration=2.5)  # straight + faster
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
        # Turn to face a new direction (a tight arc — see _turn_command), then report the new
        # view. Bounded (|angle| <= 180) and always stops. Positive = left (CCW), negative =
        # right. The body's drive_for keeps the intent fresh so the walk policy actually turns.
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
        vx, vyaw, duration = _turn_command(degrees)  # a tight arc; the gait won't spin on the spot
        robot.drive_for(vx, 0.0, vyaw, duration=duration)  # the body owns the keep-alive
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
                "description": (
                    "Degrees to turn; positive = left, negative = right. The duck turns "
                    "in a tight arc, stepping a little forward as it goes, and lands "
                    "within about 15° of the request — so 20-120° to face a different "
                    "piece, then check the view and correct if needed."
                ),
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
            "Turn to face a new direction (positive degrees = left, negative = right), "
            "then report what the duck now sees. Use it to look toward a different wall or object "
            "before walking to it or examining it.",
            Risk.ACTION,
            turn_schema,
            _turn,
            preview=_turn_preview,
            confirm_always=True,  # free locomotion (a walking pivot): confirmed even under trust
        ),
    ]
