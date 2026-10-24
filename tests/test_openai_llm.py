from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from microduck_claude.brain import OpenAICompatLLM, ToolResult


class _FakeOpenAI:
    """A fake OpenAI-compatible /chat/completions server over a real socket."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self.requests: list[dict[str, Any]] = []
        self.auth: list[str | None] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                pass

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0") or 0)
                outer.requests.append(json.loads(self.rfile.read(length) or b"{}"))
                outer.auth.append(self.headers.get("Authorization"))
                body = outer._responses.pop(0) if outer._responses else _text("?")
                data = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    def __enter__(self) -> _FakeOpenAI:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(2.0)


def _text(content: str) -> dict[str, Any]:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def _tool(call_id: str, name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args)},
                        }
                    ],
                }
            }
        ]
    }


def test_text_request_shape_and_auth() -> None:
    with _FakeOpenAI([_text("hi there")]) as fake:
        llm = OpenAICompatLLM(model="llama3.2", base_url=fake.base_url, api_key="secret")
        llm.start("SYS", [{"name": "t", "description": "d", "input_schema": {"type": "object"}}])
        resp = llm.send_user("hello")
        assert resp.texts == ["hi there"]
        body = fake.requests[0]
        assert body["model"] == "llama3.2"
        assert body["messages"][0] == {"role": "system", "content": "SYS"}
        assert body["tools"][0]["function"]["name"] == "t"
        assert fake.auth[0] == "Bearer secret"


def test_tool_call_roundtrip() -> None:
    with _FakeOpenAI([_tool("c1", "do", {"x": 1}), _text("done")]) as fake:
        llm = OpenAICompatLLM(model="m", base_url=fake.base_url)
        llm.start("S", [])
        first = llm.send_user("go")
        assert first.tool_calls[0].name == "do"
        assert first.tool_calls[0].input == {"x": 1}
        second = llm.send_tool_results([ToolResult("c1", "result")])
        assert second.texts == ["done"]
        tool_msg = fake.requests[1]["messages"][-1]
        assert tool_msg["role"] == "tool"
        assert tool_msg["tool_call_id"] == "c1"


def test_tool_result_with_image_tells_the_model_it_cannot_see() -> None:
    # This adapter drops images; the tool result must say so, or the model invents a view.
    with _FakeOpenAI([_text("acknowledged")]) as fake:
        llm = OpenAICompatLLM(model="m", base_url=fake.base_url)
        llm.start("S", [])
        llm.send_tool_results(
            [ToolResult("c1", "Here is what the camera sees.", image_png=b"PNGBYTES")]
        )
        tool_msg = fake.requests[0]["messages"][-1]
        assert tool_msg["role"] == "tool"
        assert "cannot see images" in tool_msg["content"]


def test_dangling_tool_calls_are_closed_before_the_next_user_turn() -> None:
    with _FakeOpenAI([_tool("c1", "do", {}), _text("ok")]) as fake:
        llm = OpenAICompatLLM(model="m", base_url=fake.base_url)
        llm.start("S", [])
        llm.send_user("go")  # returns an assistant tool_call c1, left unanswered (as if capped)
        llm.send_user("again")  # must answer c1 before sending the next user message
        messages = fake.requests[1]["messages"]
        assert any(
            m.get("role") == "tool" and m.get("tool_call_id") == "c1" for m in messages
        )  # c1 was closed
        assert messages[-1] == {"role": "user", "content": "again"}
