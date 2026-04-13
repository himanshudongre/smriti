# Smriti demo recording script

Target: 4-5 minute Loom recording for README and Reddit relaunch.
Story: multi-agent coordination on a real project, not a toy.

---

## Pre-recording setup

1. Backend running: `make dev` (port 8000)
2. Frontend running: `make dev-frontend` (port 5173)
3. Terminal visible with dark theme, readable font size
4. Chrome open to `http://localhost:5173`
5. smriti-dev space has real data (56 checkpoints, 37 claims)

---

## Act 1: The state surface (90 seconds)

### Terminal

```bash
# "Every agent starts by reading the current state."
smriti state smriti-dev --compact
```

**Highlight while output is visible:**
- "This is what every coding agent reads before starting work."
- Point to: latest checkpoint by `codex-local`, decisions, structured tasks with `[intent]` tags and `(id: ...)` slugs
- "Two agents — Claude Code and Codex — have been working on this project. The state shows what was decided, what's in progress, and who did what."

### Browser: LineagePage

Navigate to `http://localhost:5173/spaces/5d08572f-08d4-4b17-b853-396a064d9c4f/lineage`

**Highlight:**
- Summary panel: project name, current direction, status bar (checkpoints, claims, tasks)
- Checkpoint timeline: scroll through the cards
- Point to milestone markers (star icons)
- Point to author agent badges (`claude-code` vs `codex-local`)
- "This is 56 checkpoints of real development work. Not a demo project — the actual product."

---

## Act 2: The coordination proof (2 minutes)

### Terminal

```bash
# "Here are the project-level coordination metrics."
smriti metrics smriti-dev
```

**Highlight while output is visible:**
- "56 checkpoints, 2 agents, 30 cross-agent continuations"
- "That means 30 times one agent picked up where a different agent left off."
- "37 claims, 100% completion, 3 with task IDs"

### Milestone checkpoint

```bash
# "Let me show you the autonomy proof."
smriti checkpoint show <autonomy-milestone-id>
```

Use ID: `a11d5579-1ad8-457e-a7a4-a37411540aab`

**Highlight:**
- The 4 structured tasks with IDs and intent hints
- The milestone note: "first clean autonomous task-ID-based complementary work"
- The founder note about the product wedge
- "Two agents started at the same time, read this task surface, and independently picked different tasks. No human told them what to do."

### Browser: CommitDetailPage

Navigate to the milestone checkpoint detail page.

**Highlight:**
- Structured tasks with intent badges (blue), task IDs
- Notes section with milestone marker and founder commentary
- "The reasoning state isn't prose — it's structured fields that agents can read and act on."

---

## Act 3: Developer experience (60 seconds)

### Terminal

```bash
# "Setting up a new project takes one command."
smriti init demo-project
```

**Highlight:**
- Space created, skill pack installed, SessionStart hook configured
- "After this, every Claude Code session automatically reads the state before starting."

```bash
# "The skill pack teaches the agent the whole workflow."
head -30 .claude/skills/smriti/SKILL.md
```

**Highlight:**
- "Read state first. Checkpoint at inflection points. Check for collisions."
- "The agent doesn't need to be told how to use Smriti — the skill pack makes it the default reflex."

```bash
# "And the backend tells agents what features are available."
curl -s localhost:8000/health | python3 -m json.tool
```

**Highlight:**
- git_sha, capabilities list
- "If an agent hits a stale backend, it knows immediately."

---

## Closing (30 seconds)

"Smriti is version control for reasoning — a shared backend where multiple coding agents coordinate without an orchestrator. It's open source. The repo you're looking at was built using the system itself."

---

## Screenshot capture checklist

Capture these 3 screenshots after recording (or during):

### 1. `docs/assets/lineage-dashboard.png`
- URL: `http://localhost:5173/spaces/5d08572f-08d4-4b17-b853-396a064d9c4f/lineage`
- Capture: the summary panel + first ~6 checkpoint cards
- Make sure milestone markers (star) and author badges are visible
- Crop to ~1200x800px, dark theme

### 2. `docs/assets/cli-state-and-metrics.png`
- Terminal: run `smriti state smriti-dev --compact` then `smriti metrics smriti-dev`
- Capture both outputs in one screenshot
- Dark terminal background, readable font
- Crop to ~900x600px

### 3. `docs/assets/checkpoint-detail.png`
- URL: CommitDetailPage for the autonomy milestone checkpoint
- Or terminal: `smriti checkpoint show a11d5579-1ad8-457e-a7a4-a37411540aab`
- Capture: structured tasks with intent badges + notes section
- Crop to ~1200x700px
