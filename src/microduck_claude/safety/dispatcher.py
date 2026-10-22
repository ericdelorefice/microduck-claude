"""The safety gate: allow-list + confirmation, enforced in code (not by prompt).

Every tool call Claude makes goes through :meth:`Dispatcher.dispatch`. Two
guarantees hold regardless of what the model says or what any tool returns:

* **Allow-list** — only a tool registered in the :class:`ToolRegistry` can run.
* **Confirmation** — an ACTION runs only if the :class:`Confirmer` (the user
  channel) says yes. The dispatcher never inspects model text or tool output to
  decide this, so a "yes" injected into either cannot authorise an action.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from ..tools.base import Risk, Tool, ToolRegistry, ToolResult

log = logging.getLogger("microduck_claude.safety")


class Confirmer(Protocol):
    """The sole source of user confirmation for actions."""

    def confirm(self, prompt: str) -> bool: ...


class Outcome(enum.Enum):
    EXECUTED = "executed"
    REFUSED_UNKNOWN = "refused_unknown"
    DECLINED_BY_USER = "declined_by_user"
    ERROR = "error"


@dataclass
class AuditEvent:
    """A single, reviewable record of a dispatch decision (no raw arguments)."""

    name: str
    risk: str | None
    outcome: Outcome


@dataclass
class DispatchResult:
    name: str
    outcome: Outcome
    result: ToolResult | None = None

    @property
    def is_error(self) -> bool:
        return self.outcome is not Outcome.EXECUTED

    @property
    def content_for_model(self) -> str:
        """Text returned to the model as the tool result (a data channel)."""
        if self.outcome is Outcome.EXECUTED and self.result is not None:
            return self.result.content
        if self.outcome is Outcome.REFUSED_UNKNOWN:
            return f"Refused: no tool named {self.name!r} is available."
        if self.outcome is Outcome.DECLINED_BY_USER:
            return "The user did not confirm this action, so it was not performed."
        if self.result is not None:
            return self.result.content
        return "The tool could not be run."


class Dispatcher:
    """Runs tool calls behind the safety gate."""

    def __init__(self, registry: ToolRegistry, confirmer: Confirmer) -> None:
        self._registry = registry
        self._confirmer = confirmer
        self.audit: list[AuditEvent] = []

    def dispatch(self, name: str, arguments: dict[str, Any]) -> DispatchResult:
        tool = self._registry.get(name)

        # 1. Allow-list: an unregistered name is never run.
        if tool is None:
            return self._record(name, None, Outcome.REFUSED_UNKNOWN, None)

        # 2. Confirmation gate: actions require a 'yes' from the confirmer (the user
        #    channel) ONLY — never from model text or tool output.
        if tool.risk is Risk.ACTION and not self._confirmer.confirm(self._prompt(tool, arguments)):
            return self._record(name, tool.risk, Outcome.DECLINED_BY_USER, None)

        # 3. Run the tool; a failure becomes an error result, not a crash.
        try:
            result = tool.run(arguments)
        except Exception as exc:
            log.warning("tool %r raised %s", name, exc.__class__.__name__)
            return self._record(
                name, tool.risk, Outcome.ERROR, ToolResult(f"tool error: {exc}", ok=False)
            )

        outcome = Outcome.EXECUTED if result.ok else Outcome.ERROR
        return self._record(name, tool.risk, outcome, result)

    def _prompt(self, tool: Tool, arguments: dict[str, Any]) -> str:
        preview = getattr(tool, "preview", None)
        if callable(preview):
            return f"The duck will {preview(arguments)}. Allow it?"
        return f"Allow the action {tool.name!r}? arguments={arguments!r}"

    def _record(
        self,
        name: str,
        risk: Risk | None,
        outcome: Outcome,
        result: ToolResult | None,
    ) -> DispatchResult:
        self.audit.append(
            AuditEvent(name=name, risk=risk.value if risk is not None else None, outcome=outcome)
        )
        return DispatchResult(name=name, outcome=outcome, result=result)
