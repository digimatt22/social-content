from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session, sessionmaker

from .db_models import Base


DEFAULT_DB_PATH = Path("data/marketing_os.sqlite")


def database_url(db_path: str | Path | None = None) -> str:
    explicit = os.environ.get("MARKETING_OS_DB_URL")
    if explicit:
        return explicit
    path = Path(os.environ.get("MARKETING_OS_DB_PATH", db_path or DEFAULT_DB_PATH))
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path}"


def create_db_engine(db_path: str | Path | None = None, echo: bool = False) -> Engine:
    url = database_url(db_path)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, echo=echo, future=True, connect_args=connect_args)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    _apply_lightweight_sqlite_migrations(engine)


def _apply_lightweight_sqlite_migrations(engine: Engine) -> None:
    """Add new nullable/defaulted columns for local SQLite databases.

    This project is still local-first and small enough to avoid a full
    migration dependency, but create_all will not add columns to existing
    tables. Keep this intentionally boring and additive.
    """
    if engine.dialect.name != "sqlite":
        return

    additions: dict[str, dict[str, str]] = {
        "products": {
            "external_source": "VARCHAR(80) NOT NULL DEFAULT ''",
            "external_id": "VARCHAR(160) NOT NULL DEFAULT ''",
            "canonical_url": "VARCHAR(500) NOT NULL DEFAULT ''",
            "last_synced_at": "DATETIME",
            "sync_status": "VARCHAR(80) NOT NULL DEFAULT 'local'",
            "sync_error": "TEXT NOT NULL DEFAULT ''",
            "staleness_state": "VARCHAR(80) NOT NULL DEFAULT 'unknown'",
            "manual_override_state": "VARCHAR(80) NOT NULL DEFAULT ''",
            "manual_override_note": "TEXT NOT NULL DEFAULT ''",
        },
        "assets": {
            "external_source": "VARCHAR(80) NOT NULL DEFAULT ''",
            "external_id": "VARCHAR(160) NOT NULL DEFAULT ''",
            "canonical_url": "VARCHAR(500) NOT NULL DEFAULT ''",
            "last_synced_at": "DATETIME",
            "sync_status": "VARCHAR(80) NOT NULL DEFAULT 'local'",
            "sync_error": "TEXT NOT NULL DEFAULT ''",
            "staleness_state": "VARCHAR(80) NOT NULL DEFAULT 'unknown'",
            "manual_override_state": "VARCHAR(80) NOT NULL DEFAULT ''",
            "manual_override_note": "TEXT NOT NULL DEFAULT ''",
            "file_exists": "INTEGER NOT NULL DEFAULT 0",
            "file_checked_at": "DATETIME",
            "file_modified_at": "DATETIME",
            "file_checksum": "VARCHAR(128) NOT NULL DEFAULT ''",
            "review_state": "VARCHAR(80) NOT NULL DEFAULT 'unreviewed'",
            "approval_notes": "TEXT NOT NULL DEFAULT ''",
            "generated_prompt": "TEXT NOT NULL DEFAULT ''",
            "source_asset_id": "INTEGER",
        },
        "tasks": {
            "published_url": "VARCHAR(500) NOT NULL DEFAULT ''",
            "platform_post_id": "VARCHAR(160) NOT NULL DEFAULT ''",
            "metric_due_date": "DATE",
            "metric_status": "VARCHAR(80) NOT NULL DEFAULT 'not due'",
            "external_source": "VARCHAR(80) NOT NULL DEFAULT ''",
            "external_id": "VARCHAR(160) NOT NULL DEFAULT ''",
            "canonical_url": "VARCHAR(500) NOT NULL DEFAULT ''",
            "last_synced_at": "DATETIME",
            "sync_status": "VARCHAR(80) NOT NULL DEFAULT 'local'",
            "sync_error": "TEXT NOT NULL DEFAULT ''",
            "staleness_state": "VARCHAR(80) NOT NULL DEFAULT 'unknown'",
            "manual_override_state": "VARCHAR(80) NOT NULL DEFAULT ''",
            "manual_override_note": "TEXT NOT NULL DEFAULT ''",
        },
        "metrics": {
            "collection_status": "VARCHAR(80) NOT NULL DEFAULT 'recorded'",
            "external_source": "VARCHAR(80) NOT NULL DEFAULT ''",
            "external_id": "VARCHAR(160) NOT NULL DEFAULT ''",
            "last_synced_at": "DATETIME",
            "sync_status": "VARCHAR(80) NOT NULL DEFAULT 'manual'",
            "sync_error": "TEXT NOT NULL DEFAULT ''",
            "manual_override_state": "VARCHAR(80) NOT NULL DEFAULT ''",
            "manual_override_note": "TEXT NOT NULL DEFAULT ''",
        },
    }

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table, columns in additions.items():
            if table not in table_names:
                continue
            existing = {column["name"] for column in inspector.get_columns(table)}
            for name, definition in columns.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, future=True, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
