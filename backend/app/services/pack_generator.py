"""Context pack generation service — deterministic template-based rendering."""

from app.domain.enums import TargetTool
from app.domain.models import ContextPack, ExtractionResult


def generate_pack(result: ExtractionResult, target: TargetTool) -> ContextPack:
    """Generate a target-specific continuation pack from extraction results.

    This is a pure function — deterministic, no LLM, no IO.
    Each target gets a format optimized for that tool's strengths.

    Args:
        result: The extraction result containing all artifacts.
        target: The target tool for the continuation pack.

    Returns:
        ContextPack with rendered content.
    """
    generators = {
        TargetTool.CHATGPT: _generate_chatgpt_pack,
        TargetTool.CLAUDE: _generate_claude_pack,
        TargetTool.CURSOR: _generate_cursor_pack,
        TargetTool.GENERIC: _generate_generic_pack,
    }

    generator = generators[target]
    content = generator(result)

    return ContextPack(
        target_tool=target,
        content=content,
        format="markdown",
    )


def _generate_chatgpt_pack(result: ExtractionResult) -> str:
    """Generate a conversational continuation prompt for ChatGPT."""
    lines = []
    lines.append("I'm continuing a previous work session. Here's the context you need to help me pick up where I left off:")
    lines.append("")

    lines.append(f"**What we were working on:** {result.summary}")
    lines.append("")

    if result.decisions:
        lines.append("**Key decisions already made:**")
        for d in result.decisions:
            lines.append(f"- {d.description}")
        lines.append("")

    if result.tasks:
        pending = [t for t in result.tasks if t.status != "completed"]
        if pending:
            lines.append("**Outstanding tasks:**")
            for t in pending:
                lines.append(f"- {t.description} (status: {t.status})")
            lines.append("")

    if result.open_questions:
        lines.append("**Open questions to address:**")
        for q in result.open_questions:
            lines.append(f"- {q.question}")
        lines.append("")

    if result.entities:
        lines.append("**Important context:**")
        entity_names = [e.name for e in result.entities]
        lines.append(f"Key entities/concepts: {', '.join(entity_names)}")
        lines.append("")

    if result.code_snippets:
        lines.append("**Relevant code from the session:**")
        for s in result.code_snippets:
            lines.append(f"```{s.language}")
            lines.append(s.code)
            lines.append("```")
            if s.description:
                lines.append(f"({s.description})")
            lines.append("")

    lines.append("Please help me continue this work. Start by confirming you understand the context, then let's proceed with the outstanding tasks.")

    return "\n".join(lines)


def _generate_claude_pack(result: ExtractionResult) -> str:
    """Generate a structured continuation prompt for Claude with XML-style sections."""
    lines = []
    lines.append("I'm continuing work from a previous session. Here's the structured context:")
    lines.append("")

    lines.append("<context>")
    lines.append(f"<summary>{result.summary}</summary>")
    lines.append("")

    if result.decisions:
        lines.append("<decisions>")
        for d in result.decisions:
            lines.append(f"  <decision>{d.description}</decision>")
        lines.append("</decisions>")
        lines.append("")

    if result.tasks:
        lines.append("<tasks>")
        for t in result.tasks:
            lines.append(f"  <task status=\"{t.status}\">{t.description}</task>")
        lines.append("</tasks>")
        lines.append("")

    if result.open_questions:
        lines.append("<open_questions>")
        for q in result.open_questions:
            lines.append(f"  <question>{q.question}</question>")
        lines.append("</open_questions>")
        lines.append("")

    if result.entities:
        lines.append("<entities>")
        for e in result.entities:
            lines.append(f"  <entity type=\"{e.type}\">{e.name}</entity>")
        lines.append("</entities>")
        lines.append("")

    if result.code_snippets:
        lines.append("<code_context>")
        for s in result.code_snippets:
            lines.append(f"  <snippet language=\"{s.language}\">")
            lines.append(f"    {s.code}")
            lines.append(f"  </snippet>")
        lines.append("</code_context>")
        lines.append("")

    lines.append("</context>")
    lines.append("")
    lines.append("Please review this context and help me continue. Focus on the outstanding tasks and open questions.")

    return "\n".join(lines)


def _generate_cursor_pack(result: ExtractionResult) -> str:
    """Generate a developer-focused continuation pack for Cursor."""
    lines = []
    lines.append("# Continuation Context")
    lines.append("")
    lines.append(f"## Summary")
    lines.append(result.summary)
    lines.append("")

    if result.tasks:
        lines.append("## Task Checklist")
        for t in result.tasks:
            checkbox = "x" if t.status == "completed" else " "
            lines.append(f"- [{checkbox}] {t.description}")
        lines.append("")

    if result.decisions:
        lines.append("## Decisions")
        for d in result.decisions:
            lines.append(f"- {d.description}")
        lines.append("")

    if result.entities:
        files = [e for e in result.entities if e.type == "file"]
        tech = [e for e in result.entities if e.type == "technology"]
        other = [e for e in result.entities if e.type not in ("file", "technology")]
        if files:
            lines.append("## Relevant Files")
            for e in files:
                lines.append(f"- `{e.name}`")
            lines.append("")
        if tech:
            lines.append("## Technologies")
            for e in tech:
                lines.append(f"- {e.name}")
            lines.append("")
        if other:
            lines.append("## Key Entities")
            for e in other:
                lines.append(f"- {e.name} ({e.type})")
            lines.append("")

    if result.code_snippets:
        lines.append("## Code Context")
        for s in result.code_snippets:
            if s.description:
                lines.append(f"### {s.description}")
            lines.append(f"```{s.language}")
            lines.append(s.code)
            lines.append("```")
            lines.append("")

    if result.open_questions:
        lines.append("## Open Questions")
        for q in result.open_questions:
            lines.append(f"- {q.question}")
        lines.append("")

    return "\n".join(lines)


def _generate_generic_pack(result: ExtractionResult) -> str:
    """Generate a portable Markdown continuation pack."""
    lines = []
    lines.append("# Session Continuation Pack")
    lines.append("")
    lines.append("## Summary")
    lines.append(result.summary)
    lines.append("")

    if result.decisions:
        lines.append("## Key Decisions")
        for d in result.decisions:
            lines.append(f"- **{d.description}**")
            if d.context:
                lines.append(f"  Context: {d.context}")
        lines.append("")

    if result.tasks:
        lines.append("## Tasks")
        for t in result.tasks:
            status_icon = "✅" if t.status == "completed" else "⬜"
            lines.append(f"- {status_icon} {t.description} [{t.status}]")
        lines.append("")

    if result.open_questions:
        lines.append("## Open Questions")
        for q in result.open_questions:
            lines.append(f"- {q.question}")
            if q.context:
                lines.append(f"  Context: {q.context}")
        lines.append("")

    if result.entities:
        lines.append("## Entities")
        for e in result.entities:
            lines.append(f"- **{e.name}** ({e.type})")
        lines.append("")

    if result.code_snippets:
        lines.append("## Code Snippets")
        for s in result.code_snippets:
            if s.description:
                lines.append(f"### {s.description}")
            lines.append(f"```{s.language}")
            lines.append(s.code)
            lines.append("```")
            lines.append("")

    return "\n".join(lines)


from typing import Any

def generate_from_memories(memories: list[Any], target: TargetTool) -> ContextPack:
    """Generate a target-specific continuation pack from a list of memory items.
    
    Unlike generate_pack which uses fixed ExtractionResult schemas, this
    dynamically groups and renders any memory items.
    """
    generators = {
        TargetTool.CHATGPT: _generate_chatgpt_memories_pack,
        TargetTool.CLAUDE: _generate_claude_memories_pack,
        TargetTool.CURSOR: _generate_cursor_memories_pack,
        TargetTool.GENERIC: _generate_generic_memories_pack,
    }
    
    generator = generators[target]
    content = generator(memories)
    
    return ContextPack(
        target_tool=target,
        content=content,
        format="markdown",
    )


def _render_memories_markdown(memories: list[Any]) -> str:
    """Helper to render a list of memories into structured markdown."""
    lines = []
    from collections import defaultdict
    grouped = defaultdict(list)
    for m in memories:
        # handle dicts or objects
        m_type = m["type"] if isinstance(m, dict) else m.type
        grouped[m_type].append(m)
        
    order = ["summary", "decision", "preference", "episodic", "semantic", "task", "code"]
    
    for t in order:
        if t in grouped:
            lines.append(f"## {t.title()}s")
            for m in grouped[t]:
                m_content = m["content"] if isinstance(m, dict) else m.content
                lines.append(f"- {m_content}")
            lines.append("")
            
    for t, items in grouped.items():
        if t not in order:
            lines.append(f"## {t.title()}s")
            for m in items:
                m_content = m["content"] if isinstance(m, dict) else m.content
                lines.append(f"- {m_content}")
            lines.append("")
            
    return "\n".join(lines)


def _generate_chatgpt_memories_pack(memories: list[Any]) -> str:
    lines = [
        "I'm continuing a previous work session. Here is our shared memory context:",
        "",
        _render_memories_markdown(memories),
        "Please help me continue this work. Start by confirming you understand the context."
    ]
    return "\n".join(lines)


def _generate_claude_memories_pack(memories: list[Any]) -> str:
    lines = [
        "I'm continuing work from a previous session. Here is our shared memory context:",
        "",
        "<context>",
        _render_memories_markdown(memories),
        "</context>",
        "",
        "Please review this context and help me continue."
    ]
    return "\n".join(lines)


def _generate_cursor_memories_pack(memories: list[Any]) -> str:
    lines = [
        "# Shared Memory Context",
        "",
        _render_memories_markdown(memories)
    ]
    return "\n".join(lines)


def _generate_generic_memories_pack(memories: list[Any]) -> str:
    lines = [
        "# Session Continuation Pack",
        "",
        _render_memories_markdown(memories)
    ]
    return "\n".join(lines)
