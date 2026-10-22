"""The Claude brain: the conversation loop and client factory."""

from __future__ import annotations

from .client import MissingAPIKeyError, build_client
from .loop import Brain, BrainConfig, Turn
from .prompts import SYSTEM_PROMPT

__all__ = [
    "SYSTEM_PROMPT",
    "Brain",
    "BrainConfig",
    "MissingAPIKeyError",
    "Turn",
    "build_client",
]
