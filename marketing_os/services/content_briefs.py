from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..context import load_business_context
from ..db_models import (
    AssetRecord,
    GeneratedContentCandidateRecord,
    PlanRecord,
    PlannedContentRecord,
    ProductRecord,
    TaskRecord,
    utc_now,
)
from ..phase3 import json_list, link_generated_content_to_task, owner_for, playbook_for
from .copywriter import generate_facebook_post, score_copy_against_voice
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
CANDIDATE_REVIEW_STATES = ["needs_review", "approved", "rejected", "rewrite_requested"]


@dataclass(frozen=True)
class ContentProductionResult:
    planned_item: PlannedContentRecord
    candidates: list[GeneratedContentCandidateRecord]
    created: int
    skipped: int


@dataclass(frozen=True)
class PlannedTaskResult:
    task: TaskRecord
    candidate: GeneratedContentCandidateRecord | None


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
    query = select(PlannedContentRecord).order_by(
        PlannedContentRecord.calendar_date, PlannedContentRecord.id
    )
    if target_date is not None:
        query = query.where(PlannedContentRecord.calendar_date <= target_date)
    candidates = list(session.scalars(query))
    items = [
        item
        for item in candidates
        if item.status == "planned" or any(candidate.review_state == "rewrite_requested" for candidate in item.candidates)
    ]
    if channel:
        normalized = channel.lower()
        items = [item for item in items if any(destination.lower() == normalized for destination in destinations_for(item))]
    return items[:limit]


def has_rewrite_request(item: PlannedContentRecord) -> bool:
    return any(candidate.review_state == "rewrite_requested" for candidate in item.candidates)


def build_content_brief(session: Session, item: PlannedContentRecord, business_dir: str = "docs/business") -> dict[str, object]:
    context = load_business_context(business_dir)
    products = products_for_item(session, item)
    source_assets = source_assets_for_products(session, products)
    approved_source_assets = [asset for asset in source_assets if _asset_is_approved_source(asset)]
    return {
        "planned_item_id": item.id,
        "calendar_date": item.calendar_date.isoformat(),
        "destinations": destinations_for(item),
        "goals": goals_for(item),
        "products": [product.name for product in products],
        "product_facts": [_product_facts(product) for product in products],
        "source_assets": [_source_asset_facts(asset) for asset in source_assets],
        "approved_source_asset_ids": [asset.id for asset in approved_source_assets],
        "missing_inputs": _missing_inputs(source_assets, approved_source_assets),
        "rewrite_requests": [_rewrite_request_facts(candidate) for candidate in item.candidates if candidate.review_state == "rewrite_requested"],
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
        copy_text = "\n\n".join([draft.hook, draft.body])
        quality_score = score_copy_against_voice(copy_text, brief)
        body = json.dumps(
            {
                "hook": draft.hook,
                "body": draft.body,
                "cta": draft.cta,
                "quality_checklist": draft.quality_checklist,
                "quality_score": {
                    "passed": quality_score.passed,
                    "warnings": quality_score.warnings,
                },
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
            source_asset_ids=_approved_source_asset_ids(brief),
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
        source_asset_ids=_approved_source_asset_ids(brief),
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
    source_asset_ids: list[int] | None = None,
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
            planned_item=item,
            candidate_type=candidate_type,
            provider=provider,
        )
        session.add(existing)
        created = True
    else:
        created = False
    existing.body = body
    existing.source_facts_json = json.dumps(source_facts, indent=2)
    existing.source_asset_ids_json = json.dumps(source_asset_ids or [])
    existing.review_state = "needs_review"
    existing.revision_notes = "Generated by the content production job; review before posting."
    session.flush()
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


def source_assets_for_products(session: Session, products: list[ProductRecord]) -> list[AssetRecord]:
    product_ids = [product.id for product in products if product.id is not None]
    if not product_ids:
        return []
    return list(
        session.scalars(
            select(AssetRecord)
            .where(AssetRecord.product_id.in_(product_ids))
            .where(AssetRecord.asset_type.in_(["source photo", "Etsy product photo", "edited photo", "external listing image"]))
            .order_by((AssetRecord.review_state == "approved").desc(), AssetRecord.file_exists.desc(), AssetRecord.product_id, AssetRecord.id)
        )
    )


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
        "copy_text": _candidate_copy_body(candidate.body),
        "display_body": _display_body(candidate.body),
        "source_facts": _json_dict(candidate.source_facts_json),
        "source_asset_ids": json_list(candidate.source_asset_ids_json),
        "review_state": candidate.review_state,
        "revision_notes": candidate.revision_notes,
        "reviewed_by": candidate.reviewed_by,
        "reviewed_at": candidate.reviewed_at.isoformat() if candidate.reviewed_at else None,
        "created_at": candidate.created_at.isoformat() if candidate.created_at else None,
        "updated_at": candidate.updated_at.isoformat() if candidate.updated_at else None,
    }


def record_candidate_review(
    session: Session,
    candidate_id: int,
    review_state: str,
    revision_notes: str = "",
    reviewed_by: str = "",
    edited_copy_text: str = "",
) -> GeneratedContentCandidateRecord:
    if review_state not in CANDIDATE_REVIEW_STATES:
        raise ValueError(f"Unsupported review state: {review_state}")
    candidate = session.get(GeneratedContentCandidateRecord, candidate_id)
    if candidate is None:
        raise ValueError(f"Generated content candidate not found: {candidate_id}")
    if edited_copy_text.strip():
        update_facebook_candidate_copy(candidate, edited_copy_text)
    candidate.review_state = review_state
    if revision_notes.strip():
        candidate.revision_notes = revision_notes.strip()
    if reviewed_by.strip():
        candidate.reviewed_by = reviewed_by.strip()
    if review_state != "needs_review" or reviewed_by.strip():
        candidate.reviewed_at = utc_now()
    return candidate


def update_facebook_candidate_copy(candidate: GeneratedContentCandidateRecord, copy_text: str) -> None:
    if candidate.candidate_type != "facebook_post":
        raise ValueError("Only Facebook post candidates can be edited as post copy.")
    paragraphs = [part.strip() for part in copy_text.replace("\r\n", "\n").split("\n\n") if part.strip()]
    if not paragraphs:
        raise ValueError("Edited Facebook copy cannot be blank.")

    existing = _json_dict(candidate.body)
    source_facts = _json_dict(candidate.source_facts_json)
    hook = paragraphs[0]
    body = "\n\n".join(paragraphs[1:]) if len(paragraphs) > 1 else hook
    cta = paragraphs[-1]
    quality_score = score_copy_against_voice("\n\n".join([hook, body]), source_facts)
    existing.update(
        {
            "hook": hook,
            "body": body,
            "cta": cta,
            "quality_score": {
                "passed": quality_score.passed,
                "warnings": quality_score.warnings,
            },
        }
    )
    candidate.body = json.dumps(existing, indent=2)


def create_task_from_planned_content(
    session: Session,
    item_id: int,
    destination: str | None = None,
    candidate_id: int | None = None,
) -> PlannedTaskResult:
    item = session.get(PlannedContentRecord, item_id)
    if item is None:
        raise ValueError(f"Planned content item not found: {item_id}")

    selected_destination = _selected_destination(item, destination)
    content_type = _content_type_for_destination(selected_destination)
    products = products_for_item(session, item)
    product_name = ", ".join(product.name for product in products) if products else "Planned product focus"
    primary_product = products[0] if products else None
    asset = _best_task_asset(session, primary_product)
    playbook = playbook_for(selected_destination, content_type)
    plan = session.scalars(select(PlanRecord).order_by(PlanRecord.generated_at.desc(), PlanRecord.id.desc())).first()
    if plan is None:
        raise ValueError("Create or seed a plan before creating posting tasks.")

    candidate = session.get(GeneratedContentCandidateRecord, candidate_id) if candidate_id else _approved_candidate_for_item(item)
    draft_caption = item.notes or f"Draft a {selected_destination} {content_type} for {product_name}."
    cta = _cta_for_goals(goals_for(item))
    if candidate is not None:
        if candidate.planned_item_id != item.id:
            raise ValueError("Candidate does not belong to this planned item.")
        if candidate.review_state != "approved":
            raise ValueError("Approve the generated candidate before creating a posting task from it.")
        candidate_copy = _candidate_copy_body(candidate.body)
        if candidate_copy:
            draft_caption = candidate_copy
        cta = _candidate_cta(candidate.body) or cta

    task = TaskRecord(
        plan_id=plan.id,
        planned_content_item_id=item.id,
        due_date=item.calendar_date,
        title=_task_title(item, selected_destination, product_name),
        owner_role=owner_for(selected_destination, content_type),
        platform=selected_destination,
        content_type=content_type,
        product_name=product_name,
        asset_id=asset.id if asset else None,
        draft_caption=draft_caption,
        cta=cta,
        hashtags_json="[]",
        posting_steps_json=json.dumps(playbook["steps"]),
        preview_checklist_json=json.dumps(playbook["checklist"]),
        metric_instruction=_metric_instruction(selected_destination, goals_for(item), playbook),
        metric_status="not due",
        status="ready to post" if asset else "needs asset",
        notes=_task_notes(item),
    )
    session.add(task)
    session.flush()
    if candidate is not None:
        link_generated_content_to_task(session, task.id, candidate.id)
    item.status = "approved" if candidate is not None else "brief_ready"
    return PlannedTaskResult(task=task, candidate=candidate)


def _valid_choices(values: list[str], allowed: list[str]) -> list[str]:
    allowed_lookup = {value.lower(): value for value in allowed}
    result: list[str] = []
    for value in values:
        canonical = allowed_lookup.get(str(value).strip().lower())
        if canonical and canonical not in result:
            result.append(canonical)
    return result


def _selected_destination(item: PlannedContentRecord, destination: str | None) -> str:
    destinations = destinations_for(item)
    if destination:
        for value in destinations:
            if value.lower() == destination.strip().lower():
                return value
        raise ValueError("Choose one of the planned destinations.")
    if not destinations:
        raise ValueError("Planned item has no destination.")
    return destinations[0]


def _content_type_for_destination(destination: str) -> str:
    lookup = {
        "Facebook": "post",
        "Instagram": "post",
        "Pinterest": "pin",
        "Blog post": "blog topic",
        "Website": "blog topic",
        "Etsy": "promotion",
        "Email": "email",
    }
    return lookup.get(destination, "post")


def _approved_candidate_for_item(item: PlannedContentRecord) -> GeneratedContentCandidateRecord | None:
    for candidate in item.candidates:
        if candidate.review_state == "approved" and candidate.candidate_type in {"facebook_post", "blog_outline"}:
            return candidate
    return None


def _best_task_asset(session: Session, product: ProductRecord | None) -> AssetRecord | None:
    if product is None:
        return None
    return session.scalar(
        select(AssetRecord)
        .where(AssetRecord.product_id == product.id)
        .where(AssetRecord.review_state.in_(["approved", "complete", "needs review", "unreviewed"]))
        .order_by(AssetRecord.file_exists.desc(), AssetRecord.review_state, AssetRecord.id)
    )


def _candidate_copy_body(value: str) -> str:
    data = _json_dict(value)
    if not data:
        return value.strip()
    pieces = [str(data.get("hook") or "").strip(), str(data.get("body") or "").strip()]
    return "\n\n".join(piece for piece in pieces if piece)


def _candidate_cta(value: str) -> str:
    data = _json_dict(value)
    return str(data.get("cta") or "").strip() if data else ""


def _cta_for_goals(goals: list[str]) -> str:
    if any(goal.lower() == "sales growth" for goal in goals):
        return "Take a look at the shop listing when you are ready."
    if any(goal.lower() == "followers" for goal in goals):
        return "Follow along for the next tiny build."
    if any(goal.lower() == "email signup" for goal in goals):
        return "Join the email list for new releases and behind-the-scenes notes."
    return "Reply with what you want to see next."


def _metric_instruction(destination: str, goals: list[str], playbook: dict[str, object]) -> str:
    goal_text = ", ".join(goals) if goals else "planned goal"
    return f"Track {destination} outcome for {goal_text}: {playbook.get('metric') or 'record reach, engagement, and notes later.'}"


def _task_title(item: PlannedContentRecord, destination: str, product_name: str) -> str:
    occasion = f" - {item.occasion}" if item.occasion else ""
    return f"{destination} planned post for {product_name}{occasion}"


def _task_notes(item: PlannedContentRecord) -> str:
    parts = []
    if item.audience:
        parts.append(f"Audience: {item.audience}")
    if item.occasion:
        parts.append(f"Occasion: {item.occasion}")
    if item.promotion:
        parts.append(f"Promotion: {item.promotion}")
    if item.notes:
        parts.append(f"Planning notes: {item.notes}")
    return "\n".join(parts)


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


def _source_asset_facts(asset: AssetRecord) -> dict[str, object]:
    return {
        "id": asset.id,
        "product_id": asset.product_id,
        "name": asset.name,
        "asset_type": asset.asset_type,
        "source_path": asset.source_path,
        "preview_path": asset.preview_path,
        "platform_suitability": json_list(asset.platform_suitability_json),
        "readiness_state": asset.readiness_state,
        "review_state": asset.review_state,
        "file_exists": bool(asset.file_exists),
        "file_checksum": asset.file_checksum,
        "file_size_bytes": asset.file_size_bytes,
        "mime_type": asset.mime_type,
        "width": asset.width,
        "height": asset.height,
        "external_source": asset.external_source,
        "external_id": asset.external_id,
        "canonical_url": asset.canonical_url,
        "rights": asset.rights,
        "brand_safe": asset.brand_safe,
    }


def _rewrite_request_facts(candidate: GeneratedContentCandidateRecord) -> dict[str, object]:
    return {
        "candidate_id": candidate.id,
        "candidate_type": candidate.candidate_type,
        "provider": candidate.provider,
        "review_state": candidate.review_state,
        "revision_notes": candidate.revision_notes,
        "reviewed_by": candidate.reviewed_by,
        "reviewed_at": candidate.reviewed_at.isoformat() if candidate.reviewed_at else None,
        "previous_copy_text": _candidate_copy_body(candidate.body),
    }


def _image_prompt_brief(brief: dict[str, object]) -> str:
    products = ", ".join(str(item) for item in brief.get("products", [])) or "selected product"
    destinations = ", ".join(str(item) for item in brief.get("destinations", [])) or "social"
    source_assets = [item for item in brief.get("source_assets", []) if isinstance(item, dict)]
    approved_ids = _approved_source_asset_ids(brief)
    source_line = (
        f"Use approved source asset IDs {', '.join(str(item) for item in approved_ids)}."
        if approved_ids
        else "No approved file-backed source asset is available yet; ask for one before image generation."
    )
    if source_assets and not approved_ids:
        source_line += " Candidate source assets exist but still need review or file checks."
    return (
        f"Create product-accurate image directions for {products} for {destinations}. "
        f"{source_line} Preserve product shape, color, printed details, and proportions. "
        "Return concepts that can be reviewed before any generated image is used."
    )


def _approved_source_asset_ids(brief: dict[str, object]) -> list[int]:
    values: list[int] = []
    raw_values = brief.get("approved_source_asset_ids")
    if isinstance(raw_values, list):
        for raw in raw_values:
            try:
                values.append(int(raw))
            except (TypeError, ValueError):
                continue
    return values


def _asset_is_approved_source(asset: AssetRecord) -> bool:
    return bool(asset.file_exists and asset.review_state == "approved")


def _missing_inputs(source_assets: list[AssetRecord], approved_source_assets: list[AssetRecord]) -> list[str]:
    missing: list[str] = []
    if not source_assets:
        missing.append("No source assets are linked to the planned product focus.")
    elif not approved_source_assets:
        missing.append("No approved file-backed source asset is ready for image generation.")
    return missing


def _json_dict(value: str) -> dict[str, object]:
    try:
        data = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _display_body(value: str) -> str:
    data = _json_dict(value)
    if not data:
        return value
    parts: list[str] = []
    for label, key in (("Hook", "hook"), ("Body", "body"), ("CTA", "cta")):
        text = str(data.get(key) or "").strip()
        if text:
            parts.append(f"{label}: {text}")
    checklist = data.get("quality_checklist")
    if isinstance(checklist, list) and checklist:
        parts.append("Quality checklist: " + "; ".join(str(item) for item in checklist))
    score = data.get("quality_score")
    if isinstance(score, dict):
        passed = score.get("passed")
        warnings = score.get("warnings")
        if isinstance(passed, list) and passed:
            parts.append("Quality passed: " + "; ".join(str(item) for item in passed))
        if isinstance(warnings, list) and warnings:
            parts.append("Quality warnings: " + "; ".join(str(item) for item in warnings))
    return "\n\n".join(parts) or value
