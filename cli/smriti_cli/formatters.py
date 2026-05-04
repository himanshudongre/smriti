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


def _normalize_task_item(item) -> dict:
    """Normalize a task to a dict with at least a 'text' key.

    Handles both legacy string tasks and structured task objects.
    """
    if isinstance(item, str):
        return {"text": item}
    if isinstance(item, dict) and item.get("text"):
        return item
    # Fallback: coerce to string
    return {"text": str(item)}


def _task_section(tasks: list, heading: str = "In progress") -> str:
    """Render tasks with optional intent hints, status, and blocked_by.

    Backward-compatible: plain string tasks render as simple bullets.
    Structured tasks render with inline annotations:
      - Add freshness tests [test] → blocked by: freshness-impl
      - Update cli README [docs] (done)
    """
    if not tasks:
        return ""
    lines = [f"## {heading}"]
    for raw in tasks:
        t = _normalize_task_item(raw)
        text = t["text"]
        parts = [text]

        hint = t.get("intent_hint")
        if hint:
            parts.append(f"[{hint}]")

        task_id = t.get("id")
        if task_id:
            parts.append(f"(id: {task_id})")

        status = t.get("status")
        if status and status != "open":
            parts.append(f"({status})")

        blocked = t.get("blocked_by")
        if blocked:
            parts.append(f"→ blocked by: {blocked}")

        lines.append(f"- {' '.join(parts)}")
    return "\n".join(lines) + "\n"


def _artifact_section(
    artifacts: list[dict],
    preview_chars: int = 800,
    full: bool = False,
    compact: bool = False,
    checkpoint_id: str = "",
) -> str:
    if not artifacts:
        return ""
    if compact:
        # Labels only — no content. Explicit recovery instruction.
        lines = [f"## Attached artifacts (compact — content omitted)"]
        for art in artifacts:
            label = art.get("label") or "Untitled"
            lines.append(f"- {label}")
        lines.append("")
        if checkpoint_id:
            lines.append(
                f"To inspect artifact content: "
                f"`smriti checkpoint show {checkpoint_id} --full-artifacts`"
            )
        else:
            lines.append(
                "To inspect artifact content: "
                "`smriti checkpoint show <checkpoint-id> --full-artifacts`"
            )
        return "\n".join(lines) + "\n"

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


def _artifact_compact_stats(
    artifacts: list[dict],
    checkpoint_id: str = "",
) -> dict | None:
    """Compute savings by rendering both full and compact artifact sections
    and comparing their actual char counts. Returns None only if there are
    no artifacts at all."""
    if not artifacts:
        return None
    full_rendered = _artifact_section(artifacts, full=True)
    compact_rendered = _artifact_section(
        artifacts, compact=True, checkpoint_id=checkpoint_id,
    )
    full_chars = len(full_rendered)
    compact_chars = len(compact_rendered)
    saved = full_chars - compact_chars
    pct = round(saved * 100 / full_chars) if full_chars > 0 else 0
    return {
        "artifacts_omitted": len(artifacts),
        "full_chars": full_chars,
        "compact_chars": compact_chars,
        "chars_saved": max(saved, 0),
        "reduction_pct": max(pct, 0),
    }


def _format_compact_stats_footer(stats: dict | None, compact: bool = True) -> str:
    """Footer for --stats. Always returns a line when called — either
    savings data or an explicit 'nothing to report' message."""
    if not compact:
        return "\n---\ncompact stats: no artifact savings to report (--compact not used)\n"
    if not stats:
        return "\n---\ncompact stats: no artifact savings to report (0 artifacts)\n"
    if stats["chars_saved"] <= 0:
        return "\n---\ncompact stats: no artifact savings to report (artifacts too small)\n"
    return (
        f"\n---\n"
        f"compact stats: {stats['artifacts_omitted']} artifact(s) omitted "
        f"· {stats['chars_saved']} chars saved "
        f"· {stats['reduction_pct']}% smaller artifact section "
        f"(full: {stats['full_chars']} chars → compact: {stats['compact_chars']} chars)\n"
    )


def _format_freshness_section(freshness: dict | None) -> str:
    """Render the freshness check result. Empty string when no freshness
    data (no --since provided). Compact and actionable."""
    if not freshness:
        return ""
    since_hash = freshness.get("since_commit_hash", "?")
    if not freshness.get("changed"):
        return f"## State: unchanged since `{since_hash}`\n"

    count = freshness.get("new_checkpoints_count", 0)
    lines = [f"## State: changed since `{since_hash}`", ""]
    lines.append(f"{count} new checkpoint(s) on main:")
    for c in freshness.get("new_checkpoints", []):
        h = c.get("commit_hash", "?")
        author = c.get("author_agent") or "unknown"
        msg = c.get("message", "")
        created = _relative_time(c.get("created_at") or "")
        lines.append(f"- `{h}` · `{author}` · {created} — {msg}")
    if count > len(freshness.get("new_checkpoints", [])):
        lines.append(f"  ... and {count - len(freshness['new_checkpoints'])} more")
    lines.append("")
    lines.append("Review the current state below before continuing.")
    return "\n".join(lines) + "\n"


def _format_active_branches_section(active_branches: list[dict]) -> str:
    """One line per non-main branch. Pointer, not a brief.

    Empty input → empty string (caller elides the whole section).
    """
    if not active_branches:
        return ""
    lines = ["## Active branches"]
    for b in active_branches:
        hash_short = (b.get("commit_hash") or "")[:7]
        branch = b.get("branch_name") or "?"
        author = b.get("author_agent") or "unknown"
        created = _relative_time(b.get("created_at") or "")
        msg = (b.get("message") or "").strip() or "(no message)"
        lines.append(
            f"- `{branch}` · `{hash_short}` · `{author}` · {created} — {msg}"
        )
    return "\n".join(lines) + "\n"


def _format_active_claims_section(active_claims: list[dict]) -> str:
    """One line per active work claim. Shows who is working on what,
    from which base, on which branch. Elided when empty."""
    if not active_claims:
        return ""
    lines = ["## Active work"]
    for c in active_claims:
        agent = c.get("agent") or "unknown"
        branch = c.get("branch_name") or "main"
        scope = c.get("scope") or "(no scope)"
        intent = c.get("intent_type") or "implement"
        base_hash = c.get("base_commit_hash") or "?"
        created = _relative_time(c.get("claimed_at") or "")
        task_ref = c.get("task_id")
        task_suffix = f" (task: {task_ref})" if task_ref else ""
        lines.append(
            f"- `{agent}` [{intent}] on `{branch}` from `{base_hash}` "
            f"· {created} — {scope}{task_suffix}"
        )
        worktree_id = c.get("worktree_id")
        worktree = c.get("worktree")
        if worktree:
            path = _pretty_path(worktree.get("path")) or worktree.get("path") or "?"
            dirty = worktree.get("dirty_files", 0)
            ahead = worktree.get("ahead", 0)
            behind = worktree.get("behind", 0)
            last_sha = worktree.get("last_commit_sha") or "?"
            last_rel = worktree.get("last_commit_relative") or "?"
            lines.append(f"   · worktree: {path}")
            lines.append(
                f"   · branch: {worktree.get('branch') or '?'} · "
                f"{dirty} dirty · ahead {ahead} · behind {behind} · "
                f"last commit `{last_sha}` {last_rel}"
            )
        elif worktree_id:
            lines.append("   · worktree: (probe failed or worktree closed)")
    return "\n".join(lines) + "\n"


def _format_divergence_signal_section(divergence: dict | None) -> str:
    """Lightweight divergence signal. Names specific conflicting decisions
    per branch (capped by the backend at 3 per side per pair) and points
    the reader at `smriti compare` for the full diff.

    Elides cleanly when `divergence` is None or has no pairs.
    """
    if not divergence:
        return ""
    pairs = divergence.get("pairs") or []
    if not pairs:
        return ""
    lines = ["## Divergence signal"]
    lines.append(
        "Decisions on `main` and one or more active branches disagree. "
        "Run `smriti compare` for the full diff."
    )
    for pair in pairs:
        branch = pair.get("branch_name") or "?"
        branch_hash = (pair.get("branch_commit_hash") or "")[:7]
        lines.append("")
        lines.append(f"### main ↔ `{branch}` (`{branch_hash}`)")
        main_only = pair.get("main_only_decisions") or []
        branch_only = pair.get("branch_only_decisions") or []
        if main_only:
            lines.append("Only on `main`:")
            for d in main_only:
                lines.append(f"- {d}")
        if branch_only:
            lines.append(f"Only on `{branch}`:")
            for d in branch_only:
                lines.append(f"- {d}")
    return "\n".join(lines) + "\n"


def format_state_brief(
    space: dict,
    head: dict,
    commit: dict,
    *,
    full_artifacts: bool = False,
    compact: bool = False,
    stats: bool = False,
    space_state: dict | None = None,
) -> str:
    """A continuation-oriented markdown brief for the current project state.

    Intended to be pasted directly into an agent's (or human's) working
    context. Sections are elided cleanly when empty.

    When `space_state` is provided (as returned by
    `GET /api/v4/chat/spaces/{id}/state`), two additional sections are
    appended after the main brief:

      - ## Active branches  (when `space_state["active_branches"]` is non-empty)
      - ## Divergence signal (when `space_state["divergence"]["pairs"]` is non-empty)

    Both sections are fully elided when their payload is empty, so
    passing `space_state` for a project with no fork activity yields
    output identical to the pre-multi-branch version.

    The main continuation brief always renders first and is unchanged —
    the multi-branch extensions are additive pointers, not a replacement.
    """
    parts: list[str] = []

    # Freshness signal — rendered at the very top so the agent sees it first.
    if space_state is not None:
        parts.append(_format_freshness_section(space_state.get("freshness")))

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
    parts.append(_task_section(tasks))
    checkpoint_id = commit.get("id") or head.get("commit_id") or ""
    parts.append(_artifact_section(
        artifacts,
        full=full_artifacts,
        compact=compact,
        checkpoint_id=str(checkpoint_id),
    ))

    if entities:
        parts.append(f"## Key entities\n{', '.join(entities)}\n")

    # Multi-branch extensions. Appended after the main brief so the
    # agent's continuation context stays at the top of the output where
    # it is most useful. Both helpers return "" for empty input, so
    # projects with no fork activity produce no change.
    if space_state is not None:
        parts.append(
            _format_active_branches_section(space_state.get("active_branches") or [])
        )
        parts.append(
            _format_active_claims_section(space_state.get("active_claims") or [])
        )
        parts.append(
            _format_divergence_signal_section(space_state.get("divergence"))
        )

    result = "\n".join(p for p in parts if p).rstrip() + "\n"

    if stats:
        if compact:
            compact_stats = _artifact_compact_stats(
                artifacts, checkpoint_id=str(checkpoint_id),
            )
            result += _format_compact_stats_footer(compact_stats, compact=True)
        else:
            result += _format_compact_stats_footer(None, compact=False)

    return result


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
    parts.append(_task_section(commit.get("tasks") or [], heading="Tasks"))
    parts.append(_list_section("Open questions", commit.get("open_questions") or []))
    parts.append(_artifact_section(commit.get("artifacts") or [], full=full_artifacts))

    entities = commit.get("entities") or []
    if entities:
        parts.append(f"## Entities\n{', '.join(entities)}\n")

    # Notes from metadata_ — additive founder/human annotations.
    metadata = commit.get("metadata") or commit.get("metadata_") or {}
    notes = metadata.get("notes") or []
    if notes:
        lines = ["## Notes"]
        for n in notes:
            kind = n.get("kind", "note")
            kind_prefix = f"[{kind}] " if kind != "note" else ""
            author = n.get("author", "?")
            created = _relative_time(n.get("created_at") or "")
            text = n.get("text", "")
            lines.append(f"- {kind_prefix}{author} · {created} — {text}")
        parts.append("\n".join(lines) + "\n")

    return "\n".join(p for p in parts if p).rstrip() + "\n"


def format_metrics(data: dict) -> str:
    """Readable one-screen project metrics."""
    parts: list[str] = []
    name = data.get("space_name", "unknown")
    parts.append(f"# {name} — project metrics\n")

    # Coordination
    coord = data.get("coordination", {})
    total = coord.get("total_checkpoints", 0)
    agents = coord.get("unique_agents", 0)
    agent_dist = coord.get("agent_checkpoints", {})
    dist_str = ", ".join(f"{a}: {n}" for a, n in sorted(agent_dist.items()))
    parts.append("## Coordination")
    parts.append(f"{total} checkpoints · {agents} agent{'s' if agents != 1 else ''} ({dist_str})")

    cross = coord.get("cross_agent_continuations", 0)
    parts.append(f"{cross} cross-agent continuation{'s' if cross != 1 else ''}")

    claims_total = coord.get("total_claims", 0)
    rate = coord.get("claim_completion_rate")
    rate_str = f"{int(rate * 100)}% completion" if rate is not None else "no claims resolved"
    task_id_claims = coord.get("claims_with_task_id", 0)
    parts.append(f"{claims_total} claims · {rate_str} · {task_id_claims} with task IDs")
    parts.append("")

    # State quality
    sq = data.get("state_quality", {})
    avg_d = sq.get("avg_decisions_per_checkpoint", 0)
    avg_t = sq.get("avg_tasks_per_checkpoint", 0)
    structured = sq.get("checkpoints_with_structured_tasks", 0)
    with_ids = sq.get("checkpoints_with_task_ids", 0)
    milestones = sq.get("milestone_count", 0)
    noise = sq.get("noise_count", 0)
    parts.append("## State quality")
    parts.append(f"{avg_d} decisions/checkpoint · {avg_t} tasks/checkpoint")
    parts.append(f"{structured} with structured tasks · {with_ids} with task IDs")
    parts.append(f"{milestones} milestone{'s' if milestones != 1 else ''} · {noise} noise label{'s' if noise != 1 else ''}")
    parts.append("")

    # Branches
    br = data.get("branches", {})
    active = br.get("active", 0)
    integrated = br.get("integrated", 0)
    abandoned = br.get("abandoned", 0)
    parts.append("## Branches")
    parts.append(f"{active} active · {integrated} integrated · {abandoned} abandoned")

    return "\n".join(parts).rstrip() + "\n"


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
        # Include the full checkpoint UUID in parentheses right after the
        # short hash. Humans skim past it; agents need it as a handle to
        # pass into smriti_fork / smriti_compare / smriti_restore.
        # Rendered when c["id"] is populated; omitted otherwise so legacy
        # callers without ids still produce a clean line.
        commit_id = c.get("id")
        id_part = f" ({commit_id})" if commit_id else ""
        lines.append(
            f"- `{_short_hash(c.get('commit_hash'))}`{id_part} "
            f"{c.get('message', 'Untitled')}"
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
