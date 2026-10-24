from __future__ import annotations

from microduck_claude.assembly import build_registry
from microduck_claude.brain import AnthropicLLM, Brain, ToolResult
from microduck_claude.robot import FakeRobot
from microduck_claude.safety import CallbackConfirmer, Dispatcher
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


def test_tool_cap_does_not_leave_an_unanswered_tool_use() -> None:
    # A turn that hits max_tool_iterations ends with a tool_use the brain never answered. The
    # API requires every tool_use to be answered by the next message, so without a close-out
    # every later turn in the conversation would be rejected.
    client = FakeAnthropic(
        [tool_response(f"t{i}", "get_time", {}) for i in range(3)] + [text_response("hi")]
    )
    robot = FakeRobot()
    registry = build_registry(robot)
    dispatcher = Dispatcher(registry, CallbackConfirmer(lambda _p: True))
    brain = Brain(AnthropicLLM(client), registry, dispatcher, system="S", max_tool_iterations=2)
    brain.send("keep checking the time")
    assert brain.send("hello again").texts == ["hi"]
    last = client.messages.calls[-1]["messages"][-1]
    assert last["role"] == "user"
    assert last["content"][0]["type"] == "tool_result"
    assert last["content"][0]["tool_use_id"] == "t2"
    assert last["content"][0]["is_error"] is True
    assert last["content"][-1] == {"type": "text", "text": "hello again"}
