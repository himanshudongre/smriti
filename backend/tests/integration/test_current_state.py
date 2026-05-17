"""Integration tests for the Project Current State endpoint.

Covers `GET /api/v5/current/spaces/{space_id}` end-to-end through the
FastAPI app with an in-memory SQLite session. No mocking.

- Empty space returns a usable, fully-empty shape
- current_direction is drawn from the latest main checkpoint
- counts aggregate checkpoints / agents / claims / branches / tasks / milestones
- open_tasks_by_intent groups open structured tasks, excludes done tasks
- recent_milestones surfaces milestone notes, newest-first, capped at 5
- recent_activity surfaces recent checkpoints, capped at 8
- attention carries open_question, divergence, and active_work signals
- unknown space returns 404
"""
from __future__ import annotations

import uuid

# ── Helpers (match the shape used in test_multi_branch_state.py) ─────────────


def _create_repo(client, name: str = "Current State Test") -> str:
    r = client.post("/api/v2/repos", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_session(client, repo_id: str, title: str = "test") -> str:
    r = client.post(
        f"/api/v4/chat/spaces/{repo_id}/sessions",
        json={"title": title, "provider": "openrouter", "model": "mock"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _commit(client, repo_id: str, session_id: str, message: str = "checkpoint", **kwargs) -> dict:
    payload = {"repo_id": repo_id, "session_id": session_id, "message": message, **kwargs}
    r = client.post("/api/v4/chat/commit", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _fork(client, space_id: str, checkpoint_id: str, branch_name: str = "") -> dict:
    r = client.post(
        "/api/v5/lineage/sessions/fork",
        json={
            "space_id": space_id,
            "checkpoint_id": checkpoint_id,
            "branch_name": branch_name,
            "provider": "openrouter",
            "model": "mock",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _add_note(
    client, checkpoint_id: str, text: str, kind: str = "note", author: str = "founder"
) -> dict:
    r = client.post(
        f"/api/v5/checkpoint/{checkpoint_id}/notes",
        json={"text": text, "kind": kind, "author": author},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _create_claim(
    client, space_id: str, agent: str, scope: str, intent_type: str = "implement"
) -> dict:
    r = client.post(
        "/api/v5/claims",
        json={"space_id": space_id, "agent": agent, "scope": scope, "intent_type": intent_type},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _get_current(client, space_id: str) -> dict:
    r = client.get(f"/api/v5/current/spaces/{space_id}")
    assert r.status_code == 200, r.text
    return r.json()


# ── Tests ────────────────────────────────────────────────────────────────────


def test_current_empty_space(client):
    """A space with no checkpoints returns a usable, fully-empty payload."""
    repo_id = _create_repo(client, "Empty Current")

    cur = _get_current(client, repo_id)

    assert cur["space_id"] == repo_id
    assert cur["name"] == "Empty Current"
    assert cur["current_direction"]["objective"] is None
    assert cur["current_direction"]["checkpoint_id"] is None
    assert cur["counts"] == {
        "checkpoints": 0,
        "agents": 0,
        "active_claims": 0,
        "active_branches": 0,
        "open_tasks": 0,
        "milestones": 0,
    }
    assert cur["attention"] == []
    assert cur["active_work"] == []
    assert cur["recent_milestones"] == []
    assert cur["open_tasks_by_intent"] == {}
    assert cur["recent_activity"] == []


def test_current_direction_from_latest_main_checkpoint(client):
    """current_direction mirrors the latest main checkpoint."""
    repo_id = _create_repo(client, "Direction")
    session_id = _create_session(client, repo_id)
    commit = _commit(
        client,
        repo_id,
        session_id,
        message="Build the current-state layer",
        objective="Ship Project Current State",
        summary="Backend endpoint plus a UI panel.",
        author_agent="claude-code",
    )

    cur = _get_current(client, repo_id)

    direction = cur["current_direction"]
    assert direction["headline"] == "Build the current-state layer"
    assert direction["objective"] == "Ship Project Current State"
    assert direction["summary"] == "Backend endpoint plus a UI panel."
    assert direction["checkpoint_id"] == commit["id"]
    assert direction["checkpoint_hash"] == commit["commit_hash"]
    assert direction["author_agent"] == "claude-code"
    assert cur["counts"]["checkpoints"] == 1
    assert cur["counts"]["agents"] == 1
    assert len(cur["recent_activity"]) == 1
    assert cur["recent_activity"][0]["message"] == "Build the current-state layer"
    assert cur["recent_activity"][0]["has_milestone"] is False


def test_current_open_tasks_grouped_by_intent(client):
    """open_tasks_by_intent groups open tasks; done tasks are excluded."""
    repo_id = _create_repo(client, "Tasks")
    session_id = _create_session(client, repo_id)
    _commit(
        client,
        repo_id,
        session_id,
        message="Has tasks",
        tasks=[
            {
                "text": "Implement endpoint",
                "intent_hint": "implement",
                "id": "impl-1",
                "status": "open",
            },
            {"text": "Write tests", "intent_hint": "test", "status": "open"},
            {"text": "Update docs", "intent_hint": "docs", "status": "done"},
            {"text": "Unlabelled work", "status": "open"},
        ],
    )

    cur = _get_current(client, repo_id)

    grouped = cur["open_tasks_by_intent"]
    assert set(grouped.keys()) == {"implement", "test", "other"}
    assert "docs" not in grouped  # its only task is done
    assert len(grouped["implement"]) == 1
    assert grouped["implement"][0]["text"] == "Implement endpoint"
    assert grouped["implement"][0]["id"] == "impl-1"
    assert grouped["other"][0]["text"] == "Unlabelled work"
    assert cur["counts"]["open_tasks"] == 3  # done task excluded


def test_current_open_tasks_accept_legacy_intent_type(client):
    """Demo data seeded before intent_hint should still group cleanly."""
    repo_id = _create_repo(client, "Legacy Task Intent")
    session_id = _create_session(client, repo_id)
    _commit(
        client,
        repo_id,
        session_id,
        message="Has legacy task intent",
        tasks=[
            {
                "text": "Implement middleware",
                "intent_type": "implement",
                "id": "middleware",
                "status": "open",
            },
        ],
    )

    cur = _get_current(client, repo_id)

    assert set(cur["open_tasks_by_intent"].keys()) == {"implement"}
    assert cur["open_tasks_by_intent"]["implement"][0]["id"] == "middleware"


def test_current_handles_list_valued_blocked_by(client):
    """Real projects produce tasks whose `blocked_by` is a list of
    dependency labels. The current-state surface must normalize that to a
    display string, not 500 on it (regression: HTTP 500 from a Pydantic
    ValidationError when blocked_by was a list)."""
    repo_id = _create_repo(client, "List Blocked-By")
    session_id = _create_session(client, repo_id)
    _commit(
        client,
        repo_id,
        session_id,
        message="Tasks with varied blocked_by shapes",
        tasks=[
            {
                "text": "Wire the limiter into the gateway",
                "intent_hint": "implement",
                "id": "wire-gateway",
                "status": "open",
                "blocked_by": ["middleware", "load-test"],
            },
            {
                "text": "Single-dependency task",
                "intent_hint": "implement",
                "id": "single-dep",
                "status": "open",
                "blocked_by": "wire-gateway",
            },
        ],
    )

    # Pre-fix, a list-valued blocked_by raised a Pydantic ValidationError
    # and this request 500ed; _get_current asserts a 200.
    cur = _get_current(client, repo_id)

    by_id = {t["id"]: t for t in cur["open_tasks_by_intent"]["implement"]}
    assert by_id["wire-gateway"]["blocked_by"] == "middleware, load-test"
    assert by_id["single-dep"]["blocked_by"] == "wire-gateway"


def test_current_recent_milestones(client):
    """Milestone notes surface in recent_milestones; plain notes do not."""
    repo_id = _create_repo(client, "Milestones")
    session_id = _create_session(client, repo_id)
    commit = _commit(client, repo_id, session_id, message="Proof checkpoint")
    _add_note(client, commit["id"], "First clean autonomous proof", kind="milestone")
    _add_note(client, commit["id"], "just a plain note", kind="note")

    cur = _get_current(client, repo_id)

    assert len(cur["recent_milestones"]) == 1
    ms = cur["recent_milestones"][0]
    assert ms["note"] == "First clean autonomous proof"
    assert ms["checkpoint_hash"] == commit["commit_hash"]
    assert ms["checkpoint_message"] == "Proof checkpoint"
    assert cur["counts"]["milestones"] == 1  # plain note not counted
    assert cur["recent_activity"][0]["has_milestone"] is True


def test_current_attention_open_questions(client):
    """Open questions on the latest checkpoint become open_question signals."""
    repo_id = _create_repo(client, "Questions")
    session_id = _create_session(client, repo_id)
    _commit(
        client,
        repo_id,
        session_id,
        message="Has questions",
        open_questions=["Should state be cached?", "How do we page large spaces?"],
    )

    cur = _get_current(client, repo_id)

    oq = [a for a in cur["attention"] if a["kind"] == "open_question"]
    assert len(oq) == 2
    assert {a["message"] for a in oq} == {
        "Should state be cached?",
        "How do we page large spaces?",
    }
    assert all(a["severity"] == "info" for a in oq)


def test_current_attention_active_work(client):
    """An active claim appears in active_work and as an active_work signal."""
    repo_id = _create_repo(client, "Active Work")
    session_id = _create_session(client, repo_id)
    _commit(client, repo_id, session_id, message="Base")
    _create_claim(client, repo_id, agent="codex-local", scope="Wire the CLI surface")

    cur = _get_current(client, repo_id)

    assert cur["counts"]["active_claims"] == 1
    assert len(cur["active_work"]) == 1
    assert cur["active_work"][0]["agent"] == "codex-local"

    aw = [a for a in cur["attention"] if a["kind"] == "active_work"]
    assert len(aw) == 1
    assert "codex-local" in aw[0]["message"]
    assert "Wire the CLI surface" in aw[0]["message"]


def test_current_attention_divergence(client):
    """A divergent active branch produces a divergence attention signal."""
    repo_id = _create_repo(client, "Divergence")
    session_id = _create_session(client, repo_id)
    base = _commit(
        client,
        repo_id,
        session_id,
        message="Base",
        decisions=["Use Postgres for storage"],
    )

    fork = _fork(client, repo_id, base["id"], branch_name="sqlite-route")
    _commit(
        client,
        repo_id,
        fork["session_id"],
        message="Try SQLite",
        decisions=["Use embedded SQLite only", "Drop the Postgres dependency"],
    )

    cur = _get_current(client, repo_id)

    assert cur["counts"]["active_branches"] == 1
    div = [a for a in cur["attention"] if a["kind"] == "divergence"]
    assert len(div) == 1
    assert div[0]["severity"] == "warn"
    assert "sqlite-route" in div[0]["message"]


def test_current_recent_activity_capped_at_8(client):
    """recent_activity is capped at 8 and ordered newest-first."""
    repo_id = _create_repo(client, "Many Checkpoints")
    session_id = _create_session(client, repo_id)
    for i in range(10):
        _commit(client, repo_id, session_id, message=f"checkpoint-{i:02d}")

    cur = _get_current(client, repo_id)

    assert cur["counts"]["checkpoints"] == 10
    assert len(cur["recent_activity"]) == 8
    timestamps = [e["created_at"] for e in cur["recent_activity"]]
    assert timestamps == sorted(timestamps, reverse=True)  # newest-first


def test_current_recent_milestones_capped_at_5(client):
    """recent_milestones caps at 5 even though counts.milestones is the true total."""
    repo_id = _create_repo(client, "Many Milestones")
    session_id = _create_session(client, repo_id)
    for i in range(6):
        commit = _commit(client, repo_id, session_id, message=f"milestone-cp-{i}")
        _add_note(client, commit["id"], f"Milestone {i}", kind="milestone")

    cur = _get_current(client, repo_id)

    assert len(cur["recent_milestones"]) == 5
    assert cur["counts"]["milestones"] == 6


def test_current_unknown_space_returns_404(client):
    """An unknown space id returns 404."""
    r = client.get(f"/api/v5/current/spaces/{uuid.uuid4()}")
    assert r.status_code == 404
