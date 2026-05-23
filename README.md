# Smriti

**Code has Git. Multi-agent reasoning does not.**

Smriti is version control for project reasoning state — versioned, structured, branchable snapshots of *what was decided*, *what's still open*, and *what each agent is doing right now*. So multiple coding agents can coordinate on the same codebase without overwriting each other's thinking.

When you run multiple coding agents on the same project — Claude Code and Codex, or two Claude Code sessions — they share no state. Each agent starts from scratch, re-discovers decisions already made, and occasionally duplicates work another agent is already doing. The standard workaround is `HANDOFF.md` / `NOTES.md`. That works until reasoning needs to branch, be compared, be restored, or be validated against the actual repo. Smriti gives reasoning state the same primitives Git gives code — plus the coordination primitives Git doesn't have.

---

## The Git analogy

Git preserves *code history*: what changed, when, by whom, on which branch. Smriti preserves *project reasoning*: what was decided, what's still open, what each agent is doing right now, and how the recorded state compares to the live repo.

| Code (Git)              | Reasoning state (Smriti)                                                  |
|-------------------------|---------------------------------------------------------------------------|
| commit                  | **checkpoint** — structured snapshot of reasoning state                    |
| branch                  | **fork** from any checkpoint to explore an alternative                     |
| diff                    | `smriti compare` — structured diff of two checkpoints                      |
| revert / checkout       | `smriti restore` — return to a clean, isolated checkpoint                  |
| working-tree drift      | **repo-state drift** — flags when the repo has moved past the checkpoint   |
| —                       | **active claims** — advisory coordination so agents see each other coming  |
| —                       | **freshness checks** — "has state moved since my base?" before checkpointing |
| —                       | **structured tasks + IDs** — collision detection at the task level         |

The first five rows extend the Git analogy. The last three are coordination primitives Git doesn't have — because Git is built for one human committing serial code, and Smriti is built for multiple agents writing reasoning state in parallel.

---

## Why markdown handoffs aren't enough

Markdown notes (`HANDOFF.md`, `NOTES.md`, etc.) can store free-form context — and for a solo developer working on one model, often that's enough. They start breaking the moment more than one agent needs to coordinate.

Markdown can store notes. It cannot reliably provide:

- **Active claims** — who is working on what right now, with a TTL
- **Freshness checks** — has the state moved since my base, before I checkpoint?
- **Task IDs tied to claims** — collision detection at the task level when agents pick up work
- **Repo-state drift detection** — recorded state vs the live repo, with N-commits-ahead / branch-mismatch surfacing
- **Branchable, comparable, restorable reasoning** — `smriti fork`, `smriti compare`, `smriti restore`
- **A current-state surface** — one well-defined brief multiple agents read at session start

The fundamental difference: markdown is *prose*. Smriti is *structured, versioned, queryable state*. Markdown describes what you were thinking; Smriti lets the next session pick up where you left off — without re-reading prose, without two agents redoing the same work, without lying about the repo.

---

## Getting started

The core coordination loop runs entirely on a local SQLite file — **no Docker, no API keys, no cloud required.** API keys come in only for the optional LLM-assisted features (more below).

You'll need Python 3.11+ and Node 20.19+ / 22.12+.

### 1. Install (local-first)

```bash
git clone https://github.com/himanshudongre/smriti
cd smriti
make setup-local              # backend venv + CLI + frontend, no Docker
```

`make setup-local` creates a `.env` from the example, installs the backend, the CLI (`smriti` + `smriti-mcp`), and the frontend. The CLI binaries live in `backend/.venv/bin/` — `source backend/.venv/bin/activate` puts them on your PATH.

Start the backend in one terminal and keep it running:

```bash
make dev-local                # backend on http://localhost:8000
```

In a second terminal, activate the CLI before running `smriti` commands:

```bash
cd smriti
source backend/.venv/bin/activate
```

Local mode stores state in SQLite at `~/.smriti/smriti.db`. For a shared/team setup with Postgres, see [Shared / team mode](#shared--team-mode-postgres) below.

For the chat UI, run `make dev-frontend` in a separate terminal and open http://localhost:5173.

### 2. Confirm install — `smriti doctor`

```bash
smriti doctor
```

Backend reachable, CLI/backend versions aligned, provider status. If anything's off, doctor tells you what.

### 3. See Smriti at work — `smriti quickstart`

```bash
smriti quickstart
```

Seeds a `smriti-demo` Space — one finished mini-project (a rate-limiting feature built by two agents, with a branch explored and dropped) — and prints a ~3-minute guided walkthrough. Works without API keys — quickstart seeds pre-built checkpoints, no live extraction. (For live `--extract` you need a real provider; see [Provider configuration](#provider-configuration-llm-backed-features).) Clean up with `smriti quickstart --remove`.

### 4. Attach your own project — `smriti init`

`cd` into the project you want to attach. `smriti init` writes project-local files (skill packs, SessionStart hook, attachment record) into the current directory, so it attaches whichever project you're standing in — running it in the wrong directory attaches the wrong project.

```bash
cd /path/to/your-project       # your own project, not the Smriti repo
smriti init my-project
```

`smriti init`:
- creates a Space named `my-project`
- installs the Claude Code and Codex skill packs into the project
- writes the SessionStart hook for Claude Code
- writes `.smriti.json` at the repo root, binding this repo to the Space

The MCP config block `smriti init` prints is ready to paste into Claude Code, Cursor, or Windsurf. The shape:

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

Use the resolved path from `smriti init` rather than a bare `"smriti-mcp"` — a bare command name only works if it's on the MCP host's PATH, which a venv install usually isn't.

Use `smriti attach <space>` to bind (or re-bind) a repo to an existing Space without the full `init`.

**Multiple projects.** Attachment is per-project-directory, not global. Everything `smriti init` writes — `.smriti.json`, the SessionStart hook in `.claude/settings.json`, and the skill packs (`.claude/skills/smriti/SKILL.md` and `AGENTS.md`) — lives *inside the project directory*. Run `smriti init` once per project; the files for `~/code/project-a` and `~/code/project-b` never see each other. A Claude Code or Codex session opened in `~/code/project-a` automatically lands on space `project-a`; the same agent opened in `~/code/project-b` lands on `project-b`. The MCP server registration (the JSON block above) is machine-wide but stateless — every MCP call passes `space="..."` explicitly, so the server has no "current space" of its own.

### 5. Daily workflow — no `<space>` needed

Inside an attached repo, the everyday commands resolve the Space from `.smriti.json`:

```bash
smriti state                   # continuation brief — read first each session
smriti current                 # compact snapshot: direction, attention, open work
smriti metrics                 # project coordination KPIs
```

The SessionStart hook `smriti init` wrote will inject `smriti state --compact` at the start of each Claude Code session. The hook is space-agnostic — one hook works in every attached project.

The exact hook block (what `smriti init` writes into `.claude/settings.json`):

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

### Shared / team mode (Postgres)

Postgres remains the stronger shared/team backend — an explicit database service, Docker-backed state, and the closer path toward a hosted deployment.

```bash
cp -n .env.example .env
# In .env, set:
#   SMRITI_DB_MODE=postgres
#   DATABASE_URL=postgresql://smriti:smriti@localhost:5432/smriti

make setup-postgres              # starts Docker Postgres and runs migrations
make dev-postgres                # backend on http://localhost:8000
make dev-frontend                # frontend on http://localhost:5173
```

---

## What you get

The primitives that turn "shared state" from a phrase into something that actually works for multiple agents:

- **Versioned reasoning.** Every checkpoint is a structured snapshot — objective, decisions, assumptions, tasks (with intent hints and IDs), open questions, entities, artifacts. Fork from any checkpoint to explore an alternative; `smriti compare` for a structured diff; `smriti restore` to return to a clean state. Pre-restore turns are excluded from context at the data layer, not just hidden.
- **Active work claims.** Agents declare intent before starting. Claims are advisory (not locks), time-bounded, and visible to every other agent via the state brief. Two agents see each other coming.
- **Structured tasks + IDs.** Checkpoint tasks carry optional `intent_hint`, `blocked_by`, `status` (open/done), and stable `id` slugs. Agents pick complementary work from the task list; claims can reference a specific task ID (`--task-id impl-1`) for precise collision detection when two agents start near-simultaneously.
- **Freshness checks** (`--since`). "Has the state moved since my base?" — checked before checkpointing, so an agent never writes on top of stale assumptions.
- **Repo-state drift detection.** `smriti state` compares the working git repo against the HEAD and branch the latest checkpoint recorded, surfacing dirty trees, detached HEAD, project-root mismatch, and N-commits-ahead-of-the-checkpoint signals. The reasoning state stops being "trust me" — it tells you when it may be stale.
- **Project Current State** (`smriti current`). A compact, packaged snapshot of where a project is right now: current direction, attention signals, active work, open tasks by intent, recent milestones, recent activity. Founder- and agent-facing.
- **Worktrees.** First-class git worktree primitive so multiple agents work on the same project without sharing one checkout. Each agent gets its own working tree; claims can bind to a worktree, and the state brief surfaces per-claim drift (branch, dirty count, ahead/behind vs `origin/main`).
- **Backend capability manifest + `smriti doctor`.** `/health` advertises the backend's feature surface so agents can detect a stale backend running old code; `smriti doctor` diagnoses backend reachability, runtime/code mismatches, and provider status.
- **Destructive-action guards.** Deleting a Space that still holds checkpoints requires an explicit `--force` (CLI), an echo-back `confirm_space` argument (MCP), or `force=true` (API). Real reasoning state cannot be wiped by one careless flag.

---

## Four surfaces, one core

1. **CLI** (`smriti`) — how a coding agent reads and writes reasoning state from a shell tool loop.
2. **MCP server** (`smriti-mcp`) — the same surface as 21 MCP tools for Claude Code, Cursor, Windsurf.
3. **Agent skill pack** — versioned instructions teaching agents *when* to checkpoint (and critically *when not to*), when to fork, how to detect drift, and how to pick complementary work. Install once per project.
4. **Chat UI** — how a human reads, steers, and debugs shared state.

---

## What Smriti is not

- **Not an orchestrator.** Smriti describes state. It does not assign tasks, schedule work, or route agents. Agents make their own decisions from shared metadata.
- **Not a task manager.** Tasks live inside checkpoints as structured fields. No separate task table, no Jira-like lifecycle, no assignment system.
- **Not a memory database.** Smriti stores structured reasoning snapshots at inflection points, not a running log of everything an agent said or saw.
- **Not markdown.** `HANDOFF.md` / `NOTES.md` handoffs work until you need claims, freshness, branching, drift detection, or coordination at all.
- **Not production infrastructure (yet).** Single demo user, no auth, no multi-tenancy. Works for solo builders running multi-agent workflows.

---

## Provider configuration (LLM-backed features)

Smriti draws a hard line between **core coordination** (works with no API key) and **LLM-backed features** (require a configured provider).

### Works with no key

- `setup` / `doctor` / `quickstart`
- `smriti state` / `current` / `metrics`
- claims (`smriti claim`, claim listing)
- attach / no-arg project workflow
- manual structured checkpoints (`smriti checkpoint create <space>` with a JSON payload on stdin)
- repo-state drift detection
- the chat UI's read-only dashboards (timeline, checkpoints, claims, drift signals)

### Require a real provider

- `smriti checkpoint create --extract` — extracts structured fields from freeform markdown
- `smriti checkpoint review` — consistency review of a checkpoint
- checkpoint draft
- the chat UI's send loop — where the agent actually responds

Without a configured provider, these refuse to run rather than silently return placeholder content. `--extract` returns **HTTP 412 Precondition Failed** with an actionable error listing the configuration paths. **Mock content is never silently committed into a real project** — that would pollute reasoning state, which Smriti exists to keep trustworthy.

### Configure a provider

Set one of these in `.env` (or your shell):

```
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
OPENROUTER_API_KEY=...
```

Or, for a **local OpenAI-compatible model** (Ollama, LM Studio, vLLM, Together, etc.):

```
SMRITI_GENERIC_API_URL=http://localhost:11434/v1   # your local server
SMRITI_GENERIC_MODEL=llama3.1:8b
# SMRITI_GENERIC_API_KEY=not-required               # most local servers don't need one
```

Then set `background_intelligence.provider: generic` in `backend/config/providers.yaml`.

Extraction is a relatively lightweight structured-output task and is usually handled well by cost-efficient or local OpenAI-compatible models. That said, *quality varies by model* — validate with `smriti checkpoint create --extract --dry-run` on a representative document before relying on a small model for real work.

After configuring, run `smriti doctor` (optionally with `--strict`) to confirm the background provider line reads `ready`. `--strict` exits non-zero (EX_CONFIG / 78) if the provider is `mock_or_disabled`, which makes it safe to use in CI before any `--extract` step.

### Mock mode

A deterministic `MockAdapter` exists for tests, demos, and the `quickstart` mechanics. It returns a fixed JSON blob (containing literal strings like `"Mock decision from provider"`). **It is never the default for `--extract`** — it only runs when the caller explicitly opts in (e.g. tests passing `use_mock=true` to the HTTP endpoint). Do not commit mock-extracted content into a real project Space.

---

## Built with Smriti

The coordination substrate was built using Claude Code and Codex working in parallel on the same codebase, coordinating through Smriti's own state. `smriti metrics smriti-dev`:

- **117 checkpoints** across **2 agents** (Claude Code: 70, Codex: 47)
- **61 cross-agent continuations** — checkpoints where a different agent picked up where the previous one left off
- **77 work claims** at **96% completion** — nearly every declared intent finished
- **7 milestones** marking proven coordination proofs

The strongest proof: two agents started near-simultaneously, read the same task surface (4 tasks with stable IDs and intent hints), and independently picked different complementary tasks — one chose `[test]`, the other chose `[implement]` — without any human routing. No orchestrator. No task queue. Just structured metadata on shared state.

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

- **Space** — a container for a line of work. Holds checkpoints and sessions. One project, one Space.
- **Checkpoint** — a structured snapshot of reasoning state (title, objective, summary, decisions, assumptions, tasks with intent hints and IDs, open questions, entities, artifacts). Created at inflection points — not after every small step.
- **Session** — a live conversation runtime inside a Space. Can be forked from any checkpoint.
- **Claim** — a lightweight, time-bounded declaration that an agent is working on something. Advisory, not a lock. Carries `intent_type` and optional `task_id`.

## Context modes

- **FRESH** — blank state, no context
- **HEAD** — latest checkpoint + recent turns
- **RESTORED** — specific checkpoint restored; pre-restore turns excluded at the data layer
- **FORKED** — checkpoint base + separate branch

Restored mode is where isolation actually works. Earlier conversation is not hidden or summarized — it is excluded.

---

## Current limitations

- Single user only — no auth, no multi-tenancy
- No merging of divergent checkpoint branches
- No streaming responses
- No mobile UI

---

## Tech stack

FastAPI · SQLAlchemy · PostgreSQL / SQLite · React + TypeScript + Vite

## Docker (Postgres mode helpers)

```bash
make up       # start all services
make logs     # follow logs
make down     # stop all services
```

## Try the demo

The fastest way to see Smriti work is `smriti quickstart` (Getting started, step 3). For a deeper single-user walkthrough — checkpoint / fork / compare — see `demos/branching-reasoning-demo/`.
