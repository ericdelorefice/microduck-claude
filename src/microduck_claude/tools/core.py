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
from ..robot.motion import turn_by, walk
from .base import FunctionTool, Risk, Tool, ToolResult

_NO_ARGS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


# How far from a painting to stop. The camera sees ~31° above its axis (62° tall, upright), plus
# ~11° of head tilt when looking: to get the top of a gallery frame (~1.45 m) in view from a head
# at ~0.22 m takes ~1.3 m. At 0.9 m the duck said it was "right under it". Placards still read.
_VIEWING_DISTANCE_M = 1.3
# Head pitch (negative = up). Walking it looks ahead, so the distance sensor sees what is in the
# way; stopped in front of a painting, a level gaze shows only its bottom edge (measured on the sim
# at 1.3 m: -0.45 clips the top of the frame, -0.7 to -0.95 frame the whole picture).
_WALK_HEAD_PITCH = -0.2
_VIEW_HEAD_PITCH = -0.8
_EXPLORE_LEG_S = 2.5  # two legs of this, looking between them, per explore

# How wide the head camera's picture is, left edge to right edge. The alpha robot's IMX219 sees 62°
# across its long side and is mounted a quarter turn over, so the upright picture is the short
# side: 2·atan(tan 31° · 9/16) ≈ 37°. The gallery sim is set to match (scripts/gallery). Without it
# the model guessed "off to the right" meant ~45° and overshot; at the edge it is only ~19°.
CAMERA_HFOV_DEG = 37.3


def _view_note(hfov_deg: float) -> str:
    edge, half = hfov_deg / 2, hfov_deg / 4
    return (
        f"(My camera sees about {round(hfov_deg)}° from edge to edge: something at the left or "
        f"right edge is about {round(edge)}° that way, halfway to the edge about {round(half)}°.)"
    )


def build_core_tools(
    robot: RobotInterface, *, gesture_pace: float = 0.0, camera_hfov_deg: float = CAMERA_HFOV_DEG
) -> list[Tool]:
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

    view_note = _view_note(camera_hfov_deg)

    def _camera_result(got: str, missing: str) -> ToolResult:
        """Return the duck's current camera view, or an honest 'no camera' result."""
        png = robot.capture_frame()
        if png is None:
            return ToolResult(missing, ok=False)
        return ToolResult(f"{got} {view_note}", image_png=png)

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
        # A bounded, safe autonomous roam: up to two short forward legs, holding its heading and
        # looking between them, stopping at viewing distance from whatever is ahead when the
        # body has a distance sensor. The caps live here (not with the model) and the duck always
        # stops at the end. Sim-safe as written; a physical robot needs hardware limits (speed
        # cap, tilt/bump stop, a kill) first — see PLAN §6.
        result = None
        moved = False
        try:
            for _leg in range(2):
                robot.set_head(head_pitch=_WALK_HEAD_PITCH)  # look ahead while walking
                if gesture_pace:
                    time.sleep(gesture_pace)
                result = walk(robot, _EXPLORE_LEG_S, stop_at=_VIEWING_DISTANCE_M)
                moved = moved or result.moved
                if result.blocked:
                    break
        finally:
            robot.stop()  # never leave the duck driving
        if result is not None and result.blocked:  # something in front: look up at it
            robot.set_head(head_pitch=_VIEW_HEAD_PITCH)
            if gesture_pace:
                time.sleep(gesture_pace)
        ahead = result.range_m if result is not None else None
        if result is not None and result.blocked and not moved:
            what = "I didn't walk: something is already close in front of me"
            if ahead is not None:
                what = f"I didn't walk: something is already about {ahead:.1f} m in front of me"
            what += " (turn to face somewhere else to go on)"
        elif result is not None and result.blocked:
            what = "I walked up until something was close in front of me, and looked up at it"
            if ahead is not None:
                what = (
                    f"I walked up until something was about {ahead:.1f} m in front of me, "
                    "and stopped and looked up at it"
                )
        else:
            what = "I roamed forward a little on my own, pausing to look"
            if ahead is not None:
                what += f"; there's about {ahead:.1f} m of space ahead"
        return _camera_result(
            f"{what} — here's where I ended up.",
            f"{what}, but my camera isn't available to show what I found "
            "(run the sim with DUCK_SIM_CAMERAS=a).",
        )

    def _explore_preview(_: dict[str, Any]) -> str:
        return "roam around a little on my own to see what's here"

    def _turn(arguments: dict[str, Any]) -> ToolResult:
        # Turn to face a new direction (a tight arc, by heading when the body reports one — see
        # robot.motion), then report the new view and the angle actually turned, so the model
        # corrects from what happened rather than what it asked for. Bounded (|angle| <= 180),
        # time-capped, and always stops. Positive = left (CCW), negative = right.
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
        result = turn_by(robot, degrees)
        robot.set_head(head_pitch=-0.1)  # settle, gaze roughly level
        if gesture_pace:
            time.sleep(gesture_pace)
        if result.turned_deg is not None:  # measured by the duck's own heading
            turned = result.turned_deg
            did = f"I turned {abs(round(turned))}° to the {'left' if turned > 0 else 'right'}"
            if abs(turned - degrees) > 10:
                did += f" (you asked for {abs(int(degrees))}°)"
        else:
            did = f"I turned about {abs(int(degrees))}° to the {'left' if degrees > 0 else 'right'}"
        return _camera_result(
            f"{did} — here's what's in front of me now.",
            f"{did}, but my camera isn't available (run the sim with DUCK_SIM_CAMERAS=a).",
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
                    "within a few degrees of the request. To face something in the "
                    f"picture: at its left or right edge it is about {round(camera_hfov_deg / 2)}° "
                    f"away, halfway to the edge about {round(camera_hfov_deg / 4)}° — the "
                    "camera is narrow, so small turns. Then check the view and correct."
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
