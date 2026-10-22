"""Safety layer: the allow-list + confirmation gate, and confirmer helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .dispatcher import AuditEvent, Confirmer, Dispatcher, DispatchResult, Outcome


@dataclass
class CallbackConfirmer:
    """Adapter turning a ``callable(prompt) -> bool`` into a :class:`Confirmer`."""

    callback: Callable[[str], bool]

    def confirm(self, prompt: str) -> bool:
        return self.callback(prompt)


__all__ = [
    "AuditEvent",
    "CallbackConfirmer",
    "Confirmer",
    "DispatchResult",
    "Dispatcher",
    "Outcome",
]
