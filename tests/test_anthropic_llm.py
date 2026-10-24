from __future__ import annotations

from typing import Any

import pytest

from microduck_claude.brain import AnthropicLLM, ToolResult
from microduck_claude.brain.anthropic_llm import _FRAME_OMITTED, _MAX_IMAGES
from tests.fakes import FakeAnthropic, refusal_response, text_response, tool_response


def _count_image_parts(messages: list[dict[str, Any]]) -> tuple[int, int]:
    """Return (image blocks, 'omitted frame' placeholders) across tool_result contents."""
    images = placeholders = 0
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            inner = block.get("content")
            if not isinstance(inner, list):
                continue
            for part in inner:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "image":
                    images += 1
                elif part.get("type") == "text" and part.get("text") == _FRAME_OMITTED:
                    placeholders += 1
    return images, placeholders


def test_text_response_and_params_forwarded() -> None:
    client = FakeAnthropic([text_response("hi")])
    llm = AnthropicLLM(client, model="m", max_tokens=99)
    llm.start("SYS", [{"name": "t", "description": "d", "input_schema": {}}])
    resp = llm.send_user("hello")
    assert resp.texts == ["hi"]
    assert not resp.tool_calls and not resp.refused
    call = client.messages.calls[0]
    assert call["system"] == "SYS"
    assert call["model"] == "m"
    assert call["max_tokens"] == 99
    assert call["tools"][0]["name"] == "t"


def test_tool_use_then_results_roundtrip() -> None:
    client = FakeAnthropic([tool_response("t1", "do", {"x": 1}), text_response("done")])
    llm = AnthropicLLM(client, model="m", max_tokens=50)
    llm.start("SYS", [])
    first = llm.send_user("go")
    assert first.tool_calls[0].name == "do"
    assert first.tool_calls[0].input == {"x": 1}
    second = llm.send_tool_results([ToolResult("t1", "result", is_error=False)])
    assert second.texts == ["done"]
    sent = client.messages.calls[1]["messages"][-1]["content"][0]
    assert sent["type"] == "tool_result"
    assert sent["tool_use_id"] == "t1"


def test_refusal() -> None:
    llm = AnthropicLLM(FakeAnthropic([refusal_response()]), model="m", max_tokens=9)
    llm.start("S", [])
    assert llm.send_user("x").refused is True


def test_failed_request_does_not_poison_history() -> None:
    class _BoomThenOK:
        def __init__(self) -> None:
            self.calls = 0
            self.last_messages: list[dict[str, Any]] | None = None

        def create(self, **kwargs: Any) -> Any:
            self.calls += 1
            self.last_messages = list(kwargs["messages"])
            if self.calls == 1:
                raise RuntimeError("API 400: bad image block")
            return text_response("recovered")

    client: Any = type("Client", (), {})()
    client.messages = _BoomThenOK()
    llm = AnthropicLLM(client, model="m", max_tokens=10)
    llm.start("S", [])

    with pytest.raises(RuntimeError):
        llm.send_user("first")  # the API rejects this turn
    resp = llm.send_user("second")  # the next turn must still work
    assert resp.texts == ["recovered"]
    # the rejected "first" turn was rolled back, so only "second" reaches the model
    assert client.messages.last_messages == [{"role": "user", "content": "second"}]


def test_old_camera_frames_are_pruned() -> None:
    client = FakeAnthropic([text_response("ok")] * 5)
    llm = AnthropicLLM(client, model="m", max_tokens=10)
    llm.start("S", [])
    for i in range(5):
        llm.send_tool_results([ToolResult(f"t{i}", "frame", image_png=b"\x89PNG" + bytes([i]))])
    images, placeholders = _count_image_parts(client.messages.calls[-1]["messages"])
    assert images == _MAX_IMAGES  # only the most recent frames stay as images
    assert placeholders == 5 - _MAX_IMAGES  # the rest became short placeholders


def test_unanswered_tool_use_is_closed_on_next_user_turn() -> None:
    client = FakeAnthropic([tool_response("t1", "do", {}), text_response("after")])
    llm = AnthropicLLM(client, model="m", max_tokens=10)
    llm.start("S", [])
    llm.send_user("go")  # the model asks for tool t1, which is never answered (as if capped)
    resp = llm.send_user("next")  # the adapter must close t1 and carry the new text
    assert resp.texts == ["after"]
    sent = client.messages.calls[1]["messages"][-1]
    assert sent["role"] == "user"
    tool_result, text_block = sent["content"]
    assert tool_result["type"] == "tool_result"
    assert tool_result["tool_use_id"] == "t1"
    assert tool_result["is_error"] is True
    assert text_block == {"type": "text", "text": "next"}
