"""Skill pack target configurations.

A "target" is the agent host the skill pack is being installed into.
Two targets ship in v1.0:

- claude-code: installs to `./.claude/skills/smriti/SKILL.md`. Claude
  Code reads skills out of `.claude/skills/<name>/SKILL.md` as
  project-level instructions. Primary tool notation is MCP
  (`smriti_state(space="x")`) because Claude Code speaks MCP natively.
- codex: installs to `./AGENTS.md`. Codex reads `AGENTS.md` at the
  project root as its primary instruction file. Primary tool notation
  is CLI (`smriti state x`) because the Codex CLI runs commands in a
  shell loop.

Both targets render from the SAME template source — only the primary
tool notation and display name vary. Workflow heuristics, anti-patterns,
and when-not-to-checkpoint rules are identical for both targets by
design.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


PrimaryMode = Literal["mcp", "cli"]


@dataclass(frozen=True)
class SkillTarget:
    """Configuration for one agent skill pack target."""

    key: str
    display_name: str
    default_destination: Path
    primary_mode: PrimaryMode
    # One-line summary used by `smriti skills list`.
    description: str


TARGETS: dict[str, SkillTarget] = {
    "claude-code": SkillTarget(
        key="claude-code",
        display_name="Claude Code",
        default_destination=Path(".claude/skills/smriti/SKILL.md"),
        primary_mode="mcp",
        description="Claude Code (MCP-native host; installs to .claude/skills/smriti/SKILL.md)",
    ),
    "codex": SkillTarget(
        key="codex",
        display_name="Codex",
        default_destination=Path("AGENTS.md"),
        primary_mode="cli",
        description="Codex (shell-based host; installs to AGENTS.md)",
    ),
}


def list_targets() -> list[SkillTarget]:
    """Return all known skill pack targets in a deterministic order."""
    return [TARGETS[k] for k in sorted(TARGETS.keys())]


def get_target(target_key: str) -> SkillTarget:
    """Resolve a target by key. Raises ValueError for unknown keys.

    The error message lists the known targets so CLI users and agents
    get actionable feedback without having to consult the docs.
    """
    if target_key not in TARGETS:
        known = ", ".join(sorted(TARGETS.keys()))
        raise ValueError(
            f"Unknown skill pack target: '{target_key}'. Known targets: {known}"
        )
    return TARGETS[target_key]
