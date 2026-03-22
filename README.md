# Smriti — Version control for reasoning.

Conversations become structured state, not disposable logs.

Smriti is a versioned AI workspace. It turns conversations into structured, immutable
snapshots called Checkpoints that you can carry across models, fork into new reasoning
paths, and compare later.

**Smriti owns the reasoning state. Models are interchangeable.**

For example: you spend an hour with GPT-4o working through an architecture decision,
checkpoint the conclusion, then continue the same thread in a new session using a
different model. No re-explanation, no lost context.

---

## Demo preview

Click to watch a 3–4 minute walkthrough of branching, checkpoints, and comparison:

[![Smriti demo](docs/assets/checkpoint-diff.png)](https://www.loom.com/share/0531ab1b6f114ceb9996ec5780052158)

---

## The problem

You spend an hour working through a hard problem. You reach a clear decision. Then you
need to step away, switch models, or revisit an earlier direction.

There is no clean way to do this. The only record is a flat transcript. You cannot
return to the exact state you were in an hour ago. You cannot fork the conversation to
explore a different direction without contaminating the original thread. You cannot
switch models without re-explaining everything from scratch.

Smriti fixes this by treating reasoning state as a first-class artifact, versioned and
isolated from the event stream that produced it.

---

## What you can do with it

- **Return to any prior state.** Mount any Checkpoint; the model receives exactly that
  state as context, nothing more. Later work does not leak backward.
- **Switch models mid-session.** Checkpoints carry state across providers. Switch from
  OpenAI to Anthropic without re-explaining the problem.
- **Fork a line of reasoning.** Branch from any Checkpoint into a new session. Both
  threads remain live in the same Space.
- **Compare branches.** Diff any two Checkpoints across branches to see exactly where
  decisions diverged.

---

## Beyond chat: reasoning state for agents

Smriti is not limited to chat workflows.

Agents also struggle with state. Multi-step reasoning chains become hard to debug,
reproduce, or branch. Once an agent run diverges, there is no clean way to return to
a prior state or explore alternatives in parallel.

Smriti provides a structured state layer that agents can use:

- Persist intermediate reasoning as checkpoints
- Resume from any prior state deterministically
- Fork execution paths to explore alternatives
- Compare outcomes across runs

This makes agent behavior inspectable, reproducible, and debuggable.

---

## Quick start

### Prerequisites

- Python 3.11+
- Node 18+
- PostgreSQL 14+
- At least one LLM provider API key (OpenAI, Anthropic, or OpenRouter), or use Mock
  Mode to run without any keys

```bash
git clone https://github.com/himanshudongre/smriti
cd smriti

# Copy environment template
cp .env.example .env

# Install all dependencies and run database migrations
make setup

# Start backend (terminal 1)
make dev

# Start frontend (terminal 2)
make dev-frontend
```

Frontend: `http://localhost:5173` | Backend API: `http://localhost:8000`

**No API key?** Enable **Mock Mode** in the compose bar to run with scripted responses
and no provider calls.

### Docker

```bash
make up       # Start all services (postgres + backend + frontend)
make logs     # Follow logs
make down     # Stop all services
```

---

## Try the demo

`demos/branching-reasoning-demo/` contains a complete, repeatable walkthrough
demonstrating Smriti's branching and comparison workflow. Includes step-by-step
instructions, exact messages to paste, expected diff output, and a presenter talk track.

[demos/branching-reasoning-demo/README.md](demos/branching-reasoning-demo/README.md)

---

## Core Concepts

### Space

A Space is the long-lived container for a line of work. It holds the full history of
Checkpoints created within that work and all Sessions associated with it.

Analogy: a Git repository, but for a thinking process rather than a codebase.

Spaces are named and persistent. You might have one for a product architecture
decision, another for a research topic, another for a client engagement.

### Session

A Session is a live chat runtime. It may be attached to a Space (and thus have access
to that Space's Checkpoint history) or standalone (no persistent state).

A Session has an active provider and model. Switching provider or model within a
Session does not lose conversational history — Smriti stores Turns independently of
any provider session.

### Checkpoint

A Checkpoint is a structured, immutable state snapshot. It contains:

| Field | Description |
|---|---|
| **Title** | 3–5 word label for the state |
| **Objective** | The goal being worked toward at this point |
| **Summary** | Narrative of what was figured out |
| **Decisions** | Explicit choices made — only what was stated, not inferred |
| **Tasks** | Concrete action items identified |
| **Open Questions** | Unresolved questions at this point |
| **Entities** | Key concepts, tools, systems, or proper nouns |

Checkpoints are created manually at meaningful points — before switching models,
before stepping away, when a significant decision is reached. The **Draft with AI**
feature uses a background intelligence model to extract a draft from the current
session's active Turns; the user reviews and saves.

A Checkpoint is never created automatically. This is intentional: automatic
checkpointing produces noise, not signal.

### Turn

A Turn is a single unit in the event stream: one user message or one assistant reply,
with its provider, model, and sequence number recorded. Turns are append-only and
never edited.

Turns are the raw material. Checkpoints are the distillate.

---

## The Context Modes

| Mode | What the model sees |
|---|---|
| **FRESH** | No Checkpoint context. Blank slate. Only the current Turn. |
| **HEAD** | The latest Checkpoint in the attached Space, plus recent Turns in this Session. |
| **MOUNTED** | A specific Checkpoint, plus only Turns created after mounting. Nothing else. |
| **FORKED** | The fork-source Checkpoint as base context, plus Turns created in this fork session. |

The MOUNTED mode is the key differentiator.

When you mount a specific Checkpoint, Smriti records the sequence number of the last
Turn at the moment of mounting. All subsequent requests pass only Turns with sequence
numbers above that boundary. Turns from other sessions, from other providers, or from
work that happened after that Checkpoint was created — none of it enters the context.
The isolation is enforced at the data layer, not by prompt instruction.

---

## How It Works

### Starting a session

Open the workspace. A new Session is created automatically. By default it has no
Space attached (FRESH mode).

### Attaching a Space

Click the Space button in the thread header. Select an existing Space or create one.
Choose a memory scope:

- **Latest checkpoint only** — the most recent Checkpoint provides base context
- **Latest 3 checkpoints** — the three most recent Checkpoints provide layered context

### Creating a Checkpoint

When you reach a meaningful point — a decision, a model switch, the end of a work
block — click the Checkpoint button in the thread header.

The Checkpoint form opens with empty fields. Click **Draft with AI** to have the
background intelligence model extract a draft from the current session's active Turns.
The draft reflects only the active context mode (FRESH, HEAD, or MOUNTED). Review,
edit, and save.

### Mounting a Checkpoint

Open the Checkpoint history panel by clicking the context badge in the thread header.
Find the Checkpoint you want to return to. Click **Mount**.

The header updates to show `MOUNTED · <hash>`. Any Turn you send from this point is
resolved against that Checkpoint's state only.

To return to HEAD mode, click **Unmount** in the history panel.

### Forking a Session

Open the Branch Tree for a Space. Click **Fork** on any Checkpoint. Give the branch
a name. A new Session is created, seeded from that Checkpoint's state, with a clean
Turn history.

The fork session starts in FORKED mode. Its reasoning develops independently from the
main branch. Both branches remain live in the same Space.

### Comparing Checkpoints

In the Branch Tree, select any two Checkpoints across any branches and click
**Compare**. The diff view shows decisions, tasks, and summaries side by side with
per-branch and shared items clearly marked.

### Switching providers

Change the provider and model in the session toolbar. The Session continues
uninterrupted. Smriti passes the same Checkpoint context and Turn history to the new
provider. No re-explanation required.

---

## Current Limitations

- Single-user; no authentication
- No merging of divergent Checkpoint lines
- No streaming responses — each Turn is a synchronous request/response cycle
- Transcript ingestion via paste (V1 API) is a legacy feature; not the primary workflow
- No mobile UI
- No MCP or browser extension integrations

---

## Provider Configuration

Smriti uses two independent provider slots:

**Chat provider** — the model you converse with. Selected per-session in the UI
toolbar. Supports: OpenAI, Anthropic, OpenRouter.

**Background intelligence** — a separate model used for Draft with AI and session
auto-titling. Configured server-side. Not visible in the chat UI.

### YAML configuration (recommended)

Copy `backend/config/providers.example.yaml` to `backend/config/providers.yaml` and
fill in your keys:

```yaml
providers:
  openai:
    api_key: "sk-..."
    default_model: "gpt-4o"

  anthropic:
    api_key: "sk-ant-..."
    default_model: "claude-sonnet-4-6"

  openrouter:
    api_key: "sk-or-..."
    base_url: "https://openrouter.ai/api/v1"

chat:
  default_provider: "openrouter"

background_intelligence:
  provider: "openai"
  model: "gpt-4o-mini"
```

### Environment variables

```bash
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
OPENROUTER_API_KEY=sk-or-...
SMRITI_DEFAULT_PROVIDER=openrouter
DATABASE_URL=postgresql://smriti:smriti@localhost:5432/smriti
```

Environment variables take precedence over YAML values. API keys are never returned
by any API endpoint.

### Mock Mode

The UI includes a **Mock Mode** toggle (compose bar) that uses a deterministic mock
adapter — no API calls, scripted responses. Useful for testing checkpoint and session
mechanics without a live provider key.

---

## Technical Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, SQLAlchemy, Alembic, Python 3.11+ |
| Database | PostgreSQL |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS |
| Provider adapters | OpenAI SDK, Anthropic SDK, OpenRouter (OpenAI-compatible) |

The backend API is versioned by product generation. V4 handles chat sessions and
message sending. V5 handles checkpoint and lineage operations. V1 and V2 are legacy
endpoints retained for compatibility but not part of the current primary workflow.

---

## Roadmap

- Streaming responses
- Multi-user Spaces with authentication
- Provider expansion (additional providers and local models)
- Source Turn range recorded on Checkpoints (which conversation produced this snapshot)
- MCP integrations
- Checkpoint merging

---

## Further Reading

- [ARCHITECTURE.md](ARCHITECTURE.md) — system model, checkpoint isolation mechanism,
  provider abstraction, API versioning
- [docs/API.md](docs/API.md) — endpoint reference for V4 (chat) and V5 (checkpoint
  and lineage)
- [DECISIONS.md](DECISIONS.md) — key architectural and product decisions
- [CONTRIBUTING.md](CONTRIBUTING.md) — how to set up the dev environment and contribute
