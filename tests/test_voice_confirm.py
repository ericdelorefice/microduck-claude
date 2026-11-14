from __future__ import annotations

from microduck_claude.voice import VoiceConfirmer
from tests.fakes import FakeSTT, FakeTTS


def test_spoken_yes_confirms() -> None:
    tts = FakeTTS()
    assert VoiceConfirmer(FakeSTT(["yes"]), tts).confirm("Do the thing?") is True
    assert any("Do the thing?" in line for line in tts.spoken)  # the prompt was spoken


def test_spoken_no_and_silence_decline() -> None:
    assert VoiceConfirmer(FakeSTT(["no"]), FakeTTS()).confirm("X?") is False
    assert VoiceConfirmer(FakeSTT(["maybe later"]), FakeTTS()).confirm("X?") is False
    assert VoiceConfirmer(FakeSTT([]), FakeTTS()).confirm("X?") is False  # silence -> no


def test_only_the_spoken_answer_decides_not_the_prompt() -> None:
    # The prompt literally contains "yes", but the spoken answer "no" must win:
    # confirmation comes only from the live mic, never from the prompt/model text.
    assert VoiceConfirmer(FakeSTT(["no"]), FakeTTS()).confirm("Say yes to continue?") is False


def test_prompt_echo_is_not_a_self_confirmation() -> None:
    # The mic picking up the duck's own "...answer yes or no" prompt must NOT confirm:
    # it contains a negation, so it is heard as a decline (fail-safe).
    assert VoiceConfirmer(FakeSTT(["yes or no"]), FakeTTS()).confirm("Do it?") is False


def test_affirmations_confirm_and_negations_decline() -> None:
    for yes in ("yes", "sure", "okay", "go ahead", "do it"):
        assert VoiceConfirmer(FakeSTT([yes]), FakeTTS()).confirm("Do it?") is True
    for no in ("no", "nope", "cancel", "yes but no"):  # any negation wins, even mixed with 'yes'
        assert VoiceConfirmer(FakeSTT([no]), FakeTTS()).confirm("Do it?") is False


def test_hedged_answers_are_not_a_yes() -> None:
    # Each of these contains an affirmative word ("sure", "okay", "yes") but is not a yes;
    # a locomotion confirmation must not go through on "I'm not sure".
    for hedge in ("I'm not sure", "not now, okay?", "sure, not yet", "okay wait", "yes, maybe"):
        assert VoiceConfirmer(FakeSTT([hedge]), FakeTTS()).confirm("Turn?") is False, hedge
    for contraction in ("I can't say yes", "okay, I won't", "that isn\u2019t okay"):
        assert VoiceConfirmer(FakeSTT([contraction]), FakeTTS()).confirm("Turn?") is False


def test_a_hedged_answer_does_not_move_the_duck() -> None:
    from microduck_claude.assembly import build_registry
    from microduck_claude.robot import FakeRobot
    from microduck_claude.safety import Dispatcher, Outcome

    robot = FakeRobot()
    confirmer = VoiceConfirmer(FakeSTT(["I'm not sure"]), FakeTTS())
    result = Dispatcher(build_registry(robot), confirmer).dispatch("turn", {"degrees": 90})
    assert result.outcome is Outcome.DECLINED_BY_USER
    assert not [c for c in robot.calls if c.method == "drive"]
