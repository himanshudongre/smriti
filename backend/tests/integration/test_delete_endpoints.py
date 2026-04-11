"""
Integration tests for DELETE endpoints across V2 (repos, commits) and V4 (sessions).

Covers cascade correctness, child-commit / forked-session refusal, the cascade
escape hatch, and idempotency. All tests use the SQLite-backed in-memory client
fixture from conftest.py which enables FK enforcement via PRAGMA foreign_keys=ON.
"""
import uuid

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────


def _create_repo(client, name="Delete Test Repo"):
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


def _fork(client, space_id, checkpoint_id, branch_name=""):
    r = client.post("/api/v5/lineage/sessions/fork", json={
        "space_id": space_id,
        "checkpoint_id": checkpoint_id,
        "branch_name": branch_name,
    })
    assert r.status_code == 201, r.text
    return r.json()


# ── 1. Space delete cascades commits ─────────────────────────────────────────


def test_delete_space_cascades_commits(client):
    repo_id = _create_repo(client, "Cascade-1")
    session_id = _create_session(client, repo_id)
    c1 = _commit(client, repo_id, session_id, "first")
    c2 = _commit(client, repo_id, session_id, "second")

    r = client.delete(f"/api/v2/repos/{repo_id}")
    assert r.status_code == 204, r.text

    assert client.get(f"/api/v2/repos/{repo_id}").status_code == 404
    assert client.get(f"/api/v2/commits/{c1['id']}").status_code == 404
    assert client.get(f"/api/v2/commits/{c2['id']}").status_code == 404


# ── 2. Space delete cascades sessions and turns ──────────────────────────────


def test_delete_space_cascades_sessions_and_turns(client):
    repo_id = _create_repo(client, "Cascade-2")
    session_id = _create_session(client, repo_id)
    _send(client, session_id, "hello")
    _send(client, session_id, "world")

    r = client.delete(f"/api/v2/repos/{repo_id}")
    assert r.status_code == 204, r.text

    # The session's turns endpoint should fail because the session itself is gone.
    turns = client.get(f"/api/v4/chat/sessions/{session_id}/turns")
    assert turns.status_code == 404


# ── 3. Space delete rejects cross-user ───────────────────────────────────────


def test_delete_space_cross_user_returns_404(client, db_session):
    from app.db.models import RepoModel

    other_user = uuid.UUID("00000000-0000-0000-0000-0000000000ff")
    repo = RepoModel(user_id=other_user, name="Not mine", description="", metadata_={})
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)
    other_id = str(repo.id)

    r = client.delete(f"/api/v2/repos/{other_id}")
    assert r.status_code == 404


# ── 4. Checkpoint leaf delete succeeds ───────────────────────────────────────


def test_delete_commit_leaf_succeeds(client):
    repo_id = _create_repo(client, "Leaf")
    session_id = _create_session(client, repo_id)
    commit = _commit(client, repo_id, session_id, "solo")

    r = client.delete(f"/api/v2/commits/{commit['id']}")
    assert r.status_code == 204, r.text
    assert client.get(f"/api/v2/commits/{commit['id']}").status_code == 404


# ── 5. Checkpoint delete refuses when children exist (no cascade) ────────────


def test_delete_commit_with_child_refuses_without_cascade(client):
    repo_id = _create_repo(client, "With-Child")
    session_id = _create_session(client, repo_id)
    c1 = _commit(client, repo_id, session_id, "parent")
    _send(client, session_id, "next turn")
    c2 = _commit(client, repo_id, session_id, "child")

    r = client.delete(f"/api/v2/commits/{c1['id']}")
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert "child commit" in detail["message"].lower()
    assert detail["dependents"]["blocking_count"] >= 1
    assert len(detail["dependents"]["child_commits"]) == 1
    assert detail["dependents"]["child_commits"][0]["id"] == c2["id"]

    # C1 still exists
    assert client.get(f"/api/v2/commits/{c1['id']}").status_code == 200


# ── 6. Checkpoint cascade deletes entire subtree ─────────────────────────────


def test_delete_commit_with_cascade_deletes_subtree(client):
    repo_id = _create_repo(client, "Subtree")
    session_id = _create_session(client, repo_id)
    c1 = _commit(client, repo_id, session_id, "root")
    _send(client, session_id, "turn 1")
    c2 = _commit(client, repo_id, session_id, "mid")
    _send(client, session_id, "turn 2")
    c3 = _commit(client, repo_id, session_id, "leaf")

    r = client.delete(f"/api/v2/commits/{c1['id']}?cascade=true")
    assert r.status_code == 204, r.text

    assert client.get(f"/api/v2/commits/{c1['id']}").status_code == 404
    assert client.get(f"/api/v2/commits/{c2['id']}").status_code == 404
    assert client.get(f"/api/v2/commits/{c3['id']}").status_code == 404


# ── 7. Checkpoint with fork refuses without cascade ──────────────────────────


def test_delete_commit_with_fork_refuses_without_cascade(client):
    repo_id = _create_repo(client, "Fork-Refuse")
    session_id = _create_session(client, repo_id)
    c1 = _commit(client, repo_id, session_id, "base")
    fork = _fork(client, repo_id, c1["id"], branch_name="experiment")
    fork_session_id = fork["session_id"]

    r = client.delete(f"/api/v2/commits/{c1['id']}")
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert detail["dependents"]["blocking_count"] >= 1
    assert len(detail["dependents"]["forked_sessions"]) == 1
    assert detail["dependents"]["forked_sessions"][0]["id"] == fork_session_id


# ── 8. Checkpoint cascade also deletes forked sessions and turns ─────────────


def test_delete_commit_with_cascade_deletes_forked_sessions_and_turns(client):
    repo_id = _create_repo(client, "Fork-Cascade")
    session_id = _create_session(client, repo_id)
    c1 = _commit(client, repo_id, session_id, "base")
    fork = _fork(client, repo_id, c1["id"], branch_name="experiment")
    fork_session_id = fork["session_id"]
    _send(client, fork_session_id, "fork message 1")
    _send(client, fork_session_id, "fork message 2")

    r = client.delete(f"/api/v2/commits/{c1['id']}?cascade=true")
    assert r.status_code == 204, r.text

    assert client.get(f"/api/v2/commits/{c1['id']}").status_code == 404
    assert client.get(f"/api/v4/chat/sessions/{fork_session_id}").status_code == 404


# ── 9. Seeded-only session does NOT block checkpoint delete ─────────────────


def test_delete_commit_with_seeded_only_session_succeeds(client):
    repo_id = _create_repo(client, "Seeded-Only")
    session_a_id = _create_session(client, repo_id, title="author session")
    c1 = _commit(client, repo_id, session_a_id, "first")

    # New session — auto-seeds from head (which is C1). It is NOT a fork.
    session_b_id = _create_session(client, repo_id, title="reader session")
    session_b = client.get(f"/api/v4/chat/sessions/{session_b_id}").json()
    assert session_b["seeded_commit_id"] == c1["id"]
    assert session_b["forked_from_checkpoint_id"] is None  # not a fork

    # Delete C1: informational seed should not block.
    r = client.delete(f"/api/v2/commits/{c1['id']}")
    assert r.status_code == 204, r.text

    # session_b still exists; seeded_commit_id is now null.
    r2 = client.get(f"/api/v4/chat/sessions/{session_b_id}")
    assert r2.status_code == 200
    assert r2.json()["seeded_commit_id"] is None


# ── 10. Session delete cascades turn events ──────────────────────────────────


def test_delete_chat_session_cascades_turns(client):
    repo_id = _create_repo(client, "Session-Cascade")
    session_id = _create_session(client, repo_id)
    _send(client, session_id, "hello")
    _send(client, session_id, "world")

    turns_before = client.get(f"/api/v4/chat/sessions/{session_id}/turns").json()
    assert len(turns_before) >= 2

    r = client.delete(f"/api/v4/chat/sessions/{session_id}")
    assert r.status_code == 204, r.text

    assert client.get(f"/api/v4/chat/sessions/{session_id}").status_code == 404
    assert client.get(f"/api/v4/chat/sessions/{session_id}/turns").status_code == 404


# ── 11. Session delete preserves commits it authored ─────────────────────────


def test_delete_chat_session_leaves_commits_authored_by_it(client):
    repo_id = _create_repo(client, "Preserve-Commits")
    session_id = _create_session(client, repo_id)
    commit = _commit(client, repo_id, session_id, "survives")

    r = client.delete(f"/api/v4/chat/sessions/{session_id}")
    assert r.status_code == 204, r.text

    # Commit authored by the deleted session still exists.
    r2 = client.get(f"/api/v2/commits/{commit['id']}")
    assert r2.status_code == 200


# ── 12. Checkpoint delete rejects cross-user ────────────────────────────────


def test_delete_commit_cross_user_returns_404(client, db_session):
    from app.db.models import RepoModel, CommitModel

    other_user = uuid.UUID("00000000-0000-0000-0000-0000000000ff")
    repo = RepoModel(user_id=other_user, name="Not mine", description="", metadata_={})
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    commit = CommitModel(
        repo_id=repo.id,
        commit_hash="deadbeef" * 8,
        branch_name="main",
        author_type="user",
        message="foreign",
        metadata_={},
    )
    db_session.add(commit)
    db_session.commit()
    db_session.refresh(commit)

    r = client.delete(f"/api/v2/commits/{commit.id}")
    assert r.status_code == 404


# ── 13. Subtree cascade ordering is safe ─────────────────────────────────────


def test_delete_commit_subtree_ordering_is_safe(client, db_session):
    from app.db.models import CommitModel

    repo_id = _create_repo(client, "Ordering")
    session_id = _create_session(client, repo_id)
    c1 = _commit(client, repo_id, session_id, "depth-1")
    _send(client, session_id, "t1")
    c2 = _commit(client, repo_id, session_id, "depth-2")
    _send(client, session_id, "t2")
    c3 = _commit(client, repo_id, session_id, "depth-3")

    r = client.delete(f"/api/v2/commits/{c1['id']}?cascade=true")
    assert r.status_code == 204, r.text

    # Ensure nothing left with parent_commit_id pointing at a deleted commit.
    remaining = db_session.query(CommitModel).all()
    deleted_ids = {uuid.UUID(c1["id"]), uuid.UUID(c2["id"]), uuid.UUID(c3["id"])}
    for c in remaining:
        assert c.id not in deleted_ids, f"{c.id} should have been deleted"
        assert c.parent_commit_id not in deleted_ids, (
            f"{c.id} still points at deleted parent {c.parent_commit_id}"
        )


# ── 14. Idempotency: double-delete is not a 500 ──────────────────────────────


def test_delete_idempotency_double_call(client):
    repo_id = _create_repo(client, "Idempotent")
    session_id = _create_session(client, repo_id)
    commit = _commit(client, repo_id, session_id, "solo")

    r1 = client.delete(f"/api/v2/commits/{commit['id']}")
    assert r1.status_code == 204

    r2 = client.delete(f"/api/v2/commits/{commit['id']}")
    assert r2.status_code == 404

    # And the same for space delete
    r3 = client.delete(f"/api/v2/repos/{repo_id}")
    assert r3.status_code == 204
    r4 = client.delete(f"/api/v2/repos/{repo_id}")
    assert r4.status_code == 404
