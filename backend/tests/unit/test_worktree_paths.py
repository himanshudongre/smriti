"""Unit tests for worktree naming/path helpers."""
from __future__ import annotations

from pathlib import Path

from app.api.routes import worktrees


def test_slugify_lowercases_and_replaces_non_alphanumeric():
    assert worktrees._slugify("Smriti Dev!") == "smriti-dev"
    assert worktrees._slugify("Claude_Code v2") == "claude-code-v2"
    assert worktrees._slugify("!!!", fallback="fallback") == "fallback"


def test_default_branch_name_uses_agent_slug():
    assert (
        worktrees._default_branch_name("Claude Code", "abc12345")
        == "smriti/claude-code/abc12345"
    )


def test_default_worktree_path_uses_home_space_agent_and_suffix(monkeypatch, tmp_path):
    monkeypatch.setattr(worktrees.Path, "home", lambda: Path(tmp_path))

    path = worktrees._default_worktree_path(
        "Smriti Dev",
        "Codex Local",
        "abc12345",
    )

    assert path == str(
        tmp_path / ".smriti" / "worktrees" / "smriti-dev" / "codex-local-abc12345"
    )
