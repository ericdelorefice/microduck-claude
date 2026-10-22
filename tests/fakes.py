"""Test doubles: a scripted stand-in for the Anthropic client, and a recording confirmer.

These let the safety layer and the brain loop be tested fully offline — no network,
no ANTHROPIC_API_KEY. The fake blocks mimic the attribute shape (``.type``, ``.text``,
``.name``, ``.input``, ``.id``) the loop reads from real SDK content blocks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeBlock:
    type: str
    text: str | None = None
    id: str | None = None
    name: str | None = None
    input: dict[str, Any] | None = None


@dataclass
class FakeResponse:
    content: list[FakeBlock]
    stop_reason: str


class FakeMessages:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> FakeResponse:
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("messages.create called more times than scripted")
        return self._responses.pop(0)


class FakeAnthropic:
    """A stand-in for ``anthropic.Anthropic`` with a scripted ``messages.create``."""

    def __init__(self, responses: list[FakeResponse]) -> None:
        self.messages = FakeMessages(responses)


def text_response(text: str, stop_reason: str = "end_turn") -> FakeResponse:
    return FakeResponse([FakeBlock(type="text", text=text)], stop_reason)


def tool_response(
    tool_use_id: str,
    name: str,
    tool_input: dict[str, Any],
    text: str | None = None,
) -> FakeResponse:
    blocks: list[FakeBlock] = []
    if text is not None:
        blocks.append(FakeBlock(type="text", text=text))
    blocks.append(FakeBlock(type="tool_use", id=tool_use_id, name=name, input=tool_input))
    return FakeResponse(blocks, "tool_use")


def refusal_response() -> FakeResponse:
    return FakeResponse([], "refusal")


@dataclass
class RecordingConfirmer:
    """A confirmer that records every prompt it is asked and returns a fixed answer."""

    answer: bool = True
    prompts: list[str] = field(default_factory=list)

    def confirm(self, prompt: str) -> bool:
        self.prompts.append(prompt)
        return self.answer
