from __future__ import annotations

import argparse
from unittest.mock import MagicMock

import pytest

from smriti_cli import main as cli_main
from smriti_cli.client import SmritiClient


def _space_dict(**overrides):
    base = {
        "id": "space-uuid",
        "name": "my-project",
        "description": "",
        "project_root": "/tmp/project",
    }
    base.update(overrides)
    return base


def test_space_create_parser_wiring():
    parser = cli_main._build_parser()

    args = parser.parse_args(
        [
            "space",
            "create",
            "my-project",
            "--description",
            "Test",
            "--project-root",
            "/tmp/project",
        ]
    )

    assert args.command == "space"
    assert args.subcommand == "create"
    assert args.name == "my-project"
    assert args.description == "Test"
    assert args.project_root == "/tmp/project"
    assert args.no_project_root is False
    assert args.func is cli_main.cmd_space_create


def test_space_create_parser_supports_no_project_root():
    parser = cli_main._build_parser()

    args = parser.parse_args(["space", "create", "my-project", "--no-project-root"])

    assert args.project_root is None
    assert args.no_project_root is True


def test_space_set_project_root_parser_wiring():
    parser = cli_main._build_parser()

    args = parser.parse_args(
        ["space", "set-project-root", "my-project", "/tmp/project"]
    )

    assert args.command == "space"
    assert args.subcommand == "set-project-root"
    assert args.space == "my-project"
    assert args.path == "/tmp/project"
    assert args.here is False
    assert args.func is cli_main.cmd_space_set_project_root


def test_space_set_project_root_parser_supports_here_flag():
    parser = cli_main._build_parser()

    args = parser.parse_args(["space", "set-project-root", "my-project", "--here"])

    assert args.path is None
    assert args.here is True


def test_cmd_space_create_defaults_project_root_to_cwd(
    tmp_path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    client = MagicMock(spec=SmritiClient)
    client.create_space.return_value = _space_dict(project_root=str(tmp_path))
    args = argparse.Namespace(
        name="my-project",
        description="",
        project_root=None,
        no_project_root=False,
        json=False,
    )

    cli_main.cmd_space_create(client, args)

    out = capsys.readouterr().out
    assert "Created space: my-project" in out
    assert f"Project root: {tmp_path}" in out
    client.create_space.assert_called_once_with(
        name="my-project",
        description="",
        project_root=str(tmp_path),
    )


def test_cmd_space_create_passes_explicit_project_root():
    client = MagicMock(spec=SmritiClient)
    client.create_space.return_value = _space_dict(project_root="/tmp/explicit")
    args = argparse.Namespace(
        name="my-project",
        description="Test",
        project_root="/tmp/explicit",
        no_project_root=False,
        json=False,
    )

    cli_main.cmd_space_create(client, args)

    client.create_space.assert_called_once_with(
        name="my-project",
        description="Test",
        project_root="/tmp/explicit",
    )


def test_cmd_space_create_can_leave_project_root_null(
    capsys: pytest.CaptureFixture[str],
):
    client = MagicMock(spec=SmritiClient)
    client.create_space.return_value = _space_dict(project_root=None)
    args = argparse.Namespace(
        name="my-project",
        description="",
        project_root=None,
        no_project_root=True,
        json=False,
    )

    cli_main.cmd_space_create(client, args)

    out = capsys.readouterr().out
    assert "Project root:" not in out
    client.create_space.assert_called_once_with(
        name="my-project",
        description="",
        project_root=None,
    )


def test_cmd_space_set_project_root_calls_patch(capsys: pytest.CaptureFixture[str]):
    client = MagicMock(spec=SmritiClient)
    client.resolve_space.return_value = _space_dict(id="space-uuid", name="my-project")
    client.set_project_root.return_value = _space_dict(
        id="space-uuid",
        name="my-project",
        project_root="/tmp/project",
    )
    args = argparse.Namespace(
        space="my-project",
        path="/tmp/project",
        here=False,
        json=False,
    )

    cli_main.cmd_space_set_project_root(client, args)

    assert (
        capsys.readouterr().out == "Set project_root for 'my-project' to /tmp/project\n"
    )
    client.resolve_space.assert_called_once_with("my-project")
    client.set_project_root.assert_called_once_with("space-uuid", "/tmp/project")


def test_cmd_space_set_project_root_dot_resolves_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = MagicMock(spec=SmritiClient)
    client.resolve_space.return_value = _space_dict(id="space-uuid")
    client.set_project_root.return_value = _space_dict(project_root=str(tmp_path))
    args = argparse.Namespace(space="my-project", path=".", here=False, json=False)

    cli_main.cmd_space_set_project_root(client, args)

    client.set_project_root.assert_called_once_with("space-uuid", str(tmp_path))


def test_cmd_space_set_project_root_here_flag_resolves_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = MagicMock(spec=SmritiClient)
    client.resolve_space.return_value = _space_dict(id="space-uuid")
    client.set_project_root.return_value = _space_dict(project_root=str(tmp_path))
    args = argparse.Namespace(space="my-project", path=None, here=True, json=False)

    cli_main.cmd_space_set_project_root(client, args)

    client.set_project_root.assert_called_once_with("space-uuid", str(tmp_path))
