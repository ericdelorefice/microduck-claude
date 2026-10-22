# microduck-claude

A safe, conversational **Claude brain** for the Pollen Robotics × Hugging Face **Microduck** robot.
Claude runs on your Mac or a server; the duck is the body. You talk to it, Claude converses and performs
a small set of **allow-listed, confirmation-gated** tasks, the duck moves and chirps to match — and it
can now **see through its own camera**.

> **Unofficial community project.** Not affiliated with, authorized, or endorsed by Pollen Robotics or
> Hugging Face. "Microduck" is their product name; this project only *talks to* the robot's open
> (Apache-2.0) software interface and vendors none of their code.

Microduck ships as an action / reinforcement-learning robot with **no built-in voice or LLM** — this
project adds the conversational layer on top, in the style of Pollen's Reachy Mini. Full design,
research, and licenses are in [`docs/PLAN.md`](docs/PLAN.md); engineering guardrails in
[`CLAUDE.md`](CLAUDE.md).

## What it does

- **Talks** — text chat, or a host **voice loop** (type, or a real mic via faster-whisper; replies
  spoken through macOS `say`).
- **Moves** — two dozen head/body **gestures** (including emotional ones), plus the sim's real tricks
  (roulade, kicks); paced so they're actually visible on a real body.
- **Sees** — a `see` tool grabs the duck's camera frame and hands it to Claude as an image, so it can
  describe or react to what's in front of it. [`scripts/duck-cam.html`](scripts/duck-cam.html) shows the
  live feed as a floating "body-cam."
- **Remembers** — a local long-term memory (`remember` / `recall` / `forget`), writes gated.
- **Stays safe** — allow-listed tools, read-only by default, a confirmation gate before any action, and
  everything it hears / reads / sees treated as untrusted.

Runs on the in-process **`fake`** backend (no hardware), a real **`duck-sim`**, or a physical robot —
the same code behind one interface.

## Status

Milestones 1–3 are **done**: a safety-tested text→gesture core on a `FakeRobot`; an `RpcRobot` that
drives a real `duck-sim` / robot over Microduck's `duck-ipc-proto` (JSON-RPC 2.0 / NDJSON Unix socket);
a host voice loop with spoken yes/no confirmation; vision; a hardware-free **playground** web
visualizer; and a provider-neutral brain (Claude by default, or any OpenAI-compatible server). Speaking
*through the duck's own speaker* over SSH is scaffolded and tested, pending on-board validation.
**Next:** validate the SSH-audio and mic-in paths on hardware, and full bring-up — see
[`docs/PLAN.md`](docs/PLAN.md) §7.

## Requirements

- **Python 3.10+**
- An Anthropic API key as **`ANTHROPIC_API_KEY`** — read **only** from the environment; never asked for,
  stored, or logged. (Or run a local model; see *Other models* below.)

## Setup

```bash
git clone <your-fork-url> microduck-claude && cd microduck-claude
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

`uv` works too (`uv venv && uv pip install -e ".[dev]"`).

## Usage

```bash
export ANTHROPIC_API_KEY=...     # you set this; the app never stores it
microduck-claude chat
```

The default **`fake`** backend needs no hardware — gestures run in-process and print as stage
directions:

```
🦆  Talk to your Microduck (backend=fake). Ctrl-D to quit.

you › do a little celebration
duck › 🦆  May I do a little dance? [y/N] y
duck › Ta-da!
      🦆 shifts its body, *wheee*
```

Read-only requests (the time, the gesture list, status, **what it sees**) run freely; **any action is
previewed and only runs after you confirm it**.

### Voice mode

```bash
microduck-claude voice
```

Type a line as your "speech," or install the voice extra (`pip install -e '.[voice]'`) and set
`MICRODUCK_VOICE_INPUT=mic` for a **real microphone** (on-device faster-whisper, no cloud). Replies are
spoken via macOS `say`; the duck reacts with motion + chirps. **Actions are confirmed by a spoken yes/no
from the live mic only** — a "yes" in the model's text or a tool result never counts.

For a dry British-narrator manner, run with `MICRODUCK_PERSONA=narrator` — it pairs well with a
measured `MICRODUCK_SAY_RATE` (e.g. `165`) and an en-GB voice like Daniel or Oliver.

### Vision & the duck-cam

With a camera-enabled `duck-sim` (or robot), ask *"what do you see?"* — the `see` tool captures a frame
and Claude describes it. To watch the feed yourself, open
[`scripts/duck-cam.html`](scripts/duck-cam.html) in a browser: a live "body-cam" that reconnects on its
own, with a **float** button that pins it always-on-top in a corner. It reads `MICRODUCK_CAMERA_URL`
(default the duck-sim `mediad` `/frame` endpoint); run the sim with `DUCK_SIM_CAMERAS=a` to enable the
camera.

### Playground

```bash
microduck-claude playground
```

A local web page (default `http://127.0.0.1:8777`) that **visualizes the fake duck live** — head, beak,
pose, chirps — with a chat box and gesture buttons. The visualization needs no API key; the chat box
uses your key if it's set.

### Other models (Ollama, OpenAI, …)

The brain is provider-neutral — keep Claude (the default) or point it at any OpenAI-compatible server:

```bash
MICRODUCK_LLM_PROVIDER=openai MICRODUCK_MODEL=llama3.2 microduck-claude chat   # local, no key
```

Adding a provider means implementing the small `LLM` interface in
[`brain/llm.py`](src/microduck_claude/brain/llm.py); the open core depends on no provider beyond the
Anthropic SDK. (Vision needs a multimodal model — text-only models simply skip the image.)

### Driving the real simulator

The `rpc` backend speaks the robot's own contract, so it drives Pollen's local **`duck-sim`** on your
Mac:

```bash
export MICRODUCK_ROBOT_BACKEND=rpc      # socket defaults to ~/.cache/duck-sim/duck-a.sock
microduck-claude chat
```

Build/run `duck-sim` from
[`pollen-robotics/microduck`](https://github.com/pollen-robotics/microduck) (a Rust build plus a
`microduck_rl` MuJoCo environment; Apple Silicon supported). The same `RpcRobot` reaches a physical
robot over an `ssh -L` forwarded socket. Contract details and the hardware roadmap are in
[`docs/PLAN.md`](docs/PLAN.md).

### Configuration

| Variable | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Anthropic key (required for the `anthropic` provider; env only). |
| `MICRODUCK_LLM_PROVIDER` | `anthropic` | `anthropic` (Claude) or `openai` (OpenAI-compatible). |
| `MICRODUCK_MODEL` | provider default | Model name (`claude-opus-5-5`, or e.g. `llama3.2`). |
| `MICRODUCK_OPENAI_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible endpoint (Ollama by default). |
| `MICRODUCK_PERSONA` | `duckling` | `duckling`, `zen`, `scholar`, `grumpy`, `narrator`. |
| `MICRODUCK_ROBOT_BACKEND` | `fake` | `fake` (in-process) or `rpc` (real duck-sim / robot). |
| `MICRODUCK_ROBOT_SOCKET` | `~/.cache/duck-sim/duck-a.sock` | Unix socket for the `rpc` backend. |
| `MICRODUCK_CAMERA_URL` | `http://127.0.0.1:8080/frame` | Camera snapshot endpoint for the `see` tool. |
| `MICRODUCK_VOICE_INPUT` | `stdin` | `stdin` (typed) or `mic` (needs the `[voice]` extra). |
| `MICRODUCK_VOICE_OUTPUT` | `host` | `host` (Mac speaker) or `duck` (through the duck via SSH). |

Less-common knobs — `MICRODUCK_PERSONA` detail, `MICRODUCK_MEMORY_PATH`, `MICRODUCK_SAY_VOICE`, `MICRODUCK_SAY_RATE`,
`MICRODUCK_BARGE_IN`, `MICRODUCK_STT_MODEL`, the `MICRODUCK_DUCK_SSH_*` / audio-device settings,
`MICRODUCK_API_VERSION`, `MICRODUCK_CLAUDE_MAX_TOKENS` — are listed in
[`config.py`](src/microduck_claude/config.py).

## Safety

Safety is built in, not bolted on (see [`docs/PLAN.md`](docs/PLAN.md) §6 and [`CLAUDE.md`](CLAUDE.md)):
allow-listed tools, **read-only by default**, an explicit **confirmation gate** before any action, and
everything the robot hears, reads, or sees treated as **untrusted input** (prompt injection). A "yes"
produced by the model, or found inside tool output, never counts as your confirmation.

## Development

```bash
pytest                               # no API key needed; the Anthropic client is mocked
ruff check . && ruff format --check .
mypy
```

CI (GitHub Actions) runs lint + type-check + tests on Python 3.10–3.12 with **no API key**.

## Contributing

Issues and PRs are welcome. Keep anything personal or private in your own separate package — the open
core discovers optional tools through the `microduck_claude.tool_providers` entry-point group and
depends on none of them.

## License

[Apache-2.0](LICENSE). Copyright the microduck-claude Authors. This project interoperates with the
Apache-2.0 Microduck software; it includes none of Pollen Robotics' code or hardware designs.
