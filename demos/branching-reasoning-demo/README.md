# Demo: Choosing the Architecture for an Autonomous Research Agent

**Theme:** A team is designing an autonomous research agent. The main branch represents the enterprise/retrieval-heavy path the team has been building toward. A fork explores an alternative: an individual-researcher-oriented, state-first, branching-reasoning architecture.

**What this demo shows:**

1. Smriti tracks a multi-turn architecture conversation as a persistent, checkpointed thread.
2. A single checkpoint creates a genuine branch point — the fork inherits all prior context but accumulates its own reasoning independently.
3. Both branches remain live in the same Space; neither overwrites the other.
4. At any point, either branch's checkpoint can be compared, mounted, or used as a new fork source.
5. The branching-reasoning approach produces visibly different decisions and open questions from the retrieval-heavy approach — giving the team a concrete, structured diff rather than a lost Slack thread.

---

## Repo layout

```
demos/branching-reasoning-demo/
├── README.md           ← this file
├── RUNBOOK.md          ← step-by-step demo execution guide
├── DEMO_SCRIPT.md      ← exact messages to paste for each turn
├── EXPECTED_OUTCOMES.md← what checkpoints and diffs should look like when done correctly
├── SEED_DATA.md        ← Space/repo setup and pre-seeded checkpoint data
└── TALK_TRACK.md       ← presenter narrative and audience Q&A guide
```

---

## Quick-start (5 minutes)

1. Start the backend: `cd backend && uvicorn app.main:app --reload`
2. Start the frontend: `cd frontend && npm run dev`
3. Follow **RUNBOOK.md** to create the Space, run the main-branch thread, create Checkpoint A, fork, run the fork thread, and create Checkpoint B.
4. Use **DEMO_SCRIPT.md** to paste the exact messages so the demo is reproducible.
5. Refer to **EXPECTED_OUTCOMES.md** to validate the diff looks right.
6. Use **TALK_TRACK.md** for the presenter narrative.

---

## Core demo proposition

> "These two branches started from the same conversation. Neither was deleted, summarised into a doc, or lost in Slack. Smriti captured exactly where they diverged, what each branch decided, and what questions each left open. You can compare them right now."
