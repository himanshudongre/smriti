"""Markdown output formatters for the Smriti CLI.

The default output of every command is a readable markdown brief shaped
so an agent or a human can paste it directly into a working context.
Use --json on any command for structured output instead.
"""

from __future__ import annotations

from datetime import datetime, timezone


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
    parts.append(
        f"Latest checkpoint: `{_short_hash(commit_hash)}`"
        + (f" · {_relative_time(created_at)}" if created_at else "")
        + "\n"
    )

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
    meta_line = f"`{_short_hash(commit_hash)}`"
    if created_at:
        meta_line += f" · {_relative_time(created_at)}"
    meta_line += f" · branch `{branch}`"
    parts.append(meta_line + "\n")

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
