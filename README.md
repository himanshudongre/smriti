# Smriti

A shared reasoning-state backend that lets multiple coding agents coordinate on the same project — without an orchestrator.

---

## What Smriti does

When you run multiple coding agents on the same project — Claude Code and Codex, or two Claude Code sessions — they have no shared state. Each agent starts from scratch, re-discovers decisions already made, and occasionally duplicates work another agent is already doing. The current workaround is markdown handoff files (`HANDOFF.md`, `NOTES.md`), which break the moment reasoning branches or two agents need to work in parallel.

Smriti replaces that with a structured reasoning-state layer. Agents read the current state at session start, declare what they're working on, and checkpoint their thinking at meaningful inflection points. The state is structured — decisions, assumptions, tasks, open questions, artifacts — not prose. It's branchable, comparable, restorable, and visible to every agent working on the project.

---

## Built with Smriti

The entire coordination substrate was developed with Claude Code and Codex working in parallel on the same codebase, coordinating through Smriti's own state. Current project metrics (`smriti metrics smriti-dev`):

- **117 checkpoints** across **2 agents** (Claude Code: 70, Codex: 47)
- **61 cross-agent continuations** — checkpoints where a different agent picked up where the previous one left off
- **77 work claims** at **96% completion** — nearly every declared intent finished
- **7 milestones** marking proven coordination proofs

The strongest proof: two agents started near-simultaneously, read the same task surface (4 tasks with stable IDs and intent hints), and independently picked different complementary tasks — one chose `[test]`, the other chose `[implement]` — without any human routing. No orchestrator. No task queue. Just structured metadata on the shared state.

---

## How it works

### Four surfaces on the same core

1. **A CLI** (`smriti`) — how a coding agent reads and writes reasoning state from a shell tool loop.
2. **An MCP server** (`smriti-mcp`) — the same surface wrapped as 21 MCP tools for Claude Code, Cursor, and Windsurf.
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
- **Repo-state drift detection** — `smriti state` compares the working git repo against the HEAD and branch the latest checkpoint recorded, flagging when the repo has moved on (commits ahead of the checkpoint, a different branch, a dirty tree). The reasoning state stops being "trust me" — it tells you when it may be stale.
- **Branch disposition** — branches are explicitly marked `integrated`, `abandoned`, or `active` so the state brief stays clean.
- **Checkpoint notes** — additive annotations (note, milestone, noise) on existing checkpoints without modifying the immutable reasoning state.
- **Backend capabilities** (`/health`) — the backend advertises its feature surface so agents can detect stale backends. `smriti doctor` diagnoses backend reachability and runtime/code mismatches.
- **Compact mode** (`--compact`) — artifact content omitted for token efficiency; labels and recovery instructions preserved.
- **Project metrics** (`smriti metrics <space>`) — coordination, state quality, and branch lifecycle KPIs computed on demand from existing data.
- **Project Current State** (`smriti current <space>`) — a compact, packaged snapshot of where a project is right now: current direction, counts, attention signals, active work, recent milestones, open tasks by intent, and recent activity. Founder- and agent-facing; also rendered as a panel in the chat UI.
- **Worktrees** (`smriti worktree open/list/show/close`) — first-class git worktree primitive so multiple agents can work on the same project without sharing one checkout. Each agent gets its own working tree and staging index, eliminating the cross-agent commit pollution failure mode that motivated the feature. Claims can be bound to a worktree (`smriti claim create --worktree <id>`); the state brief surfaces per-claim working-tree drift (branch, dirty count, ahead/behind vs origin/main, last commit) so agents can see what other agents are editing without asking. The skill pack teaches the reflex.
- **Destructive-action guards** — deleting a Space that still holds checkpoints requires an explicit `--force` (CLI), an echo-back `confirm_space` argument (MCP tool), or `force=true` (API). Real reasoning state cannot be wiped by a single careless flag.

---

## What Smriti is not

- **Not an orchestrator.** Smriti describes state. It does not assign tasks, schedule work, or route agents. Agents make their own decisions from shared metadata.
- **Not a task manager.** Tasks live inside checkpoints as structured fields. There is no separate task table, no Jira-like lifecycle, no assignment system.
- **Not a memory database.** Smriti stores structured reasoning snapshots at inflection points, not a running log of everything an agent said or saw.
- **Not production infrastructure (yet).** Single demo user, no auth, no multi-tenancy. Works for solo builders running multi-agent workflows.

---

## Getting started

You will need: Python 3.11+ and Node 20.19+ or Node 22.12+. Docker is
only needed for Postgres/shared-team mode.

### 1. Clone and set up for solo/local mode

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

make setup-local                 # backend venv + CLI + frontend, no Docker
```

Local mode uses SQLite at `~/.smriti/smriti.db` by default. Override it
with `SMRITI_LOCAL_DB_PATH=/path/to/smriti.db` if you want the database
somewhere else.

`make setup-local` installs the backend, the CLI (`smriti` + `smriti-mcp`), and the frontend. The CLI binaries are installed into the backend venv at `backend/.venv/bin/`. To use them from your shell:

```bash
source backend/.venv/bin/activate
```

### 2. Start the backend and frontend

```bash
make dev-local        # backend on http://localhost:8000 (keep running)
make dev-frontend     # frontend on http://localhost:5173 (separate terminal)
```

**For the chat UI only, you're done.** Open http://localhost:5173.

### Shared/team mode with Postgres

Postgres remains the stronger shared/team mode. Use it when you want an
explicit database service, Docker-backed state, or a closer path toward a
hosted deployment.

```bash
cp .env.example .env
# In .env, set:
#   SMRITI_DB_MODE=postgres
#   DATABASE_URL=postgresql://smriti:smriti@localhost:5432/smriti

make setup-postgres              # starts Docker Postgres and runs migrations
make dev-postgres                # backend on http://localhost:8000
make dev-frontend                # frontend on http://localhost:5173
```

If `DATABASE_URL` is explicitly set to a Postgres URL, Smriti preserves
Postgres behavior.

### 3. See Smriti work — do this first

Before connecting your own project, watch Smriti work on a project that
already has reasoning state in it. This is the fastest way to understand what
it is for — and it keeps you from opening to an empty space.

In a new terminal:

```bash
source backend/.venv/bin/activate

smriti doctor                  # confirm the backend and CLI are healthy
smriti quickstart              # seed a demo space, then print a guided walkthrough
```

`smriti quickstart` seeds `smriti-demo` — one small, finished project (a
rate-limiting feature built by two agents, with a branch explored and then
dropped) — and prints a short, guided ~3-minute walkthrough of it. It shows
the real shape of a Smriti project instead of an empty space, and it works in
mock mode with no API key. Clean it up afterward with `smriti quickstart --remove`.

### 4. Connect your own project (coding agents)

Now point Smriti at a real project. In the same terminal where you activated
the venv (step 3):

```bash
cd /path/to/your-project       # your own project — NOT the Smriti repo
smriti init my-project
```

Run `smriti init` from **inside your own project's directory**. It writes the
skill pack and the `SessionStart` hook into the current directory, so running
it from the Smriti repo would wire up Smriti's own repo by mistake. It creates
the space, installs the Claude Code and Codex skill packs, configures the
SessionStart hook, and prints the exact next steps to follow.

It also **attaches** the repo to that space — a small `.smriti.json` file at
the repo root. From then on, `smriti` commands run inside the repo resolve the
space automatically: `smriti state`, `smriti current`, `smriti claim …` need no
space argument, and a Claude or Codex session opened anywhere in the repo
connects to the right space on its own. Use `smriti attach <space>` to attach a
repo (or re-point one) without the full `init`.

Once attached, the everyday commands need no `<space>` argument — run them from
anywhere inside the repo:

```bash
smriti state                   # the continuation brief — read first each session
smriti current                 # compact snapshot: direction, attention, open work
smriti metrics                 # project coordination KPIs
```

**MCP config** (Claude Code, Cursor, Windsurf). `smriti init` prints a
ready-to-paste MCP config block with the executable path and API URL already
resolved for your machine — use what it prints. If you configure MCP manually
instead, activate the Smriti venv first and use the absolute path from
`which smriti-mcp` so the host does not pick up a stale executable. The shape:

```json
{
  "mcpServers": {
    "smriti": {
      "command": "/absolute/path/to/smriti-mcp",
      "env": { "SMRITI_API_URL": "http://localhost:8000" }
    }
  }
}
```

Use the resolved path from `smriti init` rather than a bare `"smriti-mcp"` — a
bare command name only works if `smriti-mcp` is on the MCP host's PATH, which
it usually is not for a venv install.

**Skill pack** (teaches the agent when and why to use Smriti). `smriti init`
already installs both — run these only to reinstall or upgrade:

```bash
smriti skills install claude-code     # → .claude/skills/smriti/SKILL.md
smriti skills install codex           # → AGENTS.md (commit it)
```

**Runtime model.** In solo/local mode, Smriti stores state in a SQLite
file and the backend runs locally via `make dev-local`. In shared/team
mode, Postgres runs in Docker and the backend runs via `make dev-postgres`.
Agents are clients of `http://localhost:8000` — they do not manage the
backend.

### 5. Auto-inject state at session start (Claude Code)

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          {
            "type": "command",
            "command": "smriti state --compact 2>/dev/null || echo 'Smriti backend not reachable. Start it with: make dev-local'"
          }
        ]
      }
    ]
  }
}
```

`smriti init` already writes this hook into `.claude/settings.json`, with the `smriti` path resolved for your machine — the block above is what it generates. The hook is space-agnostic — `smriti state --compact` resolves the space from the repo's `.smriti.json`, so one hook works in every project. With the hook in place, the state brief is injected automatically at session start; the agent doesn't need to remember to call `smriti_state`.

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

### Project timeline (dashboard)

![Smriti LineagePage dashboard](docs/assets/lineage-dashboard.png)

*Real project timeline from building Smriti with Smriti: summary panel, checkpoint cards with author badges, note indicators, needs-attention signal.*

### Agent-facing state and metrics (CLI)

![CLI state and metrics](docs/assets/cli-state-and-metrics.png)

*What every agent reads at session start (`smriti state --compact`) and the project health KPIs (`smriti metrics`).*

### Structured checkpoint detail

![Checkpoint detail with structured tasks and notes](docs/assets/checkpoint-detail.png)

*The autonomy milestone checkpoint — structured tasks with intent badges, task IDs, and a founder milestone note annotating the first clean autonomous complementary-work proof.*

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

**Mock mode.** With no API keys set, Smriti runs in mock mode. Setup, the chat
UI, the CLI, `smriti quickstart`, and the whole coordination flow work
normally — but the LLM-backed paths (`smriti checkpoint create --extract`,
checkpoint draft, and review) return deterministic placeholder content instead
of real extraction. Mock mode is good for trying the mechanics; add an API key
when you want real structured checkpoints pulled from freeform notes.

## Tech stack

FastAPI · SQLAlchemy · PostgreSQL / SQLite · React + TypeScript + Vite

---

## Docker

```bash
make up       # start all services
make logs     # follow logs
make down     # stop all services
```

---

## Try the demo

The fastest way to see Smriti work is `smriti quickstart` — it seeds a demo
space and prints a guided walkthrough (see Getting started, step 3).

For a deeper single-user walkthrough, `demos/branching-reasoning-demo/` covers
the checkpoint / fork / compare workflow step by step.
