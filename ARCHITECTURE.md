# Smriti — Architecture

This document describes the system model, the checkpoint isolation mechanism, the
provider abstraction, and the API versioning strategy. It is a reference for
contributors and for anyone who wants to understand why Smriti behaves the way it does.

---

## The Foundational Distinction: Event Stream vs. State Snapshot

Every AI conversation produces two fundamentally different kinds of data:

**Event stream** — the sequence of Turns. User sends a message; assistant replies.
Each Turn has a role, content, provider, model, and sequence number. The event stream
is append-only and never modified. It is the historical record of what was said.

**State snapshot (Checkpoint)** — a structured, immutable summary of what was
concluded at a specific point. It contains: title, objective, summary, decisions,
tasks, open questions, entities. Once saved, a Checkpoint never changes.

Most AI tools expose only the event stream. Smriti makes the state snapshot a
first-class, versioned object. This distinction is the architectural foundation of
everything else.

```
EVENT STREAM (turns)          STATE SNAPSHOTS (checkpoints)
─────────────────────         ──────────────────────────────
Turn 1  user                  Checkpoint A  ── title
Turn 2  assistant             (saved at        objective
Turn 3  user                   turn 8)         summary
Turn 4  assistant                              decisions[]
Turn 5  user                                   tasks[]
Turn 6  assistant                              open_questions[]
Turn 7  user                                   entities[]
Turn 8  assistant
  ↑ checkpoint created here   Checkpoint B  ── title
Turn 9  user                  (saved at        objective
Turn 10 assistant              turn 14)        summary
Turn 11 user                                   decisions[]
...                                            ...
```

A Checkpoint is not a transcript slice. It is not "turns 1–8 in summarized form."
It is a structured extraction of what was explicitly decided and understood —
extracted by the user (with optional AI drafting assistance), reviewed, and committed.
The extraction process has no access to anything outside the active conversation window.

---

## Data Model

### Space (RepoModel)

The long-lived container. Fields: `id`, `name`, `description`, `user_id`,
`created_at`, `updated_at`.

A Space holds many Checkpoints and many Sessions. It does not hold conversation
content directly; it is the namespace.

### Session (ChatSession)

The live chat runtime. Fields: `id`, `repo_id` (nullable), `title`,
`active_provider`, `active_model`, `seeded_commit_id`, `created_at`, `updated_at`.

`repo_id` — null if the Session is not attached to a Space (FRESH mode).

`seeded_commit_id` — the Checkpoint this Session was initialized from, if any.
Currently informational; not used as a hard isolation boundary by itself.

A Session is not bound to a provider. The `active_provider` and `active_model` fields
reflect the last provider used, but any Turn can be created with any configured
provider.

### Turn (TurnEvent)

The event stream record. Fields: `id`, `session_id`, `repo_id`, `role`, `content`,
`provider`, `model`, `sequence_number`, `created_at`.

`sequence_number` is assigned at write time, incrementing within the Session. It is
the key field used for checkpoint isolation (see below).

`role` is `"user"` or `"assistant"`. System-role Turns are filtered out of context
construction.

Turns are never deleted or updated.

### Checkpoint (CommitModel)

The state snapshot. Fields: `id`, `repo_id`, `commit_hash`, `parent_commit_id`,
`branch_name`, `message`, `objective`, `summary`, `decisions[]`, `tasks[]`,
`open_questions[]`, `entities[]`, `author_agent`, `metadata_`, `created_at`.

`commit_hash` — a SHA-256 derived from repo ID, message, and creation timestamp.
Stable identifier for display (first 7 characters shown in the UI).

`parent_commit_id` — links to the previous Checkpoint in the same Space. Forms an
implicit chain used for ancestor walking in `latest_3` scope mode.

`metadata_` — JSONB field; currently stores `session_id` of the Session that
created the Checkpoint. Reserved for future use (source Turn range, etc.).

---

## The Three Context Modes

When a message is sent, `send_message` determines what context to inject into the
prompt based on three variables:

1. Whether a Space is attached (`repo_id`)
2. Whether a specific Checkpoint is mounted (`mounted_checkpoint_id`)
3. The memory scope (`memory_scope`: `latest_1` or `latest_3`)

### FRESH

`repo_id` is null. No Checkpoint context. The prompt contains only the current user
message. The model has no prior structured state.

### HEAD

`repo_id` is set, `mounted_checkpoint_id` is null.

`_resolve_checkpoints()` fetches the N most recent Checkpoints from the Space
(`latest_1` → 1, `latest_3` → 3), ordered oldest-first.

Turn history filter: `TurnEvent.created_at >= latest_checkpoint.created_at`.
This passes Turns created since the most recent Checkpoint was saved — the
"work since last checkpoint" window.

### MOUNTED

`mounted_checkpoint_id` is set to a specific Checkpoint ID.

`_resolve_checkpoints()` uses `_walk_ancestors()` to build the chain: the mounted
Checkpoint plus up to N-1 ancestors via `parent_commit_id`, oldest-first.

Turn history filter: `TurnEvent.sequence_number > history_base_seq`.

`history_base_seq` is provided by the frontend and represents the `sequence_number`
of the last Turn that existed at the moment the user clicked Mount. Only Turns
created after that moment are included. This is the isolation mechanism.

---

## Checkpoint Isolation — The Mechanism

This is the most important behavioral guarantee in Smriti.

**The problem it solves:**

A user works in Session A, creates Checkpoint 1 (Australia trip), continues working,
creates Checkpoint 2 (Australia + New Zealand). Later, the user mounts Checkpoint 1
and asks a question. Without isolation, the Turn history filter `created_at >=
checkpoint1.created_at` would include all the New Zealand turns, because they were
created after Checkpoint 1 was saved. The model would see NZ context it should not.

**The solution:**

When the user clicks Mount in the UI, the frontend records:

```typescript
const mountedAtSeq = Math.max(...turns.map(t => t.sequence_number ?? 0));
```

This is the sequence number of the last Turn that existed before mounting. It is
passed as `history_base_seq` on every subsequent `send_message` call.

The backend applies:

```python
if payload.mounted_checkpoint_id is not None and payload.history_base_seq is not None:
    history_stmt = history_stmt.where(
        TurnEvent.sequence_number > payload.history_base_seq
    )
```

Effect: Turns 1–12 (pre-mount) are excluded. Only Turns 13+ (typed after mounting)
are included. The NZ conversation is turn 5–12 and does not enter the context.

**Why sequence number, not timestamp?**

Timestamps can have sub-second collisions and are harder to reason about precisely.
Sequence numbers are assigned by the backend at write time, monotonically increasing
within a session. `sequence_number > N` is an exact, collision-free boundary.

**Current limitation:**

The isolation is enforced within a single Session. Mounting Checkpoint 1 in Session A
uses Turns from Session A only (filtered by sequence boundary). This is correct
behavior. A future improvement (v5.3) will support true session forking: mounting a
Checkpoint creates a new Session with a clean Turn history, making the isolation
architecturally complete rather than boundary-based.

**The same isolation applies to Draft with AI:**

`draft_checkpoint` in `checkpoint.py` uses the same `_fetch_turns_for_draft()`
function that applies the identical `sequence_number > history_base_seq` filter.
A Checkpoint draft created while in MOUNTED mode sees only the same Turn window
as the chat session does. The two are consistent.

---

## Context Construction

When `send_message` is called, the prompt is built by `build_prompt_from_checkpoints()`:

```
You are continuing a conversation.

Checkpoint [N] Summary:
<checkpoint.summary>

Checkpoint [N] Key Decisions:
- <decision>
...

Checkpoint [N] Open Tasks:
- <task>
...

Recent Conversation:
User: <turn content>
Assistant: <turn content>
...

User Query:
<current message>
```

The prompt does not pass raw Turn content for Turns before the isolation boundary.
It passes structured Checkpoint fields (summary, decisions, tasks) for context, then
only the post-boundary Turn history as conversational context.

This is a deliberate design: the model receives structured facts, not a raw log dump.
Noise in the event stream does not reach the model — only what was explicitly
crystallized into a Checkpoint.

---

## Draft with AI — Extraction Quality

The `draft_checkpoint` endpoint (`POST /api/v5/checkpoint/draft`) calls the
background intelligence model with a single extraction prompt. Key design constraints:

**No prior context injection.** The prompt contains only the current conversation
transcript. No previous Checkpoint's decisions, tasks, or summary are injected. This
prevents cross-session contamination — a real failure mode where old product decisions
(e.g. "Use Postgres") appeared in travel planning checkpoints because they were in the
prior HEAD Checkpoint's fields.

**Extract only, do not infer.** The prompt explicitly instructs: "Extract ONLY what is
discussed or decided in this conversation. Do NOT infer, hallucinate, or carry over
content from any other context. If a field has nothing relevant, return an empty array."

**Decisions field semantics.** The prompt defines decisions as "explicit choices made
in the conversation, not hypothetical ones." This reduces false positives.

**Replace, not merge.** Each Draft with AI call replaces all form fields. There is
no accumulation of previous drafts. The user sees a fresh extraction on every call.

---

## Provider Abstraction

All LLM calls go through a common adapter interface defined in
`backend/app/providers/registry.py`. Each provider (OpenAI, Anthropic, OpenRouter)
implements `send(messages, model, **kwargs) -> str`.

OpenRouter uses the OpenAI SDK with a custom `base_url`. Anthropic uses the Anthropic
SDK. The adapter normalizes the message format and error handling.

The abstraction has two important properties:

1. **The session does not depend on the provider.** Turns are stored by Smriti, not
   by the provider. Switching from OpenAI to Anthropic mid-session loses nothing.
   The next request reconstructs the context prompt from Smriti's Turn and Checkpoint
   records, the same way it would for any provider.

2. **Background intelligence is a separate slot.** The model used for Draft with AI
   and session auto-titling is configured independently in `background_intelligence`
   in `providers.yaml`. It does not have to be the same provider the user is chatting
   with. This allows a cheap, fast model (e.g. `gpt-4o-mini`) for extraction tasks
   while the user interacts with a more capable model for reasoning.

---

## API Versioning

The backend API has multiple version prefixes. Each represents a product-generation
pivot, not an incremental change.

| Prefix | Status | Purpose |
|---|---|---|
| `/api/v1` | Legacy | Transcript paste ingestion → session/artifact pipeline. Not part of current workflow. |
| `/api/v2` | Legacy | Agent-push model: repos, commits, context packs. Direct API-to-API handoff. Not part of current UI workflow. |
| `/api/v4` | Current | Chat sessions, message sending, provider management. The primary API. |
| `/api/v5` | Current | Checkpoint drafting. Isolated from chat API by design. |

V1 and V2 endpoints remain registered for compatibility. They are not used by the
current frontend. New development targets V4 and V5 exclusively.

The split between V4 and V5 is intentional: checkpoint operations (which involve a
background LLM call and structured extraction) are separated from the real-time chat
path. This allows different latency budgets and error handling strategies for each.

---

## Frontend State Management

The frontend manages three pieces of state relevant to checkpoint isolation:

```typescript
const [mountedCheckpointId, setMountedCheckpointId] = useState<string | null>(null);
const [mountedAtSeq, setMountedAtSeq] = useState<number | null>(null);
const [memoryScope, setMemoryScope] = useState<MemoryScope>('latest_1');
```

`mountedCheckpointId` — the ID of the currently mounted Checkpoint, or null.

`mountedAtSeq` — the sequence number of the last Turn at the moment of mounting.
Set when Mount is clicked; cleared when Unmount is clicked or the Space changes.

`memoryScope` — `'latest_1'` or `'latest_3'`. Selected in the Attach Space modal.
Controls ancestor walking depth in `_resolve_checkpoints()`.

Every `sendChatMessage` call passes all three values. The backend uses them to
determine which context mode applies and which Turns to include.

The UI displays the active context mode in two places:
- The thread header badge: `FRESH` / `HEAD · <hash>` / `MOUNTED · <hash>`
- The composer status line: `ctx: <mode> (description)`

These are always in sync with the actual context being sent to the backend.

---

## What Is Not Yet In the Architecture

**Source Turn range on Checkpoints.** There is no record of which Turn range produced
a given Checkpoint. The `metadata_` JSONB field on `CommitModel` is the intended
storage location. This would allow "show me the conversation that produced this
Checkpoint" — a useful debugging and audit feature.

**Streaming.** All provider calls are synchronous request/response. The adapter
interface does not yet support streaming. Each Turn waits for the full response.

**Checkpoint merging.** The lineage graph can represent divergent branches but there
is no operation to merge two Checkpoint lines back together. Merging structured fields
(decisions, tasks) is mechanically possible; the semantics of merging reasoning intent
are not yet defined.

**Authentication and multi-user.** All Spaces currently belong to a single demo user
(`DEMO_USER_ID`). There is no authentication layer, no user registration, and no
per-user isolation.
