# Smriti

Version control for reasoning.

Image Git for LLM/Agentic Reasoning

---

## Why I ended up building this

I was just switching between ChatGPT, Claude, Cursor etc while working on problems, and something kept breaking.

Not the models.

My own context.

I would spend 30–40 minutes figuring something out, reach a clean decision and then:

- switch models  
- come back later  
- try a different approach  

and suddenly I had to reconstruct everything again.

Not just the text. The actual *state of thinking*.

That’s what pushed me to build this.

---

## The core idea (at least how I think about it)

Instead of treating conversations as logs (Like we do today using .md files) 
treat the **state of reasoning** as something explicit

So I introduced this concept of a **checkpoint**

It is basically a snapshot of where you are:

- what you have figured out  
- decisions you have made  
- what is still open  
- what needs to be done  

Nothing magical. Just structured.

---

## Demo

![Smriti demo](docs/assets/checkpoint-diff.png)

Watch demo (3–4 min):  
https://www.loom.com/share/0531ab1b6f114ceb9996ec5780052158

---

## The problem (the way I see it)

You spend an hour working through something.

You finally reach clarity.

Then you need to:

- step away  
- switch models  
- revisit an earlier direction  

And everything falls apart.

There’s no clean way to:

- return to that exact state  
- branch thinking without messing up the original  
- switch models without re-explaining everything  

And the more we use multiple models, the worse this gets.

Honestly, this is where I feel things start breaking.

**Reasoning state becomes the bottleneck.**

---

## What this lets you do

A few things started working once I built this:

You can go back to any prior state  
not by scrolling, but by actually mounting that checkpoint again

You can switch models mid-session  
without rewriting the entire context every time

You can fork your thinking  
like “let me try a completely different approach from here”  
without corrupting the original path

You can compare two checkpoints  
and actually see where the reasoning diverged

That last one surprised me a bit. It is more useful than I expected.

---

## One thing I did differently (maybe controversial)

Most systems rely on prompts to manage context.

I didn’t.

When you mount a checkpoint, I enforce boundaries in the data layer itself.

Which basically means:

only the relevant turns are visible  
nothing from the future leaks in  
nothing from other sessions sneaks in  

It’s stricter than typical chat systems.

Not sure if this is the right long-term decision.  
But it felt important to try.

---

## This is not just for chat

I initially built this thinking about chat.

But the more I worked on it, the more it felt like this might matter more for agents.

Because agents have the same problem, just worse:

- multi-step reasoning chains  
- hard to debug  
- hard to reproduce  
- no clean way to “go back”  

Once something diverges, you are kind of stuck.

With checkpoints, you can:

- persist intermediate reasoning  
- resume from a known state  
- fork execution paths  
- compare outcomes across runs  

Basically, you can inspect what actually happened.

Which is something I feel is missing right now.

---

## Quick start

You’ll need:

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

There is also a mock mode if you don’t want to deal with API keys.

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

It includes:

- exact steps  
- what to type  
- expected outcomes  

I wrote it mainly so people don’t have to guess how to use this.

---

## Core concepts (keeping this simple)

### Space

Think of it like a container for a line of work.

It holds checkpoints and sessions.

Kind of like a repo, but for thinking.

---

### Session

This is just your live chat.

It may or may not be attached to a Space.

You can switch models here without losing history.

---

### Checkpoint

This is the main thing.

A structured snapshot:

- title  
- objective  
- summary  
- decisions  
- tasks  
- open questions  
- entities  

You create it manually.

I tried auto-checkpointing early on.

Didn’t work. It just created noise.

---

### Turn

One message. Either user or assistant.

Append-only.

Nothing fancy.

---

## Context modes (this part matters)

- **FRESH** → nothing, blank state  
- **HEAD** → latest checkpoint + recent turns  
- **MOUNTED** → specific checkpoint + only new turns  
- **FORKED** → checkpoint base + separate branch  

Mounted mode is the key one.

That’s where isolation actually works.

---

## How it works (rough flow)

Start a session -> attach a Space -> create checkpoints -> mount / fork / compare

That’s it.

No complicated flow.

---

## Current limitations

There are quite a few:

- single user only  
- no merging of branches  
- no streaming responses  
- UI is functional, not polished  
- no mobile  
- no integrations  

Also…

I’m not fully convinced yet that this abstraction is correct.

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

There’s also a mock mode.

---

## Tech stack

- FastAPI  
- SQLAlchemy  
- PostgreSQL  
- React + TypeScript + Vite  

Nothing unusual.

---

## Where this might go (if it makes sense)

Still figuring this out.

Some directions that feel interesting:

- structured reasoning memory  
- agent workflows  
- shared state across tools  
- maybe knowledge graph layer on top  

But none of this is built yet.

---

## Why I’m sharing this

I’m mainly trying to validate the idea.

Not the implementation.

The implementation is early. I know that.

What I care about is:

Does this way of thinking about reasoning actually help  
or is chat history already “good enough” and I’m overcomplicating it?

Happy to get blunt feedback.
