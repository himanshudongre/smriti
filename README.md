# Smriti

A shared reasoning-state backend that lets multiple coding agents coordinate on the same project — without an orchestrator.

---

## What Smriti does

When you run multiple coding agents on the same project — Claude Code and Codex, or two Claude Code sessions — they have no shared state. Each agent starts from scratch, re-discovers decisions already made, and occasionally duplicates work another agent is already doing. The current workaround is markdown handoff files (`HANDOFF.md`, `NOTES.md`), which break the moment reasoning branches or two agents need to work in parallel.

Smriti replaces that with a structured reasoning-state layer. Agents read the current state at session start, declare what they're working on, and checkpoint their thinking at meaningful inflection points. The state is structured — decisions, assumptions, tasks, open questions, artifacts — not prose. It's branchable, comparable, restorable, and visible to every agent working on the project.

---

## Built with Smriti

The entire coordination substrate was developed with Claude Code and Codex working in parallel on the same codebase, coordinating through Smriti's own state. Current project metrics (`smriti metrics smriti-dev`):

- **56 checkpoints** across **2 agents** (Claude Code: 35, Codex: 21)
- **30 cross-agent continuations** — checkpoints where a different agent picked up where the previous one left off
- **37 work claims** with **100% completion** — every declared intent was finished, none abandoned
- **2 milestones** marking proven coordination proofs

The strongest proof: two agents started near-simultaneously, read the same task surface (4 tasks with stable IDs and intent hints), and independently picked different complementary tasks — one chose `[test]`, the other chose `[implement]` — without any human routing. No orchestrator. No task queue. Just structured metadata on the shared state.

---

## How it works

### Four surfaces on the same core

1. **A CLI** (`smriti`) — how a coding agent reads and writes reasoning state from a shell tool loop.
2. **An MCP server** (`smriti-mcp`) — the same surface wrapped as 17 MCP tools for Claude Code, Cursor, and Windsurf.
3. **An agent skill pack** — a versioned instruction file (`.claude/skills/smriti/SKILL.md` or `AGENTS.md`) that teaches the agent when to checkpoint, when not to, how to detect drift, and how to select complementary work. Install once per project.
4. **A chat UI** — how a human reads, steers, and debugs the shared state. Dashboard with checkpoint timeline, active claims, milestone markers, and needs-attention signals.

```bash
smriti state my-project                                    # what every agent reads first
smriti metrics my-project                                  # project-level coordination KPIs
cat notes.md | smriti checkpoint create my-project --extract  # structured checkpoint from freeform markdown
smriti claim create my-project --agent claude-code \
    --scope "Add freshness endpoint" --task-id impl-1      # declare intent with task reference
smriti compare <id-a> <id-b>                               # structured diff of two checkpoints
```

### Coordination primitives

One project, one Smriti Space, multiple agents. Each reads the state, declares intent, does work, and checkpoints. The following primitives make this reliable:

- **Structured checkpoints** — decisions, assumptions, tasks, open questions, artifacts. Not prose summaries. Structured fields that agents can read and act on.
- **Work claims** — agents declare intent before starting. Claims are advisory (not locks), expire after a TTL, and carry an `intent_type` (implement, review, test, docs, investigate). Other agents see active claims and avoid collision.
- **Structured tasks with intent hints** — checkpoint tasks carry optional `intent_hint`, `blocked_by`, `status` (open/done), and stable `id` slugs. Agents self-select complementary work from the task list.
- **Task-referenced claims** — claims can reference a specific task ID (`--task-id impl-1`), enabling precise collision detection when agents start near-simultaneously.
- **Freshness checks** (`--since`) — agents detect whether the state has moved since their base before checkpointing.
- **Branch disposition** — branches are explicitly marked `integrated`, `abandoned`, or `active` so the state brief stays clean.
- **Checkpoint notes** — additive annotations (note, milestone, noise) on existing checkpoints without modifying the immutable reasoning state.
- **Backend capabilities** (`/health`) — the backend advertises its feature surface so agents can detect stale backends.
- **Compact mode** (`--compact`) — artifact content omitted for token efficiency; labels and recovery instructions preserved.
- **Project metrics** (`smriti metrics <space>`) — coordination, state quality, and branch lifecycle KPIs computed on demand from existing data.

---

## What Smriti is not

- **Not an orchestrator.** Smriti describes state. It does not assign tasks, schedule work, or route agents. Agents make their own decisions from shared metadata.
- **Not a task manager.** Tasks live inside checkpoints as structured fields. There is no separate task table, no Jira-like lifecycle, no assignment system.
- **Not a memory database.** Smriti stores structured reasoning snapshots at inflection points, not a running log of everything an agent said or saw.
- **Not production infrastructure (yet).** Single demo user, no auth, no multi-tenancy. Works for solo builders running multi-agent workflows.

---

## Getting started

You will need: Python 3.11+, Node 18+, Docker (for Postgres).

### 1. Clone and set up

```bash
git clone https://github.com/himanshudongre/smriti
cd smriti

cp .env.example .env
# Edit .env to add your API keys (OpenAI, Anthropic, or both).
# Leave keys commented out to use mock mode (no real LLM calls).
#
# Using Ollama or another local model? Set these instead:
#   SMRITI_GENERIC_API_URL=http://localhost:11434/v1
#   SMRITI_GENERIC_MODEL=llama3.1:8b
# See .env.example for details.

docker compose up -d postgres    # start the database
make setup                       # backend venv + deps + migrations + CLI + frontend
```

`make setup` installs the backend, the CLI (`smriti` + `smriti-mcp`), and the frontend. The CLI binaries are installed into the backend venv at `backend/.venv/bin/`. To use them from your shell:

```bash
source backend/.venv/bin/activate
```

### 2. Start the backend and frontend

```bash
make dev              # backend on http://localhost:8000 (keep running)
make dev-frontend     # frontend on http://localhost:5173 (separate terminal)
```

**For the chat UI only, you're done.** Open http://localhost:5173.

### 3. For coding agents

**Quick path:**

```bash
source backend/.venv/bin/activate
smriti init my-project
```

This creates the space, installs skill packs for Claude Code and Codex, and configures the SessionStart hook. Follow the printed next steps.

**MCP config** (Claude Code, Cursor, Windsurf):

```json
{
  "mcpServers": {
    "smriti": {
      "command": "smriti-mcp",
      "env": { "SMRITI_API_URL": "http://localhost:8000" }
    }
  }
}
```

**Skill pack** (teaches the agent when and why to use Smriti):

```bash
smriti skills install claude-code     # → .claude/skills/smriti/SKILL.md
smriti skills install codex           # → AGENTS.md (commit it)
```

**Runtime model.** Postgres runs in Docker. The backend runs locally via `make dev`. The human starts both. Agents are clients of `http://localhost:8000` — they do not manage the backend.

### 4. Auto-inject state at session start (Claude Code)

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          {
            "type": "command",
            "command": "smriti state my-project --compact 2>/dev/null || echo 'Smriti backend not reachable. Start it with: make dev'"
          }
        ]
      }
    ]
  }
}
```

With this hook in `.claude/settings.json`, the state brief is injected automatically at session start. The agent doesn't need to remember to call `smriti_state`.

---

## The single-user story

Smriti started here. Before multi-agent coordination, the problem was simpler: you spend 30 minutes figuring something out, reach a clean decision, and then switch models, come back later, or try a different approach — and you have to reconstruct everything from scratch.

That's still a real problem, and Smriti still solves it:

- **Restore to a clean state** — when a conversation drifts or gets polluted with bad context, restore to an earlier checkpoint. Pre-restore turns are excluded from context at the data layer.
- **Branch your thinking** — fork from any checkpoint to explore a different direction. The original path stays untouched.
- **Compare where reasoning diverged** — structured diff of any two checkpoints showing exactly which decisions differ.
- **Review checkpoint consistency** — surface contradictions, hidden assumptions, resolved questions.
- **Switch models without losing state** — Smriti owns the state. The model is a rendering engine.

The multi-agent coordination layer grew from this foundation. Agents have the same drift and recovery problems as humans, but worse — they can't ask clarifying questions about stale context, and two of them can silently overwrite each other's work.

---

## What it looks like

**Project timeline (LineagePage dashboard)** — the UI shows 56 checkpoints across 2 agents with milestone markers, author badges, and note indicators. Active claims and needs-attention signals are visible in the summary panel.

**Agent-facing state (CLI)** — what every agent reads at session start:

```
$ smriti state smriti-dev --compact

# smriti-dev
Latest checkpoint: `a333bc7` · by `claude-code`
## In progress
- Add task_id to capabilities manifest [implement] (id: cap-task-id)
- Write collision detection test [test] (id: test-collision)
- Update ARCHITECTURE.md [docs] (id: docs-arch-ids)
## Active work
- `claude-code` [test] on `main` — collision detection test (task: test-collision)
- `codex-local` [implement] on `main` — capabilities manifest (task: cap-task-id)
```

**Project metrics** — coordination KPIs computed on demand:

```
$ smriti metrics smriti-dev

## Coordination
56 checkpoints · 2 agents (claude-code: 35, codex-local: 21)
30 cross-agent continuations
37 claims · 100% completion · 3 with task IDs
```

---

## Core concepts

### Space

A container for a line of work. Holds checkpoints and sessions. One project, one Space.

### Checkpoint

A structured snapshot of reasoning state: title, objective, summary, decisions, assumptions, tasks (with intent hints and IDs), open questions, entities, artifacts. Created manually at inflection points — not after every small step.

### Session

A live conversation runtime inside a Space. Can be forked from any checkpoint.

### Claim

A lightweight, time-bounded declaration that an agent is working on something. Advisory, not a lock. Carries `intent_type` and optional `task_id`.

---

## Context modes

- **FRESH** — blank state, no context
- **HEAD** — latest checkpoint + recent turns
- **RESTORED** — specific checkpoint restored, pre-restore turns excluded at the data layer
- **FORKED** — checkpoint base + separate branch

Restored mode is where isolation works. Earlier conversation is not hidden or summarized — it is excluded.

---

## Current limitations

- Single user only — no auth, no multi-tenancy
- No merging of divergent checkpoint branches
- No streaming responses
- No mobile UI

---

## Provider setup

Smriti supports OpenAI, Anthropic, OpenRouter, and any OpenAI-compatible provider (Ollama, LM Studio, vLLM) via the generic provider slot.

Set API keys in `.env`:

```
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
OPENROUTER_API_KEY=...
```

Or use mock mode (no API keys needed) for trying the product without real LLM calls.

## Tech stack

FastAPI · SQLAlchemy · PostgreSQL · React + TypeScript + Vite

---

## Docker

```bash
make up       # start all services
make logs     # follow logs
make down     # stop all services
```

---

## Try the demo

There is a guided walkthrough in `demos/branching-reasoning-demo/` covering the single-user checkpoint/fork/compare workflow. For the multi-agent coordination story, follow the Getting Started section above and run `smriti state` + `smriti metrics` on your own project.
