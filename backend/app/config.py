"""Application settings and database-mode resolution."""

from pathlib import Path

from pydantic_settings import BaseSettings

DEFAULT_POSTGRES_URL = "postgresql://smriti:smriti@localhost:5432/smriti"
DEFAULT_LOCAL_DB_PATH = "~/.smriti/smriti.db"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App
    app_name: str = "Smriti"
    debug: bool = False

    # Database — see db_mode / resolved_database_url for how these resolve.
    # database_url: the raw DATABASE_URL env var. Empty string means "unset".
    database_url: str = ""
    # smriti_db_mode: the raw SMRITI_DB_MODE env var — "local" | "postgres".
    # Empty string means "derive" (see db_mode).
    smriti_db_mode: str = ""
    # smriti_local_db_path: SQLite file path for local mode. Empty string
    # means the default, ~/.smriti/smriti.db.
    smriti_local_db_path: str = ""

    # OpenAI (for extraction service)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def db_mode(self) -> str:
        """Resolved database mode: 'local' or 'postgres'.

        An explicit SMRITI_DB_MODE wins. Otherwise, an explicitly-set
        Postgres DATABASE_URL preserves Postgres behavior (backward
        compatibility for existing setups); an otherwise-unconfigured
        environment defaults to local, so a solo user needs no database
        server.
        """
        mode = self.smriti_db_mode.strip().lower()
        if mode in ("local", "postgres"):
            return mode
        if self.database_url.strip().startswith(("postgresql://", "postgres://")):
            return "postgres"
        return "local"

    @property
    def local_db_path(self) -> Path:
        """Absolute path to the local-mode SQLite database file."""
        raw = self.smriti_local_db_path.strip() or DEFAULT_LOCAL_DB_PATH
        return Path(raw).expanduser().resolve()

    @property
    def resolved_database_url(self) -> str:
        """The SQLAlchemy URL the engine should connect to, per db_mode."""
        if self.db_mode == "postgres":
            return self.database_url.strip() or DEFAULT_POSTGRES_URL
        return f"sqlite:///{self.local_db_path}"


settings = Settings()
