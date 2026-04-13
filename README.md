# Smriti

Version control for reasoning.

---

## Why I ended up building this

I was switching between ChatGPT, Claude, Cursor etc while working on problems, and something kept breaking.

Not the models. My own context.

I would spend 30-40 minutes figuring something out, reach a clean decision and then:

- switch models
- come back later
- try a different approach

and suddenly I had to reconstruct everything again.

Worse, sometimes the conversation itself would drift. I would keep adding messages, and eventually the model was building on confused or contradictory context. Once that happens, it is hard to recover. You either keep patching the thread or restart from scratch.

That is what pushed me to build this.

---

## The core idea

Instead of treating conversations as logs, treat the **state of reasoning** as something explicit and structured.

A **checkpoint** captures where you are:

- what you figured out
- decisions you made
- assumptions you are relying on
- what is still open
- what needs to be done
- artifacts you want to preserve (code, plans, key outputs)

When reasoning drifts or goes wrong, you can **restore to a clean checkpoint** and continue from there. The earlier conversation is excluded from context entirely. Not hidden, not summarized. Actually excluded at the data layer.

You can also **branch your thinking** from any checkpoint, explore a different direction, and later **compare** where the two paths diverged.

---

## Demo

![Smriti checkpoint diff](docs/assets/checkpoint-diff.png)

*Comparing two checkpoints: one exploring retrieval-heavy architecture, the other a state-first approach. Smriti shows exactly where the decisions diverged.*

Watch demo (3-4 min):
https://www.loom.com/share/0531ab1b6f114ceb9996ec5780052158

---

## The problem

You spend an hour working through something. You finally reach clarity. Then you need to:

- step away and come back later
- switch to a different model
- revisit an earlier direction

And everything falls apart. There is no clean way to:

- return to that exact state of thinking
- branch thinking without messing up the original
- switch models without re-explaining everything
- recover from a conversation that went wrong

The more you work with multiple models and complex problems, the worse this gets.

**Reasoning state becomes the bottleneck.**

---

## What this lets you do

### Restore to a clean state

When a conversation drifts or gets polluted with bad context, restore to an earlier checkpoint. Pre-restore turns are visually dimmed and excluded from context. The model only sees the checkpoint state and your new messages.

### Branch your thinking

Fork from any checkpoint to explore a different direction. The original path stays untouched. Both branches live in the same space and can be compared.

### Compare where reasoning diverged

Side-by-side structured diff of any two checkpoints. See exactly which decisions differ, which assumptions changed, what questions were resolved differently.

### Review checkpoint consistency

Run a review on any checkpoint to surface reasoning issues: possible contradictions between decisions, hidden assumptions that should be explicit, open questions that were already resolved, and entities that are disconnected from the reasoning.

### Track assumptions separately from decisions

Assumptions are things your reasoning takes for granted. Decisions are explicit choices. Smriti keeps them separate because when reasoning goes wrong, you need to know whether a bad decision was made or whether it was built on an unexamined assumption.

### Attach real artifacts

Capture assistant responses, code snippets, plans, or other outputs directly into a checkpoint. When the checkpoint is active, these artifacts are included in the model's context. The reasoning is grounded in actual content, not just summaries of what was discussed.

### Switch models without losing state

Smriti owns the reasoning state. The model is just a rendering engine. Switch from GPT-4o to Claude to Llama mid-session without re-explaining anything.

### See who is working on what (work claims)

Before starting work, an agent declares a lightweight claim — "I'm about to work on X." Other agents reading the state see the active claims and avoid collision. Claims are advisory, not locks. They expire automatically if an agent forgets to close them. This is Smriti's first concurrency primitive, designed for multi-agent workflows where two coding agents might otherwise start the same task simultaneously.

---

## When to use Smriti

**Use it when:**

- you are working through something complex over multiple sessions
- you need to explore multiple approaches and compare them
- your conversation has drifted and you want to recover cleanly
- you are switching between models and need context continuity
- you want to preserve specific outputs alongside your reasoning state
- multiple coding agents (Claude Code, Codex, etc.) are working on the same project and need shared continuity

**Probably not needed when:**

- quick one-shot questions
- simple tasks that don't involve evolving reasoning
- anything where context starts fresh each time

---

## One thing I did differently

Most systems rely on prompts to manage context. I didn't.

When you restore a checkpoint, I enforce boundaries in the data layer itself. Only the relevant turns are visible. Nothing from the future leaks in. Nothing from other sessions sneaks in.

It is stricter than typical chat systems. But it felt important to try.

---

## Smriti is a backend, not just a chat app

I initially built this thinking about chat, but the more I worked on it, the more it felt like a reasoning-state backend that happens to have a chat UI on top. Agents have the same drift / recovery / handoff problems as humans, just worse.

The concrete use case that drove this direction: working on a coding project and wanting to switch between different coding agents mid-project. Context reset every time. Markdown handoff files that broke down the moment reasoning branched. The strengths Smriti already had — checkpoints, restore, fork, compare, assumptions, artifacts, model interchangeability — mapped directly onto that pain.

So Smriti now has four surfaces on the same core:

1. **The chat UI**: how a human reads, steers, and debugs shared reasoning state. Still the primary way I inspect what is happening in a project.
2. **A CLI** (`smriti`): how a coding agent reads and writes the same reasoning state from a shell tool loop. Works from any host that can run a shell command. `smriti state` is multi-branch by default — it shows main plus active non-main branches plus a lightweight divergence signal when agents disagree on decisions.
3. **An MCP server** (`smriti-mcp`): the same surface, wrapped as 16 MCP tools for hosts that speak the Model Context Protocol natively (Claude Code, Cursor, Windsurf). Agents call `smriti_state`, `smriti_create_checkpoint`, `smriti_fork`, etc. as structured tool calls instead of shelling out.
4. **An agent skill pack**: a versioned markdown instruction file installed into an agent host's project directory (`.claude/skills/smriti/SKILL.md` for Claude Code, `AGENTS.md` for Codex). The skill pack teaches the agent *when* and *why* to use Smriti's tools — when to checkpoint, critically when NOT to checkpoint, when to fork, how to detect drift, and the explicit anti-patterns to reject. Install it once per project with `smriti skills install <target>` and Smriti becomes the agent's default reflex instead of a tool it has to remember to call.

One project, one Smriti Space, multiple agents reading from and writing to the same structured state. Agents don't need to know about each other. They just need to (a) know how to read the current state and write a checkpoint at each inflection point, which is what the skill pack teaches, and (b) see each other's work on that state, which is what multi-branch `smriti state` makes visible.

See `cli/README.md` for all three agent-facing surfaces (CLI, MCP, skill pack). Quick taste:

```bash
smriti state my-project                                    # continuation brief
cat handoff.md | smriti checkpoint create my-project --extract   # structured commit from freeform markdown
smriti checkpoint review <id>                              # consistency check before handing off
smriti fork <id> --branch experiment                       # branch off a checkpoint
smriti compare <id-a> <id-b>                               # structured diff of two checkpoints
```

Or from inside Claude Code, after adding `smriti-mcp` to your MCP config: "*show me the current state of my-project*" → the agent calls `smriti_state(space="my-project")` and the brief lands in its context.

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
# .env is the primary config path. config/providers.yaml is optional
# and gitignored — you do not need it for a standard setup.

docker compose up -d postgres    # start the database
make setup                       # backend venv + deps + migrations + CLI + frontend
```

`make setup` installs the backend, the CLI (`smriti` + `smriti-mcp`), and the frontend. The CLI binaries are installed into the backend venv at `backend/.venv/bin/`. To use them from your shell, activate the venv:

```bash
source backend/.venv/bin/activate
```

Or reference them by full path (e.g. `backend/.venv/bin/smriti state ...`). The SessionStart hook in `.claude/settings.json` already uses the full path so it works without activation.

### 2. Start the backend and frontend

```bash
make dev              # backend on http://localhost:8000 (keep running)
make dev-frontend     # frontend on http://localhost:5173 (separate terminal)
```

**For the chat UI only, you're done.** Open http://localhost:5173.

### 3. For coding agents, continue here

**Quick path:** if you just want everything set up in one command:

```bash
source backend/.venv/bin/activate
smriti init my-project
```

This creates the space, installs skill packs for Claude Code and Codex, and configures the SessionStart hook. Follow the printed next steps for MCP config and committing `AGENTS.md`. Skip to step 4 if you used `smriti init`.

**Manual path (or if you want to understand each step):**

**Runtime model.** Postgres runs in Docker. The backend runs locally via `make dev`. The human starts both. Agents are clients of `http://localhost:8000` — they do not start, restart, or manage the backend or Docker.

**3a. Configure your MCP host** (Claude Code, Cursor, Windsurf — skip for Codex):

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

Add this to your host's MCP config file and restart the host. The `smriti_*` tools appear in the tool picker. Codex uses the CLI directly and does not need MCP.

**3b. Install the skill pack** so the agent knows *when* and *why* to use Smriti:

```bash
smriti skills install claude-code     # → .claude/skills/smriti/SKILL.md

smriti skills install codex           # → AGENTS.md (commit it so Codex sees it)
git add AGENTS.md && git commit -m "Add Smriti skill pack for Codex"
```

**3c. Create a space and start working:**

```bash
smriti space create my-project --description "What this project is about"
smriti state my-project               # your agent's first action, every session
```

### 4. Auto-inject state at session start (Claude Code)

Claude Code supports SessionStart hooks that run a command before the agent processes the first prompt. Add a `.claude/settings.json`:

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

With this hook, the state brief is injected in compact mode — artifact content is omitted to save tokens, but artifact labels and a recovery command are included. The agent doesn't need to remember to call `smriti_state`. See `CLAUDE.md` for the project-level instructions that complement the hook.

### 4b. Codex equivalent (optional, local-only)

Codex does not support session hooks. Its closest equivalent is:

- repo-local `AGENTS.md` for the shared project contract
- an optional user-local `developer_instructions` entry in `~/.codex/config.toml`

Example:

```toml
developer_instructions = """
When the current working directory is /path/to/your/project, begin by saying "Reading current state from Smriti." and run `smriti state my-project --compact` before reading files or taking substantive action. Then follow AGENTS.md exactly. Outside this repo, ignore this instruction.
"""
```

This is local-only configuration. Do not commit `~/.codex/config.toml`.

### Why this is better than markdown handoffs

Smriti checkpoints are structured, branchable, comparable, and restorable. When reasoning drifts or an agent goes in the wrong direction, you can restore to a clean checkpoint and the bad context is excluded — not summarized, not hidden, actually excluded at the data layer. Markdown handoff files can't do that, and they fall apart the moment two agents need to work in parallel.

---

## Docker (if you prefer that)

```bash
make up
make logs
make down
```

---

## Try the demo properly

There is a full walkthrough here:

demos/branching-reasoning-demo/

It includes exact steps, what to type, and expected outcomes. Written so people don't have to guess how to use this.

---

## Core concepts

### Space

A container for a line of work. Holds checkpoints and sessions. Think of it like a repo, but for thinking.

### Session

Your live conversation. It may or may not be attached to a Space. You can switch models here without losing history.

### Checkpoint

The main abstraction. A structured snapshot of reasoning state:

- title and objective
- summary of what was figured out
- decisions (explicit choices made)
- assumptions (things taken for granted)
- tasks (concrete action items)
- open questions (unresolved issues)
- entities (key concepts and terms)
- artifacts (attached content: plans, code, outputs)

You create checkpoints manually. I tried auto-checkpointing early on. It just created noise. The system can help draft and review checkpoints, but the signal for when to checkpoint comes from you.

### Turn

One message. Either user or assistant. Append-only.

---

## Context modes

- **FRESH** -> nothing, blank state
- **HEAD** -> latest checkpoint + recent turns
- **RESTORED** -> specific checkpoint restored, only new turns visible
- **FORKED** -> checkpoint base + separate branch

Restored mode is the key one. That is where isolation actually works. Earlier conversation is excluded, and the model continues from a clean checkpoint state.

---

## How it works

Start a session -> attach a Space -> have a conversation -> create a checkpoint -> restore / fork / compare / review

Nothing complicated. The value shows up when your thinking evolves, drifts, or branches.

---

## Current limitations

- single user only
- no merging of branches
- no streaming responses
- no mobile

I'm still refining whether this abstraction is exactly right. The core question: does treating reasoning state as explicit, versioned, and structured actually help? Or is raw conversation history already good enough?

---

## Provider setup

You can use:

- OpenAI
- Anthropic
- OpenRouter

Either via YAML:

backend/config/providers.yaml

or env variables:

```
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
OPENROUTER_API_KEY=...
```

There is also a mock mode for trying the product without API keys.

---

## Tech stack

- FastAPI
- SQLAlchemy
- PostgreSQL
- React + TypeScript + Vite

---

## Where this is going

The chat UI is not going away — it is how I read, steer, and debug what is happening. But the thing underneath the chat UI, the CLI, the MCP server, and the skill pack is a shared reasoning-state layer that any client can read from and write to. Five rounds of dogfood testing exercised the basic handoff loop end to end; transport parity landed; the next gap was that agents didn't reliably know when or why to use the tools. That gap is what the skill pack closes — the workflow heuristics (when to checkpoint, when NOT to checkpoint, how to detect drift) live in the agent's system context as a versioned markdown instruction file installed into the project directory, and `smriti state` is multi-branch by default so the first command an agent runs on a shared project actually shows the other agents' work.

What I care about right now: two different coding agents working on the same project, handing off cleanly through Smriti, surfacing their disagreements through the divergence signal when they diverge, and neither of them ever writing `HANDOFF.md`. When that holds reliably, Smriti is the default backend for multi-agent coding. The questions I'm still chasing are shape questions — is this the right mental model, are these the right checkpoint fields, does the pattern scale past single-user — not transport questions and not tool-fluency questions.

---

## Why I am sharing this

I am mainly trying to validate the idea, not the implementation. The implementation is early.

What I care about is whether this way of thinking about reasoning actually helps, or whether chat history is already good enough and I am overcomplicating it.

Happy to get blunt feedback.
