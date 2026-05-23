"""Integration tests for POST /api/v4/chat/sessions/{id}/title.

Pre-fix behavior: a bare `except Exception: pass` swallowed every failure
(provider not configured, provider call errors, DB errors). The endpoint
always returned 200, and clients could not distinguish "never asked for
a title yet" from "tried and failed because no provider."

Post-fix contract (this file pins it):
  - Endpoint still always returns 200 with the session (chat surface is
    never blocked by title generation).
  - A new response field `title_generation_status` carries a stable
    enum-like value: "ok" | "skipped:provider_not_configured" |
    "skipped:provider_error" | "skipped:db_error".
  - On failure, a single WARNING/ERROR log line is emitted with
    session_id, provider, model, exception type, and message — enough
    to diagnose without leaking secrets.
  - No exception bubbles out of the handler.
"""

import logging
import pytest

from app.config_loader import ProviderNotConfiguredError
from app.providers.base import ProviderAdapter
from app.api.routes import chat as chat_route


# ── helpers (kept inline so this file stands alone) ──────────────────────────


def _create_repo(client, name="Chat Title Test Repo"):
    r = client.post("/api/v2/repos", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_session(client, repo_id, title="default"):
    r = client.post(f"/api/v4/chat/spaces/{repo_id}/sessions", json={
        "title": title, "provider": "openrouter", "model": "mock",
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _send_one_turn(client, session_id, message="Hello world"):
    """Send a single turn via the mock adapter so /title has something to
    summarize. Uses use_mock=True so this fixture requires no provider key."""
    r = client.post("/api/v4/chat/send", json={
        "session_id": session_id,
        "provider": "openrouter",
        "model": "mock",
        "message": message,
        "use_mock": True,
    })
    assert r.status_code == 200, r.text


def _setup_session_with_turns(client, original_title="Original Title"):
    """Create a repo + session + one turn so the title endpoint has input."""
    repo_id = _create_repo(client)
    session_id = _create_session(client, repo_id, title=original_title)
    _send_one_turn(client, session_id, "Let's discuss the refactor plan.")
    return session_id


# ── Fake adapters for monkeypatching get_adapter ─────────────────────────────


class _GoodAdapter(ProviderAdapter):
    """Returns a fixed title string."""
    def __init__(self, title: str = "My Refactor Plan"):
        self._title = title

    def send(self, messages, model, **kwargs):
        return self._title

    def healthcheck(self) -> bool:  # pragma: no cover
        return True


class _ErroringAdapter(ProviderAdapter):
    """Raises on send() — simulates network/API failure."""
    def send(self, messages, model, **kwargs):
        raise RuntimeError("simulated provider failure (no API key in this message)")

    def healthcheck(self) -> bool:  # pragma: no cover
        return True


# ── Success path ─────────────────────────────────────────────────────────────


def test_title_generation_succeeds_with_provider(client, monkeypatch, caplog):
    """When a real provider answers, the title is saved and status == 'ok'.
    No WARNING/ERROR log noise on the happy path."""
    monkeypatch.setattr(chat_route, "get_adapter", lambda p, allow_mock=False: _GoodAdapter("My Refactor Plan"))

    session_id = _setup_session_with_turns(client, original_title="default")

    with caplog.at_level(logging.WARNING, logger="app.api.routes.chat"):
        r = client.post(f"/api/v4/chat/sessions/{session_id}/title")

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["title"] == "My Refactor Plan"
    assert data["title_generation_status"] == "ok"
    # No WARNING/ERROR on happy path
    assert not [rec for rec in caplog.records if rec.levelno >= logging.WARNING]


# ── Failure path — provider not configured (the regression test) ─────────────


def test_title_generation_fails_loud_without_provider(client, monkeypatch, caplog):
    """No provider configured: returns 200 with the session UNCHANGED,
    status == 'skipped:provider_not_configured', and a WARNING log line
    carrying session_id, provider, model, and exception type/message.

    This is the regression test for the bare-except bug: pre-fix, the
    endpoint silently returned the unchanged session with no signal.
    """
    def _raise_not_configured(provider, allow_mock=False):
        raise ProviderNotConfiguredError(
            f"Provider '{provider}' has no API key configured."
        )
    monkeypatch.setattr(chat_route, "get_adapter", _raise_not_configured)

    session_id = _setup_session_with_turns(client, original_title="My Sticky Title")

    with caplog.at_level(logging.WARNING, logger="app.api.routes.chat"):
        r = client.post(f"/api/v4/chat/sessions/{session_id}/title")

    # No exception bubbled — endpoint still returns 200.
    assert r.status_code == 200, r.text
    data = r.json()
    # Title is UNCHANGED (the chat surface is never blocked / corrupted).
    assert data["title"] == "My Sticky Title"
    # Status is the stable enum so the UI can switch on it.
    assert data["title_generation_status"] == "skipped:provider_not_configured"

    # WARNING was logged with enough context to diagnose.
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1, f"expected exactly one WARNING, got {warnings}"
    msg = warnings[0].getMessage()
    assert "session_title" in msg
    assert "provider not configured" in msg
    assert str(session_id) in msg
    assert "ProviderNotConfiguredError" in msg
    # Sanity: no obvious secret leakage patterns (api keys, bearer tokens).
    assert "sk-" not in msg.lower()
    assert "bearer " not in msg.lower()


# ── Failure path — provider call errors ──────────────────────────────────────


def test_title_generation_handles_provider_call_error(client, monkeypatch, caplog):
    """Provider call raises a generic exception (network, 4xx, parse error, etc.):
    returns 200 with the session unchanged, status == 'skipped:provider_error',
    WARNING log line. No exception bubbles."""
    monkeypatch.setattr(chat_route, "get_adapter", lambda p, allow_mock=False: _ErroringAdapter())

    session_id = _setup_session_with_turns(client, original_title="My Sticky Title")

    with caplog.at_level(logging.WARNING, logger="app.api.routes.chat"):
        r = client.post(f"/api/v4/chat/sessions/{session_id}/title")

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["title"] == "My Sticky Title"
    assert data["title_generation_status"] == "skipped:provider_error"

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    msg = warnings[0].getMessage()
    assert "provider call failed" in msg
    assert "RuntimeError" in msg
    assert str(session_id) in msg


# ── Pre-condition preserved: no turns is still a 400 ─────────────────────────


def test_title_endpoint_400_when_no_turns(client):
    """Session with zero turns still returns 400 (genuine error, not silent).
    The new typed-except code path must not accidentally turn this into a 200."""
    repo_id = _create_repo(client)
    session_id = _create_session(client, repo_id)
    # Intentionally no turns

    r = client.post(f"/api/v4/chat/sessions/{session_id}/title")
    assert r.status_code == 400, r.text


# ── Other endpoints that return SessionResponse are unaffected ───────────────


def test_other_session_endpoints_omit_title_generation_status(client):
    """The new field defaults to None on every endpoint that returns
    SessionResponse other than /title. Pinned so we never accidentally leak
    a stale status from a previous call."""
    repo_id = _create_repo(client)
    session_id = _create_session(client, repo_id)
    r = client.get(f"/api/v4/chat/sessions/{session_id}")
    assert r.status_code == 200, r.text
    data = r.json()
    # Field is present (additive) but null for non-title endpoints.
    assert data.get("title_generation_status") is None
