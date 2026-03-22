# Smriti — Repository Structure

```
smriti/
│
├── README.md                   Product overview, core concepts, setup
├── ARCHITECTURE.md             System model, isolation mechanism, API versioning
├── DECISIONS.md                Key architectural and product decisions
├── CONTRIBUTING.md             Development setup and contribution guide
├── REPO_STRUCTURE.md           This file
│
├── Makefile                    Dev, test, build, and migration targets
├── docker-compose.yml          Postgres + backend + frontend services
├── .env.example                Environment variable template
│
├── backend/
│   ├── app/
│   │   ├── main.py             FastAPI app factory, CORS, router registration
│   │   ├── config.py           Pydantic settings (DATABASE_URL, DEBUG)
│   │   ├── config_loader.py    Provider config loader (providers.yaml + env vars)
│   │   ├── schemas/
│   │   │   └── __init__.py     Pydantic request/response schemas
│   │   ├── db/
│   │   │   ├── database.py     SQLAlchemy engine and session factory
│   │   │   └── models.py       ORM models: RepoModel, CommitModel, ChatSession,
│   │   │                         TurnEvent
│   │   ├── domain/
│   │   │   └── enums.py        SessionStatus, TargetTool, etc.
│   │   ├── api/
│   │   │   └── routes/
│   │   │       ├── chat.py     V4: sessions, send_message, commit, head,
│   │   │       │                 provider status
│   │   │       ├── checkpoint.py  V5: draft_checkpoint
│   │   │       ├── lineage.py  V5: fork, branch tree, checkpoint compare,
│   │   │       │                 reachable checkpoints
│   │   │       ├── repos.py    V2: Space CRUD, Checkpoint CRUD
│   │   │       └── sessions.py V1: transcript ingestion (legacy)
│   │   └── providers/
│   │       ├── registry.py     Provider lookup and adapter instantiation
│   │       ├── openai_adapter.py
│   │       ├── anthropic_adapter.py
│   │       └── mock_adapter.py Deterministic mock for testing
│   ├── config/
│   │   ├── providers.example.yaml  Template — copy to providers.yaml
│   │   └── providers.yaml          Your keys (gitignored, not committed)
│   ├── alembic/                Database migrations
│   ├── tests/                  Backend tests
│   └── pyproject.toml          Python dependencies
│
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── ChatWorkspacePage.tsx   Primary UI: chat, sidebar, checkpoint
│   │   │   │                             modal, history panel, context indicators
│   │   │   └── LineagePage.tsx         Branch tree, checkpoint compare
│   │   ├── api/
│   │   │   └── client.ts       API client functions (V4, V5, V2)
│   │   ├── types/
│   │   │   └── index.ts        TypeScript type definitions
│   │   └── main.tsx            App entry point, router
│   └── package.json
│
├── docs/
│   └── API.md                  V4 and V5 endpoint reference
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
| `/api/v2` | `repos.py` | Partially current | Space and Checkpoint CRUD used by UI; agent-push workflow is legacy |
| `/api/v4` | `chat.py` | Current | Primary chat and session API |
| `/api/v5` | `checkpoint.py`, `lineage.py` | Current | Checkpoint draft, fork, lineage |

---

## Make targets

```
make setup          Install deps + run migrations (first-time setup)
make dev            Run backend dev server (port 8000)
make dev-frontend   Run frontend dev server (port 5173)
make up             Start all services via Docker Compose
make down           Stop all services
make test           Run all backend tests
make lint           Lint backend code (ruff)
make format         Format backend code (ruff)
make migrate        Run pending Alembic migrations
make migration      Create a new migration (usage: make migration msg="...")
```
