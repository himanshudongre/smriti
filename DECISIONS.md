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

### Why skill packs are a first-class surface, not documentation

After shipping the CLI and the MCP server, the next friction item from real
agent sessions was not about the tools — it was about agents not reaching for
them. An agent dropped into a Smriti-enabled project with 17 MCP tools
available would call a few of them reactively, miss the reflex of reading
state at session start, and quietly fall back to writing `HANDOFF.md` under
context pressure because markdown handoff files are what the training data
shows. The tools were technically reachable and operationally invisible.

The options for closing this gap were (a) ship documentation and hope agents
read it, (b) rely on richer tool docstrings and hope agents synthesize a
workflow from them, or (c) ship a versioned instruction file into the agent
host's project directory so the workflow heuristics live in the agent's
system context during every session on that project.

(a) is known not to work. (b) depends on agents generalizing from tool
descriptions the way a human would — real agents don't, reliably, under
context pressure. (c) is the skill pack.

The skill pack is installed via `smriti skills install <target>`, which writes
a single versioned markdown file to the target host's conventional project
location (`.claude/skills/smriti/SKILL.md` for Claude Code, `AGENTS.md` for
Codex). The content is a single source-of-truth `template.md` rendered
per-target via a pure-function substituter — both targets share the same
workflow heuristics; only the primary tool notation differs. Versioning is
frontmatter-based and the installer refuses to overwrite a same-or-newer
destination without `--force`.

The most important content is Section 5, "When NOT to checkpoint," which gets
equal weight to "When to checkpoint" on purpose. Without the anti-pattern
section, agents either checkpoint reflexively (noise) or not at all (missed
inflection points). A three-question signal test and a concrete frequency
target (2-4 checkpoints per 4-hour session) give agents deterministic
criteria for each call.

Treating this as a first-class surface rather than a README means it versions
alongside the code, ships via `pip install -e ./cli`, lives on the install
path, and has a test suite that asserts the critical content cannot be
silently dropped by future template edits.

### Why smriti state is multi-branch by default

The original `smriti state` (and `smriti_state`) returned only the main-branch
HEAD. That was correct for single-agent use and silently wrong for
multi-agent: on a shared project where Claude Code was on main and Codex was
on a fork branch, the first command every well-behaved agent runs hid the
other agent's work entirely. The skill pack teaches agents to call `state`
unconditionally at session start — but if that call returns a blind spot, the
skill pack is teaching the wrong reflex.

Multi-branch is the new default. `GET /api/v4/chat/spaces/{id}/state` returns
the main continuation brief unchanged at the top of the response, then
appends a concise `## Active branches` section (one line per non-main branch
with author attribution, capped at 5 branches) and a lightweight
`## Divergence signal` section when any active branch disagrees with main on
decisions. Divergence detection reuses `_normalize_text` and `_diff_lists`
from the existing compare endpoint so matching stays consistent —
decisions differing only in case or punctuation do not trigger false
divergence.

Both extensions are fully elided when their payload is empty, so a
single-agent project with no forks sees output identical to the pre-build
shape. Hard caps (5 branches, 2 divergent pairs per signal, 3 decisions per
side per pair) keep the aggregate response digestible on busy projects. When
the divergence signal fires, it names the specific conflicting decisions and
points at `smriti compare` for the full diff; it does not reproduce the full
diff inline, because the signal's job is to be noticeable, not complete.

The legacy single-HEAD path is preserved behind `--main-only` (CLI) and
`main_only=True` (MCP) so scripts that parsed the old shape still work.
Nothing else changed: `/head` still exists, `get_head` still returns the
same shape, `format_state_brief` accepts the new `space_state` kwarg as
optional so existing callers are unaffected.

### Why work claims are advisory, not locks

When two agents start working on the same scope simultaneously, there are three
possible responses: block one of them (hard lock), warn both (advisory signal),
or do nothing and let them collide. Smriti uses the advisory approach.

Hard locks were rejected because:

- Smriti is a reasoning-state system, not a file-locking system. Agents reason
  in overlapping conceptual spaces, not in files. A lock on "I'm working on the
  lineage test" has no clear mutex boundary.
- Lock lifecycle is fragile in agent contexts. If an agent crashes or times out
  mid-work, a hard lock orphans and blocks everyone until a human intervenes.
  Advisory claims with a fixed TTL (default 4 hours) expire naturally.
- The coordination problem is visibility, not serialization. The failure mode in
  practice — two agents both implementing the same test because neither knew the
  other was doing it — is solved by making intent visible. It does not require
  preventing one agent from starting.

The claim primitive is a dedicated `work_claims` table, not session metadata or
checkpoint metadata. Session metadata is the wrong lifecycle (sessions persist
long after work ends). Checkpoint metadata is post-work (claims are pre-work).
A dedicated table is queryable, expirable, and independently evolvable without
touching the checkpoint or session schemas.

`intent_type` (implement / review / investigate / docs / test) is included
because bare scope strings are ambiguous. Two claims on "lineage author_agent
test coverage" could be a collision (both implementing) or a follow-up (one
reviewing the other's work). The intent type makes this distinction
machine-readable without requiring scope-matching heuristics.

### Why the shared runtime model is documented, not enforced

The canonical local setup — Postgres in Docker, backend via `make dev`, agents
as clients of `http://localhost:8000` — is documented in the skill pack, the
operating contract, and the README, but not enforced in code.

This was deliberate. The failure mode that motivated the documentation was
agents trying to start the backend themselves from inside their tool loops,
which caused environment-variable inheritance issues (the extractor silently
fell back to MockAdapter because the uvicorn subprocess didn't inherit the
shell profile's API keys). Documenting the rule ("agents are clients, the
human starts the backend") solved the problem without code changes. Adding
enforcement (e.g., refusing to serve requests from non-local origins or
checking process parentage) would add complexity for a problem that behavioral
guidance already handles.

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
- **Branch lifecycle** — Smriti branches (non-main checkpoint chains) have no
  explicit lifecycle. A branch whose work has been integrated into main still
  appears as "active" in the state brief. The next primitive is an explicit
  branch disposition signal, not a git-merge heuristic.
