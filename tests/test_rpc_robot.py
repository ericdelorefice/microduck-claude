from __future__ import annotations

import time

import pytest

from microduck_claude.expressions import perform_gesture
from microduck_claude.robot import FakeRobot, RobotInterface, RpcRobot, UnixSocketTransport
from microduck_claude.robot.transport import JsonRpcError
from tests.duck_server import FakeDuckServer


def _connect(server: FakeDuckServer) -> RpcRobot:
    transport = UnixSocketTransport(server.path)
    transport.connect()
    robot = RpcRobot(transport, subscribe_hz=0.0)  # keep the notification stream clean
    robot.handshake()
    return robot


def _wait_until(predicate: object, timeout: float = 2.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():  # type: ignore[operator]
            return True
        time.sleep(0.01)
    return False


def test_rpc_robot_satisfies_interface() -> None:
    assert isinstance(RpcRobot(UnixSocketTransport("/nonexistent.sock")), RobotInterface)


def test_handshake_sends_hello() -> None:
    with FakeDuckServer() as server:
        robot = _connect(server)
        try:
            assert any(m["method"] == "hello" for m in server.requests())
        finally:
            robot.close()


def test_do_behavior_round_trips_accept_flag() -> None:
    with FakeDuckServer() as server:
        robot = _connect(server)
        try:
            assert robot.do_behavior("sit_toggle") is True
            assert robot.do_behavior("teleport") is False
            dos = [m for m in server.requests() if m["method"] == "robot.do"]
            assert dos[0]["params"] == {"skill": "sit_toggle"}
        finally:
            robot.close()


def test_continuous_commands_are_notifications() -> None:
    with FakeDuckServer() as server:
        robot = _connect(server)
        try:
            robot.drive(0.1, 0.0, 0.2)
            robot.set_head(head_yaw=0.5)
            robot.set_pose(z=0.01)
            assert server.wait_for(
                lambda msgs: (
                    {"robot.move", "robot.head", "robot.pose"}
                    <= {m.get("method") for m in msgs if m.get("id") is None}
                )
            )
        finally:
            robot.close()


def test_play_sound_validates_tag_before_sending() -> None:
    with FakeDuckServer() as server:
        robot = _connect(server)
        try:
            with pytest.raises(ValueError):
                robot.play_sound("kaboom")
            robot.play_sound("greet")
            assert server.wait_for(lambda msgs: any(m.get("method") == "robot.sound" for m in msgs))
        finally:
            robot.close()


def test_get_battery_from_health() -> None:
    with FakeDuckServer() as server:
        robot = _connect(server)
        try:
            assert robot.get_battery() == pytest.approx(0.9)
        finally:
            robot.close()


def test_get_state_reflects_pushed_state() -> None:
    with FakeDuckServer() as server:
        robot = _connect(server)
        try:
            server.push("robot.state", {"joints": [0, 0, 0]})
            assert _wait_until(lambda: "joints" in robot.get_state())
        finally:
            robot.close()


def test_error_surfaces_as_exception() -> None:
    def _boom(_params: dict[str, object]) -> object:
        raise RuntimeError("boom")

    with FakeDuckServer() as server:
        robot = _connect(server)
        try:
            server.handlers["robot.policies"] = _boom
            with pytest.raises(JsonRpcError):
                robot.list_behaviors()
        finally:
            robot.close()


def test_drop_in_equivalence_with_fake_robot() -> None:
    # The same gesture must produce matching intents whether the body is a FakeRobot
    # or an RpcRobot talking to a duck over the wire.
    fake = FakeRobot()
    perform_gesture(fake, "nod")
    expected_head_calls = sum(1 for c in fake.calls if c.method == "set_head")

    with FakeDuckServer() as server:
        robot = _connect(server)
        try:
            perform_gesture(robot, "nod")
            assert server.wait_for(
                lambda msgs: (
                    sum(1 for m in msgs if m.get("method") == "robot.head") >= expected_head_calls
                )
            )
            head_notes = [m for m in server.notifications() if m["method"] == "robot.head"]
            assert len(head_notes) == expected_head_calls
        finally:
            robot.close()
