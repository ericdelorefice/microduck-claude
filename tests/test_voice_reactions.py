from __future__ import annotations

from microduck_claude.robot import SOUND_TAGS, FakeRobot
from microduck_claude.voice import SpeechReactor


def test_reactor_uses_only_bounded_expressive_primitives() -> None:
    robot = FakeRobot()
    reactor = SpeechReactor(robot)
    reactor.on_listening()
    reactor.on_speaking("a reasonably long sentence to animate the beak a few times")
    reactor.on_idle()

    allowed = {"set_head", "set_mouth", "play_sound"}
    assert robot.calls  # it did react
    assert all(c.method in allowed for c in robot.calls)
    # A reaction is expressive, never a navigational/manipulation action:
    assert not any(c.method in {"drive", "do_behavior", "stop"} for c in robot.calls)
    for call in robot.calls:
        if call.method == "play_sound":
            assert call.kwargs["tag"] in SOUND_TAGS


def test_reactor_speaking_chirps() -> None:
    robot = FakeRobot()
    SpeechReactor(robot).on_speaking("hello")
    # on_speaking announces a reply with a chirp; beak motion is animate()'s job now.
    assert any(c.method == "play_sound" and c.kwargs["tag"] == "coo" for c in robot.calls)


def test_reactor_animate_bobs_head_and_beak_during_speech() -> None:
    import threading
    import time

    robot = FakeRobot()
    stop = threading.Event()
    worker = threading.Thread(target=SpeechReactor(robot, period=0.01).animate, args=(stop,))
    worker.start()
    time.sleep(0.05)
    stop.set()
    worker.join(timeout=1.0)

    # The talking animation bobs the head (the visible cue in-sim) and works the beak.
    assert any(c.method == "set_head" for c in robot.calls)
    assert any(c.method == "set_mouth" for c in robot.calls)


def test_reactor_animate_stays_within_safe_primitives() -> None:
    import threading
    import time

    robot = FakeRobot()
    stop = threading.Event()
    worker = threading.Thread(target=SpeechReactor(robot, period=0.01).animate, args=(stop,))
    worker.start()
    time.sleep(0.05)
    stop.set()
    worker.join(timeout=1.0)

    # Animation is embodiment, never a navigational/manipulation action.
    assert robot.calls
    assert all(c.method in {"set_head", "set_mouth"} for c in robot.calls)
    assert not any(c.method in {"drive", "do_behavior", "stop"} for c in robot.calls)
