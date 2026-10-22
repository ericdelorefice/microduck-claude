"""Robot abstraction: one interface, swappable bodies."""

from __future__ import annotations

from .factory import build_robot
from .fake import FakeRobot, RobotCall
from .interface import SOUND_TAGS, STOCK_BEHAVIORS, RobotInterface
from .rpc import RpcRobot
from .transport import JsonRpcError, UnixSocketTransport

__all__ = [
    "SOUND_TAGS",
    "STOCK_BEHAVIORS",
    "FakeRobot",
    "JsonRpcError",
    "RobotCall",
    "RobotInterface",
    "RpcRobot",
    "UnixSocketTransport",
    "build_robot",
]
