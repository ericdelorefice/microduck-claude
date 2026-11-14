"""Build a robot backend from configuration: the in-process fake, or a real RPC duck."""

from __future__ import annotations

import os

from .fake import FakeRobot
from .interface import RobotInterface
from .protocol import API_VERSION, DEFAULT_SIM_SOCKET, TOF_ROBOT_SOCKET
from .rpc import RpcRobot
from .transport import UnixSocketTransport


def build_robot(
    backend: str = "fake",
    *,
    socket_path: str = DEFAULT_SIM_SOCKET,
    api_version: int = API_VERSION,
    camera_url: str = "",
    tof_socket: str = "",
) -> RobotInterface:
    """Return a :class:`RobotInterface`.

    ``"fake"`` is the in-process :class:`FakeRobot`. ``"rpc"`` connects to a running
    ``duck-sim`` (or an ``ssh -L`` forwarded robot socket) and performs the handshake;
    it may raise ``OSError`` (no socket) or ``JsonRpcError`` (handshake failed).
    ``camera_url`` is the live body's camera snapshot endpoint (the fake has no camera).
    ``tof_socket`` is tofd's depth stream; empty means look beside the robot socket (the
    sim's ``duck-a-tof.sock``), then the robot's own path. A body without one still works.
    """
    backend = backend.lower()
    if backend == "fake":
        return FakeRobot()
    if backend == "rpc":
        path = os.path.expanduser(socket_path)
        transport = UnixSocketTransport(path)
        transport.connect()
        robot = RpcRobot(transport, api_version=api_version, camera_url=camera_url)
        robot.handshake()
        tof = os.path.expanduser(tof_socket) if tof_socket else _find_tof_socket(path)
        if tof:
            robot.open_tof(tof)
        return robot
    raise ValueError(f"unknown robot backend {backend!r}; use 'fake' or 'rpc'")


def _find_tof_socket(robot_socket: str) -> str:
    stem, ext = os.path.splitext(robot_socket)
    for candidate in (f"{stem}-tof{ext}", TOF_ROBOT_SOCKET):
        if os.path.exists(candidate):
            return candidate
    return ""
