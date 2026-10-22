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
    model: str = DEFAULT_MODEL
    max_tokens: int = DEFAULT_MAX_TOKENS
    robot_backend: str = "fake"  # "fake" (in-process) | "rpc" (duck-sim / robot)
    robot_socket: str = DEFAULT_SIM_SOCKET
    api_version: int = API_VERSION

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            model=os.environ.get("MICRODUCK_CLAUDE_MODEL", DEFAULT_MODEL),
            max_tokens=_int_env("MICRODUCK_CLAUDE_MAX_TOKENS", DEFAULT_MAX_TOKENS),
            robot_backend=os.environ.get("MICRODUCK_ROBOT_BACKEND", "fake").lower(),
            robot_socket=os.environ.get("MICRODUCK_ROBOT_SOCKET", DEFAULT_SIM_SOCKET),
            api_version=_int_env("MICRODUCK_API_VERSION", API_VERSION),
        )


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default
