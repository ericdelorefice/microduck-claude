"""The built-in, default LLM adapter: Anthropic's Claude via the official SDK.

This is the reference implementation of :class:`~.llm.LLM`. It keeps the Anthropic
conversation (including thinking blocks, via ``response.content``) so multi-turn
tool use replays correctly.
"""

from __future__ import annotations

import base64
from typing import Any

from .llm import LLMResponse, ToolCall, ToolResult

DEFAULT_MODEL = "claude-opus-5-5"

# Keep only the most recent few camera frames in history. Older frames are stale once the duck
# has moved, and resending every frame every turn bloats cost/latency and eventually trips the
# API's per-request image limit (which would abort a long explore); older image blocks become a
# short text placeholder instead.
_MAX_IMAGES = 3
_FRAME_OMITTED = "[an earlier camera frame was omitted to keep the request small]"


def _image_media_type(data: bytes) -> str:
    """Sniff an image's media type from its magic bytes (default PNG).

    The camera capture returns whatever the endpoint serves; the Anthropic API rejects a
    block whose declared media_type doesn't match the bytes, so we detect rather than
    assume PNG (hardware cameras often serve JPEG).
    """
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"GIF8"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


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
        # Close out any tool_use the model emitted that the brain never answered (e.g. a turn
        # that hit the tool-call limit). The API requires every tool_use to be followed by a
        # tool_result, so inject synthetic ones and carry the new text in the SAME user message.
        pending = self._pending_tool_use_ids()
        if pending:
            content: list[dict[str, Any]] = [self._cancel_block(tid) for tid in pending]
            if text:
                content.append({"type": "text", "text": text})
            return self._exchange({"role": "user", "content": content})
        return self._exchange({"role": "user", "content": text})

    def send_tool_results(self, results: list[ToolResult]) -> LLMResponse:
        content = [self._tool_result_block(r) for r in results]
        return self._exchange({"role": "user", "content": content})

    def _exchange(self, user_message: dict[str, Any]) -> LLMResponse:
        self._messages.append(user_message)
        self._prune_images()
        try:
            return self._complete()
        except Exception:
            self._messages.pop()  # a turn the API rejected must not poison later requests
            raise

    def _pending_tool_use_ids(self) -> list[str]:
        """IDs of tool_use blocks in a trailing assistant turn that were never answered."""
        if not self._messages:
            return []
        last = self._messages[-1]
        if last.get("role") != "assistant":
            return []
        content = last.get("content")
        if not isinstance(content, list):
            return []
        ids: list[str] = []
        for block in content:
            if getattr(block, "type", None) == "tool_use":
                tid = getattr(block, "id", None)
                if isinstance(tid, str):
                    ids.append(tid)
        return ids

    @staticmethod
    def _cancel_block(tool_use_id: str) -> dict[str, Any]:
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": "Stopped: the tool-call limit for this turn was reached.",
            "is_error": True,
        }

    def _prune_images(self) -> None:
        """Replace all but the most recent ``_MAX_IMAGES`` camera frames with a short note."""
        parts: list[tuple[list[Any], int]] = []
        for message in self._messages:
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                inner = block.get("content")
                if not isinstance(inner, list):
                    continue
                for i, part in enumerate(inner):
                    if isinstance(part, dict) and part.get("type") == "image":
                        parts.append((inner, i))
        for inner, i in parts[:-_MAX_IMAGES]:
            inner[i] = {"type": "text", "text": _FRAME_OMITTED}

    @staticmethod
    def _tool_result_block(result: ToolResult) -> dict[str, Any]:
        block: dict[str, Any] = {
            "type": "tool_result",
            "tool_use_id": result.tool_call_id,
            "content": result.content,
            "is_error": result.is_error,
        }
        if result.image_png is not None:
            # A vision tool (e.g. the camera) hands back an image block alongside the text.
            encoded = base64.b64encode(result.image_png).decode("ascii")
            parts: list[dict[str, Any]] = []
            if result.content:  # the API rejects an empty text block
                parts.append({"type": "text", "text": result.content})
            parts.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": _image_media_type(result.image_png),
                        "data": encoded,
                    },
                }
            )
            block["content"] = parts
        return block

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
