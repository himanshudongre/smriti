import logging
import re
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

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

    from app.api.routes import repos, commits, context_git, chat, checkpoint, lineage

    # V2 Routes (Git for memory)
    app.include_router(repos.router, prefix="/api/v2", tags=["repos"])
    app.include_router(commits.router, prefix="/api/v2", tags=["commits"])
    app.include_router(context_git.router, prefix="/api/v2", tags=["commits"])

    # V4 Routes (Chat workspace)
    app.include_router(chat.router, prefix="/api/v4", tags=["chat-v4"])

    # V5 Routes
    app.include_router(checkpoint.router, prefix="/api/v5/checkpoint", tags=["checkpoint-v5"])
    app.include_router(lineage.router, prefix="/api/v5", tags=["lineage-v5"])

    @app.get("/health")
    async def health_check():
        return {"status": "ok"}

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

    return app


app = create_app()
