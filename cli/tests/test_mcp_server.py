"""Unit tests for smriti_cli.mcp_server tool handlers.

Each tool is tested as a plain Python function with a mocked SmritiClient.
This does not exercise the MCP protocol layer — correctness of the
JSON-RPC wire format is delegated to FastMCP. The goal here is to verify
that every tool handler:
  - passes the right arguments to SmritiClient
  - returns the expected markdown content on success
  - raises SmritiToolError with useful context on failure
"""
from __future__ import annotations

import pytest

from smriti_cli import mcp_server
from smriti_cli.client import SmritiError
from smriti_cli.mcp_server import SmritiToolError


# ── smriti_list_spaces ──────────────────────────────────────────────────


def test_list_spaces_happy_path(mock_client):
    mock_client.list_spaces.return_value = [
        {
            "id": "11111111-2222-3333-4444-555555555555",
            "name": "alpha",
            "description": "first space",
        },
        {
            "id": "99999999-8888-7777-6666-555555555555",
            "name": "beta",
            "description": "",
        },
    ]

    result = mcp_server.smriti_list_spaces()

    assert "alpha" in result
    assert "beta" in result
    assert "11111111-2222" in result
    assert mock_client.list_spaces.call_count == 1


def test_list_spaces_error_raises_tool_error(mock_client):
    mock_client.list_spaces.side_effect = SmritiError(
        "GET /api/v2/repos failed: HTTP 500 — internal error",
        status=500,
    )

    with pytest.raises(SmritiToolError) as excinfo:
        mcp_server.smriti_list_spaces()

    msg = str(excinfo.value)
    assert "HTTP 500" in msg
    assert "internal error" in msg


# ── smriti_state ────────────────────────────────────────────────────────


def _space_dict(**overrides):
    base = {
        "id": "space-uuid",
        "name": "my-project",
        "description": "A test project.",
        "created_at": "2026-04-11T12:00:00Z",
        "updated_at": "2026-04-11T12:00:00Z",
    }
    base.update(overrides)
    return base


def _commit_dict(**overrides):
    base = {
        "id": "commit-uuid",
        "repo_id": "space-uuid",
        "commit_hash": "abcdef1234567890",
        "parent_commit_id": None,
        "branch_name": "main",
        "author_agent": "codex-test",
        "project_root": "/tmp/project",
        "message": "Base design",
        "summary": "Getting started.",
        "objective": "Build the thing.",
        "decisions": ["Use stdlib"],
        "assumptions": ["Python 3.11+"],
        "tasks": ["Write tests"],
        "open_questions": [],
        "entities": ["stdlib"],
        "artifacts": [],
        "created_at": "2026-04-11T12:00:00Z",
    }
    base.update(overrides)
    return base


def test_state_happy_path_main_only(mock_client):
    """Legacy two-call path via main_only=True: get_head + get_commit.

    The default path (one call to get_space_state) is covered by
    test_state_multi_branch.py — this test preserves explicit
    coverage of the main_only fallback."""
    mock_client.resolve_space.return_value = _space_dict()
    mock_client.get_head.return_value = {
        "commit_id": "commit-uuid",
        "commit_hash": "abcdef1234567890",
        "created_at": "2026-04-11T12:00:00Z",
    }
    mock_client.get_commit.return_value = _commit_dict()

    result = mcp_server.smriti_state(space="my-project", main_only=True)

    assert "my-project" in result
    assert "Build the thing" in result
    assert "Use stdlib" in result
    # Legacy path uses the old two-call sequence.
    mock_client.resolve_space.assert_called_once_with("my-project")
    mock_client.get_head.assert_called_once()
    mock_client.get_commit.assert_called_once_with("commit-uuid")
    mock_client.get_space_state.assert_not_called()


def test_state_no_checkpoints_short_circuits_main_only(mock_client):
    """Legacy path empty-space: get_head returns no commit_id, tool
    short-circuits with the empty-state message without calling
    get_commit."""
    mock_client.resolve_space.return_value = _space_dict()
    mock_client.get_head.return_value = {"commit_id": None}

    result = mcp_server.smriti_state(space="my-project", main_only=True)

    assert "my-project" in result
    assert "No checkpoints yet" in result
    assert mock_client.get_commit.call_count == 0


def test_state_unknown_space_raises(mock_client):
    mock_client.resolve_space.side_effect = SmritiError(
        "No space found matching 'ghost'"
    )

    with pytest.raises(SmritiToolError):
        mcp_server.smriti_state(space="ghost")


# ── smriti_show_checkpoint ─────────────────────────────────────────────


def test_show_checkpoint_happy_path(mock_client):
    mock_client.get_commit.return_value = _commit_dict(message="Shipped v1")

    result = mcp_server.smriti_show_checkpoint(checkpoint_id="commit-uuid")

    assert "Shipped v1" in result
    mock_client.get_commit.assert_called_once_with("commit-uuid")


def test_show_checkpoint_not_found(mock_client):
    mock_client.get_commit.side_effect = SmritiError(
        "GET /api/v2/commits/ghost failed: HTTP 404 — Commit not found",
        status=404,
    )

    with pytest.raises(SmritiToolError) as excinfo:
        mcp_server.smriti_show_checkpoint(checkpoint_id="ghost")

    assert "HTTP 404" in str(excinfo.value)


# ── smriti_list_checkpoints ─────────────────────────────────────────────


def test_list_checkpoints_happy_path(mock_client):
    mock_client.resolve_space.return_value = _space_dict()
    mock_client.list_commits.return_value = [
        _commit_dict(
            id="11111111-1111-4111-8111-111111111111",
            commit_hash="aaaa1111" * 8,
            message="First",
        ),
        _commit_dict(
            id="22222222-2222-4222-8222-222222222222",
            commit_hash="bbbb2222" * 8,
            message="Second",
        ),
    ]

    result = mcp_server.smriti_list_checkpoints(space="my-project")

    assert "First" in result
    assert "Second" in result
    # Full UUIDs must be in the output so agents can pass them into
    # smriti_fork / smriti_compare / smriti_restore without a second
    # round-trip to the backend.
    assert "11111111-1111-4111-8111-111111111111" in result
    assert "22222222-2222-4222-8222-222222222222" in result
    mock_client.list_commits.assert_called_once_with("space-uuid", branch=None)


def test_list_checkpoints_with_branch_filter(mock_client):
    mock_client.resolve_space.return_value = _space_dict()
    mock_client.list_commits.return_value = []

    mcp_server.smriti_list_checkpoints(space="my-project", branch="experiment")

    mock_client.list_commits.assert_called_once_with("space-uuid", branch="experiment")


# ── smriti_review_checkpoint ───────────────────────────────────────────


def test_review_checkpoint_happy_path(mock_client):
    mock_client.review_checkpoint.return_value = {
        "issues": [
            {
                "type": "contradiction",
                "description": "Decision 1 conflicts with assumption 2.",
            }
        ],
        "suggestions": ["Reconcile the timing assumption"],
    }

    result = mcp_server.smriti_review_checkpoint(checkpoint_id="commit-uuid")

    assert "contradiction" in result.lower() or "Possible contradiction" in result
    assert "Reconcile the timing assumption" in result
    mock_client.review_checkpoint.assert_called_once_with("commit-uuid")


def test_review_checkpoint_error(mock_client):
    mock_client.review_checkpoint.side_effect = SmritiError(
        "POST /api/v5/checkpoint/ghost/review failed: HTTP 404 — Checkpoint not found",
        status=404,
    )

    with pytest.raises(SmritiToolError):
        mcp_server.smriti_review_checkpoint(checkpoint_id="ghost")


# ── smriti_restore ──────────────────────────────────────────────────────


def test_restore_happy_path(mock_client):
    mock_client.get_commit.return_value = _commit_dict()
    mock_client.get_space.return_value = _space_dict()

    result = mcp_server.smriti_restore(checkpoint_id="commit-uuid")

    assert "Continuation brief for checkpoint" in result
    assert "abcdef1" in result  # short hash
    assert "Build the thing" in result
    mock_client.get_commit.assert_called_once_with("commit-uuid")
    mock_client.get_space.assert_called_once_with("space-uuid")


def test_restore_checkpoint_not_found(mock_client):
    mock_client.get_commit.side_effect = SmritiError(
        "GET /api/v2/commits/ghost failed: HTTP 404 — Commit not found",
        status=404,
    )

    with pytest.raises(SmritiToolError):
        mcp_server.smriti_restore(checkpoint_id="ghost")


# ── smriti_compare ──────────────────────────────────────────────────────


def test_compare_happy_path(mock_client):
    mock_client.compare_checkpoints.return_value = {
        "checkpoint_a": {
            "commit_hash": "aaaaaaaaaaaaaaaa",
            "message": "Main impl",
            "branch_name": "main",
        },
        "checkpoint_b": {
            "commit_hash": "bbbbbbbbbbbbbbbb",
            "message": "Alternative",
            "branch_name": "experiment",
        },
        "diff": {
            "common_ancestor_commit_id": "parent-uuid",
            "summary_a": "Summary A",
            "summary_b": "Summary B",
            "objective_a": "Same objective",
            "objective_b": "Same objective",
            "decisions_only_a": ["Use click"],
            "decisions_only_b": ["Use argparse"],
            "decisions_shared": ["Ship a CLI"],
            "assumptions_only_a": [],
            "assumptions_only_b": [],
            "assumptions_shared": [],
            "tasks_only_a": [],
            "tasks_only_b": [],
            "tasks_shared": [],
        },
    }

    result = mcp_server.smriti_compare(
        checkpoint_a="aaaa-uuid",
        checkpoint_b="bbbb-uuid",
    )

    assert "parent-uuid" in result
    assert "Use click" in result
    assert "Use argparse" in result
    assert "Ship a CLI" in result
    mock_client.compare_checkpoints.assert_called_once_with("aaaa-uuid", "bbbb-uuid")


def test_compare_error(mock_client):
    mock_client.compare_checkpoints.side_effect = SmritiError(
        "GET /api/v5/lineage/... failed: HTTP 404 — Checkpoint not found",
        status=404,
    )

    with pytest.raises(SmritiToolError):
        mcp_server.smriti_compare(checkpoint_a="ghost", checkpoint_b="also-ghost")


# ── smriti_create_space ────────────────────────────────────────────────


def test_create_space_happy_path(mock_client):
    mock_client.create_space.return_value = {
        "id": "new-space-uuid",
        "name": "my-new-project",
    }

    result = mcp_server.smriti_create_space(
        name="my-new-project",
        description="Just getting started",
    )

    assert "new-space-uuid" in result
    assert "my-new-project" in result
    mock_client.create_space.assert_called_once_with("my-new-project", "Just getting started")


def test_create_space_error(mock_client):
    mock_client.create_space.side_effect = SmritiError(
        "POST /api/v2/repos failed: HTTP 500 — database error",
        status=500,
    )

    with pytest.raises(SmritiToolError) as excinfo:
        mcp_server.smriti_create_space(name="doomed")

    assert "HTTP 500" in str(excinfo.value)


# ── smriti_fork ─────────────────────────────────────────────────────────


def test_fork_happy_path(mock_client):
    mock_client.get_commit.return_value = _commit_dict()
    mock_client.fork_session.return_value = {
        "session_id": "fork-session-uuid",
        "branch_name": "experiment",
        "forked_from_checkpoint_id": "commit-uuid",
        "history_base_seq": 0,
    }

    result = mcp_server.smriti_fork(
        checkpoint_id="commit-uuid",
        branch="experiment",
    )

    assert "Forked from" in result
    assert "experiment" in result
    assert "fork-session-uuid" in result
    mock_client.fork_session.assert_called_once_with(
        space_id="space-uuid",
        checkpoint_id="commit-uuid",
        branch_name="experiment",
    )


def test_fork_checkpoint_not_found(mock_client):
    mock_client.get_commit.side_effect = SmritiError(
        "GET /api/v2/commits/ghost failed: HTTP 404 — Commit not found",
        status=404,
    )

    with pytest.raises(SmritiToolError):
        mcp_server.smriti_fork(checkpoint_id="ghost")


# ── smriti_create_checkpoint ───────────────────────────────────────────


def _extracted_payload():
    """Default canned response from extract_checkpoint_content that
    matches MockAdapter's canned JSON shape (minus the issues/suggestions
    fields which the extract endpoint strips)."""
    return {
        "title": "Settled on Pydantic",
        "objective": "State validation",
        "summary": "We decided to use Pydantic BaseModel for runtime state.",
        "decisions": ["Use BaseModel"],
        "assumptions": ["Latency is acceptable"],
        "tasks": ["Benchmark the validator"],
        "open_questions": ["How to handle mutation"],
        "entities": ["Pydantic"],
        "artifacts": [],
    }


def test_create_checkpoint_extract_happy_path(mock_client):
    mock_client.resolve_space.return_value = _space_dict()
    mock_client.extract_checkpoint_content.return_value = _extracted_payload()
    mock_client.create_session.return_value = {"id": "new-session-uuid"}
    mock_client.create_chat_commit.return_value = {
        "id": "commit-uuid",
        "commit_hash": "abcdef1234567890",
        "message": "Settled on Pydantic",
        "branch_name": "main",
    }

    result = mcp_server.smriti_create_checkpoint(
        space="my-project",
        content="# We decided to use Pydantic\n\n- BaseModel works well",
    )

    assert "Created checkpoint `abcdef1`" in result
    assert "Settled on Pydantic" in result
    assert "main" in result

    mock_client.extract_checkpoint_content.assert_called_once()
    mock_client.create_session.assert_called_once()
    mock_client.create_chat_commit.assert_called_once()

    payload = mock_client.create_chat_commit.call_args[0][0]
    assert payload["repo_id"] == "space-uuid"
    assert payload["session_id"] == "new-session-uuid"
    assert payload["message"] == "Settled on Pydantic"
    assert payload["decisions"] == ["Use BaseModel"]
    # empty project_root / author_agent defaults don't appear in payload
    assert "project_root" not in payload
    assert "author_agent" not in payload


def test_create_checkpoint_existing_session_skips_create(mock_client):
    mock_client.resolve_space.return_value = _space_dict()
    mock_client.extract_checkpoint_content.return_value = _extracted_payload()
    mock_client.create_chat_commit.return_value = {
        "commit_hash": "aaaa1111" * 8,
        "message": "Settled on Pydantic",
        "branch_name": "experiment",
    }

    mcp_server.smriti_create_checkpoint(
        space="my-project",
        content="# Design\n\n- decision x",
        session="existing-session-uuid",
    )

    # create_session must NOT be called when `session` is provided
    mock_client.create_session.assert_not_called()
    mock_client.create_chat_commit.assert_called_once()
    payload = mock_client.create_chat_commit.call_args[0][0]
    assert payload["session_id"] == "existing-session-uuid"


def test_create_checkpoint_dry_run_returns_preview_without_writing(mock_client):
    mock_client.resolve_space.return_value = _space_dict()
    mock_client.extract_checkpoint_content.return_value = _extracted_payload()

    result = mcp_server.smriti_create_checkpoint(
        space="my-project",
        content="# Design\n\n- decision x",
        dry_run=True,
    )

    assert "Dry run" in result
    assert "```json" in result
    assert "Use BaseModel" in result  # extracted decision inside the JSON preview

    # No session or commit calls in dry-run mode
    mock_client.create_session.assert_not_called()
    mock_client.create_chat_commit.assert_not_called()


def test_create_checkpoint_with_author_agent_and_project_root(mock_client):
    mock_client.resolve_space.return_value = _space_dict()
    mock_client.extract_checkpoint_content.return_value = _extracted_payload()
    mock_client.create_session.return_value = {"id": "sess"}
    mock_client.create_chat_commit.return_value = {
        "commit_hash": "aaaa" * 16,
        "message": "Settled on Pydantic",
        "branch_name": "main",
    }

    mcp_server.smriti_create_checkpoint(
        space="my-project",
        content="# doc",
        author_agent="claude-code",
        project_root="/home/user/projects/foo",
    )

    payload = mock_client.create_chat_commit.call_args[0][0]
    assert payload["author_agent"] == "claude-code"
    assert payload["project_root"] == "/home/user/projects/foo"


def test_create_checkpoint_empty_content_raises_before_any_client_call(mock_client):
    with pytest.raises(SmritiToolError) as excinfo:
        mcp_server.smriti_create_checkpoint(space="my-project", content="   \n  ")

    assert "non-empty" in str(excinfo.value).lower()
    # Must fail before any client call so an empty content cannot touch the backend
    mock_client.resolve_space.assert_not_called()
    mock_client.extract_checkpoint_content.assert_not_called()


def test_create_checkpoint_extract_error(mock_client):
    mock_client.resolve_space.return_value = _space_dict()
    mock_client.extract_checkpoint_content.side_effect = SmritiError(
        "POST /api/v5/checkpoint/extract failed: HTTP 502 — provider error",
        status=502,
    )

    with pytest.raises(SmritiToolError) as excinfo:
        mcp_server.smriti_create_checkpoint(space="my-project", content="# doc")

    assert "HTTP 502" in str(excinfo.value)


# ── smriti_delete_space ────────────────────────────────────────────────


def test_delete_space_happy_path(mock_client):
    mock_client.resolve_space.return_value = _space_dict()
    mock_client.list_commits.return_value = [_commit_dict(), _commit_dict()]
    mock_client.delete_space.return_value = None

    result = mcp_server.smriti_delete_space(space="my-project")

    assert "Deleted space 'my-project'" in result
    assert "2 checkpoint" in result  # commit count included
    mock_client.delete_space.assert_called_once_with("space-uuid")


def test_delete_space_unknown_space(mock_client):
    mock_client.resolve_space.side_effect = SmritiError(
        "No space found matching 'ghost'"
    )

    with pytest.raises(SmritiToolError):
        mcp_server.smriti_delete_space(space="ghost")

    # delete_space never called because resolution failed first
    mock_client.delete_space.assert_not_called()


# ── smriti_delete_checkpoint ───────────────────────────────────────────


def test_delete_checkpoint_happy_path(mock_client):
    mock_client.get_commit.return_value = _commit_dict()
    mock_client.delete_commit.return_value = None

    result = mcp_server.smriti_delete_checkpoint(checkpoint_id="commit-uuid")

    assert "Deleted checkpoint `abcdef1`" in result
    assert "(cascade)" not in result  # non-cascade default
    mock_client.delete_commit.assert_called_once_with("commit-uuid", cascade=False)


def test_delete_checkpoint_cascade_happy_path(mock_client):
    mock_client.get_commit.return_value = _commit_dict()
    mock_client.delete_commit.return_value = None

    result = mcp_server.smriti_delete_checkpoint(
        checkpoint_id="commit-uuid",
        cascade=True,
    )

    assert "Deleted checkpoint `abcdef1` (cascade)" in result
    mock_client.delete_commit.assert_called_once_with("commit-uuid", cascade=True)


def test_delete_checkpoint_409_with_dependents_dict(mock_client):
    mock_client.get_commit.return_value = _commit_dict()
    mock_client.delete_commit.side_effect = SmritiError(
        "DELETE /api/v2/commits/commit-uuid failed: HTTP 409 — has dependents",
        status=409,
        detail={
            "message": "Cannot delete — has dependents",
            "dependents": {
                "child_commits": [
                    {"id": "c1-uuid", "label": "Child A"},
                    {"id": "c2-uuid", "label": "Child B"},
                ],
                "forked_sessions": [
                    {"id": "s1-uuid", "label": "experiment"},
                ],
            },
        },
    )

    with pytest.raises(SmritiToolError) as excinfo:
        mcp_server.smriti_delete_checkpoint(checkpoint_id="commit-uuid")

    msg = str(excinfo.value)
    assert "Refusing to delete" in msg
    assert "child commit: Child A" in msg
    assert "child commit: Child B" in msg
    assert "forked session: experiment" in msg
    assert "cascade=true" in msg.lower()


def test_delete_checkpoint_409_with_non_dict_detail_falls_back(mock_client):
    """If the 409 detail isn't a dict (unexpected backend shape), the tool
    falls back to the generic _raise_from error format."""
    mock_client.get_commit.return_value = _commit_dict()
    mock_client.delete_commit.side_effect = SmritiError(
        "conflict",
        status=409,
        detail="plain string",  # not a dict
    )

    with pytest.raises(SmritiToolError) as excinfo:
        mcp_server.smriti_delete_checkpoint(checkpoint_id="commit-uuid")

    msg = str(excinfo.value)
    assert "HTTP 409" in msg
    assert "conflict" in msg


def test_delete_checkpoint_not_found(mock_client):
    mock_client.get_commit.side_effect = SmritiError(
        "GET /api/v2/commits/ghost failed: HTTP 404 — Commit not found",
        status=404,
    )

    with pytest.raises(SmritiToolError):
        mcp_server.smriti_delete_checkpoint(checkpoint_id="ghost")

    mock_client.delete_commit.assert_not_called()


# ── smriti_install_skill ───────────────────────────────────────────────


def test_install_skill_claude_code_returns_markdown():
    """The tool returns a markdown block with the rendered Claude Code
    skill pack and a pointer to the suggested destination path. It
    does NOT touch the client — the renderer is entirely local."""
    result = mcp_server.smriti_install_skill(target="claude-code")

    assert "Claude Code" in result
    assert ".claude/skills/smriti/SKILL.md" in result
    # Rendered content is wrapped in a fenced markdown block for the
    # agent to write via its host's file tools.
    assert "```markdown" in result
    # MCP-primary notation is in the body.
    assert "smriti_state(" in result
    # The "When NOT to checkpoint" section must make it through.
    assert "after every small step" in result.lower()


def test_install_skill_codex_returns_markdown():
    """Codex target uses CLI-primary notation."""
    result = mcp_server.smriti_install_skill(target="codex")

    assert "Codex" in result
    assert "AGENTS.md" in result
    assert "smriti state " in result
    # And the MCP-primary notation is absent.
    assert "smriti_state(space" not in result


def test_install_skill_unknown_target_raises():
    """Unknown target → SmritiToolError with the known targets listed."""
    with pytest.raises(SmritiToolError, match="Unknown skill pack target"):
        mcp_server.smriti_install_skill(target="windsurf-skill")


def test_install_skill_does_not_touch_client(mock_client):
    """Skill pack rendering is fully local; the tool must not call
    any SmritiClient method. Regression guard against accidentally
    turning the tool into a network call."""
    mcp_server.smriti_install_skill(target="claude-code")

    # No method on the mocked client should have been called.
    assert mock_client.method_calls == []
