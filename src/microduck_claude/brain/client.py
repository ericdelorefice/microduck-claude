"""Factory for the official Anthropic client.

The key is read only from the environment by the SDK itself — we check that it is
*present* (never its value) to fail fast with a friendly message, and we never
store or log it.
"""

from __future__ import annotations

import os
from typing import Any


class MissingAPIKeyError(RuntimeError):
    """Raised when ANTHROPIC_API_KEY is not set in the environment."""


def build_client() -> Any:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise MissingAPIKeyError(
            "ANTHROPIC_API_KEY is not set. Export it in your shell; this app reads it "
            "only from the environment and never stores, logs, or asks for it."
        )
    import anthropic  # lazy import keeps the core import-light and test-friendly

    # The SDK picks up ANTHROPIC_API_KEY from the environment on its own.
    return anthropic.Anthropic()
