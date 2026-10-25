from __future__ import annotations

import anthropic
import pytest

from microduck_claude.brain import MissingCredentialsError, build_client
from microduck_claude.brain.client import _credentials_available


class _StubClient:
    """Mimics a constructed ``anthropic.Anthropic`` with the attributes we inspect."""

    def __init__(self, *, api_key: str | None = None, auth_token: str | None = None) -> None:
        self.api_key = api_key
        self.auth_token = auth_token


def _patch_anthropic(monkeypatch: pytest.MonkeyPatch, client: object) -> None:
    monkeypatch.setattr(anthropic, "Anthropic", lambda: client)


def _patch_probe(monkeypatch: pytest.MonkeyPatch, *, available: bool) -> None:
    import anthropic._client as ac

    monkeypatch.setattr(ac, "_has_auto_discoverable_credentials", lambda: available)


def test_build_client_returns_client_with_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = _StubClient(api_key="sk-ant-test")
    _patch_anthropic(monkeypatch, stub)
    assert build_client() is stub


def test_build_client_accepts_auto_discovered_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    # No static key/token, but an `ant auth login` profile is discoverable.
    stub = _StubClient()
    _patch_anthropic(monkeypatch, stub)
    _patch_probe(monkeypatch, available=True)
    assert build_client() is stub


def test_build_client_raises_without_any_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = _StubClient()
    _patch_anthropic(monkeypatch, stub)
    _patch_probe(monkeypatch, available=False)
    with pytest.raises(MissingCredentialsError):
        build_client()


def test_build_client_wraps_construction_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # A configured-but-broken profile makes the SDK raise at construction; we surface a
    # MissingCredentialsError (with guidance) rather than an unhandled traceback.
    def _raise() -> object:
        raise anthropic.CredentialsError("profile 'default' not found")

    monkeypatch.setattr(anthropic, "Anthropic", _raise)
    with pytest.raises(MissingCredentialsError):
        build_client()


def test_credentials_available_short_circuits_on_static_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A static key is enough on its own; the auto-discovery probe must not be consulted.
    import anthropic._client as ac

    def _boom() -> bool:
        raise AssertionError("probe should not run when a static key is present")

    monkeypatch.setattr(ac, "_has_auto_discoverable_credentials", _boom)
    assert _credentials_available(_StubClient(api_key="sk-ant-test")) is True
