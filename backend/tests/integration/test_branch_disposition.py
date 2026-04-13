"""Integration tests for branch disposition / lifecycle.

Covers:
- Setting disposition to integrated, abandoned, active
- Disposition filters branches from /state active_branches
- Disposition filters branches from /state divergence signal
- Reversibility: integrated → active re-shows the branch
- Nonexistent branch returns 404
- Invalid disposition returns 400
"""
from __future__ import annotations


def _create_repo(client, name="Disposition Test"):
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


def _fork(client, space_id, checkpoint_id, branch_name=""):
    r = client.post(
        "/api/v5/lineage/sessions/fork",
        json={
            "space_id": space_id,
            "checkpoint_id": checkpoint_id,
            "branch_name": branch_name,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _set_disposition(client, space_id, branch_name, disposition):
    r = client.patch(
        "/api/v5/lineage/branches/disposition",
        json={
            "space_id": space_id,
            "branch_name": branch_name,
            "disposition": disposition,
        },
    )
    return r


def _get_state(client, repo_id):
    r = client.get(f"/api/v4/chat/spaces/{repo_id}/state")
    assert r.status_code == 200, r.text
    return r.json()


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_set_disposition_integrated(client):
    repo_id = _create_repo(client, "Integrated")
    session_id = _create_session(client, repo_id)
    base = _commit(client, repo_id, session_id, "base", decisions=["D1"])

    fork = _fork(client, repo_id, base["id"], branch_name="side-work")
    _commit(client, repo_id, fork["session_id"], "fork commit", decisions=["D2"])

    r = _set_disposition(client, repo_id, "side-work", "integrated")
    assert r.status_code == 200
    data = r.json()
    assert data["disposition"] == "integrated"
    assert data["sessions_updated"] == 1


def test_integrated_branch_hidden_from_state(client):
    """An integrated branch should not appear in active_branches or divergence."""
    repo_id = _create_repo(client, "Hidden After Integrated")
    session_id = _create_session(client, repo_id)
    base = _commit(client, repo_id, session_id, "base", decisions=["Use Pydantic"])

    fork = _fork(client, repo_id, base["id"], branch_name="experiment")
    _commit(
        client, repo_id, fork["session_id"],
        "experiment commit", decisions=["Use dataclasses"],
    )

    # Before disposition: branch visible
    state_before = _get_state(client, repo_id)
    assert len(state_before["active_branches"]) == 1
    assert state_before["active_branches"][0]["branch_name"] == "experiment"

    # Mark integrated
    _set_disposition(client, repo_id, "experiment", "integrated")

    # After disposition: branch hidden
    state_after = _get_state(client, repo_id)
    assert len(state_after["active_branches"]) == 0
    assert state_after["divergence"] is None


def test_abandoned_branch_hidden_from_state(client):
    repo_id = _create_repo(client, "Hidden After Abandoned")
    session_id = _create_session(client, repo_id)
    base = _commit(client, repo_id, session_id, "base")

    fork = _fork(client, repo_id, base["id"], branch_name="dead-end")
    _commit(client, repo_id, fork["session_id"], "dead end commit")

    _set_disposition(client, repo_id, "dead-end", "abandoned")

    state = _get_state(client, repo_id)
    assert len(state["active_branches"]) == 0


def test_reversibility_active_restores_branch(client):
    """Setting back to active re-shows the branch."""
    repo_id = _create_repo(client, "Reversible")
    session_id = _create_session(client, repo_id)
    base = _commit(client, repo_id, session_id, "base")

    fork = _fork(client, repo_id, base["id"], branch_name="temp")
    _commit(client, repo_id, fork["session_id"], "temp commit")

    _set_disposition(client, repo_id, "temp", "integrated")
    state_hidden = _get_state(client, repo_id)
    assert len(state_hidden["active_branches"]) == 0

    _set_disposition(client, repo_id, "temp", "active")
    state_restored = _get_state(client, repo_id)
    assert len(state_restored["active_branches"]) == 1
    assert state_restored["active_branches"][0]["branch_name"] == "temp"


def test_nonexistent_branch_returns_404(client):
    repo_id = _create_repo(client, "No Branch")
    r = _set_disposition(client, repo_id, "ghost-branch", "integrated")
    assert r.status_code == 404


def test_invalid_disposition_returns_400(client):
    repo_id = _create_repo(client, "Bad Disposition")
    session_id = _create_session(client, repo_id)
    base = _commit(client, repo_id, session_id, "base")
    fork = _fork(client, repo_id, base["id"], branch_name="b1")

    r = _set_disposition(client, repo_id, "b1", "archived")
    assert r.status_code == 400
    assert "disposition" in r.json()["detail"].lower()


def test_only_active_branches_generate_divergence(client):
    """Integrated branches should not trigger the divergence signal."""
    repo_id = _create_repo(client, "Divergence Filter")
    session_id = _create_session(client, repo_id)
    base = _commit(
        client, repo_id, session_id, "base",
        decisions=["Main decision"],
    )

    fork = _fork(client, repo_id, base["id"], branch_name="alt")
    _commit(
        client, repo_id, fork["session_id"],
        "alt commit", decisions=["Alt decision"],
    )

    # Divergence exists before disposition
    state_before = _get_state(client, repo_id)
    assert state_before["divergence"] is not None

    _set_disposition(client, repo_id, "alt", "integrated")

    # Divergence gone after disposition
    state_after = _get_state(client, repo_id)
    assert state_after["divergence"] is None
