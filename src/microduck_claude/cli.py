"""`microduck-claude chat` (text) and `microduck-claude voice` (host voice loop)."""

from __future__ import annotations

import os
import sys
import webbrowser
from typing import Any

from .assembly import build_registry
from .brain import SYSTEM_PROMPT, Brain, BrainConfig, MissingAPIKeyError, build_client
from .config import Config
from .playground import PlaygroundApp, build_server
from .robot import FakeRobot, JsonRpcError, RobotCall, RobotInterface, build_robot
from .safety import Dispatcher
from .tools import ToolRegistry
from .voice import (
    MacSayTTS,
    PrintTTS,
    SpeechReactor,
    StdinSTT,
    TextToSpeech,
    VoiceConfirmer,
    VoiceLoop,
)


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
    args = sys.argv[1:] if argv is None else list(argv)
    if args == ["chat"]:
        return _run(voice=False)
    if args == ["voice"]:
        return _run(voice=True)
    if args == ["playground"]:
        return _run_playground()
    print("usage: microduck-claude {chat|voice|playground}", file=sys.stderr)
    return 2


def _run(*, voice: bool) -> int:
    config = Config.from_env()

    try:
        client = build_client()
    except MissingAPIKeyError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    try:
        robot = build_robot(
            config.robot_backend,
            socket_path=config.robot_socket,
            api_version=config.api_version,
        )
    except (OSError, JsonRpcError) as exc:
        print(
            f"could not connect to the duck (backend={config.robot_backend}): {exc}",
            file=sys.stderr,
        )
        return 1

    registry = build_registry(robot)
    brain_config = BrainConfig(model=config.model, max_tokens=config.max_tokens)
    try:
        if voice:
            _run_voice(client, robot, registry, brain_config, config)
        else:
            _run_chat(client, robot, registry, brain_config, config)
    finally:
        close = getattr(robot, "close", None)
        if callable(close):
            close()
    return 0


def _run_chat(
    client: Any,
    robot: RobotInterface,
    registry: ToolRegistry,
    brain_config: BrainConfig,
    config: Config,
) -> None:
    dispatcher = Dispatcher(registry, ConsoleConfirmer())
    brain = Brain(client, registry, dispatcher, system=SYSTEM_PROMPT, config=brain_config)
    fake = robot if isinstance(robot, FakeRobot) else None

    print(f"🦆  Talk to your Microduck (backend={config.robot_backend}). Ctrl-D to quit.\n")
    while True:
        try:
            user = input("you › ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user:
            continue

        before = len(fake.calls) if fake is not None else 0
        try:
            turn = brain.send(user)
        except Exception as exc:  # keep the REPL alive on API/transport errors
            print(f"(error talking to Claude: {exc})", file=sys.stderr)
            continue

        for text in turn.texts:
            print(f"duck › {text}")
        if turn.refused and not turn.texts:
            print("duck › (declined to respond)")
        if fake is not None:
            summary = _summarize(fake.calls[before:])
            if summary:
                print(f"      🦆 {summary}")


def _run_voice(
    client: Any,
    robot: RobotInterface,
    registry: ToolRegistry,
    brain_config: BrainConfig,
    config: Config,
) -> None:
    stt = StdinSTT()
    tts: TextToSpeech = MacSayTTS() if MacSayTTS.available() else PrintTTS()
    dispatcher = Dispatcher(registry, VoiceConfirmer(stt, tts))
    brain = Brain(client, registry, dispatcher, system=SYSTEM_PROMPT, config=brain_config)
    reactor = SpeechReactor(robot)

    tts_kind = "say" if MacSayTTS.available() else "print"
    print(
        f"🦆  Voice mode (backend={config.robot_backend}, tts={tts_kind}). "
        "Speak by typing a line; Ctrl-D to quit.\n"
    )
    VoiceLoop(brain, stt, tts, reactor).run()


def _playground_port() -> int:
    raw = os.environ.get("MICRODUCK_PLAYGROUND_PORT", "8777")
    try:
        return int(raw)
    except ValueError:
        return 8777


def _run_playground() -> int:
    config = Config.from_env()
    client: Any | None
    try:
        client = build_client()
    except MissingAPIKeyError:
        client = None
        print("(no ANTHROPIC_API_KEY — chat disabled; gesture preview + visualization still work)")

    app = PlaygroundApp(
        client,
        brain_config=BrainConfig(model=config.model, max_tokens=config.max_tokens),
    )
    port = _playground_port()
    try:
        server = build_server(app, port=port)
    except OSError as exc:
        print(f"could not start playground on port {port}: {exc}", file=sys.stderr)
        return 1

    url = f"http://127.0.0.1:{port}/"
    print(f"🦆  Playground running at {url}  (Ctrl-C to stop)")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping…")
    finally:
        server.shutdown()
    return 0
