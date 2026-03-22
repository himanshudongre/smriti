"""SQLAlchemy database engine and session management."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, echo=settings.debug)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


import logging
logger = logging.getLogger("uvicorn.error")

def get_db():
    """Dependency that yields a database session."""
    logger.info("get_db: Creating new session...")
    db = SessionLocal()
    logger.info("get_db: Session created.")
    try:
        logger.info("get_db: Yielding session...")
        yield db
    finally:
        logger.info("get_db: Closing session...")
        db.close()
