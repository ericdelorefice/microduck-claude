"""`microduck-claude chat` — a text REPL that drives the FakeRobot."""

from __future__ import annotations

import sys

from .assembly import build_registry
from .brain import SYSTEM_PROMPT, Brain, BrainConfig, MissingAPIKeyError, build_client
from .config import Config
from .robot import FakeRobot, RobotCall
from .safety import Dispatcher


class ConsoleConfirmer:
    """Reads confirmation from the user via stdin — the user channel.

    A 'yes' produced by the model, or found inside tool output, cannot reach this
    prompt, so it cannot authorise an action.
    """

    def confirm(self, prompt: str) -> bool:
        try:
            answer = input(f"🦆  {prompt} [y/N] ").strip().lower()
        except EOFError:
            return False
        return answer in {"y", "yes"}


_VERBS = {
    "set_head": "tilts its head",
    "look_at": "looks over",
    "set_pose": "shifts its body",
    "set_mouth": "opens its beak",
    "drive": "scoots about",
    "stop": "settles",
}


def _summarize(calls: list[RobotCall]) -> str:
    """Render recent robot calls as a short, readable stage direction."""
    parts: list[str] = []
    for call in calls:
        if call.method == "play_sound":
            parts.append(f"*{call.kwargs.get('tag')}*")
        elif call.method == "do_behavior":
            parts.append(f"does {call.kwargs.get('skill')}")
        else:
            parts.append(_VERBS.get(call.method, call.method))
    deduped: list[str] = []
    for part in parts:
        if not deduped or deduped[-1] != part:
            deduped.append(part)
    return ", ".join(deduped)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if list(args) != ["chat"]:
        print("usage: microduck-claude chat", file=sys.stderr)
        return 2

    config = Config.from_env()
    robot = FakeRobot()
    registry = build_registry(robot)
    dispatcher = Dispatcher(registry, ConsoleConfirmer())

    try:
        client = build_client()
    except MissingAPIKeyError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    brain = Brain(
        client,
        registry,
        dispatcher,
        system=SYSTEM_PROMPT,
        config=BrainConfig(model=config.model, max_tokens=config.max_tokens),
    )

    print("🦆  Talk to your Microduck. Ctrl-D to quit.\n")
    while True:
        try:
            user = input("you › ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user:
            continue

        before = len(robot.calls)
        try:
            turn = brain.send(user)
        except Exception as exc:  # keep the REPL alive on API/transport errors
            print(f"(error talking to Claude: {exc})", file=sys.stderr)
            continue

        for text in turn.texts:
            print(f"duck › {text}")
        if turn.refused and not turn.texts:
            print("duck › (declined to respond)")
        summary = _summarize(robot.calls[before:])
        if summary:
            print(f"      🦆 {summary}")

    return 0
