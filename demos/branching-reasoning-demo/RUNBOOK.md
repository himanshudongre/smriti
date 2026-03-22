# Runbook: Branching Reasoning Demo

Follow these steps in order. Each step references the exact messages in **DEMO_SCRIPT.md**.

---

## Prerequisites

- Backend running: `cd backend && uvicorn app.main:app --reload`
- Frontend running: `cd frontend && npm run dev`
- Browser open at `http://localhost:5173`
- Mock Mode enabled in the compose bar (no API key required for a deterministic demo)

---

## Phase 1 — Create the Space

1. In the left sidebar, click **New Space**.
2. Name it: `Research Agent Architecture`
3. Note the Space ID that appears in the URL (you will need it for forking).

---

## Phase 2 — Main branch thread (retrieval-heavy approach)

All messages are in **DEMO_SCRIPT.md → Section 1: Main Branch Thread**.

1. Paste **Turn 1** (scope setting). Send.
2. Paste **Turn 2** (retrieval-layer constraints). Send.
3. Paste **Turn 3** (enterprise deployment assumptions). Send.
4. Paste **Turn 4** (decision to use a vector index + reranker). Send.

After Turn 4, the conversation represents a concrete design decision: the team is committed to retrieval-augmented generation with a managed vector store.

---

## Phase 3 — Create Checkpoint A (main branch)

1. Click the **checkpoint** button (or press the keyboard shortcut) to open the commit dialog.
2. Use the draft button to auto-populate fields. Verify:
   - **Title:** something like "Commit: RAG architecture baseline"
   - **Objective:** long-term RAG-based research agent
   - **Decisions:** vector store chosen, reranker in pipeline, tool calls gated by retrieval confidence
   - **Branch:** main
3. Click **Save Checkpoint**.
4. Verify the checkpoint appears in the checkpoint history panel (left sidebar or panel toggle).

This is the fork point.

---

## Phase 4 — Fork the session from Checkpoint A

1. In the checkpoint history panel, click **Checkpoint A**.
2. Click **Fork from here**.
3. Name the branch: `state-first-reasoning`
4. The UI navigates to a new session in the same Space. The compose bar shows the FORKED chip with Checkpoint A's hash.
5. The empty state shows: *"Exploring alternate direction — Forked from \<hash\>"*

---

## Phase 5 — Fork branch thread (state-first approach)

All messages are in **DEMO_SCRIPT.md → Section 2: Fork Branch Thread**.

1. Paste **Fork Turn 1** (challenge retrieval-first assumption). Send.
2. Paste **Fork Turn 2** (advocate for explicit reasoning state). Send.
3. Paste **Fork Turn 3** (propose scratchpad + plan/act loop). Send.
4. Paste **Fork Turn 4** (address individual researcher use case). Send.

After Fork Turn 4, this branch represents a genuinely different design: no vector store, explicit reasoning state, lightweight deployment.

---

## Phase 6 — Create Checkpoint B (fork branch)

1. Click the **checkpoint** button.
2. Use the draft button to auto-populate. Verify:
   - **Title:** something like "Commit: State-first reasoning baseline"
   - **Objective:** individual-researcher, state-first autonomous agent
   - **Decisions:** no vector store, scratchpad-based reasoning, plan/act loop
   - **Branch:** state-first-reasoning (NOT main)
3. Click **Save Checkpoint**.

---

## Phase 7 — Show the diff

1. In the lineage/branch panel, both Checkpoint A (main) and Checkpoint B (state-first-reasoning) are visible.
2. Select Checkpoint A and Checkpoint B, then click **Compare**.
3. The diff view shows:
   - Decisions unique to A (retrieval, vector store, reranker)
   - Decisions unique to B (scratchpad, plan/act, no vector dependency)
   - Shared decisions (agent autonomy goal, tool-call interface)

See **EXPECTED_OUTCOMES.md** for the expected diff content.

---

## Phase 8 — Optional: return to main and continue

1. Click the main-branch session in the sidebar.
2. Checkpoint A is still the head of main. The fork branch made no changes to it.
3. Show that a new message on main creates a new checkpoint on main, independent of the fork.

---

## Cleanup

To reset the demo to a clean state, delete the Space from the sidebar. All sessions and checkpoints in that Space will be removed.
