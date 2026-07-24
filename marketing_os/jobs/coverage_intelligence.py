from __future__ import annotations

from typing import Any
from urllib.error import HTTPError

from sqlalchemy import select

from ..db import create_db_engine, init_db, session_factory, session_scope
from ..db_models import MeasurementCursorRecord, ProductIdentityRecord
from ..integrations import MattMadeMeAgentApiAdapter, WebsiteConfig
from ..services.coverage_intelligence import (
    MEASUREMENT_SOURCE,
    accept_catalog_snapshot,
    enqueue_identity_materialization,
    ingest_measurement_page,
    load_coverage_config,
    materialize_product_coverage,
    reproject_editorial_product_identities,
    reconcile_editorial_snapshot,
    seed_taxonomy,
)
from ..services.durable_jobs import enqueue_job
from ..services.job_handlers import NonRetryableJobError
from ..services.product_identity import reconcile_product_identities


def catalog_reconcile_handler(_payload: dict[str, Any]) -> dict[str, Any]:
    website_config = WebsiteConfig.from_env()
    if not website_config.api_key:
        raise NonRetryableJobError("catalog read credential is not configured")
    adapter = MattMadeMeAgentApiAdapter(website_config)
    try:
        snapshot = adapter.list_products_v2()
    except ValueError as exc:
        raise NonRetryableJobError(str(exc)) from exc
    except HTTPError as exc:
        if exc.code in {400, 401, 403, 404}:
            raise NonRetryableJobError(f"catalog read rejected with HTTP {exc.code}") from exc
        raise
    engine = create_db_engine()
    init_db(engine)
    factory = session_factory(engine)
    try:
        with session_scope(factory) as session:
            identity_result = reconcile_product_identities(
                session, snapshot["products"]
            )
            projection_result = reproject_editorial_product_identities(session)
            seed_taxonomy(session)
            result = accept_catalog_snapshot(session, snapshot)
            repair_product_ids = sorted(
                (
                    set(identity_result["transitioned_product_ids"])
                    | set(projection_result["affectedProductIds"])
                )
                - set(result["materializedProductIds"])
            )
            repair_jobs = enqueue_identity_materialization(
                session,
                repair_product_ids,
                source_revision=snapshot["revision"],
            )
            return {
                **result,
                "identity": identity_result,
                "editorialProjection": projection_result,
                "identityRepairJobs": repair_jobs,
            }
    except ValueError as exc:
        raise NonRetryableJobError(str(exc)) from exc
    finally:
        engine.dispose()


def editorial_reconcile_handler(_payload: dict[str, Any]) -> dict[str, Any]:
    website_config = WebsiteConfig.from_env()
    if not website_config.api_key:
        raise NonRetryableJobError("catalog read credential is not configured")
    adapter = MattMadeMeAgentApiAdapter(website_config)
    try:
        snapshot = adapter.list_editorial_v2()
    except ValueError as exc:
        raise NonRetryableJobError(str(exc)) from exc
    except HTTPError as exc:
        if exc.code in {400, 401, 403, 404}:
            raise NonRetryableJobError(f"editorial read rejected with HTTP {exc.code}") from exc
        raise
    engine = create_db_engine()
    init_db(engine)
    factory = session_factory(engine)
    try:
        with session_scope(factory) as session:
            result = reconcile_editorial_snapshot(session, snapshot)
            if result["accepted"]:
                product_ids = sorted(
                    {
                        identity.product_id
                        for identity in session.scalars(
                            select(ProductIdentityRecord).where(
                                ProductIdentityRecord.mapping_state == "mapped"
                            )
                        )
                    }
                )
                for product_id in product_ids:
                    enqueue_job(
                        session,
                        job_type="coverage.materialize",
                        payload={
                            "productId": product_id,
                            "sourceRevision": result["revision"],
                            "trigger": "editorial",
                        },
                        idempotency_key=(
                            f"coverage.materialize:editorial:{product_id}:"
                            f"{str(result['revision'])[:64]}"
                        ),
                        correlation_id=f"editorial:{str(result['revision'])[:16]}",
                    )
            return result
    except ValueError as exc:
        raise NonRetryableJobError(str(exc)) from exc
    finally:
        engine.dispose()


def coverage_materialize_handler(payload: dict[str, Any]) -> dict[str, Any]:
    product_id = payload.get("productId")
    if not isinstance(product_id, int) or product_id <= 0:
        return {
            "cells": 0,
            "suppressed": 0,
            "exception": "catalog_product_identity_unresolved",
            "sourceProductId": payload.get("sourceProductId"),
        }
    source_revision = str(payload.get("sourceRevision", "")).strip()
    if not source_revision:
        raise NonRetryableJobError("coverage materialization requires sourceRevision")
    engine = create_db_engine()
    init_db(engine)
    factory = session_factory(engine)
    try:
        with session_scope(factory) as session:
            return materialize_product_coverage(
                session,
                product_id,
                source_revision=source_revision,
            )
    except (LookupError, ValueError) as exc:
        raise NonRetryableJobError(str(exc)) from exc
    finally:
        engine.dispose()


def measurement_ingest_handler(_payload: dict[str, Any]) -> dict[str, Any]:
    config = load_coverage_config()
    website_config = WebsiteConfig.from_env()
    if not website_config.measurement_api_key:
        raise NonRetryableJobError("measurement read credential is not configured")
    adapter = MattMadeMeAgentApiAdapter(website_config)
    engine = create_db_engine()
    init_db(engine)
    factory = session_factory(engine)
    pages = 0
    events = 0
    backlog = False
    try:
        with factory() as session:
            checkpoint = session.scalar(
                select(MeasurementCursorRecord).where(
                    MeasurementCursorRecord.source_name == MEASUREMENT_SOURCE
                )
            )
            after = checkpoint.opaque_cursor if checkpoint and checkpoint.opaque_cursor else None
        while pages < config.policy["limits"]["measurementPagesPerRun"]:
            try:
                external_page = adapter.list_growth_events_v2(
                    after=after,
                    limit=config.policy["limits"]["measurementPageSize"],
                )
            except ValueError as exc:
                raise NonRetryableJobError(str(exc)) from exc
            except HTTPError as exc:
                if exc.code in {400, 401, 403, 404}:
                    raise NonRetryableJobError(
                        f"measurement read rejected with HTTP {exc.code}"
                    ) from exc
                raise
            try:
                with session_scope(factory) as session:
                    result = ingest_measurement_page(session, external_page, config=config)
            except ValueError as exc:
                raise NonRetryableJobError(str(exc)) from exc
            pages += 1
            events += int(result["created"])
            after = str(result["nextCursor"]) or None
            backlog = bool(result["hasMore"])
            if not backlog:
                break
        return {
            "pages": pages,
            "eventsCreated": events,
            "backlog": backlog,
            "resumeCursorPresent": bool(after),
        }
    finally:
        engine.dispose()
