# microduck-claude

A safe, conversational **Claude brain** for the Pollen Robotics × Hugging Face **Microduck** robot.
Claude is the brain (it runs on your Mac or a server); the duck is the body. You talk to it, Claude
converses and performs a small set of **allow-listed, confirmation-gated** tasks, and the duck's
movement and expressions match.

> Microduck ships as an action / reinforcement-learning robot with **no built-in voice or LLM** — this
> project adds the conversational layer on top, in the style of Pollen's Reachy Mini. See
> [`docs/PLAN.md`](docs/PLAN.md) for the full design and research (with sources and licenses).

## Status — Milestone 1

Text chat with Claude driving a **simulated** Microduck's head/body gestures, with a fully tested
safety layer. **No hardware or simulator process is required**: gestures run against an in-process
`FakeRobot`. Driving the real `duck-sim` / robot over its JSON-RPC contract is Milestone 2.

## Requirements

- **Python 3.10+**
- An Anthropic API key exported as **`ANTHROPIC_API_KEY`**. The code reads it **only** from the
  environment — it is never asked for, stored, or logged.

## Install

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

`uv` works too and is the Pollen-ecosystem standard (`uv venv && uv pip install -e ".[dev]"`); it isn't
required for this milestone.

## Run

```bash
export ANTHROPIC_API_KEY=...     # you set this; the app never stores it
microduck-claude chat
```

Type to the duck. Claude replies and may request gestures. **Read-only requests run without friction;
any action is previewed and only runs after you confirm it.**

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

## License

[Apache-2.0](LICENSE). This project only *talks to* the Apache-2.0 Microduck runtime over its JSON-RPC
contract; it vendors none of Pollen's code.
