"""Integration tests for POST /api/v5/checkpoint/extract.

Post launch-blocker fix (provider-extract-safety):

  - The DEFAULT path (no `use_mock` flag) requires a real configured
    background provider. If none is configured, the endpoint returns
    HTTP 412 with a structured `provider_not_configured` detail. It
    never silently falls back to MockAdapter — that would pollute a
    real user's reasoning state with placeholder content.

  - The EXPLICIT mock path (`use_mock=True`) still works for tests
    and demos. It always returns the canned MockAdapter response.

These tests pin both contracts.
"""

import json
import pytest

from app.config_loader import ProviderNotConfiguredError
from app.providers.base import ProviderAdapter
from app.providers import registry as provider_registry
from app.api.routes import checkpoint as checkpoint_route


def _sample_markdown() -> str:
    return """# Design: envdiff CLI

## Objective
Build a stdlib-only CLI that compares two .env files.

## Decisions
- Use argparse, not click
- Single file, not a package

## Assumptions
- Python 3.11+ is available

```python
def main():
    print("hello")
```
"""


# ── Explicit mock path: use_mock=True ─────────────────────────────────────────


def test_extract_happy_path_with_mock(client):
    """use_mock=True: MockAdapter returns canned content, 200 OK."""
    r = client.post(
        "/api/v5/checkpoint/extract",
        json={"content": _sample_markdown(), "use_mock": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # MockAdapter JSON mode returns the canned _MOCK_JSON_RESPONSE in
    # registry.py — these are the exact values defined there.
    assert data["title"] == "Mock Checkpoint"
    assert data["summary"].startswith("Mock summary")
    assert "Mock decision from provider" in data["decisions"]
    assert "Mock assumption from provider" in data["assumptions"]
    # Tasks are now structured objects; a plain string from the mock
    # becomes {"text": "Mock task from provider"}.
    assert any(
        (t.get("text") if isinstance(t, dict) else t) == "Mock task from provider"
        for t in data["tasks"]
    )
    assert "Mock open question from provider" in data["open_questions"]
    assert "MockEntity" in data["entities"]
    assert len(data["artifacts"]) == 1
    assert data["artifacts"][0]["label"] == "Mock artifact"
    # Echo fields must mark this as mock so callers can refuse to commit.
    assert data["provider"] == "mock"
    assert data["model"] == "mock"


# ── Default path without provider: must fail loud (the launch-blocker fix) ───


def test_extract_without_provider_fails_loud(client, monkeypatch):
    """Default path (no use_mock) + no real provider configured: HTTP 412 with
    a structured 'provider_not_configured' detail. Never silent mock.

    This is the regression test for the launch-blocker bug where the extract
    endpoint silently returned MockAdapter content like
    "Mock decision from provider" when no provider was configured.
    """
    # Force the provider-not-configured state regardless of test-env API keys.
    def _raise_not_configured(provider: str, allow_mock: bool = False):
        # The endpoint must call with allow_mock=False (no silent fallback).
        assert allow_mock is False, (
            "extract endpoint must call get_adapter with allow_mock=False"
        )
        raise ProviderNotConfiguredError(f"no API key for {provider}")

    monkeypatch.setattr(checkpoint_route, "get_adapter", _raise_not_configured)

    r = client.post(
        "/api/v5/checkpoint/extract",
        json={"content": _sample_markdown()},
    )
    assert r.status_code == 412, r.text
    detail = r.json().get("detail")
    assert isinstance(detail, dict), f"detail must be a structured dict, got {type(detail)}"
    assert detail.get("error") == "provider_not_configured"
    assert "not configured" in detail.get("message", "").lower()
    assert detail.get("provider")  # backend echoes which provider it tried
    assert isinstance(detail.get("fix"), list)
    assert len(detail["fix"]) >= 3, "fix list should enumerate at least 3 paths"
    # CRITICAL: response body must NOT contain mock content. The bug we are
    # fixing literally returned "Mock decision from provider" in the response.
    body_text = r.text
    assert "Mock decision from provider" not in body_text
    assert "Mock Checkpoint" not in body_text


# ── Default path with a real provider: provider/model echoed ─────────────────


class _FakeAdapter(ProviderAdapter):
    """Test double for a real provider — returns valid JSON shaped like a
    real extraction so we can verify the endpoint's success-path metadata."""

    def send(self, messages, model, **kwargs):
        return json.dumps({
            "title": "Real Extraction Result",
            "objective": "Build envdiff CLI.",
            "summary": "A short summary of the design doc.",
            "decisions": ["Use argparse, not click"],
            "assumptions": ["Python 3.11+ is available"],
            "tasks": [{"id": "impl-1", "text": "Scaffold the CLI"}],
            "open_questions": [],
            "entities": ["envdiff"],
            "artifacts": [],
        })

    def healthcheck(self) -> bool:  # pragma: no cover
        return True


def test_extract_with_provider_echoes_provider_and_model(client, monkeypatch):
    """Default path + a real (faked) provider: 200 OK, response echoes
    `provider` and `model` so the CLI can show 'extracted via openai/gpt-4o-mini'
    on commit and refuse to persist mock content."""
    def _fake_adapter(provider: str, allow_mock: bool = False):
        return _FakeAdapter()

    monkeypatch.setattr(checkpoint_route, "get_adapter", _fake_adapter)

    r = client.post(
        "/api/v5/checkpoint/extract",
        json={"content": _sample_markdown()},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["title"] == "Real Extraction Result"
    # Echo: must be the configured provider/model, NOT "mock".
    assert data["provider"] != "mock", "real-provider path must not echo provider=mock"
    assert data["provider"] != ""
    assert data["model"] != "mock"
    assert data["model"] != ""


# ── Validation tests (unchanged) ─────────────────────────────────────────────


def test_extract_rejects_empty_content(client):
    """Empty content is a 422 validation error."""
    r = client.post(
        "/api/v5/checkpoint/extract",
        json={"content": "   "},
    )
    assert r.status_code == 422, r.text


def test_extract_rejects_oversized_content(client):
    """Content exceeding 200000 character cap is a 422 validation error."""
    r = client.post(
        "/api/v5/checkpoint/extract",
        json={"content": "x" * 300_000},
    )
    assert r.status_code == 422, r.text
