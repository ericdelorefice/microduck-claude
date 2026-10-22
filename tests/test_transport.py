from __future__ import annotations

import pytest

from microduck_claude.robot.transport import JsonRpcError, UnixSocketTransport
from tests.duck_server import FakeDuckServer


def test_request_response_round_trip() -> None:
    with FakeDuckServer() as server, UnixSocketTransport(server.path) as transport:
        result = transport.request("hello", {"api_version": 36})
        assert result["api_version"] == 36
        assert "daemon_version" in result
        assert any(m["method"] == "hello" for m in server.requests())


def test_notification_carries_no_id() -> None:
    with FakeDuckServer() as server, UnixSocketTransport(server.path) as transport:
        transport.notify("robot.move", {"vx": 0.1, "vy": 0.0, "vyaw": 0.0})
        assert server.wait_for(lambda msgs: any(m.get("method") == "robot.move" for m in msgs))
        note = server.notifications()[-1]
        assert note["method"] == "robot.move"
        assert "id" not in note


def test_error_reply_raises() -> None:
    with FakeDuckServer() as server, UnixSocketTransport(server.path) as transport:
        with pytest.raises(JsonRpcError):
            transport.request("does.not.exist")


def test_request_timeout_raises() -> None:
    with FakeDuckServer() as server, UnixSocketTransport(server.path, request_timeout=0.2) as t:
        server.handlers["robot.do"] = lambda _params: FakeDuckServer.NO_REPLY
        with pytest.raises(JsonRpcError):
            t.request("robot.do", {"skill": "x"}, timeout=0.2)
