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
- **Explores** — a bounded `explore` roam: it creeps forward on its own, pausing to look, then reports
  what it found (an action, behind the confirm / trust gate; the movement is slow and short).
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
- A model backend. The default is **Claude** (needs Anthropic credentials — see **Models & credentials**
  below), or run a **free local model** with no key at all. Credentials are read **only** from your
  environment — never asked for, stored, or logged.

## Setup

```bash
git clone <your-fork-url> microduck-claude && cd microduck-claude
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

`uv` works too (`uv venv && uv pip install -e ".[dev]"`).

## Models & credentials

The brain runs on a swappable backend. Credentials — when a backend needs them — are read **only** from
your environment and are never asked for, stored, or logged.

**Claude (the default).** Authenticate to the Claude **Console (API)** either way:

```bash
export ANTHROPIC_API_KEY=sk-ant-...        # a static key, or…
# …a key-free browser login instead:  brew install anthropics/tap/ant && ant auth login
```

Paying for Claude:

- **Max / Team plans include monthly API credits that cover the Claude API** — **$200/mo on Max 20x,
  $100/mo on Max 5x**. Claim once (claude.ai → **Settings → Billing → API credits** → link a Console
  organization), create a key in that org, and your calls spend the credits first; **usage is never
  charged to your plan** (requests just pause if you run out). For a hobby duck that is effectively free.
  See Anthropic's [API credits for Max and Team plans](https://platform.claude.com/docs/en/about-claude/api-credits-for-subscribers).
- Otherwise it is **pay-as-you-go API**, which is cheap on a small model — set
  `MICRODUCK_MODEL=claude-haiku-5-5` and a chat turn costs a fraction of a cent.

> A claude.ai **Pro** plan — or **ChatGPT Plus/Pro** — can't fund this app. Consumer subscriptions are
> walled off from API access by both vendors; only Claude **Max/Team** bridge to the API, and only via
> the credits above. No eligible plan? Use the **free local path** (see *Using other models* below).

## Usage

```bash
microduck-claude chat            # after setting up a backend — see Models & credentials
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

### Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Claude API key (env only). Or run `ant auth login` instead; Max/Team API credits cover usage. See **Models & credentials**. |
| `MICRODUCK_LLM_PROVIDER` | `anthropic` | `anthropic` (Claude) or `openai` (OpenAI-compatible server). |
| `MICRODUCK_MODEL` | provider default | Model name (`claude-opus-5-5`, or e.g. `llama3.2` for Ollama). |
| `MICRODUCK_CLAUDE_MODEL` | `claude-opus-5-5` | (Legacy) Claude model; `MICRODUCK_MODEL` overrides it. |
| `MICRODUCK_CLAUDE_MAX_TOKENS` | `4096` | Max response tokens. |
| `MICRODUCK_OPENAI_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible endpoint (Ollama by default). |
| `MICRODUCK_OPENAI_KEY_ENV` | `OPENAI_API_KEY` | Env var holding the OpenAI-compatible server's key. |
| `MICRODUCK_PERSONA` | `duckling` | `duckling`, `zen`, `scholar`, `grumpy`, `narrator`. |
| `MICRODUCK_MEMORY_PATH` | `~/.microduck-claude/memory.json` | Where the duck stores what it remembers (local, never committed). |
| `MICRODUCK_TRUST` | `off` | Standing OK for actions (skips the per-action prompt; consequential actions still confirm). |
| `MICRODUCK_VOICE_OUTPUT` | `host` | `host` (Mac `say`), `duck` (through the duck via SSH), or `elevenlabs` (cloud neural). |
| `MICRODUCK_SAY_VOICE` | — | macOS `say` voice (e.g. `Daniel`); empty = auto-pick a working one. |
| `MICRODUCK_SAY_RATE` | `0` | macOS `say` words-per-minute (0 = system default; ~165 reads narrator-ish). |
| `ELEVENLABS_API_KEY` | — | ElevenLabs API key (env only; for `voice_output=elevenlabs`). |
| `MICRODUCK_ELEVENLABS_VOICE` | — | ElevenLabs voice id (for `voice_output=elevenlabs`). |
| `MICRODUCK_ELEVENLABS_MODEL` | `eleven_multilingual_v2` | ElevenLabs model id. |
| `MICRODUCK_VOICE_INPUT` | `stdin` | `stdin` (typed) or `mic` (microphone STT; needs `pip install '.[voice]'`). |
| `MICRODUCK_STT_MODEL` | `base.en` | faster-whisper model for mic STT (e.g. `small.en`, `base`). |
| `MICRODUCK_BARGE_IN` | `off` | Interrupt the duck mid-reply (host `say` + mic; experimental). |
| `MICRODUCK_DUCK_SSH_HOST` | — | Duck's SSH host for `voice_output=duck` (auth via your own SSH keys). |
| `MICRODUCK_DUCK_SSH_USER` | `microduck` | SSH user for the duck. |
| `MICRODUCK_DUCK_AUDIO_DEVICE` | `plughw:aic3104` | Duck ALSA device (`default` on the beta board). |
| `MICRODUCK_ROBOT_BACKEND` | `fake` | `fake` (in-process) or `rpc` (real duck-sim / robot). |
| `MICRODUCK_ROBOT_SOCKET` | `~/.cache/duck-sim/duck-a.sock` | Unix socket for the `rpc` backend. |
| `MICRODUCK_CAMERA_URL` | `http://127.0.0.1:8080/frame` | Camera snapshot endpoint for the vision tools (`see` / `look_around`). |
| `MICRODUCK_EXPLORE_ALLOW_RPC` | `off` | Allow autonomous `explore` on the `rpc` backend (confirm it is the sim, not a real body). |
| `MICRODUCK_API_VERSION` | `44` | `duck-ipc-proto` handshake version. |
| `MICRODUCK_PLAYGROUND_PORT` | `8777` | Port for `microduck-claude playground`. |

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

For a studio-grade narrator voice, set `MICRODUCK_VOICE_OUTPUT=elevenlabs` with `ELEVENLABS_API_KEY`
(from your env) and `MICRODUCK_ELEVENLABS_VOICE=<voice id>` — a rich neural voice via
[ElevenLabs](https://elevenlabs.io) (optional, cloud-based; the core stays on offline `say`). Grab a
British-narrator voice id from your ElevenLabs Voice Library.

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

This is the **no-subscription, no-Max path** anyone can use: **Ollama** runs fully local and free, and
hosted OpenAI-compatible services with free tiers (e.g. **OpenRouter**, **Groq**) work the same way —
point `MICRODUCK_OPENAI_BASE_URL` at the endpoint and set the key in the env var named by
`MICRODUCK_OPENAI_KEY_ENV` (default `OPENAI_API_KEY`).

Adding another provider means implementing the small `LLM` interface
([`brain/llm.py`](src/microduck_claude/brain/llm.py)); the open core depends on no provider beyond the
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

## Safety

Safety is built in, not bolted on (see [`docs/PLAN.md`](docs/PLAN.md) §6 and [`CLAUDE.md`](CLAUDE.md)):
allow-listed tools, **read-only by default**, a **confirmation gate** before any action — or a standing
**trust mode** (`MICRODUCK_TRUST`) you switch on to skip the per-action prompt for safe actions — and
everything the robot hears, reads, or sees treated as **untrusted input** (prompt injection). A "yes"
produced by the model or found in tool output never counts as your confirmation, and nothing the duck
hears, reads, or sees can enable trust mode. A consequential action (e.g. free locomotion) is confirmed
even under trust.

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
