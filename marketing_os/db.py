from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
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
