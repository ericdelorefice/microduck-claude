"""The playground's local HTTP server and the app that wires it together.

Binds localhost only, and accepts POSTs only from its own page. Uses a threading server
so an in-browser confirmation can be answered while the ``/say`` request that is waiting
on it is still open. Safety is preserved: actions go through the normal Dispatcher, and
the :class:`WebConfirmer` is answered only by the browser's explicit Allow/Deny — model or
tool text can't.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from ..assembly import build_registry
from ..brain import LLM, SYSTEM_PROMPT, Brain
from ..expressions import (
    GestureUnavailableError,
    UnknownGestureError,
    gesture_names,
    perform_gesture,
)
from ..robot import FakeRobot, RobotCall
from ..safety import Dispatcher
from .page import PAGE_HTML
from .state import DuckState


@dataclass
class _Pending:
    id: int
    prompt: str
    event: threading.Event
    allowed: bool = False


class WebConfirmer:
    """Confirms an action via the browser. Fail-safe: a timeout counts as 'no'.

    Only an explicit Allow from the browser (:meth:`resolve` with ``allow=True``)
    confirms; model output or tool results can never reach this.
    """

    def __init__(self, timeout: float = 120.0) -> None:
        self._timeout = timeout
        self._lock = threading.Lock()
        self._next_id = 0
        self._pending: _Pending | None = None

    def confirm(self, prompt: str) -> bool:
        with self._lock:
            self._next_id += 1
            pending = _Pending(id=self._next_id, prompt=prompt, event=threading.Event())
            self._pending = pending
        allowed = pending.event.wait(self._timeout) and pending.allowed
        with self._lock:
            if self._pending is pending:
                self._pending = None
        return allowed

    def snapshot(self) -> dict[str, Any] | None:
        with self._lock:
            if self._pending is None:
                return None
            return {"id": self._pending.id, "prompt": self._pending.prompt}

    def resolve(self, pending_id: int, allow: bool) -> bool:
        with self._lock:
            pending = self._pending
            if pending is None or pending.id != pending_id:
                return False
            pending.allowed = allow
            pending.event.set()
            return True


class PlaygroundApp:
    """Owns the fake duck, its state, the brain, and the web confirmer."""

    def __init__(self, llm: LLM | None = None, *, confirm_timeout: float = 120.0) -> None:
        self._lock = threading.Lock()
        self.state = DuckState()
        self.robot = FakeRobot(on_call=self._on_call)
        self.confirmer = WebConfirmer(timeout=confirm_timeout)
        registry = build_registry(self.robot)
        dispatcher = Dispatcher(registry, self.confirmer)
        self._brain = (
            Brain(llm, registry, dispatcher, system=SYSTEM_PROMPT) if llm is not None else None
        )

    def _on_call(self, call: RobotCall) -> None:
        with self._lock:
            self.state.apply(call)

    def state_dict(self) -> dict[str, Any]:
        with self._lock:
            duck = self.state.to_dict()
        return {"duck": duck, "pending": self.confirmer.snapshot()}

    def say(self, text: str) -> dict[str, Any]:
        if self._brain is None:
            return {
                "replies": [
                    "No Anthropic credentials — run `ant auth login` "
                    "or set ANTHROPIC_API_KEY, then restart me to chat."
                ],
                "refused": False,
            }
        turn = self._brain.send(text)
        return {"replies": turn.texts, "refused": turn.refused}

    def preview_gesture(self, name: str) -> dict[str, Any]:
        try:
            gesture = perform_gesture(self.robot, name)
        except UnknownGestureError:
            return {"ok": False, "error": f"unknown gesture {name!r}"}
        except GestureUnavailableError:
            return {"ok": False, "error": f"the duck can't do {name!r} on this body"}
        return {"ok": True, "gesture": gesture.name}

    def gesture_names(self) -> list[str]:
        return gesture_names()


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    app: PlaygroundApp

    def __init__(self, address: tuple[str, int], app: PlaygroundApp) -> None:
        super().__init__(address, _Handler)
        self.app = app


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:  # quiet by default
        pass

    @property
    def _app(self) -> PlaygroundApp:
        return self.server.app  # type: ignore[attr-defined]

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send(200, "text/html; charset=utf-8", PAGE_HTML.encode("utf-8"))
        elif path == "/state":
            self._json(self._app.state_dict())
        elif path == "/gestures":
            self._json({"gestures": self._app.gesture_names()})
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        if not self._from_this_page():
            self.send_error(403, "POSTs are accepted only from the playground page")
            return
        body = self._read_json()
        if self.path == "/say":
            text = str(body.get("text", "")).strip()
            self._json({"replies": [], "refused": False} if not text else self._app.say(text))
        elif self.path == "/gesture":
            self._json(self._app.preview_gesture(str(body.get("name", ""))))
        elif self.path == "/confirm":
            ok = self._app.confirmer.resolve(_int(body.get("id")), bool(body.get("allow")))
            self._json({"ok": ok})
        else:
            self.send_error(404)

    def _from_this_page(self) -> bool:
        """Whether a POST came from the playground page itself, not another site.

        Another page in the browser can send a form-style (``text/plain``) POST here with no
        CORS preflight, and could answer a pending confirmation. The page always sends JSON,
        which a browser sends cross-origin only after a preflight this server never answers;
        a foreign ``Origin`` is refused, and the ``Host`` check stops DNS rebinding.
        """
        port = self.server.server_port  # type: ignore[attr-defined]
        host = self.headers.get("Host", "")
        if host not in (f"127.0.0.1:{port}", f"localhost:{port}"):
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin != f"http://{host}":
            return False
        content_type = self.headers.get("Content-Type", "")
        return content_type.split(";", 1)[0].strip().lower() == "application/json"

    def _read_json(self) -> dict[str, Any]:
        length = _int(self.headers.get("Content-Length"))
        raw = self.rfile.read(length) if length > 0 else b""
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _json(self, obj: Any) -> None:
        self._send(200, "application/json", json.dumps(obj).encode("utf-8"))

    def _send(self, status: int, content_type: str, data: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def build_server(
    app: PlaygroundApp, host: str = "127.0.0.1", port: int = 8777
) -> ThreadingHTTPServer:
    """Create (but do not start) the playground server bound to localhost."""
    return _Server((host, port), app)
