# microduck-claude

A safe, conversational **Claude brain** for the Pollen Robotics × Hugging Face **Microduck** robot.
Claude is the brain (it runs on your Mac or a server); the duck is the body. You talk to it, Claude
converses and performs a small set of **allow-listed, confirmation-gated** tasks, and the duck's
movement and expressions match.

> **Unofficial community project.** Not affiliated with, authorized, or endorsed by Pollen Robotics or
> Hugging Face. "Microduck" is their product name; this project only *talks to* the robot's open
> (Apache-2.0) software interface and vendors none of their code.

Microduck ships as an action / reinforcement-learning robot with **no built-in voice or LLM** — this
project adds the conversational layer on top, in the style of Pollen's Reachy Mini. See
[`docs/PLAN.md`](docs/PLAN.md) for the full design and research (with sources and licenses) and
[`CLAUDE.md`](CLAUDE.md) for the engineering guardrails.

## Status

- **Milestone 1 (done):** text chat → Claude → head/body gestures on an in-process `FakeRobot`, with a
  fully tested safety layer. No hardware or simulator required.
- **Milestone 2 (done):** `RpcRobot` drives a real **`duck-sim`** (or robot) over Microduck's
  `duck-ipc-proto` **JSON-RPC 2.0 / NDJSON Unix-socket** contract — a drop-in for `FakeRobot`. Verified
  end-to-end over a real socket against a faithful fake server; validate against a running `duck-sim`
  or hardware when available.
- **Milestone 3 (done):** a host **voice loop** — swappable STT/TTS, the duck reacting with motion +
  chirps, and spoken yes/no action confirmation. `microduck-claude voice` runs it on the fake duck today
  (type to "speak", hear replies via macOS `say`); a **real on-device microphone backend** (faster-whisper)
  is available via the `[voice]` extra with `MICRODUCK_VOICE_INPUT=mic`.
- **Playground (done):** `microduck-claude playground` opens a local web page that visualizes the fake
  duck live (head, beak, pose, chirps) with a chat box and gesture-preview buttons — a hardware-free
  test area, no robot required.
- **Multiple models (done):** the brain runs on any model behind a provider-neutral `LLM` interface —
  Claude via the official SDK (default), or any OpenAI-compatible server (OpenAI, or local models via
  Ollama) with `MICRODUCK_LLM_PROVIDER=openai`.
- **Expression, memory & persona (done):** 23 gestures incl. emotions; a local long-term memory
  (`remember` / `recall` / `forget`, writes gated); and persona profiles (`MICRODUCK_PERSONA`).
- **Speak through the duck (scaffolded):** `MICRODUCK_VOICE_OUTPUT=duck` renders TTS on the host and
  plays it on the duck's speaker over SSH (`SshDuckTTS`); the command path is tested, pending validation
  on a real board.
- **Next / roadmap:** validate the SSH audio path + mic-in STT on hardware, and full hardware bring-up —
  see [`docs/PLAN.md`](docs/PLAN.md) §7.

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

`uv` works too and is the Pollen-ecosystem standard (`uv venv && uv pip install -e ".[dev]"`); it is not
required for this project.

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

This starts a text chat with the duck. The default **`fake`** backend needs no hardware — gestures run
against an in-process robot and are printed as stage directions:

```
🦆  Talk to your Microduck (backend=fake). Ctrl-D to quit.

you › hey, can you look to your left?
duck › Sure thing! Peeking left now. 👀
      🦆 tilts its head
you › do a little celebration
duck › 🦆  The duck will perform the gesture 'dance'. Allow it? [y/N] y
duck › Ta-da!
      🦆 shifts its body, *wheee*
```

Read-only requests (the time, the gesture list, status) run freely; **any action is previewed and only
runs after you confirm it**.

### Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Claude API key (env only). Or run `ant auth login` instead; Max/Team API credits cover usage. See **Models & credentials**. |
| `MICRODUCK_LLM_PROVIDER` | `anthropic` | `anthropic` (Claude) or `openai` (OpenAI-compatible server). |
| `MICRODUCK_MODEL` | provider default | Model name (`claude-opus-5-5`, or e.g. `llama3.2` for Ollama). |
| `MICRODUCK_OPENAI_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible endpoint (Ollama by default). |
| `MICRODUCK_CLAUDE_MODEL` | `claude-opus-5-5` | (Legacy) Claude model; `MICRODUCK_MODEL` overrides it. |
| `MICRODUCK_PERSONA` | `duckling` | Personality: `duckling`, `zen`, `scholar`, `grumpy`. |
| `MICRODUCK_MEMORY_PATH` | `~/.microduck-claude/memory.json` | Where the duck stores what it remembers (local, never committed). |
| `MICRODUCK_VOICE_OUTPUT` | `host` | `host` (Mac speaker) or `duck` (speak through the duck via SSH). |
| `MICRODUCK_DUCK_SSH_HOST` | — | Duck's SSH host for `voice_output=duck` (auth via your own SSH keys). |
| `MICRODUCK_DUCK_AUDIO_DEVICE` | `plughw:aic3104` | Duck ALSA device (`default` on the beta board). |
| `MICRODUCK_VOICE_INPUT` | `stdin` | `stdin` (typed) or `mic` (microphone STT; needs `pip install '.[voice]'`). |
| `MICRODUCK_STT_MODEL` | `base.en` | faster-whisper model for mic STT (e.g. `small.en`, `base`). |
| `MICRODUCK_BARGE_IN` | `off` | Interrupt the duck mid-reply (host `say` + mic; experimental). |
| `MICRODUCK_CLAUDE_MAX_TOKENS` | `4096` | Max response tokens. |
| `MICRODUCK_ROBOT_BACKEND` | `fake` | `fake` (in-process) or `rpc` (real duck-sim / robot). |
| `MICRODUCK_ROBOT_SOCKET` | `~/.cache/duck-sim/duck-a.sock` | Unix socket for the `rpc` backend. |
| `MICRODUCK_API_VERSION` | `44` | `duck-ipc-proto` handshake version. |

### Voice mode

```bash
microduck-claude voice
```

Talk to the duck. By default you type a line as your "speech"; install the voice extra
(`pip install -e '.[voice]'`) and set `MICRODUCK_VOICE_INPUT=mic` for a **real microphone** (on-device
faster-whisper, no cloud). Claude's replies are spoken via the macOS `say` command (or printed if `say`
isn't available), and the duck reacts with motion + chirps. **Actions are confirmed by
a spoken yes/no**, captured from the live mic only — a "yes" in the model's text or a tool result can
never confirm one.

### Playground

```bash
microduck-claude playground
```

Opens a local web page (default `http://127.0.0.1:8777`) that **visualizes the fake duck live** — its
head tilts, its beak opens, and chirps/gestures show as they happen — with a chat box and
gesture-preview buttons. The visualization and gesture preview need **no API key**; the chat box uses
your key if it's set. A hardware-free test area for the whole experience.

### Using other models (Ollama, OpenAI, …)

The brain is provider-neutral. Keep Claude (the default), or point it at any OpenAI-compatible server:

```bash
# Local models via Ollama (no API key):
MICRODUCK_LLM_PROVIDER=openai MICRODUCK_MODEL=llama3.2 microduck-claude chat

# OpenAI:
MICRODUCK_LLM_PROVIDER=openai MICRODUCK_MODEL=gpt-4o-mini \
  MICRODUCK_OPENAI_BASE_URL=https://api.openai.com/v1 OPENAI_API_KEY=sk-... microduck-claude chat
```

This is the **no-subscription, no-Max path** anyone can use: **Ollama** runs fully local and free, and
hosted OpenAI-compatible services with free tiers (e.g. **OpenRouter**, **Groq**) work the same way —
point `MICRODUCK_OPENAI_BASE_URL` at the endpoint and set the key in the env var named by
`MICRODUCK_OPENAI_KEY_ENV` (default `OPENAI_API_KEY`).

Adding another provider means implementing the small `LLM` interface (`brain/llm.py`) — the open core
depends on no provider beyond the Anthropic SDK.

## Driving the real simulator (optional)

The `rpc` backend speaks the same contract the real robot uses, so you can drive Pollen's **local
simulator** on your Mac:

1. Build and run `duck-sim` from [`pollen-robotics/microduck`](https://github.com/pollen-robotics/microduck)
   (a Rust `cargo build` plus a `microduck_rl` MuJoCo environment; the script supports Apple Silicon).
   It binds a control socket at `~/.cache/duck-sim/duck-a.sock`.
2. Point this app at it:

   ```bash
   export MICRODUCK_ROBOT_BACKEND=rpc
   # export MICRODUCK_ROBOT_SOCKET=~/.cache/duck-sim/duck-a.sock   # (default)
   microduck-claude chat
   ```

The same `RpcRobot` reaches a physical robot over an `ssh -L` forwarded socket. See
[`docs/PLAN.md`](docs/PLAN.md) §2–§7 for the contract details and the hardware roadmap.

## Giving the duck a voice (planned)

The JSON-RPC API only exposes a fixed voice-bank (`robot.sound`), but the robot plays audio via `aplay`
on a Linux board you can SSH into — so host-rendered TTS can be streamed to its speaker (and its mic
captured for STT) without firmware changes. This is a planned milestone with on-hardware validation;
details and caveats are in [`docs/PLAN.md`](docs/PLAN.md) §2.4.

## Safety

Safety is built in, not bolted on (see [`docs/PLAN.md`](docs/PLAN.md) §6 and [`CLAUDE.md`](CLAUDE.md)):
allow-listed tools, **read-only by default**, an explicit **confirmation gate** before any action, and
everything the robot hears or reads treated as **untrusted input** (prompt injection). A "yes" produced
by the model, or found inside tool output, never counts as your confirmation.

## Development

```bash
pytest                               # no API key needed; the Anthropic client is mocked
ruff check . && ruff format --check .
mypy
```

CI (GitHub Actions) runs lint + type-check + tests on Python 3.10–3.12 with **no API key**.

## Contributing

Issues and PRs are welcome; the maintainer reviews and merges. Keep anything personal or private in your
own separate package — the open core discovers optional tools through the
`microduck_claude.tool_providers` entry-point group and depends on none of them.

## License

[Apache-2.0](LICENSE). Copyright the microduck-claude Authors. This project interoperates with the
Apache-2.0 Microduck software; it does not include Pollen Robotics' code or hardware designs.
