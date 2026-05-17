"""Tests for durable project attachment (`.smriti.json`) and CLI auto-resolution.

Covers:
- the attachment module — find (walk-up), read, write, malformed handling
- _resolve_space — explicit arg wins, attachment fallback, clear failure
- cmd_attach — bind to existing/new space, re-show the current attachment
- parser wiring — `attach`, and `<space>` optional on the daily-driver commands

Like the rest of cli/tests, these use MagicMock(spec=SmritiClient) and tmp_path —
no running backend required.
"""
from __future__ import annotations

import argparse
import json
from unittest.mock import MagicMock

import pytest

from smriti_cli import attachment
from smriti_cli import main as cli_main
from smriti_cli.client import SmritiClient, SmritiError


def _ns(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


# ── attachment module ────────────────────────────────────────────────────────


def test_write_and_read_attachment(tmp_path):
    path = attachment.write_attachment(tmp_path, "my-space", "space-uuid-1")
    assert path == tmp_path / ".smriti.json"
    record = attachment.read_attachment(tmp_path)
    assert record["space"] == "my-space"
    assert record["space_id"] == "space-uuid-1"
    assert record["version"] == attachment.ATTACHMENT_VERSION


def test_find_attachment_walks_up_from_subdirectory(tmp_path):
    attachment.write_attachment(tmp_path, "root-space")
    sub = tmp_path / "a" / "b" / "c"
    sub.mkdir(parents=True)
    found = attachment.find_attachment_file(sub)
    assert found == tmp_path / ".smriti.json"
    # And resolution works the same from the subdirectory.
    assert attachment.read_attachment(sub)["space"] == "root-space"


def test_read_attachment_none_when_absent(tmp_path):
    assert attachment.read_attachment(tmp_path) is None
    assert attachment.find_attachment_file(tmp_path) is None


def test_read_attachment_none_when_malformed(tmp_path):
    """A broken attachment file must read as 'not attached', never raise."""
    (tmp_path / ".smriti.json").write_text("{ not valid json")
    assert attachment.read_attachment(tmp_path) is None


def test_read_attachment_none_when_space_missing(tmp_path):
    (tmp_path / ".smriti.json").write_text(json.dumps({"version": 1}))
    assert attachment.read_attachment(tmp_path) is None


def test_write_attachment_overwrites(tmp_path):
    """Re-attaching a repo to a different space is supported."""
    attachment.write_attachment(tmp_path, "old-space", "old-id")
    attachment.write_attachment(tmp_path, "new-space", "new-id")
    record = attachment.read_attachment(tmp_path)
    assert record["space"] == "new-space"
    assert record["space_id"] == "new-id"


# ── _resolve_space ───────────────────────────────────────────────────────────


def test_resolve_space_explicit_arg_wins():
    client = MagicMock(spec=SmritiClient)
    client.resolve_space.return_value = {"id": "x", "name": "explicit"}
    result = cli_main._resolve_space(client, _ns(space="explicit"))
    assert result["name"] == "explicit"
    client.resolve_space.assert_called_once_with("explicit")


def test_resolve_space_falls_back_to_attachment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    attachment.write_attachment(tmp_path, "attached-space", "att-uuid")
    client = MagicMock(spec=SmritiClient)
    client.get_space.return_value = {"id": "att-uuid", "name": "attached-space"}
    result = cli_main._resolve_space(client, _ns(space=None))
    assert result["name"] == "attached-space"
    client.get_space.assert_called_once_with("att-uuid")


def test_resolve_space_attachment_id_miss_falls_back_to_name(tmp_path, monkeypatch):
    """A stale space_id (e.g. attachment read against another backend) must
    fall back to resolving by the portable space name."""
    monkeypatch.chdir(tmp_path)
    attachment.write_attachment(tmp_path, "attached-space", "stale-uuid")
    client = MagicMock(spec=SmritiClient)
    client.get_space.side_effect = SmritiError("not found", status=404)
    client.resolve_space.return_value = {"id": "real", "name": "attached-space"}
    result = cli_main._resolve_space(client, _ns(space=None))
    assert result["name"] == "attached-space"
    client.resolve_space.assert_called_once_with("attached-space")


def test_resolve_space_fails_clearly_when_unattached(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    client = MagicMock(spec=SmritiClient)
    with pytest.raises(SystemExit):
        cli_main._resolve_space(client, _ns(space=None))
    assert "attach" in capsys.readouterr().err.lower()


# ── cmd_attach ───────────────────────────────────────────────────────────────


def test_cmd_attach_binds_repo_to_existing_space(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = MagicMock(spec=SmritiClient)
    client.base_url = "http://localhost:8000"
    client.list_spaces.return_value = []
    client.resolve_space.return_value = {"id": "uuid-1", "name": "my-space"}

    cli_main.cmd_attach(client, _ns(space="my-space", description="", json=False))

    record = attachment.read_attachment(tmp_path)
    assert record["space"] == "my-space"
    assert record["space_id"] == "uuid-1"
    client.set_project_root.assert_called_once()
    client.create_space.assert_not_called()


def test_cmd_attach_creates_space_when_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = MagicMock(spec=SmritiClient)
    client.base_url = "http://localhost:8000"
    client.list_spaces.return_value = []
    client.resolve_space.side_effect = SmritiError("not found")
    client.create_space.return_value = {"id": "new-uuid", "name": "fresh"}

    cli_main.cmd_attach(client, _ns(space="fresh", description="", json=False))

    client.create_space.assert_called_once()
    assert attachment.read_attachment(tmp_path)["space"] == "fresh"


def test_cmd_attach_no_arg_shows_current_attachment(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    attachment.write_attachment(tmp_path, "bound-space", "bound-uuid")
    client = MagicMock(spec=SmritiClient)

    cli_main.cmd_attach(client, _ns(space=None, json=False))

    assert "bound-space" in capsys.readouterr().out
    # Showing the attachment must not need the backend.
    client.list_spaces.assert_not_called()


def test_cmd_attach_no_arg_unattached(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    client = MagicMock(spec=SmritiClient)
    cli_main.cmd_attach(client, _ns(space=None, json=False))
    assert "not attached" in capsys.readouterr().out.lower()


# ── parser wiring ────────────────────────────────────────────────────────────


def test_attach_parser_wired():
    parser = cli_main._build_parser()
    args = parser.parse_args(["attach", "some-space"])
    assert args.command == "attach"
    assert args.space == "some-space"
    assert args.func is cli_main.cmd_attach
    # `attach` with no space is valid — it shows the current attachment.
    assert cli_main._build_parser().parse_args(["attach"]).space is None


@pytest.mark.parametrize(
    "command", ["state", "current", "metrics", "checkpoint list", "claim list"]
)
def test_space_positional_is_optional(command):
    """The daily-driver commands accept no <space> — resolved from the attachment."""
    args = cli_main._build_parser().parse_args(command.split())
    assert args.space is None


def test_space_delete_still_requires_explicit_space():
    """Destructive `space delete` must never auto-resolve the attached space."""
    with pytest.raises(SystemExit):
        cli_main._build_parser().parse_args(["space", "delete"])
