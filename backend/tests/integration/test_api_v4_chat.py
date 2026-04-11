"""
V4 Chat API integration tests.
All tests use use_mock=True so they run without any real provider API keys.
"""
import pytest


def test_provider_status(client):
    """Providers endpoint returns status dict."""
    resp = client.get("/api/v4/chat/providers")
    assert resp.status_code == 200
    data = resp.json()
    assert {"openai", "anthropic", "openrouter"}.issubset(set(data.keys()))
    for _name, status in data.items():
        assert "enabled" in status
        assert "has_key" in status


def _create_repo(client, name="Chat Test Repo"):
    r = client.post("/api/v2/repos", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_session_lifecycle(client):
    repo_id = _create_repo(client)

    # Create session (no head commit yet)
    s = client.post(f"/api/v4/chat/spaces/{repo_id}/sessions", json={
        "title": "Test session",
        "provider": "openrouter",
        "model": "mock-model",
        "seed_from": "head",
    })
    assert s.status_code == 201, s.text
    session = s.json()
    assert session["repo_id"] == repo_id
    assert session["active_provider"] == "openrouter"
    assert session["seeded_commit_id"] is None   # No head commit exists yet

    session_id = session["id"]

    # Fetch session
    get_s = client.get(f"/api/v4/chat/spaces/{repo_id}/sessions/{session_id}")
    assert get_s.status_code == 200
    assert get_s.json()["id"] == session_id

    # Initially no turns
    turns = client.get(f"/api/v4/chat/spaces/{repo_id}/sessions/{session_id}/turns")
    assert turns.status_code == 200
    assert turns.json() == []


def test_send_message_mock(client):
    repo_id = _create_repo(client, "Send Test Repo")

    s = client.post(f"/api/v4/chat/spaces/{repo_id}/sessions", json={
        "title": "Send test",
        "provider": "openrouter",
        "model": "mock-model",
    })
    session_id = s.json()["id"]

    # Send a message using the mock adapter
    send = client.post("/api/v4/chat/send", json={
        "repo_id": repo_id,
        "session_id": session_id,
        "provider": "openrouter",
        "model": "mock-model",
        "message": "What is the plan?",
        "use_mock": True,
    })
    assert send.status_code == 200, send.text
    resp = send.json()
    assert "reply" in resp
    assert "mock:mock-model" in resp["reply"]
    assert "What is the plan?" in resp["reply"]
    assert resp["turn_count"] == 2   # user + assistant

    # Turns should now exist
    turns = client.get(f"/api/v4/chat/spaces/{repo_id}/sessions/{session_id}/turns")
    assert turns.status_code == 200
    turn_list = turns.json()
    assert len(turn_list) == 2
    assert turn_list[0]["role"] == "user"
    assert turn_list[1]["role"] == "assistant"


def test_model_switch_preserves_history(client):
    """Switching provider/model mid-session keeps prior turns in context."""
    repo_id = _create_repo(client, "Model Switch Repo")

    s = client.post(f"/api/v4/chat/spaces/{repo_id}/sessions", json={
        "provider": "openrouter", "model": "mock-model",
    })
    session_id = s.json()["id"]

    # First turn with mock/openrouter
    client.post("/api/v4/chat/send", json={
        "repo_id": repo_id, "session_id": session_id,
        "provider": "openrouter", "model": "gpt-mock",
        "message": "Turn one", "use_mock": True,
    })

    # Second turn — simulate model switch (different model string)
    send2 = client.post("/api/v4/chat/send", json={
        "repo_id": repo_id, "session_id": session_id,
        "provider": "anthropic", "model": "claude-mock",
        "message": "Turn two, new model", "use_mock": True,
    })
    assert send2.status_code == 200

    # All 4 turns should exist (2 user + 2 assistant)
    turns = client.get(f"/api/v4/chat/spaces/{repo_id}/sessions/{session_id}/turns")
    assert len(turns.json()) == 4

    # Session should reflect latest model
    sess = client.get(f"/api/v4/chat/spaces/{repo_id}/sessions/{session_id}")
    assert sess.json()["active_provider"] == "anthropic"
    assert sess.json()["active_model"] == "claude-mock"


def test_manual_commit_from_session(client):
    repo_id = _create_repo(client, "Commit Session Repo")

    s = client.post(f"/api/v4/chat/spaces/{repo_id}/sessions", json={
        "provider": "openrouter", "model": "mock",
    })
    session_id = s.json()["id"]

    # Chat first
    client.post("/api/v4/chat/send", json={
        "repo_id": repo_id, "session_id": session_id,
        "provider": "openrouter", "model": "mock",
        "message": "We decided to use Postgres", "use_mock": True,
    })

    # Manual commit
    commit_r = client.post("/api/v4/chat/commit", json={
        "repo_id": repo_id,
        "session_id": session_id,
        "message": "Decided on database",
        "summary": "We chose Postgres as our primary DB.",
        "decisions": ["Use Postgres", "No ORM for now"],
        "tasks": ["Set up schema"],
    })
    assert commit_r.status_code == 201, commit_r.text
    commit = commit_r.json()
    assert commit["message"] == "Decided on database"
    assert len(commit["commit_hash"]) == 64


def test_manual_commit_with_project_root_and_author_agent(client):
    """project_root and explicit author_agent round-trip through the V4 commit
    endpoint and are readable via the V2 single-commit GET."""
    repo_id = _create_repo(client, "Metadata Round Trip")
    s = client.post(f"/api/v4/chat/spaces/{repo_id}/sessions", json={
        "provider": "openrouter", "model": "mock",
    })
    session_id = s.json()["id"]

    commit_r = client.post("/api/v4/chat/commit", json={
        "repo_id": repo_id,
        "session_id": session_id,
        "message": "Base",
        "summary": "Setting up.",
        "project_root": "/Users/test/Documents/GitHub/foo",
        "author_agent": "claude-code",
    })
    assert commit_r.status_code == 201, commit_r.text
    commit_id = commit_r.json()["id"]

    # Read back via the V2 single-commit endpoint — this is the canonical
    # path the CLI uses, so asserting here covers the full schema surface.
    get_r = client.get(f"/api/v2/commits/{commit_id}")
    assert get_r.status_code == 200, get_r.text
    payload = get_r.json()
    assert payload["project_root"] == "/Users/test/Documents/GitHub/foo"
    assert payload["author_agent"] == "claude-code"


def test_manual_commit_author_agent_falls_back_to_session_provider(client):
    """When the commit request omits author_agent, the backend falls back
    to the session's active_provider so nothing goes un-tagged."""
    repo_id = _create_repo(client, "Author Fallback")
    s = client.post(f"/api/v4/chat/spaces/{repo_id}/sessions", json={
        "provider": "openrouter", "model": "mock",
    })
    session_id = s.json()["id"]

    commit_r = client.post("/api/v4/chat/commit", json={
        "repo_id": repo_id,
        "session_id": session_id,
        "message": "No explicit author",
    })
    assert commit_r.status_code == 201, commit_r.text
    commit_id = commit_r.json()["id"]

    get_r = client.get(f"/api/v2/commits/{commit_id}")
    assert get_r.status_code == 200, get_r.text
    payload = get_r.json()
    # Session was created with provider=openrouter, so that's the fallback value
    assert payload["author_agent"] == "openrouter"
    assert payload["project_root"] is None


def test_head_endpoint(client):
    repo_id = _create_repo(client, "Head Repo")

    # No session yet
    head = client.get(f"/api/v4/chat/spaces/{repo_id}/head")
    assert head.status_code == 200
    data = head.json()
    assert data["commit_hash"] is None
    assert data["latest_session_id"] is None

    # Create session + commit
    s = client.post(f"/api/v4/chat/spaces/{repo_id}/sessions", json={"provider": "openrouter", "model": "mock"})
    session_id = s.json()["id"]

    client.post("/api/v4/chat/commit", json={
        "repo_id": repo_id, "session_id": session_id,
        "message": "First commit", "objective": "Test head",
    })

    head2 = client.get(f"/api/v4/chat/spaces/{repo_id}/head")
    assert head2.status_code == 200
    data2 = head2.json()
    assert data2["commit_hash"] is not None
    assert data2["objective"] == "Test head"
    assert data2["latest_session_id"] == session_id


def test_session_seeded_from_head(client):
    """Session created after a commit should have seeded_commit_id set."""
    repo_id = _create_repo(client, "Seed Test Repo")

    # Create a session and commit first
    s = client.post(f"/api/v4/chat/spaces/{repo_id}/sessions", json={"provider": "openrouter", "model": "mock"})
    session_id = s.json()["id"]

    commit_r = client.post("/api/v4/chat/commit", json={
        "repo_id": repo_id, "session_id": session_id,
        "message": "Initial state", "summary": "We started here.",
    })
    commit_id = commit_r.json()["id"]

    # Now open a NEW session — should be seeded from the commit
    s2 = client.post(f"/api/v4/chat/spaces/{repo_id}/sessions", json={
        "provider": "openrouter", "model": "mock", "seed_from": "head",
    })
    assert s2.json()["seeded_commit_id"] == commit_id

    # First send should inject seed context (just verify it doesn't crash)
    send = client.post("/api/v4/chat/send", json={
        "repo_id": repo_id, "session_id": s2.json()["id"],
        "provider": "openrouter", "model": "mock",
        "message": "Continue from prior state", "use_mock": True,
    })
    assert send.status_code == 200
