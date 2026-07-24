from __future__ import annotations

import os
from typing import Any

from ..db import create_db_engine, init_db, session_factory, session_scope
from ..services.job_handlers import AmbiguousExternalWriteError, NonRetryableJobError
from ..services.pinterest_connector import (
    FixturePinterestProvider,
    ProviderResult,
    claim_publish,
    record_publish_result,
    reconcile_unknown,
)


def pinterest_publish_handler(payload: dict[str, Any]) -> dict[str, Any]:
    provider = _fixture_provider(payload, operation="publish")
    engine = create_db_engine()
    init_db(engine)
    factory = session_factory(engine)
    try:
        with session_scope(factory) as session:
            publication, attempt, request = claim_publish(
                session,
                publication_id=int(payload["publicationId"]),
                policy_class=str(payload["policyClass"]),
                provider=provider,
            )
            publication_id = publication.id
            attempt_id = attempt.id if attempt is not None else None
        if attempt_id is None or request is None:
            raise AmbiguousExternalWriteError(
                "A prior submitted Pinterest attempt requires reconciliation."
            )
        try:
            result = provider.create_pin(request)
        except Exception as exc:
            result = ProviderResult(
                "ambiguous",
                error_code="transport_exception_after_submit",
                error_message=str(exc),
            )
        with session_scope(factory) as session:
            publication, persisted_attempt = record_publish_result(
                session,
                publication_id=publication_id,
                attempt_id=attempt_id,
                result=result,
            )
            response = {
                "publicationId": publication.id,
                "state": publication.lifecycle_state,
                "providerStatus": result.status,
            }
            persisted_attempt_state = persisted_attempt.state
        if persisted_attempt_state == "ambiguous":
            raise AmbiguousExternalWriteError(
                "Pinterest provider evidence is ambiguous or conflicts with reconciled truth."
            )
        if result.status == "ambiguous":
            raise AmbiguousExternalWriteError(
                "Pinterest response was ambiguous; publication persisted as publish_unknown."
            )
        if result.status in {"auth_error", "validation_error"}:
            raise NonRetryableJobError(result.error_message or result.status)
        if result.status in {"throttled", "server_error"}:
            raise RuntimeError(result.error_message or result.status)
        return response
    finally:
        engine.dispose()


def pinterest_reconcile_handler(payload: dict[str, Any]) -> dict[str, Any]:
    provider = _fixture_provider(payload, operation="reconcile")
    engine = create_db_engine()
    init_db(engine)
    factory = session_factory(engine)
    try:
        with session_scope(factory) as session:
            publication, result = reconcile_unknown(
                session,
                publication_id=int(payload["publicationId"]),
                provider=provider,
            )
            response = {
                "publicationId": publication.id,
                "state": publication.lifecycle_state,
                "providerStatus": result.status,
            }
            publication_state = publication.lifecycle_state
        if result.status in {"provider_error", "still_unknown"}:
            raise RuntimeError(result.error_message or result.status)
        if result.status == "absent" and publication_state != "confirmed_absent":
            raise RuntimeError("Pinterest absence has not reached the confirmation threshold.")
        return response
    finally:
        engine.dispose()


def _fixture_provider(payload: dict[str, Any], *, operation: str) -> FixturePinterestProvider:
    if os.environ.get("MARKETING_OS_ENV", "").lower() == "production":
        raise NonRetryableJobError(
            "No reviewed live Pinterest provider is installed; fixture execution is refused in production."
        )
    if payload.get("provider") != "fixture":
        raise NonRetryableJobError(
            "Only the fixture Pinterest provider exists in the disabled Phase 4 increment."
        )
    if operation == "publish":
        return FixturePinterestProvider(create_status=str(payload.get("fixtureStatus", "created")))
    return FixturePinterestProvider(reconcile_status=str(payload.get("fixtureStatus", "published")))
