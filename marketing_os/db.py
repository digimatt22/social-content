from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session, sessionmaker
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory

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
    if os.environ.get("MARKETING_OS_ENV", "").lower() == "production" and engine.dialect.name != "postgresql":
        raise RuntimeError("Production Marketing OS processes require PostgreSQL.")
    if engine.dialect.name != "sqlite":
        require_current_schema(engine)
        return
    Base.metadata.create_all(engine)
    _apply_lightweight_sqlite_migrations(engine)
    _drop_removed_product_columns(engine)
    _normalize_remote_image_reference_states(engine)


def schema_revisions(engine: Engine, alembic_config_path: str = "alembic.ini") -> tuple[str | None, str]:
    script = ScriptDirectory.from_config(_alembic_config(alembic_config_path))
    expected = script.get_current_head()
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    return current, expected


def require_current_schema(engine: Engine, alembic_config_path: str = "alembic.ini") -> None:
    current, expected = schema_revisions(engine, alembic_config_path)
    if current != expected:
        raise RuntimeError(
            "Database schema is not current "
            f"(database={current or 'unversioned'}, expected={expected}). "
            "Run `alembic upgrade head` before starting the service."
        )


def _alembic_config(path: str):
    from alembic.config import Config

    return Config(path)


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
            "file_size_bytes": "INTEGER",
            "mime_type": "VARCHAR(120) NOT NULL DEFAULT ''",
            "width": "INTEGER",
            "height": "INTEGER",
            "relative_path": "VARCHAR(500) NOT NULL DEFAULT ''",
            "asset_role": "VARCHAR(120) NOT NULL DEFAULT ''",
            "rights": "VARCHAR(80) NOT NULL DEFAULT 'unknown'",
            "brand_safe": "VARCHAR(80) NOT NULL DEFAULT 'review'",
            "indexed_at": "DATETIME",
            "review_state": "VARCHAR(80) NOT NULL DEFAULT 'unreviewed'",
            "approval_notes": "TEXT NOT NULL DEFAULT ''",
            "generated_prompt": "TEXT NOT NULL DEFAULT ''",
            "source_asset_id": "INTEGER",
            "default_reference": "INTEGER NOT NULL DEFAULT 0",
            "hidden_from_generation": "INTEGER NOT NULL DEFAULT 0",
        },
        "tasks": {
            "planned_content_item_id": "INTEGER",
            "generated_content_candidate_id": "INTEGER",
            "scheduled_time": "VARCHAR(5) NOT NULL DEFAULT '09:00'",
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
            "outcome_tags_json": "TEXT NOT NULL DEFAULT '[]'",
            "collection_status": "VARCHAR(80) NOT NULL DEFAULT 'recorded'",
            "external_source": "VARCHAR(80) NOT NULL DEFAULT ''",
            "external_id": "VARCHAR(160) NOT NULL DEFAULT ''",
            "last_synced_at": "DATETIME",
            "sync_status": "VARCHAR(80) NOT NULL DEFAULT 'manual'",
            "sync_error": "TEXT NOT NULL DEFAULT ''",
            "manual_override_state": "VARCHAR(80) NOT NULL DEFAULT ''",
            "manual_override_note": "TEXT NOT NULL DEFAULT ''",
        },
        "planned_content_items": {
            "scheduled_time": "VARCHAR(5) NOT NULL DEFAULT '09:00'",
            "audience": "VARCHAR(200) NOT NULL DEFAULT ''",
            "occasion": "VARCHAR(200) NOT NULL DEFAULT ''",
            "promotion": "VARCHAR(200) NOT NULL DEFAULT ''",
            "notes": "TEXT NOT NULL DEFAULT ''",
            "selected_source_asset_ids_json": "TEXT NOT NULL DEFAULT '[]'",
            "status": "VARCHAR(80) NOT NULL DEFAULT 'planned'",
            "brief_status": "VARCHAR(80) NOT NULL DEFAULT 'pending'",
            "last_production_run_at": "DATETIME",
            "production_error": "TEXT NOT NULL DEFAULT ''",
        },
        "generated_content_candidates": {
            "source_asset_ids_json": "TEXT NOT NULL DEFAULT '[]'",
            "revision_notes": "TEXT NOT NULL DEFAULT ''",
            "reviewed_by": "VARCHAR(120) NOT NULL DEFAULT ''",
            "reviewed_at": "DATETIME",
        },
        "creative_generation_jobs": {
            "candidate_asset_id": "INTEGER",
            "model_name": "VARCHAR(120) NOT NULL DEFAULT ''",
            "provider_error": "TEXT NOT NULL DEFAULT ''",
            "output_url": "VARCHAR(500) NOT NULL DEFAULT ''",
            "response_metadata_json": "TEXT NOT NULL DEFAULT '{}'",
            "review_notes": "TEXT NOT NULL DEFAULT ''",
            "reviewed_by": "VARCHAR(120) NOT NULL DEFAULT ''",
            "reviewed_at": "DATETIME",
        },
        "product_sales": {
            "product_id": "INTEGER",
            "source_name": "VARCHAR(80) NOT NULL DEFAULT ''",
            "external_id": "VARCHAR(220) NOT NULL DEFAULT ''",
            "listing_id": "VARCHAR(160) NOT NULL DEFAULT ''",
            "listing_title": "VARCHAR(260) NOT NULL DEFAULT ''",
            "quantity": "INTEGER NOT NULL DEFAULT 0",
            "revenue_cents": "INTEGER NOT NULL DEFAULT 0",
            "currency_code": "VARCHAR(12) NOT NULL DEFAULT ''",
            "sold_at": "DATETIME",
            "raw_data_json": "TEXT NOT NULL DEFAULT '{}'",
            "imported_at": "DATETIME",
        },
        "etsy_reviews": {
            "product_id": "INTEGER",
            "external_source": "VARCHAR(80) NOT NULL DEFAULT 'etsy_api'",
            "external_id": "VARCHAR(220) NOT NULL DEFAULT ''",
            "shop_id": "VARCHAR(160) NOT NULL DEFAULT ''",
            "listing_id": "VARCHAR(160) NOT NULL DEFAULT ''",
            "transaction_id": "VARCHAR(160) NOT NULL DEFAULT ''",
            "buyer_user_id": "VARCHAR(160) NOT NULL DEFAULT ''",
            "rating": "INTEGER",
            "review": "TEXT NOT NULL DEFAULT ''",
            "language": "VARCHAR(40) NOT NULL DEFAULT ''",
            "image_url_fullxfull": "VARCHAR(500) NOT NULL DEFAULT ''",
            "created_timestamp": "INTEGER",
            "updated_timestamp": "INTEGER",
            "raw_data_json": "TEXT NOT NULL DEFAULT '{}'",
            "imported_at": "DATETIME",
            "updated_at": "DATETIME",
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


def _normalize_remote_image_reference_states(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(engine)
    if "assets" not in set(inspector.get_table_names()):
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                UPDATE assets
                SET review_state = 'synced',
                    readiness_state = 'remote Etsy reference'
                WHERE external_source = 'etsy'
                  AND asset_type = 'Etsy product photo'
                  AND file_exists = 0
                  AND review_state IN ('needs review', 'unreviewed')
                """
            )
        )
        connection.execute(
            text(
                """
                UPDATE assets
                SET review_state = 'synced',
                    readiness_state = 'remote website reference'
                WHERE external_source = 'mattmademe_website'
                  AND asset_type = 'external listing image'
                  AND file_exists = 0
                  AND review_state IN ('needs review', 'unreviewed')
                """
            )
        )


def _drop_removed_product_columns(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(engine)
    if "products" not in set(inspector.get_table_names()):
        return
    existing = {column["name"] for column in inspector.get_columns("products")}
    removed = [name for name in ["status", "primary_audience", "launch_priority"] if name in existing]
    if not removed:
        return

    with engine.begin() as connection:
        for name in removed:
            connection.execute(text(f"ALTER TABLE products DROP COLUMN {name}"))


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
