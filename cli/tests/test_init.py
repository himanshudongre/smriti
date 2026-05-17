"""Tests for the smriti init command.

Covers:
- Parser wiring
- Space creation (new) and connection (existing)
- Skill pack installation for both targets
- AGENTS.md safety: skips when non-Smriti content exists
- SessionStart hook generation and idempotence
- Idempotent re-run (everything already configured)
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from smriti_cli import main as cli_main
from smriti_cli.client import SmritiClient


@pytest.fixture
def mock_client(monkeypatch):
    client = MagicMock(spec=SmritiClient)
    client.base_url = "http://localhost:8000"
    client.list_spaces.return_value = []
    monkeypatch.setattr(cli_main, "SmritiClient", lambda **kw: client)
    monkeypatch.setattr(
        cli_main,
        "_smriti_hook_executable",
        lambda: "/opt/smriti/bin/smriti",
    )
    monkeypatch.setattr(
        cli_main,
        "_smriti_mcp_executable",
        lambda: "/opt/smriti/bin/smriti-mcp",
    )
    return client


def test_init_parser_wiring():
    parser = cli_main._build_parser()
    args = parser.parse_args(["init", "my-project", "--description", "Test"])
    assert args.command == "init"
    assert args.space == "my-project"
    assert args.description == "Test"
    assert args.func is cli_main.cmd_init


def test_session_start_hook_command_shell_quotes(monkeypatch):
    monkeypatch.setattr(
        cli_main,
        "_smriti_hook_executable",
        lambda: "/Applications/Smriti Tools/bin/smriti",
    )

    command = cli_main._build_session_start_hook_command("http://localhost:8000")

    # Space-agnostic: the hook resolves the space from .smriti.json — no name embedded.
    assert command.startswith(
        "'/Applications/Smriti Tools/bin/smriti' --api-url "
        "http://localhost:8000 state --compact"
    )
    assert "backend/.venv/bin/smriti" not in command


def test_smriti_session_start_detector_handles_quoted_executable():
    entry = {
        "matcher": "startup",
        "hooks": [
            {
                "type": "command",
                "command": (
                    "'/Applications/Smriti Tools/bin/smriti' --api-url "
                    "http://localhost:8000 state p --compact 2>/dev/null"
                ),
            }
        ],
    }

    assert cli_main._is_smriti_session_start_entry(entry) is True


def test_init_creates_space_and_skill_packs(mock_client, tmp_path, monkeypatch):
    """Init with a fresh project: creates space, installs both skill packs."""
    monkeypatch.chdir(tmp_path)

    # Space doesn't exist — resolve fails, create succeeds
    from smriti_cli.client import SmritiError
    mock_client.resolve_space.side_effect = SmritiError("not found")
    mock_client.create_space.return_value = {
        "id": "new-space-uuid",
        "name": "test-project",
    }

    args = cli_main._build_parser().parse_args(["init", "test-project"])
    args.api_url = None
    cli_main.cmd_init(mock_client, args)

    # Space was created
    mock_client.create_space.assert_called_once_with(name="test-project", description="")

    # Claude skill pack was installed
    assert (tmp_path / ".claude" / "skills" / "smriti" / "SKILL.md").exists()

    # Codex skill pack was installed (no pre-existing AGENTS.md)
    assert (tmp_path / "AGENTS.md").exists()
    assert "smriti_skill_pack_version" in (tmp_path / "AGENTS.md").read_text()

    # SessionStart hook was generated
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert "SessionStart" in settings.get("hooks", {})
    command = settings["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert command.startswith(
        "/opt/smriti/bin/smriti --api-url "
        "http://localhost:8000 state --compact"
    )
    assert "backend/.venv/bin/smriti" not in command
    assert "--preview" not in command
    assert "test-project" not in command  # the hook is space-agnostic

    # init attaches the repo: .smriti.json records the repo → space binding
    record = json.loads((tmp_path / ".smriti.json").read_text())
    assert record["space"] == "test-project"
    assert record["space_id"] == "new-space-uuid"


def test_init_connects_existing_space(mock_client, tmp_path, monkeypatch):
    """When space already exists, init connects instead of creating."""
    monkeypatch.chdir(tmp_path)
    mock_client.resolve_space.return_value = {
        "id": "existing-uuid",
        "name": "my-project",
    }

    args = cli_main._build_parser().parse_args(["init", "my-project"])
    args.api_url = None
    cli_main.cmd_init(mock_client, args)

    mock_client.create_space.assert_not_called()


def test_init_skips_agents_md_with_existing_non_smriti_content(
    mock_client, tmp_path, monkeypatch
):
    """AGENTS.md with non-Smriti content should NOT be overwritten."""
    monkeypatch.chdir(tmp_path)
    mock_client.resolve_space.return_value = {"id": "uuid", "name": "p"}

    # Pre-existing AGENTS.md with user content (no smriti frontmatter)
    agents = tmp_path / "AGENTS.md"
    agents.write_text("# My Custom Agent Instructions\n\nDo not touch this.\n")

    args = cli_main._build_parser().parse_args(["init", "p"])
    args.api_url = None
    cli_main.cmd_init(mock_client, args)

    # AGENTS.md should be untouched
    assert "My Custom Agent Instructions" in agents.read_text()
    assert "smriti_skill_pack_version" not in agents.read_text()


def test_init_upgrades_existing_smriti_agents_md(
    mock_client, tmp_path, monkeypatch
):
    """AGENTS.md that IS a Smriti skill pack should be upgraded normally."""
    monkeypatch.chdir(tmp_path)
    mock_client.resolve_space.return_value = {"id": "uuid", "name": "p"}

    agents = tmp_path / "AGENTS.md"
    agents.write_text("---\nsmriti_skill_pack_version: 0.1\n---\nOld content\n")

    args = cli_main._build_parser().parse_args(["init", "p"])
    args.api_url = None
    cli_main.cmd_init(mock_client, args)

    # Should be upgraded (0.1 < current version)
    content = agents.read_text()
    assert "smriti_skill_pack_version" in content
    assert "0.1" not in content  # upgraded past 0.1


def test_init_idempotent_second_run(mock_client, tmp_path, monkeypatch):
    """Running init twice should not error or duplicate anything."""
    monkeypatch.chdir(tmp_path)
    mock_client.resolve_space.return_value = {"id": "uuid", "name": "p"}

    args = cli_main._build_parser().parse_args(["init", "p"])
    args.api_url = None

    # First run
    cli_main.cmd_init(mock_client, args)

    # Second run — should succeed silently
    cli_main.cmd_init(mock_client, args)

    # Hook still has exactly 3 SessionStart entries (not 6)
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert len(settings["hooks"]["SessionStart"]) == 3


def test_init_updates_stale_smriti_session_start_hook(
    mock_client, tmp_path, monkeypatch
):
    """Repo-relative / preview-mode hooks should be upgraded in place."""
    monkeypatch.chdir(tmp_path)
    mock_client.resolve_space.return_value = {"id": "uuid", "name": "p"}

    settings_dir = tmp_path / ".claude"
    settings_dir.mkdir()
    settings_file = settings_dir / "settings.json"
    settings_file.write_text(
        json.dumps({
            "hooks": {
                "SessionStart": [
                    {
                        "matcher": "startup",
                        "hooks": [
                            {
                                "type": "command",
                                "command": (
                                    "backend/.venv/bin/smriti state p --preview "
                                    "2>/dev/null || echo old"
                                ),
                            }
                        ],
                    }
                ]
            }
        })
    )

    args = cli_main._build_parser().parse_args(["init", "p"])
    args.api_url = None
    cli_main.cmd_init(mock_client, args)

    settings = json.loads(settings_file.read_text())
    commands = [
        entry["hooks"][0]["command"]
        for entry in settings["hooks"]["SessionStart"]
    ]
    assert len(commands) == 3
    assert all(
        command.startswith(
            "/opt/smriti/bin/smriti --api-url http://localhost:8000 state --compact"
        )
        for command in commands
    )
    assert all("backend/.venv/bin/smriti" not in command for command in commands)
    assert all("--preview" not in command for command in commands)


def test_init_preserves_unrelated_session_start_hooks(
    mock_client, tmp_path, monkeypatch
):
    """User-managed SessionStart hooks should survive init."""
    monkeypatch.chdir(tmp_path)
    mock_client.resolve_space.return_value = {"id": "uuid", "name": "p"}

    settings_dir = tmp_path / ".claude"
    settings_dir.mkdir()
    settings_file = settings_dir / "settings.json"
    user_hook = {
        "matcher": "startup",
        "hooks": [{"type": "command", "command": "echo user hook"}],
    }
    settings_file.write_text(json.dumps({"hooks": {"SessionStart": [user_hook]}}))

    args = cli_main._build_parser().parse_args(["init", "p"])
    args.api_url = None
    cli_main.cmd_init(mock_client, args)

    settings = json.loads(settings_file.read_text())
    entries = settings["hooks"]["SessionStart"]
    assert entries[0] == user_hook
    assert len(entries) == 4
    assert any(
        entry["hooks"][0]["command"].startswith(
            "/opt/smriti/bin/smriti --api-url http://localhost:8000 state --compact"
        )
        for entry in entries[1:]
    )


def test_init_json_preserves_api_url_for_hooks_and_mcp(
    mock_client, tmp_path, monkeypatch, capsys
):
    """Custom backend URLs should survive generated hooks and MCP hints."""
    monkeypatch.chdir(tmp_path)
    mock_client.base_url = "http://127.0.0.1:8999"
    mock_client.resolve_space.return_value = {"id": "uuid", "name": "p"}

    args = cli_main._build_parser().parse_args([
        "--api-url",
        "http://127.0.0.1:8999",
        "init",
        "p",
        "--json",
    ])
    cli_main.cmd_init(mock_client, args)

    payload = json.loads(capsys.readouterr().out)
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    command = settings["hooks"]["SessionStart"][0]["hooks"][0]["command"]

    assert "--api-url http://127.0.0.1:8999" in command
    assert any("/opt/smriti/bin/smriti-mcp" in step for step in payload["next_steps"])
    assert any("http://127.0.0.1:8999" in step for step in payload["next_steps"])


def test_init_merges_into_existing_settings_json(
    mock_client, tmp_path, monkeypatch
):
    """If .claude/settings.json exists with other keys, init merges without overwriting."""
    monkeypatch.chdir(tmp_path)
    mock_client.resolve_space.return_value = {"id": "uuid", "name": "p"}

    settings_dir = tmp_path / ".claude"
    settings_dir.mkdir()
    settings_file = settings_dir / "settings.json"
    settings_file.write_text(json.dumps({"permissions": {"allow": ["Bash"]}}))

    args = cli_main._build_parser().parse_args(["init", "p"])
    args.api_url = None
    cli_main.cmd_init(mock_client, args)

    settings = json.loads(settings_file.read_text())
    # Original key preserved
    assert settings["permissions"]["allow"] == ["Bash"]
    # Hook added
    assert "SessionStart" in settings["hooks"]
