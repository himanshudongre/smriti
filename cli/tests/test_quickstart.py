"""Tests for `smriti quickstart` and the shipped demo-space fixture.

Covers:
- Parser wiring (flags, mutually exclusive --remove/--reset)
- Fixture integrity — counts, valid intent types / note kinds, the demo
  marker, branch divergence, structured tasks. These are content-integrity
  guards: the demo is shipped data, and these tests fail loudly if an edit
  silently breaks the narrative it is meant to teach.
- seed_demo_space drives the expected sequence of API calls, and rolls back
  a half-built space on failure
- cmd_quickstart: seeds when absent, is idempotent when present, fails
  cleanly on an unreachable backend
- remove_demo_space deletes only a marked demo space; refuses a look-alike

Like the rest of cli/tests, these use MagicMock(spec=SmritiClient) — no
running backend required.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from smriti_cli import main as cli_main
from smriti_cli.client import SmritiClient, SmritiError
from smriti_cli.quickstart import (
    CLAIMS,
    DEMO_MARKER,
    DEMO_SPACE_DESCRIPTION,
    DEMO_SPACE_NAME,
    FORK_CHECKPOINT,
    MAIN_CHECKPOINTS,
    NOTES,
    build_guide,
    find_demo_space,
    is_demo_space,
    remove_demo_space,
    seed_demo_space,
)

# These mirror the backend's validation sets (claims.py VALID_INTENT_TYPES,
# checkpoint.py VALID_NOTE_KINDS). If the demo fixture ever uses a value
# outside them, seeding would 400 against a real backend — catch it here.
BACKEND_INTENT_TYPES = {"implement", "review", "investigate", "docs", "test"}
BACKEND_NOTE_KINDS = {"note", "milestone", "noise"}


# ── helpers ──────────────────────────────────────────────────────────────────


def _make_seed_client() -> MagicMock:
    """A MagicMock(spec=SmritiClient) with every seed-path method configured."""
    client = MagicMock(spec=SmritiClient)
    client.base_url = "http://localhost:8000"
    client.list_spaces.return_value = []
    client.create_space.return_value = {"id": "demo-space-id", "name": DEMO_SPACE_NAME}
    client.create_session.return_value = {"id": "session-main"}

    commit_counter = iter(range(1, 9999))

    def _commit(payload):
        n = next(commit_counter)
        return {"id": f"commit-{n}", "commit_hash": f"hash{n:04d}", "branch_name": "main"}

    client.create_chat_commit.side_effect = _commit
    client.fork_session.return_value = {
        "session_id": "session-fork",
        "branch_name": "explore/redis-limiter",
    }
    client.close_branch.return_value = {"branch_name": "explore/redis-limiter"}
    client.add_checkpoint_note.return_value = {"checkpoint_id": "cp", "kind": "note"}

    claim_counter = iter(range(1, 9999))

    def _claim(**kwargs):
        return {"id": f"claim-{next(claim_counter)}", **kwargs}

    client.create_claim.side_effect = _claim
    client.update_claim.return_value = {"id": "claim-1", "status": "done"}
    return client


def _args(*argv: str):
    """Parse a quickstart argv and stub api_url, the way main() would."""
    parsed = cli_main._build_parser().parse_args(["quickstart", *argv])
    parsed.api_url = None
    return parsed


# ── parser wiring ────────────────────────────────────────────────────────────


def test_quickstart_parser_wiring():
    args = _args()
    assert args.command == "quickstart"
    assert args.func is cli_main.cmd_quickstart
    assert args.remove is False and args.reset is False
    assert args.yes is False and args.json is False

    assert _args("--remove").remove is True
    reset = _args("--reset", "-y")
    assert reset.reset is True and reset.yes is True


def test_quickstart_remove_and_reset_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        cli_main._build_parser().parse_args(["quickstart", "--remove", "--reset"])


# ── fixture integrity ────────────────────────────────────────────────────────


def test_fixture_has_four_main_checkpoints_and_one_fork():
    assert len(MAIN_CHECKPOINTS) == 4
    assert FORK_CHECKPOINT["key"] == "redis-spike"
    assert FORK_CHECKPOINT["disposition"] == "abandoned"


def test_fixture_uses_two_distinct_agents():
    authors = {cp["author_agent"] for cp in MAIN_CHECKPOINTS}
    authors.add(FORK_CHECKPOINT["author_agent"])
    assert authors == {"claude-code", "codex-local"}


def test_fixture_has_a_cross_agent_continuation():
    """At least one adjacent main checkpoint pair changes author — the
    hand-off that makes the coordination metric non-zero."""
    pairs = zip(MAIN_CHECKPOINTS, MAIN_CHECKPOINTS[1:])
    assert any(a["author_agent"] != b["author_agent"] for a, b in pairs)


def test_fixture_note_kinds_cover_all_three():
    kinds = {note["kind"] for note in NOTES}
    assert kinds == BACKEND_NOTE_KINDS


def test_fixture_note_kinds_are_backend_valid():
    for note in NOTES:
        assert note["kind"] in BACKEND_NOTE_KINDS


def test_fixture_notes_reference_real_checkpoints():
    valid_keys = {cp["key"] for cp in MAIN_CHECKPOINTS} | {FORK_CHECKPOINT["key"]}
    for note in NOTES:
        assert note["checkpoint_key"] in valid_keys


def test_fixture_claim_intent_types_are_backend_valid():
    for claim in CLAIMS:
        assert claim["intent_type"] in BACKEND_INTENT_TYPES


def test_fixture_has_one_done_and_one_active_claim():
    statuses = {claim["final_status"] for claim in CLAIMS}
    assert statuses == {"done", "active"}


def test_fixture_demo_space_is_obviously_demo_data():
    assert DEMO_SPACE_NAME == "smriti-demo"
    assert DEMO_SPACE_DESCRIPTION.startswith("[DEMO]")
    assert DEMO_MARKER in DEMO_SPACE_DESCRIPTION


def test_fixture_fork_source_is_a_real_main_checkpoint():
    main_keys = {cp["key"] for cp in MAIN_CHECKPOINTS}
    assert FORK_CHECKPOINT["fork_from"] in main_keys


def test_fixture_branch_diverges_from_its_fork_source():
    """The explored branch must disagree with its source on at least one
    decision or assumption, so `smriti compare` shows a real divergence."""
    source = next(
        cp for cp in MAIN_CHECKPOINTS if cp["key"] == FORK_CHECKPOINT["fork_from"]
    )
    new_decisions = set(FORK_CHECKPOINT["decisions"]) - set(source["decisions"])
    new_assumptions = set(FORK_CHECKPOINT["assumptions"]) - set(source["assumptions"])
    assert new_decisions or new_assumptions


def test_fixture_tasks_are_well_formed():
    for cp in [*MAIN_CHECKPOINTS, FORK_CHECKPOINT]:
        for task in cp["tasks"]:
            assert {"id", "text", "intent_type", "status"} <= set(task)
            assert task["status"] in {"open", "done"}


def test_fixture_decisions_accumulate_down_the_main_chain():
    """Each main checkpoint carries the standing decisions forward — so the
    HEAD checkpoint (and `current`/`state`) shows the full picture."""
    seen = [len(cp["decisions"]) for cp in MAIN_CHECKPOINTS]
    assert seen == sorted(seen)
    assert seen[-1] >= 4


# ── seed_demo_space ──────────────────────────────────────────────────────────


def test_seed_demo_space_makes_expected_api_calls():
    client = _make_seed_client()
    seed_demo_space(client)

    client.create_space.assert_called_once()
    client.create_session.assert_called_once()
    # 4 main checkpoints + 1 on the explored branch
    assert client.create_chat_commit.call_count == 5
    client.fork_session.assert_called_once()
    client.close_branch.assert_called_once()
    assert client.add_checkpoint_note.call_count == 3
    assert client.create_claim.call_count == 2
    # exactly one claim is marked done; the other stays active
    client.update_claim.assert_called_once()


def test_seed_closes_the_explored_branch_as_abandoned():
    client = _make_seed_client()
    seed_demo_space(client)
    space_id, branch_name, disposition = client.close_branch.call_args[0]
    assert disposition == "abandoned"


def test_seed_marks_the_implement_claim_done():
    client = _make_seed_client()
    seed_demo_space(client)
    assert client.update_claim.call_args[0][1] == "done"


def test_seed_uses_a_long_ttl_so_active_work_stays_visible():
    client = _make_seed_client()
    seed_demo_space(client)
    for call in client.create_claim.call_args_list:
        assert call.kwargs["ttl_hours"] >= 168  # at least a week


def test_seed_returns_handles_for_every_checkpoint():
    client = _make_seed_client()
    result = seed_demo_space(client)
    assert result["space_id"] == "demo-space-id"
    expected = {cp["key"] for cp in MAIN_CHECKPOINTS} | {FORK_CHECKPOINT["key"]}
    assert set(result["checkpoints"]) == expected
    assert len(result["claims"]) == 2


def test_seed_rolls_back_a_half_built_space_on_failure():
    client = _make_seed_client()
    client.create_chat_commit.side_effect = SmritiError("backend exploded")
    with pytest.raises(SmritiError):
        seed_demo_space(client)
    # the partially-created space is removed so a retry starts clean
    client.delete_space.assert_called_once_with("demo-space-id")


# ── build_guide ──────────────────────────────────────────────────────────────


def test_build_guide_fills_in_real_checkpoint_ids():
    seed = {
        "space_id": "s",
        "checkpoints": {
            "frame": {"id": "c-frame"},
            "decide": {"id": "c-decide"},
            "ship": {"id": "c-ship"},
            "loadtest": {"id": "c-loadtest"},
            "redis-spike": {"id": "c-redis"},
        },
        "branch_name": "explore/redis-limiter",
        "claims": [],
    }
    guide = build_guide(seed)
    assert len(guide) == 5
    compare = next(s for s in guide if s["command"].startswith("smriti compare"))
    assert "c-decide" in compare["command"]
    assert "c-redis" in compare["command"]


# ── remove_demo_space ────────────────────────────────────────────────────────


def test_remove_deletes_a_marked_demo_space():
    client = MagicMock(spec=SmritiClient)
    client.resolve_space.return_value = {
        "id": "demo-space-id",
        "name": DEMO_SPACE_NAME,
        "description": DEMO_SPACE_DESCRIPTION,
    }
    result = remove_demo_space(client)
    assert result["removed"] is True
    client.delete_space.assert_called_once_with("demo-space-id")


def test_remove_refuses_a_space_without_the_demo_marker():
    """A real space that merely shares the smriti-demo name must survive."""
    client = MagicMock(spec=SmritiClient)
    client.resolve_space.return_value = {
        "id": "real-space-id",
        "name": DEMO_SPACE_NAME,
        "description": "My actual project. Do not delete.",
    }
    result = remove_demo_space(client)
    assert result["removed"] is False
    assert result["reason"] == "not-a-demo-space"
    client.delete_space.assert_not_called()


def test_remove_when_no_demo_space_exists():
    client = MagicMock(spec=SmritiClient)
    client.resolve_space.side_effect = SmritiError("no space found")
    result = remove_demo_space(client)
    assert result["removed"] is False
    assert result["reason"] == "no-demo-space"
    client.delete_space.assert_not_called()


def test_is_demo_space_only_true_for_marked_spaces():
    assert is_demo_space({"description": DEMO_SPACE_DESCRIPTION}) is True
    assert is_demo_space({"description": "something else"}) is False
    assert is_demo_space({}) is False


def test_find_demo_space_returns_none_when_absent():
    client = MagicMock(spec=SmritiClient)
    client.resolve_space.side_effect = SmritiError("not found")
    assert find_demo_space(client) is None


# ── cmd_quickstart ───────────────────────────────────────────────────────────


def test_cmd_quickstart_seeds_when_space_absent():
    client = _make_seed_client()
    client.resolve_space.side_effect = SmritiError("not found")
    cli_main.cmd_quickstart(client, _args())
    client.create_space.assert_called_once()


def test_cmd_quickstart_is_idempotent_when_space_present(capsys):
    client = MagicMock(spec=SmritiClient)
    client.base_url = "http://localhost:8000"
    client.list_spaces.return_value = []
    client.resolve_space.return_value = {
        "id": "demo-space-id",
        "name": DEMO_SPACE_NAME,
        "description": DEMO_SPACE_DESCRIPTION,
    }
    cli_main.cmd_quickstart(client, _args())
    client.create_space.assert_not_called()
    assert "already seeded" in capsys.readouterr().out


def test_cmd_quickstart_fails_cleanly_on_unreachable_backend(capsys):
    client = MagicMock(spec=SmritiClient)
    client.base_url = "http://localhost:8000"
    client.list_spaces.side_effect = SmritiError("connection refused")
    with pytest.raises(SystemExit):
        cli_main.cmd_quickstart(client, _args())
    err = capsys.readouterr().err
    assert "make dev-local" in err


def test_cmd_quickstart_remove_deletes_the_demo_space():
    client = MagicMock(spec=SmritiClient)
    client.base_url = "http://localhost:8000"
    client.list_spaces.return_value = []
    client.resolve_space.return_value = {
        "id": "demo-space-id",
        "name": DEMO_SPACE_NAME,
        "description": DEMO_SPACE_DESCRIPTION,
    }
    cli_main.cmd_quickstart(client, _args("--remove", "-y"))
    client.delete_space.assert_called_once_with("demo-space-id")


def test_cmd_quickstart_reset_removes_then_reseeds():
    client = _make_seed_client()
    # present on the first lookup (removal), absent on the second (seed)
    client.resolve_space.side_effect = [
        {
            "id": "old-demo-id",
            "name": DEMO_SPACE_NAME,
            "description": DEMO_SPACE_DESCRIPTION,
        },
        {
            "id": "old-demo-id",
            "name": DEMO_SPACE_NAME,
            "description": DEMO_SPACE_DESCRIPTION,
        },
        SmritiError("not found"),
    ]
    cli_main.cmd_quickstart(client, _args("--reset", "-y"))
    client.delete_space.assert_called_once_with("old-demo-id")
    client.create_space.assert_called_once()
