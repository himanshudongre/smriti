# Smriti — Repository Structure

```
smriti/
│
├── README.md                   Product overview, core concepts, setup,
│                                 coding-agent quick start
├── ARCHITECTURE.md             System model, isolation mechanism, API versioning,
│                                 multi-branch state, local-first DB modes, skill pack surface
├── DECISIONS.md                Key architectural and product decisions
├── CONTRIBUTING.md             Development setup and contribution guide
├── AGENTS.md                   Smriti skill pack for Codex (generated, committed)
├── REPO_STRUCTURE.md           This file
│
├── Makefile                    Dev, test, build, and migration targets
├── docker-compose.yml          Postgres + backend + frontend services
├── .env.example                Environment variable template (dotenv-loaded)
│
├── backend/
│   ├── app/
│   │   ├── main.py             FastAPI app factory, CORS, router registration,
│   │   │                         startup provider validation
│   │   ├── config.py           Pydantic settings; local SQLite / Postgres db-mode resolution
│   │   ├── config_loader.py    Provider config loader (dotenv + providers.yaml
│   │   │                         + env vars), reset_config() for dev reloads
│   │   ├── schemas/
│   │   │   └── __init__.py     Pydantic request/response schemas
│   │   ├── db/
│   │   │   ├── database.py     SQLAlchemy engine + session factory; SQLite/Postgres
│   │   │   │                     engine setup, local first-run bootstrap
│   │   │   ├── models.py       ORM models: RepoModel, CommitModel, ChatSession,
│   │   │   │                     TurnEvent, WorkClaim, WorkTree
│   │   │   └── types.py        Portable column types (JSONB↔JSON, vector↔JSON)
│   │   ├── domain/
│   │   │   └── enums.py        SessionStatus, TargetTool, etc.
│   │   ├── api/
│   │   │   └── routes/
│   │   │       ├── chat.py     V4: sessions, send_message, commit, head,
│   │   │       │                 multi-branch state (/state), provider status
│   │   │       ├── checkpoint.py  V5: draft, review, extract
│   │   │       ├── current.py  V5: Project Current State aggregate surface
│   │   │       ├── metrics.py  V5: project coordination / quality metrics
│   │   │       ├── lineage.py  V5: fork, branch tree, checkpoint compare,
│   │   │       │                 reachable checkpoints
│   │   │       ├── claims.py   V5: work claims (create, update, list)
│   │   │       ├── worktrees.py V5: git worktrees (open, list, show, close)
│   │   │       ├── repos.py    V2: Space CRUD, Checkpoint CRUD
│   │   │       ├── commits.py  V2: direct commit creation
│   │   │       └── context_git.py  V2: context extraction
│   │   ├── providers/
│   │   │   ├── registry.py     Provider lookup, adapter instantiation,
│   │   │   │                     MockAdapter fallback with warning log
│   │   │   ├── openai_adapter.py
│   │   │   ├── anthropic_adapter.py
│   │   │   └── openrouter_adapter.py
│   │   └── services/
│   │       ├── extractor.py    Transcript → structured extraction
│   │       ├── embedding.py    Embedding generation (pgvector)
│   │       ├── parser.py       Transcript parsing utilities
│   │       ├── pack_generator.py  Context pack rendering (V1 legacy)
│   │       ├── worktree_probe.py  Cached git drift probe for bound claims
│   │       └── llm/
│   │           ├── base.py         LLM provider base class
│   │           ├── mock_provider.py  Deterministic mock for testing
│   │           └── openai_provider.py  OpenAI chat completions
│   ├── config/
│   │   ├── providers.example.yaml  Template — copy to providers.yaml
│   │   └── providers.yaml          Your keys (gitignored, not committed)
│   ├── alembic/                Database migrations (15 versions)
│   ├── tests/
│   │   ├── integration/        API integration tests (156 tests)
│   │   │   ├── test_api_v4_chat.py
│   │   │   ├── test_api_v5_lineage.py
│   │   │   ├── test_multi_branch_state.py
│   │   │   ├── test_current_state.py
│   │   │   ├── test_claims.py
│   │   │   ├── test_claim_worktree_binding.py
│   │   │   ├── test_project_root_migration.py
│   │   │   ├── test_repos_project_root.py
│   │   │   ├── test_worktrees.py
│   │   │   ├── test_checkpoint_extract.py
│   │   │   ├── test_local_sqlite_smoke.py
│   │   │   └── test_delete_endpoints.py
│   │   └── unit/               Unit tests (133 tests)
│   │       ├── test_config_loader.py
│   │       ├── test_extractor.py
│   │       ├── test_golden_outputs.py
│   │       ├── test_worktree_probe.py
│   │       ├── test_worktree_paths.py
│   │       ├── test_worktree_id_resolution.py
│   │       ├── test_pack_generator.py
│   │       └── test_parser.py
│   └── pyproject.toml          Python dependencies (includes python-dotenv)
│
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── WorkspaceOverviewPage.tsx  Resume-focused landing page
│   │   │   ├── ChatWorkspacePage.tsx      Primary chat UI: sidebar, checkpoint
│   │   │   │                                modal, history panel, context indicators
│   │   │   └── LineagePage.tsx            Branch tree with author_agent tags,
│   │   │                                   checkpoint compare
│   │   ├── api/
│   │   │   └── client.ts       API client functions (V4, V5, V2)
│   │   ├── types/
│   │   │   └── index.ts        TypeScript type definitions (includes
│   │   │                         CheckpointNode.author_agent)
│   │   └── main.tsx            App entry point, router
│   └── package.json
│
├── cli/                        Programmatic CLI + MCP server for agents
│   ├── README.md               Command reference, MCP tools, skill pack install,
│   │                             agent handoff workflow
│   ├── pyproject.toml          Installable as `pip install -e ./cli`
│   │                             → `smriti` + `smriti-mcp` on PATH
│   ├── smriti_cli/
│   │   ├── main.py             argparse dispatcher: init, doctor, status, space,
│   │   │                         state, current, checkpoint, fork, restore,
│   │   │                         compare, branch, claim, worktree, skills, metrics
│   │   ├── attachment.py       Project attachment: read/write `.smriti.json`,
│   │   │                         the durable repo ↔ space binding
│   │   ├── mcp_server.py       FastMCP server (21 tools, stdio transport)
│   │   ├── client.py           SmritiClient HTTP wrapper (includes claims/worktrees)
│   │   ├── formatters.py       Continuation-oriented markdown renderers
│   │   │                         (multi-branch, active claims, divergence)
│   │   └── skill_pack/         Agent skill pack source and renderer
│   │       ├── template.md     Single source of truth (v2.3, 15 sections)
│   │       ├── renderer.py     Pure-function render + versioned install
│   │       └── targets.py      Target configs (claude-code, codex)
│   └── tests/                  CLI + MCP tests (151 tests)
│       ├── test_branch_close.py
│       ├── test_current_cli.py
│       ├── test_doctor_cli.py
│       ├── test_init.py
│       ├── test_mcp_server.py
│       ├── test_skill_pack.py
│       ├── test_smoke.py
│       ├── test_space_cli.py
│       ├── test_state_multi_branch.py
│       ├── test_worktree_cli.py
│       └── test_worktree_mcp.py
│
├── docs/
│   ├── API.md                  V2, V4, and V5 endpoint reference
│   └── DEMO_SCRIPT.md           Demo recording script
│
└── demos/
    └── branching-reasoning-demo/   Complete demo scenario with runbook,
                                    script, and expected outcomes
```

---

## API version map

| Prefix | Module | Status | Notes |
|---|---|---|---|
| `/api/v1` | `sessions.py` | Legacy | Transcript paste ingestion |
| `/api/v2` | `repos.py`, `commits.py` | Current | Space CRUD, checkpoint read/list. `CommitResponse` includes `assumptions` and `artifacts`. |
| `/api/v4` | `chat.py` | Current | Chat sessions, send_message, commit, head, multi-branch state (`/state` with active branches, active claims, and divergence signal). Provider status. |
| `/api/v5` | `checkpoint.py`, `current.py`, `metrics.py`, `lineage.py`, `claims.py`, `worktrees.py` | Current | Checkpoint draft/review/extract, Project Current State, project metrics, fork, lineage tree, compare, work claims with optional worktree binding, git worktrees. |

---

## Make targets

```
make setup-local    Solo setup: venv + deps + CLI + frontend (local SQLite, no Docker)
make setup-postgres Shared/team setup: venv + deps + Docker Postgres + migrations
make dev-local      Run backend in local-first SQLite mode (port 8000)
make dev-postgres   Run backend in Postgres mode (port 8000)
make dev-frontend   Run frontend dev server (port 5173)
make up             Start all services via Docker Compose
make down           Stop all services
make test           Run all backend tests
make lint           Lint backend code (ruff)
make format         Format backend code (ruff)
make migrate        Run pending Alembic migrations (Postgres mode)
make migration      Create a new migration (usage: make migration msg="...")
```

---

## Test counts (as of local-first SQLite mode)

| Suite | Count | Location |
|---|---|---|
| Backend integration | 156 | `backend/tests/integration/` |
| Backend unit | 133 | `backend/tests/unit/` |
| CLI + MCP | 151 | `cli/tests/` |
| **Total** | **440** | |
