"""Unit tests for _normalize_tasks in the checkpoint route module.

Validates that the task normalizer handles:
- Plain string tasks (legacy format)
- Structured task objects with valid intent_hint
- Invalid or missing intent_hint values are dropped
- blocked_by is preserved when present and non-empty
- Deduplication by text field
- Mixed string + object input
"""
import pytest

from app.api.routes.checkpoint import _normalize_tasks


def test_plain_strings():
    result = _normalize_tasks(["Task A", "Task B"])
    assert result == [{"text": "Task A"}, {"text": "Task B"}]


def test_structured_with_valid_intent():
    result = _normalize_tasks([
        {"text": "Add endpoint", "intent_hint": "implement"},
    ])
    assert result == [{"text": "Add endpoint", "intent_hint": "implement"}]


def test_structured_with_all_fields():
    result = _normalize_tasks([
        {
            "text": "Write tests",
            "intent_hint": "test",
            "blocked_by": "endpoint-impl",
        },
    ])
    assert result == [
        {"text": "Write tests", "intent_hint": "test", "blocked_by": "endpoint-impl"},
    ]


def test_invalid_intent_hint_dropped():
    """Invalid intent_hint values are silently dropped."""
    result = _normalize_tasks([
        {"text": "Do stuff", "intent_hint": "invalid-type"},
    ])
    assert result == [{"text": "Do stuff"}]


def test_null_intent_hint_dropped():
    result = _normalize_tasks([
        {"text": "Do stuff", "intent_hint": None},
    ])
    assert result == [{"text": "Do stuff"}]


def test_empty_blocked_by_dropped():
    result = _normalize_tasks([
        {"text": "Task", "blocked_by": ""},
    ])
    assert result == [{"text": "Task"}]


def test_null_blocked_by_dropped():
    result = _normalize_tasks([
        {"text": "Task", "blocked_by": None},
    ])
    assert result == [{"text": "Task"}]


def test_dedup_by_text():
    """Duplicate text entries are deduplicated."""
    result = _normalize_tasks([
        {"text": "Same task", "intent_hint": "implement"},
        {"text": "Same task", "intent_hint": "test"},
    ])
    assert len(result) == 1
    assert result[0]["text"] == "Same task"
    # First occurrence wins
    assert result[0]["intent_hint"] == "implement"


def test_dedup_across_string_and_dict():
    """String and dict with same text are deduplicated."""
    result = _normalize_tasks([
        "Add feature",
        {"text": "Add feature", "intent_hint": "implement"},
    ])
    assert len(result) == 1
    # String version comes first, no intent_hint
    assert result[0] == {"text": "Add feature"}


def test_mixed_string_and_dict():
    result = _normalize_tasks([
        "Legacy task",
        {"text": "Structured task", "intent_hint": "docs"},
    ])
    assert result == [
        {"text": "Legacy task"},
        {"text": "Structured task", "intent_hint": "docs"},
    ]


def test_empty_items_skipped():
    result = _normalize_tasks(["", None, {"text": ""}, "Valid task"])
    assert result == [{"text": "Valid task"}]


def test_empty_list():
    assert _normalize_tasks([]) == []


def test_all_five_intents_accepted():
    """All valid intent types are accepted."""
    for intent in ("implement", "review", "investigate", "docs", "test"):
        result = _normalize_tasks([{"text": f"Task for {intent}", "intent_hint": intent}])
        assert result[0]["intent_hint"] == intent, f"intent {intent} was dropped"


def test_intent_case_insensitive():
    """Intent hints are normalized to lowercase."""
    result = _normalize_tasks([
        {"text": "Task", "intent_hint": "IMPLEMENT"},
    ])
    assert result[0]["intent_hint"] == "implement"


# ── Task ID tests ──────────────────────────────────────────────────────────


def test_task_id_passthrough():
    """Task id field is preserved when present."""
    result = _normalize_tasks([
        {"text": "Implement endpoint", "id": "impl-1", "intent_hint": "implement"},
    ])
    assert result[0]["id"] == "impl-1"


def test_task_id_stripped():
    """Task id is stripped of whitespace."""
    result = _normalize_tasks([
        {"text": "Task", "id": "  docs-arch  "},
    ])
    assert result[0]["id"] == "docs-arch"


def test_task_id_empty_dropped():
    """Empty task id is not included."""
    result = _normalize_tasks([
        {"text": "Task", "id": ""},
    ])
    assert "id" not in result[0]


def test_task_id_null_dropped():
    """None task id is not included."""
    result = _normalize_tasks([
        {"text": "Task", "id": None},
    ])
    assert "id" not in result[0]


def test_task_id_with_all_fields():
    """Task with id, intent_hint, and blocked_by preserves all."""
    result = _normalize_tasks([
        {
            "text": "Write tests",
            "id": "test-e2e",
            "intent_hint": "test",
            "blocked_by": "impl-1",
        },
    ])
    assert result[0] == {
        "text": "Write tests",
        "id": "test-e2e",
        "intent_hint": "test",
        "blocked_by": "impl-1",
    }


def test_string_task_has_no_id():
    """Plain string tasks have no id field."""
    result = _normalize_tasks(["A string task"])
    assert "id" not in result[0]
