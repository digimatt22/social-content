from __future__ import annotations

import os
import subprocess
from typing import Any

from ..db import create_db_engine, init_db, session_factory, session_scope
from ..services.job_handlers import NonRetryableJobError
from ..services.pinterest_shadow import build_weekly_digest, generate_shadow_packages


def shadow_generate_handler(payload: dict[str, Any]) -> dict[str, Any]:
    product_id = payload.get("productId")
    if product_id is not None and (not isinstance(product_id, int) or product_id <= 0):
        raise NonRetryableJobError("shadow generation productId must be a positive integer")
    try:
        repository_revision = _repository_revision(payload)
    except ValueError as exc:
        raise NonRetryableJobError(str(exc)) from exc
    engine = create_db_engine()
    init_db(engine)
    factory = session_factory(engine)
    try:
        with session_scope(factory) as session:
            return generate_shadow_packages(
                session,
                repository_revision=repository_revision,
                product_id=product_id,
            )
    except (LookupError, ValueError) as exc:
        raise NonRetryableJobError(str(exc)) from exc
    finally:
        engine.dispose()


def shadow_digest_handler(_payload: dict[str, Any]) -> dict[str, Any]:
    engine = create_db_engine()
    init_db(engine)
    factory = session_factory(engine)
    try:
        with session_scope(factory) as session:
            digest, created = build_weekly_digest(session)
            return {
                "digestId": digest.id,
                "utcWeek": digest.utc_week.isoformat(),
                "ready": digest.ready_count,
                "blocked": digest.blocked_count,
                "created": created,
                "publicWrites": 0,
                "providerCalls": 0,
            }
    finally:
        engine.dispose()


def _repository_revision(payload: dict[str, Any]) -> str:
    explicit = str(
        payload.get("repositoryRevision")
        or os.environ.get("MARKETING_OS_REPOSITORY_REVISION", "")
    ).strip()
    if explicit:
        return explicit
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        revision = ""
    if not revision:
        raise ValueError(
            "MARKETING_OS_REPOSITORY_REVISION is required when git metadata is unavailable"
        )
    return revision
