"""Smriti MCP server — stdio transport.

Exposes the Smriti CLI surface as 12 MCP tools so agents inside MCP-aware
hosts (Claude Code, Cursor, Windsurf) can read and write reasoning state
without shelling out to the `smriti` binary.

Thin shim: each tool builds a SmritiClient, calls 1-2 client methods,
runs the result through an existing formatter, returns a str. FastMCP
auto-wraps the string into TextContent. Errors raise SmritiToolError
which FastMCP converts into an MCP error response.

Entry point: `smriti-mcp` (see cli/pyproject.toml [project.scripts]).
"""
from __future__ import annotations

import json
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import SmritiClient, SmritiError
from .formatters import (
    format_checkpoint,
    format_commit_list,
    format_compare_result,
    format_fork_result,
    format_restore_brief,
    format_review,
    format_space_list,
    format_state_brief,
)


# ── server instance ─────────────────────────────────────────────────────

mcp = FastMCP("smriti")


# ── client factory ──────────────────────────────────────────────────────


def _client() -> SmritiClient:
    """Build a fresh SmritiClient per tool call.

    Constructing per-call is cheap (requests.Session reuse is nice-to-have
    but not critical) and lets SMRITI_API_URL env changes take effect
    without restarting the MCP server subprocess.
    """
    return SmritiClient(base_url=os.environ.get("SMRITI_API_URL"))


# ── error wrapper ───────────────────────────────────────────────────────


class SmritiToolError(Exception):
    """Raised from a tool handler to signal a user-visible error to the
    MCP host. FastMCP catches exceptions raised inside tool functions and
    converts them into MCP error responses on the tool call.

    We raise this instead of SmritiError so the message prefix is
    predictable and includes the HTTP status + structured detail when
    present.
    """


def _raise_from(err: SmritiError) -> None:
    """Convert a SmritiError into a SmritiToolError with consistent
    formatting. Includes HTTP status, message, and structured detail
    (pretty-printed JSON) if present. Always raises."""
    pieces: list[str] = []
    if err.status is not None:
        pieces.append(f"HTTP {err.status}")
    pieces.append(str(err))
    if isinstance(err.detail, dict):
        pieces.append(json.dumps(err.detail, indent=2, default=str))
    raise SmritiToolError("\n".join(pieces))


# ── tools ───────────────────────────────────────────────────────────────


@mcp.tool()
def smriti_list_spaces() -> str:
    """List all Smriti spaces (projects).

    Returns a markdown bullet list of every space's name, UUID, and
    description. Use this to orient on what projects exist before calling
    smriti_state or smriti_list_checkpoints.
    """
    try:
        spaces = _client().list_spaces()
    except SmritiError as e:
        _raise_from(e)
    return format_space_list(spaces)


@mcp.tool()
def smriti_state(space: str, preview: bool = False) -> str:
    """Print a continuation-oriented brief of a space's current state.

    Fetches the HEAD checkpoint of the given space (resolved by name or
    UUID) and renders it as a markdown brief with objective, summary,
    decisions, assumptions, open questions, tasks, and artifacts. This is
    the single best tool for "what's this project about right now" — use
    it at the start of any session where you need to pick up where work
    left off.

    Args:
        space: Space name or UUID.
        preview: If True, truncate artifact content to a short preview
            instead of showing it in full. Default: full artifacts.
    """
    client = _client()
    try:
        s = client.resolve_space(space)
        head = client.get_head(s["id"])
        if not head.get("commit_id"):
            # Space exists but has no checkpoints yet.
            lines = [f"# {s.get('name', 'Untitled space')}"]
            if s.get("description"):
                lines.append("")
                lines.append(s["description"])
            lines.append("")
            lines.append(
                "No checkpoints yet. Create one with smriti_create_checkpoint."
            )
            return "\n".join(lines) + "\n"
        commit = client.get_commit(head["commit_id"])
    except SmritiError as e:
        _raise_from(e)
    return format_state_brief(s, head, commit, full_artifacts=not preview)


@mcp.tool()
def smriti_show_checkpoint(checkpoint_id: str, full_artifacts: bool = False) -> str:
    """Print a specific checkpoint as markdown.

    Fetches the checkpoint by UUID and renders every field (message,
    objective, summary, decisions, assumptions, tasks, open questions,
    entities, artifacts) as a detail view. Use this when you already
    know the checkpoint you want to inspect — for a space-level brief
    of the current HEAD, use smriti_state instead.

    Args:
        checkpoint_id: Checkpoint UUID.
        full_artifacts: If True, include full artifact content.
            Default: truncated preview.
    """
    try:
        commit = _client().get_commit(checkpoint_id)
    except SmritiError as e:
        _raise_from(e)
    return format_checkpoint(commit, full_artifacts=full_artifacts)


@mcp.tool()
def smriti_list_checkpoints(space: str, branch: str = "") -> str:
    """List checkpoints in a space, optionally filtered by branch.

    Returns a markdown list with each checkpoint's short hash, message,
    creation time, and branch annotation (for non-main branches). Use
    this to navigate a project's history before picking a specific
    checkpoint for smriti_show_checkpoint, smriti_compare, or
    smriti_restore.

    Args:
        space: Space name or UUID.
        branch: Optional branch name filter (e.g. "alternative-design").
            Empty = all branches.
    """
    client = _client()
    try:
        s = client.resolve_space(space)
        commits = client.list_commits(s["id"], branch=branch or None)
    except SmritiError as e:
        _raise_from(e)
    return format_commit_list(commits)


@mcp.tool()
def smriti_review_checkpoint(checkpoint_id: str) -> str:
    """Run the LLM-backed consistency review on a checkpoint.

    Sends the checkpoint's structured fields to Smriti's background
    intelligence provider and returns a short list of potential issues
    (contradictions, hidden assumptions, possibly-resolved questions,
    unused entities) plus actionable suggestions. Use this as a
    self-audit before handing a checkpoint off to another agent.

    Args:
        checkpoint_id: Checkpoint UUID.
    """
    try:
        result = _client().review_checkpoint(checkpoint_id)
    except SmritiError as e:
        _raise_from(e)
    return format_review(result)


@mcp.tool()
def smriti_restore(checkpoint_id: str, preview: bool = False) -> str:
    """Print a specific checkpoint as a continuation brief.

    Renders the checkpoint in the same shape as smriti_state but
    targeted at an arbitrary checkpoint rather than the space's HEAD.
    The header explicitly marks this as a restore brief so callers
    can distinguish it from a live state snapshot. Use this to pull
    an older or branched checkpoint into the session context as if
    you were continuing from it.

    Args:
        checkpoint_id: Checkpoint UUID.
        preview: If True, truncate artifact content to a short preview.
            Default: full artifacts.
    """
    client = _client()
    try:
        commit = client.get_commit(checkpoint_id)
        space = client.get_space(str(commit.get("repo_id", "")))
    except SmritiError as e:
        _raise_from(e)
    return format_restore_brief(space, commit, full_artifacts=not preview)


@mcp.tool()
def smriti_compare(
    checkpoint_a: str,
    checkpoint_b: str,
    full_artifacts: bool = False,
) -> str:
    """Compare two checkpoints and return a structured diff.

    Shows the common ancestor, per-side summaries and objectives, and
    Shared / Only-in-A / Only-in-B splits for decisions, assumptions,
    and tasks. Shared-set matching is case- and punctuation-insensitive
    so two checkpoints phrasing the same commitment differently still
    show up as shared. Use this to review how a forked branch has
    diverged from main, or to see two alternative design directions
    side-by-side.

    Args:
        checkpoint_a: First checkpoint UUID (side A).
        checkpoint_b: Second checkpoint UUID (side B).
        full_artifacts: Accepted for interface consistency; not currently
            used (compare does not surface artifacts).
    """
    try:
        result = _client().compare_checkpoints(checkpoint_a, checkpoint_b)
    except SmritiError as e:
        _raise_from(e)
    return format_compare_result(result, full_artifacts=full_artifacts)


@mcp.tool()
def smriti_create_space(name: str, description: str = "") -> str:
    """Create a new Smriti space (project).

    Spaces are the top-level container for reasoning state. Every
    checkpoint lives in exactly one space, and sessions are scoped to
    a space.

    Args:
        name: The space's display name. Does not need to be globally
            unique but `smriti_state`/`smriti_list_checkpoints` prefer
            unique names so they can resolve by name rather than UUID.
        description: Optional short description.
    """
    try:
        space = _client().create_space(name, description)
    except SmritiError as e:
        _raise_from(e)
    return f"Created space `{space['id']}`: {space['name']}\n"


@mcp.tool()
def smriti_fork(checkpoint_id: str, branch: str = "") -> str:
    """Fork a new session from an existing checkpoint.

    Creates a new chat session seeded from the given checkpoint on a
    new branch. The first checkpoint written to the new session (via
    smriti_create_checkpoint with `session=<fork-session-id>`) will
    have the fork source as its parent. Use this to explore an
    alternative direction from a checkpoint without losing the main
    branch.

    Args:
        checkpoint_id: UUID of the checkpoint to fork from.
        branch: Optional branch name for the new session. If empty,
            the backend generates a dated branch name like
            "branch-2026-04-12".
    """
    client = _client()
    try:
        commit = client.get_commit(checkpoint_id)
        fork = client.fork_session(
            space_id=str(commit.get("repo_id", "")),
            checkpoint_id=checkpoint_id,
            branch_name=branch or "",
        )
    except SmritiError as e:
        _raise_from(e)
    return format_fork_result(fork, commit)


@mcp.tool()
def smriti_create_checkpoint(
    space: str,
    content: str,
    session: str = "",
    author_agent: str = "",
    project_root: str = "",
    dry_run: bool = False,
) -> str:
    """Create a checkpoint in the given space from freeform markdown.

    The `content` is sent to Smriti's extract endpoint which uses a
    background LLM to pull out structured fields (message, objective,
    summary, decisions, assumptions, tasks, open_questions, entities,
    artifacts). If `dry_run=True`, the extracted payload is returned as
    JSON inside a fenced code block without creating a checkpoint — use
    this to preview the extractor's output before committing.

    This is the primary tool for writing state into Smriti from an
    agent session: write a freeform markdown document describing what
    you figured out, pass it here, and the LLM does the structuring.

    Args:
        space: Space name or UUID.
        content: Freeform markdown describing the work (a design doc,
            handoff note, session summary, etc.). Must be non-empty.
        session: Optional existing session UUID to attach the checkpoint
            to (used for fork workflows — pair with `smriti_fork`).
            Empty = create a new lightweight session under the space.
        author_agent: Optional agent identifier to tag on the checkpoint
            (e.g. "claude-code", "codex-local"). Empty = backend
            fallback to the session's active provider.
        project_root: Optional absolute path to record as the
            checkpoint's project_root. Empty = no project_root
            recorded. Unlike the CLI, the MCP server does NOT auto-
            capture cwd, because MCP servers run in the host's arbitrary
            working directory. Pass an explicit path when you want the
            checkpoint to know where the project lives on disk.
        dry_run: If True, return the extracted payload as JSON without
            creating a checkpoint.
    """
    if not content.strip():
        raise SmritiToolError("content must be a non-empty markdown string.")

    client = _client()
    try:
        space_dict = client.resolve_space(space)
        extracted = client.extract_checkpoint_content(content)
        payload: dict[str, Any] = {
            "message": (extracted.get("title") or "").strip() or "Extracted checkpoint",
            "objective": extracted.get("objective", ""),
            "summary": extracted.get("summary", ""),
            "decisions": extracted.get("decisions", []),
            "assumptions": extracted.get("assumptions", []),
            "tasks": extracted.get("tasks", []),
            "open_questions": extracted.get("open_questions", []),
            "entities": extracted.get("entities", []),
            "artifacts": extracted.get("artifacts", []),
        }

        if dry_run:
            return (
                "Dry run — extracted payload (no checkpoint created):\n\n"
                "```json\n"
                + json.dumps(payload, indent=2, default=str)
                + "\n```\n"
            )

        if session:
            session_id = session
        else:
            sess = client.create_session(
                repo_id=space_dict["id"],
                title=f"mcp: {payload['message'][:80]}",
            )
            session_id = sess["id"]

        commit_payload: dict[str, Any] = {
            "repo_id": space_dict["id"],
            "session_id": session_id,
            **payload,
        }
        if project_root:
            commit_payload["project_root"] = project_root
        if author_agent:
            commit_payload["author_agent"] = author_agent

        commit = client.create_chat_commit(commit_payload)
    except SmritiError as e:
        _raise_from(e)

    short = (commit.get("commit_hash") or "")[:7]
    msg = commit.get("message", "")
    branch = commit.get("branch_name") or "main"
    return f"Created checkpoint `{short}` on branch `{branch}`: {msg}\n"


@mcp.tool()
def smriti_delete_space(space: str) -> str:
    """Delete a Smriti space and everything it contains.

    Cascades to every checkpoint, session, and turn under the space.
    This is irreversible. The MCP host's tool-approval gate is the
    only safety check — there is no per-tool confirmation prompt
    (unlike the CLI's `-y` flag, because the MCP tool-call approval
    already serves that purpose).

    Args:
        space: Space name or UUID.
    """
    client = _client()
    try:
        s = client.resolve_space(space)
        commits = client.list_commits(s["id"])
        client.delete_space(s["id"])
    except SmritiError as e:
        _raise_from(e)
    return f"Deleted space '{s['name']}' and its {len(commits)} checkpoint(s).\n"


@mcp.tool()
def smriti_delete_checkpoint(checkpoint_id: str, cascade: bool = False) -> str:
    """Delete a checkpoint.

    Refuses with a descriptive error when the checkpoint has child
    commits or forked sessions, unless `cascade=True` is passed. The
    error message lists the blocking dependents (child commits and
    forked session branches) and reminds the caller to retry with
    `cascade=True` if they really want to delete the whole subtree.

    Args:
        checkpoint_id: Checkpoint UUID.
        cascade: If True, also delete descendant commits and forked
            sessions. Default False refuses on any blocking dependent.
    """
    client = _client()
    try:
        commit = client.get_commit(checkpoint_id)
    except SmritiError as e:
        _raise_from(e)

    try:
        client.delete_commit(checkpoint_id, cascade=cascade)
    except SmritiError as e:
        if e.status == 409 and isinstance(e.detail, dict):
            deps = e.detail.get("dependents", {}) or {}
            lines = [f"Refusing to delete: {e.detail.get('message', str(e))}"]
            for c in deps.get("child_commits", []):
                lines.append(f"    - child commit: {c.get('label', '?')} ({c.get('id', '?')})")
            for s in deps.get("forked_sessions", []):
                lines.append(f"    - forked session: {s.get('label', '?')} ({s.get('id', '?')})")
            lines.append("  Re-run with cascade=true to delete the subtree.")
            raise SmritiToolError("\n".join(lines))
        _raise_from(e)

    short = (commit.get("commit_hash") or "")[:7]
    note = " (cascade)" if cascade else ""
    return f"Deleted checkpoint `{short}`{note}.\n"


# ── entry point ─────────────────────────────────────────────────────────


def main() -> None:
    """Entry point for the `smriti-mcp` console script. Runs over stdio.

    The `mcp` SDK emits an INFO line ("Processing request of type …") on
    every tool call, which clutters host log panels during normal use.
    Default the `mcp` logger to WARNING; set `SMRITI_MCP_LOG_LEVEL=INFO`
    (or DEBUG) to re-enable verbose logging when debugging a transport
    issue.
    """
    import logging

    log_level = os.environ.get("SMRITI_MCP_LOG_LEVEL", "WARNING").upper()
    logging.getLogger("mcp").setLevel(log_level)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
