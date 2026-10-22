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
- **Next:** a voice loop (speech-to-text / text-to-speech on the host). The duck can also be made to
  *speak* via SSH — see [Giving the duck a voice](#giving-the-duck-a-voice-planned).

## Requirements

- **Python 3.10+**
- An Anthropic API key exported as **`ANTHROPIC_API_KEY`**. It is read **only** from the environment —
  never asked for, stored, or logged.

## Setup

```bash
git clone <your-fork-url> microduck-claude && cd microduck-claude
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

`uv` works too and is the Pollen-ecosystem standard (`uv venv && uv pip install -e ".[dev]"`); it is not
required for this project.

## Usage

```bash
export ANTHROPIC_API_KEY=...     # you set this; the app never stores it
microduck-claude chat
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
| `ANTHROPIC_API_KEY` | — | Your Anthropic key (required; env only). |
| `MICRODUCK_CLAUDE_MODEL` | `claude-opus-5-5` | Claude model to use. |
| `MICRODUCK_CLAUDE_MAX_TOKENS` | `4096` | Max response tokens. |
| `MICRODUCK_ROBOT_BACKEND` | `fake` | `fake` (in-process) or `rpc` (real duck-sim / robot). |
| `MICRODUCK_ROBOT_SOCKET` | `~/.cache/duck-sim/duck-a.sock` | Unix socket for the `rpc` backend. |
| `MICRODUCK_API_VERSION` | `44` | `duck-ipc-proto` handshake version. |

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
