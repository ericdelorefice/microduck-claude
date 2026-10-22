"""The built-in, default LLM adapter: Anthropic's Claude via the official SDK.

This is the reference implementation of :class:`~.llm.LLM`. It keeps the Anthropic
conversation (including thinking blocks, via ``response.content``) so multi-turn
tool use replays correctly.
"""

from __future__ import annotations

from typing import Any

from .llm import LLMResponse, ToolCall, ToolResult

DEFAULT_MODEL = "claude-opus-5-5"


class AnthropicLLM:
    def __init__(self, client: Any, *, model: str = DEFAULT_MODEL, max_tokens: int = 4096) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens
        self._system = ""
        self._tools: list[dict[str, Any]] = []
        self._messages: list[dict[str, Any]] = []

    def start(self, system: str, tools: list[dict[str, Any]]) -> None:
        self._system = system
        self._tools = list(tools)
        self._messages = []

    def send_user(self, text: str) -> LLMResponse:
        self._messages.append({"role": "user", "content": text})
        return self._complete()

    def send_tool_results(self, results: list[ToolResult]) -> LLMResponse:
        content = [
            {
                "type": "tool_result",
                "tool_use_id": r.tool_call_id,
                "content": r.content,
                "is_error": r.is_error,
            }
            for r in results
        ]
        self._messages.append({"role": "user", "content": content})
        return self._complete()

    def _complete(self) -> LLMResponse:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=self._system,
            tools=self._tools,
            thinking={"type": "adaptive"},
            messages=self._messages,
        )
        # Preserve the assistant content verbatim (keeps thinking + tool_use blocks
        # intact for the next request).
        self._messages.append({"role": "assistant", "content": response.content})

        if getattr(response, "stop_reason", None) == "refusal":
            return LLMResponse(refused=True)

        texts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in response.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                texts.append(block.text)
            elif block_type == "tool_use":
                tool_calls.append(
                    ToolCall(id=block.id, name=block.name, input=dict(block.input or {}))
                )
        return LLMResponse(texts=texts, tool_calls=tool_calls)
