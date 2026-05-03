from __future__ import annotations

import argparse
from unittest.mock import MagicMock

import pytest

from smriti_cli import main as cli_main
from smriti_cli.client import SmritiClient


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


def test_worktree_open_parser_wiring():
    parser = cli_main._build_parser()

    args = parser.parse_args(
        [
            "worktree",
            "open",
            "my-project",
            "--agent",
            "claude-1",
            "--branch",
            "feature/wt",
            "--base-commit",
            "abc123",
            "--base-path",
            "/tmp/wt",
        ]
    )

    assert args.command == "worktree"
    assert args.subcommand == "open"
    assert args.space == "my-project"
    assert args.agent == "claude-1"
    assert args.branch == "feature/wt"
    assert args.base_commit == "abc123"
    assert args.base_path == "/tmp/wt"
    assert args.func is cli_main.cmd_worktree_open


def test_cmd_worktree_open_calls_client_and_prints_path(capsys: pytest.CaptureFixture[str]):
    client = MagicMock(spec=SmritiClient)
    client.resolve_space.return_value = {"id": "space-uuid", "name": "my-project"}
    client.create_worktree.return_value = _worktree_dict(path="/tmp/wt")
    args = argparse.Namespace(
        space="my-project",
        agent="claude-1",
        branch=None,
        base_commit=None,
        base_path=None,
        json=False,
    )

    cli_main.cmd_worktree_open(client, args)

    out = capsys.readouterr().out
    assert out == "/tmp/wt\n"
    client.resolve_space.assert_called_once_with("my-project")
    client.create_worktree.assert_called_once_with(
        space_id="space-uuid",
        agent="claude-1",
        branch_name=None,
        base_commit_sha=None,
        base_path=None,
    )


def test_cmd_worktree_open_json_path():
    client = MagicMock(spec=SmritiClient)
    client.resolve_space.return_value = {"id": "space-uuid", "name": "my-project"}
    worktree = _worktree_dict(path="/tmp/json-wt")
    client.create_worktree.return_value = worktree
    args = argparse.Namespace(
        space="my-project",
        agent="claude-1",
        branch="feature/wt",
        base_commit="abc123",
        base_path="/tmp/json-wt",
        json=True,
    )
    captured: list[dict] = []
    original = cli_main._print_json
    cli_main._print_json = captured.append
    try:
        cli_main.cmd_worktree_open(client, args)
    finally:
        cli_main._print_json = original

    assert captured == [worktree]
    client.create_worktree.assert_called_once_with(
        space_id="space-uuid",
        agent="claude-1",
        branch_name="feature/wt",
        base_commit_sha="abc123",
        base_path="/tmp/json-wt",
    )


def test_cmd_worktree_list_calls_client(capsys: pytest.CaptureFixture[str]):
    client = MagicMock(spec=SmritiClient)
    client.resolve_space.return_value = {"id": "space-uuid", "name": "my-project"}
    client.list_worktrees.return_value = [_worktree_dict()]
    args = argparse.Namespace(space="my-project", include_closed=False, json=False)

    cli_main.cmd_worktree_list(client, args)

    out = capsys.readouterr().out
    assert "AGENT" in out
    assert "claude-1" in out
    client.list_worktrees.assert_called_once_with("space-uuid", include_closed=False)


def test_cmd_worktree_show_calls_client(capsys: pytest.CaptureFixture[str]):
    client = MagicMock(spec=SmritiClient)
    client.get_worktree.return_value = _worktree_dict()
    args = argparse.Namespace(worktree_id="wt-uuid", json=False)

    cli_main.cmd_worktree_show(client, args)

    out = capsys.readouterr().out
    assert "branch: smriti/claude-1/abc12345" in out
    client.get_worktree.assert_called_once_with("wt-uuid")


def test_cmd_worktree_close_calls_client(capsys: pytest.CaptureFixture[str]):
    client = MagicMock(spec=SmritiClient)
    client.close_worktree.return_value = _worktree_dict(status="closed")
    args = argparse.Namespace(worktree_id="wt-uuid", force=True, json=False)

    cli_main.cmd_worktree_close(client, args)

    out = capsys.readouterr().out
    assert "Closed worktree" in out
    client.close_worktree.assert_called_once_with("wt-uuid", force=True)
