"""Test doubles: a scripted stand-in for the Anthropic client, and a recording confirmer.

These let the safety layer and the brain loop be tested fully offline — no network,
no ANTHROPIC_API_KEY. The fake blocks mimic the attribute shape (``.type``, ``.text``,
``.name``, ``.input``, ``.id``) the loop reads from real SDK content blocks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from microduck_claude.brain import LLMResponse, ToolCall
from microduck_claude.voice.interfaces import Utterance


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
        recorded = dict(kwargs)
        if "messages" in recorded:
            recorded["messages"] = list(recorded["messages"])  # snapshot; the list grows later
        self.calls.append(recorded)
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


class FakeSTT:
    """A scripted speech recognizer: yields each line once, then stops (None)."""

    def __init__(self, lines: list[str]) -> None:
        self._lines = list(lines)

    def listen(self) -> Utterance | None:
        if not self._lines:
            return None
        return Utterance(self._lines.pop(0))


class FakeTTS:
    """Records spoken text instead of producing audio."""

    def __init__(self) -> None:
        self.spoken: list[str] = []

    def speak(self, text: str) -> None:
        self.spoken.append(text)


class FakeLLM:
    """A scripted, provider-neutral LLM for testing the brain loop in isolation."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)
        self.started: dict[str, Any] | None = None

    def start(self, system: str, tools: list[dict[str, Any]]) -> None:
        self.started = {"system": system, "tools": tools}

    def send_user(self, text: str) -> LLMResponse:
        return self._next()

    def send_tool_results(self, results: list[Any]) -> LLMResponse:
        return self._next()

    def _next(self) -> LLMResponse:
        if not self._responses:
            raise AssertionError("LLM called more times than scripted")
        return self._responses.pop(0)


def llm_text(text: str) -> LLMResponse:
    return LLMResponse(texts=[text])


def llm_tool(
    call_id: str, name: str, tool_input: dict[str, Any], text: str | None = None
) -> LLMResponse:
    return LLMResponse(
        texts=[text] if text else [], tool_calls=[ToolCall(call_id, name, tool_input)]
    )


def llm_refusal() -> LLMResponse:
    return LLMResponse(refused=True)
