from __future__ import annotations

import argparse
from unittest.mock import MagicMock

import pytest

from smriti_cli import attachment
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


# ── space delete: destructive-delete guard ───────────────────────────────────
#
# Incident: `smriti space delete <space> -y` cascade-deleted a populated space.
# A non-empty or attached space must now require an explicit --force.


def _delete_args(space="my-project", yes=False, force=False, json=False):
    return argparse.Namespace(space=space, yes=yes, force=force, json=json)


def test_space_delete_parser_has_force_flag():
    parser = cli_main._build_parser()
    args = parser.parse_args(["space", "delete", "my-project", "--force", "-y"])
    assert args.force is True
    assert args.yes is True
    # --force defaults off
    assert parser.parse_args(["space", "delete", "my-project"]).force is False


def test_cmd_space_delete_empty_unattached_space_allows_yes(tmp_path, monkeypatch):
    """Empty, unattached space: -y still deletes it (convenience retained)."""
    monkeypatch.chdir(tmp_path)
    client = MagicMock(spec=SmritiClient)
    client.resolve_space.return_value = _space_dict()
    client.list_commits.return_value = []  # empty
    cli_main.cmd_space_delete(client, _delete_args(yes=True))
    client.delete_space.assert_called_once_with("space-uuid")


def test_cmd_space_delete_nonempty_refused_without_force(tmp_path, monkeypatch, capsys):
    """The incident path: -y alone must NOT delete a populated space."""
    monkeypatch.chdir(tmp_path)
    client = MagicMock(spec=SmritiClient)
    client.resolve_space.return_value = _space_dict()
    client.list_commits.return_value = [{"id": "c1"}, {"id": "c2"}]  # non-empty
    with pytest.raises(SystemExit):
        cli_main.cmd_space_delete(client, _delete_args(yes=True, force=False))
    client.delete_space.assert_not_called()
    err = capsys.readouterr().err
    assert "Refusing to delete" in err
    assert "--force" in err


def test_cmd_space_delete_nonempty_allowed_with_force(tmp_path, monkeypatch):
    """A populated space deletes only with --force (in addition to -y)."""
    monkeypatch.chdir(tmp_path)
    client = MagicMock(spec=SmritiClient)
    client.resolve_space.return_value = _space_dict()
    client.list_commits.return_value = [{"id": "c1"}, {"id": "c2"}]
    cli_main.cmd_space_delete(client, _delete_args(yes=True, force=True))
    client.delete_space.assert_called_once_with("space-uuid")


def test_cmd_space_delete_attached_space_refused_without_force(tmp_path, monkeypatch):
    """An attached space is force-gated even when it is empty."""
    monkeypatch.chdir(tmp_path)
    attachment.write_attachment(tmp_path, "my-project", "space-uuid")
    client = MagicMock(spec=SmritiClient)
    client.resolve_space.return_value = _space_dict()
    client.list_commits.return_value = []  # empty, but attached
    with pytest.raises(SystemExit):
        cli_main.cmd_space_delete(client, _delete_args(yes=True, force=False))
    client.delete_space.assert_not_called()


def test_cmd_space_delete_attached_space_allowed_with_force(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    attachment.write_attachment(tmp_path, "my-project", "space-uuid")
    client = MagicMock(spec=SmritiClient)
    client.resolve_space.return_value = _space_dict()
    client.list_commits.return_value = []
    cli_main.cmd_space_delete(client, _delete_args(yes=True, force=True))
    client.delete_space.assert_called_once_with("space-uuid")
