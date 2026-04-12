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
3. **An MCP server** (`smriti-mcp`): the same surface, wrapped as 13 MCP tools for hosts that speak the Model Context Protocol natively (Claude Code, Cursor, Windsurf). Agents call `smriti_state`, `smriti_create_checkpoint`, `smriti_fork`, etc. as structured tool calls instead of shelling out.
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

## Quick start

You will need:

- Python 3.11+
- Node 18+
- PostgreSQL 14+

```bash
git clone https://github.com/himanshudongre/smriti
cd smriti

cp .env.example .env

make setup

# backend
make dev

# frontend (separate terminal)
make dev-frontend
```

Frontend: http://localhost:5173
Backend: http://localhost:8000

There is also a mock mode if you don't want to deal with API keys.

### CLI (for agents and scripts)

```bash
cd cli
pip install -e .
smriti space list
```

The CLI wraps the backend API. See `cli/README.md` for the full command list and the agent handoff workflow.

---

## Quick start for coding agents

If you want Claude Code or Codex to use Smriti as a shared reasoning-state backend, this is the fast path. Assumes the backend is already running (see Quick Start above).

**Runtime model.** Postgres runs in Docker (`docker compose up -d postgres`). The backend runs locally via `make dev`. The human starts both. Agents are clients of `http://localhost:8000` — they do not start, restart, or manage the backend or Docker. If the backend is unreachable, agents should stop and tell the human.

**1. Install the CLI + MCP server** (one command gets both):

```bash
cd cli && pip install -e . && cd ..
```

**2. Configure your MCP host** if your agent host supports MCP (Claude Code example — check your host's docs for the config file path):

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

Restart the host. The `smriti_*` tools appear in the tool picker.

If you are using Codex in CLI mode, you can skip this step and continue with the CLI + `AGENTS.md` path below.

**3. Install the skill pack** so the agent knows *when* and *why* to use Smriti, not just *how*:

```bash
# For Claude Code — installs to .claude/skills/smriti/SKILL.md
smriti skills install claude-code

# For Codex — installs to AGENTS.md (commit it so Codex sees it)
smriti skills install codex
git add AGENTS.md && git commit -m "Add Smriti skill pack for Codex"
```

**4. Create a space and start working:**

```bash
smriti space create my-project --description "What this project is about"
smriti state my-project                    # your agent's first action, every session
```

From here, the skill pack teaches the agent to read state first, checkpoint at inflection points (not after every small step), fork before exploring alternatives, and never write `HANDOFF.md`. See `cli/README.md` for the full workflow walkthrough.

**Why this is better than markdown handoffs:** Smriti checkpoints are structured, branchable, comparable, and restorable. When reasoning drifts or an agent goes in the wrong direction, you can restore to a clean checkpoint and the bad context is excluded — not summarized, not hidden, actually excluded at the data layer. Markdown handoff files can't do that, and they fall apart the moment two agents need to work in parallel.

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
