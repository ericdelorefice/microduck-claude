"""The conversation orchestrator: a manual Claude tool-use loop.

A manual loop (rather than an opaque helper) keeps the safety gate explicit and
easy to test: every tool call the model makes is routed through the Dispatcher,
and nothing the model emits can bypass it. The Anthropic client is injected, so
tests run with a fake and no API key.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ..safety.dispatcher import Dispatcher
from ..tools.base import ToolRegistry

log = logging.getLogger("microduck_claude.brain")


@dataclass
class BrainConfig:
    model: str = "claude-opus-5-5"
    max_tokens: int = 4096
    max_tool_iterations: int = 6


@dataclass
class Turn:
    """What came back from one user input: the duck's words, and whether it refused."""

    texts: list[str] = field(default_factory=list)
    refused: bool = False


class Brain:
    def __init__(
        self,
        client: Any,
        registry: ToolRegistry,
        dispatcher: Dispatcher,
        *,
        system: str,
        config: BrainConfig | None = None,
    ) -> None:
        self._client = client
        self._registry = registry
        self._dispatcher = dispatcher
        self._system = system
        self._config = config or BrainConfig()
        self._messages: list[dict[str, Any]] = []

    @property
    def messages(self) -> list[dict[str, Any]]:
        return self._messages

    def send(self, user_text: str) -> Turn:
        """Send one user turn, running any tool calls, and return the reply."""
        self._messages.append({"role": "user", "content": user_text})
        turn = Turn()

        for _ in range(self._config.max_tool_iterations):
            response = self._client.messages.create(
                model=self._config.model,
                max_tokens=self._config.max_tokens,
                system=self._system,
                tools=self._registry.specs(),
                thinking={"type": "adaptive"},
                messages=self._messages,
            )

            # Safety classifiers may decline (HTTP 200, stop_reason "refusal").
            if getattr(response, "stop_reason", None) == "refusal":
                turn.refused = True
                self._messages.append({"role": "assistant", "content": response.content})
                break

            tool_uses: list[Any] = []
            for block in response.content:
                block_type = getattr(block, "type", None)
                if block_type == "text":
                    turn.texts.append(block.text)
                elif block_type == "tool_use":
                    tool_uses.append(block)

            # Append the assistant turn verbatim so thinking + tool_use blocks are
            # preserved for the next request.
            self._messages.append({"role": "assistant", "content": response.content})

            if getattr(response, "stop_reason", None) != "tool_use" or not tool_uses:
                break

            results: list[dict[str, Any]] = []
            for block in tool_uses:
                outcome = self._dispatcher.dispatch(block.name, dict(block.input or {}))
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": outcome.content_for_model,
                        "is_error": outcome.is_error,
                    }
                )
            self._messages.append({"role": "user", "content": results})

        return turn
