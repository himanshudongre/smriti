# Contributing to Smriti

Thanks for your interest in contributing. This document covers how to get the dev
environment running, how to run tests, and how to propose changes.

---

## Dev environment

**Prerequisites:** Python 3.11+, Node 18+, PostgreSQL 14+

```bash
git clone https://github.com/your-org/smriti
cd smriti

# Copy environment config
cp .env.example .env

# Copy provider config template
cp backend/config/providers.example.yaml backend/config/providers.yaml
# Edit providers.yaml to add at least one provider API key,
# or leave all keys empty and use Mock Mode in the UI.

# Install backend deps + run migrations
make setup

# Start backend (terminal 1)
make dev

# Start frontend (terminal 2)
make dev-frontend
```

Open `http://localhost:5173`.

---

## Running tests

```bash
# All backend tests (uses mock provider — no API key required)
make test

# CLI + MCP tests
cd cli && pip install -e ".[dev]" && pytest

# TypeScript typecheck
cd frontend && npx tsc --noEmit

# Frontend production build
cd frontend && npm run build
```

The backend integration test suite uses the deterministic mock adapter and an
in-memory SQLite database (via `conftest.py`). No live API keys are needed.

The CLI test suite (`cli/tests/`) covers MCP tool handlers, skill pack
rendering and installation, multi-branch state formatting, and content-integrity
guards for the skill pack template. CLI tests use `MagicMock(spec=SmritiClient)`
fixtures — no running backend required.

**When to run which tests:**

| Changed area | Run |
|---|---|
| `backend/app/` | `make test` (177 integration + 97 unit tests) |
| `cli/smriti_cli/` | `cd cli && pytest` (70 tests) |
| `cli/smriti_cli/skill_pack/template.md` | `cd cli && pytest tests/test_skill_pack.py` — content-integrity tests catch dropped sections |
| `frontend/src/` | `cd frontend && npx tsc --noEmit` |
| Both backend + CLI | Both suites — they share no test infrastructure but both call the same backend API |

---

## Code style

**Backend:** Python code is formatted and linted with `ruff`.

```bash
make lint       # Check
make format     # Fix in place
```

**Frontend:** TypeScript with strict type checking. ESLint is configured but not
enforced in CI yet.

There are no hard style rules beyond what ruff and tsc enforce. Prefer clarity over
brevity. Keep functions short. Do not add comments that restate the code — only
comment non-obvious decisions.

---

## Making changes

1. Fork the repo and create a feature branch.
2. Make your changes. Keep commits focused: one logical change per commit.
3. Run backend tests and frontend typecheck before opening a PR.
4. Open a PR against `main`. Describe what changed and why.

For larger changes (new feature, API change, refactor), open an issue first to discuss
scope before writing code.

---

## Reporting bugs

Open a GitHub issue. Include:

- What you expected to happen
- What actually happened
- Steps to reproduce (minimal, if possible)
- Relevant log output (`make logs` for Docker, or terminal output)
- Backend version (git hash or tag)

---

## Contributing demos and docs

Docs live in `docs/` and at the repo root (`README.md`, `ARCHITECTURE.md`,
`DECISIONS.md`). Demo scenarios live in `demos/`.

For doc fixes: open a PR directly. For new demo scenarios: follow the structure in
`demos/branching-reasoning-demo/` — a README, RUNBOOK, DEMO_SCRIPT, and
EXPECTED_OUTCOMES at minimum.

---

## Agent-facing surfaces

Smriti has three agent-facing surfaces beyond the chat UI:

- **CLI** (`cli/smriti_cli/main.py`) — `smriti` command, 8 subcommand groups
- **MCP server** (`cli/smriti_cli/mcp_server.py`) — `smriti-mcp` command, 15 tools
- **Skill pack** (`cli/smriti_cli/skill_pack/`) — versioned instruction files for Claude Code and Codex

Changes to any of these should include corresponding test coverage in `cli/tests/`.
Skill pack content changes should pass the content-integrity tests in
`test_skill_pack.py` — these assert that critical sections (anti-patterns, signal
test, drift detection, work claims) cannot be silently dropped by template edits.

---

## What we are not looking for

- Automatic checkpointing logic — Checkpoints are intentionally manual.
- Authentication / multi-user support — deferred by design.
- Generic orchestration or task management — work claims are advisory and narrow.
- Changes to legacy V1 endpoints — these are retained for compatibility only.

If you want to work on something that falls outside normal scope, open an issue first.
