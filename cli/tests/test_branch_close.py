from __future__ import annotations

import argparse
from unittest.mock import MagicMock

import pytest

from smriti_cli import main as cli_main
from smriti_cli import mcp_server
from smriti_cli.client import SmritiClient, SmritiError
from smriti_cli.mcp_server import SmritiToolError


def test_branch_close_parser_wiring():
    parser = cli_main._build_parser()

    args = parser.parse_args(
        [
            "branch",
            "close",
            "my-project",
            "feature/demo",
            "--disposition",
            "integrated",
        ]
    )

    assert args.command == "branch"
    assert args.subcommand == "close"
    assert args.space == "my-project"
    assert args.branch_name == "feature/demo"
    assert args.disposition == "integrated"
    assert args.func is cli_main.cmd_branch_close


def test_cmd_branch_close_prints_human_readable_result(capsys: pytest.CaptureFixture[str]):
    client = MagicMock(spec=SmritiClient)
    client.resolve_space.return_value = {"id": "space-uuid", "name": "my-project"}
    client.close_branch.return_value = {
        "branch_name": "feature/demo",
        "disposition": "integrated",
        "sessions_updated": 2,
    }
    args = argparse.Namespace(
        space="my-project",
        branch_name="feature/demo",
        disposition="integrated",
        json=False,
    )

    cli_main.cmd_branch_close(client, args)

    out = capsys.readouterr().out
    assert "feature/demo" in out
    assert "integrated" in out
    assert "2 session(s) updated" in out
    client.resolve_space.assert_called_once_with("my-project")
    client.close_branch.assert_called_once_with(
        "space-uuid", "feature/demo", "integrated"
    )


def test_cmd_branch_close_json_path():
    client = MagicMock(spec=SmritiClient)
    client.resolve_space.return_value = {"id": "space-uuid", "name": "my-project"}
    client.close_branch.return_value = {
        "branch_name": "feature/demo",
        "disposition": "abandoned",
        "sessions_updated": 1,
    }
    args = argparse.Namespace(
        space="my-project",
        branch_name="feature/demo",
        disposition="abandoned",
        json=True,
    )
    captured: list[dict] = []
    original = cli_main._print_json
    cli_main._print_json = captured.append
    try:
        cli_main.cmd_branch_close(client, args)
    finally:
        cli_main._print_json = original

    assert captured == [
        {
            "branch_name": "feature/demo",
            "disposition": "abandoned",
            "sessions_updated": 1,
        }
    ]


def test_mcp_close_branch_happy_path(mock_client):
    mock_client.resolve_space.return_value = {
        "id": "space-uuid",
        "name": "my-project",
    }
    mock_client.close_branch.return_value = {
        "branch_name": "feature/demo",
        "disposition": "active",
        "sessions_updated": 3,
    }

    result = mcp_server.smriti_close_branch(
        space="my-project",
        branch="feature/demo",
        disposition="active",
    )

    assert "feature/demo" in result
    assert "active" in result
    assert "3 session(s) updated" in result
    mock_client.resolve_space.assert_called_once_with("my-project")
    mock_client.close_branch.assert_called_once_with(
        "space-uuid", "feature/demo", "active"
    )


def test_mcp_close_branch_error_raises_tool_error(mock_client):
    mock_client.resolve_space.return_value = {
        "id": "space-uuid",
        "name": "my-project",
    }
    mock_client.close_branch.side_effect = SmritiError(
        "PATCH /api/v5/lineage/branches/disposition failed: HTTP 400 — invalid disposition",
        status=400,
    )

    with pytest.raises(SmritiToolError) as excinfo:
        mcp_server.smriti_close_branch(
            space="my-project",
            branch="feature/demo",
            disposition="not-a-status",
        )

    msg = str(excinfo.value)
    assert "HTTP 400" in msg
    assert "invalid disposition" in msg
