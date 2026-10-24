"""The safety gate: allow-list + confirmation, enforced in code (not by prompt).

Every tool call Claude makes goes through :meth:`Dispatcher.dispatch`. Two
guarantees hold regardless of what the model says or what any tool returns:

* **Allow-list** — only a tool registered in the :class:`ToolRegistry` can run.
* **Confirmation** — an ACTION runs only if the user authorises it on the user
  channel: a per-action "yes" from the :class:`Confirmer`, or a standing ``trust``
  mode the user turned on. The dispatcher never inspects model text or tool output
  (or anything the duck hears / reads / sees) to decide this, so a "yes" injected
  into any of them cannot authorise an action or enable trust mode. A tool marked
  ``confirm_always`` (a consequential action) is confirmed even under trust.
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
    auto_approved: bool = False  # an action that ran under trust mode, without a prompt


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

    @property
    def image_for_model(self) -> bytes | None:
        """An image to hand the model, only from a tool that actually executed."""
        if self.outcome is Outcome.EXECUTED and self.result is not None:
            return self.result.image_png
        return None


class Dispatcher:
    """Runs tool calls behind the safety gate."""

    def __init__(
        self, registry: ToolRegistry, confirmer: Confirmer, *, trust: bool = False
    ) -> None:
        self._registry = registry
        self._confirmer = confirmer
        self._trust = trust
        self.audit: list[AuditEvent] = []

    def dispatch(self, name: str, arguments: dict[str, Any]) -> DispatchResult:
        tool = self._registry.get(name)

        # 1. Allow-list: an unregistered name is never run.
        if tool is None:
            return self._record(name, None, Outcome.REFUSED_UNKNOWN, None)

        # 2. Confirmation gate: an ACTION needs the user's OK on the user channel —
        #    either a per-action 'yes' from the confirmer, or a standing trust mode the
        #    user turned on. Model text, tool output, or anything heard/read/seen can
        #    never authorise one. A consequential (confirm_always) action is confirmed
        #    even under trust.
        auto_approved = False
        if tool.risk is Risk.ACTION:
            always = getattr(tool, "confirm_always", False)
            # A tool may also mark a *specific* call consequential (e.g. an acrobatic
            # gesture). If the predicate errors, fail safe and require confirmation.
            confirm_when = getattr(tool, "confirm_when", None)
            if callable(confirm_when):
                try:
                    if confirm_when(arguments):
                        always = True
                except Exception:
                    always = True
            if self._trust and not always:
                auto_approved = True
                log.info("auto-approved action %r (trust mode on)", name)
            elif not self._confirmer.confirm(self._prompt(tool, arguments)):
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
        return self._record(name, tool.risk, outcome, result, auto_approved=auto_approved)

    def _prompt(self, tool: Tool, arguments: dict[str, Any]) -> str:
        preview = getattr(tool, "preview", None)
        if callable(preview):
            return f"May I {preview(arguments)}?"
        return f"May I run the action {tool.name!r} with arguments {arguments!r}?"

    def _record(
        self,
        name: str,
        risk: Risk | None,
        outcome: Outcome,
        result: ToolResult | None,
        *,
        auto_approved: bool = False,
    ) -> DispatchResult:
        self.audit.append(
            AuditEvent(
                name=name,
                risk=risk.value if risk is not None else None,
                outcome=outcome,
                auto_approved=auto_approved,
            )
        )
        return DispatchResult(name=name, outcome=outcome, result=result)
