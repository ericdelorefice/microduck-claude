"""microduck-claude: a safe, conversational Claude brain for the Microduck robot.

Claude is the brain (runs on a host); the duck is the body. This package wires a
Claude conversation loop to an allow-listed, confirmation-gated set of tools that
drive a robot behind a single interface (a FakeRobot in Milestone 1; a real
JSON-RPC client later). See docs/PLAN.md and CLAUDE.md.
"""

from __future__ import annotations

__version__ = "0.1.0"
