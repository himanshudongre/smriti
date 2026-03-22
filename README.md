# Smriti — Version control for reasoning.

Conversations become structured state, not disposable logs.

Smriti (स्मृति, *memory* in Sanskrit) is a versioned AI workspace. It separates the
ephemeral event stream of a conversation from the durable structured state that
conversation produces — and makes that state explicitly versioned, inspectable, and
portable across models.

**In Smriti, the system owns the state. Models are interchangeable processors.**

---

## The Problem

Every current LLM interface — ChatGPT, Claude.ai, Perplexity — treats conversation
state as disposable. When you close a tab, switch a model, or start a new session,
your context evaporates. You can export a transcript, but a transcript is
undifferentiated text: no structure, no version history, no way to return to a prior
state cleanly.

The practical consequences:

- Switching models means re-explaining everything from scratch
- There is no way to ask "what did I know at this point?"
- Context is implicit and fragile — the model infers it, often incorrectly
- There is no version history of reasoning, only a log of messages
- Long conversations accumulate noise faster than signal

These are not UI problems. They are structural: existing tools do not distinguish
between *what was said* and *what was concluded*.

---

## What Smriti Does Differently

Smriti introduces a hard separation between two layers:

**The event stream** — Turns of conversation, ordered, append-only, ephemeral.

**The state snapshot (Checkpoint)** — an immutable, structured summary of what was
decided and understood at a specific point: title, objective, summary, decisions, tasks,
open questions, entities.

A Checkpoint is not a transcript. It is the extracted state of a thinking process at a
moment in time. Once created, it does not change.

This separation enables:

- **Returning to a prior state** — mount any Checkpoint; only Turns created after
  mounting are included in context. Later work does not leak backward.
- **Cross-model continuity** — a Checkpoint created in a GPT-4o session can seed a
  Claude or Gemini session. The state travels; the model does not matter.
- **Inspectability** — "what did I decide at this point?" has a concrete, queryable
  answer.
- **Branching** — fork any Checkpoint into a new session and explore a diverging line
  of reasoning without affecting the original thread.
- **Comparison** — diff two Checkpoints across any branches to see exactly where
  reasoning diverged.

Smriti does not eliminate ambiguity or hallucination. It makes reasoning inspectable,
versioned, and recoverable.

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

## Setup

### Prerequisites

- Python 3.11+
- Node 18+
- PostgreSQL 14+
- At least one LLM provider API key (OpenAI, Anthropic, or OpenRouter), or use Mock
  Mode to run without keys

### Quick start

```bash
git clone https://github.com/your-org/smriti
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

Frontend: `http://localhost:5173` — Backend API: `http://localhost:8000`

### Docker

```bash
make up       # Start all services (postgres + backend + frontend)
make logs     # Follow logs
make down     # Stop all services
```

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

## Try the Demo

The `demos/branching-reasoning-demo/` directory contains a complete, repeatable demo
scenario demonstrating Smriti's branching-reasoning workflow. It includes:

- Step-by-step runbook
- Exact messages to paste for each turn
- Expected diff output
- Presenter talk track

See [demos/branching-reasoning-demo/README.md](demos/branching-reasoning-demo/README.md)
for the full walkthrough.

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
- Provider expansion (Gemini, local models via Ollama)
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
