"""The optional integration hook.

A private/external assistant adds tools by shipping a package that registers a
:class:`ToolProvider` under the ``microduck_claude.tool_providers`` entry-point
group. The open core ships none and imports none; discovery finding nothing is the
normal case. Every tool a provider contributes still passes through the same safety
gate (allow-list + confirmation) as core tools.
"""

from __future__ import annotations

import logging
from importlib.metadata import entry_points
from typing import Protocol

from ..tools.base import Tool

log = logging.getLogger("microduck_claude.plugins")

ENTRY_POINT_GROUP = "microduck_claude.tool_providers"


class ToolProvider(Protocol):
    """A source of additional tools."""

    def get_tools(self) -> list[Tool]: ...


def discover_providers(group: str = ENTRY_POINT_GROUP) -> list[ToolProvider]:
    """Load installed tool providers. Returns an empty list when none are installed."""
    providers: list[ToolProvider] = []
    for ep in entry_points().select(group=group):
        try:
            obj = ep.load()
            provider = obj() if isinstance(obj, type) else obj
        except Exception:
            log.warning("failed to load tool provider %r; skipping", ep.name)
            continue
        providers.append(provider)
    return providers
