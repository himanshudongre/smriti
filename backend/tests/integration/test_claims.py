"""Integration tests for the work claims API.

Covers:
- Create a claim with all fields
- Create a claim with minimal fields (defaults)
- Update claim status to done
- Update claim status to abandoned
- Cannot update a non-active claim
- List active claims (excludes expired)
- List all claims (includes expired/done)
- Claims appear in /state response
- Invalid intent_type rejected
- Claim with nonexistent space rejected
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone


def _create_repo(client, name="Claims Test Repo"):
    r = client.post("/api/v2/repos", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_session(client, repo_id, title="test"):
    r = client.post(
        f"/api/v4/chat/spaces/{repo_id}/sessions",
        json={"title": title, "provider": "openrouter", "model": "mock"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _commit(client, repo_id, session_id, message="checkpoint", **kwargs):
    payload = {"repo_id": repo_id, "session_id": session_id, "message": message, **kwargs}
    r = client.post("/api/v4/chat/commit", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _create_claim(client, space_id, **kwargs):
    payload = {
        "space_id": space_id,
        "agent": kwargs.get("agent", "claude-code"),
        "scope": kwargs.get("scope", "Test scope"),
        "branch_name": kwargs.get("branch_name", "main"),
        "intent_type": kwargs.get("intent_type", "implement"),
        "ttl_hours": kwargs.get("ttl_hours", 4.0),
    }
    if "base_commit_id" in kwargs:
        payload["base_commit_id"] = kwargs["base_commit_id"]
    r = client.post("/api/v5/claims", json=payload)
    return r


# ── Create tests ─────────────────────────────────────────────────────────────


def test_create_claim_full_fields(client):
    repo_id = _create_repo(client, "Claim Full")
    session_id = _create_session(client, repo_id)
    commit = _commit(client, repo_id, session_id, "base")

    r = _create_claim(
        client,
        repo_id,
        agent="claude-code",
        scope="Adding lineage test",
        branch_name="main",
        intent_type="implement",
        base_commit_id=commit["id"],
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["agent"] == "claude-code"
    assert data["scope"] == "Adding lineage test"
    assert data["intent_type"] == "implement"
    assert data["status"] == "active"
    assert data["branch_name"] == "main"
    assert data["base_commit_id"] == commit["id"]
    assert data["id"] is not None
    assert data["claimed_at"] is not None
    assert data["expires_at"] is not None


def test_create_claim_minimal_defaults(client):
    repo_id = _create_repo(client, "Claim Minimal")

    r = _create_claim(client, repo_id, agent="codex-local", scope="Quick fix")
    assert r.status_code == 201
    data = r.json()
    assert data["agent"] == "codex-local"
    assert data["intent_type"] == "implement"  # default
    assert data["branch_name"] == "main"  # default
    assert data["status"] == "active"


def test_create_claim_invalid_intent_type(client):
    repo_id = _create_repo(client, "Claim Bad Intent")

    r = _create_claim(client, repo_id, intent_type="deploy")
    assert r.status_code == 400
    assert "intent_type" in r.json()["detail"].lower()


def test_create_claim_nonexistent_space(client):
    fake_id = str(uuid.uuid4())
    r = _create_claim(client, fake_id, agent="test", scope="test")
    assert r.status_code == 404


# ── Update tests ─────────────────────────────────────────────────────────────


def test_update_claim_done(client):
    repo_id = _create_repo(client, "Claim Done")
    r = _create_claim(client, repo_id)
    claim_id = r.json()["id"]

    r2 = client.patch(f"/api/v5/claims/{claim_id}", json={"status": "done"})
    assert r2.status_code == 200
    assert r2.json()["status"] == "done"


def test_update_claim_abandoned(client):
    repo_id = _create_repo(client, "Claim Abandon")
    r = _create_claim(client, repo_id)
    claim_id = r.json()["id"]

    r2 = client.patch(f"/api/v5/claims/{claim_id}", json={"status": "abandoned"})
    assert r2.status_code == 200
    assert r2.json()["status"] == "abandoned"


def test_cannot_update_non_active_claim(client):
    repo_id = _create_repo(client, "Claim Double Update")
    r = _create_claim(client, repo_id)
    claim_id = r.json()["id"]

    client.patch(f"/api/v5/claims/{claim_id}", json={"status": "done"})
    r2 = client.patch(f"/api/v5/claims/{claim_id}", json={"status": "abandoned"})
    assert r2.status_code == 409


def test_update_invalid_status(client):
    repo_id = _create_repo(client, "Claim Bad Status")
    r = _create_claim(client, repo_id)
    claim_id = r.json()["id"]

    r2 = client.patch(f"/api/v5/claims/{claim_id}", json={"status": "paused"})
    assert r2.status_code == 400


# ── List tests ───────────────────────────────────────────────────────────────


def test_list_active_claims(client):
    repo_id = _create_repo(client, "Claim List")
    _create_claim(client, repo_id, agent="a1", scope="Task A")
    _create_claim(client, repo_id, agent="a2", scope="Task B")

    r = client.get(f"/api/v5/claims?space_id={repo_id}")
    assert r.status_code == 200
    claims = r.json()
    assert len(claims) == 2
    agents = {c["agent"] for c in claims}
    assert agents == {"a1", "a2"}


def test_list_excludes_done_by_default(client):
    repo_id = _create_repo(client, "Claim List Done")
    r1 = _create_claim(client, repo_id, agent="a1", scope="Done task")
    claim_id = r1.json()["id"]
    client.patch(f"/api/v5/claims/{claim_id}", json={"status": "done"})
    _create_claim(client, repo_id, agent="a2", scope="Active task")

    r = client.get(f"/api/v5/claims?space_id={repo_id}")
    claims = r.json()
    assert len(claims) == 1
    assert claims[0]["agent"] == "a2"


def test_list_all_includes_done(client):
    repo_id = _create_repo(client, "Claim List All")
    r1 = _create_claim(client, repo_id, agent="a1", scope="Done task")
    claim_id = r1.json()["id"]
    client.patch(f"/api/v5/claims/{claim_id}", json={"status": "done"})
    _create_claim(client, repo_id, agent="a2", scope="Active task")

    r = client.get(f"/api/v5/claims?space_id={repo_id}&include_expired=true")
    claims = r.json()
    assert len(claims) == 2


# ── State integration test ───────────────────────────────────────────────────


def test_active_claims_appear_in_state(client):
    """Active claims should surface in the /state response."""
    repo_id = _create_repo(client, "Claim State")
    session_id = _create_session(client, repo_id)
    _commit(client, repo_id, session_id, "base")
    _create_claim(
        client, repo_id,
        agent="claude-code",
        scope="Building work claims feature",
        intent_type="implement",
    )

    r = client.get(f"/api/v4/chat/spaces/{repo_id}/state")
    assert r.status_code == 200
    state = r.json()
    assert len(state["active_claims"]) == 1
    claim = state["active_claims"][0]
    assert claim["agent"] == "claude-code"
    assert claim["scope"] == "Building work claims feature"
    assert claim["intent_type"] == "implement"
