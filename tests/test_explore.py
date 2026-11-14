"""Autonomous `explore` mode safety: the sim-backend guard and the bounded roam loop."""

from __future__ import annotations

from microduck_claude.assembly import build_roam_registry
from microduck_claude.brain import LLMResponse
from microduck_claude.cli import _run_explore
from microduck_claude.config import Config
from microduck_claude.robot import FakeRobot
from microduck_claude.tools import ToolRegistry
from microduck_claude.voice import PrintTTS
from tests.fakes import FakeLLM, FakeTTS, llm_text, llm_tool


def test_explore_refuses_rpc_without_opt_in() -> None:
    # The rpc backend serves both the sim and a real body, so autonomous locomotion there
    # is refused unless the operator explicitly opts in (MICRODUCK_EXPLORE_ALLOW_RPC).
    robot = FakeRobot()
    config = Config(robot_backend="rpc")  # explore_allow_rpc defaults False
    rc = _run_explore(FakeLLM([]), robot, ToolRegistry(), "sys", config)
    assert rc == 1  # refused
    assert robot.calls == []  # the duck never moved


def test_explore_runs_on_the_fake_backend() -> None:
    # The in-process fake body is always sim-safe, so the bounded roam runs and stops cleanly.
    robot = FakeRobot()
    config = Config(robot_backend="fake")
    llm = FakeLLM([llm_text("I look around the gallery.")] * 15)
    registry = build_roam_registry(robot)
    rc = _run_explore(llm, robot, registry, "sys", config, tts=PrintTTS())  # silent: no `say`
    assert rc == 0
    assert any(c.method == "stop" for c in robot.calls)  # stopped when the roam ended


def test_explore_allows_rpc_with_opt_in() -> None:
    # With the explicit opt-in the guard passes (the operator has confirmed it is the sim).
    robot = FakeRobot()
    config = Config(robot_backend="rpc", explore_allow_rpc=True)
    llm = FakeLLM([llm_text("Looking around.")] * 15)
    rc = _run_explore(llm, robot, build_roam_registry(robot), "sys", config, tts=PrintTTS())
    assert rc == 0


def test_explore_narrates_each_line_aloud() -> None:
    # The demo payoff: the duck speaks every observation through the configured voice.
    robot = FakeRobot()
    config = Config(robot_backend="fake")
    tts = FakeTTS()
    llm = FakeLLM([llm_text("That is the Mona Lisa.")] + [llm_text("Moving on.")] * 14)
    rc = _run_explore(llm, robot, build_roam_registry(robot), "sys", config, tts=tts)
    assert rc == 0
    assert tts.spoken[0] == "That is the Mona Lisa."
    assert len(tts.spoken) == 15  # every round's narration was spoken, not just printed


def test_explore_coaxes_narration_when_a_round_is_silent() -> None:
    # A round that moves but says nothing would be silent in the film (only reply text is heard),
    # so the loop nudges the duck for a narrator line before moving on. Round 1 acts then falls
    # silent; the nudge recovers the line. (This is the gap that left the first recording silent.)
    robot = FakeRobot()
    config = Config(robot_backend="fake")
    tts = FakeTTS()
    responses = [
        llm_tool("t1", "explore", {}),  # round 1: the duck acts...
        LLMResponse(),  # ...and says nothing, so the round would be silent
        llm_text("A wall. The duck is unmoved."),  # drawn out by the nudge
    ] + [llm_text("Moving on.")] * 14  # rounds 2-15 narrate directly
    rc = _run_explore(FakeLLM(responses), robot, build_roam_registry(robot), "sys", config, tts=tts)
    assert rc == 0
    assert "A wall. The duck is unmoved." in tts.spoken  # the nudge recovered the missing line
    assert len(tts.spoken) == 15  # one narration per round — none left silent
