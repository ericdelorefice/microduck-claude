from __future__ import annotations

import base64
import http.client
from typing import Any, cast

import pytest

from microduck_claude.assembly import build_registry
from microduck_claude.brain import AnthropicLLM, ToolResult
from microduck_claude.robot import FakeRobot
from microduck_claude.tools import Risk
from microduck_claude.tools import core as tools_core
from tests.fakes import FakeAnthropic, text_response

_PNG = b"\x89PNG\r\n\x1a\n"  # a valid PNG signature


class _FakeHTTPResponse:
    """A minimal urlopen() context manager returning canned bytes."""

    def __init__(self, data: bytes, status: int = 200, truncate: bool = False) -> None:
        self._data = data
        self.status = status
        self._truncate = truncate

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self, amt: int = -1) -> bytes:
        if self._truncate:
            raise http.client.IncompleteRead(b"partial")
        return self._data[:amt] if amt is not None and amt >= 0 else self._data


def _patch_camera(monkeypatch: pytest.MonkeyPatch, response: _FakeHTTPResponse) -> None:
    def fake_urlopen(url: Any, timeout: float = 0) -> _FakeHTTPResponse:
        return response

    monkeypatch.setattr(tools_core.urllib.request, "urlopen", fake_urlopen)


def test_capture_accepts_a_small_valid_image(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = _PNG + b"tiny-pixels"
    _patch_camera(monkeypatch, _FakeHTTPResponse(frame))
    assert tools_core._capture_camera_png("http://cam/frame") == frame


def test_capture_rejects_a_non_image_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    # A 200 that is actually an HTML error page or an MJPEG stream must not reach the model.
    _patch_camera(monkeypatch, _FakeHTTPResponse(b"<html>500 Internal Server Error</html>"))
    assert tools_core._capture_camera_png("http://cam/frame") is None


def test_capture_rejects_an_oversized_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    big = _PNG + b"x" * (6 * 1024 * 1024)  # over the 5 MB per-image limit
    _patch_camera(monkeypatch, _FakeHTTPResponse(big))
    assert tools_core._capture_camera_png("http://cam/frame") is None


def test_capture_handles_a_truncated_response(monkeypatch: pytest.MonkeyPatch) -> None:
    # http.client.IncompleteRead is not an OSError; it must still be caught, not raised.
    _patch_camera(monkeypatch, _FakeHTTPResponse(b"", truncate=True))
    assert tools_core._capture_camera_png("http://cam/frame") is None


def test_see_tool_returns_a_camera_image(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tools_core, "_capture_camera_png", lambda url, **kw: b"\x89PNG-fake")
    tool = build_registry(FakeRobot(), camera_url="http://cam/frame").get("see")
    assert tool is not None
    result = tool.run({})
    assert result.ok
    assert result.image_png == b"\x89PNG-fake"


def test_see_tool_is_honest_without_a_camera(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tools_core, "_capture_camera_png", lambda url, **kw: None)
    tool = build_registry(FakeRobot(), camera_url="").get("see")
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


def test_look_around_sweeps_and_returns_a_view(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tools_core, "_capture_camera_png", lambda url, **kw: b"\x89PNG-view")
    robot = FakeRobot()
    tool = build_registry(robot, camera_url="http://cam/frame").get("look_around")
    assert tool is not None
    result = tool.run({})
    assert result.ok
    assert result.image_png == b"\x89PNG-view"
    assert any(c.method == "set_head" for c in robot.calls)  # it actually looked around


def test_look_around_is_honest_without_a_camera(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tools_core, "_capture_camera_png", lambda url, **kw: None)
    tool = build_registry(FakeRobot(), camera_url="").get("look_around")
    assert tool is not None
    result = tool.run({})
    assert not result.ok
    assert result.image_png is None


def test_explore_roams_and_always_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tools_core, "_capture_camera_png", lambda url, **kw: b"\x89PNG-roam")
    robot = FakeRobot()
    tool = build_registry(robot, camera_url="http://cam/frame").get("explore")
    assert tool is not None
    result = tool.run({})
    assert result.ok
    assert result.image_png == b"\x89PNG-roam"
    methods = [c.method for c in robot.calls]
    assert "drive" in methods and "stop" in methods
    assert methods[-1] == "stop"  # it never leaves the duck driving


def test_explore_is_a_gated_action() -> None:
    # explore moves the body, so it is an ACTION (gated), unlike the read-only look_around.
    tool = build_registry(FakeRobot(), camera_url="http://cam/frame").get("explore")
    assert tool is not None
    assert tool.risk is Risk.ACTION


def test_turn_rotates_in_place_and_always_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tools_core, "_capture_camera_png", lambda url, **kw: b"\x89PNG-turn")
    robot = FakeRobot()
    tool = build_registry(robot, camera_url="http://cam/frame").get("turn")
    assert tool is not None
    result = tool.run({"degrees": 60})
    assert result.ok
    assert result.image_png == b"\x89PNG-turn"
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
    left, right = FakeRobot(), FakeRobot()
    lt = build_registry(left, camera_url="http://cam/frame").get("turn")
    rt = build_registry(right, camera_url="http://cam/frame").get("turn")
    assert lt is not None and rt is not None
    lt.run({"degrees": 45})
    rt.run({"degrees": -45})
    left_yaw = cast(float, next(c.kwargs["vyaw"] for c in left.calls if c.method == "drive"))
    right_yaw = cast(float, next(c.kwargs["vyaw"] for c in right.calls if c.method == "drive"))
    assert left_yaw > 0 and right_yaw < 0  # positive degrees = left (CCW)


def test_turn_rejects_non_numeric_degrees() -> None:
    tool = build_registry(FakeRobot(), camera_url="http://cam/frame").get("turn")
    assert tool is not None
    result = tool.run({"degrees": "a lot"})
    assert not result.ok


def test_turn_is_a_gated_action() -> None:
    tool = build_registry(FakeRobot(), camera_url="http://cam/frame").get("turn")
    assert tool is not None
    assert tool.risk is Risk.ACTION
