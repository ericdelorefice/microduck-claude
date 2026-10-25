"""Factory for the official Anthropic client.

Credentials are resolved by the SDK itself and are never asked for, stored, or logged:

* ``ANTHROPIC_API_KEY`` — a static API key, or
* ``ANTHROPIC_AUTH_TOKEN`` / an ``ant auth login`` profile (a browser OAuth login against
  the Claude Console, so there is no static key to manage), or WIF federation.

All of these authenticate to the Claude **Console** and bill as pay-as-you-go API usage. A
static ``ANTHROPIC_API_KEY`` takes precedence over a login, so unset it to use a profile;
``ant auth status`` shows which credential is active.

Note: a claude.ai Pro/Max *subscription* is not a supported credential for SDK apps — that
path exists only inside Claude Code — so this app cannot bill to a subscription.
"""

from __future__ import annotations

from typing import Any

_NO_CREDENTIALS = (
    "No Anthropic credentials found. Set up ONE (both bill as pay-as-you-go API usage):\n"
    "  - run `ant auth login`  (browser login; no static key to manage), then unset\n"
    "    ANTHROPIC_API_KEY, or\n"
    "  - export ANTHROPIC_API_KEY=sk-ant-...\n"
    "`ant auth status` shows which credential is active. Credentials are only read from\n"
    "your environment or login — never stored, logged, or asked for."
)


class MissingCredentialsError(RuntimeError):
    """Raised when the SDK can find no Anthropic credentials (API key or OAuth profile)."""


def build_client() -> Any:
    import anthropic  # lazy import keeps the core import-light and test-friendly

    # The SDK resolves credentials on its own, in order: ANTHROPIC_API_KEY, then
    # ANTHROPIC_AUTH_TOKEN, then an `ant auth login` profile or WIF federation. All
    # authenticate to the Console (API billing). Nothing is stored or logged here.
    try:
        client = anthropic.Anthropic()
    except anthropic.AnthropicError as exc:
        # A credential source is configured but could not be loaded — e.g. ANTHROPIC_PROFILE
        # names a profile you have not logged into. Surface the SDK's reason plus guidance.
        raise MissingCredentialsError(f"{exc}\n\n{_NO_CREDENTIALS}") from exc
    if _credentials_available(client):
        return client
    raise MissingCredentialsError(_NO_CREDENTIALS)


def _credentials_available(client: Any) -> bool:
    """Best-effort: does the SDK have *some* credential to authenticate with?

    The SDK resolves credentials lazily (at the first request), so a client with no
    credential still constructs. We check the static key/token it resolved plus the SDK's
    own probe for an auto-discoverable profile (``ant auth login`` / WIF). If that probe is
    unavailable (SDK internals changed), we don't block — the first request then raises its
    own clear authentication error.
    """
    if getattr(client, "api_key", None) or getattr(client, "auth_token", None):
        return True
    try:
        from anthropic._client import _has_auto_discoverable_credentials
    except Exception:
        return True  # can't probe -> don't falsely block a valid profile
    return bool(_has_auto_discoverable_credentials())
