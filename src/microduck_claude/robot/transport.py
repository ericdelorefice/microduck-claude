"""A JSON-RPC 2.0 / NDJSON transport over a Unix domain socket.

Microduck's daemons speak JSON-RPC 2.0 with one object per line (NDJSON) over a
Unix socket; there is deliberately no TCP control port. This transport implements
that framing with a background reader thread that demultiplexes responses (matched
by ``id``) from server notifications (e.g. ``robot.state``), so callers can issue
blocking :meth:`request` calls and fire-and-forget :meth:`notify` calls safely from
one thread.

The same transport drives the local ``duck-sim`` socket and, over an ``ssh -L``
forwarded socket, a real robot — the wire contract is identical.
"""

from __future__ import annotations

import json
import logging
import socket
import threading
from collections import deque
from dataclasses import dataclass
from types import TracebackType
from typing import Any

from .protocol import ROBOT_STATE

log = logging.getLogger("microduck_claude.robot.transport")


class JsonRpcError(RuntimeError):
    """A JSON-RPC error reply, a transport failure, or a request timeout."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(f"JSON-RPC error {code}: {message}")
        self.code = code
        self.message = message
        self.data = data


@dataclass
class _Pending:
    event: threading.Event
    result: Any = None
    error: JsonRpcError | None = None


class UnixSocketTransport:
    """Speaks NDJSON JSON-RPC 2.0 to a Unix domain socket."""

    def __init__(
        self,
        path: str,
        *,
        connect_timeout: float = 5.0,
        request_timeout: float = 5.0,
    ) -> None:
        self._path = path
        self._connect_timeout = connect_timeout
        self._request_timeout = request_timeout
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()  # guards _next_id, _pending, and sends
        self._pending: dict[int, _Pending] = {}
        self._next_id = 0
        self._notifications: deque[dict[str, Any]] = deque(maxlen=256)
        self._latest_state: dict[str, Any] | None = None
        self._reader: threading.Thread | None = None
        self._closed = threading.Event()

    # -- lifecycle -------------------------------------------------------------

    def connect(self) -> None:
        if self._sock is not None:
            return
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self._connect_timeout)
        sock.connect(self._path)
        sock.settimeout(None)  # blocking reads; close() unblocks via shutdown
        self._sock = sock
        self._reader = threading.Thread(target=self._read_loop, name="duck-rpc-reader", daemon=True)
        self._reader.start()

    def close(self) -> None:
        self._closed.set()
        sock = self._sock
        self._sock = None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
        if self._reader is not None:
            self._reader.join(timeout=2.0)
            self._reader = None
        self._fail_all(JsonRpcError(-1, "transport closed"))

    def __enter__(self) -> UnixSocketTransport:
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # -- public API ------------------------------------------------------------

    def request(self, method: str, params: Any = None, *, timeout: float | None = None) -> Any:
        """Send a request and block for its matching response."""
        if self._sock is None:
            raise JsonRpcError(-1, "not connected")
        pending = _Pending(event=threading.Event())
        with self._lock:
            self._next_id += 1
            msg_id = self._next_id
            self._pending[msg_id] = pending
            payload: dict[str, Any] = {"jsonrpc": "2.0", "id": msg_id, "method": method}
            if params is not None:
                payload["params"] = params
            self._send(payload)
        wait = self._request_timeout if timeout is None else timeout
        if not pending.event.wait(wait):
            with self._lock:
                self._pending.pop(msg_id, None)
            raise JsonRpcError(-1, f"timeout waiting for response to {method!r}")
        if pending.error is not None:
            raise pending.error
        return pending.result

    def notify(self, method: str, params: Any = None) -> None:
        """Send a notification (no id, no reply expected)."""
        if self._sock is None:
            raise JsonRpcError(-1, "not connected")
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        with self._lock:
            self._send(payload)

    def latest_state(self) -> dict[str, Any] | None:
        """The most recent ``robot.state`` notification payload, if any."""
        state = self._latest_state
        return dict(state) if state is not None else None

    # -- internals -------------------------------------------------------------

    def _send(self, payload: dict[str, Any]) -> None:
        # Caller holds self._lock.
        assert self._sock is not None
        line = json.dumps(payload, separators=(",", ":")) + "\n"
        self._sock.sendall(line.encode("utf-8"))

    def _read_loop(self) -> None:
        sock = self._sock
        assert sock is not None
        buffer = b""
        try:
            while not self._closed.is_set():
                try:
                    chunk = sock.recv(65536)
                except OSError:
                    break
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    raw, buffer = buffer.split(b"\n", 1)
                    raw = raw.strip()
                    if raw:
                        self._dispatch(raw)
        finally:
            self._fail_all(JsonRpcError(-1, "transport closed"))

    def _dispatch(self, raw: bytes) -> None:
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("dropping non-JSON line from robot (%d bytes)", len(raw))
            return
        if not isinstance(message, dict):
            return
        msg_id = message.get("id")
        if msg_id is not None and ("result" in message or "error" in message):
            self._deliver_response(msg_id, message)
        else:
            self._handle_notification(message)

    def _deliver_response(self, msg_id: Any, message: dict[str, Any]) -> None:
        with self._lock:
            pending = self._pending.pop(msg_id, None)
        if pending is None:
            return
        error = message.get("error")
        if error:
            pending.error = JsonRpcError(
                int(error.get("code", -1)), str(error.get("message", "")), error.get("data")
            )
        else:
            pending.result = message.get("result")
        pending.event.set()

    def _handle_notification(self, message: dict[str, Any]) -> None:
        if message.get("method") == ROBOT_STATE:
            params = message.get("params")
            if isinstance(params, dict):
                self._latest_state = params
        self._notifications.append(message)

    def _fail_all(self, error: JsonRpcError) -> None:
        with self._lock:
            pending = list(self._pending.values())
            self._pending.clear()
        for item in pending:
            if not item.event.is_set():
                item.error = error
                item.event.set()
