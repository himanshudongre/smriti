from __future__ import annotations

import argparse
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from smriti_cli import main as cli_main
from smriti_cli.client import SmritiClient, SmritiError
from smriti_cli.formatters import format_project_current


def _space() -> dict:
    return {
        "id": "space-uuid",
        "name": "smriti-dev",
        "description": "Shared reasoning backend.",
    }


def _commit(**overrides) -> dict:
    base = {
        "id": "checkpoint-uuid",
        "repo_id": "space-uuid",
        "commit_hash": "abcdef1234567890",
        "branch_name": "main",
        "author_agent": "codex-local",
        "message": "Project Current State direction",
        "objective": "Make current project operation legible.",
        "summary": "Current-state surface is the next product packaging layer.",
        "tasks": [
            {
                "id": "current-cli",
                "text": "Add Project Current State CLI surface",
                "intent_hint": "implement",
            },
            {
                "id": "current-review",
                "text": "Review the current-state UI",
                "intent_hint": "review",
                "blocked_by": "current-ui",
            },
        ],
        "open_questions": ["Should this live in state or current?"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    base.update(overrides)
    return base


def _current_payload() -> dict:
    return {
        "space_id": "space-uuid",
        "name": "smriti-dev",
        "description": "Shared reasoning backend.",
        "current_direction": "Make current project operation legible.",
        "latest_checkpoint": {
            "commit_hash": "abcdef1234567890",
            "message": "Project Current State direction",
            "author_agent": "codex-local",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        "counts": {
            "checkpoints": 74,
            "active_claims": 1,
            "active_branches": 0,
            "open_tasks": 2,
            "milestones": 2,
            "attention": 1,
        },
        "attention": [
            {"severity": "question", "message": "1 open question on latest checkpoint."}
        ],
        "active_work": [
            {
                "agent": "codex-local",
                "intent_type": "implement",
                "task_id": "current-cli",
                "branch_name": "codex/project-current-state-cli",
                "scope": "Add Project Current State CLI surface",
                "claimed_at": datetime.now(timezone.utc).isoformat(),
            }
        ],
        "recent_milestones": [
            {
                "commit_hash": "1111222233334444",
                "note": "First autonomous task selection worked.",
                "author": "founder",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ],
        "open_tasks_by_intent": {
            "implement": [
                {
                    "id": "current-cli",
                    "text": "Add Project Current State CLI surface",
                    "intent_hint": "implement",
                }
            ],
            "review": [
                {
                    "id": "current-review",
                    "text": "Review the current-state UI",
                    "intent_hint": "review",
                    "blocked_by": "current-ui",
                }
            ],
        },
        "recent_activity": [
            {
                "commit_hash": "abcdef1234567890",
                "author_agent": "codex-local",
                "message": "Project Current State direction",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ],
    }


def test_current_parser_wiring():
    parser = cli_main._build_parser()

    args = parser.parse_args(["current", "smriti-dev"])

    assert args.command == "current"
    assert args.space == "smriti-dev"
    assert args.func is cli_main.cmd_current


def test_format_project_current_renders_contract_sections():
    out = format_project_current(_current_payload())

    assert "# smriti-dev — current state" in out
    assert "## Counts" in out
    assert "active claims: 1" in out
    assert "## Needs attention" in out
    assert "[question] 1 open question" in out
    assert "## Active work" in out
    assert "task `current-cli`" in out
    assert "## Recent milestones" in out
    assert "First autonomous task selection worked." in out
    assert "## Open tasks by intent" in out
    assert "### implement" in out
    assert "`current-review` Review the current-state UI → blocked by: current-ui" in out
    assert "## Recent activity" in out


def test_format_project_current_prefers_objective_for_direction():
    payload = _current_payload()
    payload["current_direction"] = {
        "objective": "Add per-client rate limiting before launch.",
        "headline": "Load test passes",
        "summary": "Long backend-provided summary that may be preview-clipped.",
    }

    out = format_project_current(payload)

    assert "Add per-client rate limiting before launch." in out
    assert "Long backend-provided summary" not in out


def test_cmd_current_prefers_backend_payload(capsys: pytest.CaptureFixture[str]):
    client = MagicMock(spec=SmritiClient)
    client.resolve_space.return_value = _space()
    client.get_current_state.return_value = _current_payload()
    args = argparse.Namespace(space="smriti-dev", json=False)

    cli_main.cmd_current(client, args)

    out = capsys.readouterr().out
    assert "# smriti-dev — current state" in out
    assert "Add Project Current State CLI surface" in out
    client.resolve_space.assert_called_once_with("smriti-dev")
    client.get_current_state.assert_called_once_with("space-uuid")
    client.get_space_state.assert_not_called()


def test_cmd_current_json_outputs_backend_payload():
    client = MagicMock(spec=SmritiClient)
    client.resolve_space.return_value = _space()
    payload = _current_payload()
    client.get_current_state.return_value = payload
    args = argparse.Namespace(space="smriti-dev", json=True)
    captured: list[dict] = []
    original = cli_main._print_json
    cli_main._print_json = captured.append
    try:
        cli_main.cmd_current(client, args)
    finally:
        cli_main._print_json = original

    assert captured == [payload]


def test_cmd_current_falls_back_to_shipped_endpoints(capsys: pytest.CaptureFixture[str]):
    client = MagicMock(spec=SmritiClient)
    client.resolve_space.return_value = _space()
    client.get_current_state.side_effect = SmritiError(
        "endpoint missing", status=404
    )
    commit = _commit()
    client.get_space_state.return_value = {
        "commit": commit,
        "head": {"commit_id": "checkpoint-uuid"},
        "active_claims": [
            {
                "agent": "codex-local",
                "intent_type": "implement",
                "task_id": "current-cli",
                "branch_name": "codex/project-current-state-cli",
                "scope": "Add Project Current State CLI surface",
                "claimed_at": datetime.now(timezone.utc).isoformat(),
            }
        ],
        "active_branches": [],
        "divergence": None,
    }
    client.list_commits.return_value = [
        {
            **commit,
            "metadata": {
                "notes": [
                    {
                        "kind": "milestone",
                        "text": "Current-state direction chosen.",
                        "author": "founder",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                ]
            },
        }
    ]
    client.get_space_metrics.return_value = {
        "coordination": {"total_checkpoints": 74},
        "state_quality": {"milestone_count": 3},
        "branches": {"active": 0},
    }
    args = argparse.Namespace(space="smriti-dev", json=False)

    cli_main.cmd_current(client, args)

    out = capsys.readouterr().out
    assert "Make current project operation legible." in out
    assert "checkpoints: 74" in out
    assert "active claims: 1" in out
    assert "open tasks: 2" in out
    assert "[question] 1 open question" in out
    assert "Current-state direction chosen." in out
    assert "### implement" in out
    assert "`current-cli` Add Project Current State CLI surface" in out
    client.get_space_state.assert_called_once_with("space-uuid")
    client.list_commits.assert_called_once_with("space-uuid")
    client.get_space_metrics.assert_called_once_with("space-uuid")
