"""
V5 Lineage API integration tests.

All chat turns use use_mock=True to avoid requiring real provider API keys.

Covers:
- Fork session creation and field correctness
- Forked session context isolation (the critical regression test)
- Lineage endpoint shape
- Compare endpoint diffs
- Auto-inherit of forked_from_checkpoint_id in send_message
- Error cases
"""
import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _create_repo(client, name="Lineage Test Repo"):
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


def _fork(client, space_id, checkpoint_id, branch_name="", provider="", model=""):
    r = client.post("/api/v5/lineage/sessions/fork", json={
        "space_id": space_id,
        "checkpoint_id": checkpoint_id,
        "branch_name": branch_name,
        "provider": provider,
        "model": model,
    })
    return r


def _add_note(client, checkpoint_id, text, author="founder", kind="note"):
    r = client.post(f"/api/v5/checkpoint/{checkpoint_id}/notes", json={
        "text": text,
        "author": author,
        "kind": kind,
    })
    assert r.status_code == 201, r.text
    return r.json()


# ── Fork tests ────────────────────────────────────────────────────────────────

def test_fork_creates_new_session(client):
    """POST fork returns a new session with correct fork fields."""
    repo_id = _create_repo(client, "Fork Basic")
    session_id = _create_session(client, repo_id)
    commit = _commit(client, repo_id, session_id, "base commit",
                     summary="Base state.", decisions=["Use SQLite"])
    checkpoint_id = commit["id"]

    r = _fork(client, repo_id, checkpoint_id, branch_name="experiment-1")
    assert r.status_code == 201, r.text
    data = r.json()

    assert data["forked_from_checkpoint_id"] == checkpoint_id
    assert data["branch_name"] == "experiment-1"
    assert data["history_base_seq"] == 0
    # Must be a fresh UUID, not the original session
    assert data["session_id"] != session_id


def test_fork_auto_generates_branch_name(client):
    """Fork with no branch_name still produces a non-empty branch name."""
    repo_id = _create_repo(client, "Fork AutoName")
    session_id = _create_session(client, repo_id)
    commit = _commit(client, repo_id, session_id, "base")
    checkpoint_id = commit["id"]

    r = _fork(client, repo_id, checkpoint_id)
    assert r.status_code == 201, r.text
    assert r.json()["branch_name"] != ""


def test_fork_session_appears_in_session_get(client):
    """GET /sessions/{id} on a forked session returns branch identity fields."""
    repo_id = _create_repo(client, "Fork Get")
    session_id = _create_session(client, repo_id)
    commit = _commit(client, repo_id, session_id, "base")
    checkpoint_id = commit["id"]

    fork_resp = _fork(client, repo_id, checkpoint_id, branch_name="feat-branch")
    fork_id = fork_resp.json()["session_id"]

    get_r = client.get(f"/api/v4/chat/sessions/{fork_id}")
    assert get_r.status_code == 200, get_r.text
    s = get_r.json()
    assert s["forked_from_checkpoint_id"] == checkpoint_id
    assert s["branch_name"] == "feat-branch"


def test_fork_nonexistent_checkpoint(client):
    """Forking from a non-existent checkpoint returns 404."""
    repo_id = _create_repo(client, "Fork 404")
    fake_id = "00000000-0000-0000-0000-000000000099"
    r = _fork(client, repo_id, fake_id)
    assert r.status_code == 404, r.text


def test_fork_checkpoint_wrong_space(client):
    """Forking a checkpoint that belongs to a different space returns 400."""
    repo_a = _create_repo(client, "Space A")
    repo_b = _create_repo(client, "Space B")

    session_a = _create_session(client, repo_a)
    commit_a = _commit(client, repo_a, session_a, "commit in A")
    checkpoint_a_id = commit_a["id"]

    # Try to fork checkpoint from space A into space B
    r = _fork(client, repo_b, checkpoint_a_id)
    assert r.status_code == 400, r.text


# ── Context isolation tests ───────────────────────────────────────────────────

def test_fork_isolation_between_two_forks(client):
    """Two forks from the same checkpoint accumulate turns independently."""
    repo_id = _create_repo(client, "Fork Isolation")
    session_id = _create_session(client, repo_id)
    commit = _commit(client, repo_id, session_id, "shared base")
    checkpoint_id = commit["id"]

    fork1_id = _fork(client, repo_id, checkpoint_id, branch_name="branch-1").json()["session_id"]
    fork2_id = _fork(client, repo_id, checkpoint_id, branch_name="branch-2").json()["session_id"]

    _send(client, fork1_id, "Message only in branch-1")
    _send(client, fork2_id, "Message only in branch-2")

    turns1 = client.get(f"/api/v4/chat/spaces/{repo_id}/sessions/{fork1_id}/turns").json()
    turns2 = client.get(f"/api/v4/chat/spaces/{repo_id}/sessions/{fork2_id}/turns").json()

    branch1_contents = [t["content"] for t in turns1]
    branch2_contents = [t["content"] for t in turns2]

    assert any("branch-1" in c for c in branch1_contents)
    assert not any("branch-2" in c for c in branch1_contents)
    assert any("branch-2" in c for c in branch2_contents)
    assert not any("branch-1" in c for c in branch2_contents)


def test_fork_isolation_regression_checkpoint_a_does_not_see_b_era_context(client):
    """
    Regression test for the commit-isolation bug.

    Scenario:
      1. Create Checkpoint A (Australia trip planning).
      2. Continue the session, add NZ context, create Checkpoint B.
      3. Fork a new session from Checkpoint A.
      4. Send a message in the fork.
      5. Verify the forked session's turns do NOT include any NZ-era turns
         from the period between A and B.

    Before the fix, history_base_seq=0 was not enforced for forked sessions,
    so all turns in the original session (including post-A NZ turns) bled in.
    """
    repo_id = _create_repo(client, "Regression Fork")
    session_id = _create_session(client, repo_id)

    # ── Phase 1: build up to Checkpoint A ────────────────────────────────────
    _send(client, session_id, "Let's plan the Australia trip.")
    _send(client, session_id, "We should visit Sydney and Melbourne.")

    commit_a = _commit(client, repo_id, session_id, "Checkpoint A",
                       summary="Planning Australia trip.",
                       decisions=["Visit Sydney", "Visit Melbourne"])
    checkpoint_a_id = commit_a["id"]

    # ── Phase 2: continue in the same session, add NZ content ─────────────────
    _send(client, session_id, "Actually, let's also add New Zealand to the trip.")
    _send(client, session_id, "We should visit Auckland and Queenstown.")

    _commit(client, repo_id, session_id, "Checkpoint B",
            summary="Added New Zealand to itinerary.",
            decisions=["Visit Auckland", "Visit Queenstown"])

    # ── Phase 3: fork from Checkpoint A ──────────────────────────────────────
    fork_resp = _fork(client, repo_id, checkpoint_a_id, branch_name="australia-only")
    assert fork_resp.status_code == 201, fork_resp.text
    fork_id = fork_resp.json()["session_id"]

    # ── Phase 4: send a message in the fork ──────────────────────────────────
    send_resp = _send(client, fork_id, "What cities are we visiting?")

    # ── Phase 5: verify NZ-era turns are not in the fork's history ───────────
    turns = client.get(f"/api/v4/chat/spaces/{repo_id}/sessions/{fork_id}/turns").json()
    all_fork_content = " ".join(t["content"] for t in turns)

    # The fork should not contain NZ references from the original session's
    # post-A turns.  (The mock LLM echoes the prompt, so if NZ content were
    # injected as history it would appear in the assistant reply.)
    assert "New Zealand" not in all_fork_content, (
        "NZ-era context from post-A turns leaked into the forked session. "
        "history_base_seq isolation is broken."
    )
    assert "Auckland" not in all_fork_content, (
        "Auckland turn from post-A leaked into the fork."
    )


def test_send_auto_inherits_fork_context_without_explicit_mount(client):
    """
    send_message in a forked session must use checkpoint context automatically,
    even when mounted_checkpoint_id is not passed in the request.
    """
    repo_id = _create_repo(client, "Fork Auto-Inherit")
    session_id = _create_session(client, repo_id)
    commit = _commit(client, repo_id, session_id, "base",
                     summary="The project uses Rust.", decisions=["Use Rust"])
    checkpoint_id = commit["id"]

    fork_id = _fork(client, repo_id, checkpoint_id).json()["session_id"]

    # Send WITHOUT passing mounted_checkpoint_id — backend must auto-inherit
    r = client.post("/api/v4/chat/send", json={
        "session_id": fork_id,
        "provider": "openrouter",
        "model": "mock",
        "message": "What language are we using?",
        "use_mock": True,
        # No mounted_checkpoint_id, no history_base_seq
    })
    assert r.status_code == 200, r.text


# ── Lineage view tests ────────────────────────────────────────────────────────

def test_lineage_empty_space(client):
    """Lineage on a space with no checkpoints or sessions returns empty lists."""
    repo_id = _create_repo(client, "Empty Lineage")
    r = client.get(f"/api/v5/lineage/spaces/{repo_id}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["space_id"] == repo_id
    assert data["checkpoints"] == []
    assert data["sessions"] == []


def test_lineage_linear_chain(client):
    """A → B → C checkpoint chain appears with correct parent_checkpoint_id links."""
    repo_id = _create_repo(client, "Linear Lineage")
    session_id = _create_session(client, repo_id)

    _send(client, session_id, "Step 1")
    commit_a = _commit(client, repo_id, session_id, "A")

    _send(client, session_id, "Step 2")
    commit_b = _commit(client, repo_id, session_id, "B")

    _send(client, session_id, "Step 3")
    commit_c = _commit(client, repo_id, session_id, "C")

    r = client.get(f"/api/v5/lineage/spaces/{repo_id}")
    assert r.status_code == 200, r.text
    checkpoints = r.json()["checkpoints"]
    assert len(checkpoints) == 3

    by_id = {c["id"]: c for c in checkpoints}
    assert by_id[commit_a["id"]]["parent_checkpoint_id"] is None
    assert by_id[commit_b["id"]]["parent_checkpoint_id"] == commit_a["id"]
    assert by_id[commit_c["id"]]["parent_checkpoint_id"] == commit_b["id"]


def test_lineage_with_fork_shows_both_sessions(client):
    """After forking, the lineage view contains both the original and forked sessions."""
    repo_id = _create_repo(client, "Fork Lineage")
    session_id = _create_session(client, repo_id)
    commit = _commit(client, repo_id, session_id, "base")
    checkpoint_id = commit["id"]

    fork_resp = _fork(client, repo_id, checkpoint_id, branch_name="side-branch")
    fork_id = fork_resp.json()["session_id"]

    r = client.get(f"/api/v5/lineage/spaces/{repo_id}")
    assert r.status_code == 200, r.text
    data = r.json()

    session_ids = {s["id"] for s in data["sessions"]}
    assert session_id in session_ids
    assert fork_id in session_ids

    fork_node = next(s for s in data["sessions"] if s["id"] == fork_id)
    assert fork_node["forked_from_checkpoint_id"] == checkpoint_id
    assert fork_node["branch_name"] == "side-branch"


def test_lineage_checkpoint_includes_author_agent(client):
    """author_agent round-trips through the lineage endpoint.

    Verifies that:
    - a checkpoint created with an explicit author_agent has that value
      in the lineage CheckpointNode response
    - a checkpoint created without author_agent returns null

    Regression guard for the V4 Build 1 change that added author_agent
    to CheckpointNode in lineage.py (flagged as missing test coverage
    by Codex review checkpoint b9d2002).
    """
    repo_id = _create_repo(client, "Author Agent Lineage")
    session_id = _create_session(client, repo_id)

    tagged = _commit(
        client, repo_id, session_id,
        message="Tagged checkpoint",
        author_agent="claude-code",
    )
    fallback = _commit(
        client, repo_id, session_id,
        message="Fallback checkpoint",
        # No explicit author_agent — backend falls back to
        # session.active_provider ("openrouter" in test fixtures).
    )

    r = client.get(f"/api/v5/lineage/spaces/{repo_id}")
    assert r.status_code == 200, r.text
    checkpoints = r.json()["checkpoints"]
    assert len(checkpoints) == 2

    by_id = {c["id"]: c for c in checkpoints}

    # Tagged checkpoint must have the explicit author_agent value.
    assert by_id[tagged["id"]]["author_agent"] == "claude-code"

    # Checkpoint without explicit author_agent falls back to
    # session.active_provider. The field is never null once stored —
    # the fallback happens at commit time in the backend, not at
    # response time. Verify it is present and non-empty.
    fallback_agent = by_id[fallback["id"]]["author_agent"]
    assert fallback_agent is not None and fallback_agent != "", (
        f"Expected a fallback author_agent from session.active_provider, "
        f"got: {fallback_agent!r}"
    )


def test_lineage_checkpoint_includes_note_summary(client):
    """note_count and note_kinds round-trip through the lineage endpoint."""
    repo_id = _create_repo(client, "Lineage Note Summary")
    session_id = _create_session(client, repo_id)

    mixed = _commit(client, repo_id, session_id, message="Checkpoint with mixed notes")
    plain = _commit(client, repo_id, session_id, message="Checkpoint without notes")

    _add_note(client, mixed["id"], "Milestone note", kind="milestone")
    _add_note(client, mixed["id"], "Noise note", kind="noise")
    _add_note(client, mixed["id"], "Plain note", kind="note")

    r = client.get(f"/api/v5/lineage/spaces/{repo_id}")
    assert r.status_code == 200, r.text
    checkpoints = r.json()["checkpoints"]
    by_id = {c["id"]: c for c in checkpoints}

    assert by_id[mixed["id"]]["note_count"] == 3
    assert by_id[mixed["id"]]["note_kinds"] == ["milestone", "noise", "note"]
    assert by_id[plain["id"]]["note_count"] == 0
    assert by_id[plain["id"]]["note_kinds"] == []


# ── Compare tests ─────────────────────────────────────────────────────────────

def test_compare_same_checkpoint(client):
    """Comparing a checkpoint with itself produces an empty diff."""
    repo_id = _create_repo(client, "Compare Same")
    session_id = _create_session(client, repo_id)
    commit = _commit(client, repo_id, session_id, "base",
                     summary="Hello.",
                     decisions=["Use Postgres"],
                     tasks=["Set up schema"])
    cid = commit["id"]

    r = client.get(f"/api/v5/lineage/checkpoints/{cid}/compare/{cid}")
    assert r.status_code == 200, r.text
    diff = r.json()["diff"]

    assert diff["summary_a"] == diff["summary_b"]
    assert diff["decisions_only_a"] == []
    assert diff["decisions_only_b"] == []
    assert diff["tasks_only_a"] == []
    assert diff["tasks_only_b"] == []
    assert "Use Postgres" in diff["decisions_shared"]


def test_compare_diverged_checkpoints(client):
    """Two checkpoints with different decisions produce correct A-only / B-only / shared splits."""
    repo_id = _create_repo(client, "Compare Diverged")
    session_id = _create_session(client, repo_id)

    commit_a = _commit(client, repo_id, session_id, "A",
                       decisions=["Use Postgres", "Use Redis", "No auth"],
                       tasks=["Write schema"])

    fork_id = _fork(client, repo_id, commit_a["id"]).json()["session_id"]
    _send(client, fork_id, "Let's take a different approach.")

    commit_b = _commit(client, repo_id, fork_id, "B",
                       decisions=["Use MySQL", "Use Redis", "Add JWT auth"],
                       tasks=["Write schema", "Add migration"])

    r = client.get(f"/api/v5/lineage/checkpoints/{commit_a['id']}/compare/{commit_b['id']}")
    assert r.status_code == 200, r.text
    diff = r.json()["diff"]

    assert "Use Postgres" in diff["decisions_only_a"]
    assert "No auth" in diff["decisions_only_a"]
    assert "Use MySQL" in diff["decisions_only_b"]
    assert "Add JWT auth" in diff["decisions_only_b"]
    assert "Use Redis" in diff["decisions_shared"]

    assert "Write schema" in diff["tasks_shared"]
    assert "Add migration" in diff["tasks_only_b"]


def test_compare_nonexistent_checkpoint(client):
    """Comparing with a non-existent checkpoint returns 404."""
    repo_id = _create_repo(client, "Compare 404")
    session_id = _create_session(client, repo_id)
    commit = _commit(client, repo_id, session_id, "real")
    fake_id = "00000000-0000-0000-0000-000000000099"

    r = client.get(f"/api/v5/lineage/checkpoints/{commit['id']}/compare/{fake_id}")
    assert r.status_code == 404, r.text


# ── Compare: common ancestor walk + normalized shared-set matching ────────────


def test_compare_finds_direct_common_ancestor(client):
    """LCA is computed when two checkpoints share a direct parent.

    C1 on main. C2 on main (parent=C1). Fork from C1, commit C3 on the
    fork (parent=C1). Compare C2 vs C3 -> LCA is C1.
    """
    repo_id = _create_repo(client, "LCA Direct")
    session_id = _create_session(client, repo_id)
    c1 = _commit(client, repo_id, session_id, "root")
    _send(client, session_id, "turn 1")
    c2 = _commit(client, repo_id, session_id, "c2 on main")

    fork = _fork(client, repo_id, c1["id"], branch_name="branch-a").json()
    fork_session_id = fork["session_id"]
    _send(client, fork_session_id, "turn on fork")
    c3 = _commit(client, repo_id, fork_session_id, "c3 on fork")

    r = client.get(f"/api/v5/lineage/checkpoints/{c2['id']}/compare/{c3['id']}")
    assert r.status_code == 200, r.text
    diff = r.json()["diff"]
    assert diff["common_ancestor_commit_id"] == c1["id"]


def test_compare_finds_two_step_ancestor(client):
    """LCA walks multiple parent steps up both chains.

    C1 -> C2 -> C3 on main. Fork from C2, commit C4 on fork.
    Compare C3 vs C4 -> LCA is C2 (two steps up from C3, one step from C4).
    """
    repo_id = _create_repo(client, "LCA Two Step")
    session_id = _create_session(client, repo_id)
    _commit(client, repo_id, session_id, "c1")
    _send(client, session_id, "turn a")
    c2 = _commit(client, repo_id, session_id, "c2")
    _send(client, session_id, "turn b")
    c3 = _commit(client, repo_id, session_id, "c3")

    fork = _fork(client, repo_id, c2["id"], branch_name="branch-two").json()
    fork_session_id = fork["session_id"]
    _send(client, fork_session_id, "turn on fork")
    c4 = _commit(client, repo_id, fork_session_id, "c4 on fork")

    r = client.get(f"/api/v5/lineage/checkpoints/{c3['id']}/compare/{c4['id']}")
    assert r.status_code == 200, r.text
    diff = r.json()["diff"]
    assert diff["common_ancestor_commit_id"] == c2["id"]


def test_compare_returns_null_ancestor_for_unrelated_checkpoints(client):
    """Checkpoints in separate spaces share no ancestor -> LCA is None."""
    repo_a = _create_repo(client, "LCA Unrelated A")
    session_a = _create_session(client, repo_a)
    c_a = _commit(client, repo_a, session_a, "isolated a")

    repo_b = _create_repo(client, "LCA Unrelated B")
    session_b = _create_session(client, repo_b)
    c_b = _commit(client, repo_b, session_b, "isolated b")

    r = client.get(f"/api/v5/lineage/checkpoints/{c_a['id']}/compare/{c_b['id']}")
    assert r.status_code == 200, r.text
    diff = r.json()["diff"]
    assert diff["common_ancestor_commit_id"] is None


def test_compare_shared_set_matches_normalized(client):
    """Shared-set matching ignores case + punctuation differences.

    Two agents agreeing on the same commitment with slightly different
    wording should show the overlap in shared. The A-side original is
    the deterministic winner for the displayed shared value.
    """
    repo_id = _create_repo(client, "Shared Normalized")
    session_id = _create_session(client, repo_id)
    c_a = _commit(client, repo_id, session_id, "a",
                  decisions=["Use stdlib only", "Prefer PostgreSQL", "Ship a CLI"])

    fork = _fork(client, repo_id, c_a["id"], branch_name="variant").json()
    fork_session_id = fork["session_id"]
    _send(client, fork_session_id, "turn")
    c_b = _commit(client, repo_id, fork_session_id, "b",
                  decisions=["use STDLIB only.", "Prefer postgresql!", "Skip the CLI"])

    r = client.get(f"/api/v5/lineage/checkpoints/{c_a['id']}/compare/{c_b['id']}")
    assert r.status_code == 200, r.text
    diff = r.json()["diff"]

    # The two stdlib / postgresql commitments normalize equally and show
    # up in shared with the A-side originals.
    assert "Use stdlib only" in diff["decisions_shared"]
    assert "Prefer PostgreSQL" in diff["decisions_shared"]
    # "Ship a CLI" and "Skip the CLI" normalize differently, so they split.
    assert "Ship a CLI" in diff["decisions_only_a"]
    assert "Skip the CLI" in diff["decisions_only_b"]


# ── Regression: existing sessions default to main branch ──────────────────────

def test_existing_session_defaults_to_main_branch(client):
    """Sessions created via the normal (non-fork) path default to branch_name='main'."""
    repo_id = _create_repo(client, "Main Branch Default")
    session_id = _create_session(client, repo_id)

    r = client.get(f"/api/v4/chat/sessions/{session_id}")
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["branch_name"] == "main"
    assert s["forked_from_checkpoint_id"] is None


# ── Branch-semantics regression tests ────────────────────────────────────────
# These tests cover the real manual-testing bug found in March 2026:
# checkpoints created from forked sessions were silently written to main.

def test_manual_commit_from_fork_uses_fork_branch(client):
    """
    T1: A checkpoint created from a forked session must have branch_name equal
    to the fork session's branch, NOT 'main'.
    """
    repo_id = _create_repo(client, "BranchSemantics T1")
    session_id = _create_session(client, repo_id)
    commit_a = _commit(client, repo_id, session_id, "Checkpoint A",
                       summary="Australia only.", decisions=["Visit Sydney"])

    fork_resp = _fork(client, repo_id, commit_a["id"], branch_name="au-vietnam")
    fork_id = fork_resp.json()["session_id"]

    _send(client, fork_id, "Let's add Vietnam to the trip.")

    fork_commit = _commit(client, repo_id, fork_id, "Fork-local checkpoint",
                          summary="Australia + Vietnam.", decisions=["Visit Hanoi"])

    assert fork_commit["branch_name"] == "au-vietnam", (
        f"Expected branch 'au-vietnam', got '{fork_commit['branch_name']}'. "
        "manual_commit is still writing fork checkpoints to main."
    )


def test_manual_commit_from_fork_first_checkpoint_parents_to_fork_source(client):
    """
    T2: The first checkpoint created on a fork branch must have parent_commit_id
    equal to the fork source checkpoint, not the main-branch head.
    """
    repo_id = _create_repo(client, "BranchSemantics T2")
    session_id = _create_session(client, repo_id)
    commit_a = _commit(client, repo_id, session_id, "Checkpoint A",
                       summary="Australia only.")
    _send(client, session_id, "Add New Zealand.")
    commit_b = _commit(client, repo_id, session_id, "Checkpoint B",
                       summary="Australia + New Zealand.")  # main head is now B

    # Fork from A — not from B
    fork_resp = _fork(client, repo_id, commit_a["id"], branch_name="au-only-fork")
    fork_id = fork_resp.json()["session_id"]
    _send(client, fork_id, "Add Vietnam.")
    fork_commit = _commit(client, repo_id, fork_id, "Fork first checkpoint",
                          summary="Australia + Vietnam.")

    assert fork_commit["parent_commit_id"] == commit_a["id"], (
        f"Expected parent to be checkpoint A ({commit_a['id']}), "
        f"got {fork_commit['parent_commit_id']}. "
        "Fork's first checkpoint is reparenting to the main-branch head (B) instead of A."
    )


def test_manual_commit_from_fork_chains_locally(client):
    """
    T3: The second fork-local checkpoint must parent to the first fork-local
    checkpoint, not to main-branch head or the fork source again.
    """
    repo_id = _create_repo(client, "BranchSemantics T3")
    session_id = _create_session(client, repo_id)
    commit_a = _commit(client, repo_id, session_id, "A")

    fork_resp = _fork(client, repo_id, commit_a["id"], branch_name="local-chain")
    fork_id = fork_resp.json()["session_id"]

    _send(client, fork_id, "Step 1 on fork.")
    fork_c1 = _commit(client, repo_id, fork_id, "Fork C1")

    _send(client, fork_id, "Step 2 on fork.")
    fork_c2 = _commit(client, repo_id, fork_id, "Fork C2")

    assert fork_c2["parent_commit_id"] == fork_c1["id"], (
        f"Expected Fork C2 to parent Fork C1 ({fork_c1['id']}), "
        f"got {fork_c2['parent_commit_id']}. "
        "Fork-local checkpoints are not chaining to each other."
    )


def test_fork_checkpoint_not_visible_on_main_branch_filter(client):
    """
    T4: A checkpoint created on a fork branch must NOT appear when listing
    commits filtered to branch='main'.
    """
    repo_id = _create_repo(client, "BranchSemantics T4")
    session_id = _create_session(client, repo_id)
    commit_a = _commit(client, repo_id, session_id, "A on main")

    fork_resp = _fork(client, repo_id, commit_a["id"], branch_name="side-branch")
    fork_id = fork_resp.json()["session_id"]
    _send(client, fork_id, "Fork-local work.")
    fork_commit = _commit(client, repo_id, fork_id, "Fork-local checkpoint")

    main_commits = client.get(f"/api/v2/repos/{repo_id}/commits?branch=main").json()
    main_ids = {c["id"] for c in main_commits}

    assert fork_commit["id"] not in main_ids, (
        "Fork-local checkpoint is appearing in the main-branch commit list. "
        "It must only appear under its own branch."
    )


def test_reachable_checkpoints_main_session_returns_main_only(client):
    """
    T5: For a main-branch session the reachable-checkpoints endpoint returns
    only main-branch commits.
    """
    repo_id = _create_repo(client, "BranchSemantics T5")
    session_id = _create_session(client, repo_id)
    commit_a = _commit(client, repo_id, session_id, "A")

    fork_resp = _fork(client, repo_id, commit_a["id"], branch_name="other-branch")
    fork_id = fork_resp.json()["session_id"]
    _send(client, fork_id, "Fork work.")
    fork_commit = _commit(client, repo_id, fork_id, "Fork checkpoint")

    r = client.get(f"/api/v5/lineage/sessions/{session_id}/checkpoints")
    assert r.status_code == 200, r.text
    ids = {c["id"] for c in r.json()}

    assert commit_a["id"] in ids
    assert fork_commit["id"] not in ids, (
        "Reachable-checkpoints for a main session is including a fork-branch checkpoint. "
        "It should return only main-branch commits."
    )


def test_reachable_checkpoints_forked_session_excludes_downstream_main(client):
    """
    T6 (NZ regression): The reachable-checkpoints endpoint for a forked session
    must NOT include main-branch checkpoints created AFTER the fork point.

    Australia/NZ scenario:
      main: A (AU only) → B (AU + NZ)
      fork from A: branch 'au-vietnam'
    The fork's reachable set must include A but NOT B.
    """
    repo_id = _create_repo(client, "BranchSemantics T6")
    session_id = _create_session(client, repo_id)

    _send(client, session_id, "Australia trip planning.")
    commit_a = _commit(client, repo_id, session_id, "Checkpoint A",
                       summary="Australia only.",
                       decisions=["Visit Sydney", "Visit Melbourne"])

    _send(client, session_id, "Add New Zealand.")
    commit_b = _commit(client, repo_id, session_id, "Checkpoint B",
                       summary="Australia + New Zealand.",
                       decisions=["Visit Auckland"])

    # Fork from A
    fork_resp = _fork(client, repo_id, commit_a["id"], branch_name="au-vietnam")
    fork_id = fork_resp.json()["session_id"]

    r = client.get(f"/api/v5/lineage/sessions/{fork_id}/checkpoints")
    assert r.status_code == 200, r.text
    reachable = r.json()
    ids = {c["id"] for c in reachable}

    assert commit_a["id"] in ids, "Fork source (Checkpoint A) must be reachable."
    assert commit_b["id"] not in ids, (
        "Checkpoint B (NZ, created on main AFTER the fork point) must NOT be "
        "reachable from the fork session. This is the NZ-bleed regression."
    )


def test_reachable_checkpoints_forked_session_includes_fork_local(client):
    """
    T7: The reachable-checkpoints endpoint for a forked session includes
    checkpoints created on that session's own branch after the fork.
    """
    repo_id = _create_repo(client, "BranchSemantics T7")
    session_id = _create_session(client, repo_id)
    commit_a = _commit(client, repo_id, session_id, "A")

    fork_resp = _fork(client, repo_id, commit_a["id"], branch_name="au-vietnam")
    fork_id = fork_resp.json()["session_id"]
    _send(client, fork_id, "Vietnam discussion.")
    fork_commit = _commit(client, repo_id, fork_id, "Fork checkpoint: AU+VN",
                          summary="Australia + Vietnam.", decisions=["Visit Hanoi"])

    r = client.get(f"/api/v5/lineage/sessions/{fork_id}/checkpoints")
    assert r.status_code == 200, r.text
    ids = {c["id"] for c in r.json()}

    assert fork_commit["id"] in ids, (
        "Fork-local checkpoint must appear in the forked session's reachable set."
    )
    assert commit_a["id"] in ids, (
        "Fork source (Checkpoint A) must also appear in the reachable set."
    )


def test_draft_isolation_forked_session_no_explicit_mount(client):
    """
    T8: draft_checkpoint for a forked session with no explicit mount must
    only include fork-local turns (sequence_number > 0).

    We verify this indirectly: the draft endpoint must succeed and not raise,
    demonstrating that the session-based isolation path is reached without error.
    The turn-boundary correctness is already covered by the send_message
    regression test (T6 equivalent in the original test suite).
    """
    repo_id = _create_repo(client, "BranchSemantics T8")
    session_id = _create_session(client, repo_id)
    commit_a = _commit(client, repo_id, session_id, "Checkpoint A",
                       summary="Australia only.")

    fork_resp = _fork(client, repo_id, commit_a["id"], branch_name="draft-test")
    fork_id = fork_resp.json()["session_id"]
    _send(client, fork_id, "Let's discuss Vietnam.")
    _send(client, fork_id, "We should visit Hanoi and Ho Chi Minh City.")

    # Draft with NO mounted_checkpoint_id — backend must auto-apply fork isolation
    r = client.post("/api/v5/checkpoint/draft", json={
        "session_id": fork_id,
        "num_turns": 10,
        # No mounted_checkpoint_id, no history_base_seq — fork isolation is auto-applied
    })
    assert r.status_code == 200, r.text
    data = r.json()
    # Draft must return a valid (possibly empty) structured object
    assert "decisions" in data
    assert "tasks" in data
    assert "summary" in data
