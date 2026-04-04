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

---

## When to use Smriti

**Use it when:**

- you are working through something complex over multiple sessions
- you need to explore multiple approaches and compare them
- your conversation has drifted and you want to recover cleanly
- you are switching between models and need context continuity
- you want to preserve specific outputs alongside your reasoning state

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

## This is not just for chat

I initially built this thinking about chat. But the more I worked on it, the more it felt like this might matter more for agents.

Because agents have the same problem, just worse:

- multi-step reasoning chains
- hard to debug
- hard to reproduce
- no clean way to "go back"

With checkpoints, you can persist intermediate reasoning, resume from a known state, fork execution paths, and compare outcomes across runs.

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

The same idea that makes reasoning recoverable in chat also applies when the reasoning happens more autonomously. If something is making decisions over multiple steps, you want to be able to inspect what it decided, go back to where it was still on track, and try a different path. That does not require a different system. It requires the same one.

---

## Why I am sharing this

I am mainly trying to validate the idea, not the implementation. The implementation is early.

What I care about is whether this way of thinking about reasoning actually helps, or whether chat history is already good enough and I am overcomplicating it.

Happy to get blunt feedback.
