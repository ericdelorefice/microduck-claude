"""Autonomous `explore` mode safety: the sim-backend guard and the bounded roam loop."""

from __future__ import annotations

from microduck_claude.assembly import build_roam_registry
from microduck_claude.cli import _run_explore
from microduck_claude.config import Config
from microduck_claude.robot import FakeRobot
from microduck_claude.tools import ToolRegistry
from tests.fakes import FakeLLM, llm_text


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
    rc = _run_explore(llm, robot, registry, "sys", config)
    assert rc == 0
    assert any(c.method == "stop" for c in robot.calls)  # stopped when the roam ended


def test_explore_allows_rpc_with_opt_in() -> None:
    # With the explicit opt-in the guard passes (the operator has confirmed it is the sim).
    robot = FakeRobot()
    config = Config(robot_backend="rpc", explore_allow_rpc=True)
    llm = FakeLLM([llm_text("Looking around.")] * 15)
    rc = _run_explore(llm, robot, build_roam_registry(robot), "sys", config)
    assert rc == 0
