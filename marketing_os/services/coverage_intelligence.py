from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..db_models import (
    CatalogChangeRecord,
    CatalogSnapshotRecord,
    CoverageCellRecord,
    CoverageOutcomeRecord,
    DecisionRunRecord,
    GrowthEventRecord,
    LandingPageRecord,
    MeasurementCursorRecord,
    PageOpportunityRecord,
    ProductIdentityRecord,
    ProductRecord,
    PublicationOpportunityRecord,
    SearchIntentRecord,
    utc_now,
)
from .durable_jobs import enqueue_job
from .growth_contracts import record_growth_event


POLICY_PATH = Path("config/coverage-policy-v1.json")
TAXONOMY_PATH = Path("config/coverage-taxonomy-v1.json")
CATALOG_SOURCE = "mattmademe.products.v2"
EDITORIAL_SOURCE = "mattmademe.editorial.v2"
MEASUREMENT_SOURCE = "mattmademe.growth-events.v2"


@dataclass(frozen=True)
class CoverageConfig:
    policy: dict[str, Any]
    taxonomy: dict[str, Any]
    policy_hash: str
    taxonomy_hash: str


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def load_coverage_config(
    policy_path: str | Path = POLICY_PATH,
    taxonomy_path: str | Path = TAXONOMY_PATH,
) -> CoverageConfig:
    policy = json.loads(Path(policy_path).read_text(encoding="utf-8"))
    taxonomy = json.loads(Path(taxonomy_path).read_text(encoding="utf-8"))
    _validate_policy(policy)
    _validate_taxonomy(taxonomy)
    return CoverageConfig(policy, taxonomy, stable_hash(policy), stable_hash(taxonomy))


def seed_taxonomy(session: Session, config: CoverageConfig | None = None) -> dict[str, int]:
    loaded = config or load_coverage_config()
    identities = {
        identity.website_id: identity.product_id
        for identity in session.scalars(
            select(ProductIdentityRecord).where(ProductIdentityRecord.website_id.is_not(None))
        )
    }
    intents_created = 0
    intents_updated = 0
    for item in loaded.taxonomy["intents"]:
        product_ids = sorted(
            identities[website_id]
            for website_id in item["websiteProductIds"]
            if website_id in identities
        )
        payload = {
            "query": item["query"],
            "audience": item["audience"],
            "occasion": item["occasion"],
            "locale": loaded.taxonomy["locale"],
            "season": item["season"],
            "eventDate": item["eventDate"],
            "evidenceState": item["evidenceState"],
            "confidenceBps": item["confidenceBps"],
            "evidenceReferences": item["evidenceReferences"],
            "productIds": product_ids,
        }
        intent = session.scalar(
            select(SearchIntentRecord).where(SearchIntentRecord.intent_key == item["key"])
        )
        if intent is None:
            intent = SearchIntentRecord(intent_key=item["key"], revision_hash=stable_hash(payload))
            session.add(intent)
            intents_created += 1
        else:
            intents_updated += int(intent.revision_hash != stable_hash(payload))
        intent.normalized_query = _normalized_query(item["query"])
        intent.audience = item["audience"]
        intent.occasion = item["occasion"]
        intent.locale = loaded.taxonomy["locale"]
        intent.season_key = item["season"]
        intent.event_date = date.fromisoformat(item["eventDate"]) if item["eventDate"] else None
        intent.evidence_state = item["evidenceState"]
        intent.confidence_bps = item["confidenceBps"]
        intent.evidence_ids_json = canonical_json(item["evidenceReferences"])
        intent.product_ids_json = canonical_json(product_ids)
        intent.revision_hash = stable_hash(payload)
        intent.lifecycle_state = "active"

    session.flush()
    intents = {
        intent.intent_key: intent
        for intent in session.scalars(
            select(SearchIntentRecord).where(SearchIntentRecord.lifecycle_state == "active")
        )
    }
    pages_created = 0
    for item in loaded.taxonomy["landingPageSeeds"]:
        page = session.scalar(
            select(LandingPageRecord).where(LandingPageRecord.website_id == item["websiteId"])
        )
        if page is None:
            page = LandingPageRecord(
                website_id=item["websiteId"],
                page_type=item["pageType"],
                canonical_path=item["canonicalPath"],
                readiness_state="seed_only",
            )
            session.add(page)
            pages_created += 1
        if page.readiness_state in {"", "seed_only"}:
            product_ids = sorted(
                identities[website_id]
                for website_id in item["websiteProductIds"]
                if website_id in identities
            )
            page.page_type = item["pageType"]
            page.canonical_path = item["canonicalPath"]
            page.website_product_ids_json = canonical_json(
                sorted(item["websiteProductIds"])
            )
            page.product_ids_json = canonical_json(product_ids)
            page.intent_keys_json = canonical_json(
                [key for key in item["intentKeys"] if key in intents]
            )
            page.lifecycle_state = "draft"
            page.readiness_state = "seed_only"
            page.readiness_reason = "Awaiting a complete typed website read."
            page.website_revision = loaded.taxonomy_hash
            page.checked_at = utc_now()
    session.flush()
    return {
        "intentsCreated": intents_created,
        "intentsUpdated": intents_updated,
        "pagesCreated": pages_created,
    }


def accept_catalog_snapshot(
    session: Session,
    payload: dict[str, Any],
    *,
    config: CoverageConfig | None = None,
    source_name: str = CATALOG_SOURCE,
) -> dict[str, Any]:
    loaded = config or load_coverage_config()
    products = payload.get("products")
    revision = payload.get("revision")
    count = payload.get("productCount")
    limit = loaded.policy["limits"]
    encoded_size = len(canonical_json(payload).encode("utf-8"))
    if (
        payload.get("contractVersion") != "v2"
        or payload.get("complete") is not True
        or not isinstance(products, list)
        or not isinstance(revision, str)
        or len(revision) != 64
        or count != len(products)
    ):
        raise ValueError("Only a complete, count-verified v2 catalog snapshot can be accepted.")
    if len(products) > limit["catalogProducts"] or encoded_size > limit["catalogBytes"]:
        raise ValueError("Catalog snapshot exceeds the reviewed Phase 2 work budget.")
    source_ids = [str(item.get("id", "")).strip() for item in products if isinstance(item, dict)]
    if len(source_ids) != len(products) or any(not item for item in source_ids):
        raise ValueError("Every catalog product requires a source ID.")
    if len(set(source_ids)) != len(source_ids):
        raise ValueError("Catalog snapshot contains duplicate source IDs.")

    _lock_source(session, source_name)
    checkpoint = session.scalar(
        select(CatalogSnapshotRecord)
        .where(CatalogSnapshotRecord.source_name == source_name)
        .with_for_update()
    )
    product_payloads = {str(item["id"]): item for item in products}
    current_hashes = {
        source_id: stable_hash(product_payloads[source_id]) for source_id in sorted(product_payloads)
    }
    payload_hash = stable_hash(current_hashes)
    if (
        checkpoint is not None
        and checkpoint.source_revision == revision
        and checkpoint.payload_hash == payload_hash
    ):
        return {
            "accepted": False,
            "changes": 0,
            "jobs": 0,
            "materializedProductIds": [],
            "revision": revision,
        }

    previous_hashes = (
        json.loads(checkpoint.product_hashes_json) if checkpoint is not None else {}
    )
    identity_by_website_id = {
        str(identity.website_id): identity
        for identity in session.scalars(
            select(ProductIdentityRecord).where(ProductIdentityRecord.website_id.is_not(None))
        )
    }
    changes: list[CatalogChangeRecord] = []
    created_jobs = 0
    materialized_product_ids: set[int] = set()
    for source_id in sorted(set(current_hashes) | set(previous_hashes)):
        before_hash = str(previous_hashes.get(source_id, ""))
        after_hash = str(current_hashes.get(source_id, ""))
        if before_hash == after_hash:
            continue
        change_type = "new" if not before_hash else "retired" if not after_hash else "updated"
        dedupe = stable_hash(
            {
                "source": source_name,
                "revision": revision,
                "product": source_id,
                "type": change_type,
                "before": before_hash,
                "after": after_hash,
            }
        )
        identity = identity_by_website_id.get(source_id)
        change = CatalogChangeRecord(
            source_name=source_name,
            source_revision=revision,
            source_product_id=source_id,
            product_id=identity.product_id if identity else None,
            change_type=change_type,
            before_hash=before_hash,
            after_hash=after_hash,
            deduplication_key=dedupe,
            payload_json=canonical_json(product_payloads.get(source_id, {})),
        )
        session.add(change)
        if identity is not None:
            if change_type == "retired":
                identity.mapping_state = "retired"
                identity.exception_reason = "absent_from_complete_website_catalog"
            elif identity.mapping_state == "retired":
                identity.mapping_state = "mapped"
                identity.exception_reason = ""
        session.flush()
        _, job_created = enqueue_job(
            session,
            job_type="coverage.materialize",
            payload={
                "catalogChangeId": change.id,
                "productId": change.product_id,
                "sourceProductId": source_id,
                "sourceRevision": revision,
                "changeType": change_type,
            },
            idempotency_key=f"coverage.materialize:{dedupe}",
            correlation_id=f"catalog:{revision[:16]}",
        )
        created_jobs += int(job_created)
        if change.product_id is not None:
            materialized_product_ids.add(change.product_id)
        changes.append(change)

    if checkpoint is None:
        checkpoint = CatalogSnapshotRecord(source_name=source_name)
        session.add(checkpoint)
    checkpoint.source_revision = revision
    checkpoint.payload_hash = payload_hash
    checkpoint.product_count = len(products)
    checkpoint.completeness_state = "complete"
    checkpoint.product_hashes_json = canonical_json(current_hashes)
    checkpoint.accepted_at = utc_now()
    session.flush()
    return {
        "accepted": True,
        "changes": len(changes),
        "jobs": created_jobs,
        "materializedProductIds": sorted(materialized_product_ids),
        "revision": revision,
    }


def enqueue_identity_materialization(
    session: Session,
    product_ids: list[int],
    *,
    source_revision: str,
) -> int:
    created_jobs = 0
    for product_id in sorted(set(product_ids)):
        identity = session.scalar(
            select(ProductIdentityRecord).where(
                ProductIdentityRecord.product_id == product_id
            )
        )
        mapping_revision = int(identity.mapping_revision or 0) if identity else 0
        _, created = enqueue_job(
            session,
            job_type="coverage.materialize",
            payload={
                "productId": product_id,
                "sourceRevision": source_revision,
                "trigger": "identity_repair",
            },
            idempotency_key=(
                f"coverage.materialize:identity:{product_id}:"
                f"{source_revision[:64]}:mapping-{mapping_revision}"
            ),
            correlation_id=f"identity:{source_revision[:16]}",
        )
        created_jobs += int(created)
    return created_jobs


def reproject_editorial_product_identities(session: Session) -> dict[str, Any]:
    identities = {
        str(item.website_id): item.product_id
        for item in session.scalars(
            select(ProductIdentityRecord).where(
                ProductIdentityRecord.website_id.is_not(None),
                ProductIdentityRecord.mapping_state == "mapped",
            )
        )
    }
    pages_updated = 0
    affected_product_ids: set[int] = set()
    for page in session.scalars(select(LandingPageRecord).order_by(LandingPageRecord.id)):
        website_product_ids = _json_str_list(page.website_product_ids_json)
        previous = _json_int_list(page.product_ids_json)
        projected = sorted(
            identities[website_id]
            for website_id in website_product_ids
            if website_id in identities
        )
        if projected != previous:
            page.product_ids_json = canonical_json(projected)
            pages_updated += 1
            affected_product_ids.update(previous)
            affected_product_ids.update(projected)
    session.flush()
    return {
        "pagesUpdated": pages_updated,
        "affectedProductIds": sorted(affected_product_ids),
    }


def reconcile_editorial_snapshot(
    session: Session,
    payload: dict[str, Any],
    *,
    config: CoverageConfig | None = None,
) -> dict[str, int | bool | str]:
    loaded = config or load_coverage_config()
    pages = payload.get("pages")
    revision = payload.get("revision")
    count = payload.get("pageCount")
    if (
        payload.get("contractVersion") != "v2"
        or payload.get("complete") is not True
        or not isinstance(pages, list)
        or count != len(pages)
        or not isinstance(revision, str)
        or len(revision) != 64
    ):
        raise ValueError("Only a complete, count-verified v2 editorial snapshot can be accepted.")
    if len(pages) > loaded.policy["limits"]["catalogProducts"]:
        raise ValueError("Editorial snapshot exceeds the reviewed Phase 2 work budget.")
    _lock_source(session, EDITORIAL_SOURCE)
    checkpoint = session.scalar(
        select(CatalogSnapshotRecord)
        .where(CatalogSnapshotRecord.source_name == EDITORIAL_SOURCE)
        .with_for_update()
    )
    page_by_id = {str(page.get("id", "")): page for page in pages if isinstance(page, dict)}
    if len(page_by_id) != len(pages) or "" in page_by_id:
        raise ValueError("Editorial snapshot contains missing or duplicate IDs.")
    page_hashes = {key: stable_hash(value) for key, value in sorted(page_by_id.items())}
    payload_hash = stable_hash(page_hashes)
    if checkpoint and checkpoint.source_revision == revision and checkpoint.payload_hash == payload_hash:
        return {"accepted": False, "pages": 0, "revision": revision}

    identities = {
        str(item.website_id): item.product_id
        for item in session.scalars(
            select(ProductIdentityRecord).where(ProductIdentityRecord.website_id.is_not(None))
        )
    }
    seen: set[str] = set()
    for website_id, item in page_by_id.items():
        _validate_editorial_page(item)
        seen.add(website_id)
        record = session.scalar(
            select(LandingPageRecord).where(LandingPageRecord.website_id == website_id)
        )
        if record is None:
            record = LandingPageRecord(
                website_id=website_id,
                page_type=item["pageType"],
                canonical_path=item["canonicalPath"],
            )
            session.add(record)
        record.page_type = item["pageType"]
        record.canonical_path = item["canonicalPath"]
        record.canonical_url = item["canonicalUrl"]
        record.website_revision = item["revision"]
        record.website_product_ids_json = canonical_json(
            sorted(str(product_id) for product_id in item["productIds"])
        )
        record.product_ids_json = canonical_json(
            sorted(
                identities[str(product_id)]
                for product_id in item["productIds"]
                if str(product_id) in identities
            )
        )
        record.intent_keys_json = canonical_json(sorted(item["intentKeys"]))
        record.lifecycle_state = item["status"]
        record.readiness_state = "ready" if item["ready"] and item["status"] == "published" else "not_ready"
        record.readiness_reason = item["readinessReason"]
        record.published_at = _parse_datetime(item.get("publishedAt"))
        record.checked_at = utc_now()

    for record in session.scalars(select(LandingPageRecord)):
        if record.website_id not in seen and record.readiness_state != "seed_only":
            record.lifecycle_state = "retired"
            record.readiness_state = "not_ready"
            record.readiness_reason = "Absent from the latest complete editorial snapshot."

    if checkpoint is None:
        checkpoint = CatalogSnapshotRecord(source_name=EDITORIAL_SOURCE)
        session.add(checkpoint)
    checkpoint.source_revision = revision
    checkpoint.payload_hash = payload_hash
    checkpoint.product_count = len(pages)
    checkpoint.completeness_state = "complete"
    checkpoint.product_hashes_json = canonical_json(page_hashes)
    checkpoint.accepted_at = utc_now()
    session.flush()
    return {"accepted": True, "pages": len(pages), "revision": revision}


def materialize_product_coverage(
    session: Session,
    product_id: int,
    *,
    source_revision: str,
    config: CoverageConfig | None = None,
    today: date | None = None,
) -> dict[str, int]:
    loaded = config or load_coverage_config()
    checked_date = today or date.today()
    product = session.get(ProductRecord, product_id)
    if product is None:
        raise LookupError(f"product {product_id} was not found")
    identity = session.scalar(
        select(ProductIdentityRecord).where(ProductIdentityRecord.product_id == product_id)
    )
    intents = [
        intent
        for intent in session.scalars(
            select(SearchIntentRecord)
            .where(SearchIntentRecord.lifecycle_state == "active")
            .order_by(SearchIntentRecord.intent_key)
        )
        if product_id in _json_int_list(intent.product_ids_json)
    ]
    if len(intents) > loaded.policy["limits"]["cellsPerMaterializationJob"]:
        raise ValueError("Coverage materialization exceeds the reviewed cell budget.")

    cells = 0
    suppressed = 0
    for intent in intents:
        matching_pages = _matching_pages(session, product_id, intent.intent_key)
        page = matching_pages[0] if matching_pages else None
        destination_ambiguous = len(
            [item for item in matching_pages if item.lifecycle_state == "published"]
        ) > 1
        content_format = "static_pin"
        dimensional_key = (
            f"product:{product_id}|intent:{intent.intent_key}|season:{intent.season_key}"
            f"|format:{content_format}|channel:pinterest"
        )
        cell = session.scalar(
            select(CoverageCellRecord).where(
                CoverageCellRecord.dimensional_key == dimensional_key
            )
        )
        if cell is None:
            cell = CoverageCellRecord(
                dimensional_key=dimensional_key,
                product_id=product_id,
                search_intent_id=intent.id,
                content_format=content_format,
            )
            session.add(cell)
        cell.season_key = intent.season_key
        cell.landing_page_id = page.id if page else None
        cell.channel = "pinterest"
        cell.coverage_state = _coverage_state(page)
        cell.freshness_state = _freshness_state(page, loaded)
        cell.source_revision = source_revision
        cell.last_observed_at = utc_now()
        cell.suppression_state, cell.suppression_reason = _suppression(
            identity, intent, checked_date, destination_ambiguous=destination_ambiguous
        )
        suppressed += int(bool(cell.suppression_state))
        cell.explanation_json = canonical_json(
            {
                "evidenceState": intent.evidence_state,
                "confidenceBps": intent.confidence_bps,
                "pageReadiness": page.readiness_state if page else "missing",
                "pageRevision": page.website_revision if page else "",
                "suppressionReason": cell.suppression_reason,
            }
        )
        session.flush()
        _score_cell(session, cell, product, intent, page, loaded, checked_date)
        cells += 1

    run_key = stable_hash(
        {
            "type": "coverage.materialize",
            "product": product_id,
            "sourceRevision": source_revision,
            "policy": loaded.policy_hash,
            "taxonomy": loaded.taxonomy_hash,
        }
    )
    run = session.scalar(
        select(DecisionRunRecord).where(DecisionRunRecord.run_key == run_key)
    )
    if run is None:
        run = DecisionRunRecord(
            run_key=run_key,
            run_type="coverage.materialize",
            input_revision=source_revision,
            score_version=loaded.policy["version"],
            considered_count=cells,
            selected_count=cells - suppressed,
            suppressed_count=suppressed,
            explanation_json=canonical_json(
                {
                    "policyHash": loaded.policy_hash,
                    "taxonomyHash": loaded.taxonomy_hash,
                    "tieBreakers": loaded.policy["tieBreakers"],
                }
            ),
        )
        session.add(run)
    session.flush()
    return {"cells": cells, "suppressed": suppressed}


def ingest_measurement_page(
    session: Session,
    payload: dict[str, Any],
    *,
    config: CoverageConfig | None = None,
    source_name: str = MEASUREMENT_SOURCE,
) -> dict[str, Any]:
    loaded = config or load_coverage_config()
    events = payload.get("events")
    next_cursor = payload.get("nextCursor")
    if (
        payload.get("contractVersion") != "v2"
        or not isinstance(events, list)
        or len(events) > loaded.policy["limits"]["measurementPageSize"]
        or not isinstance(next_cursor, str)
        or not isinstance(payload.get("hasMore"), bool)
    ):
        raise ValueError("Measurement page does not satisfy the reviewed v2 contract.")
    for item in events:
        _validate_measurement_event(item)
    event_keys = [str(item["eventKey"]) for item in events]
    if event_keys != sorted(set(event_keys)):
        raise ValueError("Measurement events must be unique and ordered by event key.")
    if event_keys and next_cursor != event_keys[-1]:
        raise ValueError("Measurement cursor must equal the last accepted event key.")
    _lock_source(session, source_name)
    cursor = session.scalar(
        select(MeasurementCursorRecord)
        .where(MeasurementCursorRecord.source_name == source_name)
        .with_for_update()
    )
    if cursor is None:
        cursor = MeasurementCursorRecord(source_name=source_name)
        session.add(cursor)
    elif cursor.opaque_cursor and next_cursor < cursor.opaque_cursor:
        raise ValueError("Measurement cursor cannot move backwards.")
    elif not event_keys and cursor.opaque_cursor and next_cursor != cursor.opaque_cursor:
        raise ValueError("An empty measurement page cannot skip the cursor forward.")
    created = 0
    affected_products: set[int] = set()
    last_event_key = cursor.last_event_key
    last_source_at = cursor.last_source_at
    for item in events:
        source_at = _parse_datetime(item.get("occurredAt"))
        if source_at is None:
            raise ValueError("Measurement event requires occurredAt.")
        website_product_id = item.get("productId")
        identity = (
            session.scalar(
                select(ProductIdentityRecord).where(
                    ProductIdentityRecord.website_id == str(website_product_id)
                )
            )
            if website_product_id is not None
            else None
        )
        landing_path = str(item.get("landingPath") or item.get("pagePath") or "")
        page = (
            session.scalar(
                select(LandingPageRecord).where(
                    LandingPageRecord.canonical_path == landing_path
                )
            )
            if landing_path
            else None
        )
        event, was_created = record_growth_event(
            session,
            {
                "event_id": item["eventId"],
                "event_type": item["eventName"],
                "campaign_id": item.get("campaignId", ""),
                "content_id": item.get("contentId", ""),
                "publication_id": item.get("publicationId", ""),
                "product_id": identity.product_id if identity else None,
                "source_timestamp": source_at,
                "attribution_quality": (
                    "utm_complete"
                    if item.get("campaignId") and item.get("contentId") and item.get("publicationId")
                    else "platform_only"
                ),
                "destination_url": f"https://{item.get('destinationHost', '')}",
                "properties": {
                    "landingPath": landing_path,
                    "pinId": item.get("pinId"),
                    "sourceEventKey": item.get("eventKey"),
                },
            },
        )
        if was_created:
            created += 1
            if identity:
                affected_products.add(identity.product_id)
            _record_event_outcomes(session, event, identity, page, item, loaded)
        last_event_key = str(item.get("eventKey") or last_event_key)
        last_source_at = max(filter(None, (last_source_at, source_at)), default=source_at)

    cursor.opaque_cursor = next_cursor
    cursor.last_event_key = last_event_key
    cursor.last_source_at = last_source_at
    cursor.ingested_count += created
    cursor.checkpointed_at = utc_now()
    for product_id in sorted(affected_products):
        enqueue_job(
            session,
            job_type="coverage.materialize",
            payload={
                "productId": product_id,
                "sourceRevision": last_event_key or stable_hash(payload),
                "trigger": "measurement",
            },
            idempotency_key=(
                f"coverage.materialize:measurement:{product_id}:"
                f"{stable_hash(last_event_key or next_cursor)[:32]}"
            ),
            correlation_id=f"measurement:{stable_hash(next_cursor)[:16]}",
        )
    session.flush()
    return {
        "created": created,
        "affectedProducts": sorted(affected_products),
        "nextCursor": next_cursor,
        "hasMore": payload["hasMore"],
    }


def coverage_read_model(session: Session, product_id: int | None = None) -> dict[str, Any]:
    statement = select(CoverageCellRecord)
    if product_id is not None:
        statement = statement.where(CoverageCellRecord.product_id == product_id)
    cells = list(session.scalars(statement))
    rows = [_serialize_cell(session, cell) for cell in cells]
    rows.sort(
        key=lambda row: (
            -int(row["nextActionScore"]),
            row["nextActionDate"] is None,
            row["nextActionDate"] or "",
            int(row["product"]["id"]),
            str(row["intent"]["key"]),
        )
    )
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return {
        "cells": rows,
        "count": len(rows),
        "generatedAt": utc_now().isoformat() + "Z",
    }


def coverage_exceptions(session: Session) -> dict[str, Any]:
    cells = list(
        session.scalars(
            select(CoverageCellRecord)
            .where(
                (CoverageCellRecord.suppression_state != "")
                | CoverageCellRecord.freshness_state.in_(("stale", "unknown"))
            )
            .order_by(CoverageCellRecord.product_id, CoverageCellRecord.id)
        )
    )
    identity_exceptions = [
        {
            "productId": item.product_id,
            "kind": "product_identity",
            "reason": item.exception_reason or item.mapping_state,
        }
        for item in session.scalars(
            select(ProductIdentityRecord)
            .where(ProductIdentityRecord.mapping_state != "mapped")
            .order_by(ProductIdentityRecord.product_id)
        )
    ]
    catalog_checkpoint = session.scalar(
        select(CatalogSnapshotRecord).where(
            CatalogSnapshotRecord.source_name == CATALOG_SOURCE
        )
    )
    catalog_ids = (
        sorted(json.loads(catalog_checkpoint.product_hashes_json))
        if catalog_checkpoint is not None
        else []
    )
    mapped_catalog_ids = {
        str(item.website_id)
        for item in session.scalars(
            select(ProductIdentityRecord).where(
                ProductIdentityRecord.website_id.is_not(None)
            )
        )
        if item.mapping_state in {"mapped", "retired"}
    }
    catalog_exceptions = [
        {
            "sourceProductId": source_id,
            "kind": "catalog_identity",
            "reason": "website_product_not_mapped",
        }
        for source_id in catalog_ids
        if source_id not in mapped_catalog_ids
    ]
    return {
        "coverage": [_serialize_cell(session, cell) for cell in cells],
        "identity": identity_exceptions,
        "catalog": catalog_exceptions,
        "count": len(cells) + len(identity_exceptions) + len(catalog_exceptions),
    }


def _score_cell(
    session: Session,
    cell: CoverageCellRecord,
    product: ProductRecord,
    intent: SearchIntentRecord,
    page: LandingPageRecord | None,
    config: CoverageConfig,
    checked_date: date,
) -> None:
    policy = config.policy
    defaults = policy["defaults"]
    cohort_names = {item["name"] for item in config.taxonomy["products"]}
    business = (
        defaults["cohortBusinessRelevance"]
        if product.name in cohort_names
        else defaults["otherBusinessRelevance"]
    )
    demand_raw = defaults["hypothesisDemand"]
    demand = demand_raw * intent.confidence_bps // policy["scoreScale"]
    seasonal, target_ready, publish_start = _seasonal_score(intent, policy, checked_date)
    outcome_cutoff = datetime.combine(
        checked_date - timedelta(days=policy["performance"]["rollingWindowDays"]),
        datetime.min.time(),
    )
    clicks = session.scalar(
        select(func.coalesce(func.sum(CoverageOutcomeRecord.observed_value), 0)).where(
            CoverageOutcomeRecord.coverage_cell_id == cell.id,
            CoverageOutcomeRecord.metric_name == "etsy_outbound_click",
            CoverageOutcomeRecord.maturity_window == "30d_performance",
            CoverageOutcomeRecord.period_end > outcome_cutoff,
        )
    )
    performance = min(
        policy["performance"]["maximum"],
        defaults["performancePrior"]
        + int(clicks or 0) * policy["performance"]["qualifiedClickIncrement"],
    )
    coverage_gap = policy["coverageGap"].get(cell.coverage_state, 0)
    internal_link = (
        defaults["missingPageInternalLinkValue"]
        if page is None
        else 5000 if page.readiness_state != "ready" else 2000
    )
    data_penalty = 0
    data_penalty_reasons: list[str] = []
    page_coverage_penalty = 0
    if cell.coverage_state == "published":
        page_coverage_penalty = policy["penalties"]["duplicateOrCovered"]
    if cell.freshness_state == "stale":
        data_penalty += policy["penalties"]["staleEvidence"]
        data_penalty_reasons.append("stale")
    if intent.evidence_state in {"hypothesis", "insufficient_evidence"}:
        data_penalty += policy["penalties"]["insufficientEvidence"]
        data_penalty_reasons.append("insufficient_evidence")

    page_components = {
        "businessRelevance": business,
        "demandEvidence": demand,
        "seasonalUrgency": seasonal,
        "performancePrior": performance,
        "coverageGap": coverage_gap,
        "internalLinkValue": internal_link,
    }
    publication_components = {
        "businessRelevance": business,
        "demandEvidence": demand,
        "seasonalUrgency": seasonal,
        "performancePrior": performance,
        "coverageGap": policy["coverageGap"]["missing"],
    }
    page_score = _weighted_score(
        page_components,
        policy["weights"]["page"],
        data_penalty + page_coverage_penalty,
    )
    publication_score = _weighted_score(
        publication_components, policy["weights"]["publication"], data_penalty
    )
    eligible = bool(
        page
        and page.lifecycle_state == "published"
        and page.readiness_state == "ready"
        and cell.freshness_state == "fresh"
        and not cell.suppression_state
        and (intent.event_date is None or checked_date <= intent.event_date)
        and (publish_start is None or checked_date >= publish_start)
    )
    blocker = (
        cell.suppression_reason
        or ("missing_destination_page" if page is None else "")
        or ("page_not_published" if page.lifecycle_state != "published" else "")
        or ("page_not_ready" if page.readiness_state != "ready" else "")
        or ("page_readiness_stale" if cell.freshness_state != "fresh" else "")
        or (
            "publication_window_not_open"
            if publish_start is not None and checked_date < publish_start
            else ""
        )
    )
    page_opportunity = session.scalar(
        select(PageOpportunityRecord).where(
            PageOpportunityRecord.coverage_cell_id == cell.id
        )
    )
    if page_opportunity is None:
        page_opportunity = PageOpportunityRecord(
            coverage_cell_id=cell.id,
            action_type="create_page",
            score=0,
            score_version=policy["version"],
            score_components_json="{}",
            explanation="",
        )
        session.add(page_opportunity)
    page_opportunity.action_type = (
        "create_page" if page is None else "refresh_page" if cell.coverage_state != "published" else "maintain_page"
    )
    page_opportunity.score = page_score
    page_opportunity.score_version = policy["version"]
    page_opportunity.score_components_json = canonical_json(
        {
            **page_components,
            "penalty": data_penalty + page_coverage_penalty,
            "penaltyReasons": [
                *data_penalty_reasons,
                *(["already_covered"] if page_coverage_penalty else []),
            ],
            "outcomeSignal": {
                "qualifiedEtsyClicks": int(clicks or 0),
                "inference": "observational",
            },
            "counterfactual": _counterfactual(
                page_score, page_components, policy["weights"]["page"]
            ),
        }
    )
    page_opportunity.explanation = (
        f"{page_opportunity.action_type} scores {page_score}/10000; "
        f"demand is {intent.evidence_state}; observed Etsy clicks={int(clicks or 0)}."
    )
    page_opportunity.target_ready_date = target_ready
    page_opportunity.lifecycle_state = "suppressed" if cell.suppression_state else "ranked"
    page_opportunity.scored_at = utc_now()

    publication = session.scalar(
        select(PublicationOpportunityRecord).where(
            PublicationOpportunityRecord.coverage_cell_id == cell.id
        )
    )
    if publication is None:
        publication = PublicationOpportunityRecord(
            coverage_cell_id=cell.id,
            action_type="create_pin",
            score=0,
            score_version=policy["version"],
            score_components_json="{}",
            explanation="",
            eligibility_reason="",
        )
        session.add(publication)
    publication.action_type = "create_pin"
    publication.score = publication_score
    publication.score_version = policy["version"]
    publication.score_components_json = canonical_json(
        {
            **publication_components,
            "penalty": data_penalty,
            "penaltyReasons": data_penalty_reasons,
            "outcomeSignal": {
                "qualifiedEtsyClicks": int(clicks or 0),
                "inference": "observational",
            },
            "counterfactual": _counterfactual(
                publication_score,
                publication_components,
                policy["weights"]["publication"],
            ),
        }
    )
    publication.explanation = (
        f"{publication.action_type} scores {publication_score}/10000; "
        f"eligibility={'ready' if eligible else blocker or 'blocked'}."
    )
    publication.eligible = eligible
    publication.eligibility_reason = "ready" if eligible else blocker or "not_ready"
    publication.publish_start_date = publish_start
    publication.lifecycle_state = "ranked" if eligible else "blocked"
    publication.scored_at = utc_now()
    session.flush()


def _serialize_cell(session: Session, cell: CoverageCellRecord) -> dict[str, Any]:
    page_opportunity = session.scalar(
        select(PageOpportunityRecord).where(
            PageOpportunityRecord.coverage_cell_id == cell.id
        )
    )
    publication = session.scalar(
        select(PublicationOpportunityRecord).where(
            PublicationOpportunityRecord.coverage_cell_id == cell.id
        )
    )
    if cell.suppression_state:
        next_action = "resolve_exception"
        next_score = 0
        next_date = None
        next_reason = cell.suppression_reason
    elif (
        publication is not None
        and publication.eligible
        and page_opportunity is not None
        and page_opportunity.action_type == "maintain_page"
    ):
        next_action = publication.action_type
        next_score = publication.score
        next_date = (
            publication.publish_start_date.isoformat()
            if publication.publish_start_date
            else None
        )
        next_reason = publication.explanation
    else:
        next_action = page_opportunity.action_type if page_opportunity else "materialize"
        next_score = page_opportunity.score if page_opportunity else 0
        next_date = (
            page_opportunity.target_ready_date.isoformat()
            if page_opportunity and page_opportunity.target_ready_date
            else None
        )
        next_reason = page_opportunity.explanation if page_opportunity else "Not scored."
    return {
        "id": cell.id,
        "product": {"id": cell.product.id, "name": cell.product.name},
        "intent": {
            "key": cell.search_intent.intent_key,
            "query": cell.search_intent.normalized_query,
            "evidenceState": cell.search_intent.evidence_state,
            "confidenceBps": cell.search_intent.confidence_bps,
        },
        "season": cell.season_key,
        "format": cell.content_format,
        "channel": cell.channel,
        "coverageState": cell.coverage_state,
        "freshnessState": cell.freshness_state,
        "suppressionState": cell.suppression_state,
        "suppressionReason": cell.suppression_reason,
        "landingPage": (
            {
                "path": cell.landing_page.canonical_path,
                "type": cell.landing_page.page_type,
                "status": cell.landing_page.lifecycle_state,
                "readiness": cell.landing_page.readiness_state,
            }
            if cell.landing_page
            else None
        ),
        "pageOpportunity": _serialize_page_opportunity(page_opportunity),
        "publicationOpportunity": _serialize_publication_opportunity(publication),
        "nextAction": next_action,
        "nextActionScore": next_score,
        "nextActionDate": next_date,
        "nextActionReason": next_reason,
    }


def _serialize_page_opportunity(item: PageOpportunityRecord | None) -> dict[str, Any] | None:
    if item is None:
        return None
    return {
        "action": item.action_type,
        "score": item.score,
        "scoreVersion": item.score_version,
        "components": json.loads(item.score_components_json),
        "explanation": item.explanation,
        "targetReadyDate": item.target_ready_date.isoformat() if item.target_ready_date else None,
        "state": item.lifecycle_state,
    }


def _serialize_publication_opportunity(
    item: PublicationOpportunityRecord | None,
) -> dict[str, Any] | None:
    if item is None:
        return None
    return {
        "action": item.action_type,
        "score": item.score,
        "scoreVersion": item.score_version,
        "components": json.loads(item.score_components_json),
        "explanation": item.explanation,
        "eligible": item.eligible,
        "eligibilityReason": item.eligibility_reason,
        "publishStartDate": item.publish_start_date.isoformat() if item.publish_start_date else None,
        "state": item.lifecycle_state,
    }


def _record_event_outcomes(
    session: Session,
    event: GrowthEventRecord,
    identity: ProductIdentityRecord | None,
    page: LandingPageRecord | None,
    source_item: dict[str, Any],
    config: CoverageConfig,
) -> None:
    performance = config.policy["performance"]
    destination_host = str(source_item.get("destinationHost", ""))
    future_cutoff = utc_now() + timedelta(seconds=performance["futureClockSkewSeconds"])
    qualified = bool(
        event.event_type == performance["qualifiedEventName"]
        and event.attribution_quality == performance["requiredAttributionQuality"]
        and identity is not None
        and page is not None
        and (
            destination_host == "etsy.com"
            or destination_host.endswith(".etsy.com")
        )
        and event.source_timestamp <= future_cutoff
    )
    if not qualified or identity is None or page is None:
        return
    cells = list(
        session.scalars(
            select(CoverageCellRecord).where(
                CoverageCellRecord.product_id == identity.product_id,
                *(
                    (CoverageCellRecord.landing_page_id == page.id,)
                    if page is not None
                    else ()
                ),
            )
        )
    )
    day_start = event.source_timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = day_start - timedelta(days=day_start.weekday())
    windows = (
        ("24h_diagnostic", day_start, day_start + timedelta(days=1)),
        ("7d_diagnostic", week_start, week_start + timedelta(days=7)),
        ("30d_performance", day_start, day_start + timedelta(days=1)),
    )
    for cell in cells or [None]:
        cell_id = cell.id if cell is not None else None
        for maturity_window, period_start, period_end in windows:
            outcome_key = (
                f"etsy_outbound_click:{maturity_window}:{identity.product_id}:{page.id}:"
                f"{cell_id or 0}:{period_start.date().isoformat()}"
            )
            outcome = session.scalar(
                select(CoverageOutcomeRecord).where(
                    CoverageOutcomeRecord.outcome_key == outcome_key
                )
            )
            if outcome is None:
                outcome = CoverageOutcomeRecord(
                    outcome_key=outcome_key,
                    coverage_cell_id=cell_id,
                    product_id=identity.product_id,
                    landing_page_id=page.id,
                    metric_name="etsy_outbound_click",
                    maturity_window=maturity_window,
                    observed_value=0,
                    period_start=period_start,
                    period_end=period_end,
                    source_revision=event.event_id,
                )
                session.add(outcome)
            outcome.observed_value += 1
            outcome.attribution_quality = event.attribution_quality
            outcome.inference_kind = "observational"
            outcome.source_revision = event.event_id
            outcome.explanation_json = canonical_json(
                {
                    "eventId": event.event_id,
                    "causal": False,
                    "reason": "Qualified product/page observation; no Phase 2 publication-to-cell causal join exists.",
                }
            )


def _matching_pages(
    session: Session, product_id: int, intent_key: str
) -> list[LandingPageRecord]:
    candidates = []
    for page in session.scalars(
        select(LandingPageRecord).order_by(LandingPageRecord.id)
    ):
        if (
            product_id in _json_int_list(page.product_ids_json)
            and intent_key in _json_str_list(page.intent_keys_json)
            and page.lifecycle_state != "retired"
        ):
            candidates.append(page)
    candidates.sort(
        key=lambda item: (
            item.readiness_state == "ready",
            item.lifecycle_state == "published",
            item.checked_at,
        ),
        reverse=True,
    )
    return candidates


def _coverage_state(page: LandingPageRecord | None) -> str:
    if page is None:
        return "missing"
    if page.lifecycle_state == "published" and page.readiness_state == "ready":
        return "published"
    return "planned"


def _freshness_state(
    page: LandingPageRecord | None, config: CoverageConfig
) -> str:
    if page is None:
        return "unknown"
    if page.readiness_state == "seed_only":
        return "unknown"
    cutoff = utc_now() - timedelta(hours=config.policy["freshness"]["landingPageHours"])
    return "fresh" if page.checked_at >= cutoff else "stale"


def _suppression(
    identity: ProductIdentityRecord | None,
    intent: SearchIntentRecord,
    checked_date: date,
    *,
    destination_ambiguous: bool = False,
) -> tuple[str, str]:
    if identity is None or identity.mapping_state != "mapped":
        return "suppressed", "product_identity_unresolved"
    if intent.lifecycle_state != "active":
        return "suppressed", "intent_inactive"
    if destination_ambiguous:
        return "suppressed", "destination_identity_ambiguous"
    if intent.event_date is not None and checked_date > intent.event_date:
        return "suppressed", "season_expired"
    return "", ""


def _seasonal_score(
    intent: SearchIntentRecord, policy: dict[str, Any], checked_date: date
) -> tuple[int, date | None, date | None]:
    seasonal = policy["seasonal"]
    if intent.event_date is None:
        return policy["defaults"]["evergreenSeasonalUrgency"], None, None
    target_ready = intent.event_date - timedelta(days=seasonal["targetReadyLeadDays"])
    publish_start = intent.event_date - timedelta(days=seasonal["publishStartLeadDays"])
    if checked_date < target_ready:
        urgency = seasonal["urgencyBeforeReady"]
    elif checked_date < publish_start:
        urgency = seasonal["urgencyReadyWindow"]
    elif checked_date <= intent.event_date:
        urgency = seasonal["urgencyPublishWindow"]
    else:
        urgency = seasonal["urgencyExpired"]
    return urgency, target_ready, publish_start


def _weighted_score(
    components: dict[str, int], weights: dict[str, int], penalty: int
) -> int:
    weighted = sum(components[key] * weights[key] for key in weights) // 10000
    return max(0, min(10000, weighted - penalty))


def _counterfactual(
    score: int,
    components: dict[str, int],
    weights: dict[str, int],
) -> dict[str, Any]:
    threshold = min(10000, ((score // 1000) + 1) * 1000)
    score_increase = max(0, threshold - score)
    candidates: list[tuple[int, str]] = []
    for key, value in components.items():
        weight = weights.get(key, 0)
        if not weight or score_increase == 0:
            continue
        required = (score_increase * 10000 + weight - 1) // weight
        if value + required <= 10000:
            candidates.append((required, key))
    candidates.sort(key=lambda item: (item[0], item[1]))
    smallest = (
        {
            "component": candidates[0][1],
            "increase": candidates[0][0],
            "from": components[candidates[0][1]],
            "to": components[candidates[0][1]] + candidates[0][0],
        }
        if candidates
        else None
    )
    return {
        "nextScoreThreshold": threshold,
        "scoreIncreaseRequired": score_increase,
        "smallestNamedComponentChange": smallest,
        "eligibilityRequires": "fresh_ready_published_destination_and_no_suppression",
    }


def _lock_source(session: Session, source_name: str) -> None:
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        lock_id = int(hashlib.sha256(source_name.encode("utf-8")).hexdigest()[:15], 16)
        session.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})


def _validate_policy(policy: dict[str, Any]) -> None:
    if policy.get("version") != "coverage-v1" or policy.get("scoreScale") != 10000:
        raise ValueError("Unsupported coverage policy.")
    for key in ("page", "publication"):
        weights = policy.get("weights", {}).get(key, {})
        if sum(weights.values()) != 10000 or any(
            not isinstance(value, int) or value < 0 for value in weights.values()
        ):
            raise ValueError(f"{key} weights must be nonnegative integers totaling 10000.")
    if policy.get("review", {}).get("gate") != "independent_phase2_strategy_automation_feedback_review":
        raise ValueError("Coverage policy review gate is missing.")


def _validate_taxonomy(taxonomy: dict[str, Any]) -> None:
    if taxonomy.get("version") != "taxonomy-v1" or taxonomy.get("locale") != "en-US":
        raise ValueError("Unsupported coverage taxonomy.")
    product_ids = [str(item.get("websiteId", "")) for item in taxonomy.get("products", [])]
    if not product_ids or len(product_ids) != len(set(product_ids)):
        raise ValueError("Taxonomy product IDs must be present and unique.")
    intent_keys = [str(item.get("key", "")) for item in taxonomy.get("intents", [])]
    if not intent_keys or len(intent_keys) != len(set(intent_keys)):
        raise ValueError("Taxonomy intent keys must be present and unique.")
    for item in taxonomy["intents"]:
        if item.get("evidenceState") not in {"observed", "hypothesis"}:
            raise ValueError("Intent evidence must be observed or hypothesis.")
        if not set(item.get("websiteProductIds", [])).issubset(product_ids):
            raise ValueError("Intent references an unknown website product ID.")
        if not 0 <= int(item.get("confidenceBps", -1)) <= 10000:
            raise ValueError("Intent confidence must be between 0 and 10000.")
    if taxonomy.get("review", {}).get("gate") != "independent_phase2_strategy_automation_feedback_review":
        raise ValueError("Coverage taxonomy review gate is missing.")


def _validate_editorial_page(item: dict[str, Any]) -> None:
    if (
        item.get("pageType") not in {"product", "collection", "guide", "article", "story"}
        or item.get("status") not in {"draft", "published", "retired"}
        or not isinstance(item.get("canonicalPath"), str)
        or not item["canonicalPath"].startswith("/")
        or not isinstance(item.get("canonicalUrl"), str)
        or not item["canonicalUrl"].startswith(("https://", "http://"))
        or not isinstance(item.get("revision"), str)
        or not isinstance(item.get("ready"), bool)
        or not isinstance(item.get("readinessReason"), str)
        or not isinstance(item.get("productIds"), list)
        or not isinstance(item.get("intentKeys"), list)
    ):
        raise ValueError("Editorial page does not satisfy the v2 read contract.")


def _validate_measurement_event(item: Any) -> None:
    if not isinstance(item, dict):
        raise ValueError("Measurement event must be an object.")
    event_id = item.get("eventId")
    occurred_at = item.get("occurredAt")
    event_key = item.get("eventKey")
    if (
        not isinstance(event_id, str)
        or not re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
            event_id,
            re.IGNORECASE,
        )
        or not isinstance(occurred_at, str)
        or event_key != f"{occurred_at}#{event_id}"
        or item.get("eventName") != "etsy_outbound_click"
        or not isinstance(item.get("destinationHost"), str)
        or not str(item["destinationHost"]).endswith("etsy.com")
    ):
        raise ValueError("Measurement event identity or destination is invalid.")


def _normalized_query(value: str) -> str:
    return " ".join(value.lower().strip().split())


def _json_int_list(value: str) -> list[int]:
    loaded = json.loads(value or "[]")
    return [int(item) for item in loaded]


def _json_str_list(value: str) -> list[str]:
    loaded = json.loads(value or "[]")
    return [str(item) for item in loaded]


def _parse_datetime(value: Any) -> datetime | None:
    if value in {None, ""}:
        return None
    if not isinstance(value, str):
        raise ValueError("Expected an ISO datetime string.")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
