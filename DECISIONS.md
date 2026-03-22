# Smriti — Key Decisions

This document records significant architectural and product decisions and the
reasoning behind them. It is not a changelog; it covers choices that might otherwise
be revisited or questioned without this context.

---

## Product decisions

### Why version-control semantics, not a memory database

Early versions of Smriti were built around extracting "memories" from transcripts and
storing them in a retrievable database. This proved wrong for several reasons:

- Memories extracted from text are ambiguous and often incorrect
- Retrieval-based systems require the user to trust the retrieval quality — an
  invisible black box
- There is no notion of "state at a point in time" — you cannot ask what you knew
  at a specific moment and get a reliable answer

The version-control model is fundamentally different: it requires the user to
explicitly create a Checkpoint at a meaningful point. The state is user-defined, not
inferred. The history is deterministic and inspectable. You can return to any
Checkpoint and know exactly what context the model will receive.

The tradeoff is deliberate friction: Checkpoints are not automatic. This is correct.
Automatic snapshotting produces noise. Signal requires judgment.

### Why separation of chat and checkpoint as distinct concerns

The V4 API handles sessions and message sending. The V5 API handles checkpoint
drafting. These are separate for good reason: checkpoint drafting involves a
background LLM call with different latency, error handling, and reliability
requirements than real-time chat. Keeping them in separate route modules and API
version prefixes makes this boundary explicit.

### Why Spaces are user-facing but Repos internally

The codebase uses `RepoModel`, `repo_id`, and `/repos` in the database and API.
The UI and all user-facing text uses "Space." This is not a naming inconsistency —
it is a deliberate translation. "Repo" is accurate internally (it is Git-inspired)
but confusing to users who may think it refers to a code repository. "Space" is
neutral and descriptive: a named container for a line of work.

When reading the code: `repo` = `Space` in user-facing terms.

### Why checkpoints are called "Checkpoints" not "Commits"

"Commit" is accurate in the Git analogy and is used throughout the codebase
(`CommitModel`, `commit_hash`, `parent_commit_id`). In user-facing text, "Checkpoint"
is preferred because:

- It implies a deliberate save point, not a routine code commit
- It does not suggest branching/merging is available (it is not yet)
- It maps more intuitively to the actual usage: "I'm at a good stopping point, let
  me save my state"

### Why the name Smriti

Smriti (स्मृति) means memory in Sanskrit. It is short, meaningful, and directly
describes the product's intent. The name was chosen before the product's mental model
shifted from "memory storage" to "versioned state" — but remains appropriate because
the core promise is still about preserving and recovering structured knowledge.

---

## Architectural decisions

### Why checkpoint isolation uses sequence numbers, not timestamps

The isolation boundary — which Turns to include when a specific Checkpoint is mounted
— is enforced by `sequence_number > history_base_seq`, not by a timestamp comparison.

Timestamps can have sub-millisecond collisions. Sequence numbers are assigned
monotonically within a Session at write time. `sequence_number > N` is an exact,
collision-free predicate. This matters because the boundary must be reliable: a
single Turn that should have been excluded contaminating the context is a trust failure.

### Why history_base_seq is frontend-owned

`history_base_seq` is computed by the frontend (the max `sequence_number` of existing
Turns at mount time) and passed on every `send_message` request. It is not stored in
the database on the Session or Checkpoint.

Alternative considered: store the boundary on the Session when mounting. This was
rejected because:
- Mounting is a UI concept, not a persistent session state change (in v5.2)
- The same Session can be unmounted and remounted to different Checkpoints without
  a database write
- The frontend always has the Turn list and can compute the boundary locally

The tradeoff: if the frontend sends an incorrect `history_base_seq`, the isolation
is wrong. This is acceptable for v5.2; v5.3 will address this by forking a new Session
on mount, making the isolation structural.

### Why Draft with AI does not inject prior checkpoint context

Earlier versions of the checkpoint draft prompt injected the HEAD Checkpoint's
decisions and tasks as "prior context" for the extraction. This caused contamination:
decisions from a previous, unrelated line of work would appear in the draft for a
new topic (e.g. "Use Postgres" appearing in a travel planning checkpoint).

The current design: the extraction prompt contains only the current conversation
Turns. The LLM is instructed to extract only what is explicitly present. No prior
state is injected. This produces accurate extractions at the cost of losing
"continuity awareness" in the extraction — but that continuity is already captured
in the Checkpoint fields that the user saves and can reference.

### Why provider switching does not create a new session

When a user switches from OpenAI to Anthropic mid-session, Smriti does not fork the
Session. The same `session_id` continues. The new provider receives the same
Checkpoint context and Turn history as the previous provider would have.

This is correct behavior. The provider is a rendering engine, not a state owner.
Smriti owns the state. The fact that Claude and GPT-4o have different internal session
concepts is irrelevant; their sessions are not used. Smriti reconstructs the context
from its own records on every `send_message` call.

### Why transcript ingestion is a legacy feature

V1 of Smriti was built around pasting a transcript from one tool and generating a
"context pack" to paste into another. This workflow was the initial wedge but proved
limited:

- Paste-based ingestion is friction-heavy
- Transcript quality is highly variable
- The extracted "context pack" was text, not structured state
- There was no versioning, no isolation, no "go back to this point"

The V4+ model replaced this: Smriti is the workspace, not a bridge between workspaces.
Users work inside Smriti directly, and the structured state lives there.

The V1 endpoints remain registered and functional for backfill use cases. They are
not part of the current UI and are not under active development.

### Why there is no automatic checkpointing

The system could detect decision keywords, count turns, or use a background model
to decide when to auto-create a Checkpoint. This was considered and rejected:

- Automatic state snapshots have unclear semantics — the user did not define them
- They produce noise in the Checkpoint history, making the history less trustworthy
- The value of a Checkpoint comes from it representing a human judgment about
  significance, not a system heuristic

The current recommendation signal (a subtle "consider checkpointing" indicator after
a significant turn count or keyword detection) is present as a nudge, not an action.

---

## Open questions and deferred decisions

- **Multi-user Spaces** — deferred. No auth, no user model.
- **Checkpoint merging** — combining state from two divergent Checkpoint lines is
  not yet defined. The semantics are unclear: merging structured fields (decisions,
  tasks) is mechanical; merging reasoning intent is not.
- **Source Turn range on Checkpoints** — there is no record of which Turn range
  produced a given Checkpoint. The `metadata_` JSONB field is the intended storage
  location once the use case is validated.
- **Streaming** — the adapter interface does not yet support streaming. All provider
  calls are synchronous request/response.
