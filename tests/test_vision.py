from __future__ import annotations

import base64
from typing import cast

from microduck_claude.assembly import build_registry
from microduck_claude.brain import AnthropicLLM, ToolResult
from microduck_claude.robot import FakeRobot
from microduck_claude.tools import Risk
from tests.fakes import FakeAnthropic, text_response

# Any non-None bytes: the FakeRobot returns its camera_frame verbatim (validation of a real
# HTTP payload lives in RpcRobot.capture_frame, tested in test_rpc_robot.py).
_FRAME = b"\x89PNG\r\n\x1a\nfake-frame"


def test_see_tool_returns_a_camera_image() -> None:
    robot = FakeRobot(camera_frame=_FRAME)
    tool = build_registry(robot).get("see")
    assert tool is not None
    result = tool.run({})
    assert result.ok
    assert result.image_png == _FRAME


def test_see_tool_is_honest_without_a_camera() -> None:
    tool = build_registry(FakeRobot()).get("see")  # no camera_frame = no camera
    assert tool is not None
    result = tool.run({})
    assert not result.ok
    assert result.image_png is None


def test_anthropic_tool_result_includes_the_image_block() -> None:
    client = FakeAnthropic([text_response("I see a floor.")])
    llm = AnthropicLLM(client, model="m", max_tokens=50)
    llm.start("S", [])
    resp = llm.send_tool_results([ToolResult("t1", "a frame", image_png=b"PNGBYTES")])
    assert resp.texts == ["I see a floor."]

    block = client.messages.calls[0]["messages"][-1]["content"][0]
    assert block["type"] == "tool_result"
    assert block["tool_use_id"] == "t1"
    text_block, image_block = block["content"]
    assert text_block == {"type": "text", "text": "a frame"}
    assert image_block["type"] == "image"
    assert image_block["source"]["media_type"] == "image/png"
    assert base64.b64decode(image_block["source"]["data"]) == b"PNGBYTES"


def test_look_around_sweeps_and_returns_a_view() -> None:
    robot = FakeRobot(camera_frame=_FRAME)
    tool = build_registry(robot).get("look_around")
    assert tool is not None
    result = tool.run({})
    assert result.ok
    assert result.image_png == _FRAME
    assert any(c.method == "set_head" for c in robot.calls)  # it actually looked around


def test_look_around_is_honest_without_a_camera() -> None:
    tool = build_registry(FakeRobot()).get("look_around")
    assert tool is not None
    result = tool.run({})
    assert not result.ok
    assert result.image_png is None


def test_explore_roams_and_always_stops() -> None:
    robot = FakeRobot(camera_frame=_FRAME)
    tool = build_registry(robot).get("explore")
    assert tool is not None
    result = tool.run({})
    assert result.ok
    assert result.image_png == _FRAME
    methods = [c.method for c in robot.calls]
    assert "drive" in methods and "stop" in methods
    assert methods[-1] == "stop"  # it never leaves the duck driving


def test_explore_is_a_gated_action() -> None:
    # explore moves the body, so it is an ACTION (gated), unlike the read-only look_around.
    tool = build_registry(FakeRobot()).get("explore")
    assert tool is not None
    assert tool.risk is Risk.ACTION


def test_turn_rotates_in_place_and_always_stops() -> None:
    robot = FakeRobot(camera_frame=_FRAME)
    tool = build_registry(robot).get("turn")
    assert tool is not None
    result = tool.run({"degrees": 60})
    assert result.ok
    assert result.image_png == _FRAME
    methods = [c.method for c in robot.calls]
    assert "drive" in methods and "stop" in methods
    last_drive = max(i for i, c in enumerate(robot.calls) if c.method == "drive")
    last_stop = max(i for i, c in enumerate(robot.calls) if c.method == "stop")
    assert last_stop > last_drive  # stopped after driving — never left the duck turning
    drives = [c for c in robot.calls if c.method == "drive"]
    # a turn in place: yaw is set, with no forward or sideways velocity
    assert any(
        c.kwargs["vyaw"] != 0.0 and c.kwargs["vx"] == 0.0 and c.kwargs["vy"] == 0.0 for c in drives
    )


def test_turn_direction_follows_the_sign() -> None:
    left, right = FakeRobot(camera_frame=_FRAME), FakeRobot(camera_frame=_FRAME)
    lt = build_registry(left).get("turn")
    rt = build_registry(right).get("turn")
    assert lt is not None and rt is not None
    lt.run({"degrees": 45})
    rt.run({"degrees": -45})
    left_yaw = cast(float, next(c.kwargs["vyaw"] for c in left.calls if c.method == "drive"))
    right_yaw = cast(float, next(c.kwargs["vyaw"] for c in right.calls if c.method == "drive"))
    assert left_yaw > 0 and right_yaw < 0  # positive degrees = left (CCW)


def test_turn_rejects_non_numeric_degrees() -> None:
    tool = build_registry(FakeRobot()).get("turn")
    assert tool is not None
    result = tool.run({"degrees": "a lot"})
    assert not result.ok


def test_turn_is_a_gated_action() -> None:
    tool = build_registry(FakeRobot()).get("turn")
    assert tool is not None
    assert tool.risk is Risk.ACTION


def test_turn_zero_degrees_does_not_move() -> None:
    robot = FakeRobot(camera_frame=_FRAME)
    tool = build_registry(robot).get("turn")
    assert tool is not None
    result = tool.run({"degrees": 0})
    assert result.ok
    assert not any(c.method == "drive" for c in robot.calls)  # a 0 degree turn does not rotate
