"""Runtime configuration, read from the environment.

The Anthropic API key is deliberately NOT represented here. The SDK reads
``ANTHROPIC_API_KEY`` from the environment itself; this project never stores, logs,
or asks for it (see CLAUDE.md guardrail #2).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .robot.protocol import API_VERSION, DEFAULT_SIM_SOCKET

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_MAX_TOKENS = 4096


@dataclass(frozen=True)
class Config:
    llm_provider: str = "anthropic"  # "anthropic" (default) | "openai"
    model: str = DEFAULT_MODEL
    max_tokens: int = DEFAULT_MAX_TOKENS
    persona: str = "duckling"
    memory_path: str = "~/.microduck-claude/memory.json"
    robot_backend: str = "fake"  # "fake" (in-process) | "rpc" (real duck-sim / robot)
    robot_socket: str = DEFAULT_SIM_SOCKET
    api_version: int = API_VERSION
    voice_output: str = "host"  # "host" (Mac speaker) | "duck" (speak through the duck via SSH)
    duck_ssh_host: str = ""
    duck_audio_device: str = "plughw:aic3104"
    duck_ssh_user: str = "microduck"
    voice_input: str = "stdin"  # "stdin" (typed) | "mic" (microphone STT; needs the [voice] extra)
    stt_model: str = "base.en"

    @classmethod
    def from_env(cls) -> Config:
        provider = os.environ.get("MICRODUCK_LLM_PROVIDER", "anthropic").lower()
        default_model = DEFAULT_MODEL if provider == "anthropic" else "llama3.2"
        model = (
            os.environ.get("MICRODUCK_MODEL")
            or os.environ.get("MICRODUCK_CLAUDE_MODEL")
            or default_model
        )
        return cls(
            llm_provider=provider,
            model=model,
            max_tokens=_int_env("MICRODUCK_CLAUDE_MAX_TOKENS", DEFAULT_MAX_TOKENS),
            persona=os.environ.get("MICRODUCK_PERSONA", "duckling").lower(),
            memory_path=os.environ.get("MICRODUCK_MEMORY_PATH", "~/.microduck-claude/memory.json"),
            robot_backend=os.environ.get("MICRODUCK_ROBOT_BACKEND", "fake").lower(),
            robot_socket=os.environ.get("MICRODUCK_ROBOT_SOCKET", DEFAULT_SIM_SOCKET),
            api_version=_int_env("MICRODUCK_API_VERSION", API_VERSION),
            voice_output=os.environ.get("MICRODUCK_VOICE_OUTPUT", "host").lower(),
            duck_ssh_host=os.environ.get("MICRODUCK_DUCK_SSH_HOST", ""),
            duck_audio_device=os.environ.get("MICRODUCK_DUCK_AUDIO_DEVICE", "plughw:aic3104"),
            duck_ssh_user=os.environ.get("MICRODUCK_DUCK_SSH_USER", "microduck"),
            voice_input=os.environ.get("MICRODUCK_VOICE_INPUT", "stdin").lower(),
            stt_model=os.environ.get("MICRODUCK_STT_MODEL", "base.en"),
        )


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default
