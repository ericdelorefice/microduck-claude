"""An OpenAI-compatible chat adapter, using only the standard library.

Targets any server speaking OpenAI's ``/chat/completions`` with tool calling —
OpenAI itself, or local models via Ollama (``http://localhost:11434/v1``) or
llama.cpp. Uses ``urllib`` only, so it adds no dependency. Verified against a fake
server in the tests; validate against a real endpoint before relying on it.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .llm import LLMResponse, ToolCall, ToolResult


class OpenAICompatError(RuntimeError):
    """A transport or protocol error talking to an OpenAI-compatible server."""


class OpenAICompatLLM:
    def __init__(
        self,
        *,
        model: str,
        base_url: str = "http://localhost:11434/v1",
        api_key: str | None = None,
        max_tokens: int = 4096,
        timeout: float = 120.0,
    ) -> None:
        self._model = model
        self._base = base_url.rstrip("/")
        self._api_key = api_key
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._tools: list[dict[str, Any]] = []
        self._messages: list[dict[str, Any]] = []

    def start(self, system: str, tools: list[dict[str, Any]]) -> None:
        self._tools = [_tool_spec(t) for t in tools]
        self._messages = [{"role": "system", "content": system}] if system else []

    def send_user(self, text: str) -> LLMResponse:
        self._close_dangling_tool_calls()
        self._messages.append({"role": "user", "content": text})
        return self._complete()

    def send_tool_results(self, results: list[ToolResult]) -> LLMResponse:
        for result in results:
            content = result.content
            if result.image_png is not None:
                # This adapter cannot deliver images, so say so plainly — otherwise the vision
                # tool's own text ("here's what the camera sees") would make the model invent
                # a scene it never saw.
                note = "(A camera image was captured, but this model cannot see images.)"
                content = f"{content}\n\n{note}" if content else note
            self._messages.append(
                {"role": "tool", "tool_call_id": result.tool_call_id, "content": content}
            )
        return self._complete()

    def _close_dangling_tool_calls(self) -> None:
        """Answer any tool_calls left unanswered by a capped/aborted turn.

        OpenAI requires an assistant message carrying tool_calls to be followed by one tool
        message per call, so an unanswered turn would make the next user message invalid.
        """
        if not self._messages or self._messages[-1].get("role") != "assistant":
            return
        for call in self._messages[-1].get("tool_calls") or []:
            self._messages.append(
                {
                    "role": "tool",
                    "tool_call_id": str(call.get("id", "")),
                    "content": "Stopped: the tool-call limit for this turn was reached.",
                }
            )

    def _complete(self) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": self._messages,
            "max_tokens": self._max_tokens,
        }
        if self._tools:
            payload["tools"] = self._tools
            payload["tool_choice"] = "auto"

        data = self._post("/chat/completions", payload)
        choices = data.get("choices") or [{}]
        message = choices[0].get("message") or {}
        self._messages.append(_assistant_message(message))

        texts: list[str] = []
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            texts.append(content)
        tool_calls: list[ToolCall] = []
        for call in message.get("tool_calls") or []:
            fn = call.get("function") or {}
            tool_calls.append(
                ToolCall(
                    id=str(call.get("id", "")),
                    name=str(fn.get("name", "")),
                    input=_parse_args(fn.get("arguments")),
                )
            )
        return LLMResponse(texts=texts, tool_calls=tool_calls)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        request = urllib.request.Request(
            self._base + path,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                raw = response.read()
        except urllib.error.URLError as exc:
            raise OpenAICompatError(f"request to {self._base}{path} failed: {exc}") from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OpenAICompatError("invalid JSON from server") from exc
        if not isinstance(data, dict):
            raise OpenAICompatError("unexpected response shape")
        return data


def _tool_spec(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
        },
    }


def _assistant_message(message: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"role": "assistant", "content": message.get("content") or ""}
    if message.get("tool_calls"):
        out["tool_calls"] = message["tool_calls"]
    return out


def _parse_args(args: Any) -> dict[str, Any]:
    if isinstance(args, dict):
        return args
    if isinstance(args, str):
        try:
            parsed = json.loads(args)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}
