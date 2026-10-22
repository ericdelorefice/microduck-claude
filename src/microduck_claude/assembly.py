"""Wire a robot + core tools (+ optional providers) into a tool allow-list."""

from __future__ import annotations

from collections.abc import Iterable

from .plugins.base import ToolProvider, discover_providers
from .robot.interface import RobotInterface
from .tools.base import ToolRegistry
from .tools.core import build_core_tools


def build_registry(
    robot: RobotInterface,
    *,
    providers: Iterable[ToolProvider] | None = None,
    include_installed_plugins: bool = False,
) -> ToolRegistry:
    """Assemble the allow-list: core tools plus any supplied or installed providers.

    The core depends on no provider; ``providers`` and ``include_installed_plugins``
    are both opt-in.
    """
    registry = ToolRegistry()
    for tool in build_core_tools(robot):
        registry.register(tool)

    extra: list[ToolProvider] = list(providers or [])
    if include_installed_plugins:
        extra.extend(discover_providers())
    for provider in extra:
        for tool in provider.get_tools():
            registry.register(tool)

    return registry
