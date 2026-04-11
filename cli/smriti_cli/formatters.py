"""Markdown output formatters for the Smriti CLI.

The default output of every command is a readable markdown brief shaped
so an agent or a human can paste it directly into a working context.
Use --json on any command for structured output instead.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone


def _pretty_path(path: str | None) -> str | None:
    """Shorten an absolute path for display: $HOME becomes ~."""
    if not path:
        return None
    try:
        home = os.path.expanduser("~")
        if path == home:
            return "~"
        if path.startswith(home + os.sep):
            return "~" + path[len(home):]
    except Exception:
        pass
    return path


def _relative_time(iso_ts: str) -> str:
    """Format an ISO-8601 UTC timestamp as a relative-time string."""
    try:
        then = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    except Exception:
        return iso_ts
    now = datetime.now(timezone.utc)
    delta = now - then
    secs = int(delta.total_seconds())
    if secs < 60:
        return "just now"
    mins = secs // 60
    if mins < 60:
        return f"{mins}m ago"
    hrs = mins // 60
    if hrs < 24:
        return f"{hrs}h ago"
    days = hrs // 24
    if days < 30:
        return f"{days}d ago"
    return then.strftime("%Y-%m-%d")


def _short_hash(commit_hash: str | None) -> str:
    return commit_hash[:7] if commit_hash else "?"


def _list_section(heading: str, items: list[str]) -> str:
    if not items:
        return ""
    lines = [f"## {heading}"]
    for item in items:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _artifact_section(artifacts: list[dict], preview_chars: int = 800, full: bool = False) -> str:
    if not artifacts:
        return ""
    lines = ["## Attached artifacts"]
    for art in artifacts:
        label = art.get("label") or "Untitled"
        content = art.get("content") or ""
        lines.append(f"### {label}")
        if full or len(content) <= preview_chars:
            lines.append(content)
        else:
            lines.append(content[:preview_chars] + "\n\n[… truncated, use --full-artifacts to see all]")
        lines.append("")
    return "\n".join(lines) + "\n"


def format_state_brief(
    space: dict,
    head: dict,
    commit: dict,
    *,
    full_artifacts: bool = False,
) -> str:
    """A continuation-oriented markdown brief for the current project state.

    Intended to be pasted directly into an agent's (or human's) working
    context. Sections are elided cleanly when empty.
    """
    parts: list[str] = []
    parts.append(f"# {space.get('name', 'Untitled space')}\n")
    if space.get("description"):
        parts.append(space["description"].rstrip() + "\n")

    commit_hash = commit.get("commit_hash")
    created_at = commit.get("created_at") or head.get("commit_hash") or ""
    meta_bits = [f"Latest checkpoint: `{_short_hash(commit_hash)}`"]
    author_agent = commit.get("author_agent")
    if author_agent:
        meta_bits.append(f"by `{author_agent}`")
    if created_at:
        meta_bits.append(_relative_time(created_at))
    project_root = _pretty_path(commit.get("project_root"))
    if project_root:
        meta_bits.append(f"at `{project_root}`")
    parts.append(" · ".join(meta_bits) + "\n")

    if commit.get("objective"):
        parts.append(f"## Current objective\n{commit['objective'].rstrip()}\n")

    if commit.get("summary"):
        parts.append(f"## Where we are\n{commit['summary'].rstrip()}\n")

    decisions = commit.get("decisions") or []
    assumptions = commit.get("assumptions") or []
    open_questions = commit.get("open_questions") or []
    tasks = commit.get("tasks") or []
    entities = commit.get("entities") or []
    artifacts = commit.get("artifacts") or []

    parts.append(_list_section("Decisions", decisions))
    parts.append(_list_section("Assumptions we are relying on", assumptions))
    parts.append(_list_section("Open questions", open_questions))
    parts.append(_list_section("In progress", tasks))
    parts.append(_artifact_section(artifacts, full=full_artifacts))

    if entities:
        parts.append(f"## Key entities\n{', '.join(entities)}\n")

    return "\n".join(p for p in parts if p).rstrip() + "\n"


def format_checkpoint(commit: dict, *, full_artifacts: bool = False) -> str:
    """Readable markdown for a single checkpoint."""
    parts: list[str] = []
    parts.append(f"# {commit.get('message', 'Untitled checkpoint')}\n")

    commit_hash = commit.get("commit_hash")
    created_at = commit.get("created_at") or ""
    branch = commit.get("branch_name") or "main"
    author_agent = commit.get("author_agent")
    project_root = _pretty_path(commit.get("project_root"))
    meta_bits = [f"`{_short_hash(commit_hash)}`"]
    if created_at:
        meta_bits.append(_relative_time(created_at))
    meta_bits.append(f"branch `{branch}`")
    if author_agent:
        meta_bits.append(f"by `{author_agent}`")
    if project_root:
        meta_bits.append(f"at `{project_root}`")
    parts.append(" · ".join(meta_bits) + "\n")

    if commit.get("objective"):
        parts.append(f"## Objective\n{commit['objective'].rstrip()}\n")

    if commit.get("summary"):
        parts.append(f"## Summary\n{commit['summary'].rstrip()}\n")

    parts.append(_list_section("Decisions", commit.get("decisions") or []))
    parts.append(_list_section("Assumptions", commit.get("assumptions") or []))
    parts.append(_list_section("Tasks", commit.get("tasks") or []))
    parts.append(_list_section("Open questions", commit.get("open_questions") or []))
    parts.append(_artifact_section(commit.get("artifacts") or [], full=full_artifacts))

    entities = commit.get("entities") or []
    if entities:
        parts.append(f"## Entities\n{', '.join(entities)}\n")

    return "\n".join(p for p in parts if p).rstrip() + "\n"


def format_space_list(spaces: list[dict]) -> str:
    if not spaces:
        return "No spaces yet. Create one with `smriti space create <name>`.\n"
    lines = [f"{len(spaces)} space(s):", ""]
    for s in spaces:
        desc = (s.get("description") or "").strip()
        desc_line = f"  {desc}" if desc else ""
        lines.append(f"- **{s['name']}** `{s['id']}`")
        if desc_line:
            lines.append(desc_line)
    return "\n".join(lines) + "\n"


def format_commit_list(commits: list[dict]) -> str:
    if not commits:
        return "No checkpoints yet.\n"
    lines = [f"{len(commits)} checkpoint(s):", ""]
    for c in commits:
        created = _relative_time(c.get("created_at") or "")
        branch = c.get("branch_name") or "main"
        marker = "" if branch == "main" else f" (branch: {branch})"
        lines.append(
            f"- `{_short_hash(c.get('commit_hash'))}` {c.get('message', 'Untitled')}"
            f" · {created}{marker}"
        )
    return "\n".join(lines) + "\n"


_REVIEW_ISSUE_LABELS = {
    "contradiction": "Possible contradiction",
    "hidden_assumption": "Hidden assumption",
    "resolved_question": "Possibly resolved",
    "unused_entity": "Possibly unused entity",
}


def format_fork_result(fork: dict, source_commit: dict) -> str:
    """One-screen output for `smriti fork` confirming the new session and
    giving the user the next command to run."""
    src_hash = _short_hash(source_commit.get("commit_hash"))
    src_message = source_commit.get("message", "").strip() or "(no message)"
    space_id = source_commit.get("repo_id", "")

    branch = fork.get("branch_name", "?")
    session_id = fork.get("session_id", "?")

    lines = [
        f"Forked from `{src_hash}` — \"{src_message}\"",
        f"  → new session: {branch} ({session_id})",
        f"  → seeded from: {src_hash}",
        "",
        "Next: write a checkpoint to this session with",
        f"  smriti checkpoint create {space_id} --session {session_id} < checkpoint.json",
        "",
    ]
    return "\n".join(lines)


def format_restore_brief(
    space: dict,
    commit: dict,
    *,
    full_artifacts: bool = False,
) -> str:
    """Render a specific checkpoint as a continuation brief.

    Shape mirrors `format_state_brief` so an agent reading the output
    can continue work from this checkpoint just as if it were HEAD.
    A header line disambiguates from `smriti state` output.
    """
    head = {
        "commit_id": commit.get("id"),
        "commit_hash": commit.get("commit_hash"),
        "summary": commit.get("summary", ""),
        "objective": commit.get("objective", ""),
        "latest_session_id": None,
        "latest_session_title": None,
    }
    header = (
        f"_Continuation brief for checkpoint "
        f"`{_short_hash(commit.get('commit_hash'))}`_\n\n"
    )
    return header + format_state_brief(space, head, commit, full_artifacts=full_artifacts)


def format_compare_result(result: dict, *, full_artifacts: bool = False) -> str:
    """Render a checkpoint compare response as a readable markdown diff.

    Sections elided when empty. full_artifacts is accepted for CLI
    consistency but not currently used — compare does not surface
    artifacts in this build.
    """
    a = result.get("checkpoint_a") or {}
    b = result.get("checkpoint_b") or {}
    diff = result.get("diff") or {}

    a_hash = _short_hash(a.get("commit_hash"))
    b_hash = _short_hash(b.get("commit_hash"))
    a_branch = a.get("branch_name") or "main"
    b_branch = b.get("branch_name") or "main"

    parts: list[str] = []
    parts.append(f"# Compare `{a_hash}` ↔ `{b_hash}`\n")

    lca = diff.get("common_ancestor_commit_id")
    if lca:
        parts.append(f"Common ancestor: `{lca}`\n")
    else:
        parts.append("Common ancestor: _none — unrelated histories_\n")

    parts.append(
        f"- A: `{a_hash}` on `{a_branch}` — {a.get('message', '').strip() or '(no message)'}\n"
        f"- B: `{b_hash}` on `{b_branch}` — {b.get('message', '').strip() or '(no message)'}\n"
    )

    # Summary / objective — show side-by-side when they differ
    summary_a = (diff.get("summary_a") or "").strip()
    summary_b = (diff.get("summary_b") or "").strip()
    if summary_a or summary_b:
        if summary_a == summary_b and summary_a:
            parts.append(f"## Summary (identical)\n{summary_a}\n")
        else:
            if summary_a:
                parts.append(f"## Summary (A)\n{summary_a}\n")
            if summary_b:
                parts.append(f"## Summary (B)\n{summary_b}\n")

    objective_a = (diff.get("objective_a") or "").strip()
    objective_b = (diff.get("objective_b") or "").strip()
    if objective_a or objective_b:
        if objective_a == objective_b and objective_a:
            parts.append(f"## Objective (identical)\n{objective_a}\n")
        else:
            if objective_a:
                parts.append(f"## Objective (A)\n{objective_a}\n")
            if objective_b:
                parts.append(f"## Objective (B)\n{objective_b}\n")

    def _bullet_group(heading: str, items: list[str]) -> str:
        if not items:
            return ""
        lines = [f"### {heading}"]
        for item in items:
            lines.append(f"- {item}")
        return "\n".join(lines) + "\n"

    def _field_section(label: str, shared_key: str, only_a_key: str, only_b_key: str) -> None:
        shared = diff.get(shared_key) or []
        only_a = diff.get(only_a_key) or []
        only_b = diff.get(only_b_key) or []
        if not (shared or only_a or only_b):
            return
        parts.append(f"## {label}\n")
        group = ""
        group += _bullet_group("Shared", shared)
        group += _bullet_group(f"Only in A (`{a_hash}`)", only_a)
        group += _bullet_group(f"Only in B (`{b_hash}`)", only_b)
        parts.append(group)

    _field_section("Decisions", "decisions_shared", "decisions_only_a", "decisions_only_b")
    _field_section("Assumptions", "assumptions_shared", "assumptions_only_a", "assumptions_only_b")
    _field_section("Tasks", "tasks_shared", "tasks_only_a", "tasks_only_b")

    return "\n".join(p for p in parts if p).rstrip() + "\n"


def format_review(result: dict) -> str:
    issues = result.get("issues") or []
    suggestions = result.get("suggestions") or []

    if not issues and not suggestions:
        return "No issues found — reasoning looks consistent.\n"

    parts = ["# Checkpoint review\n"]
    if issues:
        parts.append(f"Found {len(issues)} issue(s):\n")
        for i, issue in enumerate(issues, 1):
            label = _REVIEW_ISSUE_LABELS.get(issue.get("type"), issue.get("type", "Issue"))
            parts.append(f"{i}. **{label}**")
            parts.append(f"   {issue.get('description', '').strip()}")
            parts.append("")
    if suggestions:
        parts.append("## Suggestions")
        for s in suggestions:
            parts.append(f"- {s}")
        parts.append("")

    return "\n".join(parts).rstrip() + "\n"
