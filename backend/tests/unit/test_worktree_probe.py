"""Unit tests for cached worktree git probing."""
from __future__ import annotations

import subprocess

from app.services import worktree_probe


def _result(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(
        args=["git"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_probe_worktree_success(monkeypatch):
    worktree_probe.clear_probe_cache()
    calls: list[list[str]] = []

    def fake_run_git(path, args):
        calls.append(args)
        if args == ["status", "--porcelain"]:
            return _result(stdout=" M file.py\n?? new.py\n")
        if args == ["rev-list", "--left-right", "--count", "HEAD...origin/main"]:
            return _result(stdout="2\t1\n")
        if args == ["log", "-1", "--format=%h %ar"]:
            return _result(stdout="abc1234 5 minutes ago\n")
        raise AssertionError(args)

    monkeypatch.setattr(worktree_probe, "_run_git", fake_run_git)

    result = worktree_probe._probe_worktree("wt-1", "/tmp/wt", "feature/wt")

    assert result == {
        "id": "wt-1",
        "path": "/tmp/wt",
        "branch": "feature/wt",
        "dirty_files": 2,
        "ahead": 2,
        "behind": 1,
        "last_commit_sha": "abc1234",
        "last_commit_relative": "5 minutes ago",
    }
    assert len(calls) == 3


def test_probe_worktree_cache_hit(monkeypatch):
    worktree_probe.clear_probe_cache()
    calls = 0

    def fake_run_git(path, args):
        nonlocal calls
        calls += 1
        if args == ["status", "--porcelain"]:
            return _result(stdout="")
        if args == ["rev-list", "--left-right", "--count", "HEAD...origin/main"]:
            return _result(stdout="0\t0\n")
        return _result(stdout="abc1234 just now\n")

    monkeypatch.setattr(worktree_probe, "_run_git", fake_run_git)

    first = worktree_probe._probe_worktree("wt-cache", "/tmp/wt", "branch")
    second = worktree_probe._probe_worktree("wt-cache", "/tmp/wt", "branch")

    assert first == second
    assert calls == 3


def test_probe_worktree_timeout_returns_none_and_caches(monkeypatch):
    worktree_probe.clear_probe_cache()
    calls = 0

    def fake_run_git(path, args):
        nonlocal calls
        calls += 1
        raise subprocess.TimeoutExpired(["git"], timeout=3)

    monkeypatch.setattr(worktree_probe, "_run_git", fake_run_git)

    assert worktree_probe._probe_worktree("wt-timeout", "/tmp/wt", "branch") is None
    assert worktree_probe._probe_worktree("wt-timeout", "/tmp/wt", "branch") is None
    assert calls == 1


def test_probe_worktree_nonzero_exit_returns_none(monkeypatch):
    worktree_probe.clear_probe_cache()
    monkeypatch.setattr(
        worktree_probe,
        "_run_git",
        lambda path, args: _result(returncode=128, stderr="fatal"),
    )

    assert worktree_probe._probe_worktree("wt-fail", "/tmp/wt", "branch") is None


def test_probe_worktree_malformed_output_returns_none(monkeypatch):
    worktree_probe.clear_probe_cache()

    def fake_run_git(path, args):
        if args == ["status", "--porcelain"]:
            return _result(stdout="")
        if args == ["rev-list", "--left-right", "--count", "HEAD...origin/main"]:
            return _result(stdout="not-two-fields\n")
        raise AssertionError(args)

    monkeypatch.setattr(worktree_probe, "_run_git", fake_run_git)

    assert worktree_probe._probe_worktree("wt-bad", "/tmp/wt", "branch") is None
