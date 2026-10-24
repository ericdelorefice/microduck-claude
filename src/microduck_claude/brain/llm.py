"""A provider-neutral LLM interface, so the brain can run on different models.

The brain speaks this small interface; a provider *adapter* owns its own
conversation state and translates to/from its wire format. The built-in default
and reference is :class:`~.anthropic_llm.AnthropicLLM` (Claude via the official
SDK); :class:`~.openai_llm.OpenAICompatLLM` targets OpenAI-compatible servers
(OpenAI, or local models via Ollama / llama.cpp). The open core depends on no
provider beyond the Anthropic SDK; others are added by implementing :class:`LLM`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

# Adapters answer a tool call left open when a turn ended early (the brain's per-turn tool
# cap) with this, so the next request is still a valid conversation.
NOT_RUN = "Not run: that turn ended before this tool call was answered."


@dataclass
class ToolCall:
    """A tool invocation the model requested."""

    id: str
    name: str
    input: dict[str, Any]


@dataclass
class ToolResult:
    """The outcome of a tool, to feed back to the model."""

    tool_call_id: str
    content: str
    is_error: bool = False
    image_png: bytes | None = None


@dataclass
class LLMResponse:
    """One model turn, normalized across providers."""

    texts: list[str] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    refused: bool = False


class LLM(Protocol):
    """A conversational model with tool use. Adapters keep their own history."""

    def start(self, system: str, tools: list[dict[str, Any]]) -> None:
        """Begin a conversation with a system prompt and tool specs (each a
        ``{name, description, input_schema}`` dict)."""
        ...

    def send_user(self, text: str) -> LLMResponse: ...

    def send_tool_results(self, results: list[ToolResult]) -> LLMResponse: ...
