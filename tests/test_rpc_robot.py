from __future__ import annotations

import http.client
import time

import pytest

from microduck_claude.expressions import perform_gesture
from microduck_claude.robot import FakeRobot, RobotInterface, RpcRobot, UnixSocketTransport, rpc
from microduck_claude.robot import protocol as p
from microduck_claude.robot.transport import JsonRpcError
from tests.duck_server import FakeDuckServer

_PNG = b"\x89PNG\r\n\x1a\n"


class _RecordingTransport:
    """A minimal transport stand-in that records notify/request calls (no socket)."""

    def __init__(self) -> None:
        self.notifies: list[tuple[str, object]] = []
        self.requests: list[tuple[str, object]] = []

    def notify(self, method: str, params: object = None) -> None:
        self.notifies.append((method, params))

    def request(self, method: str, params: object = None) -> object:
        self.requests.append((method, params))
        return {}

    def close(self) -> None:
        pass

    def latest_state(self) -> dict[str, object]:
        return {}


class _FakeHTTPResponse:
    """A minimal urlopen() context manager returning canned camera bytes."""

    def __init__(self, data: bytes, status: int = 200, truncate: bool = False) -> None:
        self._data = data
        self.status = status
        self._truncate = truncate

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self, amt: int = -1) -> bytes:
        if self._truncate:
            raise http.client.IncompleteRead(b"partial")
        return self._data[:amt] if amt is not None and amt >= 0 else self._data


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


def test_drive_for_streams_the_twist_then_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    # The keep-alive (resend the twist so robotd's deadman doesn't zero it) lives here now.
    ticks = iter(i * 0.1 for i in range(100000))
    monkeypatch.setattr(rpc.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(rpc.time, "sleep", lambda _s: None)  # don't actually wait
    transport = _RecordingTransport()
    robot = RpcRobot(transport)  # type: ignore[arg-type]
    robot.drive_for(0.0, 0.0, 1.0, duration=0.5)
    moves = [m for m in transport.notifies if m[0] == p.ROBOT_MOVE]
    assert len(moves) > 1  # it kept resending the twist
    assert any(r[0] == p.ROBOT_STOP for r in transport.requests)  # and stopped at the end


def _rpc_with_camera(monkeypatch: pytest.MonkeyPatch, response: _FakeHTTPResponse) -> RpcRobot:
    monkeypatch.setattr(rpc.urllib.request, "urlopen", lambda url, timeout=0: response)
    return RpcRobot(UnixSocketTransport("/nonexistent.sock"), camera_url="http://cam/frame")


def test_capture_frame_accepts_a_small_valid_image(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = _PNG + b"pixels"
    assert _rpc_with_camera(monkeypatch, _FakeHTTPResponse(frame)).capture_frame() == frame


def test_capture_frame_rejects_a_non_image_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    robot = _rpc_with_camera(monkeypatch, _FakeHTTPResponse(b"<html>500 error</html>"))
    assert robot.capture_frame() is None


def test_capture_frame_rejects_an_oversized_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    robot = _rpc_with_camera(monkeypatch, _FakeHTTPResponse(_PNG + b"x" * (6 * 1024 * 1024)))
    assert robot.capture_frame() is None


def test_capture_frame_handles_a_truncated_response(monkeypatch: pytest.MonkeyPatch) -> None:
    robot = _rpc_with_camera(monkeypatch, _FakeHTTPResponse(b"", truncate=True))
    assert robot.capture_frame() is None


def test_capture_frame_without_a_camera_url_is_none() -> None:
    robot = RpcRobot(UnixSocketTransport("/nonexistent.sock"))  # no camera configured
    assert robot.capture_frame() is None


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
