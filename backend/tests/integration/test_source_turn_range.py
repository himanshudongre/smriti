"""
Integration tests for source turn range tracking.

Verifies that checkpoints record which conversation turns produced them,
and that the source-turns endpoint returns the correct turns.
"""
import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _create_repo(client, name="Turn Range Test Repo"):
    r = client.post("/api/v2/repos", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_session(client, repo_id, title="test session"):
    r = client.post(f"/api/v4/chat/spaces/{repo_id}/sessions", json={
        "title": title, "provider": "openrouter", "model": "mock",
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _send(client, session_id, message="hello"):
    r = client.post("/api/v4/chat/send", json={
        "session_id": session_id,
        "provider": "openrouter",
        "model": "mock",
        "message": message,
        "use_mock": True,
    })
    assert r.status_code == 200, r.text
    return r.json()


def _commit(client, repo_id, session_id, message="checkpoint", **kwargs):
    payload = {
        "repo_id": repo_id,
        "session_id": session_id,
        "message": message,
        **kwargs,
    }
    r = client.post("/api/v4/chat/commit", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


# ── Tests ────────────────────────────────────────────────────────────────────


def test_commit_records_source_turn_range(client):
    """A commit should record the sequence range of all non-system turns in the session."""
    repo_id = _create_repo(client)
    session_id = _create_session(client, repo_id)

    # Send two user messages (each produces a user + assistant turn)
    _send(client, session_id, "first message")
    _send(client, session_id, "second message")

    commit = _commit(client, repo_id, session_id, "checkpoint with turns")

    assert "source_turn_range" in commit
    tr = commit["source_turn_range"]
    assert tr is not None
    assert tr["session_id"] == session_id
    assert tr["first_sequence_number"] == 0
    assert tr["last_sequence_number"] == 3  # 0,1,2,3 (2 user + 2 assistant)
    assert tr["turn_count"] == 4


def test_commit_without_turns_has_no_source_range(client):
    """A commit on a session with no turns should have null source_turn_range."""
    repo_id = _create_repo(client)
    session_id = _create_session(client, repo_id)

    commit = _commit(client, repo_id, session_id, "empty checkpoint")

    assert commit["source_turn_range"] is None


def test_source_turns_endpoint_returns_turns(client):
    """GET /lineage/checkpoints/{id}/source-turns returns the turns that produced it."""
    repo_id = _create_repo(client)
    session_id = _create_session(client, repo_id)

    _send(client, session_id, "design the API")
    _send(client, session_id, "add error handling")

    commit = _commit(client, repo_id, session_id, "API design checkpoint")
    checkpoint_id = commit["id"]

    r = client.get(f"/api/v5/lineage/checkpoints/{checkpoint_id}/source-turns")
    assert r.status_code == 200
    turns = r.json()
    assert len(turns) == 4  # 2 user + 2 assistant
    assert turns[0]["role"] == "user"
    assert turns[0]["content"] == "design the API"
    assert turns[1]["role"] == "assistant"
    assert turns[2]["role"] == "user"
    assert turns[2]["content"] == "add error handling"
    assert turns[3]["role"] == "assistant"

    # Verify chronological order
    for i in range(len(turns) - 1):
        assert turns[i]["sequence_number"] < turns[i + 1]["sequence_number"]


def test_source_turns_endpoint_empty_for_old_checkpoint(client):
    """Checkpoints without source_turn_range metadata return an empty list."""
    repo_id = _create_repo(client)
    session_id = _create_session(client, repo_id)

    # Commit with no turns — no source_turn_range in metadata
    commit = _commit(client, repo_id, session_id, "no turns")
    checkpoint_id = commit["id"]

    r = client.get(f"/api/v5/lineage/checkpoints/{checkpoint_id}/source-turns")
    assert r.status_code == 200
    assert r.json() == []


def test_source_turns_not_found_checkpoint(client):
    """Requesting source turns for a nonexistent checkpoint returns 404."""
    r = client.get("/api/v5/lineage/checkpoints/00000000-0000-0000-0000-000000000099/source-turns")
    assert r.status_code == 404


def test_lineage_includes_source_turn_range(client):
    """The lineage endpoint should include source_turn_range in checkpoint nodes."""
    repo_id = _create_repo(client)
    session_id = _create_session(client, repo_id)

    _send(client, session_id, "hello")
    _commit(client, repo_id, session_id, "first checkpoint")

    r = client.get(f"/api/v5/lineage/spaces/{repo_id}")
    assert r.status_code == 200
    data = r.json()
    assert len(data["checkpoints"]) == 1
    ckpt = data["checkpoints"][0]
    assert "source_turn_range" in ckpt
    assert ckpt["source_turn_range"] is not None
    assert ckpt["source_turn_range"]["turn_count"] == 2  # 1 user + 1 assistant
