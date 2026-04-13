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
    return client


def test_init_parser_wiring():
    parser = cli_main._build_parser()
    args = parser.parse_args(["init", "my-project", "--description", "Test"])
    assert args.command == "init"
    assert args.space == "my-project"
    assert args.description == "Test"
    assert args.func is cli_main.cmd_init


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
    assert "test-project" in settings["hooks"]["SessionStart"][0]["hooks"][0]["command"]


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
