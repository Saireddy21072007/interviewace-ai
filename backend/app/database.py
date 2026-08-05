"""
Database engine and session management.

WHY SQLALCHEMY AND NOT RAW psycopg
----------------------------------
The project guide specifies PostgreSQL, and production should use it. But a
teammate cloning this repo on a Sunday night should not have to install and
configure a database server before they can see the app run. SQLAlchemy lets
`DATABASE_URL` decide: SQLite by default, PostgreSQL by changing one line in
.env. The models, queries and migrations are identical either way.

`database/schema.sql` holds the equivalent hand-written PostgreSQL DDL for the
report, so the schema is documented in plain SQL as well as in Python.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

settings = get_settings()

_is_sqlite = settings.database_url.startswith("sqlite")

engine = create_engine(
    settings.database_url,
    # SQLite refuses cross-thread use by default; FastAPI serves requests on a
    # thread pool, so it has to be relaxed. Postgres needs neither of these.
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    pool_pre_ping=not _is_sqlite,
    echo=False,
)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _record) -> None:
        """SQLite ignores FOREIGN KEY constraints unless asked not to.

        Without this, a cascade delete silently leaves orphan rows and the
        SQLite behaviour quietly diverges from PostgreSQL - exactly the class
        of bug that only shows up after deployment.
        """
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base for every model in models.py."""


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables. Called on startup and by the tests."""
    from . import models  # noqa: F401 - registers the models on Base.metadata

    Base.metadata.create_all(bind=engine)
