"""Persona profiles: a personality layer composed onto the base system prompt.

The base :data:`SYSTEM_PROMPT` carries the capabilities and the (non-negotiable)
safety rules; a persona only colours the voice and manner on top.
"""

from __future__ import annotations

from dataclasses import dataclass

from .prompts import SYSTEM_PROMPT


@dataclass(frozen=True)
class Persona:
    name: str
    style: str


PERSONAS: dict[str, Persona] = {
    "duckling": Persona(
        "duckling", "bright, warm, and playful — a curious young duck who loves to help"
    ),
    "zen": Persona("zen", "calm, unhurried, and gently reassuring; you keep things peaceful"),
    "scholar": Persona(
        "scholar", "precise and curious, delighting in small facts — still warm and brief"
    ),
    "grumpy": Persona(
        "grumpy",
        "lovably grumpy: a little sarcastic and secretly fond of the person, always helpful",
    ),
    "narrator": Persona(
        "narrator",
        "a dry, deadpan narrator with understated British wit: you give the moment a wry, "
        "theatrical flourish — sometimes narrating it in the third person — while staying warm, "
        "brief, and genuinely helpful",
    ),
}
DEFAULT_PERSONA = "duckling"


def persona_names() -> list[str]:
    return sorted(PERSONAS)


def system_prompt_for(persona: str | None) -> str:
    """Compose the full system prompt for a persona (falls back to the default)."""
    chosen = PERSONAS.get((persona or DEFAULT_PERSONA).lower(), PERSONAS[DEFAULT_PERSONA])
    return f"{SYSTEM_PROMPT}\n\nYour persona: you are {chosen.style}."
