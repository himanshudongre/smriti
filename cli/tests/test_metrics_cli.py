from __future__ import annotations

from smriti_cli.formatters import format_metrics


def test_format_metrics_omits_empty_agent_distribution():
    out = format_metrics({
        "space_name": "empty",
        "coordination": {
            "total_checkpoints": 0,
            "unique_agents": 0,
            "agent_checkpoints": {},
        },
        "state_quality": {},
        "branches": {},
    })

    assert "0 checkpoints · 0 agents\n" in out
    assert "0 agents ()" not in out
    assert "0 claims · 0 resolved · 0 unresolved · 0 with task IDs" in out


def test_format_metrics_names_checkpoint_task_counts():
    out = format_metrics({
        "space_name": "demo",
        "coordination": {},
        "state_quality": {
            "checkpoints_with_structured_tasks": 5,
            "checkpoints_with_task_ids": 5,
        },
        "branches": {},
    })

    assert "5 checkpoints with structured tasks · 5 checkpoints with task IDs" in out


def test_format_metrics_claim_completion_names_resolved_denominator():
    out = format_metrics({
        "space_name": "claims",
        "coordination": {
            "total_claims": 3,
            "claims_done": 2,
            "claims_abandoned": 0,
            "claims_unresolved": 1,
            "claim_completion_rate": 1.0,
            "claims_with_task_id": 2,
        },
        "state_quality": {},
        "branches": {},
    })

    assert "3 claims · 2 resolved (100% done) · 1 unresolved · 2 with task IDs" in out
    assert "100% completion" not in out
