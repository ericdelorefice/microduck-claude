"""Wire a robot + core tools (+ optional providers) into a tool allow-list."""

from __future__ import annotations

from collections.abc import Iterable

from .memory import MemoryStore, build_memory_tools
from .plugins.base import ToolProvider, discover_providers
from .robot.interface import RobotInterface
from .tools.base import ToolRegistry
from .tools.core import build_core_tools


def build_registry(
    robot: RobotInterface,
    *,
    memory: MemoryStore | None = None,
    providers: Iterable[ToolProvider] | None = None,
    include_installed_plugins: bool = False,
    gesture_pace: float = 0.0,
    camera_url: str = "",
) -> ToolRegistry:
    """Assemble the allow-list: core tools, optional memory tools, and any supplied
    or installed providers. Everything beyond the core tools is opt-in."""
    registry = ToolRegistry()
    for tool in build_core_tools(robot, gesture_pace=gesture_pace, camera_url=camera_url):
        registry.register(tool)
    if memory is not None:
        for tool in build_memory_tools(memory):
            registry.register(tool)

    extra: list[ToolProvider] = list(providers or [])
    if include_installed_plugins:
        extra.extend(discover_providers())
    for provider in extra:
        for tool in provider.get_tools():
            registry.register(tool)

    return registry
