"""Cached git status probing for worktree-bound claims.

The state endpoint uses this helper for active claims with a bound
worktree. Probing must never make `smriti state` fail: stale, broken, or
missing worktrees return None and the claim still renders normally.
"""
from __future__ import annotations

import logging
import subprocess
import time
from typing import Any

logger = logging.getLogger(__name__)

PROBE_TIMEOUT_SECONDS = 3
PROBE_CACHE_TTL_SECONDS = 60
_PROBE_CACHE: dict[str, tuple[float, dict[str, Any] | None]] = {}


def clear_probe_cache() -> None:
    """Clear the in-process probe cache. Used by tests."""
    _PROBE_CACHE.clear()


def _run_git(path: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", path, *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=PROBE_TIMEOUT_SECONDS,
    )


def _probe_worktree(worktree_id: str, path: str, branch: str) -> dict[str, Any] | None:
    """Return git drift information for a worktree, or None on any error.

    The cache is keyed by worktree_id so repeated `smriti state` calls do
    not shell out on every request. Failures are cached too for the same
    TTL to avoid repeatedly probing broken paths.
    """
    now = time.time()
    cached = _PROBE_CACHE.get(worktree_id)
    if cached and now - cached[0] < PROBE_CACHE_TTL_SECONDS:
        return cached[1]

    result = _probe_worktree_uncached(worktree_id, path, branch)
    _PROBE_CACHE[worktree_id] = (now, result)
    return result


def _probe_worktree_uncached(
    worktree_id: str,
    path: str,
    branch: str,
) -> dict[str, Any] | None:
    try:
        status = _run_git(path, ["status", "--porcelain"])
        if status.returncode != 0:
            _log_probe_failure(worktree_id, "status", status)
            return None
        dirty_files = len([line for line in status.stdout.splitlines() if line.strip()])

        counts = _run_git(path, ["rev-list", "--left-right", "--count", "HEAD...origin/main"])
        if counts.returncode != 0:
            _log_probe_failure(worktree_id, "rev-list", counts)
            return None
        parts = counts.stdout.strip().split()
        if len(parts) != 2:
            logger.warning(
                "Malformed worktree ahead/behind output for %s: %r",
                worktree_id,
                counts.stdout,
            )
            return None
        ahead, behind = int(parts[0]), int(parts[1])

        last = _run_git(path, ["log", "-1", "--format=%h %ar"])
        if last.returncode != 0:
            _log_probe_failure(worktree_id, "log", last)
            return None
        last_parts = last.stdout.strip().split(maxsplit=1)
        if len(last_parts) != 2:
            logger.warning(
                "Malformed worktree last-commit output for %s: %r",
                worktree_id,
                last.stdout,
            )
            return None

        return {
            "id": worktree_id,
            "path": path,
            "branch": branch,
            "dirty_files": dirty_files,
            "ahead": ahead,
            "behind": behind,
            "last_commit_sha": last_parts[0],
            "last_commit_relative": last_parts[1],
        }
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError) as exc:
        logger.warning("Worktree probe failed for %s: %s", worktree_id, exc)
        return None


def _log_probe_failure(
    worktree_id: str,
    command: str,
    result: subprocess.CompletedProcess[str],
) -> None:
    detail = (result.stderr or result.stdout or "").strip()
    logger.warning(
        "Worktree probe command %s failed for %s: %s",
        command,
        worktree_id,
        detail or f"exit {result.returncode}",
    )
