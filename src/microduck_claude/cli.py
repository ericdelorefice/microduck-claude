"""`microduck-claude chat` (text), `voice` (host voice loop), `playground` (web)."""

from __future__ import annotations

import importlib.util
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
    BargeInController,
    FasterWhisperSTT,
    InterruptibleSayTTS,
    MacSayTTS,
    MacSayWavRenderer,
    MicSpeechDetector,
    PrintTTS,
    SpeechReactor,
    SpeechToText,
    SshDuckAudio,
    SshDuckTTS,
    SshTarget,
    StdinSTT,
    TextToSpeech,
    VoiceConfirmer,
    VoiceLoop,
    pick_say_voice,
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
    # Hold each gesture step briefly on a real body (the sim) so motion is visible;
    # the in-process FakeRobot stays instant.
    gesture_pace = 0.35 if config.robot_backend == "rpc" else 0.0
    registry = build_registry(
        robot, memory=memory, gesture_pace=gesture_pace, camera_url=config.camera_url
    )
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


def _mic_stt_available() -> bool:
    return all(
        importlib.util.find_spec(mod) is not None
        for mod in ("faster_whisper", "sounddevice", "numpy")
    )


def _audio_capture_available() -> bool:
    return all(importlib.util.find_spec(mod) is not None for mod in ("sounddevice", "numpy"))


def _build_voice_stt(config: Config) -> tuple[SpeechToText, str]:
    """Pick the voice input: typed stdin (default), or the microphone (needs [voice])."""
    if config.voice_input == "mic":
        if _mic_stt_available():
            return FasterWhisperSTT(model_size=config.stt_model), "mic:faster-whisper"
        print(
            "(mic STT needs the voice extra — `pip install -e '.[voice]'`; using typed input)",
            file=sys.stderr,
        )
    return StdinSTT(), "stdin"


def _build_voice_tts(config: Config) -> tuple[TextToSpeech, str, str]:
    """Pick the voice output: the Mac speaker, or (validate-on-hardware) the duck.

    Returns the TTS, a short kind label, and the resolved macOS ``say`` voice (empty if
    none) so barge-in can speak in the same voice.
    """
    if config.voice_output == "duck" and config.duck_ssh_host:
        target = SshTarget(config.duck_ssh_host, config.duck_audio_device, config.duck_ssh_user)
        tts = SshDuckTTS(MacSayWavRenderer(), SshDuckAudio(target))
        return tts, f"duck@{config.duck_ssh_host}", ""
    if MacSayTTS.available():
        voice = config.say_voice or pick_say_voice() or ""
        label = f"say:{voice}" if voice else "say"
        return MacSayTTS(voice=voice or None), label, voice
    return PrintTTS(), "print", ""


def _build_barge_in(config: Config, tts_kind: str, voice: str) -> BargeInController | None:
    if not config.barge_in:
        return None
    if not tts_kind.startswith("say"):
        print("(barge-in needs host 'say' audio output; disabled)", file=sys.stderr)
        return None
    if not _audio_capture_available():
        print("(barge-in needs the voice extra for mic capture; disabled)", file=sys.stderr)
        return None
    return BargeInController(InterruptibleSayTTS(voice=voice or None), MicSpeechDetector())


def _run_voice(
    llm: LLM, robot: RobotInterface, registry: ToolRegistry, system: str, config: Config
) -> None:
    stt, stt_kind = _build_voice_stt(config)
    tts, tts_kind, voice = _build_voice_tts(config)
    barge_in = _build_barge_in(config, tts_kind, voice)
    dispatcher = Dispatcher(registry, VoiceConfirmer(stt, tts))
    brain = Brain(llm, registry, dispatcher, system=system)
    reactor = SpeechReactor(robot)

    how = "Speak into your mic" if stt_kind.startswith("mic") else "Speak by typing a line"
    extra = " · barge-in on" if barge_in is not None else ""
    print(
        f"🦆  Voice mode (in={stt_kind}, out={tts_kind}, model={config.model}, "
        f"persona={config.persona}{extra}). {how}; Ctrl-D to quit.\n"
    )
    VoiceLoop(brain, stt, tts, reactor, barge_in=barge_in).run()


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
