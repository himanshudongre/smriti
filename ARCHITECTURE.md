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
`branch_name`, `message`, `objective`, `summary`, `decisions[]`, `assumptions[]`,
`tasks[]`, `open_questions[]`, `entities[]`, `artifacts[]`, `author_agent`,
`metadata_`, `created_at`.

`assumptions` — things the reasoning takes for granted, tracked separately from
explicit decisions. Used by checkpoint review to surface hidden dependencies.

`artifacts` — attached text content (code snippets, plans, outputs). Stored as JSONB
array of `{id, type, label, content}` objects. Included in prompt context when the
checkpoint is active, capped at 2000 characters per artifact.

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

### RESTORED (internally: MOUNTED)

`mounted_checkpoint_id` is set to a specific Checkpoint ID. The UI labels this
"RESTORED STATE" to communicate that the user has returned to a clean checkpoint.

`_resolve_checkpoints()` uses `_walk_ancestors()` to build the chain: the restored
Checkpoint plus up to N-1 ancestors via `parent_commit_id`, oldest-first.

Turn history filter: `TurnEvent.sequence_number > history_base_seq`.

`history_base_seq` is provided by the frontend and represents the `sequence_number`
of the last Turn that existed at the moment the user clicked Restore. Only Turns
created after that moment are included. This is the isolation mechanism.

Pre-restore Turns are visually dimmed in the UI and a boundary divider marks the
transition. The model's context contains only the checkpoint state plus post-restore
messages.

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
| `/api/v2` | Partial | Space CRUD, checkpoint read by ID, checkpoint list by space. `CommitResponse` includes `assumptions` and `artifacts` so programmatic clients (CLI, agents) can read full checkpoints via this surface. |
| `/api/v4` | Current | Chat sessions, message sending, provider management. The primary chat API. Also the canonical checkpoint write path (`POST /chat/commit`) because it accepts the full schema including `assumptions` and `artifacts`. Multi-branch continuation brief served from `GET /chat/spaces/{id}/state` — the agent-facing default; `GET /chat/spaces/{id}/head` remains as the main-only legacy endpoint. |
| `/api/v5` | Current | Checkpoint drafting, review, fork, compare, lineage. Isolated from chat API by design. |

V1 remains registered for compatibility but is not used by the frontend or CLI.

The split between V4 and V5 is intentional: checkpoint operations (which involve a
background LLM call and structured extraction) are separated from the real-time chat
path. This allows different latency budgets and error handling strategies for each.

---

## Smriti as an agent-facing backend

The REST API is the canonical interface to Smriti. The chat UI, the CLI, the
MCP server, and the agent skill pack are all surfaces over the same model.
Nothing in the core (checkpoints, assumptions, decisions, artifacts, fork,
compare, review, extract) is specific to one surface.

The four surfaces fall into two categories:

- **Runtime surfaces** (CLI, MCP server, chat UI) — how an agent or human
  *calls* Smriti. These are the HTTP clients talking to the same backend.
- **Onboarding surface** (skill pack) — how an agent *learns* when and why
  to call Smriti. Not an HTTP client; a versioned markdown instruction file
  installed into the agent host's project directory.

Surfaces:

- **Chat UI** (`frontend/`) — the human inspection and steering surface.
  Reads and writes via V2/V4/V5 endpoints. Drives the live conversation runtime
  (`POST /api/v4/chat/send`) that injects checkpoint context into model calls.
- **CLI** (`cli/smriti_cli/main.py`, entry point `smriti`) — the programmatic
  surface for coding agents and scripts running in a shell tool loop.
  Reads via V2 (`GET /commits/{id}`, `GET /repos/{id}/commits`) and V4
  (`GET /chat/spaces/{id}/head` for main-only, or `GET /chat/spaces/{id}/state`
  for the multi-branch continuation brief, which is the default). Writes via
  V4 (`POST /chat/commit`) with the full schema including `assumptions`,
  `artifacts`, `project_root`, and `author_agent`. Extracts structured fields
  from freeform markdown via V5 (`POST /checkpoint/extract`). Triggers review
  via V5 (`POST /checkpoint/{id}/review`). Drives fork / compare / restore
  via V5 lineage endpoints. Does not touch `/chat/send` — agents run their
  own reasoning in their own context, using their own LLM provider. Smriti is
  their shared memory, not their runtime.
- **MCP server** (`cli/smriti_cli/mcp_server.py`, entry point `smriti-mcp`) —
  the same surface wrapped as 17 MCP tools for hosts that speak the Model
  Context Protocol natively (Claude Code, Cursor, Windsurf). Stdio transport.
  Each tool is a thin shim: build a `SmritiClient`, call one or two methods,
  run the result through an existing formatter, return markdown. Feature
  parity with the CLI modulo three deliberate differences: (1) MCP does not
  auto-capture `project_root` from cwd because the MCP server runs in the
  host's arbitrary working directory, (2) destructive tools have no per-tool
  confirmation prompt — the host's tool-approval UI is the gate, (3) the
  `smriti_install_skill` tool returns the rendered skill pack markdown rather
  than writing a file, because the MCP server has no business planting files
  in the host's arbitrary cwd. Shares the formatters with the CLI, so both
  transports produce byte-identical output for the same backend response.
- **Skill pack** (`cli/smriti_cli/skill_pack/`, CLI subcommand
  `smriti skills install`, MCP tool `smriti_install_skill`) — the agent-
  onboarding surface. A single versioned `template.md` renders for two
  targets (`claude-code` → `.claude/skills/smriti/SKILL.md`, `codex` →
  `AGENTS.md`) via a pure-function substituter. Workflow heuristics
  (when to checkpoint, critically when NOT to checkpoint, when to fork,
  how to detect drift) are identical across both targets by design; only
  the primary tool notation varies. The renderer is version-aware and
  refuses to overwrite a destination whose installed version is newer or
  equal unless `--force` is passed. Tests assert that every anti-pattern
  rule, the signal test, the frequency target, and the drift-detection
  heuristics appear in the rendered output, so future template edits
  cannot silently drop load-bearing content. Lives in the CLI package
  for distribution (ships via the same `pip install -e ./cli`) but has
  no runtime dependency on the HTTP client — rendering is entirely local.

### Multi-branch state (`/api/v4/chat/spaces/{id}/state`)

The CLI's `smriti state` and the MCP's `smriti_state` default to the multi-
branch state endpoint rather than the older main-only `/head` endpoint.
The endpoint returns a composite response in one round trip: the space
header, main-branch HEAD metadata (same shape as `/head`), the full
main-branch HEAD commit, a list of active non-main branches with their
latest checkpoint metadata, and a lightweight divergence summary when any
active branch disagrees with main on decisions.

Hard caps are constants in the endpoint source: `ACTIVE_BRANCHES_CAP = 5`,
`DIVERGENCE_BRANCHES_CAP = 2`, `DIVERGENCE_DECISIONS_CAP = 3`. These are
not query parameters because the agent-facing contract is "digestible by
default" — a caller who needs unbounded history should hit
`/api/v5/lineage/spaces/{id}`, which is the detail surface.

Divergence detection reuses `lineage._diff_lists` so matching stays
consistent with `smriti compare` — decisions differing only in case or
punctuation normalize to the same key and do not trigger false divergence
signals. The two helper functions (`_get_active_branch_heads`,
`_compute_space_divergence`) live alongside `_get_latest_commit` in
`chat.py`; no new module.

The legacy single-HEAD path is preserved behind `--main-only` / `main_only=True`
for scripts that parsed the old `HeadResponse` shape.

Agents interact with structured state (checkpoints) via the CLI or the MCP
server. The chat UI and either agent-facing surface can be used simultaneously
on the same project: the human steers and inspects, the agent reads and writes.
Both see the same reasoning state. The skill pack is what makes the agent's
use of that state reflexive rather than something it has to re-derive at the
start of every session.

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

## Work Claims — Pre-Work Intent Visibility

Work claims are the first concurrency primitive in Smriti. A claim is a lightweight,
time-bounded, advisory declaration that an agent is actively working on something
in a space. It makes pre-work intent visible before work produces a checkpoint.

Claims are stored in a dedicated `work_claims` table with 11 columns: `id`,
`repo_id`, `session_id`, `agent`, `branch_name`, `base_commit_id`, `scope`,
`intent_type`, `status`, `claimed_at`, `expires_at`. They are not session
metadata or checkpoint metadata — a dedicated table makes them queryable,
expirable, and independently evolvable.

`intent_type` is one of: `implement`, `review`, `investigate`, `docs`, `test`.
This helps distinguish collision (two agents implementing the same thing) from
follow-up (one agent reviewing another's implementation).

Claims surface in `GET /api/v4/chat/spaces/{id}/state` as an `active_claims`
array, rendered in the CLI/MCP state brief as `## Active work` — one line per
claim with agent, intent type, branch, base hash, scope, and relative time.
The section is elided when no active claims exist.

Claims are advisory — not locks. The skill pack teaches agents to check
`## Active work` before starting and to create their own claim after reading
state but before writing code. If scopes overlap, the agent picks different
work or asks the human. Claims expire after a configurable TTL (default 4
hours). Agents explicitly mark claims `done` or `abandoned` when work
finishes; expired claims fall out of the state view automatically.

API surface: `POST /api/v5/claims` (create), `PATCH /api/v5/claims/{id}`
(update status), `GET /api/v5/claims?space_id=...` (list active).
CLI: `smriti claim create/done/abandon/list`. MCP: `smriti_claim`,
`smriti_claim_done`.

---

## Structured Tasks — Autonomous Work Selection

Structured tasks are the mechanism that bridges work claims (what agents are
doing) with checkpoint tasks (what work exists). Before structured tasks,
checkpoint tasks were flat strings — agents could see what work existed but
had no metadata to decide which task to pick without founder routing.

**Task shape.** Tasks in `CommitModel.tasks` (JSONB) are now objects:

```json
{
  "text": "Write integration tests for freshness",
  "intent_hint": "test",
  "blocked_by": "freshness-impl",
  "status": "open"
}
```

All fields except `text` are optional. Legacy string tasks are normalized
at render time — the formatter wraps `"some string"` into `{"text": "some string"}`.
No database migration was required; JSONB accepts both shapes.

**Intent hints** use the same vocabulary as claim `intent_type`: `implement`,
`review`, `investigate`, `docs`, `test`. This shared vocabulary is what makes
autonomous selection work — an agent can filter tasks by intent and pick work
that is complementary to active claims.

**Status** is `open` or `done`. There is no `claimed` status — claims are live
coordination state (the `work_claims` table), while task status is durable
checkpoint state (the `commits` table). Keeping these separate avoids drift
between two truth sources for in-flight work.

**blocked_by** is a free-text label referencing another task. It is advisory,
not enforced — the skill pack teaches agents to skip blocked tasks, but nothing
prevents an agent from working on one.

**Extract prompt.** The checkpoint extractor prompt (both draft and extract paths
in `checkpoint.py`) asks the LLM to produce structured task objects. A
`_normalize_tasks()` function validates intent hints against the 5-type
vocabulary, drops invalid values, deduplicates by text, and normalizes case.

**Rendering.** The CLI formatter's `_task_section()` renders structured tasks
with inline annotations in the state brief:

```
## In progress
- Add freshness endpoint [implement]
- Write freshness tests [test] → blocked by: freshness-impl
- Update README [docs] (done)
```

The frontend renders intent badges (blue), done badges (green), blocked_by
markers (amber), and strikethrough for done tasks.

**The autonomy mechanism.** An agent reading the state brief applies the
selection logic taught in skill pack Section 3.8:

1. Read `## In progress` — note task intents and blocked_by
2. Read `## Active work` — note existing claim intent types
3. Pick a task whose intent is complementary to active claims
4. Skip blocked and done tasks
5. Create a claim and start work

This is descriptive, not prescriptive — tasks describe themselves, agents
decide. No scheduler, no assignment, no orchestrator.

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

**Branch lifecycle management.** Smriti branches (non-main checkpoint chains) have
no explicit lifecycle. A branch whose work has been integrated into main still
appears in the `## Active branches` section of the state brief because the
checkpoint's `branch_name` field persists. The next primitive here is an explicit
branch disposition signal (`integrated` / `superseded` / `abandoned` / `active`)
rather than a recency heuristic or a git-merge check — because Smriti branches
are reasoning branches, not git branches.
