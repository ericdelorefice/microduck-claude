from __future__ import annotations

from microduck_claude.brain import AnthropicLLM, ToolResult
from tests.fakes import FakeAnthropic, refusal_response, text_response, tool_response


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
