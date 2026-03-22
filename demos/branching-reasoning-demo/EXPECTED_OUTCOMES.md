# Expected Outcomes

Use this as a checklist when running or validating the demo. If any outcome is missing or wrong, re-check the corresponding step in RUNBOOK.md.

---

## Checkpoint A (main branch — retrieval-heavy)

**Branch:** `main`

**Objective:** Build an enterprise-grade autonomous research agent with sub-second retrieval over a 2M-document corpus, deployed on-premises with data residency and audit requirements.

**Expected decisions (at least these, possibly more):**
- Two-stage retrieval: vector index (coarse) → cross-encoder reranker (precision)
- All embedding and reranking models run locally / private cloud
- Agent tool calls gated by retrieval confidence score threshold
- Audit trail for every retrieval decision (required by enterprise compliance)
- Indexing pipeline handles daily incremental updates at scale

**Expected open questions:**
- What confidence threshold to use for gating tool calls?
- How to handle retrieval failures gracefully (fallback strategy)?
- Cross-encoder reranker latency under peak load?

---

## Checkpoint B (state-first-reasoning branch)

**Branch:** `state-first-reasoning`

**Objective:** Build a lightweight autonomous research agent for individual researchers: local deployment, transparent reasoning, no external services, handles 10k–100k documents without a dedicated index server.

**Expected decisions (at least these, possibly more):**
- Scratchpad-based reasoning: persistent, explicit reasoning state across turns
- Plan/act loop: agent explicitly plans next step, acts, then updates scratchpad
- No vector index: file system or SQLite for document storage at this scale
- No external API dependencies — fully local
- Reasoning chain is first-class, inspectable, and auditable by the researcher

**Expected open questions:**
- How to structure the scratchpad for long multi-day research sessions?
- When does the corpus outgrow SQLite and require an upgrade path?
- How to handle conflicting evidence across documents in the scratchpad?

---

## Checkpoint comparison diff

When comparing Checkpoint A vs Checkpoint B, the diff should show:

### Decisions only in A (retrieval-heavy):
- Vector index for coarse candidate retrieval
- Cross-encoder reranker for precision retrieval
- Retrieval confidence score gating for tool calls
- On-premises / private cloud model deployment
- Audit trail per retrieval decision

### Decisions only in B (state-first):
- Scratchpad as first-class reasoning state
- Plan/act loop with explicit next-step planning
- No vector index — SQLite or file system storage
- Fully local, no external service dependencies
- Researcher-auditable reasoning chain

### Decisions shared by both:
- Agent autonomy goal (multi-hop reasoning over document corpus)
- Tool-call interface pattern (agent decides when to retrieve)
- Transparency/auditability requirement (different mechanism, shared goal)

---

## UI checkpoints

| What to verify | Expected state |
|---|---|
| Checkpoint A branch field | `main` |
| Checkpoint B branch field | `state-first-reasoning` |
| Fork session empty state | "Exploring alternate direction — Forked from \<hash\>" |
| Checkpoint history panel in fork session | Shows Checkpoint A + ancestors only (not downstream main commits) |
| Compose bar mock toggle label | "Mock Mode" / "Mock Mode Active" (not "Demo Mode") |
| Branch chip in fork session | Shows `state-first-reasoning`, clickable, opens history panel |
| FORKED chip | Clickable, shows Checkpoint A hash, opens history panel on click |

---

## What a broken demo looks like

| Symptom | Likely cause |
|---|---|
| Checkpoint B appears on `main` branch | Session `branch_name` not set correctly on fork creation |
| Fork checkpoint panel shows main-branch downstream commits | Reachable checkpoint query not using branch-local semantics |
| Draft for Checkpoint B mentions enterprise/RAG decisions | Draft not isolating fork turns (fetching all turns instead of fork-local) |
| FORKED chip is not clickable | Frontend still rendering FORKED as `<span>` not `<button>` |
| Empty state shows "Start a new conversation" in fork | Empty state not checking `forked_from_checkpoint_id` |
