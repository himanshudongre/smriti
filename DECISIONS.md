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

### Why assumptions are tracked separately from decisions

Decisions are explicit choices. Assumptions are things the reasoning takes for granted
without debating them. This distinction matters because when reasoning goes wrong, the
cause is often an unexamined assumption rather than a bad decision.

Separating them makes checkpoint review more useful: the system can flag when a decision
relies on something that is not listed as either a decision or an assumption. It also
makes rollback more targeted. Instead of going back to "before things went wrong" you
can identify which specific assumption was faulty.

### Why checkpoint review is on-demand, not automatic

The system can review a checkpoint for reasoning consistency: contradictions between
decisions, hidden assumptions, resolved open questions, disconnected entities. This
review is triggered manually by the user, not run automatically on every checkpoint.

Automatic review would create noise and make checkpoints feel graded rather than
useful. The user should be in control of when they want the system to inspect their
reasoning state. The review is a tool, not an audit.

### Why artifacts are stored on checkpoints, not separately

Artifacts (attached text content like code snippets, plans, outputs) are stored as
JSONB on the checkpoint row rather than in a separate table. This keeps checkpoints
self-contained: one checkpoint is one complete package of reasoning state plus the
content being reasoned about.

Artifacts are included in prompt context when a checkpoint is active, which means
the model's responses are grounded in actual content rather than just summaries of
what was discussed. Artifact content is capped at 2000 characters per artifact in
the prompt to manage context size.

### Why a CLI is the first agent-facing surface, not MCP

Agents need a way to read and write Smriti's reasoning state from inside their
tool loops. The two realistic transports are a CLI they can invoke via shell
commands, and an MCP server they can call as structured tools. MCP is the better
long-term answer: structured tool calls, native integration with hosts that
support it, no shell indirection.

The CLI was chosen for V1 anyway. Reasons:

- Fastest path to a real end-to-end test. A CLI can be installed and wired into
  any agent that runs shell commands on the same day it ships.
- Protocol-agnostic. Works with any host, including ones that do not speak MCP
  or treat MCP inconsistently.
- MCP is an evolving protocol with different levels of support per host. A CLI
  is a stable contract.
- MCP is a wrapper around the same operations the CLI already exposes. Adding
  MCP later as a second transport over the same underlying commands is a
  smaller, cleaner move than building MCP first without knowing which commands
  agents actually use.

MCP was the expected second transport once the basic handoff loop was proven in
real use. That happened in rounds 3 and 4 of dogfood testing (Claude Code ↔
Codex and Codex ↔ Codex handoffs with the extractor), and MCP shipped as the
next build on top. See the next entry.

### Shipping MCP as the second transport

MCP shipped as V3 Build 2 after rounds 3 and 4 validated the handoff loop.
Design decisions made at ship time:

- **Same package, two entry points.** `cli/pyproject.toml` exposes both
  `smriti` (CLI) and `smriti-mcp` (server). One `pip install -e ./cli`
  installs both. The MCP server lives next to the CLI in
  `cli/smriti_cli/mcp_server.py` and imports `SmritiClient` and the
  existing formatters directly. Zero reimplementation.
- **FastMCP over the low-level Server class.** The high-level API
  (`mcp.server.fastmcp.FastMCP` + `@mcp.tool()` decorators) keeps each tool
  handler to a dozen lines: build a client, call one or two methods, run
  through a formatter, return a string. The cost is coupling to the FastMCP
  shape; the benefit is that a handler reads like an ordinary Python function.
- **Stdio transport only for v1.** HTTP / SSE and remote deployments are out
  of scope. Stdio is what Claude Code, Cursor, and Windsurf all support, and
  it's the cheapest thing to run (the host manages the subprocess lifecycle).
- **Twelve tools, one per CLI command.** No consolidation into fewer
  megatools, no hidden helpers. `smriti_state`, `smriti_list_checkpoints`,
  `smriti_fork`, etc. map 1:1 onto what the CLI exposes so docs and agent
  prompts translate directly.
- **Destructive tools have no per-tool confirmation prompt.** The MCP host's
  tool-approval UI is already the gate — adding a second confirmation layer
  inside the tool itself would be redundant, and agents can't interact with
  prompt dialogs from inside an MCP tool call anyway. (The CLI still has
  `-y` because a terminal has no equivalent approval UI.)
- **`smriti_create_checkpoint` is extract-only.** No JSON stdin mode. The
  round-4 verdict was that once the extractor exists, hand-written JSON is
  never the right path for an agent. MCP agents pass freeform markdown and
  Smriti's background LLM structures it. `dry_run=True` previews the
  extraction without committing.
- **`project_root` defaults to empty, not cwd.** MCP servers run in the host's
  arbitrary working directory, so auto-capturing cwd would plant garbage paths
  on every checkpoint. Agents pass `project_root="/absolute/path"` explicitly
  when they want the field populated. The CLI's cwd auto-capture is
  deliberately kept because `smriti` runs from the project directory.
- **Tests are plain Python unit tests against a mocked `SmritiClient`.** No
  full MCP protocol integration tests. The tool handlers are normal functions
  and FastMCP's role is a thin decorator layer; testing them with a
  `MagicMock(spec=SmritiClient)` fixture covers the behavior that matters
  without spinning up a stdio server. The protocol round-trip was validated
  separately via the `mcp` SDK's Inspector UI and a host-less Python client.

The MCP server is a pure sibling to the CLI — no shared mutable state, no
code paths that one transport uses and the other doesn't. Both talk to the
same backend via the same `SmritiClient`, and both render via the same
formatters. This is the property that makes "the CLI and the MCP server have
feature parity" not a maintenance commitment but a mechanical consequence of
the architecture.

### Why the chat UI remains alongside agent-facing surfaces

It would be tempting to frame Smriti as "an agent backend" and deprecate the
chat UI as legacy. That would be a mistake. The chat UI is the human inspection
and steering surface over the same reasoning state that agents are writing to.
When two agents have been working on a project and one of them has gone in the
wrong direction, the human needs a way to look at what happened, fork or restore
cleanly, and point the next agent at a better state.

The chat UI is not a stepping stone to an agent-only product. It is the
permanent human-in-the-loop interface over shared reasoning state.

### Why agents do not touch the live chat API (`/chat/send`)

The V4 chat send endpoint drives the live conversation runtime: it accepts user
messages, manages provider routing, injects checkpoint context, and stores
turns. Agents should not invoke it. Agents write directly to structured state
(checkpoints via `/chat/commit`) and read structured state (HEAD + commit
fetch). They run their own reasoning in their own context, using their own LLM
provider. Smriti is their shared memory, not their runtime.

This keeps the chat runtime focused on human-driven exploration, and keeps the
agent surface narrow and composable.

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
