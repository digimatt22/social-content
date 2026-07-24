from __future__ import annotations

import json
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db_models import DemandEvidenceRecord, GrowthEventRecord, utc_now


REQUIRED_FUNNEL_IDS = ("campaign_id", "content_id", "publication_id")


def tracked_destination_url(
    destination: str,
    *,
    campaign_id: str,
    content_id: str,
    publication_id: str,
    source: str = "pinterest",
    medium: str = "organic_social",
) -> str:
    identifiers = {
        "campaign_id": campaign_id,
        "content_id": content_id,
        "publication_id": publication_id,
    }
    missing = [name for name, value in identifiers.items() if not value.strip()]
    if missing:
        raise ValueError(f"missing funnel identifiers: {', '.join(missing)}")
    parsed = urlparse(destination)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update(
        {
            "utm_source": source,
            "utm_medium": medium,
            "utm_campaign": campaign_id,
            "utm_content": content_id,
            "publication_id": publication_id,
        }
    )
    return urlunparse(parsed._replace(query=urlencode(query)))


def record_growth_event(session: Session, payload: dict) -> tuple[GrowthEventRecord, bool]:
    event_id = str(payload.get("event_id", "")).strip()
    event_type = str(payload.get("event_type", "")).strip()
    if not event_id or not event_type or payload.get("source_timestamp") is None:
        raise ValueError("event_id, event_type, and source_timestamp are required")
    existing = session.scalar(select(GrowthEventRecord).where(GrowthEventRecord.event_id == event_id))
    if existing is not None:
        return existing, False
    event = GrowthEventRecord(
        event_id=event_id,
        event_type=event_type,
        campaign_id=str(payload.get("campaign_id", "")),
        content_id=str(payload.get("content_id", "")),
        publication_id=str(payload.get("publication_id", "")),
        product_id=payload.get("product_id"),
        session_id=str(payload.get("session_id", "")),
        source_timestamp=payload["source_timestamp"],
        attribution_quality=str(payload.get("attribution_quality", "unknown")),
        destination_url=str(payload.get("destination_url", "")),
        payload_json=json.dumps(payload.get("properties", {}), sort_keys=True),
    )
    session.add(event)
    session.flush()
    return event, True


def evidence_signal_state(evidence: DemandEvidenceRecord, *, now=None, freshness_hours: int = 48) -> str:
    checked_at = now or utc_now()
    if evidence.evidence_state in {"hypothesis", "invalid"}:
        return evidence.evidence_state
    if evidence.source_timestamp is None:
        return "insufficient_evidence"
    if evidence.source_timestamp < checked_at - timedelta(hours=freshness_hours):
        return "stale"
    return evidence.evidence_state


def funnel_contract_complete(event: GrowthEventRecord) -> bool:
    return all(getattr(event, name).strip() for name in REQUIRED_FUNNEL_IDS)
