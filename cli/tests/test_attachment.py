"""Tests for project attachment — the durable repo ↔ space binding.

Covers:
- The attachment module: find / load / write `.smriti.json`
- CLI space resolution: explicit arg vs. attachment fallback
- CLI api_url resolution precedence
- `smriti status` output, attached and unattached
- `<space>` is optional on the parser for attachment-aware commands
"""
from __future__ import annotations

import argparse
import json
from unittest.mock import MagicMock

import pytest

from smriti_cli import attachment
from smriti_cli import main as cli_main
from smriti_cli.attachment import (
    Attachment,
    AttachmentError,
    find_attachment_file,
    load_attachment,
    write_attachment,
)
from smriti_cli.client import SmritiClient, SmritiError


# ── attachment module ───────────────────────────────────────────────────────


def test_write_then_load_roundtrip(tmp_path):
    write_attachment(tmp_path, "my-space", api_url="http://localhost:8000")
    loaded = load_attachment(tmp_path)
    assert loaded is not None
    assert loaded.space == "my-space"
    assert loaded.api_url == "http://localhost:8000"
    assert loaded.root == tmp_path.resolve()


def test_write_attachment_records_timestamp(tmp_path):
    path = write_attachment(tmp_path, "s")
    data = json.loads(path.read_text())
    assert "attached_at" in data
    assert data["attached_at"].endswith("Z")


def test_write_attachment_preserves_unknown_keys(tmp_path):
    path = tmp_path / attachment.ATTACHMENT_FILENAME
    path.write_text(json.dumps({"space": "old", "future_key": "keep-me"}))
    write_attachment(tmp_path, "new-space")
    data = json.loads(path.read_text())
    assert data["space"] == "new-space"
    assert data["future_key"] == "keep-me"


def test_find_attachment_walks_up_to_parent(tmp_path):
    write_attachment(tmp_path, "root-space")
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    found = find_attachment_file(nested)
    assert found == (tmp_path / attachment.ATTACHMENT_FILENAME)


def test_find_attachment_returns_none_when_absent(tmp_path):
    assert find_attachment_file(tmp_path) is None


def test_load_attachment_returns_none_when_absent(tmp_path):
    assert load_attachment(tmp_path) is None


def test_load_attachment_rejects_malformed_json(tmp_path):
    (tmp_path / attachment.ATTACHMENT_FILENAME).write_text("{not json")
    with pytest.raises(AttachmentError):
        load_attachment(tmp_path)


def test_load_attachment_rejects_missing_space(tmp_path):
    (tmp_path / attachment.ATTACHMENT_FILENAME).write_text(json.dumps({"api_url": "x"}))
    with pytest.raises(AttachmentError):
        load_attachment(tmp_path)


def test_load_attachment_rejects_non_object(tmp_path):
    (tmp_path / attachment.ATTACHMENT_FILENAME).write_text(json.dumps(["not", "a", "dict"]))
    with pytest.raises(AttachmentError):
        load_attachment(tmp_path)


def test_attachment_blank_space_is_treated_as_missing(tmp_path):
    att = Attachment(tmp_path / ".smriti.json", {"space": "   "})
    assert att.space is None


# ── CLI space resolution ────────────────────────────────────────────────────


def test_resolve_space_name_prefers_explicit_arg(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_attachment(tmp_path, "attached-space")
    args = argparse.Namespace(space="explicit-space")
    assert cli_main._resolve_space_name(args) == "explicit-space"


def test_resolve_space_name_falls_back_to_attachment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_attachment(tmp_path, "attached-space")
    args = argparse.Namespace(space=None)
    assert cli_main._resolve_space_name(args) == "attached-space"


def test_resolve_space_name_fails_without_arg_or_attachment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    args = argparse.Namespace(space=None)
    with pytest.raises(SystemExit):
        cli_main._resolve_space_name(args)


def test_resolve_space_name_fails_loudly_on_corrupt_attachment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / attachment.ATTACHMENT_FILENAME).write_text("{broken")
    args = argparse.Namespace(space=None)
    with pytest.raises(SystemExit):
        cli_main._resolve_space_name(args)


# ── CLI api_url resolution ──────────────────────────────────────────────────


def test_resolve_api_url_prefers_explicit_flag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SMRITI_API_URL", raising=False)
    write_attachment(tmp_path, "s", api_url="http://attachment:9000")
    args = argparse.Namespace(api_url="http://flag:1234")
    assert cli_main._resolve_api_url(args) == "http://flag:1234"


def test_resolve_api_url_defers_to_env_var(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SMRITI_API_URL", "http://env:5555")
    write_attachment(tmp_path, "s", api_url="http://attachment:9000")
    args = argparse.Namespace(api_url=None)
    # Returns None so SmritiClient itself reads the env var.
    assert cli_main._resolve_api_url(args) is None


def test_resolve_api_url_falls_back_to_attachment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SMRITI_API_URL", raising=False)
    write_attachment(tmp_path, "s", api_url="http://attachment:9000")
    args = argparse.Namespace(api_url=None)
    assert cli_main._resolve_api_url(args) == "http://attachment:9000"


def test_resolve_api_url_none_when_nothing_set(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SMRITI_API_URL", raising=False)
    args = argparse.Namespace(api_url=None)
    assert cli_main._resolve_api_url(args) is None


# ── parser: <space> is optional for attachment-aware commands ────────────────


@pytest.mark.parametrize(
    "argv",
    [
        ["state"],
        ["current"],
        ["claim", "list"],
        ["worktree", "list"],
        ["metrics"],
        ["checkpoint", "list"],
    ],
)
def test_space_positional_is_optional(argv):
    args = cli_main._build_parser().parse_args(argv)
    assert args.space is None


def test_space_positional_still_accepts_explicit_value():
    args = cli_main._build_parser().parse_args(["state", "my-space"])
    assert args.space == "my-space"


# ── smriti status ───────────────────────────────────────────────────────────


def _status_client(reachable=True):
    client = MagicMock(spec=SmritiClient)
    client.base_url = "http://localhost:8000"
    if reachable:
        client.get_health.return_value = {"status": "ok"}
    else:
        client.get_health.side_effect = SmritiError("unreachable")
    return client


def test_status_unattached(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    client = _status_client()
    args = argparse.Namespace(json=True)
    cli_main.cmd_status(client, args)
    report = json.loads(capsys.readouterr().out)
    assert report["attached"] is False
    assert report["space"] is None
    assert report["backend_reachable"] is True


def test_status_attached_reports_space_and_claims(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_attachment(tmp_path, "bound-space")
    client = _status_client()
    client.resolve_space.return_value = {
        "id": "space-uuid",
        "name": "bound-space",
        "project_root": str(tmp_path),
    }
    client.list_claims.return_value = [
        {"intent_type": "implement", "scope": "do a thing", "agent": "claude-code"}
    ]
    client.get_head.return_value = {"commit_id": "commit-1"}
    args = argparse.Namespace(json=True)
    cli_main.cmd_status(client, args)
    report = json.loads(capsys.readouterr().out)
    assert report["attached"] is True
    assert report["space"] == "bound-space"
    assert report["space_resolved"]["id"] == "space-uuid"
    assert len(report["active_claims"]) == 1
    assert report["head_commit_id"] == "commit-1"


def test_status_attached_but_backend_down(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_attachment(tmp_path, "bound-space")
    client = _status_client(reachable=False)
    args = argparse.Namespace(json=True)
    cli_main.cmd_status(client, args)
    report = json.loads(capsys.readouterr().out)
    assert report["attached"] is True
    assert report["backend_reachable"] is False
    assert report["space_resolved"] is None


def test_status_corrupt_attachment_is_reported(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / attachment.ATTACHMENT_FILENAME).write_text("{broken")
    client = _status_client()
    args = argparse.Namespace(json=True)
    cli_main.cmd_status(client, args)
    report = json.loads(capsys.readouterr().out)
    assert report["attached"] is False
    assert report["attach_error"] is not None
