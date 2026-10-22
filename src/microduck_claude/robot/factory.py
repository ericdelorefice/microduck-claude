"""Build a robot backend from configuration: the in-process fake, or a real RPC duck."""

from __future__ import annotations

import os

from .fake import FakeRobot
from .interface import RobotInterface
from .protocol import API_VERSION, DEFAULT_SIM_SOCKET
from .rpc import RpcRobot
from .transport import UnixSocketTransport


def build_robot(
    backend: str = "fake",
    *,
    socket_path: str = DEFAULT_SIM_SOCKET,
    api_version: int = API_VERSION,
) -> RobotInterface:
    """Return a :class:`RobotInterface`.

    ``"fake"`` is the in-process :class:`FakeRobot`. ``"rpc"`` connects to a running
    ``duck-sim`` (or an ``ssh -L`` forwarded robot socket) and performs the handshake;
    it may raise ``OSError`` (no socket) or ``JsonRpcError`` (handshake failed).
    """
    backend = backend.lower()
    if backend == "fake":
        return FakeRobot()
    if backend == "rpc":
        transport = UnixSocketTransport(os.path.expanduser(socket_path))
        transport.connect()
        robot = RpcRobot(transport, api_version=api_version)
        robot.handshake()
        return robot
    raise ValueError(f"unknown robot backend {backend!r}; use 'fake' or 'rpc'")
