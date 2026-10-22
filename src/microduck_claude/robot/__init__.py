"""Robot abstraction: one interface, swappable bodies."""

from __future__ import annotations

from .fake import FakeRobot, RobotCall
from .interface import SOUND_TAGS, STOCK_BEHAVIORS, RobotInterface

__all__ = [
    "FakeRobot",
    "RobotCall",
    "RobotInterface",
    "SOUND_TAGS",
    "STOCK_BEHAVIORS",
]
