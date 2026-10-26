"""Database engine and session configuration."""

import os
from pathlib import Path
from typing import Optional

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


DEFAULT_DATABASE_URL = "sqlite:///./data/jobscraper.db"


def get_database_url() -> str:
    """Return the configured database URL."""

    return os.getenv("JOBSCRAPER_DATABASE_URL", DEFAULT_DATABASE_URL)


def create_database_engine(
    database_url: Optional[str] = None, echo: bool = False
) -> Engine:
    """Create an engine suitable for SQLite or PostgreSQL."""

    url = database_url or get_database_url()
    if url.startswith("sqlite:///") and ":memory:" not in url:
        database_path = Path(url.removeprefix("sqlite:///"))
        database_path.parent.mkdir(parents=True, exist_ok=True)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, echo=echo, connect_args=connect_args)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:
            del connection_record
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Build the application's session factory."""

    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
