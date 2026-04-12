---
smriti_skill_pack_version: 1.2
title: Smriti — how to use it well
target: {{display_name}}
---

# Smriti: how to use it well

You are working in a project that uses Smriti for reasoning state.
Before you do anything else on this project, read this file. It tells
you when to call Smriti, when not to, and why it matters.

Primary tool mode for your host: `{{primary_mode}}`.

---

## 1. What Smriti is, in one paragraph

Smriti is a reasoning-state backend. It stores structured snapshots of
your thinking at meaningful inflection points — decisions, assumptions,
tasks, open questions, artifacts — and makes them available to whatever
agent picks up the work next. It is not a memory database, not a wiki,
not a notes app, not a transcript archive. It is version control for
reasoning. Spaces are repos. Checkpoints are commits. Fork, compare,
restore, and review all mean roughly what they would mean in a source
control tool, but for the shape of the work rather than the code.

---

## 2. Why this file exists

You have been trained on thousands of projects that used a markdown
handoff file — `HANDOFF.md`, `NOTES.md`, `CONTEXT.md`, whatever — to
pass context between sessions, agents, or people. You probably reach
for that pattern by default. Don't. On this project it is wrong.

Smriti exists specifically to replace that pattern with something
structured, branchable, comparable, restorable, and resistant to
overwriting. Markdown handoff files lose on every axis except zero-
learning-curve. This file closes the learning-curve gap so your
default reflex on this project becomes Smriti, not a text file.

If you find yourself about to write `HANDOFF.md`, stop and write a
checkpoint instead. Every time.

---

## 3. The reflex: read state first

At the start of every session where you are working on a Smriti-enabled
project, your FIRST action is:

```
{{mcp:smriti_state(space="<project>")}}{{cli:smriti state <project>}}
```

Before you read any file. Before you run any test. Before you plan
anything. Before you answer the user's first prompt beyond "let me
check the state first."

The state brief is the minimum context you need to continue work
without re-discovering decisions that were already made. Calling it
unconditionally is cheap, and missing it is expensive. The brief is
multi-branch by default — if other agents are working on this project
on different branches, you will see them in the `## Active branches`
section with an author tag, and if any of them disagree with main on
decisions you will see a `## Divergence signal` section.

Say out loud to the user: **"Reading current state from Smriti."**
before you call state. This gives the human watching a visible audit
trail.

### 3.1 After reading state: cross-agent continuation

After you read state, look at the most recent checkpoint(s). Ask:

1. **Was the most recent checkpoint written by a different agent?**
   Check the `author_agent` field. If another agent wrote the latest
   checkpoint, they are handing context to you. Read their checkpoint
   carefully — don't skim past it because you didn't write it.

2. **Does it contain tasks, recommendations, or clear next actions?**
   If the `## In progress` or `## Tasks` section names specific work,
   treat that as your default continuation path unless you have a
   concrete reason not to. Another agent's task list is not a
   suggestion — it is the most informed view of what should happen
   next, written by the agent that just finished working.

3. **Is the most recent checkpoint a review?** If another agent left
   a review checkpoint (e.g. after reviewing your work), read it in
   full before acting:
   {{mcp:`smriti_show_checkpoint(checkpoint_id="<id>")`}}{{cli:`smriti checkpoint show <id>`}}
   Reviews often contain specific follow-up tasks. Do those first.

4. **Does the latest checkpoint belong to a different branch?** If
   the `## Active branches` section shows the most recent activity
   on a non-main branch, be explicit about your intent. Either
   continue that branch (fork or write into its session) or stay on
   main — but say which you are doing and why. Do not silently
   ignore another agent's branch.

**If you disagree with another agent's recommendation:** do not
silently override it. Either run
{{mcp:`smriti_compare`}}{{cli:`smriti compare`}}
to understand the divergence, or fork a branch with your alternative
and let the human decide. Quietly doing the opposite of what the
last agent recommended — without checkpointing the disagreement —
is the multi-agent equivalent of overwriting `HANDOFF.md`.

### 3.2 Repo reconciliation before acting

The state brief tells you what was decided and what tasks were
flagged. It does NOT tell you whether those tasks have already been
completed in the codebase. Another agent may have finished the work
and committed it after the checkpoint was written. Before you start
implementing anything from the state brief's tasks, reconcile:

1. **Check recent commits.** Run `git log --oneline -10` (or your
   host's equivalent). Do any of them address the task you are about
   to start?
2. **If the task targets a specific file, check that file.** Read
   or grep the file to see whether the change already exists.
3. **If the work is already done:** do NOT redo it. Instead, produce
   a short confirmation checkpoint: "Verified that <task> was
   completed in commit <hash>. Closing this task — no further action
   needed." Then move to the next open item.
4. **If the work is partially done:** continue from where it left
   off. Do not restart from scratch.
5. **If the work is not done:** proceed with implementation.

This step is especially important when the most recent checkpoints
have low-signal content (e.g. mock or empty fields). The checkpoint
may have been written with a degraded extractor — the work could
still have been done and committed even though the checkpoint does
not describe it well. The repo is the ground truth; the checkpoint
is the reasoning-state summary. When they disagree, check the repo.

Say out loud: **"Checking whether the flagged tasks are already
reflected in the repo before starting."**

---

## 4. When to checkpoint

Checkpoint at an **inflection point**. An inflection point is a moment
where the reasoning state has changed in a way a future agent needs to
know about. Concretely:

- **You made a decision you would not want to re-derive.** Checkpoint.
- **You rejected a hypothesis and now know a dead end.** Checkpoint.
- **You solved a sub-problem and the next step builds on it.** Checkpoint.
- **You are about to hand off to another agent or another session.** Checkpoint.
- **You are about to explore an alternative direction and want to
  preserve the current line.** Fork first, then checkpoint on the fork.

Use the **extract path**, not hand-written JSON. Pass freeform markdown
describing the inflection point and Smriti's background LLM will pull
out the structured fields (message, objective, summary, decisions,
assumptions, tasks, open questions, entities, artifacts) for you.

Example call:

{{mcp:```
smriti_create_checkpoint(
    space="<project>",
    content="""
# Decided on Pydantic for the state validation layer

After trying dataclass-based validation and hitting the injection
surface from unbounded extra fields, going with Pydantic BaseModel
and `extra="forbid"`. Latency overhead is ~0.3 ms per call.

## Open questions
- How do we share state across parallel agent runs?
- Cleaner schema-versioning story for migrations?
""",
    author_agent="claude-code",
)
```}}{{cli:```
cat <<'MD' | smriti checkpoint create <project> --extract --author-agent <your-agent-name>
# Decided on Pydantic for the state validation layer

After trying dataclass-based validation and hitting the injection
surface from unbounded extra fields, going with Pydantic BaseModel
and `extra="forbid"`. Latency overhead is ~0.3 ms per call.

## Open questions
- How do we share state across parallel agent runs?
- Cleaner schema-versioning story for migrations?
MD
```}}

Say out loud: **"Checkpointing now — reached an inflection point on X."**
before the call. Name the X.

Always tag `author_agent` with a stable identifier for your agent
(e.g. `claude-code`, `codex-local`). This is how humans and other
agents know who wrote what on the shared timeline. Inconsistent or
missing `author_agent` makes divergence unattributable.

---

## 5. When NOT to checkpoint

This section is more important than the previous one. Read it twice.

A checkpoint is not a save button. Most of your work should not
produce a checkpoint. Resist all of these:

- **Do not checkpoint after every small step.** Finishing a helper
  function, editing one file, running one test — not an inflection
  point. If your checkpoint's `message` would be "Wrote a helper
  function" or "Ran the tests" or "Fixed a typo," do not checkpoint.
  Keep working.

- **Do not checkpoint at end of session as a blob.** A single
  "everything I did today" commit with 15 decisions crammed into one
  message is less useful than zero checkpoints. It has no locality.
  The next agent reading it cannot tell which decisions belong
  together, what caused what, or in what order things happened. If
  you reach end-of-session without having checkpointed, you missed
  the inflection points earlier — and the fix is NOT to compensate
  with one giant dump. Write ONE crisp checkpoint for the most recent
  real decision and stop. Then reflect on what you should have
  checkpointed earlier.

- **Do not use checkpoints as a backup system.** The event stream
  (turns) is already the backup. A checkpoint is a reasoning-state
  snapshot, not a safety net. Checkpointing "because the session is
  about to end" or "because the user is leaving" is a save-button
  use and it is wrong.

- **Do not checkpoint with nothing crisp to say.** If you cannot
  write a single sentence for the `message` that names a specific
  decision made, hypothesis confirmed, problem solved, or dead end
  identified — you are not at an inflection point yet. Finish
  thinking. Then checkpoint.

- **Do not checkpoint on top of inconsistent state.** If
  `{{mcp:smriti_state}}{{cli:smriti state}}` surfaces contradictions
  between decisions, or if
  `{{mcp:smriti_review_checkpoint}}{{cli:smriti checkpoint review}}`
  flags issues on the current HEAD, resolve first. Either restore to
  a cleaner ancestor or surface the contradictions to the human. Do
  NOT stack new commits on broken state — you are compounding the
  confusion, not fixing it.

- **Do not restate existing state.** If the last checkpoint already
  contains the decision you are about to record, do not re-checkpoint
  it. Smriti tracks new commitments, not a running summary of
  everything still true. Re-checkpointing dilutes the signal.

- **Do not checkpoint just because the user asked you to.** The user
  does not always know whether you are at an inflection point. If
  they ask you to checkpoint and you are not, say so: "I don't have
  a crisp inflection point to record yet — can you tell me what
  decision or problem you want captured?" This is not disobedience;
  it is protecting the signal quality of the project's timeline from
  future noise.

### 5.1 The signal test

Before every checkpoint, ask yourself three questions:

1. **Can I name the inflection point in one sentence for `message`?**
   If you need a paragraph, wait.
2. **If another agent read only my `decisions`, `summary`, and
   `open_questions`, could they continue the work correctly?**
   If no, there is nothing worth recording yet.
3. **Is the reasoning state meaningfully different from the previous
   checkpoint on this branch?**
   If no, you are restating.

If any answer is no, do not checkpoint.

### 5.2 What good frequency looks like

A 4-hour focused session typically produces **2 to 4 checkpoints**.
Not 20. Not 0.

- A session producing 20 checkpoints is producing noise. You are
  treating checkpoints as a save button.
- A session producing 0 checkpoints is either doing trivial work or
  missing the inflection points. Reflect.
- 2–4 is the target. Aim there.

---

## 6. When to fork

Fork when you want to explore an alternative direction **without
losing the main line**. Concretely:

```
{{mcp:smriti_fork(checkpoint_id="<current-head-id>", branch="alternative-X")}}{{cli:smriti fork <current-head-id> --branch alternative-X}}
```

Then write a checkpoint into the forked session:

{{mcp:```
smriti_create_checkpoint(
    space="<project>",
    session="<fork-session-id>",
    content="...",
)
```}}{{cli:```
cat fork.md | smriti checkpoint create <project> \
    --extract --session <fork-session-id> --author-agent <your-agent-name>
```}}

**Do not fork for small variations within the same direction.** That
is continuation, not branching. Fork when two parallel lines of
reasoning should genuinely exist for future comparison — when you
want the option to go back to the original line cleanly without
re-deriving it.

Say out loud: **"Forking a branch to explore an alternative. Main
line is preserved."**

---

## 7. When to review

Run `{{mcp:smriti_review_checkpoint(checkpoint_id="<id>")}}{{cli:smriti checkpoint review <id>}}`
when:

- The state brief you just read contains decisions or assumptions
  that feel contradictory to each other.
- You are about to checkpoint on top of a state you did not write
  yourself and want a sanity pass first.
- You are handing off to another agent and want to surface any
  issues before the receiving agent wastes cycles on broken state.

Do **not** run review on every checkpoint. It is a self-audit tool,
not an audit trail. Running it reflexively adds noise.

---

## 8. When to compare

Run `{{mcp:smriti_compare(checkpoint_a="<A>", checkpoint_b="<B>")}}{{cli:smriti compare <A> <B>}}`
when:

- The state brief shows a `## Divergence signal` on an active branch
  and you want the full diff (the signal only shows the top 3
  conflicting decisions per side).
- You see two checkpoints in the lineage that should agree on
  something but seem to differ.
- You are resolving a fork back to a single line and need to decide
  which decisions to keep.

---

## 9. When to restore

Run `{{mcp:smriti_restore(checkpoint_id="<id>")}}{{cli:smriti restore <id>}}`
when:

- The current HEAD state is contradictory or corrupted and you want
  to resume from an earlier clean snapshot.
- You are reading a past checkpoint not as history but as a starting
  point — you want to continue work from it as if it were HEAD.

Say out loud: **"Restoring to an earlier checkpoint."** when you do
this. The human should know you are stepping back in time.

---

## 10. Detecting drift

If at any point you notice:

- The state brief contains tasks that appear already done, or
- Decisions that directly contradict what you have been working on, or
- Open questions that seem already resolved in the summary, or
- The `## Divergence signal` shows active branches disagreeing on
  things you considered settled,

then you are in a drift situation. **Do not paper over it.** Three
acceptable responses:

1. Run `{{mcp:smriti_review_checkpoint}}{{cli:smriti checkpoint review}}`
   on the current HEAD and act on the output.
2. Run `{{mcp:smriti_compare}}{{cli:smriti compare}}` on the two most
   recent checkpoints from each divergent author and summarize the
   difference in plain prose for the human.
3. Surface the drift to the human directly: "I am seeing scope
   divergence between what the state brief says and what I have been
   working on. Stopping to reconcile before continuing. Which line
   should I follow?"

**Do not quietly pick a side.** Scope divergence across agents is a
real signal that the project state needs a human judgment call.
Smriti's job is to make that signal visible to you; your job is to
make it visible to the human, not to hide it by picking one branch
and continuing.

Say out loud: **"I'm seeing scope divergence between the state brief
and my work. Stopping to reconcile before continuing."**

---

## 11. Anti-patterns to reject explicitly

These are in addition to the "do not checkpoint when" rules in
Section 5.

- **Do not write HANDOFF.md, NOTES.md, CONTEXT.md, PROGRESS.md, or
  any similar file on this project.** A Smriti space exists. Write
  a checkpoint instead. Markdown handoff files do not survive
  branching, do not cross-link to history, and do not participate in
  `smriti_compare`. Every time you write one, the next agent has to
  re-learn what you already knew — exactly the problem Smriti exists
  to solve. If you catch yourself about to write a handoff file,
  treat that as a signal you have reached an inflection point and
  should checkpoint.

- **Do not silently inject state output into the user's chat
  context.** Announce it: "Reading current state from Smriti." The
  human should always be able to see when you are consulting or
  writing to the shared timeline.

- **Do not tag `author_agent` inconsistently.** Pick ONE stable
  identifier for your agent — e.g. `claude-code`, `codex-local`,
  `claude-code-v2` — and use it on every checkpoint you write. If
  you change your tag mid-project, the divergence signal becomes
  unattributable. Stability of the tag is more important than its
  content.

- **Do not invoke `/chat/send` or the live chat runtime from inside
  your tool loop.** That endpoint is for humans talking to Smriti's
  chat UI, not for agents writing state. Your only write paths are
  `{{mcp:smriti_create_checkpoint}}{{cli:smriti checkpoint create --extract}}`
  and `{{mcp:smriti_fork}}{{cli:smriti fork}}`.

- **Do not treat the extract path as a free pass to dump your
  reasoning.** The extract LLM will pull whatever fields it can, but
  if you pass it 2000 words of stream-of-consciousness it will
  produce low-signal decisions and assumptions. Write the markdown
  crisply. The extract path saves you from hand-rolling JSON; it is
  not a license to be verbose.

- **Do not silently override another agent's recommendations.** If
  the most recent checkpoint was written by another agent and contains
  tasks or decisions you disagree with, do not just do something
  different without recording the disagreement. Fork, compare, or
  surface the disagreement to the human. The other agent's
  recommendations are the most informed view of what should happen
  next — overriding them silently is equivalent to deleting someone
  else's work.

- **Do not implement a task from the state brief without checking
  whether it is already done in the repo.** Smriti tracks reasoning
  state, not repo state. A task listed in a checkpoint may have been
  completed by another agent and committed to git since the checkpoint
  was written. Check `git log` and the relevant files before starting.
  Duplicating completed work wastes a full session and creates noise
  in the timeline.

- **Do not use `smriti_install_skill` to overwrite an in-project
  skill pack that you did not write.** If the project already has
  a skill pack of an older version, the install tool will tell you.
  Use the existing one unless the human asks you to upgrade.

---

## 12. Phrases to say out loud

These give the human watching your session a visible audit trail.
Use them literally.

| When you are about to... | Say |
|---|---|
| call `{{mcp:smriti_state}}{{cli:smriti state}}` | "Reading current state from Smriti." |
| create a checkpoint | "Checkpointing now — reached an inflection point on X." |
| fork a branch | "Forking a branch to explore an alternative. Main line is preserved." |
| restore an earlier checkpoint | "Restoring to an earlier checkpoint." |
| run review after a drift signal | "Running a consistency review on the current state before I continue." |
| run compare on a divergence signal | "Comparing main against the divergent branch to see the full diff." |
| reconcile state against repo | "Checking whether the flagged tasks are already reflected in the repo before starting." |
| surface drift to the human | "I'm seeing scope divergence between the state brief and my work. Stopping to reconcile before continuing." |

These are not cosmetic. They are what makes your session legible to
the human who will eventually read the thread and decide whether
your reasoning is sound.

---

## 13. The project root

Every checkpoint you write should have a `project_root` field that
points at the absolute path where this project actually lives on
disk. {{mcp:The MCP server runs in the host's arbitrary working
directory, so it does NOT auto-capture `project_root`. Pass the
path explicitly: `smriti_create_checkpoint(..., project_root="/abs/path")`.}}{{cli:The CLI auto-captures `$(pwd)` as `project_root`
when you run from the project directory. If you are running from
somewhere else, pass `--project-root /abs/path` explicitly.}}

This is how cross-agent handoffs know where the project lives.
Missing or wrong `project_root` makes the next agent spend 30
seconds hunting for the codebase.

---

## 14. Two-sentence summary

Call {{mcp:`smriti_state`}}{{cli:`smriti state`}} at session start,
unconditionally, before anything else. Checkpoint at inflection
points — not after every small step, not at end of session as a
dump, never as a save button.

Everything else in this file is implementation detail for those two
rules.

---

## 15. If you are confused about Smriti

The order of operations is always:

1. **Read state first.** You are missing context until you do.
2. **Work.** Smriti has no opinion about what happens between
   checkpoints.
3. **Checkpoint at inflection points.** Not before, not more often.
4. **Hand off.** The next agent reads the new state. No markdown
   handoff file.

If you are unsure whether an action is "Smriti-shaped," ask yourself:
"Is this a reasoning-state change, or is it just work-in-progress?"
Reasoning-state changes get checkpointed. Work-in-progress does not.

If you are still unsure, surface the question to the human. They will
tell you. Do not guess.

---

*Smriti skill pack version {{primary_mode}}-1.2 — this file is
authoritative for agent behaviour on this project. If you catch it
contradicting itself or your observed behaviour of the tools, tell
the human; the skill pack is versioned and meant to be updated.*
