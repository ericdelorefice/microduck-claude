"""`microduck-claude chat` (text), `voice` (host voice loop), `playground` (web)."""

from __future__ import annotations

import os
import sys
import webbrowser

from .assembly import build_registry
from .brain import LLM, Brain, MissingAPIKeyError, build_llm, system_prompt_for
from .config import Config
from .memory import MemoryStore
from .playground import PlaygroundApp, build_server
from .robot import FakeRobot, JsonRpcError, RobotCall, RobotInterface, build_robot
from .safety import Dispatcher
from .tools import ToolRegistry
from .voice import (
    MacSayTTS,
    MacSayWavRenderer,
    PrintTTS,
    SpeechReactor,
    SshDuckAudio,
    SshDuckTTS,
    SshTarget,
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
        llm = build_llm(config)
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

    memory = MemoryStore(config.memory_path)
    registry = build_registry(robot, memory=memory)
    system = system_prompt_for(config.persona)
    try:
        if voice:
            _run_voice(llm, robot, registry, system, config)
        else:
            _run_chat(llm, robot, registry, system, config)
    finally:
        close = getattr(robot, "close", None)
        if callable(close):
            close()
    return 0


def _run_chat(
    llm: LLM, robot: RobotInterface, registry: ToolRegistry, system: str, config: Config
) -> None:
    dispatcher = Dispatcher(registry, ConsoleConfirmer())
    brain = Brain(llm, registry, dispatcher, system=system)
    fake = robot if isinstance(robot, FakeRobot) else None

    print(
        f"🦆  Talk to your Microduck (backend={config.robot_backend}, "
        f"model={config.model}, persona={config.persona}). Ctrl-D to quit.\n"
    )
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
            print(f"(error talking to the model: {exc})", file=sys.stderr)
            continue

        for text in turn.texts:
            print(f"duck › {text}")
        if turn.refused and not turn.texts:
            print("duck › (declined to respond)")
        if fake is not None:
            summary = _summarize(fake.calls[before:])
            if summary:
                print(f"      🦆 {summary}")


def _build_voice_tts(config: Config) -> tuple[TextToSpeech, str]:
    """Pick the voice output: the Mac speaker, or (validate-on-hardware) the duck."""
    if config.voice_output == "duck" and config.duck_ssh_host:
        target = SshTarget(config.duck_ssh_host, config.duck_audio_device, config.duck_ssh_user)
        return SshDuckTTS(MacSayWavRenderer(), SshDuckAudio(target)), f"duck@{config.duck_ssh_host}"
    if MacSayTTS.available():
        return MacSayTTS(), "say"
    return PrintTTS(), "print"


def _run_voice(
    llm: LLM, robot: RobotInterface, registry: ToolRegistry, system: str, config: Config
) -> None:
    stt = StdinSTT()
    tts, tts_kind = _build_voice_tts(config)
    dispatcher = Dispatcher(registry, VoiceConfirmer(stt, tts))
    brain = Brain(llm, registry, dispatcher, system=system)
    reactor = SpeechReactor(robot)

    print(
        f"🦆  Voice mode (backend={config.robot_backend}, tts={tts_kind}, "
        f"model={config.model}, persona={config.persona}). Speak by typing a line; "
        "Ctrl-D to quit.\n"
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
    llm: LLM | None
    try:
        llm = build_llm(config)
    except MissingAPIKeyError:
        llm = None
        print("(no ANTHROPIC_API_KEY — chat disabled; gesture preview + visualization still work)")

    app = PlaygroundApp(llm)
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
