# Demo Script: Exact Messages

Paste these messages verbatim during the demo. They are written to produce consistent, structured AI responses that look good in the checkpoint diff.

If you are using **Mock Mode**, responses will be deterministic simulated outputs. If you are using a real provider, responses will vary but the structure of the conversation will still work.

---

## Section 1: Main Branch Thread (Retrieval-Heavy / Enterprise)

### Turn 1 — Scope setting

```
We're designing an autonomous research agent for an enterprise knowledge management platform. The agent needs to answer deep analytical questions by searching across a corpus of internal documents, research papers, and structured data. What are the key architectural decisions we need to make upfront?
```

### Turn 2 — Retrieval-layer constraints

```
Our corpus is large — roughly 2 million documents, updated daily. We need sub-second retrieval latency even for complex multi-hop queries. What retrieval architecture should we use, and how does it affect our indexing pipeline design?
```

### Turn 3 — Enterprise deployment assumptions

```
The platform is deployed on-premises with strict data residency requirements. We can't use external embedding APIs — all models need to run locally or in our private cloud. We also need audit trails for every retrieval decision. How does this constrain the design?
```

### Turn 4 — Decision point: commit to RAG with vector index + reranker

```
Based on what we've discussed: we're going with a two-stage retrieval pipeline — a vector index for coarse candidate retrieval, followed by a cross-encoder reranker for precision. Tool calls from the agent are gated by retrieval confidence scores. Does this architecture have any critical failure modes we should document now?
```

**→ After this turn, create Checkpoint A on main branch.**

---

## Section 2: Fork Branch Thread (State-First / Individual Researcher)

*(Fork from Checkpoint A before starting this section)*

### Fork Turn 1 — Challenge the retrieval-first assumption

```
I want to step back and challenge the retrieval-first assumption we just committed to on the main branch. For an individual researcher working with a smaller, more curated corpus — maybe 10,000 papers in their domain — a heavy vector indexing pipeline seems like overkill. What's the alternative architectural paradigm?
```

### Fork Turn 2 — Advocate for explicit reasoning state

```
The thing I keep coming back to is that the most valuable part of a research agent isn't fast retrieval — it's the quality of the reasoning chain. If we make the agent's reasoning state first-class — explicit, persistent, and inspectable — we get better science even if retrieval is slower. What does an architecture built around reasoning state look like?
```

### Fork Turn 3 — Propose scratchpad + plan/act loop

```
I'm thinking of a scratchpad architecture: the agent maintains a persistent reasoning scratchpad across turns, plans its next retrieval or synthesis step explicitly, acts, then updates the scratchpad. The corpus can be a simple file system or SQLite — no vector index needed for this scale. What does the plan/act loop look like, and what are the tradeoffs vs the RAG approach?
```

### Fork Turn 4 — Address individual researcher use case

```
For an individual researcher, the key requirements are: runs locally on a laptop, no external services, reasoning is transparent and auditable, can handle 10k-100k documents without a dedicated index server. Summarise the final architecture for this use case and list the decisions we've made that differ from the enterprise RAG approach.
```

**→ After this turn, create Checkpoint B on the state-first-reasoning branch.**
