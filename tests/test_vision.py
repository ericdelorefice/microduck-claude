from __future__ import annotations

import base64

import pytest

from microduck_claude.assembly import build_registry
from microduck_claude.brain import AnthropicLLM, ToolResult
from microduck_claude.robot import FakeRobot
from microduck_claude.tools import core as tools_core
from tests.fakes import FakeAnthropic, text_response


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
