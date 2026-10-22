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


def test_reactor_speaking_moves_the_beak() -> None:
    robot = FakeRobot()
    SpeechReactor(robot).on_speaking("hello")
    assert any(c.method == "set_mouth" for c in robot.calls)
