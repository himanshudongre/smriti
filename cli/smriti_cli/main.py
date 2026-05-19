"""Smriti CLI entry point.

Commands for agent and programmatic use:

    smriti space list
    smriti space create <name> [--description] [--project-root <path>] [--no-project-root]
    smriti space set-project-root <space> <path>
    smriti space delete <space> [-y]
    smriti doctor
    smriti state <space> [--preview]
    smriti current <space>
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
    smriti worktree open <space> --agent <id>
    smriti worktree list <space>
    smriti worktree show <worktree-id>
    smriti worktree close <worktree-id>

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
import shlex
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from typing import Any

from . import attachment
from .client import SmritiClient, SmritiError
from .formatters import (
    format_checkpoint,
    format_commit_list,
    format_compare_result,
    format_doctor,
    format_fork_result,
    format_metrics,
    format_project_current,
    format_restore_brief,
    format_review,
    format_space_list,
    format_state_brief,
    format_worktree_ahead,
    format_worktree_dirty,
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


EXPECTED_HEALTH_CAPABILITIES = {
    "claims",
    "structured_tasks",
    "task_ids",
    "checkpoint_notes",
    "branch_disposition",
    "freshness",
    "compact_state",
    "worktrees",
    "worktree_binding",
    "activation_health",
}


def _git_output_at(cwd: str | os.PathLike[str] | None, *args: str) -> str | None:
    """Return trimmed git output for diagnostics, or None outside a git repo."""
    cmd = ["git", *args]
    if cwd is not None:
        cmd = ["git", "-C", str(cwd), *args]
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def _git_output(*args: str) -> str | None:
    """Return trimmed git output for the current directory."""
    return _git_output_at(None, *args)


def _git_context(cwd: str | os.PathLike[str] | None = None) -> dict:
    root = _git_output_at(cwd, "rev-parse", "--show-toplevel")
    sha = _git_output_at(cwd, "rev-parse", "HEAD")
    short = _git_output_at(cwd, "rev-parse", "--short", "HEAD")
    branch = (
        _git_output_at(cwd, "branch", "--show-current")
        or _git_output_at(cwd, "rev-parse", "--abbrev-ref", "HEAD")
    )
    return {
        "git_root": root,
        "git_sha": sha,
        "git_sha_short": short,
        "branch": branch,
    }


def _checkpoint_repo_state() -> dict:
    """Git HEAD/branch of the current repo, recorded on a checkpoint so later
    `smriti state` runs can detect how far the repo has drifted since it.

    Empty when not inside a git repo (or for clients with no repo to inspect).
    """
    info = _git_context()
    head = info.get("git_sha")
    if not head:
        return {}
    branch = info.get("branch")
    return {
        "head": head,
        "head_short": info.get("git_sha_short"),
        "branch": None if branch == "HEAD" else branch,
    }


def _git_porcelain_count(cwd: str | os.PathLike[str] | None, prefix: str) -> int:
    out = _git_output_at(cwd, "status", "--porcelain")
    if not out:
        return 0
    return sum(1 for line in out.splitlines() if line.startswith(prefix))


def _git_dirty_count(cwd: str | os.PathLike[str] | None) -> int:
    out = _git_output_at(cwd, "status", "--porcelain")
    if not out:
        return 0
    return sum(1 for line in out.splitlines() if not line.startswith("??"))


def _git_ahead_behind(cwd: str | os.PathLike[str] | None) -> tuple[int | None, int | None]:
    out = _git_output_at(cwd, "rev-list", "--left-right", "--count", "@{upstream}...HEAD")
    if not out:
        return None, None
    parts = out.split()
    if len(parts) != 2:
        return None, None
    try:
        # With "@{upstream}...HEAD", the left side is commits only on upstream
        # (local is behind) and the right side is commits only on HEAD (local is ahead).
        behind = int(parts[0])
        ahead = int(parts[1])
    except ValueError:
        return None, None
    return ahead, behind


def _paths_same(a: str | None, b: str | None) -> bool | None:
    if not a or not b:
        return None
    try:
        return Path(a).expanduser().resolve() == Path(b).expanduser().resolve()
    except OSError:
        return False


def _git_rev_count(cwd: str | os.PathLike[str] | None, rev_range: str) -> int | None:
    """Count commits in a local git range (e.g. "A..B"). None when the range
    cannot be resolved — typically because one side is not in this repo."""
    out = _git_output_at(cwd, "rev-list", "--count", rev_range)
    if out is None:
        return None
    try:
        return int(out)
    except ValueError:
        return None


def _compare_to_checkpoint(
    commit: dict | None,
    git_root: str,
    current_head: str | None,
    current_branch: str | None,
) -> dict | None:
    """Compare the working repo against the git HEAD/branch the latest
    checkpoint recorded.

    Returns a render-ready dict plus drift signals, or None when the checkpoint
    carries no recorded git state — checkpoints created before this feature, or
    by the MCP server, have none.
    """
    recorded = ((commit or {}).get("context_blob") or {}).get("repo_state") or {}
    ckpt_head = recorded.get("head")
    if not ckpt_head:
        return None

    ckpt_branch = recorded.get("branch")
    branch_changed = bool(
        ckpt_branch and current_branch and ckpt_branch != current_branch
    )

    ahead: int | None = 0
    behind: int | None = 0
    if current_head and ckpt_head == current_head:
        relation = "in_sync"
    else:
        ahead = _git_rev_count(git_root, f"{ckpt_head}..HEAD")
        behind = _git_rev_count(git_root, f"HEAD..{ckpt_head}")
        if ahead is None or behind is None:
            relation = "unknown"  # checkpoint commit not in this repo's history
        elif ahead and behind:
            relation = "diverged"
        elif ahead:
            relation = "ahead"
        elif behind:
            relation = "behind"
        else:
            relation = "in_sync"

    signals: list[dict[str, str]] = []
    if relation == "ahead":
        signals.append({
            "kind": "ahead_of_checkpoint",
            "message": (
                f"repo is {ahead} commit(s) ahead of the last checkpoint — "
                "recorded state may be stale"
            ),
            "severity": "attention",
        })
    elif relation == "diverged":
        signals.append({
            "kind": "diverged_from_checkpoint",
            "message": (
                "repo history has diverged from the last checkpoint — "
                "recorded state may be stale"
            ),
            "severity": "attention",
        })
    elif relation == "unknown":
        signals.append({
            "kind": "checkpoint_commit_missing",
            "message": "the last checkpoint's commit is not in this repo's history",
            "severity": "attention",
        })
    if branch_changed:
        signals.append({
            "kind": "checkpoint_branch_changed",
            "message": (
                f"the last checkpoint was taken on a different branch (`{ckpt_branch}`)"
            ),
            "severity": "attention",
        })

    return {
        "head_short": recorded.get("head_short") or ckpt_head[:7],
        "branch": ckpt_branch,
        "relation": relation,
        "ahead": ahead,
        "behind": behind,
        "branch_changed": branch_changed,
        "signals": signals,
    }


def _build_repo_state(space: dict, commit: dict | None = None) -> dict | None:
    """Inspect the caller's local git repo for state/drift rendering.

    This is intentionally read-only and cheap: no fetch, no network, no merge
    base search beyond local refs. Remote freshness is represented only by the
    current upstream ahead/behind counters already present in the local clone.
    When the latest checkpoint recorded its git state, the result also carries
    a checkpoint-relative comparison (see `_compare_to_checkpoint`).
    """
    info = _git_context()
    git_root = info.get("git_root")
    if not git_root:
        return None

    ahead, behind = _git_ahead_behind(git_root)
    branch = info.get("branch")
    detached = branch == "HEAD"
    canonical_root = space.get("project_root")
    root_matches = _paths_same(git_root, canonical_root)

    dirty = _git_dirty_count(git_root)
    untracked = _git_porcelain_count(git_root, "??")

    signals: list[dict[str, str]] = []
    if root_matches is False:
        signals.append({
            "kind": "project_root_mismatch",
            "message": "current git root differs from this space's project_root",
            "severity": "attention",
        })
    if dirty:
        signals.append({
            "kind": "dirty_worktree",
            "message": f"{dirty} tracked file(s) have uncommitted changes",
            "severity": "attention",
        })
    if untracked:
        signals.append({
            "kind": "untracked_files",
            "message": f"{untracked} untracked file(s) present",
            "severity": "attention",
        })
    if detached:
        signals.append({
            "kind": "detached_head",
            "message": "repository is on a detached HEAD",
            "severity": "attention",
        })
    if behind:
        signals.append({
            "kind": "behind_upstream",
            "message": f"local branch is {behind} commit(s) behind upstream",
            "severity": "attention",
        })
    if ahead:
        signals.append({
            "kind": "ahead_upstream",
            "message": f"local branch is {ahead} commit(s) ahead of upstream",
            "severity": "info",
        })

    # Checkpoint-relative drift: how far the working repo has moved since the
    # latest checkpoint recorded its git HEAD/branch.
    checkpoint = _compare_to_checkpoint(
        commit, git_root, info.get("git_sha"), None if detached else branch
    )
    if checkpoint:
        signals.extend(checkpoint["signals"])

    return {
        "git_root": git_root,
        "branch": None if detached else branch,
        "detached": detached,
        "head": info.get("git_sha"),
        "head_short": info.get("git_sha_short"),
        "dirty_files": dirty,
        "untracked_files": untracked,
        "ahead": ahead,
        "behind": behind,
        "upstream_known": ahead is not None and behind is not None,
        "project_root": canonical_root,
        "project_root_matches": root_matches,
        "checkpoint": checkpoint,
        "signals": signals,
    }


def _is_smriti_source_root(path: str | None) -> bool:
    if not path:
        return False
    root = Path(path)
    return (
        (root / "cli" / "smriti_cli" / "main.py").exists()
        and (root / "backend" / "app" / "main.py").exists()
    )


def _build_cwd_info() -> dict:
    info = _git_context()
    info["path"] = os.getcwd()
    info["is_smriti_source"] = _is_smriti_source_root(info.get("git_root"))
    return info


def _build_smriti_source_info() -> dict:
    """Detect the Smriti source checkout backing this CLI, if available.

    `smriti doctor` is often run from a user's project repo. Runtime freshness
    must compare the backend to Smriti's own source checkout, not the caller's
    app repo. Editable installs have `__file__` inside the Smriti checkout; a
    wheel/global install may not, in which case the git comparison is simply
    unavailable rather than a mismatch.
    """
    module_dir = Path(__file__).resolve().parent
    info = _git_context(module_dir)
    info["path"] = str(module_dir)
    info["is_smriti_source"] = _is_smriti_source_root(info.get("git_root"))
    if not info["is_smriti_source"]:
        info["git_root"] = None
        info["git_sha"] = None
        info["git_sha_short"] = None
        info["branch"] = None
    return info


def _git_sha_matches(backend_sha: str | None, local_sha: str | None) -> bool | None:
    if not backend_sha or not local_sha:
        return None
    backend = backend_sha.strip()
    local = local_sha.strip()
    if not backend or not local:
        return None
    return local.startswith(backend) or backend.startswith(local)


def _resolve_executable_path(value: str | None) -> str | None:
    """Resolve a command path for diagnostics without requiring it to exist."""
    if not value:
        return None
    candidate = Path(value)
    if not candidate.is_absolute():
        found = shutil.which(value)
        if found:
            candidate = Path(found)
    try:
        return str(candidate.expanduser().resolve())
    except OSError:
        return str(candidate)


def _package_version() -> str | None:
    try:
        return metadata.version("smriti-cli")
    except metadata.PackageNotFoundError:
        return None


def _build_cli_info() -> dict:
    """Return local CLI-source details so stale PATH wrappers are visible."""
    invoked = _resolve_executable_path(sys.argv[0])
    path_entry = _resolve_executable_path(shutil.which("smriti"))
    match: bool | None
    if invoked and path_entry:
        match = invoked == path_entry
    elif invoked or path_entry:
        match = False
    else:
        match = None

    return {
        "executable": invoked,
        "path_entry": path_entry,
        "path_matches_executable": match,
        "package_version": _package_version(),
    }


def _smriti_hook_executable() -> str:
    """Choose a portable smriti executable for generated startup hooks.

    Prefer the script that is running `smriti init` when it looks like the
    installed `smriti` entry point. Fall back to the first `smriti` on PATH,
    then to the bare command. We deliberately avoid repo-relative paths such
    as `backend/.venv/bin/smriti` because init runs inside the user's target
    project, not necessarily inside the Smriti checkout.
    """
    invoked = _resolve_executable_path(sys.argv[0])
    if invoked:
        invoked_path = Path(invoked)
        if invoked_path.name == "smriti" and os.access(invoked_path, os.X_OK):
            return invoked

    path_entry = _resolve_executable_path(shutil.which("smriti"))
    return path_entry or "smriti"


def _smriti_mcp_executable() -> str:
    """Choose a practical MCP server executable for generated config hints."""
    smriti_exe = _smriti_hook_executable()
    if smriti_exe != "smriti":
        sibling = Path(smriti_exe).with_name("smriti-mcp")
        if sibling.exists() and os.access(sibling, os.X_OK):
            return str(sibling)

    path_entry = _resolve_executable_path(shutil.which("smriti-mcp"))
    return path_entry or "smriti-mcp"


def _build_session_start_hook_command(api_url: str | None = None) -> str:
    """Build the SessionStart hook command.

    The hook is space-agnostic: `smriti state --compact` resolves the space
    from the repo's `.smriti.json` attachment, so the same hook works for
    every attached project and survives re-attaching to a different space.
    """
    args = [shlex.quote(_smriti_hook_executable())]
    if api_url:
        args.extend(["--api-url", shlex.quote(api_url)])
    args.extend(
        [
            "state",
            "--compact",
            "2>/dev/null",
            "||",
            "echo",
            shlex.quote(
                "Smriti backend not reachable. Start with: make dev-local"
            ),
        ]
    )
    return " ".join(args)


def _resolve_space(client: SmritiClient, args: argparse.Namespace) -> dict:
    """Resolve the space a command should act on.

    Precedence:
      1. an explicit `<space>` argument, when the command was given one;
      2. otherwise the repo's `.smriti.json` attachment.

    Fails with actionable guidance when neither is available, so an agent
    in an un-attached repo gets a clear next step instead of a stack trace.
    """
    explicit = getattr(args, "space", None)
    if explicit:
        return client.resolve_space(explicit)

    record = attachment.read_attachment()
    if record is None:
        _fail(
            "No space given, and this directory is not attached to a Smriti space.\n"
            "Attach it once with `smriti attach <space>` (or `smriti init <space>`),\n"
            "or pass the space explicitly: `smriti <command> <space>`."
        )

    # Prefer the recorded id; fall back to the name when the id misses — the
    # attachment is git-committable and may be read against another backend.
    space_id = record.get("space_id")
    if space_id:
        try:
            return client.get_space(space_id)
        except SmritiError as e:
            if e.status != 404:
                raise
    try:
        return client.resolve_space(record["space"])
    except SmritiError:
        _fail(
            f'This repo is attached to Smriti space "{record["space"]}", but it '
            f"was not found on the backend at {client.base_url}.\n"
            "Re-attach with `smriti attach <space>`, or start/point at the right backend."
        )


def _is_smriti_session_start_entry(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    hooks = entry.get("hooks")
    if not isinstance(hooks, list):
        return False
    for hook in hooks:
        if not isinstance(hook, dict):
            continue
        command = hook.get("command")
        normalized = command.replace("'", "").replace('"', "") if isinstance(command, str) else ""
        if "smriti" in normalized and " state " in normalized:
            return True
    return False


def _background_provider_check(providers: dict) -> str:
    bg = providers.get("background_intelligence") if providers else None
    if not bg:
        return "unknown"
    return "ready" if bg.get("configured") else "mock_or_disabled"


def _build_doctor_report(client: SmritiClient) -> dict:
    """Build a small diagnostics report without attempting repairs."""
    source_info = _build_smriti_source_info()
    cwd_info = _build_cwd_info()
    if not source_info.get("git_sha") and cwd_info.get("is_smriti_source"):
        source_info = dict(cwd_info)
    source_sha = source_info.get("git_sha")

    report = {
        "api_url": client.base_url,
        "backend": {
            "reachable": False,
            "status": None,
            "git_sha": None,
            "capabilities": [],
            "error": None,
        },
        # Backward-compatible alias: historically "local" meant cwd. It now
        # means the local Smriti source/install used for runtime comparison.
        "local": source_info,
        "source": source_info,
        "cwd": cwd_info,
        "cli": _build_cli_info(),
        "checks": {
            "runtime_match": "unknown",
            "missing_capabilities": None,
            "cli_path": "unknown",
            "background_provider": "unknown",
        },
        "hints": [],
    }

    try:
        health = client.get_health()
    except SmritiError as e:
        report["backend"]["error"] = str(e)
        report["hints"].append(
            "Backend is not reachable; start Smriti with `make dev-local` "
            "for solo/local mode or `make dev-postgres` for shared/team mode, "
            "then rerun `smriti doctor`."
        )
        cli_info = report.get("cli") or {}
        if cli_info.get("path_matches_executable") is False:
            report["checks"]["cli_path"] = "mismatch"
            report["hints"].append(
                "The `smriti` on PATH differs from this doctor executable. "
                "Activate the intended environment or update PATH before daily use."
            )
        return report

    capabilities = sorted(health.get("capabilities") or [])
    backend_sha = health.get("git_sha")
    database = health.get("database") or {}
    providers = health.get("providers") or {}
    missing = sorted(EXPECTED_HEALTH_CAPABILITIES - set(capabilities))
    match = _git_sha_matches(backend_sha, source_sha)

    report["backend"].update({
        "reachable": True,
        "status": health.get("status"),
        "git_sha": backend_sha,
        "capabilities": capabilities,
        "database": database,
        "providers": providers,
        "error": None,
    })
    report["checks"]["missing_capabilities"] = missing
    report["checks"]["background_provider"] = _background_provider_check(providers)

    cli_info = report.get("cli") or {}
    cli_match = cli_info.get("path_matches_executable")
    if cli_match is True:
        report["checks"]["cli_path"] = "ok"
    elif cli_match is False:
        report["checks"]["cli_path"] = "mismatch"
        report["hints"].append(
            "The `smriti` on PATH differs from this doctor executable. "
            "Activate the intended environment or update PATH before daily use."
        )
    else:
        report["checks"]["cli_path"] = "unknown"

    if match is True:
        report["checks"]["runtime_match"] = "ok"
    elif match is False:
        report["checks"]["runtime_match"] = "mismatch"
        report["hints"].append(
            "Backend git_sha differs from the local Smriti source HEAD; "
            "restart the backend after syncing code, or check out the commit "
            "the backend is running."
        )
    else:
        report["checks"]["runtime_match"] = "not_applicable"
        if source_info.get("git_root"):
            report["hints"].append(
                "Could not compare backend git_sha with the local Smriti source checkout."
            )

    if health.get("status") != "ok":
        report["hints"].append(
            f"Backend status is `{health.get('status') or 'unknown'}` instead of `ok`."
        )
    if missing:
        report["hints"].append(
            "Backend is missing capabilities expected by this CLI: "
            + ", ".join(missing)
            + ". Pull/restart the backend if you expected newer behavior."
        )
    if not database:
        report["hints"].append(
            "Backend /health did not report database mode; restart after updating "
            "the backend if you expected activation diagnostics."
        )

    bg = providers.get("background_intelligence") if providers else None
    if not bg:
        report["hints"].append(
            "Backend /health did not report provider status; provider/mock "
            "confidence is unknown."
        )
    elif not bg.get("configured"):
        provider = bg.get("provider") or "background"
        report["hints"].append(
            f"Background intelligence provider `{provider}` is not configured; "
            "checkpoint extract/review flows may use mock output or fail."
        )

    return report


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


def cmd_doctor(client: SmritiClient, args: argparse.Namespace) -> None:
    """Print narrow backend/runtime diagnostics."""
    report = _build_doctor_report(client)
    if args.json:
        _print_json(report)
    else:
        print(format_doctor(report), end="")


def cmd_space_list(client: SmritiClient, args: argparse.Namespace) -> None:
    spaces = client.list_spaces()
    if args.json:
        _print_json(spaces)
    else:
        print(format_space_list(spaces), end="")


def cmd_space_create(client: SmritiClient, args: argparse.Namespace) -> None:
    if args.no_project_root:
        project_root: str | None = None
    elif args.project_root:
        project_root = args.project_root
    else:
        project_root = os.getcwd()

    space = client.create_space(
        name=args.name,
        description=args.description or "",
        project_root=project_root,
    )
    if args.json:
        _print_json(space)
    else:
        print(f"Created space: {space['name']}  `{space['id']}`")
        if project_root is not None:
            print(f"Project root: {project_root}")


def cmd_space_set_project_root(client: SmritiClient, args: argparse.Namespace) -> None:
    space = _resolve_space(client, args)
    if args.here or args.path in {".", "--here"}:
        path = os.getcwd()
    elif args.path:
        path = args.path
    else:
        _fail("error: path is required unless --here is passed")
    updated = client.set_project_root(space["id"], path)
    if args.json:
        _print_json(updated)
    else:
        print(f"Set project_root for '{updated['name']}' to {updated['project_root']}")


def cmd_space_delete(client: SmritiClient, args: argparse.Namespace) -> None:
    space = _resolve_space(client, args)
    commits = client.list_commits(space["id"])
    commit_count = len(commits)

    # Is this the space the current repo is attached to?
    record = attachment.read_attachment()
    is_attached = bool(record) and (
        record.get("space_id") == space["id"]
        or record.get("space") == space["name"]
    )

    # Destructive-delete guard. `-y` skips the confirmation prompt, but it must
    # NOT, on its own, delete a space that holds real work or is attached to a
    # repo. Those need an explicit, separate --force signal — the same
    # "name the stronger flag" shape as `checkpoint delete --cascade`.
    blockers: list[str] = []
    if commit_count > 0:
        blockers.append(
            f"it holds {commit_count} checkpoint(s); deletion cascades to all of "
            f"them plus every session and turn, and cannot be undone"
        )
    if is_attached:
        blockers.append(
            "this repo is attached to it (.smriti.json); deleting it unbinds the repo"
        )
    if blockers and not args.force:
        lines = [f"Refusing to delete space '{space['name']}' (`{space['id']}`):"]
        lines += [f"  - {b}" for b in blockers]
        lines.append("")
        lines.append(
            "  -y is not enough for a destructive delete like this. If you are "
            "certain,\n  re-run with --force (required in addition to -y or the prompt)."
        )
        _fail("\n".join(lines))

    preview = (
        f"Delete space '{space['name']}' (`{space['id']}`)?\n"
        f"  This will permanently delete {commit_count} checkpoint(s) "
        f"and all sessions/turns under this space."
    )
    if is_attached:
        preview += "\n  This repo is attached to this space — deleting it unbinds the repo."
    if not _confirm(preview, args.yes):
        _fail("Cancelled.", code=0)
    client.delete_space(space["id"], force=args.force)
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
    space = _resolve_space(client, args)

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
        since = getattr(args, "since", None) or ""
        state = client.get_space_state(space["id"], since=since)
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
            "freshness": state.get("freshness"),
        }

    full_artifacts = not args.preview and not args.compact
    compact = args.compact
    show_stats = getattr(args, "stats", False)
    repo_state = _build_repo_state(space, commit)
    if args.json:
        payload = {"space": space, "head": head, "commit": commit}
        if repo_state is not None:
            payload["repo_state"] = repo_state
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
                compact=compact,
                stats=show_stats,
                space_state=space_state,
                repo_state=repo_state,
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
    if space.get("project_root"):
        print(f"Project root: {space['project_root']}")
    print()
    print("No checkpoints yet. Create one with `smriti checkpoint create`.")


def _current_task_item(raw: Any) -> dict:
    if isinstance(raw, str):
        return {"text": raw}
    if isinstance(raw, dict):
        return raw
    return {"text": str(raw)}


def _current_open_tasks_by_intent(tasks: list) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for raw in tasks:
        task = _current_task_item(raw)
        status = task.get("status", "open")
        if status and status != "open":
            continue
        intent = task.get("intent_hint") or task.get("intent_type") or "other"
        grouped.setdefault(intent, []).append(task)
    return grouped


def _current_milestones(commits: list[dict], limit: int = 5) -> list[dict]:
    milestones: list[dict] = []
    for commit in commits:
        metadata = commit.get("metadata") or commit.get("metadata_") or {}
        notes = metadata.get("notes") or []
        for note in notes:
            if note.get("kind") != "milestone":
                continue
            milestones.append({
                "commit_hash": commit.get("commit_hash"),
                "message": commit.get("message"),
                "note": note.get("text") or commit.get("message"),
                "author": note.get("author") or commit.get("author_agent"),
                "created_at": note.get("created_at") or commit.get("created_at"),
            })
            if len(milestones) >= limit:
                return milestones

        # Lineage/current endpoints may expose only note kind summaries. When
        # the note text is unavailable, still surface the checkpoint as a
        # milestone so the current-state view does not hide the marker.
        note_kinds = commit.get("note_kinds") or []
        if "milestone" in note_kinds:
            milestones.append({
                "commit_hash": commit.get("commit_hash"),
                "message": commit.get("message"),
                "note": commit.get("message"),
                "author_agent": commit.get("author_agent"),
                "created_at": commit.get("created_at"),
            })
            if len(milestones) >= limit:
                return milestones
    return milestones


def _current_activity(commits: list[dict], limit: int = 5) -> list[dict]:
    return [
        {
            "id": c.get("id"),
            "commit_hash": c.get("commit_hash"),
            "message": c.get("message"),
            "author_agent": c.get("author_agent"),
            "branch_name": c.get("branch_name"),
            "created_at": c.get("created_at"),
        }
        for c in commits[:limit]
    ]


def _build_current_payload_from_existing(client: SmritiClient, space: dict) -> dict:
    """Compose the Project Current State contract from shipped endpoints.

    This keeps the CLI usable while the backend-owned compact endpoint rolls
    out in parallel. Once the endpoint is present, `cmd_current` will prefer
    it and skip this compatibility path.
    """
    space_id = space["id"]
    state = client.get_space_state(space_id)
    commits = client.list_commits(space_id)
    try:
        metrics = client.get_space_metrics(space_id)
    except SmritiError as e:
        if e.status not in (404, 405):
            raise
        metrics = {}

    commit = state.get("commit") or {}
    active_work = state.get("active_claims") or []
    active_branches = state.get("active_branches") or []
    open_tasks = _current_open_tasks_by_intent(commit.get("tasks") or [])
    open_task_count = sum(len(items) for items in open_tasks.values())
    milestones = _current_milestones(commits)

    attention: list[dict] = []
    if not commit:
        attention.append({
            "severity": "setup",
            "message": "No checkpoints yet; create the first checkpoint to establish project direction.",
        })
    divergence = state.get("divergence") or {}
    if divergence.get("pairs"):
        attention.append({
            "severity": "risk",
            "message": "Active branch divergence detected; run `smriti compare` before reconciling.",
        })
    if active_branches:
        attention.append({
            "severity": "branch",
            "message": f"{len(active_branches)} active branch(es) need disposition when resolved.",
        })
    open_questions = commit.get("open_questions") or []
    if open_questions:
        attention.append({
            "severity": "question",
            "message": f"{len(open_questions)} open question(s) on the latest checkpoint.",
        })
    if open_task_count > 0 and not active_work:
        attention.append({
            "severity": "next",
            "message": f"{open_task_count} open task(s) are available with no active claim.",
        })

    coord = metrics.get("coordination") or {}
    state_quality = metrics.get("state_quality") or {}
    branch_metrics = metrics.get("branches") or {}
    counts = {
        "checkpoints": coord.get("total_checkpoints", len(commits)),
        "active_claims": len(active_work),
        "active_branches": branch_metrics.get("active", len(active_branches)),
        "open_tasks": open_task_count,
        "milestones": state_quality.get("milestone_count", len(milestones)),
        "attention": len(attention),
    }

    return {
        "space_id": space_id,
        "name": space.get("name"),
        "description": space.get("description") or "",
        "current_direction": (
            commit.get("objective")
            or commit.get("summary")
            or commit.get("message")
            or ""
        ),
        "counts": counts,
        "attention": attention,
        "active_work": active_work,
        "recent_milestones": milestones,
        "open_tasks_by_intent": open_tasks,
        "recent_activity": _current_activity(commits),
    }


def cmd_current(client: SmritiClient, args: argparse.Namespace) -> None:
    """Print the compact Project Current State surface for a space."""
    space = _resolve_space(client, args)
    try:
        data = client.get_current_state(space["id"])
    except SmritiError as e:
        if e.status not in (404, 405):
            raise
        data = _build_current_payload_from_existing(client, space)

    if args.json:
        _print_json(data)
    else:
        print(format_project_current(data), end="")


def cmd_checkpoint_create(client: SmritiClient, args: argparse.Namespace) -> None:
    space = _resolve_space(client, args)

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

    # Record local git HEAD/branch so later `smriti state` runs can detect
    # how far the repo has drifted since this checkpoint. Best-effort: empty
    # outside a git repo, which the backend stores as no repo_state.
    repo_state = _checkpoint_repo_state()
    if repo_state:
        commit_payload["repo_state"] = repo_state

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
    space = _resolve_space(client, args)
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


def cmd_checkpoint_note(client: SmritiClient, args: argparse.Namespace) -> None:
    """Add a note to a checkpoint."""
    result = client.add_checkpoint_note(
        checkpoint_id=args.checkpoint_id,
        text=args.text,
        author=args.author,
        kind=args.kind,
    )
    if args.json:
        _print_json(result)
    else:
        kind_label = f" [{result['kind']}]" if result['kind'] != 'note' else ""
        print(f"Note added to checkpoint `{result['checkpoint_id'][:8]}…`{kind_label}")


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


# ── init command handler ─────────────────────────────────────────────────────


def cmd_init(client: SmritiClient, args: argparse.Namespace) -> None:
    """One-step agent onboarding: create space, install skill packs,
    configure SessionStart hook. Idempotent — safe to run twice."""
    import json as _json

    from .skill_pack import install as install_skill

    space_name = args.space
    results: list[str] = []
    next_steps: list[str] = []

    # 1. Verify backend reachability.
    try:
        client.list_spaces()
        results.append("Backend reachable at " + client.base_url)
    except Exception:
        _fail(
            f"error: Cannot reach Smriti backend at {client.base_url}.\n"
            "Start the backend with `make dev-local` for solo/local mode, "
            "or `make dev-postgres` for Postgres/shared-team mode."
        )
        return

    # 2. Create or connect space.
    try:
        space = client.resolve_space(space_name)
        results.append(f'Space "{space_name}" exists (id: {space["id"][:8]}…)')
    except Exception:
        space = client.create_space(
            name=space_name,
            description=args.description or "",
        )
        results.append(f'Space "{space_name}" created (id: {space["id"][:8]}…)')

    # 2b. Attach this repo to the space — a durable .smriti.json binding so
    #     commands and the session hook resolve the space automatically.
    repo_dir = _git_output("rev-parse", "--show-toplevel") or os.getcwd()
    try:
        client.set_project_root(space["id"], repo_dir)
    except Exception:
        pass  # project_root is a backend hint; the attachment is the source of truth
    attachment_path = attachment.write_attachment(repo_dir, space["name"], space["id"])
    results.append(f"Repo attached to space → {attachment_path}")

    # 3. Install Claude Code skill pack.
    claude_result = install_skill("claude-code")
    if claude_result.action == "created":
        results.append(f"Skill pack installed for Claude Code → {claude_result.destination}")
    elif claude_result.action == "overwritten":
        results.append(f"Skill pack upgraded for Claude Code → {claude_result.destination}")
    elif claude_result.action == "skipped":
        results.append(f"Skill pack for Claude Code is current (v{claude_result.version})")

    # 4. Install Codex skill pack — with safety check.
    agents_path = Path("AGENTS.md")
    codex_safe = True
    if agents_path.exists():
        content = agents_path.read_text(encoding="utf-8")
        if "smriti_skill_pack_version" not in content and content.strip():
            # Non-Smriti content exists — do not overwrite.
            codex_safe = False
            results.append(
                f"Skipped Codex skill pack — AGENTS.md has existing non-Smriti content"
            )
            next_steps.append(
                "Install Codex skill pack manually (will overwrite AGENTS.md):\n"
                "    smriti skills install codex --force\n"
                "    git add AGENTS.md && git commit -m \"Add Smriti skill pack for Codex\""
            )
    if codex_safe:
        codex_result = install_skill("codex", destination=agents_path)
        if codex_result.action == "created":
            results.append(f"Skill pack installed for Codex → {codex_result.destination}")
            next_steps.append(
                "Commit AGENTS.md so Codex can see it:\n"
                "    git add AGENTS.md && git commit -m \"Add Smriti skill pack for Codex\""
            )
        elif codex_result.action == "overwritten":
            results.append(f"Skill pack upgraded for Codex → {codex_result.destination}")
            next_steps.append(
                "Commit the updated AGENTS.md:\n"
                "    git add AGENTS.md && git commit"
            )
        elif codex_result.action == "skipped":
            results.append(f"Skill pack for Codex is current (v{codex_result.version})")

    # 5. Generate SessionStart hook.
    settings_path = Path(".claude/settings.json")
    hook_command = _build_session_start_hook_command(client.base_url)
    hook_entry = {
        "type": "command",
        "command": hook_command,
    }
    target_hooks = {
        "SessionStart": [
            {"matcher": "startup", "hooks": [hook_entry]},
            {"matcher": "compact", "hooks": [hook_entry]},
            {"matcher": "resume", "hooks": [hook_entry]},
        ]
    }

    if settings_path.exists():
        try:
            existing = _json.loads(settings_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            existing = {}
    else:
        existing = {}

    existing.setdefault("hooks", {})
    existing_session_start = existing["hooks"].get("SessionStart")
    if not isinstance(existing_session_start, list):
        existing_session_start = []

    non_smriti_hooks = [
        entry for entry in existing_session_start
        if not _is_smriti_session_start_entry(entry)
    ]
    merged_session_start = non_smriti_hooks + target_hooks["SessionStart"]

    if existing_session_start == merged_session_start:
        results.append("SessionStart hook already configured → .claude/settings.json")
    else:
        existing["hooks"]["SessionStart"] = merged_session_start
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(
            _json.dumps(existing, indent=2) + "\n", encoding="utf-8"
        )
        action = "updated" if existing_session_start else "configured"
        results.append(f"SessionStart hook {action} → .claude/settings.json")

    # 6. MCP config reminder.
    mcp_config = {
        "mcpServers": {
            "smriti": {
                "command": _smriti_mcp_executable(),
                "env": {"SMRITI_API_URL": client.base_url},
            }
        }
    }
    next_steps.append(
        "Configure MCP in your host (if using Claude Code / Cursor / Windsurf):\n"
        f"    {_json.dumps(mcp_config)}"
    )
    next_steps.append(
        "Verify activation:\n"
        "    smriti doctor\n"
        "    smriti state --compact"
    )

    # 7. Output.
    if args.json:
        _print_json({
            "space": space_name,
            "results": results,
            "next_steps": next_steps,
        })
        return

    print()
    for r in results:
        print(f"  ✓ {r}")
    if next_steps:
        print()
        print("  Next steps:")
        for i, step in enumerate(next_steps, 1):
            print(f"    {i}. {step}")
    print()


# ── attach subcommand handler ───────────────────────────────────────────────


def cmd_attach(client: SmritiClient, args: argparse.Namespace) -> None:
    """Attach this repo to a Smriti space — a durable `.smriti.json` binding.

    With no <space>: print the repo's current attachment.
    With <space>: resolve or create the space, write `.smriti.json` at the
    repo root, and set the space's project_root. Afterward, commands in this
    repo resolve the space automatically — no <space> argument needed.
    """
    # No space → show the current attachment and stop.
    if not args.space:
        record = attachment.read_attachment()
        path = attachment.find_attachment_file()
        if record is None:
            if args.json:
                _print_json({"attached": False})
            else:
                print("This directory is not attached to a Smriti space.")
                print("Attach it once:  smriti attach <space>")
            return
        if args.json:
            _print_json({
                "attached": True,
                "space": record.get("space"),
                "space_id": record.get("space_id"),
                "attachment": str(path) if path else None,
            })
            return
        print(f'Attached to Smriti space "{record.get("space")}".')
        if record.get("space_id"):
            print(f"  space id:   {record['space_id']}")
        print(f"  attachment: {path}")
        return

    # Verify backend reachability.
    try:
        client.list_spaces()
    except SmritiError:
        _fail(
            f"error: Cannot reach Smriti backend at {client.base_url}.\n"
            "Start the backend with `make dev-local` for solo/local mode, "
            "or `make dev-postgres` for Postgres/shared-team mode."
        )
        return

    # Resolve the space, or create it if it does not exist yet.
    target_name = args.space
    try:
        space = client.resolve_space(target_name)
        created = False
    except SmritiError:
        space = client.create_space(
            name=target_name, description=args.description or ""
        )
        created = True

    repo_dir = _git_output("rev-parse", "--show-toplevel") or os.getcwd()

    # Set the backend's project_root hint (best-effort). The `.smriti.json`
    # attachment is the source of truth for repo → space resolution.
    try:
        client.set_project_root(space["id"], repo_dir)
    except SmritiError:
        pass

    path = attachment.write_attachment(repo_dir, space["name"], space["id"])

    if args.json:
        _print_json({
            "space": space["name"],
            "space_id": space["id"],
            "attachment": str(path),
            "project_root": repo_dir,
            "created": created,
        })
        return

    verb = "created and attached" if created else "attached"
    print()
    print(f'  ✓ Repo {verb} to Smriti space "{space["name"]}"')
    print(f"    attachment:   {path}")
    print(f"    project root: {repo_dir}")
    print()
    print("  Commands in this repo now resolve the space automatically —")
    print("  `smriti state`, `smriti current`, `smriti claim create …` need no <space>.")
    print()


# ── quickstart subcommand handler ───────────────────────────────────────────


def _render_quickstart(args: argparse.Namespace, payload: dict) -> None:
    """Emit a quickstart result — JSON when --json, otherwise human-readable."""
    if args.json:
        _print_json(payload)
        return

    space = payload["space"]
    action = payload["action"]
    print()

    if action == "removed":
        print(f'  ✓ Removed the demo space "{space}".')
        print()
        return

    if action == "nothing-to-remove":
        print(f'  No demo space to remove — "{space}" does not exist.')
        print()
        return

    if action == "exists":
        print(f'  The demo space "{space}" is already seeded.')
        print()
        print(f"    smriti current {space}      explore it")
        print("    smriti quickstart --reset     rebuild it from scratch")
        print("    smriti quickstart --remove    delete it")
        print()
        return

    # action == "seeded"
    claims = payload["claims"]
    active = sum(1 for c in claims if c.get("status") != "done")
    n_checkpoints = len(payload["checkpoints"])
    print(f'  ✓ Seeded the demo space "{space}".')
    print(
        f"    {n_checkpoints} checkpoints · 2 agents · "
        f"1 branch explored and dropped · "
        f"{len(claims)} work claims ({active} still active)"
    )
    print()
    print('  This is one small, finished feature — "add rate limiting to the')
    print('  API" — captured the way Smriti captures reasoning: the decisions,')
    print("  the assumptions under them, a branch that was tried and dropped,")
    print("  and a hand-off between two agents. Smriti's value is this")
    print("  accumulated state — quickstart just gives you some on day one.")
    print()
    print("  Walk through it — about three minutes:")
    print()
    for i, step in enumerate(payload["guide"], 1):
        print(f"    {i}. {step['command']}")
        print(f"       {step['note']}")
        print()
    print("  Then open the dashboard:  http://localhost:5173")
    print()
    print("  Done exploring?  smriti quickstart --remove")
    print()


def cmd_quickstart(client: SmritiClient, args: argparse.Namespace) -> None:
    """Seed a curated demo space so a new user sees what Smriti is for.

    The empty-room problem: a fresh install opens to an empty space, and
    Smriti's value only shows once reasoning has accumulated. `quickstart`
    seeds one small, finished, realistic project — built by two agents, with
    a branch that was explored and dropped — and prints a short walkthrough.

    Default: seed `smriti-demo`. --remove deletes it; --reset removes then
    re-seeds. Idempotent — re-running without flags when the demo already
    exists just reprints how to explore or rebuild it.
    """
    from . import quickstart as qs

    # Backend reachability — same failure guidance as `smriti init`.
    try:
        client.list_spaces()
    except SmritiError:
        _fail(
            f"error: Cannot reach Smriti backend at {client.base_url}.\n"
            "Start the backend with `make dev-local` for solo/local mode, "
            "or `make dev-postgres` for Postgres/shared-team mode."
        )
        return

    # Removal path — both --remove and --reset clear an existing demo space.
    if args.remove or args.reset:
        existing = qs.find_demo_space(client)
        if existing is not None and qs.is_demo_space(existing):
            if not _confirm(
                f'Delete the demo space "{qs.DEMO_SPACE_NAME}" and all '
                f"its checkpoints?",
                args.yes,
            ):
                _fail("Cancelled.", code=0)
        result = qs.remove_demo_space(client)
        if not result["removed"] and result.get("reason") == "not-a-demo-space":
            _fail(
                f'error: A space named "{qs.DEMO_SPACE_NAME}" exists but was '
                f"not created by quickstart — it lacks the demo marker.\n"
                f"Refusing to delete it. To remove it yourself, run:\n"
                f"    smriti space delete {qs.DEMO_SPACE_NAME}"
            )
            return
        if args.remove:
            action = "removed" if result["removed"] else "nothing-to-remove"
            _render_quickstart(args, {"action": action, "space": qs.DEMO_SPACE_NAME})
            return
        # --reset: fall through and re-seed.

    # Seeding path.
    if qs.find_demo_space(client) is not None:
        _render_quickstart(args, {"action": "exists", "space": qs.DEMO_SPACE_NAME})
        return

    seed = qs.seed_demo_space(client)
    _render_quickstart(
        args,
        {
            "action": "seeded",
            "space": qs.DEMO_SPACE_NAME,
            "space_id": seed["space_id"],
            "checkpoints": seed["checkpoints"],
            "claims": seed["claims"],
            "guide": qs.build_guide(seed),
        },
    )


# ── branch subcommand handlers ──────────────────────────────────────────────


def cmd_branch_close(client: SmritiClient, args: argparse.Namespace) -> None:
    """Set the disposition of a branch (integrated, abandoned, or active)."""
    space = _resolve_space(client, args)
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
    space = _resolve_space(client, args)
    head = client.get_head(space["id"])
    base_commit_id = head.get("commit_id")  # auto-bind to current HEAD

    claim = client.create_claim(
        space_id=space["id"],
        agent=args.agent,
        scope=args.scope,
        branch_name=args.branch or "main",
        base_commit_id=base_commit_id,
        task_id=getattr(args, "task_id", None),
        worktree_id=getattr(args, "worktree", None),
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
    space = _resolve_space(client, args)
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


# ── worktree subcommand handlers ────────────────────────────────────────────


def _short_id(value: str) -> str:
    return f"{value[:8]}…" if len(value) > 8 else value


def _display_path(path: str) -> str:
    home = os.path.expanduser("~")
    if path == home:
        return "~"
    if path.startswith(home + os.sep):
        return "~" + path[len(home):]
    return path


def _print_worktree_table(worktrees: list[dict]) -> None:
    headers = ["ID", "AGENT", "BRANCH", "DIRTY", "AHEAD", "PATH"]
    rows = [
        [
            _short_id(str(w.get("id", ""))),
            str(w.get("agent", "")),
            str(w.get("branch_name", "")),
            format_worktree_dirty(w),
            format_worktree_ahead(w),
            _display_path(str(w.get("path", ""))),
        ]
        for w in worktrees
    ]
    widths = [
        max(len(headers[i]), *(len(row[i]) for row in rows))
        for i in range(len(headers))
    ]
    print("  ".join(headers[i].ljust(widths[i]) for i in range(len(headers))))
    for row in rows:
        print("  ".join(row[i].ljust(widths[i]) for i in range(len(row))))


def cmd_worktree_open(client: SmritiClient, args: argparse.Namespace) -> None:
    """Create a git worktree for an agent and print its path."""
    space = _resolve_space(client, args)
    worktree = client.create_worktree(
        space_id=space["id"],
        agent=args.agent,
        branch_name=args.branch,
        base_commit_sha=args.base_commit,
        base_path=args.base_path,
    )
    if args.json:
        _print_json(worktree)
    else:
        print(worktree["path"])


def cmd_worktree_list(client: SmritiClient, args: argparse.Namespace) -> None:
    """List worktrees for a space."""
    space = _resolve_space(client, args)
    worktrees = client.list_worktrees(space["id"], include_closed=args.include_closed)
    if args.json:
        _print_json(worktrees)
        return
    if not worktrees:
        print("No worktrees." if args.include_closed else "No active worktrees.")
        return
    _print_worktree_table(worktrees)


def cmd_worktree_show(client: SmritiClient, args: argparse.Namespace) -> None:
    """Show one worktree."""
    worktree = client.get_worktree(args.worktree_id)
    if args.json:
        _print_json(worktree)
        return
    print(f"id: {worktree['id']}")
    print(f"status: {worktree['status']}")
    print(f"agent: {worktree['agent']}")
    print(f"branch: {worktree['branch_name']}")
    print(f"base_commit: {worktree.get('base_commit_sha') or ''}")
    print(f"path: {worktree['path']}")
    print(f"created_at: {worktree['created_at']}")
    if worktree.get("closed_at"):
        print(f"closed_at: {worktree['closed_at']}")


def cmd_worktree_close(client: SmritiClient, args: argparse.Namespace) -> None:
    """Close/remove a git worktree."""
    worktree = client.close_worktree(args.worktree_id, force=args.force)
    if args.json:
        _print_json(worktree)
    else:
        print(f"Closed worktree `{worktree['id']}` at {worktree['path']}.")


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


def cmd_metrics(client: SmritiClient, args: argparse.Namespace) -> None:
    """Print project-level KPIs for a space."""
    space = _resolve_space(client, args)
    data = client.get_space_metrics(space["id"])
    if args.json:
        _print_json(data)
    else:
        print(format_metrics(data), end="")


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

    # init — one-step agent onboarding
    init_parser = subparsers.add_parser(
        "init",
        help="One-step agent onboarding: create space, install skill packs, configure hook",
    )
    init_parser.add_argument("space", help="Space name for this project")
    init_parser.add_argument("--description", help="Space description", default="")
    init_parser.add_argument("--json", action="store_true")
    init_parser.set_defaults(func=cmd_init)

    # attach — bind this repo to a Smriti space (durable .smriti.json)
    attach_parser = subparsers.add_parser(
        "attach",
        help="Attach this repo to a Smriti space so commands resolve it automatically",
    )
    attach_parser.add_argument(
        "space",
        nargs="?",
        help="Space to attach to (omit to show the repo's current attachment)",
    )
    attach_parser.add_argument(
        "--description", default="", help="Description, used only if the space is created"
    )
    attach_parser.add_argument("--json", action="store_true")
    attach_parser.set_defaults(func=cmd_attach)

    # doctor — local/runtime diagnostics
    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Diagnose backend reachability and runtime/code freshness",
    )
    doctor_parser.add_argument("--json", action="store_true", help="Output structured JSON")
    doctor_parser.set_defaults(func=cmd_doctor)

    # quickstart — seed a curated demo space so the product clicks fast
    quickstart_parser = subparsers.add_parser(
        "quickstart",
        help="Seed a curated demo space (smriti-demo) and print a guided walkthrough",
    )
    quickstart_mode = quickstart_parser.add_mutually_exclusive_group()
    quickstart_mode.add_argument(
        "--remove",
        action="store_true",
        help="Delete the demo space instead of seeding it",
    )
    quickstart_mode.add_argument(
        "--reset",
        action="store_true",
        help="Delete the demo space if present, then seed a fresh one",
    )
    quickstart_parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt when removing the demo space",
    )
    quickstart_parser.add_argument("--json", action="store_true")
    quickstart_parser.set_defaults(func=cmd_quickstart)

    # space
    space_parser = subparsers.add_parser("space", help="Manage Smriti spaces (projects)")
    space_sub = space_parser.add_subparsers(dest="subcommand", required=True)

    sp_list = space_sub.add_parser("list", help="List all spaces")
    sp_list.add_argument("--json", action="store_true", help="Output structured JSON")
    sp_list.set_defaults(func=cmd_space_list)

    sp_create = space_sub.add_parser("create", help="Create a new space")
    sp_create.add_argument("name", help="Space name")
    sp_create.add_argument("--description", help="Optional description", default="")
    root_group = sp_create.add_mutually_exclusive_group()
    root_group.add_argument(
        "--project-root",
        help="Canonical project checkout path for worktree operations "
        "(default: current working directory)",
    )
    root_group.add_argument(
        "--no-project-root",
        action="store_true",
        help="Leave the space without a canonical project_root",
    )
    sp_create.add_argument("--json", action="store_true", help="Output structured JSON")
    sp_create.set_defaults(func=cmd_space_create)

    sp_set_project_root = space_sub.add_parser(
        "set-project-root",
        help="Set a space's canonical project_root",
    )
    sp_set_project_root.add_argument("space", help="Space name or UUID")
    sp_set_project_root.add_argument(
        "path",
        nargs="?",
        help="Project checkout path. Use '.' for the current directory.",
    )
    sp_set_project_root.add_argument(
        "--here",
        action="store_true",
        help="Set project_root to the current directory.",
    )
    sp_set_project_root.add_argument(
        "--json", action="store_true", help="Output structured JSON"
    )
    sp_set_project_root.set_defaults(func=cmd_space_set_project_root)

    sp_delete = space_sub.add_parser(
        "delete",
        help="Delete a space and all its checkpoints, sessions, and turns",
    )
    sp_delete.add_argument("space", help="Space name or UUID")
    sp_delete.add_argument(
        "-y", "--yes", action="store_true", help="Skip confirmation prompt"
    )
    sp_delete.add_argument(
        "--force",
        action="store_true",
        help="Required to delete a non-empty or attached space (irreversible)",
    )
    sp_delete.add_argument("--json", action="store_true", help="Output structured JSON")
    sp_delete.set_defaults(func=cmd_space_delete)

    # state
    state_parser = subparsers.add_parser(
        "state",
        help="Print a continuation-oriented brief of the current project state",
    )
    state_parser.add_argument("space", nargs="?", help="Space name or UUID (optional — defaults to the attached space)")
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
    state_parser.add_argument(
        "--compact",
        action="store_true",
        help="Omit artifact content, show labels only. Saves tokens for "
             "session-start injection. Full content recoverable via "
             "smriti checkpoint show <id> --full-artifacts.",
    )
    state_parser.add_argument(
        "--stats",
        action="store_true",
        help="Show compact-mode savings (artifact chars saved, percent reduction). "
             "Only meaningful with --compact.",
    )
    state_parser.add_argument(
        "--since",
        help="Checkpoint ID to check freshness against. Shows whether HEAD "
             "has moved since that checkpoint and lists new checkpoints.",
    )
    state_parser.add_argument("--json", action="store_true", help="Output structured JSON")
    state_parser.set_defaults(func=cmd_state)

    # current — compact founder/agent current-state surface
    current_parser = subparsers.add_parser(
        "current",
        help="Print the compact Project Current State surface for a space",
    )
    current_parser.add_argument("space", nargs="?", help="Space name or UUID (optional — defaults to the attached space)")
    current_parser.add_argument("--json", action="store_true", help="Output structured JSON")
    current_parser.set_defaults(func=cmd_current)

    # checkpoint
    cp_parser = subparsers.add_parser("checkpoint", help="Manage checkpoints")
    cp_sub = cp_parser.add_subparsers(dest="subcommand", required=True)

    cp_create = cp_sub.add_parser(
        "create",
        help="Create a checkpoint from JSON on stdin or --from-json <path>",
    )
    cp_create.add_argument("space", nargs="?", help="Space name or UUID (optional — defaults to the attached space)")
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
    cp_list.add_argument("space", nargs="?", help="Space name or UUID (optional — defaults to the attached space)")
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

    cp_note = cp_sub.add_parser(
        "note",
        help="Add a note to a checkpoint (additive, does not modify checkpoint fields)",
    )
    cp_note.add_argument("checkpoint_id", help="Checkpoint UUID to annotate")
    cp_note.add_argument("--text", required=True, help="Note text (max 2000 chars)")
    cp_note.add_argument("--author", default="founder", help="Author name (default: founder)")
    cp_note.add_argument(
        "--kind", default="note",
        choices=["note", "milestone", "noise"],
        help="Note kind (default: note)",
    )
    cp_note.add_argument("--json", action="store_true")
    cp_note.set_defaults(func=cmd_checkpoint_note)

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
    br_close.add_argument("space", nargs="?", help="Space name or UUID (optional — defaults to the attached space)")
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
    cl_create.add_argument("space", nargs="?", help="Space name or UUID (optional — defaults to the attached space)")
    cl_create.add_argument("--agent", required=True, help="Your agent identifier (e.g. claude-code)")
    cl_create.add_argument("--scope", required=True, help="One sentence describing what you are about to work on")
    cl_create.add_argument("--branch", help="Branch name (default: main)", default=None)
    cl_create.add_argument(
        "--intent-type", dest="intent_type", default="implement",
        choices=["implement", "review", "investigate", "docs", "test"],
        help="Type of work (default: implement)",
    )
    cl_create.add_argument("--task-id", dest="task_id", default=None, help="Optional structured task ID this claim covers")
    cl_create.add_argument("--worktree", dest="worktree", default=None, help="Optional worktree UUID to bind to this claim")
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
    cl_list.add_argument("space", nargs="?", help="Space name or UUID (optional — defaults to the attached space)")
    cl_list.add_argument("--all", action="store_true", help="Include expired/done/abandoned claims")
    cl_list.add_argument("--json", action="store_true")
    cl_list.set_defaults(func=cmd_claim_list)

    # worktree — filesystem/index isolation for agent work
    worktree_parser = subparsers.add_parser(
        "worktree",
        help="Manage git worktrees for isolated agent working directories",
    )
    worktree_sub = worktree_parser.add_subparsers(dest="subcommand", required=True)

    wt_open = worktree_sub.add_parser("open", help="Create a worktree for an agent")
    wt_open.add_argument("space", nargs="?", help="Space name or UUID (optional — defaults to the attached space)")
    wt_open.add_argument("--agent", required=True, help="Agent identifier (e.g. claude-code)")
    wt_open.add_argument("--branch", help="Branch name for the new worktree", default=None)
    wt_open.add_argument("--base-commit", dest="base_commit", help="Git SHA to base the worktree on", default=None)
    wt_open.add_argument("--base-path", dest="base_path", help="Absolute target path for the new worktree", default=None)
    wt_open.add_argument("--json", action="store_true")
    wt_open.set_defaults(func=cmd_worktree_open)

    wt_list = worktree_sub.add_parser(
        "list",
        help="List worktrees for a space",
        description=(
            "List worktrees for a space. DIRTY shows dirty file count when "
            "available. AHEAD shows +N when ahead of origin/main, -N when "
            "behind, 0 when even, or — when unknown."
        ),
    )
    wt_list.add_argument("space", nargs="?", help="Space name or UUID (optional — defaults to the attached space)")
    wt_list.add_argument("--include-closed", action="store_true", help="Include closed worktrees")
    wt_list.add_argument("--json", action="store_true")
    wt_list.set_defaults(func=cmd_worktree_list)

    wt_show = worktree_sub.add_parser("show", help="Show one worktree")
    wt_show.add_argument("worktree_id", help="Worktree UUID")
    wt_show.add_argument("--json", action="store_true")
    wt_show.set_defaults(func=cmd_worktree_show)

    wt_close = worktree_sub.add_parser("close", help="Close/remove a worktree")
    wt_close.add_argument("worktree_id", help="Worktree UUID")
    wt_close.add_argument("--force", action="store_true", help="Force removal even if dirty")
    wt_close.add_argument("--json", action="store_true")
    wt_close.set_defaults(func=cmd_worktree_close)

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

    # ── metrics ────────────────────────────────────────────────────────
    metrics_parser = subparsers.add_parser("metrics", help="Project-level KPIs for a space")
    metrics_parser.add_argument("space", nargs="?", help="Space name or UUID (optional — defaults to the attached space)")
    metrics_parser.add_argument("--json", action="store_true", help="Output raw JSON")
    metrics_parser.set_defaults(func=cmd_metrics)

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
