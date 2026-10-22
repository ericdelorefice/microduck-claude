"""A minimal in-repo duck-ipc-proto server over a real Unix socket, for tests.

It binds a Unix socket, speaks NDJSON JSON-RPC 2.0, records every message it
receives, answers requests via handlers (defaults mimic the real daemons), and can
push notifications (e.g. ``robot.state``). This lets the transport and RpcRobot be
verified end-to-end over a real socket without the actual Rust daemons.
"""

from __future__ import annotations

import json
import os
import socket
import tempfile
import threading
import time
from collections.abc import Callable
from typing import Any

Handler = Callable[[dict[str, Any]], Any]

_KNOWN_SKILLS = ["sit_toggle", "ground_pick", "kick_left", "kick_right", "roulade"]


class FakeDuckServer:
    """A test double for a Microduck control daemon."""

    #: Sentinel a handler can return to deliberately send no reply (to test timeouts).
    NO_REPLY = object()

    def __init__(self) -> None:
        self._dir = tempfile.mkdtemp()
        self.path = os.path.join(self._dir, "d.sock")
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(self.path)
        self._server.listen(1)
        self._conn: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._closed = threading.Event()
        self._lock = threading.Lock()
        self._received: list[dict[str, Any]] = []
        self.handlers: dict[str, Handler] = {}
        self._install_defaults()

    def _install_defaults(self) -> None:
        def intent_ok(_params: dict[str, Any]) -> dict[str, Any]:
            return {"accepted": True, "reason": None}

        self.handlers["hello"] = lambda params: {
            "api_version": params.get("api_version"),
            "daemon_version": "0.17.8",
        }
        self.handlers["robot.do"] = lambda params: {
            "accepted": params.get("skill") in _KNOWN_SKILLS,
            "reason": None,
        }
        self.handlers["robot.stop"] = intent_ok
        self.handlers["robot.look"] = lambda params: {"head": {}, "clamped": False}
        self.handlers["robot.sound"] = intent_ok
        self.handlers["robot.subscribe"] = lambda params: {
            "accepted": True,
            "skills": list(_KNOWN_SKILLS),
        }
        self.handlers["robot.policies"] = lambda params: {"skills": list(_KNOWN_SKILLS)}
        self.handlers["robot.health"] = lambda params: {
            "healthy": True,
            "battery": {"volts": 7.4, "percent": 90.0},
        }

    # -- lifecycle -------------------------------------------------------------

    def start(self) -> None:
        self._thread = threading.Thread(target=self._serve, name="fake-duck", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._closed.set()
        if self._conn is not None:
            _silent_close(self._conn)
        _silent_close(self._server)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        try:
            os.remove(self.path)
        except OSError:
            pass
        try:
            os.rmdir(self._dir)
        except OSError:
            pass

    def __enter__(self) -> FakeDuckServer:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- serving ---------------------------------------------------------------

    def _serve(self) -> None:
        self._server.settimeout(1.0)
        try:
            conn, _ = self._server.accept()
        except OSError:
            return
        self._conn = conn
        conn.settimeout(0.2)
        buffer = b""
        while not self._closed.is_set():
            try:
                chunk = conn.recv(65536)
            except TimeoutError:
                continue
            except OSError:
                break
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                raw, buffer = buffer.split(b"\n", 1)
                raw = raw.strip()
                if raw:
                    self._handle(raw)

    def _handle(self, raw: bytes) -> None:
        message = json.loads(raw)
        with self._lock:
            self._received.append(message)
        msg_id = message.get("id")
        if msg_id is None:
            return  # a notification: recorded, no reply
        handler = self.handlers.get(message.get("method"))
        if handler is None:
            self._reply(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {
                        "code": -32601,
                        "message": f"method not found: {message.get('method')}",
                    },
                }
            )
            return
        try:
            result = handler(message.get("params") or {})
        except Exception as exc:
            self._reply(
                {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32000, "message": str(exc)}}
            )
            return
        if result is self.NO_REPLY:
            return
        self._reply({"jsonrpc": "2.0", "id": msg_id, "result": result})

    def _reply(self, payload: dict[str, Any]) -> None:
        conn = self._conn
        if conn is None:
            return
        try:
            conn.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        except OSError:
            pass

    def push(self, method: str, params: dict[str, Any]) -> None:
        """Send a server-initiated notification to the client."""
        self._reply({"jsonrpc": "2.0", "method": method, "params": params})

    # -- introspection ---------------------------------------------------------

    def all_messages(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._received)

    def requests(self) -> list[dict[str, Any]]:
        return [m for m in self.all_messages() if m.get("id") is not None]

    def notifications(self) -> list[dict[str, Any]]:
        return [m for m in self.all_messages() if m.get("id") is None]

    def wait_for(
        self, predicate: Callable[[list[dict[str, Any]]], bool], timeout: float = 2.0
    ) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate(self.all_messages()):
                return True
            time.sleep(0.01)
        return False


def _silent_close(sock: socket.socket) -> None:
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass
