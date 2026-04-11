"""Skill pack renderer + installer.

Pure functions — no LLM calls, no network, no global state. The
renderer reads the single source-of-truth `template.md`, substitutes
a small set of placeholders based on the target's primary mode, and
returns the rendered markdown as a string. The installer writes the
result to the target's default destination (or an override) with
version-aware refusal to overwrite.

Template syntax:

    {{display_name}}
        → replaced with the target's display_name ("Claude Code" or "Codex")

    {{primary_mode}}
        → replaced with "mcp" or "cli"

    {{mcp:some text}}{{cli:other text}}
        → paired blocks. For target primary_mode="mcp" the whole pair
          becomes "some text"; for primary_mode="cli" it becomes
          "other text". Either block may be empty. Both blocks must
          appear together — an unmatched block raises ValueError at
          render time so typos in the template fail loudly in tests.

The version is stored in frontmatter as:

    ---
    smriti_skill_pack_version: 1.0
    ...
    ---

The installer reads the existing destination's frontmatter (if any),
compares versions as strings (lexicographic — "1.0" < "1.1" < "1.10"
works for the foreseeable skill pack version series), and refuses to
overwrite a destination whose version is >= the template's version
unless `force=True` is passed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from .targets import SkillTarget, get_target


_TEMPLATE_PATH = Path(__file__).parent / "template.md"

_VERSION_RE = re.compile(
    r"^smriti_skill_pack_version:\s*([^\n]+)$",
    re.MULTILINE,
)

# Matches a paired {{mcp:...}}{{cli:...}} block. The `?` suffix on the
# inner `.` quantifiers makes them non-greedy so multiple pairs on the
# same line (or line-wrapped pairs) do not collapse into one giant
# match. Empty bodies are allowed.
_PAIRED_BLOCK_RE = re.compile(
    r"\{\{mcp:(.*?)\}\}\{\{cli:(.*?)\}\}",
    re.DOTALL,
)

# Matches any leftover unpaired block — if this matches after
# _PAIRED_BLOCK_RE has been applied, the template has a typo.
_UNPAIRED_BLOCK_RE = re.compile(
    r"\{\{(?:mcp|cli):[^}]*\}\}",
    re.DOTALL,
)


Action = Literal["created", "overwritten", "dry_run", "skipped"]


@dataclass
class InstallResult:
    """Result of a skill pack install attempt.

    - action: what happened. "skipped" means the destination already
      had a same-or-newer version and `force` was not set; nothing was
      written.
    - previous_version: the version read from the destination before
      the install attempt, or None if the destination did not exist
      or had no version frontmatter.
    - content: the rendered content that was (or would have been)
      written. Useful for `--dry-run` and for the MCP tool which
      returns the content without writing.
    """

    target: SkillTarget
    destination: Path
    action: Action
    version: str
    previous_version: Optional[str]
    content: str


def load_template() -> str:
    """Read the raw template.md from the installed package."""
    return _TEMPLATE_PATH.read_text(encoding="utf-8")


def get_version(content: Optional[str] = None) -> str:
    """Return the `smriti_skill_pack_version` value from the template
    frontmatter. Raises ValueError if the frontmatter is missing so
    missing-version bugs fail loudly during development rather than
    installing an unversioned skill pack.
    """
    text = content if content is not None else load_template()
    m = _VERSION_RE.search(text)
    if not m:
        raise ValueError(
            "Skill pack template is missing `smriti_skill_pack_version` "
            "frontmatter. Every template.md must start with a YAML "
            "frontmatter block that pins the version."
        )
    return m.group(1).strip()


def render(target_key: str) -> str:
    """Render the template for a specific target.

    The same template.md renders for every target; placeholders and
    `{{mcp:...}}{{cli:...}}` blocks control the primary-mode-specific
    variations. The content (workflow heuristics, anti-patterns,
    when-not-to-checkpoint rules) is identical across targets — only
    the tool notation and display name differ.
    """
    target = get_target(target_key)
    template = load_template()
    return _substitute_placeholders(template, target)


def _substitute_placeholders(template: str, target: SkillTarget) -> str:
    """Apply the template substitutions for a target. Pure function.

    Steps:
      1. Replace every {{mcp:X}}{{cli:Y}} paired block with X or Y
         depending on target.primary_mode.
      2. Replace {{display_name}} → target.display_name.
      3. Replace {{primary_mode}} → target.primary_mode.
      4. Assert no unmatched paired blocks remain — if any do, the
         template has a typo and the renderer fails loudly with the
         location context.
    """
    def pick(match: re.Match[str]) -> str:
        mcp_body, cli_body = match.group(1), match.group(2)
        return mcp_body if target.primary_mode == "mcp" else cli_body

    out = _PAIRED_BLOCK_RE.sub(pick, template)
    out = out.replace("{{display_name}}", target.display_name)
    out = out.replace("{{primary_mode}}", target.primary_mode)

    leftover = _UNPAIRED_BLOCK_RE.search(out)
    if leftover:
        # Provide a snippet of context so the error is actionable.
        start = max(0, leftover.start() - 30)
        end = min(len(out), leftover.end() + 30)
        raise ValueError(
            f"Skill pack template contains an unmatched "
            f"{{mcp:...}}/{{cli:...}} block. Matched fragment: "
            f"{leftover.group(0)!r}. Context: ...{out[start:end]!r}..."
        )

    return out


def install(
    target_key: str,
    destination: Optional[Path] = None,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> InstallResult:
    """Install the rendered skill pack for a target.

    Args:
        target_key: "claude-code" or "codex".
        destination: Override the target's default destination path.
            When None, uses `target.default_destination` relative to
            the current working directory.
        force: Overwrite an existing same-or-newer version. Default
            False: refuse and return `action="skipped"`.
        dry_run: Render the content and return it, but do not write
            to disk. Default False.

    Returns:
        InstallResult describing what happened.
    """
    target = get_target(target_key)
    dest = Path(destination) if destination is not None else target.default_destination
    content = render(target_key)
    current_version = get_version(content)
    previous_version: Optional[str] = None

    if dest.exists():
        try:
            existing = dest.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            existing = ""
        m = _VERSION_RE.search(existing)
        if m:
            previous_version = m.group(1).strip()

        if (
            previous_version is not None
            and not force
            and previous_version >= current_version
        ):
            return InstallResult(
                target=target,
                destination=dest,
                action="skipped",
                version=current_version,
                previous_version=previous_version,
                content=content,
            )

    if dry_run:
        return InstallResult(
            target=target,
            destination=dest,
            action="dry_run",
            version=current_version,
            previous_version=previous_version,
            content=content,
        )

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")

    return InstallResult(
        target=target,
        destination=dest,
        action="overwritten" if previous_version else "created",
        version=current_version,
        previous_version=previous_version,
        content=content,
    )
