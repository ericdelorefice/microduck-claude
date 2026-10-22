"""The brain: a provider-neutral conversation loop with pluggable LLM backends."""

from __future__ import annotations

from .anthropic_llm import AnthropicLLM
from .client import MissingAPIKeyError, build_client
from .factory import build_llm
from .llm import LLM, LLMResponse, ToolCall, ToolResult
from .loop import Brain, Turn
from .openai_llm import OpenAICompatError, OpenAICompatLLM
from .prompts import SYSTEM_PROMPT

__all__ = [
    "SYSTEM_PROMPT",
    "LLM",
    "AnthropicLLM",
    "Brain",
    "LLMResponse",
    "MissingAPIKeyError",
    "OpenAICompatError",
    "OpenAICompatLLM",
    "ToolCall",
    "ToolResult",
    "Turn",
    "build_client",
    "build_llm",
]
