"""The core, safe, non-personal tools shipped with the open project.

Deliberately minimal: a clock, the gesture catalogue, robot status (all read-only),
and one action (`perform_gesture`). Personal integrations (calendars, chats) are
NOT here — they belong in a private tool provider (see plugins/), never the core.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from ..expressions import UnknownGestureError, gesture_catalog, gesture_names, perform_gesture
from ..robot.interface import RobotInterface
from .base import FunctionTool, Risk, Tool, ToolResult

_NO_ARGS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


def build_core_tools(robot: RobotInterface) -> list[Tool]:
    """Build the core tool set, bound to a particular robot."""

    def _get_time(_: dict[str, Any]) -> ToolResult:
        return ToolResult(datetime.now().astimezone().strftime("%A %Y-%m-%d %H:%M:%S %Z"))

    def _list_gestures(_: dict[str, Any]) -> ToolResult:
        lines = [f"- {name}: {desc}" for name, desc in gesture_catalog()]
        return ToolResult("Available gestures:\n" + "\n".join(lines))

    def _robot_status(_: dict[str, Any]) -> ToolResult:
        return ToolResult(json.dumps(robot.get_state(), default=str, sort_keys=True))

    def _perform_gesture(arguments: dict[str, Any]) -> ToolResult:
        name = arguments.get("gesture")
        if not isinstance(name, str):
            return ToolResult("missing required string argument 'gesture'", ok=False)
        try:
            gesture = perform_gesture(robot, name)
        except UnknownGestureError:
            return ToolResult(
                f"unknown gesture {name!r}; call list_gestures for valid names", ok=False
            )
        return ToolResult(f"performed gesture: {gesture.name}")

    def _gesture_preview(arguments: dict[str, Any]) -> str:
        return f"perform the gesture {arguments.get('gesture')!r}"

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
            "perform_gesture",
            "Make the duck perform a named physical gesture to match the conversation.",
            Risk.ACTION,
            gesture_schema,
            _perform_gesture,
            preview=_gesture_preview,
        ),
    ]
