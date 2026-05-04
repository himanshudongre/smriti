from __future__ import annotations

from smriti_cli import mcp_server


def _worktree_dict(**overrides):
    base = {
        "id": "11111111-2222-3333-4444-555555555555",
        "repo_id": "space-uuid",
        "agent": "claude-1",
        "path": "/tmp/worktree",
        "branch_name": "smriti/claude-1/abc12345",
        "base_commit_sha": "abc123",
        "status": "active",
        "created_at": "2026-05-04T00:00:00Z",
        "closed_at": None,
    }
    base.update(overrides)
    return base


def test_mcp_worktree_open_calls_client(mock_client):
    mock_client.resolve_space.return_value = {"id": "space-uuid", "name": "my-project"}
    mock_client.create_worktree.return_value = _worktree_dict(path="/tmp/wt")

    result = mcp_server.smriti_worktree_open(
        space="my-project",
        agent="claude-1",
        branch="feature/wt",
        base_commit="abc123",
        base_path="/tmp/wt",
    )

    assert "/tmp/wt" in result
    mock_client.resolve_space.assert_called_once_with("my-project")
    mock_client.create_worktree.assert_called_once_with(
        space_id="space-uuid",
        agent="claude-1",
        branch_name="feature/wt",
        base_commit_sha="abc123",
        base_path="/tmp/wt",
    )


def test_mcp_worktree_list_calls_client(mock_client):
    mock_client.resolve_space.return_value = {"id": "space-uuid", "name": "my-project"}
    mock_client.list_worktrees.return_value = [_worktree_dict()]

    result = mcp_server.smriti_worktree_list(
        space="my-project",
        include_closed=True,
    )

    assert "claude-1" in result
    mock_client.resolve_space.assert_called_once_with("my-project")
    mock_client.list_worktrees.assert_called_once_with(
        "space-uuid",
        include_closed=True,
    )


def test_mcp_worktree_list_renders_probe_data(mock_client):
    mock_client.resolve_space.return_value = {"id": "space-uuid", "name": "my-project"}
    mock_client.list_worktrees.return_value = [
        _worktree_dict(probe={"dirty_files": 3, "ahead": 0, "behind": 2})
    ]

    result = mcp_server.smriti_worktree_list(space="my-project")

    assert "3" in result
    assert "-2" in result


def test_mcp_worktree_show_calls_client(mock_client):
    mock_client.get_worktree.return_value = _worktree_dict()

    result = mcp_server.smriti_worktree_show("wt-uuid")

    assert "smriti/claude-1/abc12345" in result
    mock_client.get_worktree.assert_called_once_with("wt-uuid")


def test_mcp_worktree_close_calls_client(mock_client):
    mock_client.close_worktree.return_value = _worktree_dict(status="closed")

    result = mcp_server.smriti_worktree_close("wt-uuid", force=True)

    assert "Closed worktree" in result
    mock_client.close_worktree.assert_called_once_with("wt-uuid", force=True)


def test_mcp_claim_passes_worktree_id(mock_client):
    mock_client.resolve_space.return_value = {"id": "space-uuid", "name": "my-project"}
    mock_client.get_head.return_value = {"commit_id": "checkpoint-uuid"}
    mock_client.create_claim.return_value = {
        "id": "claim-uuid",
        "agent": "codex-local",
        "scope": "Implement V2",
        "branch_name": "worktree-v2-binding-and-enrichment",
        "intent_type": "implement",
    }

    result = mcp_server.smriti_claim(
        space="my-project",
        scope="Implement V2",
        agent="codex-local",
        branch="worktree-v2-binding-and-enrichment",
        task_id="v2-plan",
        worktree_id="wt-uuid",
    )

    assert "Claimed" in result
    mock_client.create_claim.assert_called_once_with(
        space_id="space-uuid",
        agent="codex-local",
        scope="Implement V2",
        branch_name="worktree-v2-binding-and-enrichment",
        base_commit_id="checkpoint-uuid",
        task_id="v2-plan",
        worktree_id="wt-uuid",
        intent_type="implement",
        ttl_hours=4.0,
    )
