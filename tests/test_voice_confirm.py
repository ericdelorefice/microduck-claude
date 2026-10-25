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
