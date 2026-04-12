# Smriti — project instructions for Claude Code

This project uses Smriti as the shared reasoning-state backend.
A SessionStart hook injects `smriti state smriti-dev` into your
context automatically. Read it before doing anything else.

## Session start checklist

1. The state brief is already in your context (injected by the hook). Read it.
2. Check `## Active work` — if another agent has an active claim on work you were about to start, pick different work or ask the human.
3. Reconcile against the repo: `git log --oneline -10`. Check whether tasks from the state brief are already done.
4. Create a work claim before starting substantial work: `smriti_claim(space="smriti-dev", scope="...", agent="claude-code")`.

## During work

- Checkpoint at inflection points only, not after every small step. Use `--author-agent claude-code`.
- If exploring an alternative direction, fork first.
- If state and repo disagree, stop and reconcile — do not guess.

## Session end

- Mark your work claims done or abandoned.
- Push your branch if it should be visible.
- State the branch disposition: ready to merge, needs review, or exploratory.

## Do not

- Write HANDOFF.md, NOTES.md, or similar files. The checkpoint is the handoff.
- Start, restart, or manage the backend or Docker. You are a client.
- Merge or push to main without human approval.
- Checkpoint noise (save-button commits, end-of-session dumps).

The full skill pack is at `.claude/skills/smriti/SKILL.md`. This file is the
compact always-loaded version. Refer to the skill pack for detailed guidance
on claims, branching, drift detection, and anti-patterns.
