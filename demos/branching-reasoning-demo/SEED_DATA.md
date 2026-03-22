# Seed Data

This file documents the Space configuration and pre-seeded checkpoint structure used in the demo. It is not required for a live demo run — the demo builds the checkpoints from scratch during the session. Use this file if you want to pre-load a known-good state via the API or for automated testing.

---

## Space configuration

| Field | Value |
|---|---|
| Name | `Research Agent Architecture` |
| Branch (default) | `main` |
| User | Demo user (`00000000-0000-0000-0000-00000000000a`) |

---

## Checkpoint A (main branch baseline)

Create via `POST /api/v4/chat/commit`:

```json
{
  "repo_id": "<space_id>",
  "session_id": "<main_session_id>",
  "message": "RAG architecture baseline",
  "summary": "Team commits to a two-stage retrieval pipeline: vector index for coarse candidate retrieval, cross-encoder reranker for precision. All models run locally. Tool calls from the agent are gated by retrieval confidence scores. Audit trail required per retrieval decision.",
  "objective": "Build an enterprise-grade autonomous research agent with sub-second retrieval over a 2M-document corpus, deployed on-premises with data residency and audit requirements.",
  "decisions": [
    "Two-stage retrieval: vector index → cross-encoder reranker",
    "All embedding and reranking models run locally / private cloud",
    "Agent tool calls gated by retrieval confidence score threshold",
    "Audit trail for every retrieval decision",
    "Indexing pipeline handles daily incremental updates"
  ],
  "tasks": [
    "Benchmark local cross-encoder reranker latency under load",
    "Define confidence threshold policy for tool-call gating",
    "Design audit log schema"
  ],
  "open_questions": [
    "What confidence threshold to use for gating tool calls?",
    "How to handle retrieval failures gracefully?",
    "Cross-encoder reranker latency under peak load?"
  ],
  "entities": [
    "vector index", "cross-encoder reranker", "retrieval confidence", "audit trail", "on-premises deployment"
  ]
}
```

---

## Fork session (from Checkpoint A)

Create via `POST /api/v5/lineage/sessions/fork`:

```json
{
  "space_id": "<space_id>",
  "checkpoint_id": "<checkpoint_a_id>",
  "branch_name": "state-first-reasoning",
  "provider": "mock",
  "model": "mock"
}
```

---

## Checkpoint B (state-first-reasoning branch)

Create via `POST /api/v4/chat/commit` using the fork session ID:

```json
{
  "repo_id": "<space_id>",
  "session_id": "<fork_session_id>",
  "message": "State-first reasoning baseline",
  "summary": "Individual researcher variant: no vector index, scratchpad-based reasoning as first-class state, plan/act loop, fully local deployment on SQLite or file system. Optimised for 10k-100k document corpora on a laptop.",
  "objective": "Build a lightweight autonomous research agent for individual researchers: local deployment, transparent reasoning, no external services.",
  "decisions": [
    "Scratchpad-based reasoning: persistent, explicit reasoning state across turns",
    "Plan/act loop: agent explicitly plans next step before acting",
    "No vector index — SQLite or file system for document storage",
    "Fully local, no external service dependencies",
    "Reasoning chain is first-class and researcher-auditable"
  ],
  "tasks": [
    "Design scratchpad schema for multi-day research sessions",
    "Define upgrade path when corpus outgrows SQLite",
    "Prototype plan/act loop with simple document store"
  ],
  "open_questions": [
    "How to structure the scratchpad for long multi-day sessions?",
    "When does the corpus outgrow SQLite?",
    "How to handle conflicting evidence in the scratchpad?"
  ],
  "entities": [
    "scratchpad", "plan/act loop", "SQLite", "local deployment", "reasoning state"
  ]
}
```

---

## Notes

- The `parent_commit_id` of Checkpoint B will be set automatically by the backend to Checkpoint A's ID (because the fork session's `forked_from_checkpoint_id` points to Checkpoint A and there are no prior fork-local commits).
- `branch_name` of Checkpoint B will be `state-first-reasoning`, confirming branch-local semantics are working.
- The reachable checkpoint set for the fork session should return Checkpoint B (fork-local) + Checkpoint A (fork source) only — not any subsequent main-branch commits.
