from __future__ import annotations

import base64
import math
from typing import cast

import pytest

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


def test_turn_walks_a_tight_arc_and_always_stops() -> None:
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
    # The gait won't pivot on the spot, so a turn is a tight arc: yaw plus a slow step forward,
    # never sideways and never a full walking pace.
    assert any(
        c.kwargs["vyaw"] != 0.0
        and 0.0 < cast(float, c.kwargs["vx"]) <= 0.3
        and c.kwargs["vy"] == 0.0
        for c in drives
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


def test_turn_command_uses_full_yaw_and_scales_duration() -> None:
    from microduck_claude.robot.motion import TURN_LEFT_DEG_PER_S, TURN_MIN_S, TURN_VX
    from microduck_claude.robot.motion import turn_command as _turn_command

    # Full |vyaw| with a slow step forward; the angle is carried by the duration, and a fine
    # request clamps to a short floor.
    big_vx, big_vyaw, big_dur = _turn_command(90.0)
    fine_vx, fine_vyaw, fine_dur = _turn_command(10.0)
    assert big_vx == fine_vx == TURN_VX
    assert abs(big_vyaw) == 1.0 and abs(fine_vyaw) == 1.0
    assert big_dur == 90.0 / TURN_LEFT_DEG_PER_S  # duration carries the angle
    assert fine_dur == TURN_MIN_S and big_dur > fine_dur  # fine clamps to the floor
    assert _turn_command(30.0)[1] > 0 and _turn_command(-30.0)[1] < 0  # sign gives direction


def test_turn_command_gives_left_turns_longer() -> None:
    from microduck_claude.robot.motion import turn_command as _turn_command

    # The gait swings right more readily than left (measured), so the same angle needs longer
    # held to the left.
    assert _turn_command(90.0)[2] > _turn_command(-90.0)[2]


def test_turn_uses_full_yaw_for_both_fine_and_big() -> None:
    # The sim walk gait only pivots at full |vyaw|, so a fine turn uses the same yaw as a big one
    # (the old scaled-down yaw produced no rotation at all on the real gait).
    fine, big = FakeRobot(camera_frame=_FRAME), FakeRobot(camera_frame=_FRAME)
    fine_tool = build_registry(fine).get("turn")
    big_tool = build_registry(big).get("turn")
    assert fine_tool is not None and big_tool is not None
    fine_tool.run({"degrees": 10})
    big_tool.run({"degrees": 90})
    fine_yaw = abs(cast(float, next(c.kwargs["vyaw"] for c in fine.calls if c.method == "drive")))
    big_yaw = abs(cast(float, next(c.kwargs["vyaw"] for c in big.calls if c.method == "drive")))
    assert fine_yaw == 1.0 and big_yaw == 1.0


def test_turn_reports_the_angle_the_duck_actually_turned(monkeypatch: pytest.MonkeyPatch) -> None:
    # A body with a heading: the tool reports the measured turn, and flags a big miss, so the
    # model corrects from what happened. This one jams at 45° (pressed against something).
    class Jammed(FakeRobot):
        def __init__(self) -> None:
            super().__init__(camera_frame=_FRAME)
            self.heading_rad = 0.0

        def drive(self, vx: float, vy: float, vyaw: float) -> None:
            super().drive(vx, vy, vyaw)
            turned = (self.heading_rad or 0.0) + vyaw * 0.2
            self.heading_rad = max(-math.pi / 4, min(math.pi / 4, turned))

    from microduck_claude.robot import motion

    clock = [0.0]  # fake time, so the stall and settle waits cost nothing
    monkeypatch.setattr(motion, "_now", lambda: clock[0])
    monkeypatch.setattr(motion, "_sleep", lambda dt: clock.__setitem__(0, clock[0] + dt))
    tool = build_registry(Jammed()).get("turn")
    assert tool is not None
    result = tool.run({"degrees": 90})
    assert result.ok and "I turned 45° to the left (you asked for 90°)" in result.content


def test_explore_stops_at_viewing_distance_and_says_so() -> None:
    robot = FakeRobot(camera_frame=_FRAME)
    robot.range_m = 0.6  # already closer than viewing distance: it shouldn't walk at all
    tool = build_registry(robot).get("explore")
    assert tool is not None
    result = tool.run({})
    assert (
        result.ok
        and "I didn't walk: something is already about 0.6 m in front of me" in result.content
    )
    assert not any(c.method == "drive" for c in robot.calls)


def test_camera_results_say_how_wide_the_view_is() -> None:
    # The model can't judge a turn from a picture without knowing its width: the duck's camera
    # is narrow, so a painting at the edge of the frame is only ~19° away, not 45°.
    for name, args in (("see", {}), ("look_around", {}), ("turn", {"degrees": 30})):
        tool = build_registry(FakeRobot(camera_frame=_FRAME)).get(name)
        assert tool is not None
        content = tool.run(args).content
        assert "about 37° from edge to edge" in content, (name, content)
        assert "edge is about 19°" in content and "halfway to the edge about 9°" in content


def test_the_view_width_is_configurable_for_other_cameras() -> None:
    tool = build_registry(FakeRobot(camera_frame=_FRAME), camera_hfov_deg=60.0).get("see")
    assert tool is not None
    assert "about 60° from edge to edge" in tool.run({}).content


def test_no_view_note_without_a_picture() -> None:
    tool = build_registry(FakeRobot()).get("see")  # no camera
    assert tool is not None
    assert "edge to edge" not in tool.run({}).content


def test_turn_tool_explains_angles_in_the_picture() -> None:
    tool = build_registry(FakeRobot()).get("turn")
    assert tool is not None
    spec = next(s for s in build_registry(FakeRobot()).specs() if s["name"] == "turn")
    assert "about 19°" in spec["input_schema"]["properties"]["degrees"]["description"]


def test_explore_looks_up_at_what_it_stopped_in_front_of() -> None:
    # Walking, the head looks ahead (so the distance sensor sees what's in the way). Stopped in
    # front of a painting, a level gaze only shows its bottom edge, so the duck looks up.
    robot = FakeRobot(camera_frame=_FRAME)
    robot.range_m = 0.6
    tool = build_registry(robot).get("explore")
    assert tool is not None
    tool.run({})
    heads = [c.kwargs["head_pitch"] for c in robot.calls if c.method == "set_head"]
    assert heads and cast(float, heads[-1]) <= -0.7  # looking up when the picture is taken
