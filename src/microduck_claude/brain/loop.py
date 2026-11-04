"""The conversation orchestrator: a provider-neutral tool-use loop.

The brain manages the tool-use loop and the safety gate; the actual model call and
all provider specifics live behind the :class:`LLM` interface, which is injected.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ..safety.dispatcher import Dispatcher
from ..tools.base import ToolRegistry
from .llm import LLM, ToolCall, ToolResult


@dataclass
class Turn:
    """What came back from one user input: the duck's words, and whether it refused."""

    texts: list[str] = field(default_factory=list)
    refused: bool = False
    capped: bool = False  # the model asked for more actions than one turn allows


# What the model hears for a call it asked for past the limit. Said in the same turn, so it
# knows the move didn't happen before it speaks — not a turn later.
_LIMIT_NOTE = (
    "Not run: that is more actions than one turn allows, so this did not happen and nothing "
    "moved. Reply in words now; you can do it on your next turn."
)


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

    def send(self, user_text: str, *, on_text: Callable[[str], None] | None = None) -> Turn:
        """Send one user turn, running any tool calls, and return the reply.

        ``on_text`` hears each line as the model says it — before the tool calls that came with it
        run — so a narrator speaks "let me look" before looking, not after the whole turn.
        """
        if not self._started:
            self._llm.start(self._system, self._registry.specs())
            self._started = True

        turn = Turn()
        response = self._llm.send_user(user_text)
        iterations = 0
        while True:
            turn.texts.extend(response.texts)
            if on_text is not None:
                for text in response.texts:
                    on_text(text)
            if response.refused:
                turn.refused = True
                break
            if not response.tool_calls:
                break
            iterations += 1
            if iterations > self._max_tool_iterations:
                # Past the limit: run nothing, but answer these calls honestly and let the
                # model say so in words, instead of leaving them dangling to fail next turn.
                # Whatever it replies, nothing more runs this turn.
                turn.capped = True
                skipped = [
                    ToolResult(tool_call_id=call.id, content=_LIMIT_NOTE, is_error=True)
                    for call in response.tool_calls
                ]
                response = self._llm.send_tool_results(skipped)
                turn.texts.extend(response.texts)
                if on_text is not None:
                    for text in response.texts:
                        on_text(text)
                turn.refused = turn.refused or response.refused
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
            image_png=outcome.image_for_model,
        )
