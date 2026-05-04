"""Formatter tests for multi-branch state rendering + MCP wiring tests
for `smriti_state` main_only and default paths.

These tests cover the digestibility guarantees the build rests on:

- Passing `space_state=None` to `format_state_brief` produces output
  byte-for-byte identical to the pre-multi-branch version.
- Passing a space_state with empty active_branches and no divergence
  produces no "Active branches" or "Divergence signal" sections.
- Active branches render as a concise one-liner per branch.
- Divergence signal renders only when pairs are present and names the
  specific conflicting decisions.
- MCP `smriti_state` calls `get_space_state` by default and the legacy
  `get_head` + `get_commit` path only when `main_only=True`.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from smriti_cli import mcp_server
from smriti_cli.formatters import (
    _format_active_branches_section,
    _format_divergence_signal_section,
    _task_section,
    _normalize_task_item,
    format_state_brief,
)


# ── Fixtures: canonical space / head / commit dicts ─────────────────────────


def _base_space():
    return {
        "id": "space-uuid",
        "name": "my-project",
        "description": "Test project.",
    }


def _base_head(commit_id="commit-uuid"):
    return {
        "repo_id": "space-uuid",
        "commit_hash": "abcdef1234567890",
        "commit_id": commit_id,
        "summary": "Current state summary.",
        "objective": "Build the skill pack.",
        "latest_session_id": "session-uuid",
        "latest_session_title": "work session",
    }


def _base_commit():
    return {
        "id": "commit-uuid",
        "repo_id": "space-uuid",
        "commit_hash": "abcdef1234567890",
        "branch_name": "main",
        "author_agent": "claude-code",
        "project_root": "/tmp/test-project",
        "message": "Base",
        "summary": "Main summary here.",
        "objective": "Build something",
        "decisions": ["Decision A"],
        "assumptions": ["Assumption X"],
        "tasks": ["Task 1"],
        "open_questions": [],
        "entities": ["Pydantic"],
        "artifacts": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Formatter-level tests ────────────────────────────────────────────────────


def test_format_state_brief_no_space_state_matches_pre_build():
    """With space_state=None, output must not contain any multi-branch sections.
    This is the regression guard for existing CLI callers."""
    space = _base_space()
    head = _base_head()
    commit = _base_commit()

    out = format_state_brief(space, head, commit, space_state=None)

    assert "## Active branches" not in out
    assert "## Divergence signal" not in out
    # Core sections still present.
    assert "# my-project" in out
    assert "## Current objective" in out
    assert "## Decisions" in out


def test_format_state_brief_empty_branches_and_no_divergence_elided():
    """space_state present but empty → same output as space_state=None."""
    space = _base_space()
    head = _base_head()
    commit = _base_commit()

    empty_state = {"active_branches": [], "divergence": None}
    out = format_state_brief(space, head, commit, space_state=empty_state)

    assert "## Active branches" not in out
    assert "## Divergence signal" not in out


def test_format_state_brief_active_branches_only():
    """Non-empty active_branches → Active branches section appears,
    Divergence signal section absent."""
    space = _base_space()
    head = _base_head()
    commit = _base_commit()

    state = {
        "active_branches": [
            {
                "branch_name": "experiment-a",
                "commit_id": "branch-uuid-1",
                "commit_hash": "11112222" * 5,
                "message": "Trying stdlib",
                "author_agent": "codex-local",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "summary": "Fork summary.",
            }
        ],
        "divergence": None,
    }
    out = format_state_brief(space, head, commit, space_state=state)

    assert "## Active branches" in out
    assert "`experiment-a`" in out
    assert "`codex-local`" in out
    assert "Trying stdlib" in out
    assert "## Divergence signal" not in out


def test_format_state_brief_with_divergence():
    """Active branches + divergence → both sections rendered, specific
    conflicting decisions named."""
    space = _base_space()
    head = _base_head()
    commit = _base_commit()

    state = {
        "active_branches": [
            {
                "branch_name": "stdlib-fork",
                "commit_id": "branch-uuid",
                "commit_hash": "deadbeef" * 5,
                "message": "Stdlib attempt",
                "author_agent": "codex-local",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "summary": "Fork summary.",
            }
        ],
        "divergence": {
            "pairs": [
                {
                    "branch_name": "stdlib-fork",
                    "branch_commit_hash": "deadbeef" * 5,
                    "main_only_decisions": ["Use Pydantic with extra=forbid"],
                    "branch_only_decisions": [
                        "Use stdlib dataclasses",
                        "Reject third-party deps",
                    ],
                }
            ]
        },
    }
    out = format_state_brief(space, head, commit, space_state=state)

    assert "## Active branches" in out
    assert "## Divergence signal" in out
    assert "Use Pydantic with extra=forbid" in out
    assert "Use stdlib dataclasses" in out
    assert "Reject third-party deps" in out
    # Pointer to compare command is in the section header text.
    assert "smriti compare" in out


def test_format_divergence_signal_empty_pairs_elided():
    """divergence with empty pairs array → helper returns empty string."""
    assert _format_divergence_signal_section(None) == ""
    assert _format_divergence_signal_section({"pairs": []}) == ""
    assert _format_divergence_signal_section({}) == ""


def test_format_active_branches_empty_returns_empty():
    assert _format_active_branches_section([]) == ""


def test_format_active_branches_multiple_branches_one_line_each():
    branches = [
        {
            "branch_name": "b1",
            "commit_hash": "aaaa" * 8,
            "message": "First",
            "author_agent": "claude-code",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        {
            "branch_name": "b2",
            "commit_hash": "bbbb" * 8,
            "message": "Second",
            "author_agent": "codex-local",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    ]
    out = _format_active_branches_section(branches)
    # One bullet per branch.
    assert out.count("- `") == 2
    assert "First" in out
    assert "Second" in out
    assert "`claude-code`" in out
    assert "`codex-local`" in out


# ── MCP tool wiring tests ───────────────────────────────────────────────────


def _space_dict():
    return {"id": "space-uuid", "name": "my-project", "description": ""}


def _space_state_dict(with_divergence=False):
    base = {
        "space": _space_dict(),
        "head": _base_head(),
        "commit": _base_commit(),
        "active_branches": [],
        "divergence": None,
    }
    if with_divergence:
        base["active_branches"] = [
            {
                "branch_name": "fork-a",
                "commit_id": "fork-uuid",
                "commit_hash": "abcd" * 8,
                "message": "Fork alt",
                "author_agent": "codex-local",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "summary": "Fork summary.",
            }
        ]
        base["divergence"] = {
            "pairs": [
                {
                    "branch_name": "fork-a",
                    "branch_commit_hash": "abcd" * 8,
                    "main_only_decisions": ["Decision A"],
                    "branch_only_decisions": ["Decision B"],
                }
            ]
        }
    return base


def test_mcp_smriti_state_default_calls_get_space_state(mock_client):
    """Default path: smriti_state → resolve_space → get_space_state (one call)."""
    mock_client.resolve_space.return_value = _space_dict()
    mock_client.get_space_state.return_value = _space_state_dict()

    out = mcp_server.smriti_state(space="my-project")

    mock_client.get_space_state.assert_called_once_with("space-uuid", since="")
    mock_client.get_head.assert_not_called()
    mock_client.get_commit.assert_not_called()
    assert "# my-project" in out


def test_mcp_smriti_state_main_only_uses_legacy_path(mock_client):
    """main_only=True falls back to the old get_head + get_commit dance."""
    mock_client.resolve_space.return_value = _space_dict()
    mock_client.get_head.return_value = _base_head()
    mock_client.get_commit.return_value = _base_commit()

    out = mcp_server.smriti_state(space="my-project", main_only=True)

    mock_client.get_head.assert_called_once_with("space-uuid")
    mock_client.get_commit.assert_called_once_with("commit-uuid")
    mock_client.get_space_state.assert_not_called()
    assert "# my-project" in out


def test_mcp_smriti_state_default_renders_divergence_signal(mock_client):
    """End-to-end: default path + a divergent space_state → divergence
    section visible in rendered output."""
    mock_client.resolve_space.return_value = _space_dict()
    mock_client.get_space_state.return_value = _space_state_dict(with_divergence=True)

    out = mcp_server.smriti_state(space="my-project")

    assert "## Active branches" in out
    assert "## Divergence signal" in out
    assert "Decision A" in out
    assert "Decision B" in out


def test_mcp_smriti_state_no_checkpoints_short_circuit(mock_client):
    """Space exists but has no main commit: default path returns the
    empty-space message without calling format_state_brief."""
    empty_state = _space_state_dict()
    empty_state["head"] = {
        "repo_id": "space-uuid",
        "commit_hash": None,
        "commit_id": None,
        "summary": None,
        "objective": None,
        "latest_session_id": None,
        "latest_session_title": None,
    }
    empty_state["commit"] = None
    mock_client.resolve_space.return_value = _space_dict()
    mock_client.get_space_state.return_value = empty_state

    out = mcp_server.smriti_state(space="my-project")

    assert "No checkpoints yet" in out


# ── Compact mode tests ──────────────────────────────────────────────────────


def _commit_with_artifacts():
    """Commit with realistic artifacts for compact mode testing."""
    base = _base_commit()
    base["id"] = "abc12345-6789-0abc-def0-123456789abc"
    base["artifacts"] = [
        {
            "id": "a1",
            "type": "python",
            "label": "Draft implementation",
            "content": "def hello():\n    return 'world'\n" * 50,
        },
        {
            "id": "a2",
            "type": "markdown",
            "label": "Test plan",
            "content": "# Test Plan\n\n- Unit tests for X\n- Integration tests for Y\n" * 30,
        },
    ]
    return base


def test_compact_omits_artifact_content():
    """Compact mode shows artifact labels but not content."""
    commit = _commit_with_artifacts()
    out = format_state_brief(
        _base_space(), _base_head(), commit, compact=True,
    )

    # Labels present
    assert "Draft implementation" in out
    assert "Test plan" in out
    # Content absent
    assert "def hello():" not in out
    assert "Unit tests for X" not in out
    # Recovery instruction present
    assert "compact — content omitted" in out
    assert "smriti checkpoint show" in out
    assert "abc12345-6789-0abc-def0-123456789abc" in out


def test_compact_is_smaller_than_full():
    """Compact output must be materially smaller than full output."""
    commit = _commit_with_artifacts()
    full = format_state_brief(
        _base_space(), _base_head(), commit, full_artifacts=True,
    )
    compact = format_state_brief(
        _base_space(), _base_head(), commit, compact=True,
    )

    # Compact should be at least 50% smaller when artifacts dominate
    assert len(compact) < len(full) * 0.5, (
        f"Compact ({len(compact)} chars) should be less than 50% of "
        f"full ({len(full)} chars)"
    )


def test_compact_preserves_decisions_and_tasks():
    """Compact mode must not touch non-artifact sections."""
    commit = _commit_with_artifacts()
    out = format_state_brief(
        _base_space(), _base_head(), commit, compact=True,
    )

    assert "## Decisions" in out
    assert "Decision A" in out
    assert "## Assumptions we are relying on" in out
    assert "Assumption X" in out
    assert "## In progress" in out
    assert "Task 1" in out


def test_compact_with_no_artifacts_is_clean():
    """Compact mode on a commit with no artifacts should not show the section."""
    commit = _base_commit()  # no artifacts
    out = format_state_brief(
        _base_space(), _base_head(), commit, compact=True,
    )

    assert "Attached artifacts" not in out
    assert "compact" not in out.lower() or "compact" in out.lower()  # no section = no mention


def test_mcp_smriti_state_compact_mode(mock_client):
    """MCP tool with compact=True should pass compact to formatter."""
    mock_client.resolve_space.return_value = _space_dict()
    state = _space_state_dict()
    state["commit"] = _commit_with_artifacts()
    mock_client.get_space_state.return_value = state

    out = mcp_server.smriti_state(space="my-project", compact=True)

    # Labels present, content absent
    assert "Draft implementation" in out
    assert "def hello():" not in out
    assert "compact — content omitted" in out


def test_compact_stats_footer_shows_actual_rendered_sizes():
    """--compact --stats shows full and compact rendered char counts."""
    commit = _commit_with_artifacts()
    out = format_state_brief(
        _base_space(), _base_head(), commit, compact=True, stats=True,
    )

    assert "compact stats:" in out
    assert "artifact(s) omitted" in out
    assert "chars saved" in out
    assert "smaller artifact section" in out
    # Must show actual rendered sizes, not heuristic estimates
    assert "full:" in out
    assert "compact:" in out
    assert "chars)" in out


def test_stats_without_compact_shows_explicit_message():
    """--stats without --compact should say so, not silently produce nothing."""
    commit = _commit_with_artifacts()
    out = format_state_brief(
        _base_space(), _base_head(), commit, stats=True,
    )

    assert "compact stats:" in out
    assert "--compact not used" in out


def test_stats_with_no_artifacts_shows_explicit_message():
    """Compact+stats on a commit with no artifacts: explicit message."""
    commit = _base_commit()
    out = format_state_brief(
        _base_space(), _base_head(), commit, compact=True, stats=True,
    )

    assert "compact stats:" in out
    assert "0 artifacts" in out


# ── Structured task rendering tests ────────────────────────────────────────


def test_normalize_task_item_string():
    """Plain string task normalizes to dict with text key."""
    result = _normalize_task_item("Write tests")
    assert result == {"text": "Write tests"}


def test_normalize_task_item_dict():
    """Structured task dict passes through unchanged."""
    task = {"text": "Add endpoint", "intent_hint": "implement", "blocked_by": "schema"}
    result = _normalize_task_item(task)
    assert result == task


def test_task_section_empty():
    """Empty task list produces empty string."""
    assert _task_section([]) == ""


def test_task_section_legacy_string_tasks():
    """Old-style string tasks render as plain bullets."""
    out = _task_section(["Task A", "Task B"])
    assert "## In progress" in out
    assert "- Task A" in out
    assert "- Task B" in out
    # No intent or status annotations
    assert "[" not in out
    assert "→" not in out


def test_task_section_structured_with_intent():
    """Structured task with intent_hint renders inline tag."""
    tasks = [
        {"text": "Add freshness tests", "intent_hint": "test"},
    ]
    out = _task_section(tasks)
    assert "- Add freshness tests [test]" in out


def test_task_section_structured_with_blocked_by():
    """Structured task with blocked_by renders inline marker."""
    tasks = [
        {"text": "Write test suite", "blocked_by": "freshness-impl"},
    ]
    out = _task_section(tasks)
    assert "→ blocked by: freshness-impl" in out


def test_task_section_structured_with_done_status():
    """Task with status=done renders inline marker."""
    tasks = [
        {"text": "Implement endpoint", "status": "done"},
    ]
    out = _task_section(tasks)
    assert "(done)" in out


def test_task_section_open_status_not_rendered():
    """Task with status=open should NOT show (open) — it's the default."""
    tasks = [
        {"text": "Implement endpoint", "status": "open"},
    ]
    out = _task_section(tasks)
    assert "(open)" not in out
    assert "Implement endpoint" in out


def test_task_section_full_structured_task():
    """Task with all annotations renders them in order."""
    tasks = [
        {
            "text": "Write integration tests",
            "intent_hint": "test",
            "status": "open",
            "blocked_by": "freshness-impl",
        },
    ]
    out = _task_section(tasks)
    assert "- Write integration tests [test] → blocked by: freshness-impl" in out
    assert "(open)" not in out  # open is default, not rendered


def test_task_section_mixed_string_and_structured():
    """Mix of legacy string and structured tasks renders correctly."""
    tasks = [
        "Legacy task string",
        {"text": "New structured task", "intent_hint": "implement"},
        {"text": "Done task", "status": "done"},
    ]
    out = _task_section(tasks)
    assert "- Legacy task string" in out
    assert "- New structured task [implement]" in out
    assert "- Done task (done)" in out


def test_task_section_custom_heading():
    """Custom heading parameter is respected."""
    tasks = [{"text": "Some task"}]
    out = _task_section(tasks, heading="Tasks")
    assert "## Tasks" in out
    assert "## In progress" not in out


def test_state_brief_with_structured_tasks():
    """State brief renders structured tasks from commit data."""
    commit = _base_commit()
    commit["tasks"] = [
        {"text": "Add freshness endpoint", "intent_hint": "implement"},
        {"text": "Write freshness tests", "intent_hint": "test", "blocked_by": "freshness-endpoint"},
        "Legacy string task",
    ]
    out = format_state_brief(_base_space(), _base_head(), commit)

    assert "## In progress" in out
    assert "Add freshness endpoint [implement]" in out
    assert "Write freshness tests [test] → blocked by: freshness-endpoint" in out
    assert "- Legacy string task" in out


# ── Task ID rendering tests ────────────────────────────────────────────────


def test_task_section_with_id():
    """Task with an id renders (id: ...) annotation."""
    tasks = [
        {"id": "impl-1", "text": "Implement endpoint", "intent_hint": "implement"},
    ]
    out = _task_section(tasks)
    assert "- Implement endpoint [implement] (id: impl-1)" in out


def test_task_section_without_id():
    """Task without id renders normally — no (id: ...) annotation."""
    tasks = [
        {"text": "Implement endpoint", "intent_hint": "implement"},
    ]
    out = _task_section(tasks)
    assert "(id:" not in out
    assert "Implement endpoint [implement]" in out


def test_task_section_mixed_with_and_without_ids():
    """Mix of tasks with and without IDs renders correctly."""
    tasks = [
        {"id": "docs-arch", "text": "Update ARCHITECTURE.md", "intent_hint": "docs"},
        {"text": "Legacy task without ID"},
        {"id": "test-e2e", "text": "Write e2e test", "intent_hint": "test", "blocked_by": "impl-1"},
    ]
    out = _task_section(tasks)
    assert "(id: docs-arch)" in out
    assert "(id:" not in out.split("Legacy task")[1].split("\n")[0]  # legacy line has no id
    assert "(id: test-e2e)" in out
    assert "→ blocked by: impl-1" in out


def test_claims_section_with_task_id():
    """Active claim with task_id renders (task: ...) suffix."""
    from smriti_cli.formatters import _format_active_claims_section
    claims = [
        {
            "agent": "claude-code",
            "branch_name": "main",
            "scope": "Update ARCHITECTURE.md",
            "task_id": "docs-arch",
            "intent_type": "docs",
            "base_commit_hash": "abc1234",
            "claimed_at": datetime.now(timezone.utc).isoformat(),
        },
    ]
    out = _format_active_claims_section(claims)
    assert "(task: docs-arch)" in out
    assert "[docs]" in out


def test_claims_section_without_task_id():
    """Active claim without task_id renders normally — no (task: ...) suffix."""
    from smriti_cli.formatters import _format_active_claims_section
    claims = [
        {
            "agent": "codex-local",
            "branch_name": "main",
            "scope": "Some work",
            "intent_type": "implement",
            "base_commit_hash": "def5678",
            "claimed_at": datetime.now(timezone.utc).isoformat(),
        },
    ]
    out = _format_active_claims_section(claims)
    assert "(task:" not in out
    assert "[implement]" in out


def test_claims_section_with_worktree_info():
    """Bound worktree info renders as continuation lines under the claim."""
    from smriti_cli.formatters import _format_active_claims_section
    claims = [
        {
            "agent": "codex-local",
            "branch_name": "worktree-v2-binding-and-enrichment",
            "scope": "Implement V2",
            "task_id": "v2-plan",
            "worktree_id": "worktree-uuid",
            "worktree": {
                "id": "worktree-uuid",
                "path": "/Users/example/.smriti/worktrees/smriti-dev/codex-local-abc12345",
                "branch": "smriti/codex-local/abc12345",
                "dirty_files": 3,
                "ahead": 1,
                "behind": 0,
                "last_commit_sha": "def5678",
                "last_commit_relative": "5 minutes ago",
            },
            "intent_type": "implement",
            "base_commit_hash": "abc1234",
            "claimed_at": datetime.now(timezone.utc).isoformat(),
        },
    ]

    out = _format_active_claims_section(claims)

    assert "worktree:" in out
    assert "smriti/codex-local/abc12345" in out
    assert "3 dirty" in out
    assert "ahead 1" in out
    assert "behind 0" in out
    assert "last commit `def5678` 5 minutes ago" in out


def test_claims_section_with_worktree_probe_failure():
    """A bound claim with failed probing still renders a useful hint."""
    from smriti_cli.formatters import _format_active_claims_section
    claims = [
        {
            "agent": "codex-local",
            "branch_name": "main",
            "scope": "Implement V2",
            "worktree_id": "worktree-uuid",
            "worktree": None,
            "intent_type": "implement",
            "base_commit_hash": "abc1234",
            "claimed_at": datetime.now(timezone.utc).isoformat(),
        },
    ]

    out = _format_active_claims_section(claims)

    assert "probe failed or worktree closed" in out
