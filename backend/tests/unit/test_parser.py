"""Unit tests for transcript parser — TDD-first test definitions.

These tests validate the pure parse_transcript() function which converts
raw transcript text into structured Message objects.
"""

import pytest

from app.domain.enums import MessageRole
from app.services.parser import parse_transcript


class TestParseRoleLabeled:
    """Tests for transcripts with explicit role labels."""

    def test_parse_role_labeled_simple(self):
        """P1: Simple Human/Assistant transcript produces 2 messages."""
        raw = "Human: Hi there\nAssistant: Hello! How can I help?"
        messages = parse_transcript(raw)

        assert len(messages) == 2
        assert messages[0].role == MessageRole.HUMAN
        assert messages[0].content == "Hi there"
        assert messages[1].role == MessageRole.ASSISTANT
        assert messages[1].content == "Hello! How can I help?"

    def test_parse_role_labeled_multiline(self):
        """P2: Multi-line messages preserve full content including newlines."""
        raw = "Human: I have a question.\nIt's about databases.\nAssistant: Sure, I can help.\nWhat would you like to know?"
        messages = parse_transcript(raw)

        assert len(messages) == 2
        assert "question" in messages[0].content
        assert "databases" in messages[0].content
        assert "help" in messages[1].content

    def test_parse_multi_turn(self):
        """P3: 5+ turn realistic transcript parses all turns correctly."""
        raw = (
            "Human: Help me with Python\n"
            "Assistant: Sure! What do you need?\n"
            "Human: How do I read a file?\n"
            "Assistant: Use the open() function.\n"
            "Human: Can you show me an example?\n"
            "Assistant: Here you go: with open('file.txt') as f: data = f.read()"
        )
        messages = parse_transcript(raw)

        assert len(messages) == 6
        assert all(m.role in (MessageRole.HUMAN, MessageRole.ASSISTANT) for m in messages)
        # Check alternating roles
        for i in range(len(messages)):
            expected = MessageRole.HUMAN if i % 2 == 0 else MessageRole.ASSISTANT
            assert messages[i].role == expected

    def test_parse_message_positions(self):
        """P13: Position field increments correctly across messages."""
        raw = "Human: First\nAssistant: Second\nHuman: Third"
        messages = parse_transcript(raw)

        assert len(messages) == 3
        assert messages[0].position == 0
        assert messages[1].position == 1
        assert messages[2].position == 2


class TestParseUnlabeled:
    """Tests for transcripts without role labels."""

    def test_parse_unlabeled_transcript(self):
        """P4: Plain text without role markers returns single unknown message."""
        raw = "This is just a paragraph of text about databases and APIs."
        messages = parse_transcript(raw)

        assert len(messages) == 1
        assert messages[0].role == MessageRole.UNKNOWN
        assert "databases" in messages[0].content

    def test_parse_empty_transcript(self):
        """P7: Empty string returns empty list."""
        messages = parse_transcript("")
        assert messages == []

    def test_parse_whitespace_only(self):
        """P8: Whitespace-only transcript returns empty list."""
        messages = parse_transcript("   \n\n  ")
        assert messages == []


class TestParseCodeBlocks:
    """Tests for code block preservation."""

    def test_parse_code_blocks_preserved(self):
        """P5: Code blocks within messages are preserved intact."""
        raw = "Human: Can you show me a function?\nAssistant: Here's a function:\n```python\ndef hello():\n    print('hello')\n```\nThat should work."
        messages = parse_transcript(raw)

        assert len(messages) == 2
        # Code block should be in assistant's message
        assert "```python" in messages[1].content
        assert "def hello():" in messages[1].content
        assert "```" in messages[1].content


class TestParseAlternativeMarkers:
    """Tests for alternative role marker formats."""

    def test_parse_alternative_markers_user_ai(self):
        """P9: User/AI markers are recognized."""
        raw = "User: Hello\nAI: Hi there!"
        messages = parse_transcript(raw)

        assert len(messages) == 2
        assert messages[0].role == MessageRole.HUMAN
        assert messages[1].role == MessageRole.ASSISTANT

    def test_parse_alternative_markers_you(self):
        """P9b: 'You:' marker recognized as human."""
        raw = "You: What's the weather?\nAssistant: I can't check weather."
        messages = parse_transcript(raw)

        assert len(messages) == 2
        assert messages[0].role == MessageRole.HUMAN

    def test_parse_mixed_markers(self):
        """P10: Mixed marker formats are handled."""
        raw = "Human: Hi\nChatGPT: Hello!"
        messages = parse_transcript(raw)

        assert len(messages) == 2
        assert messages[0].role == MessageRole.HUMAN
        assert messages[1].role == MessageRole.ASSISTANT

    def test_parse_colon_in_content(self):
        """P14: Content containing colons (like URLs) is preserved."""
        raw = "Human: Check out http://example.com for more info"
        messages = parse_transcript(raw)

        assert len(messages) == 1
        assert "http://example.com" in messages[0].content


class TestParseEdgeCases:
    """Edge case tests for the parser."""

    def test_parse_special_characters(self):
        """P12: Special characters and unicode are handled."""
        raw = "Human: What about émojis 🎉 and spëcial chars?\nAssistant: They work fine! 中文也可以"
        messages = parse_transcript(raw)

        assert len(messages) == 2
        assert "🎉" in messages[0].content
        assert "中文" in messages[1].content

    def test_parse_long_transcript(self):
        """P11: Very long transcripts are parsed completely."""
        # Generate a long transcript
        turns = []
        for i in range(100):
            turns.append(f"Human: Message {i} " + "word " * 50)
            turns.append(f"Assistant: Response {i} " + "word " * 50)
        raw = "\n".join(turns)

        messages = parse_transcript(raw)
        assert len(messages) == 200

    def test_parse_with_fixture_coding(self, coding_transcript):
        """Coding fixture parses without error."""
        messages = parse_transcript(coding_transcript)
        assert len(messages) >= 1

    def test_parse_with_fixture_planning(self, planning_transcript):
        """Planning fixture parses without error."""
        messages = parse_transcript(planning_transcript)
        assert len(messages) >= 1

    def test_parse_with_fixture_unlabeled(self, unlabeled_transcript):
        """Unlabeled fixture parses without crashing."""
        messages = parse_transcript(unlabeled_transcript)
        assert len(messages) >= 1

    def test_parse_with_fixture_code_heavy(self, code_heavy_transcript):
        """Code-heavy fixture parses without error."""
        messages = parse_transcript(code_heavy_transcript)
        assert len(messages) >= 1


# ═════════════════════════════════════════════════════════════════════════
# NEW TEST CASES — Real-world transcript formats
# ═════════════════════════════════════════════════════════════════════════


class TestChatGPTWebCopyPaste:
    """Tests for ChatGPT web UI copy-paste format ('You said:' / 'ChatGPT said:')."""

    def test_chatgpt_web_basic(self):
        """N1: Basic ChatGPT web copy-paste with 'You said:' / 'ChatGPT said:'."""
        raw = (
            "You said:\n"
            "Help me with Python decorators\n\n"
            "ChatGPT said:\n"
            "Decorators are functions that modify the behavior of other functions."
        )
        messages = parse_transcript(raw)

        assert len(messages) == 2
        assert messages[0].role == MessageRole.HUMAN
        assert "decorators" in messages[0].content
        assert messages[1].role == MessageRole.ASSISTANT
        assert "modify" in messages[1].content

    def test_chatgpt_web_multi_turn(self):
        """N2: Multi-turn ChatGPT web conversation."""
        raw = (
            "You said:\n"
            "Can you help me refactor the auth module?\n\n"
            "ChatGPT said:\n"
            "Sure! JWT is a great choice for REST APIs.\n\n"
            "You said:\n"
            "What about token rotation?\n\n"
            "ChatGPT said:\n"
            "Refresh token rotation is a security best practice."
        )
        messages = parse_transcript(raw)

        assert len(messages) == 4
        assert messages[0].role == MessageRole.HUMAN
        assert messages[1].role == MessageRole.ASSISTANT
        assert messages[2].role == MessageRole.HUMAN
        assert messages[3].role == MessageRole.ASSISTANT

    def test_chatgpt_web_with_code_blocks(self):
        """N3: ChatGPT web format preserves code blocks."""
        raw = (
            "You said:\n"
            "Show me a retry decorator\n\n"
            "ChatGPT said:\n"
            "Here's a retry decorator:\n\n"
            "```python\n"
            "def retry(func):\n"
            "    def wrapper(*args):\n"
            "        return func(*args)\n"
            "    return wrapper\n"
            "```"
        )
        messages = parse_transcript(raw)

        assert len(messages) == 2
        assert "```python" in messages[1].content
        assert "def retry" in messages[1].content


class TestChatGPTSharedLink:
    """Tests for ChatGPT shared link format (bare 'User' / 'Assistant' on own line)."""

    def test_shared_link_basic(self):
        """N4: ChatGPT shared link format with bare role names."""
        raw = (
            "User\n"
            "I need help designing a database schema.\n\n"
            "Assistant\n"
            "Here's a normalized schema design with Users and Orders tables."
        )
        messages = parse_transcript(raw)

        assert len(messages) == 2
        assert messages[0].role == MessageRole.HUMAN
        assert "database schema" in messages[0].content
        assert messages[1].role == MessageRole.ASSISTANT

    def test_shared_link_multi_turn(self):
        """N5: Multi-turn shared link format."""
        raw = (
            "User\n"
            "How do I set up migrations?\n\n"
            "Assistant\n"
            "Use Alembic with autogenerate.\n\n"
            "User\n"
            "Should I denormalize anything?\n\n"
            "Assistant\n"
            "Consider denormalizing for read-heavy operations."
        )
        messages = parse_transcript(raw)

        assert len(messages) == 4
        assert messages[0].role == MessageRole.HUMAN
        assert messages[3].role == MessageRole.ASSISTANT


class TestMarkdownBoldFormat:
    """Tests for markdown bold role markers (**User**: / **Assistant**:)."""

    def test_markdown_bold_basic(self):
        """N6: Basic markdown bold format."""
        raw = (
            "**User**: I want to add error handling to the API.\n\n"
            "**Assistant**: Here's a global exception handler for FastAPI."
        )
        messages = parse_transcript(raw)

        assert len(messages) == 2
        assert messages[0].role == MessageRole.HUMAN
        assert messages[1].role == MessageRole.ASSISTANT

    def test_markdown_bold_with_code(self):
        """N7: Markdown bold format with code blocks."""
        raw = (
            "**User**: Show me a FastAPI route\n\n"
            "**Assistant**: Here you go:\n\n"
            "```python\n"
            "@app.get('/items')\n"
            "def get_items():\n"
            "    return []\n"
            "```\n\n"
            "**User**: Can you add query params?\n\n"
            "**Assistant**: Add a `skip: int = 0` parameter."
        )
        messages = parse_transcript(raw)

        assert len(messages) == 4
        assert "```python" in messages[1].content
        assert messages[2].role == MessageRole.HUMAN
        assert messages[3].role == MessageRole.ASSISTANT

    def test_markdown_bold_human_variant(self):
        """N8: Markdown bold with 'Human' instead of 'User'."""
        raw = (
            "**Human**: What's the best ORM for Python?\n\n"
            "**Assistant**: SQLAlchemy is the most popular choice."
        )
        messages = parse_transcript(raw)

        assert len(messages) == 2
        assert messages[0].role == MessageRole.HUMAN


class TestAngleBracketFormat:
    """Tests for angle-bracket format (<user> / <assistant>)."""

    def test_angle_bracket_basic(self):
        """N9: Angle bracket format."""
        raw = (
            "<user>\n"
            "How do I deploy to AWS?\n\n"
            "<assistant>\n"
            "I recommend using AWS ECS with Docker."
        )
        messages = parse_transcript(raw)

        assert len(messages) == 2
        assert messages[0].role == MessageRole.HUMAN
        assert messages[1].role == MessageRole.ASSISTANT

    def test_angle_bracket_multi_turn(self):
        """N10: Multi-turn angle bracket format."""
        raw = (
            "<human>\n"
            "What's the difference between REST and GraphQL?\n\n"
            "<assistant>\n"
            "REST uses multiple endpoints, GraphQL uses a single endpoint.\n\n"
            "<human>\n"
            "Which should I use?\n\n"
            "<assistant>\n"
            "It depends on your use case."
        )
        messages = parse_transcript(raw)

        assert len(messages) == 4


class TestMixedAndEdgeCases:
    """Mixed format and edge case tests."""

    def test_transcript_with_urls_not_confused(self):
        """N11: URLs containing role words don't trigger false splits."""
        raw = "Human: Check https://assistant.google.com for more info\nAssistant: That's a useful link!"
        messages = parse_transcript(raw)

        assert len(messages) == 2
        assert "https://assistant.google.com" in messages[0].content

    def test_case_insensitive_markers(self):
        """N12: Markers are case-insensitive."""
        raw = "HUMAN: Hello\nASSISTANT: Hi there!"
        messages = parse_transcript(raw)

        assert len(messages) == 2
        assert messages[0].role == MessageRole.HUMAN
        assert messages[1].role == MessageRole.ASSISTANT

    def test_extra_whitespace_between_messages(self):
        """N13: Extra blank lines between messages are handled."""
        raw = (
            "Human: First question\n\n\n\n"
            "Assistant: First answer\n\n\n"
            "Human: Second question\n\n"
            "Assistant: Second answer"
        )
        messages = parse_transcript(raw)

        assert len(messages) == 4

    def test_very_long_messages(self):
        """N14: Very long individual messages are preserved."""
        long_content = "word " * 500
        raw = f"Human: {long_content}\nAssistant: Got it."
        messages = parse_transcript(raw)

        assert len(messages) == 2
        assert len(messages[0].content) > 2000

    def test_code_block_with_human_keyword(self):
        """N15: Code blocks containing 'Human:' don't cause false splits."""
        raw = (
            "Human: How do I parse this?\n"
            "Assistant: Here's how:\n"
            "```\n"
            "# This line says Human: something\n"
            "data = parse(input)\n"
            "```\n"
            "That should work."
        )
        messages = parse_transcript(raw)

        # Should produce 2 messages — the code block stays in assistant's message
        assert len(messages) >= 2
        assert messages[0].role == MessageRole.HUMAN

    def test_single_role_marker(self):
        """N16: Single role marker with no alternation produces one message."""
        raw = "Human: Just a single question with no response yet."
        messages = parse_transcript(raw)

        assert len(messages) == 1
        assert messages[0].role == MessageRole.HUMAN

    def test_copilot_marker(self):
        """N17: 'Copilot:' marker recognized as assistant."""
        raw = "User: Help me\nCopilot: Sure thing!"
        messages = parse_transcript(raw)

        assert len(messages) == 2
        assert messages[1].role == MessageRole.ASSISTANT

    def test_gpt4o_marker(self):
        """N18: 'GPT-4o:' variant recognized."""
        raw = "User: What's new?\nGPT-4o: I have improved capabilities."
        messages = parse_transcript(raw)

        assert len(messages) == 2
        assert messages[1].role == MessageRole.ASSISTANT

