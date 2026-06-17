from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..context import load_business_context
from ..db_models import (
    GeneratedContentCandidateRecord,
    PlannedContentRecord,
    ProductRecord,
    utc_now,
)
from ..phase3 import json_list
from .copywriter import generate_facebook_post
from .insights import brief_performance_context


DESTINATION_OPTIONS = ["Facebook", "Instagram", "Pinterest", "Blog post", "Etsy", "Website", "Email"]
GOAL_OPTIONS = [
    "Sales growth",
    "Repeat customers",
    "Followers",
    "Product awareness",
    "Email signup",
    "Blog traffic",
    "Seasonal launch",
    "Engagement",
]
PLANNED_STATUSES = ["planned", "brief_ready", "drafted", "needs_review", "approved", "posted", "skipped"]


@dataclass(frozen=True)
class ContentProductionResult:
    planned_item: PlannedContentRecord
    candidates: list[GeneratedContentCandidateRecord]
    created: int
    skipped: int


def create_planned_content_item(
    session: Session,
    calendar_date: date,
    destinations: list[str],
    goals: list[str],
    product_ids: list[int],
    audience: str = "",
    occasion: str = "",
    promotion: str = "",
    notes: str = "",
) -> PlannedContentRecord:
    if not destinations:
        raise ValueError("Choose at least one destination.")
    if not goals:
        raise ValueError("Choose at least one goal.")
    if not product_ids:
        raise ValueError("Choose at least one product focus.")

    valid_destinations = _valid_choices(destinations, DESTINATION_OPTIONS)
    valid_goals = _valid_choices(goals, GOAL_OPTIONS)
    if not valid_destinations:
        raise ValueError("Choose at least one valid destination.")
    if not valid_goals:
        raise ValueError("Choose at least one valid goal.")

    valid_products = list(session.scalars(select(ProductRecord).where(ProductRecord.id.in_(product_ids)).order_by(ProductRecord.id)))
    if not valid_products:
        raise ValueError("Choose at least one valid product focus.")

    record = PlannedContentRecord(
        calendar_date=calendar_date,
        destinations_json=json.dumps(valid_destinations),
        goals_json=json.dumps(valid_goals),
        product_ids_json=json.dumps([product.id for product in valid_products]),
        audience=audience.strip(),
        occasion=occasion.strip(),
        promotion=promotion.strip(),
        notes=notes.strip(),
        status="planned",
        brief_status="pending",
    )
    session.add(record)
    session.flush()
    return record


def planned_content_items(session: Session) -> list[PlannedContentRecord]:
    return list(session.scalars(select(PlannedContentRecord).order_by(PlannedContentRecord.calendar_date, PlannedContentRecord.id)))


def planned_items_needing_production(
    session: Session,
    target_date: date | None = None,
    channel: str | None = None,
    limit: int = 10,
) -> list[PlannedContentRecord]:
    query = select(PlannedContentRecord).where(PlannedContentRecord.status == "planned").order_by(
        PlannedContentRecord.calendar_date, PlannedContentRecord.id
    )
    if target_date is not None:
        query = query.where(PlannedContentRecord.calendar_date <= target_date)
    items = list(session.scalars(query))
    if channel:
        normalized = channel.lower()
        items = [item for item in items if any(destination.lower() == normalized for destination in destinations_for(item))]
    return items[:limit]


def build_content_brief(session: Session, item: PlannedContentRecord, business_dir: str = "docs/business") -> dict[str, object]:
    context = load_business_context(business_dir)
    products = products_for_item(session, item)
    return {
        "planned_item_id": item.id,
        "calendar_date": item.calendar_date.isoformat(),
        "destinations": destinations_for(item),
        "goals": goals_for(item),
        "products": [product.name for product in products],
        "product_facts": [_product_facts(product) for product in products],
        "audience": item.audience,
        "occasion": item.occasion,
        "promotion": item.promotion,
        "notes": item.notes,
        "voice_pillars": context.voice_pillars,
        "useful_phrases": context.useful_phrases[:5],
        "avoid": context.avoid[:5],
        "channels": context.channels,
        "performance_context": brief_performance_context(session),
    }


def produce_content_for_item(
    session: Session,
    item: PlannedContentRecord,
    business_dir: str = "docs/business",
    force: bool = False,
) -> ContentProductionResult:
    brief = build_content_brief(session, item, business_dir)
    created = 0
    skipped = 0
    candidates: list[GeneratedContentCandidateRecord] = []

    if "Facebook" in destinations_for(item):
        draft = generate_facebook_post(brief)
        body = json.dumps(
            {
                "hook": draft.hook,
                "body": draft.body,
                "cta": draft.cta,
                "quality_checklist": draft.quality_checklist,
            },
            indent=2,
        )
        candidate, was_created = upsert_candidate(
            session,
            item,
            candidate_type="facebook_post",
            provider="codex",
            body=body,
            source_facts=brief,
            force=force,
        )
        candidates.append(candidate)
        created += 1 if was_created else 0
        skipped += 0 if was_created else 1

    prompt_candidate, was_created = upsert_candidate(
        session,
        item,
        candidate_type="image_prompt_brief",
        provider="codex",
        body=_image_prompt_brief(brief),
        source_facts=brief,
        force=force,
    )
    candidates.append(prompt_candidate)
    created += 1 if was_created else 0
    skipped += 0 if was_created else 1

    item.brief_status = "ready"
    item.status = "needs_review" if candidates else item.status
    item.last_production_run_at = utc_now()
    item.production_error = ""
    return ContentProductionResult(item, candidates, created, skipped)


def upsert_candidate(
    session: Session,
    item: PlannedContentRecord,
    candidate_type: str,
    provider: str,
    body: str,
    source_facts: dict[str, object],
    force: bool = False,
) -> tuple[GeneratedContentCandidateRecord, bool]:
    existing = session.scalar(
        select(GeneratedContentCandidateRecord).where(
            GeneratedContentCandidateRecord.planned_item_id == item.id,
            GeneratedContentCandidateRecord.candidate_type == candidate_type,
            GeneratedContentCandidateRecord.provider == provider,
        )
    )
    if existing and not force:
        return existing, False
    if existing is None:
        existing = GeneratedContentCandidateRecord(
            planned_item_id=item.id,
            candidate_type=candidate_type,
            provider=provider,
        )
        session.add(existing)
        created = True
    else:
        created = False
    existing.body = body
    existing.source_facts_json = json.dumps(source_facts, indent=2)
    existing.review_state = "needs_review"
    existing.revision_notes = "Generated by the content production job; review before posting."
    return existing, created


def destinations_for(item: PlannedContentRecord) -> list[str]:
    return json_list(item.destinations_json)


def goals_for(item: PlannedContentRecord) -> list[str]:
    return json_list(item.goals_json)


def product_ids_for(item: PlannedContentRecord) -> list[int]:
    values: list[int] = []
    for raw in json_list(item.product_ids_json):
        try:
            values.append(int(raw))
        except ValueError:
            continue
    return values


def products_for_item(session: Session, item: PlannedContentRecord) -> list[ProductRecord]:
    ids = product_ids_for(item)
    if not ids:
        return []
    products = list(session.scalars(select(ProductRecord).where(ProductRecord.id.in_(ids)).order_by(ProductRecord.name)))
    return products


def serialize_planned_content_item(session: Session, item: PlannedContentRecord) -> dict[str, object]:
    return {
        "id": item.id,
        "calendar_date": item.calendar_date.isoformat(),
        "destinations": destinations_for(item),
        "goals": goals_for(item),
        "products": [{"id": product.id, "name": product.name} for product in products_for_item(session, item)],
        "audience": item.audience,
        "occasion": item.occasion,
        "promotion": item.promotion,
        "notes": item.notes,
        "status": item.status,
        "brief_status": item.brief_status,
        "last_production_run_at": item.last_production_run_at.isoformat() if item.last_production_run_at else None,
        "production_error": item.production_error,
        "candidates": [serialize_candidate(candidate) for candidate in item.candidates],
    }


def serialize_candidate(candidate: GeneratedContentCandidateRecord) -> dict[str, object]:
    return {
        "id": candidate.id,
        "planned_item_id": candidate.planned_item_id,
        "candidate_type": candidate.candidate_type,
        "provider": candidate.provider,
        "body": candidate.body,
        "source_facts": _json_dict(candidate.source_facts_json),
        "source_asset_ids": json_list(candidate.source_asset_ids_json),
        "review_state": candidate.review_state,
        "revision_notes": candidate.revision_notes,
        "created_at": candidate.created_at.isoformat() if candidate.created_at else None,
        "updated_at": candidate.updated_at.isoformat() if candidate.updated_at else None,
    }


def _valid_choices(values: list[str], allowed: list[str]) -> list[str]:
    allowed_lookup = {value.lower(): value for value in allowed}
    result: list[str] = []
    for value in values:
        canonical = allowed_lookup.get(str(value).strip().lower())
        if canonical and canonical not in result:
            result.append(canonical)
    return result


def _product_facts(product: ProductRecord) -> dict[str, object]:
    return {
        "id": product.id,
        "name": product.name,
        "status": product.status,
        "primary_audience": product.primary_audience,
        "best_channels": json_list(product.best_channels_json),
        "use_cases": json_list(product.use_cases_json),
        "seasonality": json_list(product.seasonality_json),
        "sales_momentum_note": product.sales_momentum_note,
        "canonical_url": product.canonical_url,
    }


def _image_prompt_brief(brief: dict[str, object]) -> str:
    products = ", ".join(str(item) for item in brief.get("products", [])) or "selected product"
    destinations = ", ".join(str(item) for item in brief.get("destinations", [])) or "social"
    return (
        f"Create product-accurate image directions for {products} for {destinations}. "
        "Use approved source assets only. Preserve product shape, color, printed details, and proportions. "
        "Return concepts that can be reviewed before any generated image is used."
    )


def _json_dict(value: str) -> dict[str, object]:
    try:
        data = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}
