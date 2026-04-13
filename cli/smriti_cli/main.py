"""Smriti CLI entry point.

Commands for agent and programmatic use:

    smriti space list
    smriti space create <name> [--description]
    smriti space delete <space> [-y]
    smriti state <space> [--preview]
    smriti fork <checkpoint-id> [--branch <name>]
    smriti restore <checkpoint-id>
    smriti compare <checkpoint-a> <checkpoint-b>
    smriti checkpoint create <space> [--session <id>]
                                     [--project-root <path>] [--no-project-root]
                                     [--author-agent <name>]       # reads JSON from stdin
    smriti checkpoint create <space> --extract                     # reads markdown, LLM extracts fields
    smriti checkpoint create <space> --extract --dry-run           # preview extracted payload, no commit
    smriti checkpoint show <checkpoint-id>
    smriti checkpoint list <space>
    smriti checkpoint review <checkpoint-id>
    smriti checkpoint delete <checkpoint-id> [--cascade] [-y]

Multi-branch workflow: use `smriti fork <checkpoint>` to start a new
session on a new branch, then `smriti checkpoint create <space> --session
<fork-session-id>` to write a checkpoint on that branch, then `smriti
compare <a> <b>` to see how the branches diverged, and `smriti restore
<checkpoint>` to read any checkpoint as a continuation brief.

`smriti checkpoint create` auto-captures the current working directory
as the checkpoint's project_root and can tag the checkpoint with an
explicit `--author-agent`. Pipe freeform agent markdown to `--extract`
to have the background LLM fill in decisions/assumptions/tasks/etc
for you instead of hand-writing JSON; add `--dry-run` to preview first.
`smriti state` shows full artifact content by default; pass `--preview`
for the truncated brief.

Every command supports --json for structured output.
Default output is a readable markdown brief.

SMRITI_API_URL env var sets the backend URL (default http://localhost:8000).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

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


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, default=str))


def _fail(message: str, code: int = 1) -> None:
    print(message, file=sys.stderr)
    sys.exit(code)


def _confirm(preview: str, yes_flag: bool) -> bool:
    """Interactive 'Type yes' if stdin is a TTY, otherwise require --yes.

    Destructive commands must be approved explicitly. When stdin is piped
    (agent / script use) we refuse without --yes; when interactive we
    require the full word 'yes' typed back.
    """
    print(preview, file=sys.stderr)
    if yes_flag:
        return True
    if not sys.stdin.isatty():
        print(
            "error: refusing to proceed without --yes in non-interactive mode.",
            file=sys.stderr,
        )
        return False
    try:
        resp = input("Type 'yes' to confirm: ").strip().lower()
    except EOFError:
        return False
    return resp == "yes"


_USAGE_HINT = (
    "No checkpoint JSON provided. Pipe JSON on stdin, or use --from-json <path>.\n"
    "Example:\n"
    '  echo \'{"message":"...","summary":"..."}\' | smriti checkpoint create my-space'
)


def _read_raw_content() -> str:
    """Read freeform content from stdin. Used by --extract mode. Fails
    cleanly if stdin is a tty (no content piped)."""
    if sys.stdin.isatty():
        _fail(
            "No content provided for --extract. Pipe a markdown document on stdin:\n"
            "  cat handoff.md | smriti checkpoint create my-space --extract"
        )
    raw = sys.stdin.read()
    if not raw.strip():
        _fail("Empty content on stdin for --extract.")
    return raw


def _read_checkpoint_json(args: argparse.Namespace) -> dict:
    """Read the checkpoint JSON payload from stdin or from --from-json.

    Piping-first: if stdin is not a tty, read from stdin. Otherwise, require
    --from-json. No interactive prompt — this CLI is meant to be invoked by
    agents and scripts.
    """
    if args.from_json:
        if args.from_json == "-":
            raw = sys.stdin.read()
        else:
            with open(args.from_json, "r") as f:
                raw = f.read()
    elif not sys.stdin.isatty():
        raw = sys.stdin.read()
    else:
        _fail(_USAGE_HINT)
        return {}  # unreachable

    if not raw.strip():
        _fail(_USAGE_HINT)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        _fail(f"error: invalid JSON input — {e}")
        return {}  # unreachable


# ── command handlers ─────────────────────────────────────────────────────


def cmd_space_list(client: SmritiClient, args: argparse.Namespace) -> None:
    spaces = client.list_spaces()
    if args.json:
        _print_json(spaces)
    else:
        print(format_space_list(spaces), end="")


def cmd_space_create(client: SmritiClient, args: argparse.Namespace) -> None:
    space = client.create_space(name=args.name, description=args.description or "")
    if args.json:
        _print_json(space)
    else:
        print(f"Created space: {space['name']}  `{space['id']}`")


def cmd_space_delete(client: SmritiClient, args: argparse.Namespace) -> None:
    space = client.resolve_space(args.space)
    commits = client.list_commits(space["id"])
    commit_count = len(commits)
    preview = (
        f"Delete space '{space['name']}' (`{space['id']}`)?\n"
        f"  This will permanently delete {commit_count} checkpoint(s) "
        f"and all sessions/turns under this space."
    )
    if not _confirm(preview, args.yes):
        _fail("Cancelled.", code=0)
    client.delete_space(space["id"])
    if args.json:
        _print_json(
            {"deleted": True, "space_id": space["id"], "commits_deleted": commit_count}
        )
    else:
        print(f"Deleted space '{space['name']}' and its {commit_count} checkpoint(s).")


def cmd_state(client: SmritiClient, args: argparse.Namespace) -> None:
    """Print the continuation brief for a space.

    Default path: one round trip through the multi-branch state endpoint,
    which returns the main-branch brief plus up to 5 active non-main
    branches and a lightweight divergence signal. The extensions are
    elided cleanly when the project has no fork activity, so single-
    agent projects see output identical to the pre-build format.

    --main-only restores the legacy two-call path (get_head + get_commit)
    and produces main-branch-only output. Useful for scripts that parsed
    the old shape or for debugging the endpoint in isolation.
    """
    space = client.resolve_space(args.space)

    if args.main_only:
        # Legacy path — main branch HEAD only. Two round trips.
        head = client.get_head(space["id"])
        if not head.get("commit_id"):
            _print_no_checkpoints(space, args)
            return
        commit = client.get_commit(head["commit_id"])
        space_state: dict | None = None
    else:
        # New default path — one round trip, multi-branch aware.
        state = client.get_space_state(space["id"])
        head = state.get("head") or {}
        commit = state.get("commit") or {}
        if not head.get("commit_id"):
            _print_no_checkpoints(state.get("space") or space, args)
            return
        # Strip the duplicated head/commit so `space_state` only carries
        # the additive payload the formatter consumes (active_branches,
        # active_claims, divergence). Keeps the JSON output sensible too.
        space_state = {
            "active_branches": state.get("active_branches") or [],
            "active_claims": state.get("active_claims") or [],
            "divergence": state.get("divergence"),
        }

    full_artifacts = not args.preview
    if args.json:
        payload = {"space": space, "head": head, "commit": commit}
        if space_state is not None:
            payload["active_branches"] = space_state["active_branches"]
            payload["active_claims"] = space_state["active_claims"]
            payload["divergence"] = space_state["divergence"]
        _print_json(payload)
    else:
        print(
            format_state_brief(
                space, head, commit,
                full_artifacts=full_artifacts,
                space_state=space_state,
            ),
            end="",
        )


def _print_no_checkpoints(space: dict, args: argparse.Namespace) -> None:
    """Render the empty-space message. Shared between the default and
    --main-only paths so both produce the same output on an empty space."""
    if args.json:
        _print_json({"space": space, "head": {}, "commit": None})
        return
    print(f"# {space.get('name', 'Untitled space')}")
    if space.get("description"):
        print(space["description"])
    print()
    print("No checkpoints yet. Create one with `smriti checkpoint create`.")


def cmd_checkpoint_create(client: SmritiClient, args: argparse.Namespace) -> None:
    space = client.resolve_space(args.space)

    if args.extract and args.from_json:
        _fail("--extract and --from-json are mutually exclusive.")

    if args.extract:
        # Read freeform markdown from stdin, send to the extract endpoint,
        # and use the returned fields as the commit payload. No hand-written
        # JSON required.
        content = _read_raw_content()
        extracted = client.extract_checkpoint_content(content)
        # Extractor returns `title`; checkpoints store `message`. Map it.
        # If the LLM returned an empty title, fall back to a generic label
        # so the required `message` field is always populated.
        payload = {
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
    else:
        payload = _read_checkpoint_json(args)
        if not isinstance(payload, dict):
            _fail("Checkpoint JSON must be an object, got: " + type(payload).__name__)
        if not payload.get("message"):
            _fail("Checkpoint JSON must include a 'message' field.")

    if args.dry_run:
        # Print the full payload (extracted or hand-written) as JSON and
        # exit without creating a checkpoint. Useful for reviewing the
        # extractor's output before committing.
        _print_json(payload)
        return

    # The V4 commit endpoint requires a session_id. Agents typically do not
    # have one — the CLI creates a lightweight session on demand and attaches
    # the checkpoint to it. With --session <id>, attach the checkpoint to an
    # existing session instead (used for fork workflows where the caller
    # already ran `smriti fork` and wants to write a checkpoint on the new
    # branch).
    if args.session:
        session_id = args.session
    else:
        session = client.create_session(
            repo_id=space["id"],
            title=f"cli: {payload['message'][:80]}",
        )
        session_id = session["id"]

    # project_root precedence: CLI flag > payload field > auto-capture cwd
    # (unless --no-project-root is passed, in which case the field stays null).
    if args.no_project_root:
        project_root: str | None = None
    elif args.project_root:
        project_root = args.project_root
    elif payload.get("project_root"):
        project_root = payload["project_root"]
    else:
        project_root = os.getcwd()

    # author_agent precedence: CLI flag > payload field > None (backend falls
    # back to session.active_provider for nothing-specified).
    author_agent = args.author_agent or payload.get("author_agent")

    commit_payload: dict = {
        "repo_id": space["id"],
        "session_id": session_id,
        "message": payload["message"],
        "summary": payload.get("summary", ""),
        "objective": payload.get("objective", ""),
        "decisions": payload.get("decisions", []),
        "assumptions": payload.get("assumptions", []),
        "tasks": payload.get("tasks", []),
        "open_questions": payload.get("open_questions", []),
        "entities": payload.get("entities", []),
        "artifacts": payload.get("artifacts", []),
    }
    if project_root is not None:
        commit_payload["project_root"] = project_root
    if author_agent is not None:
        commit_payload["author_agent"] = author_agent

    commit = client.create_chat_commit(commit_payload)

    if args.json:
        _print_json(commit)
    else:
        h = commit.get("commit_hash", "")
        print(f"Created checkpoint: `{h[:7]}` {commit.get('message', '')}")


def cmd_checkpoint_show(client: SmritiClient, args: argparse.Namespace) -> None:
    commit = client.get_commit(args.checkpoint_id)
    if args.json:
        _print_json(commit)
    else:
        print(format_checkpoint(commit, full_artifacts=args.full_artifacts), end="")


def cmd_checkpoint_list(client: SmritiClient, args: argparse.Namespace) -> None:
    space = client.resolve_space(args.space)
    commits = client.list_commits(space["id"], branch=args.branch)
    if args.json:
        _print_json(commits)
    else:
        print(format_commit_list(commits), end="")


def cmd_checkpoint_review(client: SmritiClient, args: argparse.Namespace) -> None:
    result = client.review_checkpoint(args.checkpoint_id)
    if args.json:
        _print_json(result)
    else:
        print(format_review(result), end="")


def cmd_checkpoint_delete(client: SmritiClient, args: argparse.Namespace) -> None:
    commit = client.get_commit(args.checkpoint_id)
    preview = (
        f"Delete checkpoint '{commit.get('message', '')}' "
        f"(`{commit['commit_hash'][:7]}`)?"
    )
    if args.cascade:
        preview += "\n  --cascade set: descendant commits and forked sessions will also be deleted."
    if not _confirm(preview, args.yes):
        _fail("Cancelled.", code=0)
    try:
        client.delete_commit(args.checkpoint_id, cascade=args.cascade)
    except SmritiError as e:
        if e.status == 409 and isinstance(e.detail, dict):
            deps = e.detail.get("dependents", {}) or {}
            lines = [f"Refusing to delete: {e.detail.get('message', str(e))}"]
            for c in deps.get("child_commits", []):
                lines.append(f"    - child commit: {c['label']} ({c['id']})")
            for s in deps.get("forked_sessions", []):
                lines.append(f"    - forked session: {s['label']} ({s['id']})")
            lines.append("  Re-run with --cascade to delete the subtree.")
            _fail("\n".join(lines))
        raise
    if args.json:
        _print_json(
            {
                "deleted": True,
                "checkpoint_id": args.checkpoint_id,
                "cascade": args.cascade,
            }
        )
    else:
        note = " (cascade)" if args.cascade else ""
        print(f"Deleted checkpoint `{commit['commit_hash'][:7]}`{note}.")


def cmd_fork(client: SmritiClient, args: argparse.Namespace) -> None:
    # Fetch the checkpoint first to derive space_id. This also gives us the
    # source message for the output line so the user sees what they forked.
    commit = client.get_commit(args.checkpoint_id)
    space_id = commit.get("repo_id", "")
    fork = client.fork_session(
        space_id=str(space_id),
        checkpoint_id=args.checkpoint_id,
        branch_name=args.branch or "",
    )
    if args.json:
        _print_json(fork)
    else:
        print(format_fork_result(fork, commit), end="")


def cmd_compare(client: SmritiClient, args: argparse.Namespace) -> None:
    result = client.compare_checkpoints(args.checkpoint_a, args.checkpoint_b)
    if args.json:
        _print_json(result)
    else:
        print(format_compare_result(result, full_artifacts=args.full_artifacts), end="")


# ── skills subcommand handlers ──────────────────────────────────────────────


def cmd_skills_list(client: SmritiClient, args: argparse.Namespace) -> None:
    """List available skill pack targets and the template version.

    Does not talk to the backend — the skill pack is a local package
    resource. The `client` arg is unused but kept for signature
    uniformity with the other command handlers.
    """
    from .skill_pack import get_version, list_targets

    version = get_version()
    targets = list_targets()

    if args.json:
        _print_json({
            "version": version,
            "targets": [
                {
                    "key": t.key,
                    "display_name": t.display_name,
                    "default_destination": str(t.default_destination),
                    "primary_mode": t.primary_mode,
                    "description": t.description,
                }
                for t in targets
            ],
        })
        return

    print(f"Smriti skill pack v{version}")
    print()
    print("Available targets:")
    for t in targets:
        print(f"  {t.key:<14} {t.description}")
        print(f"  {'':14} → {t.default_destination}")
    print()
    print("Install with: smriti skills install <target>")


def cmd_skills_show(client: SmritiClient, args: argparse.Namespace) -> None:
    """Print the rendered skill pack for a target to stdout. Useful for
    piping to a custom location: `smriti skills show codex > my-AGENTS.md`.
    """
    from .skill_pack import render

    try:
        content = render(args.target)
    except ValueError as e:
        _fail(f"error: {e}")
        return
    print(content, end="")


def cmd_skills_install(client: SmritiClient, args: argparse.Namespace) -> None:
    """Install the rendered skill pack for a target.

    Writes to the target's default destination unless --destination
    overrides. Refuses to overwrite an existing same-or-newer version
    without --force. --dry-run returns the rendered content without
    touching disk.
    """
    from pathlib import Path

    from .skill_pack import install

    destination = Path(args.destination) if args.destination else None

    try:
        result = install(
            args.target,
            destination=destination,
            force=args.force,
            dry_run=args.dry_run,
        )
    except ValueError as e:
        _fail(f"error: {e}")
        return

    if args.json:
        _print_json({
            "target": result.target.key,
            "destination": str(result.destination),
            "action": result.action,
            "version": result.version,
            "previous_version": result.previous_version,
        })
        return

    if result.action == "dry_run":
        print(
            f"Dry run — would write {result.destination} "
            f"(version {result.version}, not creating)."
        )
        print()
        print(result.content, end="")
        return

    if result.action == "skipped":
        msg = (
            f"Skipped: {result.destination} already has skill pack version "
            f"{result.previous_version} (template is {result.version}). "
            f"Use --force to overwrite."
        )
        _fail(msg)
        return

    verb = "Overwrote" if result.action == "overwritten" else "Installed"
    prev = (
        f" (was version {result.previous_version})"
        if result.previous_version
        else ""
    )
    print(
        f"{verb} skill pack for {result.target.display_name} "
        f"at {result.destination} — version {result.version}{prev}"
    )


# ── branch subcommand handlers ──────────────────────────────────────────────


def cmd_branch_close(client: SmritiClient, args: argparse.Namespace) -> None:
    """Set the disposition of a branch (integrated, abandoned, or active)."""
    space = client.resolve_space(args.space)
    result = client.close_branch(space["id"], args.branch_name, args.disposition)
    if args.json:
        _print_json(result)
    else:
        print(
            f"Branch `{result['branch_name']}` marked `{result['disposition']}` "
            f"({result['sessions_updated']} session(s) updated)."
        )


# ── claim subcommand handlers ───────────────────────────────────────────────


def cmd_claim_create(client: SmritiClient, args: argparse.Namespace) -> None:
    """Create a work claim — declare intent before starting work."""
    space = client.resolve_space(args.space)
    head = client.get_head(space["id"])
    base_commit_id = head.get("commit_id")  # auto-bind to current HEAD

    claim = client.create_claim(
        space_id=space["id"],
        agent=args.agent,
        scope=args.scope,
        branch_name=args.branch or "main",
        base_commit_id=base_commit_id,
        intent_type=args.intent_type,
        ttl_hours=args.ttl,
    )
    if args.json:
        _print_json(claim)
    else:
        print(
            f"Claimed: [{claim['intent_type']}] \"{claim['scope']}\" "
            f"on `{claim['branch_name']}` by `{claim['agent']}`  "
            f"(id: {claim['id']}, expires in {args.ttl}h)"
        )


def cmd_claim_done(client: SmritiClient, args: argparse.Namespace) -> None:
    """Mark a claim as done."""
    claim = client.update_claim(args.claim_id, "done")
    if args.json:
        _print_json(claim)
    else:
        print(f"Claim `{claim['id']}` marked done.")


def cmd_claim_abandon(client: SmritiClient, args: argparse.Namespace) -> None:
    """Mark a claim as abandoned."""
    claim = client.update_claim(args.claim_id, "abandoned")
    if args.json:
        _print_json(claim)
    else:
        print(f"Claim `{claim['id']}` marked abandoned.")


def cmd_claim_list(client: SmritiClient, args: argparse.Namespace) -> None:
    """List active claims for a space."""
    space = client.resolve_space(args.space)
    claims = client.list_claims(space["id"], include_expired=args.all)
    if args.json:
        _print_json(claims)
        return
    if not claims:
        print("No active claims.")
        return
    print(f"{len(claims)} active claim(s):")
    for c in claims:
        agent = c.get("agent", "?")
        scope = c.get("scope", "?")
        intent = c.get("intent_type", "implement")
        branch = c.get("branch_name", "main")
        print(f"  - `{agent}` [{intent}] on `{branch}` — {scope}  (id: {c['id']})")


def cmd_restore(client: SmritiClient, args: argparse.Namespace) -> None:
    commit = client.get_commit(args.checkpoint_id)
    space = client.get_space(str(commit.get("repo_id", "")))
    # Default to full artifacts (agent-first, matching `smriti state`).
    # --preview restores the old truncated behaviour; --full-artifacts is
    # kept as a no-op alias so existing scripts still work.
    full_artifacts = not args.preview
    if args.json:
        _print_json({"space": space, "commit": commit})
    else:
        print(
            format_restore_brief(space, commit, full_artifacts=full_artifacts),
            end="",
        )


# ── argparse wiring ──────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="smriti",
        description="Command-line access to Smriti's reasoning-state backend.",
    )
    parser.add_argument(
        "--api-url",
        help="Smriti backend URL (default: $SMRITI_API_URL or http://localhost:8000)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # space
    space_parser = subparsers.add_parser("space", help="Manage Smriti spaces (projects)")
    space_sub = space_parser.add_subparsers(dest="subcommand", required=True)

    sp_list = space_sub.add_parser("list", help="List all spaces")
    sp_list.add_argument("--json", action="store_true", help="Output structured JSON")
    sp_list.set_defaults(func=cmd_space_list)

    sp_create = space_sub.add_parser("create", help="Create a new space")
    sp_create.add_argument("name", help="Space name")
    sp_create.add_argument("--description", help="Optional description", default="")
    sp_create.add_argument("--json", action="store_true", help="Output structured JSON")
    sp_create.set_defaults(func=cmd_space_create)

    sp_delete = space_sub.add_parser(
        "delete",
        help="Delete a space and all its checkpoints, sessions, and turns",
    )
    sp_delete.add_argument("space", help="Space name or UUID")
    sp_delete.add_argument(
        "-y", "--yes", action="store_true", help="Skip confirmation prompt"
    )
    sp_delete.add_argument("--json", action="store_true", help="Output structured JSON")
    sp_delete.set_defaults(func=cmd_space_delete)

    # state
    state_parser = subparsers.add_parser(
        "state",
        help="Print a continuation-oriented brief of the current project state",
    )
    state_parser.add_argument("space", help="Space name or UUID")
    state_parser.add_argument(
        "--preview",
        action="store_true",
        help="Truncate artifact content to a short preview (default: show full)",
    )
    # Back-compat: --full-artifacts is a no-op because full is now the
    # default. Kept so existing scripts don't break.
    state_parser.add_argument(
        "--full-artifacts",
        action="store_true",
        help="(default) Include full artifact content. Kept for backwards "
             "compatibility; the default is now always full. Use --preview to "
             "truncate instead.",
    )
    state_parser.add_argument(
        "--main-only",
        dest="main_only",
        action="store_true",
        help="Show only main-branch HEAD (legacy pre-V4 behaviour). "
             "Default: multi-branch state — main brief plus any active "
             "non-main branches and divergence signal.",
    )
    state_parser.add_argument("--json", action="store_true", help="Output structured JSON")
    state_parser.set_defaults(func=cmd_state)

    # checkpoint
    cp_parser = subparsers.add_parser("checkpoint", help="Manage checkpoints")
    cp_sub = cp_parser.add_subparsers(dest="subcommand", required=True)

    cp_create = cp_sub.add_parser(
        "create",
        help="Create a checkpoint from JSON on stdin or --from-json <path>",
    )
    cp_create.add_argument("space", help="Space name or UUID")
    cp_create.add_argument(
        "--from-json",
        help="Path to a JSON file with the checkpoint payload (use '-' for stdin)",
    )
    cp_create.add_argument(
        "--extract",
        action="store_true",
        help="Read stdin as freeform markdown and use the LLM extractor to "
             "produce the checkpoint payload automatically. Mutually exclusive "
             "with --from-json.",
    )
    cp_create.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Print the checkpoint payload (extracted or hand-written) as "
             "JSON and exit without creating a checkpoint. Useful for "
             "reviewing the extractor's output before committing.",
    )
    cp_create.add_argument(
        "--session",
        help="Attach the checkpoint to an existing session UUID instead of "
             "creating a new one (used for fork workflows: pair with `smriti fork`)",
    )
    cp_create.add_argument(
        "--project-root",
        dest="project_root",
        help="Explicit working directory path to record on the checkpoint. "
             "Default: the CLI's current working directory.",
    )
    cp_create.add_argument(
        "--no-project-root",
        dest="no_project_root",
        action="store_true",
        help="Do not record any project_root on the checkpoint (overrides "
             "the default cwd auto-capture).",
    )
    cp_create.add_argument(
        "--author-agent",
        dest="author_agent",
        help="Tag the checkpoint with an explicit agent identifier "
             "(e.g. 'claude-code', 'codex-local'). Default: None; the "
             "backend falls back to the session's active provider.",
    )
    cp_create.add_argument("--json", action="store_true", help="Output structured JSON")
    cp_create.set_defaults(func=cmd_checkpoint_create)

    cp_show = cp_sub.add_parser("show", help="Print a specific checkpoint as markdown")
    cp_show.add_argument("checkpoint_id", help="Checkpoint UUID")
    cp_show.add_argument(
        "--full-artifacts",
        action="store_true",
        help="Include full artifact content",
    )
    cp_show.add_argument("--json", action="store_true", help="Output structured JSON")
    cp_show.set_defaults(func=cmd_checkpoint_show)

    cp_list = cp_sub.add_parser("list", help="List checkpoints in a space")
    cp_list.add_argument("space", help="Space name or UUID")
    cp_list.add_argument("--branch", help="Filter by branch name")
    cp_list.add_argument("--json", action="store_true", help="Output structured JSON")
    cp_list.set_defaults(func=cmd_checkpoint_list)

    cp_review = cp_sub.add_parser("review", help="Run consistency review on a checkpoint")
    cp_review.add_argument("checkpoint_id", help="Checkpoint UUID")
    cp_review.add_argument("--json", action="store_true", help="Output structured JSON")
    cp_review.set_defaults(func=cmd_checkpoint_review)

    cp_delete = cp_sub.add_parser(
        "delete",
        help="Delete a checkpoint. Refuses if it has children; pass --cascade to force.",
    )
    cp_delete.add_argument("checkpoint_id", help="Checkpoint UUID")
    cp_delete.add_argument(
        "--cascade",
        action="store_true",
        help="Also delete descendant commits and forked sessions",
    )
    cp_delete.add_argument(
        "-y", "--yes", action="store_true", help="Skip confirmation prompt"
    )
    cp_delete.add_argument("--json", action="store_true", help="Output structured JSON")
    cp_delete.set_defaults(func=cmd_checkpoint_delete)

    # fork (top-level: crosses checkpoint → session)
    fork_parser = subparsers.add_parser(
        "fork",
        help="Fork a new session from an existing checkpoint",
    )
    fork_parser.add_argument("checkpoint_id", help="Checkpoint UUID to fork from")
    fork_parser.add_argument(
        "--branch",
        help="Branch name for the new session (default: branch-YYYY-MM-DD)",
    )
    fork_parser.add_argument("--json", action="store_true", help="Output structured JSON")
    fork_parser.set_defaults(func=cmd_fork)

    # restore (top-level: reads a specific checkpoint as a continuation brief)
    restore_parser = subparsers.add_parser(
        "restore",
        help="Print a continuation-oriented brief of a specific checkpoint",
    )
    restore_parser.add_argument("checkpoint_id", help="Checkpoint UUID")
    restore_parser.add_argument(
        "--preview",
        action="store_true",
        help="Truncate artifact content to a short preview (default: show full)",
    )
    # Back-compat: --full-artifacts is a no-op because full is now the
    # default. Kept so existing scripts do not break. Matches smriti state.
    restore_parser.add_argument(
        "--full-artifacts",
        action="store_true",
        help="(default) Include full artifact content. Kept for backwards "
             "compatibility; the default is now always full. Use --preview to "
             "truncate instead.",
    )
    restore_parser.add_argument("--json", action="store_true", help="Output structured JSON")
    restore_parser.set_defaults(func=cmd_restore)

    # compare (top-level: operates on two checkpoints)
    compare_parser = subparsers.add_parser(
        "compare",
        help="Compare two checkpoints and show the structured diff",
    )
    compare_parser.add_argument("checkpoint_a", help="First checkpoint UUID (side A)")
    compare_parser.add_argument("checkpoint_b", help="Second checkpoint UUID (side B)")
    compare_parser.add_argument(
        "--full-artifacts",
        action="store_true",
        help="Include full artifact content in the diff view",
    )
    compare_parser.add_argument("--json", action="store_true", help="Output structured JSON")
    compare_parser.set_defaults(func=cmd_compare)

    # branch — branch lifecycle / disposition
    branch_parser = subparsers.add_parser(
        "branch",
        help="Manage branch lifecycle (mark branches as integrated or abandoned)",
    )
    branch_sub = branch_parser.add_subparsers(dest="subcommand", required=True)

    br_close = branch_sub.add_parser(
        "close",
        help="Set the disposition of a branch (integrated, abandoned, or active)",
    )
    br_close.add_argument("space", help="Space name or UUID")
    br_close.add_argument("branch_name", help="Branch name to update")
    br_close.add_argument(
        "--disposition", default="integrated",
        choices=["integrated", "abandoned", "active"],
        help="New disposition for the branch (default: integrated)",
    )
    br_close.add_argument("--json", action="store_true")
    br_close.set_defaults(func=cmd_branch_close)

    # claim — work claims for pre-work intent visibility
    claim_parser = subparsers.add_parser(
        "claim",
        help="Manage work claims (pre-work intent visibility for multi-agent coordination)",
    )
    claim_sub = claim_parser.add_subparsers(dest="subcommand", required=True)

    cl_create = claim_sub.add_parser("create", help="Declare intent before starting work")
    cl_create.add_argument("space", help="Space name or UUID")
    cl_create.add_argument("--agent", required=True, help="Your agent identifier (e.g. claude-code)")
    cl_create.add_argument("--scope", required=True, help="One sentence describing what you are about to work on")
    cl_create.add_argument("--branch", help="Branch name (default: main)", default=None)
    cl_create.add_argument(
        "--intent-type", dest="intent_type", default="implement",
        choices=["implement", "review", "investigate", "docs", "test"],
        help="Type of work (default: implement)",
    )
    cl_create.add_argument("--ttl", type=float, default=4.0, help="Hours until expiration (default: 4)")
    cl_create.add_argument("--json", action="store_true")
    cl_create.set_defaults(func=cmd_claim_create)

    cl_done = claim_sub.add_parser("done", help="Mark a claim as done")
    cl_done.add_argument("claim_id", help="Claim UUID")
    cl_done.add_argument("--json", action="store_true")
    cl_done.set_defaults(func=cmd_claim_done)

    cl_abandon = claim_sub.add_parser("abandon", help="Mark a claim as abandoned")
    cl_abandon.add_argument("claim_id", help="Claim UUID")
    cl_abandon.add_argument("--json", action="store_true")
    cl_abandon.set_defaults(func=cmd_claim_abandon)

    cl_list = claim_sub.add_parser("list", help="List active claims for a space")
    cl_list.add_argument("space", help="Space name or UUID")
    cl_list.add_argument("--all", action="store_true", help="Include expired/done/abandoned claims")
    cl_list.add_argument("--json", action="store_true")
    cl_list.set_defaults(func=cmd_claim_list)

    # skills — install the Smriti agent skill pack into an agent host's
    # project directory. The skill pack teaches agents when and why to
    # use Smriti's tools (the load-bearing anti-pattern section is in
    # the template at section 5). This group does not hit the backend —
    # rendering is local.
    skills_parser = subparsers.add_parser(
        "skills",
        help="Install the Smriti agent skill pack for Claude Code / Codex",
    )
    skills_sub = skills_parser.add_subparsers(dest="subcommand", required=True)

    sk_list = skills_sub.add_parser(
        "list",
        help="List available skill pack targets and the template version",
    )
    sk_list.add_argument("--json", action="store_true", help="Output structured JSON")
    sk_list.set_defaults(func=cmd_skills_list)

    sk_show = skills_sub.add_parser(
        "show",
        help="Print the rendered skill pack for a target to stdout",
    )
    sk_show.add_argument(
        "target",
        choices=["claude-code", "codex"],
        help="Which target to render",
    )
    sk_show.set_defaults(func=cmd_skills_show)

    sk_install = skills_sub.add_parser(
        "install",
        help="Install the rendered skill pack to the target's destination",
    )
    sk_install.add_argument(
        "target",
        choices=["claude-code", "codex"],
        help="Which target to install",
    )
    sk_install.add_argument(
        "--destination",
        help="Override the target's default destination path "
             "(e.g. --destination my-AGENTS.md)",
    )
    sk_install.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Render the skill pack and print it without writing to disk",
    )
    sk_install.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing skill pack file even if its version is "
             "equal to or newer than the template's. Use with care.",
    )
    sk_install.add_argument("--json", action="store_true", help="Output structured JSON")
    sk_install.set_defaults(func=cmd_skills_install)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    client = SmritiClient(base_url=args.api_url)

    try:
        args.func(client, args)
    except SmritiError as e:
        _fail(f"error: {e}")
    except (json.JSONDecodeError, ValueError) as e:
        _fail(f"error: invalid JSON input — {e}")
    except FileNotFoundError as e:
        _fail(f"error: file not found — {e}")
    except KeyboardInterrupt:
        return 130

    return 0


if __name__ == "__main__":
    sys.exit(main())
