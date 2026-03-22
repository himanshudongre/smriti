# Talk Track: Branching Reasoning Demo

This is the presenter narrative. It covers what to say at each stage of the demo and includes suggested responses to common audience questions.

---

## Opening (30 seconds)

> "I want to show you a problem that comes up in every architectural design conversation.
>
> You're debating two approaches. You explore the first one for 20 minutes — you make decisions, you surface tradeoffs, you get somewhere real. Then someone says 'what if we tried the other approach?' So you explore that too.
>
> Normally, one of those threads disappears. It gets lost in a Slack thread, summarised badly into a doc, or just forgotten because you ran out of time. Smriti keeps both — as first-class, checkpointed, comparable artifacts.
>
> Let me show you."

---

## Phase 1–3: Main branch thread (2 minutes)

*Send turns 1–4 from the demo script. While the AI is responding:*

> "We're designing an autonomous research agent. The team has been working toward an enterprise deployment — large corpus, strict data residency, sub-second retrieval. We've been talking through a RAG architecture: vector index, reranker, confidence-gated tool calls."

*After Turn 4:*

> "At this point, the team has made real decisions. Not hypothetical — actual constraints and choices that affect the whole pipeline. We're going to checkpoint this."

*Create Checkpoint A.*

> "This is Checkpoint A. It's a snapshot of the conversation state — not just the messages, but the structured decisions, open questions, and objective extracted from the thread. It lives on the main branch."

---

## Phase 4: Fork (30 seconds)

*Click Fork from Checkpoint A.*

> "Now here's where it gets interesting. Someone on the team says: 'This enterprise RAG architecture is right for our platform — but what if you're an individual researcher with a 10,000-paper corpus on your laptop? Does the same architecture make sense?'
>
> We fork from exactly this checkpoint. The fork inherits everything that happened before — all the decisions, all the context — but from here, it develops its own thread independently."

*Point to the FORKED chip and branch name.*

> "Notice: we're still in the same Space. The fork didn't create a new project. It branched from a specific moment in the conversation."

---

## Phase 5–6: Fork branch thread (2 minutes)

*Send fork turns 1–4. While responding:*

> "The individual-researcher path looks very different. No vector index — SQLite or even a file system is fine at this scale. The design priority shifts from retrieval speed to reasoning quality. The scratchpad — the agent's explicit reasoning state — becomes first-class."

*After Fork Turn 4, create Checkpoint B.*

> "Checkpoint B. Same space, different branch. These two design paths are now both preserved, structured, and queryable."

---

## Phase 7: Show the diff (1 minute)

*Open the compare view for Checkpoint A vs Checkpoint B.*

> "This is what I want to show you. These two checkpoints started from the same conversation. They share the same goal — building a useful research agent. But their decisions diverged.
>
> Decisions unique to the enterprise RAG branch: vector index, reranker, confidence gating, audit trails, on-premises model hosting.
>
> Decisions unique to the individual-researcher branch: scratchpad reasoning state, plan/act loop, no vector dependency, fully local.
>
> Shared: the agent autonomy goal, the tool-call interface, the transparency requirement.
>
> Normally this comparison lives nowhere. It's in someone's head, or it's a retrospective doc that nobody reads. Here it's a structured artifact — generated from the actual reasoning thread, queryable, forkable again."

---

## Phase 8: The proposition (30 seconds)

> "You can now mount either checkpoint into a new session. You can fork from either branch. You can compare any two checkpoints in the space — including checkpoints from sessions that happened weeks apart.
>
> The branching-reasoning paradigm that Smriti is built around says: the reasoning process is as valuable as the outcome. Capturing it in a way that's structured and navigable is what lets you build on it rather than restart from scratch."

---

## Common audience questions

**Q: Can you merge the two branches?**

> "Not in the code-merge sense — these are reasoning threads, not code diffs. But you can fork from either branch's checkpoint and start a new session that synthesises both. You'd explicitly bring in the decisions you want to carry forward. That synthesis session is itself checkpointed and forkable."

**Q: What if I want to continue the main branch after the fork?**

> "Go back to the main-branch session — it still has Checkpoint A as its head. Send a new message, create a new checkpoint — that checkpoint lands on main, independent of anything that happened on the fork branch. Neither branch pollutes the other."

**Q: How does the AI know what context to use in each branch?**

> "For the fork session, the AI's context starts from the checkpoint snapshot — the structured state we saved at fork time — not from the raw message history. So it doesn't see anything that happened on main after the fork. The context is branch-local. That's what keeps the branches clean."

**Q: Does this work with real AI providers, not just Mock Mode?**

> "Yes. Mock Mode is for demos without an API key — it gives deterministic responses. With a real provider, you get actual reasoning, which is even more compelling. The checkpointing and branching work identically either way."

**Q: What's the cost of a fork?**

> "It's a database row. The session is created instantly. The checkpoint context is the snapshot we already have — we don't re-run anything. Forking is cheap enough that you can do it speculatively — try a direction, see where it leads, discard it or keep it."
