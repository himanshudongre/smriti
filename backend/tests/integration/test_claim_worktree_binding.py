"""Integration tests for claim to worktree binding."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.db.models import WorkTree


def _create_repo(client, name="Claim Worktree Test Repo"):
    r = client.post("/api/v2/repos", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_worktree_row(db_session, repo_id: str, *, status="active") -> WorkTree:
    worktree = WorkTree(
        repo_id=uuid.UUID(repo_id),
        agent="codex-local",
        path=f"/tmp/wt-{uuid.uuid4().hex[:8]}",
        branch_name=f"smriti/codex-local/{uuid.uuid4().hex[:8]}",
        base_commit_sha="abc123",
        status=status,
        created_at=datetime.now(UTC),
    )
    db_session.add(worktree)
    db_session.commit()
    db_session.refresh(worktree)
    return worktree


def _create_claim(client, space_id: str, **overrides):
    payload = {
        "space_id": space_id,
        "agent": "codex-local",
        "scope": "Bound worktree claim",
        "branch_name": "worktree-v2-binding-and-enrichment",
        "intent_type": "implement",
        "ttl_hours": 4.0,
        **overrides,
    }
    return client.post("/api/v5/claims", json=payload)


def test_create_claim_with_worktree_id_links_records(client, db_session):
    repo_id = _create_repo(client)
    worktree = _create_worktree_row(db_session, repo_id)

    r = _create_claim(client, repo_id, worktree_id=str(worktree.id))

    assert r.status_code == 201, r.text
    claim = r.json()
    assert claim["worktree_id"] == str(worktree.id)


def test_create_claim_with_nonexistent_worktree_id_returns_404(client):
    repo_id = _create_repo(client)

    r = _create_claim(client, repo_id, worktree_id=str(uuid.uuid4()))

    assert r.status_code == 404
    assert "Worktree not found" in r.json()["detail"]


def test_create_claim_with_worktree_from_other_space_returns_400(client, db_session):
    repo_id = _create_repo(client, "Claim Space")
    other_repo_id = _create_repo(client, "Other Space")
    other_worktree = _create_worktree_row(db_session, other_repo_id)

    r = _create_claim(client, repo_id, worktree_id=str(other_worktree.id))

    assert r.status_code == 400
    assert "different space" in r.json()["detail"]


def test_create_claim_with_closed_worktree_returns_400(client, db_session):
    repo_id = _create_repo(client)
    worktree = _create_worktree_row(db_session, repo_id, status="closed")

    r = _create_claim(client, repo_id, worktree_id=str(worktree.id))

    assert r.status_code == 400
    assert "not active" in r.json()["detail"]


def test_create_claim_without_worktree_id_preserves_existing_behavior(client):
    repo_id = _create_repo(client)

    r = _create_claim(client, repo_id)

    assert r.status_code == 201, r.text
    assert r.json()["worktree_id"] is None
