"""Smriti CLI entry point.

Seven commands for agent and programmatic use:

    smriti space list
    smriti space create <name> [--description]
    smriti state <space>
    smriti checkpoint create <space>               # reads JSON from stdin
    smriti checkpoint show <checkpoint-id>
    smriti checkpoint list <space>
    smriti checkpoint review <checkpoint-id>

Every command supports --json for structured output.
Default output is a readable markdown brief.

SMRITI_API_URL env var sets the backend URL (default http://localhost:8000).
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .client import SmritiClient, SmritiError
from .formatters import (
    format_checkpoint,
    format_commit_list,
    format_review,
    format_space_list,
    format_state_brief,
)


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, default=str))


def _fail(message: str, code: int = 1) -> None:
    print(message, file=sys.stderr)
    sys.exit(code)


_USAGE_HINT = (
    "No checkpoint JSON provided. Pipe JSON on stdin, or use --from-json <path>.\n"
    "Example:\n"
    '  echo \'{"message":"...","summary":"..."}\' | smriti checkpoint create my-space'
)


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


def cmd_state(client: SmritiClient, args: argparse.Namespace) -> None:
    space = client.resolve_space(args.space)
    head = client.get_head(space["id"])

    if not head.get("commit_id"):
        # Space exists but has no checkpoints yet.
        if args.json:
            _print_json({"space": space, "head": head, "commit": None})
            return
        print(f"# {space['name']}")
        if space.get("description"):
            print(space["description"])
        print()
        print("No checkpoints yet. Create one with `smriti checkpoint create`.")
        return

    commit = client.get_commit(head["commit_id"])
    if args.json:
        _print_json({"space": space, "head": head, "commit": commit})
    else:
        print(
            format_state_brief(space, head, commit, full_artifacts=args.full_artifacts),
            end="",
        )


def cmd_checkpoint_create(client: SmritiClient, args: argparse.Namespace) -> None:
    space = client.resolve_space(args.space)
    payload = _read_checkpoint_json(args)

    if not isinstance(payload, dict):
        _fail("Checkpoint JSON must be an object, got: " + type(payload).__name__)

    if not payload.get("message"):
        _fail("Checkpoint JSON must include a 'message' field.")

    # The V4 commit endpoint requires a session_id. Agents typically do not
    # have one — the CLI creates a lightweight session on demand and attaches
    # the checkpoint to it. Agents should not care about the session.
    session = client.create_session(
        repo_id=space["id"],
        title=f"cli: {payload['message'][:80]}",
    )

    commit_payload = {
        "repo_id": space["id"],
        "session_id": session["id"],
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

    # state
    state_parser = subparsers.add_parser(
        "state",
        help="Print a continuation-oriented brief of the current project state",
    )
    state_parser.add_argument("space", help="Space name or UUID")
    state_parser.add_argument(
        "--full-artifacts",
        action="store_true",
        help="Include full artifact content (default truncates previews)",
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
