from __future__ import annotations

import json
import threading
import time
import urllib.request

from microduck_claude.playground import DuckState, PlaygroundApp, WebConfirmer, build_server
from microduck_claude.robot import FakeRobot, RobotCall
from tests.fakes import FakeLLM, llm_text

# -- DuckState reducer --------------------------------------------------------


def test_duckstate_folds_calls() -> None:
    state = DuckState()
    state.apply(RobotCall("set_head", {"head_yaw": 0.5, "head_pitch": 0.1}))
    state.apply(RobotCall("set_mouth", {"open_fraction": 0.6}))
    state.apply(RobotCall("play_sound", {"tag": "coo"}))
    state.apply(RobotCall("do_behavior", {"skill": "sit_toggle", "accepted": True}))
    state.apply(RobotCall("drive", {"vx": 0.1, "vy": 0.0, "vyaw": 0.0}))

    data = state.to_dict()
    assert data["head_yaw"] == 0.5
    assert data["mouth"] == 0.6
    assert data["last_sound"] == "coo"
    assert data["last_behavior"] == "sit_toggle"
    assert data["driving"] is True
    assert data["events"] == 5

    state.apply(RobotCall("stop", {}))
    assert state.to_dict()["driving"] is False


# -- FakeRobot observer hook --------------------------------------------------


def test_fake_robot_on_call_observer() -> None:
    seen: list[RobotCall] = []
    robot = FakeRobot(on_call=seen.append)
    robot.set_head(head_yaw=0.3)
    robot.play_sound("greet")
    assert [c.method for c in seen] == ["set_head", "play_sound"]


# -- WebConfirmer -------------------------------------------------------------


def _wait_snapshot(confirmer: WebConfirmer, timeout: float = 2.0) -> dict | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        snap = confirmer.snapshot()
        if snap is not None:
            return snap
        time.sleep(0.01)
    return None


def test_web_confirmer_allow() -> None:
    confirmer = WebConfirmer(timeout=2.0)
    out: list[bool] = []
    thread = threading.Thread(target=lambda: out.append(confirmer.confirm("Do it?")))
    thread.start()
    snap = _wait_snapshot(confirmer)
    assert snap is not None and snap["prompt"] == "Do it?"
    assert confirmer.resolve(snap["id"], True) is True
    thread.join(2.0)
    assert out == [True]


def test_web_confirmer_deny() -> None:
    confirmer = WebConfirmer(timeout=2.0)
    out: list[bool] = []
    thread = threading.Thread(target=lambda: out.append(confirmer.confirm("X?")))
    thread.start()
    snap = _wait_snapshot(confirmer)
    assert snap is not None
    confirmer.resolve(snap["id"], False)
    thread.join(2.0)
    assert out == [False]


def test_web_confirmer_timeout_is_no() -> None:
    assert WebConfirmer(timeout=0.2).confirm("X?") is False  # never resolved -> no


# -- PlaygroundApp ------------------------------------------------------------


def test_preview_gesture_moves_the_duck() -> None:
    app = PlaygroundApp(llm=None)
    assert app.preview_gesture("nod") == {"ok": True, "gesture": "nod"}
    assert app.state_dict()["duck"]["events"] > 0


def test_preview_unknown_gesture() -> None:
    assert PlaygroundApp(llm=None).preview_gesture("backflip")["ok"] is False


def test_say_without_key_returns_hint() -> None:
    out = PlaygroundApp(llm=None).say("hello")
    assert out["refused"] is False
    assert out["replies"]


def test_say_with_fake_client() -> None:
    app = PlaygroundApp(llm=FakeLLM([llm_text("Quack!")]))
    assert app.say("hi")["replies"] == ["Quack!"]


# -- Server smoke -------------------------------------------------------------


def test_server_serves_page_state_and_endpoints() -> None:
    app = PlaygroundApp(llm=FakeLLM([llm_text("hi there")]))
    server = build_server(app, port=0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{port}"
        page = urllib.request.urlopen(base + "/", timeout=5).read().decode()
        assert "Microduck Playground" in page

        state = json.loads(urllib.request.urlopen(base + "/state", timeout=5).read())
        assert "duck" in state and "pending" in state

        gestures = json.loads(urllib.request.urlopen(base + "/gestures", timeout=5).read())
        assert "nod" in gestures["gestures"]

        res = json.loads(_post(base + "/gesture", {"name": "nod"}))
        assert res["ok"] is True

        reply = json.loads(_post(base + "/say", {"text": "hi"}))
        assert reply["replies"] == ["hi there"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2.0)


def _post(url: str, body: dict) -> bytes:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return urllib.request.urlopen(req, timeout=5).read()
