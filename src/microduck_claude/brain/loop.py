"""The conversation orchestrator: a provider-neutral tool-use loop.

The brain manages the tool-use loop and the safety gate; the actual model call and
all provider specifics live behind the :class:`LLM` interface, which is injected.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..safety.dispatcher import Dispatcher
from ..tools.base import ToolRegistry
from .llm import LLM, ToolCall, ToolResult


@dataclass
class Turn:
    """What came back from one user input: the duck's words, and whether it refused."""

    texts: list[str] = field(default_factory=list)
    refused: bool = False


class Brain:
    def __init__(
        self,
        llm: LLM,
        registry: ToolRegistry,
        dispatcher: Dispatcher,
        *,
        system: str,
        max_tool_iterations: int = 6,
    ) -> None:
        self._llm = llm
        self._registry = registry
        self._dispatcher = dispatcher
        self._system = system
        self._max_tool_iterations = max_tool_iterations
        self._started = False

    def send(self, user_text: str) -> Turn:
        """Send one user turn, running any tool calls, and return the reply."""
        if not self._started:
            self._llm.start(self._system, self._registry.specs())
            self._started = True

        turn = Turn()
        response = self._llm.send_user(user_text)
        iterations = 0
        while True:
            turn.texts.extend(response.texts)
            if response.refused:
                turn.refused = True
                break
            if not response.tool_calls:
                break
            iterations += 1
            if iterations > self._max_tool_iterations:
                break
            results = [self._dispatch(call) for call in response.tool_calls]
            response = self._llm.send_tool_results(results)
        return turn

    def _dispatch(self, call: ToolCall) -> ToolResult:
        outcome = self._dispatcher.dispatch(call.name, call.input)
        return ToolResult(
            tool_call_id=call.id,
            content=outcome.content_for_model,
            is_error=outcome.is_error,
        )
