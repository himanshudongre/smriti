"""Tests for the skill pack renderer + installer.

Covers:
- Template loads and has a parseable version frontmatter
- render() produces distinct output per target (MCP vs CLI notation)
- render() substitutes {{display_name}} and {{primary_mode}}
- render() raises on unknown targets
- render() raises on unmatched paired blocks (template typo guard)
- install() creates the destination file with the rendered content
- install() creates parent directories that don't exist
- install() --dry-run does NOT write to disk
- install() refuses to overwrite a same-version destination without --force
- install() --force overwrites a same-version destination
- install() writes to an explicit --destination override
- list_targets() returns the known targets deterministically
"""
from __future__ import annotations

from pathlib import Path

import pytest

from smriti_cli.skill_pack import (
    InstallResult,
    get_target,
    get_version,
    install,
    list_targets,
    load_template,
    render,
)
from smriti_cli.skill_pack.renderer import _substitute_placeholders
from smriti_cli.skill_pack.targets import SkillTarget


# ── Template loading + version ──────────────────────────────────────────────


def test_load_template_nonempty():
    text = load_template()
    assert text.strip() != ""
    assert "smriti_skill_pack_version" in text


def test_get_version_parses_frontmatter():
    version = get_version()
    assert version == "1.4"


def test_get_version_raises_when_frontmatter_missing():
    with pytest.raises(ValueError, match="smriti_skill_pack_version"):
        get_version(content="no frontmatter here\njust body text")


# ── Render ───────────────────────────────────────────────────────────────────


def test_render_claude_code_uses_mcp_notation():
    out = render("claude-code")
    assert "Claude Code" in out
    # MCP tool-call form should be present.
    assert "smriti_state(" in out
    assert "smriti_create_checkpoint(" in out
    # CLI shell form should NOT appear — the claude-code variant elides it.
    assert "smriti checkpoint create" not in out
    assert "smriti checkpoint review" not in out


def test_render_codex_uses_cli_notation():
    out = render("codex")
    assert "Codex" in out
    # CLI shell form should be present.
    assert "smriti state " in out
    assert "smriti checkpoint create" in out
    assert "smriti checkpoint review" in out
    # MCP tool-call form should NOT appear — the codex variant elides it.
    assert "smriti_state(space" not in out
    assert "smriti_create_checkpoint(" not in out


def test_render_substitutes_display_name():
    assert "Claude Code" in render("claude-code")
    assert "Codex" in render("codex")


def test_render_substitutes_primary_mode():
    claude_out = render("claude-code")
    codex_out = render("codex")
    assert "mcp" in claude_out
    assert "cli" in codex_out


def test_render_unknown_target_raises():
    with pytest.raises(ValueError, match="Unknown skill pack target"):
        render("not-a-real-target")


# ── Content integrity (shared between both targets) ─────────────────────────


# These phrases define the load-bearing parts of the skill pack's
# anti-pattern teaching. If a future template edit drops any of them,
# these tests fail and we catch the regression before shipping. The
# product contract is: both targets must always teach when NOT to
# checkpoint, with all the rules intact.
_REQUIRED_PHRASES = [
    # Section 5.x — When NOT to checkpoint
    "after every small step",
    "end of session as a blob",
    "backup system",
    "nothing crisp to say",
    "inconsistent state",
    "restate",
    # Section 5.1 — the signal test (3 questions)
    "The signal test",
    "name the inflection point",
    # Section 5.2 — frequency target
    "2 to 4 checkpoints",
    "20 checkpoints is producing noise",
    # Section 3 — the reflex
    "Reading current state from Smriti",
    # Section 11 — anti-patterns
    "HANDOFF.md",
    "author_agent",
    # Section 10 — drift detection
    "divergence",
    "scope divergence",
    # Section 3.1 — cross-agent continuation
    "cross-agent continuation",
    "written by a different agent",
    "silently override",
    # Section 3.2 — repo reconciliation
    "repo reconciliation",
    "git log",
    "already done in the repo",
    # Section 3.3 — clean start
    "clean start",
    "git fetch origin",
    "local residue",
    "default to freshness",
    # Section 3.4 — clean finish
    "clean finish",
    "branch disposition",
    "push your branch",
    # Section 3.5 — backend reachability
    "backend reachability",
    "do not attempt to start",
    # Section 14 — two-sentence summary
    "session start",
]


@pytest.mark.parametrize("target_key", ["claude-code", "codex"])
def test_render_contains_all_critical_content(target_key: str):
    """Every target must teach all anti-patterns and heuristics.

    Divergent targets with missing sections would erode the skill
    pack's value — the rules are identical across hosts and this
    test enforces that invariant.
    """
    out = render(target_key)
    missing = [p for p in _REQUIRED_PHRASES if p.lower() not in out.lower()]
    assert not missing, (
        f"Rendered skill pack for {target_key!r} is missing required "
        f"phrases: {missing}. This usually means a template edit "
        f"dropped a critical section."
    )


def test_render_targets_share_anti_pattern_section():
    """Both targets should include the same When-NOT-to-checkpoint
    bullet structure. String-match the most distinctive phrases that
    should never go away."""
    claude = render("claude-code").lower()
    codex = render("codex").lower()
    for phrase in [
        "when not to checkpoint",
        "checkpoint is not a save button",
        "do not checkpoint after every small step",
        "do not checkpoint at end of session as a blob",
    ]:
        assert phrase in claude, f"missing from claude-code: {phrase}"
        assert phrase in codex, f"missing from codex: {phrase}"


def test_substitute_placeholders_unmatched_block_raises():
    """An unpaired {{mcp:...}} or {{cli:...}} block in the template
    must fail loudly so typos in template.md are caught in tests, not
    silently shipped."""
    target = get_target("claude-code")
    bad_template = "Some text {{mcp:foo}} with an unmatched block."
    with pytest.raises(ValueError, match="unmatched"):
        _substitute_placeholders(bad_template, target)


def test_substitute_placeholders_empty_blocks_allowed():
    """A paired block where one side is empty is valid and useful for
    sections that should appear in one target but not the other."""
    target_claude = get_target("claude-code")
    target_codex = get_target("codex")
    tpl = "prefix {{mcp:only-in-mcp}}{{cli:}} suffix"
    claude_out = _substitute_placeholders(tpl, target_claude)
    codex_out = _substitute_placeholders(tpl, target_codex)
    assert "only-in-mcp" in claude_out
    assert "only-in-mcp" not in codex_out
    assert "prefix  suffix" in codex_out


# ── Install ──────────────────────────────────────────────────────────────────


def test_install_creates_file_with_rendered_content(tmp_path: Path):
    dest = tmp_path / "SKILL.md"
    result = install("claude-code", destination=dest)

    assert result.action == "created"
    assert result.previous_version is None
    assert result.destination == dest
    assert dest.exists()
    content = dest.read_text(encoding="utf-8")
    assert "Claude Code" in content
    assert "smriti_state(" in content
    assert "smriti_skill_pack_version" in content


def test_install_creates_parent_directories(tmp_path: Path):
    dest = tmp_path / "deep" / "nested" / "path" / "SKILL.md"
    assert not dest.parent.exists()

    result = install("claude-code", destination=dest)

    assert result.action == "created"
    assert dest.exists()
    assert dest.parent.is_dir()


def test_install_dry_run_does_not_write(tmp_path: Path):
    dest = tmp_path / "SKILL.md"
    result = install("claude-code", destination=dest, dry_run=True)

    assert result.action == "dry_run"
    assert not dest.exists()
    # But the rendered content is returned on the result.
    assert "Claude Code" in result.content


def test_install_refuses_same_version_without_force(tmp_path: Path):
    dest = tmp_path / "SKILL.md"
    install("claude-code", destination=dest)  # first install

    result = install("claude-code", destination=dest)  # second attempt
    assert result.action == "skipped"
    assert result.previous_version == get_version()
    # File on disk is unchanged.
    assert "Claude Code" in dest.read_text(encoding="utf-8")


def test_install_force_overwrites_same_version(tmp_path: Path):
    dest = tmp_path / "SKILL.md"
    install("claude-code", destination=dest)  # first install

    # Tamper with the file — a downstream edit the agent made by hand.
    current_ver = get_version()
    dest.write_text(
        f"---\nsmriti_skill_pack_version: {current_ver}\n---\n\nTAMPERED\n",
        encoding="utf-8",
    )

    result = install("claude-code", destination=dest, force=True)
    assert result.action == "overwritten"
    assert result.previous_version == current_ver
    # TAMPERED content is gone; fresh rendered content is back.
    assert "TAMPERED" not in dest.read_text(encoding="utf-8")
    assert "Claude Code" in dest.read_text(encoding="utf-8")


def test_install_overwrites_older_version_without_force(tmp_path: Path):
    """An older version should be overwritten automatically — only
    same or newer versions are protected."""
    dest = tmp_path / "SKILL.md"
    dest.write_text(
        "---\nsmriti_skill_pack_version: 0.9\n---\n\nOLD CONTENT\n",
        encoding="utf-8",
    )

    result = install("claude-code", destination=dest)
    assert result.action == "overwritten"
    assert result.previous_version == "0.9"
    assert "OLD CONTENT" not in dest.read_text(encoding="utf-8")


def test_install_dry_run_still_reports_previous_version(tmp_path: Path):
    dest = tmp_path / "SKILL.md"
    dest.write_text(
        "---\nsmriti_skill_pack_version: 0.5\n---\n\n...\n",
        encoding="utf-8",
    )

    result = install("claude-code", destination=dest, dry_run=True)
    assert result.action == "dry_run"
    assert result.previous_version == "0.5"
    # Dry run must not touch disk.
    assert dest.read_text(encoding="utf-8").startswith("---")
    assert "0.5" in dest.read_text(encoding="utf-8")


# ── list_targets ─────────────────────────────────────────────────────────────


def test_list_targets_returns_known_targets():
    targets = list_targets()
    keys = [t.key for t in targets]
    assert "claude-code" in keys
    assert "codex" in keys
    assert all(isinstance(t, SkillTarget) for t in targets)


def test_list_targets_is_deterministic():
    """Two calls return the same ordering — important for `smriti skills
    list` output stability across invocations."""
    a = [t.key for t in list_targets()]
    b = [t.key for t in list_targets()]
    assert a == b
