"""Smriti agent skill pack — the agent-onboarding surface.

The skill pack teaches coding agents (Claude Code, Codex) when and
why to use Smriti's tools — when to checkpoint, when NOT to checkpoint,
when to fork, how to detect drift, and the explicit anti-patterns to
reject. It is installed into an agent host's project directory as a
single versioned markdown file so the instructions live in the
agent's system context rather than in documentation the agent never
reads.

Public surface:
    render(target_key) -> str                 # render template for a target
    install(target_key, ...) -> InstallResult # write rendered template to disk
    get_version(content=None) -> str           # parse frontmatter version
    list_targets() -> list[SkillTarget]       # enumerate known targets
    get_target(target_key) -> SkillTarget     # resolve a target config

Layout:
    skill_pack/
        __init__.py      — re-exports the small public surface
        template.md      — single source of truth (versioned frontmatter)
        renderer.py      — pure-function render + install logic
        targets.py       — target configs (display name, destination)
"""
from .renderer import InstallResult, get_version, install, load_template, render
from .targets import SkillTarget, get_target, list_targets

__all__ = [
    "InstallResult",
    "SkillTarget",
    "get_target",
    "get_version",
    "install",
    "list_targets",
    "load_template",
    "render",
]
