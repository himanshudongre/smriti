"""Integration tests for GET /api/v5/metrics/spaces/{space_id}.

Tests the computed-on-demand project metrics endpoint. All data derives
from existing tables — checkpoints, claims, sessions. No new schema.
"""
from __future__ import annotations

import uuid


def _create_repo(client, name="Metrics Test"):
    r = client.post("/api/v2/repos", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_session(client, repo_id, branch="main"):
    r = client.post(f"/api/v4/chat/spaces/{repo_id}/sessions", json={
        "title": "test", "provider": "openrouter", "model": "mock",
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _commit(client, repo_id, session_id, message="cp", **kwargs):
    payload = {"repo_id": repo_id, "session_id": session_id, "message": message, **kwargs}
    r = client.post("/api/v4/chat/commit", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _claim(client, space_id, agent="test-agent", scope="test", **kwargs):
    payload = {
        "space_id": space_id, "agent": agent, "scope": scope,
        "intent_type": kwargs.get("intent_type", "implement"),
        "ttl_hours": 4.0,
    }
    if "task_id" in kwargs:
        payload["task_id"] = kwargs["task_id"]
    r = client.post("/api/v5/claims", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


# ── Basic endpoint tests ─────────────────────────────────────────────────


def test_metrics_empty_space(client):
    """Metrics for a space with no checkpoints returns zero counts."""
    repo_id = _create_repo(client, "Metrics Empty")
    r = client.get(f"/api/v5/metrics/spaces/{repo_id}")
    assert r.status_code == 200
    data = r.json()

    assert data["space_name"] == "Metrics Empty"
    assert data["coordination"]["total_checkpoints"] == 0
    assert data["coordination"]["unique_agents"] == 0
    assert data["coordination"]["total_claims"] == 0
    assert data["state_quality"]["avg_decisions_per_checkpoint"] == 0.0
    assert data["branches"]["active"] == 0


def test_metrics_nonexistent_space(client):
    """Metrics for a nonexistent space returns 404."""
    fake_id = str(uuid.uuid4())
    r = client.get(f"/api/v5/metrics/spaces/{fake_id}")
    assert r.status_code == 404


def test_metrics_with_checkpoints(client):
    """Metrics correctly count checkpoints and agent distribution."""
    repo_id = _create_repo(client, "Metrics Checkpoints")
    sid = _create_session(client, repo_id)

    c1 = _commit(client, repo_id, sid, "first",
                 decisions=["Decision A"], author_agent="claude-code")
    c2 = _commit(client, repo_id, sid, "second",
                 decisions=["Decision B", "Decision C"],
                 tasks=[{"text": "Task 1", "intent_hint": "implement"}],
                 author_agent="codex-local",
                 parent_commit_id=c1["id"])

    r = client.get(f"/api/v5/metrics/spaces/{repo_id}")
    data = r.json()

    assert data["coordination"]["total_checkpoints"] == 2
    assert data["coordination"]["unique_agents"] == 2
    assert data["coordination"]["agent_checkpoints"]["claude-code"] == 1
    assert data["coordination"]["agent_checkpoints"]["codex-local"] == 1
    assert data["state_quality"]["avg_decisions_per_checkpoint"] == 1.5
    assert data["state_quality"]["checkpoints_with_structured_tasks"] == 1


def test_metrics_cross_agent_continuations(client):
    """Cross-agent continuations counted when author_agent changes in parent chain."""
    repo_id = _create_repo(client, "Metrics Cross Agent")
    sid = _create_session(client, repo_id)

    c1 = _commit(client, repo_id, sid, "by-claude", author_agent="claude-code")
    c2 = _commit(client, repo_id, sid, "by-codex", author_agent="codex-local",
                 parent_commit_id=c1["id"])
    c3 = _commit(client, repo_id, sid, "by-claude-again", author_agent="claude-code",
                 parent_commit_id=c2["id"])

    r = client.get(f"/api/v5/metrics/spaces/{repo_id}")
    data = r.json()

    # c1→c2 is a continuation (claude→codex), c2→c3 is another (codex→claude)
    assert data["coordination"]["cross_agent_continuations"] == 2


def test_metrics_claim_stats(client):
    """Claim metrics: completion rate, task_id count."""
    repo_id = _create_repo(client, "Metrics Claims")

    cl1 = _claim(client, repo_id, agent="a1", scope="Task A", task_id="t1")
    cl2 = _claim(client, repo_id, agent="a2", scope="Task B")
    cl3 = _claim(client, repo_id, agent="a3", scope="Task C")

    # Mark cl1 done, cl3 abandoned
    client.patch(f"/api/v5/claims/{cl1['id']}", json={"status": "done"})
    client.patch(f"/api/v5/claims/{cl3['id']}", json={"status": "abandoned"})

    r = client.get(f"/api/v5/metrics/spaces/{repo_id}")
    data = r.json()

    assert data["coordination"]["total_claims"] == 3
    assert data["coordination"]["claims_done"] == 1
    assert data["coordination"]["claims_abandoned"] == 1
    assert data["coordination"]["claims_with_task_id"] == 1
    # Completion rate: 1 done / (1 done + 1 abandoned) = 0.5
    assert data["coordination"]["claim_completion_rate"] == 0.5


def test_metrics_structured_tasks_and_ids(client):
    """State quality: structured tasks and task IDs counted correctly."""
    repo_id = _create_repo(client, "Metrics Tasks")
    sid = _create_session(client, repo_id)

    _commit(client, repo_id, sid, "plain tasks",
            tasks=["plain string task"])
    _commit(client, repo_id, sid, "structured",
            tasks=[{"text": "Task", "intent_hint": "implement"}])
    _commit(client, repo_id, sid, "with ids",
            tasks=[{"text": "Task", "id": "t1", "intent_hint": "test"}])

    r = client.get(f"/api/v5/metrics/spaces/{repo_id}")
    data = r.json()

    assert data["state_quality"]["checkpoints_with_structured_tasks"] == 2
    assert data["state_quality"]["checkpoints_with_task_ids"] == 1


def test_metrics_response_shape(client):
    """Response has all expected top-level keys."""
    repo_id = _create_repo(client, "Metrics Shape")
    r = client.get(f"/api/v5/metrics/spaces/{repo_id}")
    data = r.json()

    assert "space_id" in data
    assert "space_name" in data
    assert "computed_at" in data
    assert "coordination" in data
    assert "state_quality" in data
    assert "branches" in data
