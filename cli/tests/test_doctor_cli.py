from __future__ import annotations

import argparse
from unittest.mock import MagicMock

import pytest

from smriti_cli import main as cli_main
from smriti_cli.client import SmritiClient, SmritiError


def _client(health: dict | None = None) -> MagicMock:
    client = MagicMock(spec=SmritiClient)
    client.base_url = "http://localhost:8000"
    if health is not None:
        client.get_health.return_value = health
    return client


def _patch_git(monkeypatch: pytest.MonkeyPatch, *, sha: str = "c470947abcdef", branch: str = "main") -> None:
    short = sha[:7]
    values = {
        ("rev-parse", "HEAD"): sha,
        ("rev-parse", "--short", "HEAD"): short,
        ("branch", "--show-current"): branch,
        ("rev-parse", "--abbrev-ref", "HEAD"): branch,
    }
    monkeypatch.setattr(cli_main, "_git_output", lambda *args: values.get(args))


def _patch_cli(
    monkeypatch: pytest.MonkeyPatch,
    *,
    executable: str = "/repo/backend/.venv/bin/smriti",
    path_entry: str = "/repo/backend/.venv/bin/smriti",
    version: str = "0.1.0",
) -> None:
    monkeypatch.setattr(
        cli_main,
        "_build_cli_info",
        lambda: {
            "executable": executable,
            "path_entry": path_entry,
            "path_matches_executable": executable == path_entry,
            "package_version": version,
        },
    )


def _health(**overrides) -> dict:
    base = {
        "status": "ok",
        "git_sha": "c470947",
        "capabilities": sorted(cli_main.EXPECTED_HEALTH_CAPABILITIES),
        "database": {
            "mode": "local",
            "url_scheme": "sqlite",
            "local_db_path": "/Users/test/.smriti/smriti.db",
        },
        "providers": {
            "background_intelligence": {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "configured": True,
            }
        },
    }
    base.update(overrides)
    return base


def test_doctor_parser_wiring():
    parser = cli_main._build_parser()

    args = parser.parse_args(["doctor"])

    assert args.command == "doctor"
    assert args.func is cli_main.cmd_doctor


def test_doctor_report_ok(monkeypatch: pytest.MonkeyPatch):
    _patch_git(monkeypatch)
    _patch_cli(monkeypatch)
    client = _client(_health())

    report = cli_main._build_doctor_report(client)

    assert report["backend"]["reachable"] is True
    assert report["backend"]["git_sha"] == "c470947"
    assert report["backend"]["database"]["mode"] == "local"
    assert report["backend"]["providers"]["background_intelligence"]["configured"] is True
    assert report["local"]["git_sha_short"] == "c470947"
    assert report["cli"]["path_matches_executable"] is True
    assert report["checks"]["runtime_match"] == "ok"
    assert report["checks"]["missing_capabilities"] == []
    assert report["checks"]["cli_path"] == "ok"
    assert report["checks"]["background_provider"] == "ready"
    assert report["hints"] == []


def test_doctor_report_flags_mismatch_and_missing_capability(
    monkeypatch: pytest.MonkeyPatch,
):
    _patch_git(monkeypatch, sha="c470947abcdef")
    _patch_cli(monkeypatch)
    capabilities = sorted(cli_main.EXPECTED_HEALTH_CAPABILITIES - {"worktree_binding"})
    client = _client(_health(git_sha="deadbee", capabilities=capabilities))

    report = cli_main._build_doctor_report(client)

    assert report["checks"]["runtime_match"] == "mismatch"
    assert report["checks"]["missing_capabilities"] == ["worktree_binding"]
    assert any("differs from local HEAD" in hint for hint in report["hints"])
    assert any("missing capabilities" in hint for hint in report["hints"])


def test_doctor_report_flags_cli_path_mismatch(monkeypatch: pytest.MonkeyPatch):
    _patch_git(monkeypatch)
    _patch_cli(
        monkeypatch,
        executable="/repo/backend/.venv/bin/smriti",
        path_entry="/Users/test/.local/bin/smriti",
    )
    client = _client(_health())

    report = cli_main._build_doctor_report(client)

    assert report["checks"]["cli_path"] == "mismatch"
    assert any("PATH differs" in hint for hint in report["hints"])


def test_doctor_report_flags_background_mock_risk(monkeypatch: pytest.MonkeyPatch):
    _patch_git(monkeypatch)
    _patch_cli(monkeypatch)
    client = _client(
        _health(
            providers={
                "background_intelligence": {
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "configured": False,
                }
            }
        )
    )

    report = cli_main._build_doctor_report(client)

    assert report["checks"]["background_provider"] == "mock_or_disabled"
    assert any("not configured" in hint for hint in report["hints"])


def test_cmd_doctor_handles_unreachable_backend(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    _patch_git(monkeypatch)
    _patch_cli(monkeypatch)
    client = _client()
    client.get_health.side_effect = SmritiError("Could not reach Smriti")
    args = argparse.Namespace(json=False)

    cli_main.cmd_doctor(client, args)

    out = capsys.readouterr().out
    assert "# Smriti Doctor" in out
    assert "Backend: unreachable" in out
    assert "missing capabilities: unknown" in out
    assert "make dev-local" in out
    assert "Backend is not reachable" in out


def test_cmd_doctor_json_outputs_report(monkeypatch: pytest.MonkeyPatch):
    _patch_git(monkeypatch)
    _patch_cli(monkeypatch)
    client = _client(_health())
    args = argparse.Namespace(json=True)
    captured: list[dict] = []
    original = cli_main._print_json
    cli_main._print_json = captured.append
    try:
        cli_main.cmd_doctor(client, args)
    finally:
        cli_main._print_json = original

    assert captured[0]["backend"]["reachable"] is True
    assert captured[0]["checks"]["runtime_match"] == "ok"


def test_cmd_doctor_prints_activation_details(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    _patch_git(monkeypatch)
    _patch_cli(monkeypatch)
    client = _client(_health())
    args = argparse.Namespace(json=False)

    cli_main.cmd_doctor(client, args)

    out = capsys.readouterr().out
    assert "## Runtime" in out
    assert "Database mode: `local`" in out
    assert "Local DB path: `/Users/test/.smriti/smriti.db`" in out
    assert "Background intelligence: ready (`openai` / `gpt-4o-mini`)" in out
    assert "## CLI" in out
    assert "PATH matches executable: yes" in out
