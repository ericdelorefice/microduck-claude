"""Select and build an LLM backend from configuration (Claude by default)."""

from __future__ import annotations

import os

from ..config import Config
from .anthropic_llm import AnthropicLLM
from .client import build_client
from .llm import LLM
from .openai_llm import OpenAICompatLLM


def build_llm(config: Config) -> LLM:
    """Build the configured LLM. ``anthropic`` (default) uses the Claude SDK and
    requires ``ANTHROPIC_API_KEY``; ``openai`` targets an OpenAI-compatible server."""
    if config.llm_provider == "anthropic":
        return AnthropicLLM(build_client(), model=config.model, max_tokens=config.max_tokens)
    if config.llm_provider == "openai":
        key_env = os.environ.get("MICRODUCK_OPENAI_KEY_ENV", "OPENAI_API_KEY")
        return OpenAICompatLLM(
            model=config.model,
            base_url=os.environ.get("MICRODUCK_OPENAI_BASE_URL", "http://localhost:11434/v1"),
            api_key=os.environ.get(key_env),
            max_tokens=config.max_tokens,
        )
    raise ValueError(
        f"unknown MICRODUCK_LLM_PROVIDER {config.llm_provider!r}; use 'anthropic' or 'openai'"
    )
