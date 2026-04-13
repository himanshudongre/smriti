import logging
import pathlib
import re
import subprocess
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings


def _resolve_git_sha() -> str:
    """Return the short git SHA of the backend directory, or 'unknown'."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=pathlib.Path(__file__).resolve().parent.parent,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"

class SecretGuardFilter(logging.Filter):
    def filter(self, record):
        if isinstance(record.msg, str) and re.search(r'sk-[a-zA-Z0-9_\-]+', record.msg):
            record.msg = re.sub(r'sk-[a-zA-Z0-9_\-]+', '[REDACTED_SECRET]', record.msg)
        return True


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        description="Cross-agent memory handoff system",
        version="0.1.0",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Secret Guard
    for handler in logging.root.handlers:
        handler.addFilter(SecretGuardFilter())

    from app.api.routes import repos, commits, context_git, chat, checkpoint, lineage, claims

    # V2 Routes (Git for memory)
    app.include_router(repos.router, prefix="/api/v2", tags=["repos"])
    app.include_router(commits.router, prefix="/api/v2", tags=["commits"])
    app.include_router(context_git.router, prefix="/api/v2", tags=["commits"])

    # V4 Routes (Chat workspace)
    app.include_router(chat.router, prefix="/api/v4", tags=["chat-v4"])

    # V5 Routes
    app.include_router(checkpoint.router, prefix="/api/v5/checkpoint", tags=["checkpoint-v5"])
    app.include_router(lineage.router, prefix="/api/v5", tags=["lineage-v5"])
    app.include_router(claims.router, prefix="/api/v5", tags=["claims-v5"])

    # ── Capabilities manifest ────────────────────────────────────────
    # Computed once at startup so /health is zero-cost at request time.
    _git_sha = _resolve_git_sha()

    # Hardcoded feature flags matching the route modules included above.
    # When a new feature ships (new route module, new query param, new
    # schema shape), add it here so agents can detect stale backends.
    _capabilities = [
        "claims",             # /api/v5/claims
        "structured_tasks",   # task objects with intent_hint/blocked_by/status
        "task_ids",           # structured task ids + claim.task_id support
        "checkpoint_notes",   # /api/v5/checkpoint/{id}/notes
        "branch_disposition", # PATCH /api/v5/lineage/branches/disposition
        "freshness",          # since_commit_id on state endpoint
        "compact_state",      # --compact mode on state brief
    ]

    @app.get("/health")
    async def health_check():
        return {
            "status": "ok",
            "git_sha": _git_sha,
            "capabilities": _capabilities,
        }

    @app.on_event("startup")
    async def startup_event():
        from app.config_loader import providers_status
        import logging
        logger = logging.getLogger("smriti.startup")

        status = providers_status()
        logger.info("Provider runtime validation:")
        for name, info in status.items():
            if info.get("missing_package", False):
                logger.warning(f"  - {name}: disabled (package not installed)")
            elif not info.get("has_key", False):
                logger.info(f"  - {name}: disabled (no API key configured)")
            elif not info.get("enabled", False):
                logger.info(f"  - {name}: disabled (explicitly disabled in config)")
            else:
                logger.info(f"  - {name}: configured and ready")

        # Specific check for the background provider — this is what
        # powers checkpoint extraction, drafting, and review. If it's
        # not configured, every LLM-backed endpoint will silently
        # return mock content, which is the single most confusing
        # failure mode in local development.
        bg = status.get("background_intelligence", {})
        if not bg.get("configured"):
            bg_provider = bg.get("provider", "openai")
            logger.warning(
                "⚠ Background intelligence provider '%s' is NOT configured. "
                "Checkpoint extraction, drafting, and review will return mock "
                "content instead of real LLM output. To fix: set %s in .env "
                "or add the key to config/providers.yaml.",
                bg_provider,
                {
                    "openai": "OPENAI_API_KEY",
                    "anthropic": "ANTHROPIC_API_KEY",
                    "openrouter": "OPENROUTER_API_KEY",
                }.get(bg_provider, f"{bg_provider.upper()}_API_KEY"),
            )

    return app


app = create_app()
