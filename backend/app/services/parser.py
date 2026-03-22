"""Transcript parsing service — pure function, no IO.

Supports multiple real-world transcript formats:
- Standard: Human:/Assistant:, User:/AI:, You:/Bot:, ChatGPT:/Claude:
- ChatGPT web: "You said:" / "ChatGPT said:"
- ChatGPT shared links: "User" / "Assistant" on own line
- Markdown bold: **User**: / **Assistant**:
- Plain text fallback (single UNKNOWN message)

Strategy: try each format detector in priority order; first match wins.
"""

import re
from typing import Callable

from app.domain.enums import MessageRole
from app.domain.models import Message

# ── Human / Assistant keyword sets ───────────────────────────────────────

HUMAN_KEYWORDS = {"human", "user", "you"}
ASSISTANT_KEYWORDS = {
    "assistant", "ai", "chatgpt", "claude", "cursor", "bot",
    "gpt-4", "gpt-4o", "gpt", "copilot",
}


def _detect_role(marker: str) -> MessageRole:
    """Map a role marker string to a MessageRole."""
    cleaned = marker.lower().strip().rstrip(":").strip("* ")
    if cleaned in HUMAN_KEYWORDS:
        return MessageRole.HUMAN
    if cleaned in ASSISTANT_KEYWORDS:
        return MessageRole.ASSISTANT
    return MessageRole.UNKNOWN


# ═════════════════════════════════════════════════════════════════════════
# Strategy 1: Standard "Role: content" on same line
# Matches: Human: ..., Assistant: ..., User: ..., AI: ..., ChatGPT: ...
# ═════════════════════════════════════════════════════════════════════════

_STANDARD_ROLE_WORDS = "|".join(HUMAN_KEYWORDS | ASSISTANT_KEYWORDS)

# Pattern matches "Role:" at start of line (case-insensitive)
_STANDARD_SPLIT = re.compile(
    rf"^({_STANDARD_ROLE_WORDS}):\s*",
    re.IGNORECASE | re.MULTILINE,
)


def _try_standard(raw: str) -> list[Message] | None:
    parts = _STANDARD_SPLIT.split(raw)
    if len(parts) <= 1:
        return None
    return _parts_to_messages(parts)


# ═════════════════════════════════════════════════════════════════════════
# Strategy 2: ChatGPT web copy-paste — "You said:" / "ChatGPT said:"
# ═════════════════════════════════════════════════════════════════════════

_CHATGPT_WEB_SPLIT = re.compile(
    r"^(You|ChatGPT|User|Assistant)\s+said:\s*",
    re.IGNORECASE | re.MULTILINE,
)


def _try_chatgpt_web(raw: str) -> list[Message] | None:
    parts = _CHATGPT_WEB_SPLIT.split(raw)
    if len(parts) <= 1:
        return None
    return _parts_to_messages(parts)


# ═════════════════════════════════════════════════════════════════════════
# Strategy 3: ChatGPT shared link / "Role" on own line (no colon)
# Matches: A line that is ONLY "User" or "Assistant" (possibly with
# markdown heading markers), followed by content on next lines.
# ═════════════════════════════════════════════════════════════════════════

_SHARED_LINK_SPLIT = re.compile(
    rf"^#{{0,3}}\s*({_STANDARD_ROLE_WORDS})\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _try_shared_link(raw: str) -> list[Message] | None:
    parts = _SHARED_LINK_SPLIT.split(raw)
    if len(parts) <= 1:
        return None
    return _parts_to_messages(parts)


# ═════════════════════════════════════════════════════════════════════════
# Strategy 4: Markdown bold — **User**: / **Assistant**:
# ═════════════════════════════════════════════════════════════════════════

_MARKDOWN_BOLD_SPLIT = re.compile(
    rf"^\*\*({_STANDARD_ROLE_WORDS})\*\*:\s*",
    re.IGNORECASE | re.MULTILINE,
)


def _try_markdown_bold(raw: str) -> list[Message] | None:
    parts = _MARKDOWN_BOLD_SPLIT.split(raw)
    if len(parts) <= 1:
        return None
    return _parts_to_messages(parts)


# ═════════════════════════════════════════════════════════════════════════
# Strategy 5: Angle-bracket / HTML-style — <user> / <assistant>
# ═════════════════════════════════════════════════════════════════════════

_ANGLE_BRACKET_SPLIT = re.compile(
    rf"^<({_STANDARD_ROLE_WORDS})>\s*",
    re.IGNORECASE | re.MULTILINE,
)


def _try_angle_bracket(raw: str) -> list[Message] | None:
    parts = _ANGLE_BRACKET_SPLIT.split(raw)
    if len(parts) <= 1:
        return None
    return _parts_to_messages(parts)


# ═════════════════════════════════════════════════════════════════════════
# Shared helper: convert regex split parts into Message list
# ═════════════════════════════════════════════════════════════════════════

def _parts_to_messages(parts: list[str]) -> list[Message] | None:
    """Convert regex split output (pre-text, marker, content, ...) to Messages.

    `re.split()` with a capturing group produces:
        [pre_text, marker1, content1, marker2, content2, ...]
    """
    messages: list[Message] = []
    position = 0

    # Start at index 1 to skip pre-marker text
    i = 1
    while i < len(parts) - 1:
        marker = parts[i]
        content = parts[i + 1].strip()
        if content:
            role = _detect_role(marker)
            messages.append(Message(role=role, content=content, position=position))
            position += 1
        i += 2

    return messages if messages else None


# ═════════════════════════════════════════════════════════════════════════
# Main entry point
# ═════════════════════════════════════════════════════════════════════════

# Strategies in priority order — first successful match wins
_STRATEGIES: list[Callable[[str], list[Message] | None]] = [
    _try_standard,
    _try_chatgpt_web,
    _try_markdown_bold,
    _try_angle_bracket,
    _try_shared_link,  # Last among structured — it's greedy (bare "User" on a line)
]


def parse_transcript(raw: str) -> list[Message]:
    """Parse a raw transcript into a list of Message objects.

    Tries multiple format detection strategies in order:
    1. Standard role labels (Human:/Assistant:, User:/AI:, etc.)
    2. ChatGPT web copy-paste ("You said:" / "ChatGPT said:")
    3. Markdown bold (**User**: / **Assistant**:)
    4. Angle-bracket (<user> / <assistant>)
    5. Shared-link style (bare "User" / "Assistant" on own line)
    6. Fallback: single UNKNOWN message

    All strategies:
    - Preserve code blocks intact within messages
    - Handle multi-line message content
    - Assign sequential position numbers

    Args:
        raw: The raw transcript text.

    Returns:
        List of Message objects. Empty list for empty/whitespace input.
    """
    if not raw or not raw.strip():
        return []

    # Try each strategy
    for strategy in _STRATEGIES:
        result = strategy(raw)
        if result:
            return result

    # Fallback: entire transcript as single unknown message
    return [Message(role=MessageRole.UNKNOWN, content=raw.strip(), position=0)]
