from __future__ import annotations

from pathlib import Path

from microduck_claude.assembly import build_registry
from microduck_claude.memory import MemoryStore, build_memory_tools
from microduck_claude.robot import FakeRobot
from microduck_claude.safety import CallbackConfirmer, Dispatcher, Outcome


def test_store_add_list_remove_clear(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "mem.json")
    assert store.all() == []
    store.add("my name is Pat")
    store.add("I like jazz")
    assert store.all() == ["my name is Pat", "I like jazz"]
    assert store.remove_matching("jazz") == 1
    assert store.all() == ["my name is Pat"]
    store.clear()
    assert store.all() == []


def test_store_tolerates_missing_and_bad_file(tmp_path: Path) -> None:
    assert MemoryStore(tmp_path / "nope.json").all() == []
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    assert MemoryStore(bad).all() == []


def test_memory_tools_recall_remember_forget(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "m.json")
    tools = {t.name: t for t in build_memory_tools(store)}
    assert set(tools) == {"recall_memories", "remember", "forget"}
    assert tools["remember"].run({"note": "likes tea"}).ok
    assert "likes tea" in store.all()
    assert "likes tea" in tools["recall_memories"].run({}).content
    tools["forget"].run({"about": "tea"})
    assert store.all() == []


def test_memory_writes_are_gated_but_recall_is_free(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "m.json")
    registry = build_registry(FakeRobot(), memory=store)
    assert "recall_memories" in registry
    assert "remember" in registry

    # 'remember' is an ACTION: blocked without confirmation, nothing written.
    declining = Dispatcher(registry, CallbackConfirmer(lambda _p: False))
    result = declining.dispatch("remember", {"note": "secret"})
    assert result.outcome is Outcome.DECLINED_BY_USER
    assert store.all() == []

    # 'recall_memories' is read-only: runs without a confirmation.
    assert declining.dispatch("recall_memories", {}).outcome is Outcome.EXECUTED


def test_forget_is_confirmed_even_under_trust(tmp_path: Path) -> None:
    # 'forget' is destructive and irreversible, so it must be confirmed even under trust
    # (CLAUDE.md guardrail #4) — unlike the benign, trust-covered memory actions.
    store = MemoryStore(tmp_path / "m.json")
    store.add("the user likes tea")
    registry = build_registry(FakeRobot(), memory=store)
    forget = registry.get("forget")
    assert forget is not None
    assert getattr(forget, "confirm_always", False) is True

    trusting_but_declining = Dispatcher(registry, CallbackConfirmer(lambda _p: False), trust=True)
    result = trusting_but_declining.dispatch("forget", {"about": "tea"})
    assert result.outcome is Outcome.DECLINED_BY_USER  # trust did not skip the prompt
    assert store.all() == ["the user likes tea"]  # nothing was deleted
