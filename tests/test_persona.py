from __future__ import annotations

from microduck_claude.brain import SYSTEM_PROMPT, persona_names, system_prompt_for


def test_system_prompt_includes_base_and_persona() -> None:
    prompt = system_prompt_for("zen")
    assert SYSTEM_PROMPT in prompt
    assert "calm" in prompt.lower()


def test_unknown_persona_falls_back_to_default() -> None:
    prompt = system_prompt_for("does-not-exist")
    assert SYSTEM_PROMPT in prompt  # still a valid prompt with the default persona


def test_persona_names_nonempty() -> None:
    names = persona_names()
    assert "duckling" in names
    assert len(names) >= 3
