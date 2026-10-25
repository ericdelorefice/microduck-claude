"""The brain: a provider-neutral conversation loop with pluggable LLM backends."""

from __future__ import annotations

from .anthropic_llm import AnthropicLLM
from .client import MissingCredentialsError, build_client
from .factory import build_llm
from .llm import LLM, LLMResponse, ToolCall, ToolResult
from .loop import Brain, Turn
from .openai_llm import OpenAICompatError, OpenAICompatLLM
from .persona import DEFAULT_PERSONA, PERSONAS, Persona, persona_names, system_prompt_for
from .prompts import SYSTEM_PROMPT

__all__ = [
    "DEFAULT_PERSONA",
    "PERSONAS",
    "SYSTEM_PROMPT",
    "LLM",
    "AnthropicLLM",
    "Brain",
    "LLMResponse",
    "MissingCredentialsError",
    "OpenAICompatError",
    "OpenAICompatLLM",
    "Persona",
    "ToolCall",
    "ToolResult",
    "Turn",
    "build_client",
    "build_llm",
    "persona_names",
    "system_prompt_for",
]
