"""Integration tests for the multi-branch space state endpoint.

Covers:
- Empty space returns a minimal, usable shape
- Main-only project returns no active branches, no divergence
- Fork with overlapping decisions returns active branches but no divergence
- Fork with disjoint decisions returns both active branches and divergence
- Hard caps: 5 active branches, 2 divergent branches, 3 decisions per side
- Divergence matching uses the same normalization as `smriti compare` —
  case and punctuation differences must NOT show as divergent

These tests exercise `GET /api/v4/chat/spaces/{id}/state` end-to-end
through the FastAPI app with an in-memory SQLite session. No mocking.
"""
from __future__ import annotations


# ── Helpers (match the shape used in test_api_v5_lineage.py) ─────────────────


def _create_repo(client, name: str = "Multi-Branch State Test"):
    r = client.post("/api/v2/repos", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_session(client, repo_id: str, title: str = "test"):
    r = client.post(
        f"/api/v4/chat/spaces/{repo_id}/sessions",
        json={"title": title, "provider": "openrouter", "model": "mock"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _commit(
    client,
    repo_id: str,
    session_id: str,
    message: str = "checkpoint",
    **kwargs,
) -> dict:
    payload = {"repo_id": repo_id, "session_id": session_id, "message": message, **kwargs}
    r = client.post("/api/v4/chat/commit", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _fork(client, space_id: str, checkpoint_id: str, branch_name: str = ""):
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


def _get_state(client, repo_id: str):
    r = client.get(f"/api/v4/chat/spaces/{repo_id}/state")
    assert r.status_code == 200, r.text
    return r.json()


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_state_no_checkpoints(client):
    """Empty space: head is empty, commit is None, no branches, no divergence."""
    repo_id = _create_repo(client, "Empty")

    state = _get_state(client, repo_id)

    assert state["space"]["id"] == repo_id
    assert state["space"]["name"] == "Empty"
    assert state["head"]["commit_id"] is None
    assert state["head"]["commit_hash"] is None
    assert state["commit"] is None
    assert state["active_branches"] == []
    assert state["divergence"] is None


def test_state_main_only(client):
    """Single main checkpoint, no forks: main HEAD present, no extensions."""
    repo_id = _create_repo(client, "Main Only")
    session_id = _create_session(client, repo_id)
    commit = _commit(
        client,
        repo_id,
        session_id,
        message="Initial state",
        summary="Just started.",
        decisions=["Use Pydantic for validation"],
    )

    state = _get_state(client, repo_id)

    assert state["head"]["commit_id"] == commit["id"]
    assert state["commit"] is not None
    assert state["commit"]["message"] == "Initial state"
    assert state["commit"]["decisions"] == ["Use Pydantic for validation"]
    assert state["active_branches"] == []
    assert state["divergence"] is None


def test_state_with_fork_no_conflict(client):
    """Main + fork with overlapping decisions: Active branches yes, divergence no."""
    repo_id = _create_repo(client, "Fork No Conflict")
    session_id = _create_session(client, repo_id)
    base = _commit(
        client,
        repo_id,
        session_id,
        message="Base",
        decisions=["Use Pydantic for validation", "Background LLM is gpt-4o-mini"],
    )

    fork = _fork(client, repo_id, base["id"], branch_name="experiment-a")
    _commit(
        client,
        repo_id,
        fork["session_id"],
        message="Fork commit",
        decisions=["Use Pydantic for validation", "Background LLM is gpt-4o-mini"],
    )

    state = _get_state(client, repo_id)

    assert len(state["active_branches"]) == 1
    ab = state["active_branches"][0]
    assert ab["branch_name"] == "experiment-a"
    assert ab["message"] == "Fork commit"
    assert state["divergence"] is None


def test_state_with_fork_conflict(client):
    """Main + fork with disjoint decisions: both sections populated."""
    repo_id = _create_repo(client, "Fork Conflict")
    session_id = _create_session(client, repo_id)
    base = _commit(
        client,
        repo_id,
        session_id,
        message="Base",
        decisions=["Use Pydantic with extra=forbid"],
    )

    fork = _fork(client, repo_id, base["id"], branch_name="stdlib-approach")
    _commit(
        client,
        repo_id,
        fork["session_id"],
        message="Trying stdlib",
        decisions=["Use stdlib dataclasses only", "Reject Pydantic as a dep"],
    )

    state = _get_state(client, repo_id)

    assert len(state["active_branches"]) == 1
    assert state["divergence"] is not None
    pairs = state["divergence"]["pairs"]
    assert len(pairs) == 1
    pair = pairs[0]
    assert pair["branch_name"] == "stdlib-approach"
    assert "Use Pydantic with extra=forbid" in pair["main_only_decisions"]
    # Normalization flattens tokens but both fork-only decisions should be present.
    assert any("stdlib" in d.lower() for d in pair["branch_only_decisions"])
    assert any("pydantic" in d.lower() for d in pair["branch_only_decisions"])


def test_active_branches_capped_at_5(client):
    """Seven non-main branches should render at most 5 in active_branches."""
    repo_id = _create_repo(client, "Many Forks")
    session_id = _create_session(client, repo_id)
    base = _commit(
        client,
        repo_id,
        session_id,
        message="Base",
        decisions=["Decision A"],
    )

    for i in range(7):
        fork = _fork(client, repo_id, base["id"], branch_name=f"branch-{i:02d}")
        _commit(
            client,
            repo_id,
            fork["session_id"],
            message=f"Branch {i} commit",
            decisions=["Decision A"],
        )

    state = _get_state(client, repo_id)
    assert len(state["active_branches"]) == 5
    # Divergence has nothing to report since all branches share the same decision.
    assert state["divergence"] is None


def test_divergence_branches_capped_at_2(client):
    """Three divergent forks: divergence.pairs should contain at most 2."""
    repo_id = _create_repo(client, "Three Divergent Forks")
    session_id = _create_session(client, repo_id)
    base = _commit(
        client,
        repo_id,
        session_id,
        message="Base",
        decisions=["Use Postgres"],
    )

    for i in range(3):
        fork = _fork(client, repo_id, base["id"], branch_name=f"try-{i}")
        _commit(
            client,
            repo_id,
            fork["session_id"],
            message=f"Alt {i}",
            decisions=[f"Use alternative-{i}-store"],
        )

    state = _get_state(client, repo_id)
    assert len(state["active_branches"]) == 3
    assert state["divergence"] is not None
    assert len(state["divergence"]["pairs"]) == 2


def test_divergence_decisions_capped_at_3(client):
    """A fork with 5 disjoint decisions returns 3 in main_only + 3 in branch_only."""
    repo_id = _create_repo(client, "Many Decisions")
    session_id = _create_session(client, repo_id)
    base = _commit(
        client,
        repo_id,
        session_id,
        message="Base",
        decisions=[
            "Main decision one",
            "Main decision two",
            "Main decision three",
            "Main decision four",
            "Main decision five",
        ],
    )

    fork = _fork(client, repo_id, base["id"], branch_name="wildly-different")
    _commit(
        client,
        repo_id,
        fork["session_id"],
        message="Alt",
        decisions=[
            "Branch decision one",
            "Branch decision two",
            "Branch decision three",
            "Branch decision four",
            "Branch decision five",
        ],
    )

    state = _get_state(client, repo_id)
    pair = state["divergence"]["pairs"][0]
    assert len(pair["main_only_decisions"]) == 3
    assert len(pair["branch_only_decisions"]) == 3


def test_divergence_matches_compare_normalization(client):
    """Decisions differing only in case or punctuation MUST normalize equal."""
    repo_id = _create_repo(client, "Normalization")
    session_id = _create_session(client, repo_id)
    base = _commit(
        client,
        repo_id,
        session_id,
        message="Base",
        decisions=["Use Pydantic"],
    )

    fork = _fork(client, repo_id, base["id"], branch_name="punct-diff")
    # Same decision, different punctuation + case → should match after normalize.
    _commit(
        client,
        repo_id,
        fork["session_id"],
        message="Tiny style difference",
        decisions=["use pydantic."],
    )

    state = _get_state(client, repo_id)
    assert len(state["active_branches"]) == 1
    assert state["divergence"] is None, (
        "Expected no divergence: decisions differ only in case/punctuation "
        "and must normalize equal (matches compare semantics)."
    )


def test_state_main_head_unchanged_when_forks_exist(client):
    """Regression guard: adding forks must not change what main HEAD reports."""
    repo_id = _create_repo(client, "HEAD Stability")
    session_id = _create_session(client, repo_id)
    main_commit = _commit(
        client,
        repo_id,
        session_id,
        message="Main HEAD",
        summary="Main summary.",
        decisions=["Main decision"],
    )

    # No forks yet.
    state_before = _get_state(client, repo_id)
    assert state_before["head"]["commit_id"] == main_commit["id"]
    assert state_before["commit"]["message"] == "Main HEAD"

    # Add a fork with a commit.
    fork = _fork(client, repo_id, main_commit["id"], branch_name="side")
    _commit(
        client,
        repo_id,
        fork["session_id"],
        message="Side commit",
        decisions=["Side decision"],
    )

    state_after = _get_state(client, repo_id)
    # Main HEAD is unchanged — state["commit"] still points at the original.
    assert state_after["head"]["commit_id"] == main_commit["id"]
    assert state_after["commit"]["message"] == "Main HEAD"
    assert state_after["commit"]["decisions"] == ["Main decision"]
    # And the fork is surfaced in active_branches.
    assert any(b["branch_name"] == "side" for b in state_after["active_branches"])
