from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

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
from .product_admin import ETSY_SHOP_URL
from .skill_adapters import copywriter_contract, image_creator_contracts


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
PLANNED_STATUSES = [
    "planned",
    "waiting_content_generation",
    "waiting_copy_regeneration",
    "waiting_image_generation",
    "waiting_image_regeneration",
    "brief_ready",
    "drafted",
    "needs_review",
    "approved",
    "posted",
    "skipped",
]
CANDIDATE_REVIEW_STATES = ["needs_review", "approved", "rejected", "rewrite_requested"]
IMAGE_OPTION_COUNT = 3
QUEUE_STATUSES = {
    "planned",
    "waiting_content_generation",
    "waiting_copy_regeneration",
    "waiting_image_generation",
    "waiting_image_regeneration",
}


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
    selected_source_asset_ids: list[int] | None = None,
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

    valid_destinations = _valid_choices(destinations, DESTINATION_OPTIONS)[:1]
    valid_goals = _valid_or_custom_choices(goals, GOAL_OPTIONS)[:1]
    if not valid_destinations:
        raise ValueError("Choose at least one valid destination.")
    if not valid_goals:
        raise ValueError("Choose at least one valid goal.")

    valid_products = list(session.scalars(select(ProductRecord).where(ProductRecord.id.in_(product_ids)).order_by(ProductRecord.id)))
    if not valid_products:
        raise ValueError("Choose at least one valid product focus.")
    selected_source_ids = _valid_selected_source_asset_ids(session, valid_products, selected_source_asset_ids or [])

    record = PlannedContentRecord(
        calendar_date=calendar_date,
        destinations_json=json.dumps(valid_destinations),
        goals_json=json.dumps(valid_goals),
        product_ids_json=json.dumps([product.id for product in valid_products]),
        selected_source_asset_ids_json=json.dumps(selected_source_ids),
        audience=audience.strip(),
        occasion=occasion.strip(),
        promotion=promotion.strip(),
        notes=notes.strip(),
        status="waiting_content_generation",
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
        if item.status in QUEUE_STATUSES or any(candidate.review_state == "rewrite_requested" for candidate in item.candidates)
    ]
    if channel:
        normalized = channel.lower()
        items = [item for item in items if any(destination.lower() == normalized for destination in destinations_for(item))]
    return items[:limit]


def has_rewrite_request(item: PlannedContentRecord) -> bool:
    return any(candidate.review_state == "rewrite_requested" for candidate in item.candidates)


def has_copy_rewrite_request(item: PlannedContentRecord) -> bool:
    return any(candidate.review_state == "rewrite_requested" and candidate.candidate_type == "facebook_post" for candidate in item.candidates)


def build_content_brief(session: Session, item: PlannedContentRecord, business_dir: str = "docs/business") -> dict[str, object]:
    context = load_business_context(business_dir)
    products = products_for_item(session, item)
    source_assets = source_assets_for_products(session, products)
    approved_source_assets = [asset for asset in source_assets if _asset_is_approved_source(asset)]
    selected_source_assets = _selected_source_assets(source_assets, selected_source_asset_ids_for(item))
    reference_assets = selected_source_assets or approved_source_assets
    return {
        "planned_item_id": item.id,
        "calendar_date": item.calendar_date.isoformat(),
        "destinations": destinations_for(item),
        "goals": goals_for(item),
        "products": [product.name for product in products],
        "product_facts": [_product_facts(product) for product in products],
        "source_assets": [_source_asset_facts(asset) for asset in source_assets],
        "approved_source_asset_ids": [asset.id for asset in approved_source_assets],
        "selected_source_asset_ids": [asset.id for asset in selected_source_assets],
        "reference_source_asset_ids": [asset.id for asset in reference_assets],
        "reference_source_assets": [_source_asset_facts(asset) for asset in reference_assets],
        "reference_selection_note": _reference_selection_note(selected_source_assets, reference_assets),
        "missing_inputs": _missing_inputs(source_assets, approved_source_assets, selected_source_assets),
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
    generate_copy = _should_generate_copy(item, force)
    queue_images = _should_queue_images(item)

    if generate_copy and "Facebook" in destinations_for(item):
        skill_contract = copywriter_contract(brief, "Facebook")
        draft = generate_facebook_post(brief)
        copy_text = "\n\n".join([draft.hook, draft.body])
        quality_score = score_copy_against_voice(copy_text, brief)
        body = json.dumps(
            {
                "skill": skill_contract.skill_name,
                "skill_request": skill_contract.request,
                "skill_check": skill_contract.check,
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

    if queue_images:
        _mark_image_generation_queued(item, brief)

    item.brief_status = "ready"
    item.status = _next_status_after_production(item)
    item.last_production_run_at = utc_now()
    if not queue_images:
        item.production_error = ""
    return ContentProductionResult(item, candidates, created, skipped)


def request_content_regeneration(session: Session, item_id: int, target: str, feedback: str = "") -> PlannedContentRecord:
    item = session.get(PlannedContentRecord, item_id)
    if item is None:
        raise ValueError(f"Planned content item not found: {item_id}")
    target = target.strip()
    feedback = feedback.strip()
    if target == "copy":
        for candidate in item.candidates:
            if candidate.candidate_type == "facebook_post":
                candidate.review_state = "rewrite_requested"
                candidate.revision_notes = feedback or "Copy regeneration requested from Planning."
        item.status = "waiting_copy_regeneration"
        item.brief_status = "queued"
    elif target == "images":
        for candidate in item.candidates:
            if candidate.candidate_type in {"image_asset_option", "image_option"}:
                candidate.review_state = "rewrite_requested"
                candidate.revision_notes = feedback or "Image regeneration requested from Planning."
        item.status = "waiting_image_regeneration"
        item.brief_status = "queued"
    else:
        raise ValueError("Regeneration target must be copy or images.")
    item.production_error = ""
    return item


def delete_planned_content_item(session: Session, item_id: int) -> None:
    item = session.get(PlannedContentRecord, item_id)
    if item is None:
        raise ValueError(f"Planned content item not found: {item_id}")
    session.delete(item)


def update_planned_copy_candidate(session: Session, candidate_id: int, copy_text: str) -> GeneratedContentCandidateRecord:
    candidate = session.get(GeneratedContentCandidateRecord, candidate_id)
    if candidate is None:
        raise ValueError(f"Generated content candidate not found: {candidate_id}")
    if candidate.planned_item.status in {"waiting_content_generation", "waiting_copy_regeneration"}:
        raise ValueError("Copy is queued for generation and cannot be edited yet.")
    update_facebook_candidate_copy(candidate, copy_text)
    candidate.review_state = "needs_review"
    candidate.revision_notes = "Edited in Planning."
    candidate.updated_at = utc_now()
    return candidate


def register_uploaded_image_option(
    session: Session,
    item_id: int,
    image_path: str | Path,
    name: str = "",
    notes: str = "",
) -> GeneratedContentCandidateRecord:
    item = session.get(PlannedContentRecord, item_id)
    if item is None:
        raise ValueError(f"Planned content item not found: {item_id}")
    path = Path(image_path)
    if not path.is_file():
        raise ValueError(f"Uploaded image file not found: {path}")
    products = products_for_item(session, item)
    product = products[0] if products else None
    asset = AssetRecord(
        product_id=product.id if product else None,
        name=name.strip() or f"Custom image for planned post #{item.id}",
        asset_type="user uploaded post image",
        source_path=path.as_posix(),
        preview_path=path.as_posix(),
        platform_suitability_json=json.dumps(destinations_for(item)),
        readiness_state="needs human review",
        notes=notes.strip() or "Uploaded from Planning for this post; review before use.",
        external_source="planning_upload",
        sync_status="uploaded",
        staleness_state="fresh",
        review_state="needs review",
        asset_role="post image option",
        brand_safe="review",
    )
    session.add(asset)
    session.flush()
    body = json.dumps(
        {
            "title": asset.name,
            "asset_id": asset.id,
            "source_path": asset.source_path,
            "preview_path": asset.preview_path,
            "provider_path": "user upload",
            "best_for": "Custom image uploaded by the user for this planned post.",
            "review_checklist": [
                "Image is the intended post visual.",
                "Product details look accurate.",
                "Crop fits the selected destination.",
                "No unwanted text, watermark, or off-brand details.",
            ],
        },
        indent=2,
    )
    candidate, _ = upsert_candidate(
        session,
        item,
        candidate_type="image_asset_option",
        provider="user_upload",
        body=body,
        source_facts=build_content_brief(session, item),
        source_asset_ids=[asset.id],
        force=True,
    )
    candidate.revision_notes = "Uploaded image option; review before posting."
    item.status = "needs_review"
    item.brief_status = "ready"
    item.production_error = ""
    return candidate


def register_generated_image_option(
    session: Session,
    item_id: int,
    image_path: str | Path,
    option_number: int,
    title: str = "",
    best_for: str = "",
    skill_request: dict[str, object] | None = None,
    skill_check: dict[str, object] | None = None,
    review_checklist: list[str] | None = None,
    provider: str = "codex_imagegen",
    notes: str = "",
) -> GeneratedContentCandidateRecord:
    item = session.get(PlannedContentRecord, item_id)
    if item is None:
        raise ValueError(f"Planned content item not found: {item_id}")
    path = Path(image_path)
    if not path.is_file():
        raise ValueError(f"Generated image file not found: {path}")
    if option_number < 1:
        raise ValueError("Image option number must be 1 or greater.")

    _supersede_rewrite_requested_image_options(item)
    products = products_for_item(session, item)
    product = products[0] if products else None
    option_title = title.strip() or f"Generated image option {option_number}"
    asset = AssetRecord(
        product_id=product.id if product else None,
        name=option_title,
        asset_type="generated post image",
        source_path=path.as_posix(),
        preview_path=path.as_posix(),
        platform_suitability_json=json.dumps(destinations_for(item)),
        readiness_state="needs human review",
        notes=notes.strip() or "Generated by Codex image automation; review before use.",
        external_source=provider,
        sync_status="generated",
        staleness_state="fresh",
        review_state="needs review",
        asset_role="post image option",
        brand_safe="review",
        generated_prompt=str((skill_request or {}).get("prompt") or (skill_request or {}).get("details") or ""),
    )
    session.add(asset)
    session.flush()
    body = json.dumps(
        {
            "title": option_title,
            "asset_id": asset.id,
            "source_path": asset.source_path,
            "preview_path": asset.preview_path,
            "provider_path": provider,
            "option_number": option_number,
            "best_for": best_for.strip() or "Generated image option for this planned post.",
            "skill_request": skill_request or {},
            "skill_check": skill_check or {},
            "review_checklist": review_checklist
            or [
                "Image is the intended post visual.",
                "Product details look accurate.",
                "Crop fits the selected destination.",
                "No unwanted text, watermark, or off-brand details.",
            ],
        },
        indent=2,
    )
    candidate, _ = upsert_candidate(
        session,
        item,
        candidate_type="image_asset_option",
        provider=f"{provider}_option_{option_number}",
        body=body,
        source_facts=build_content_brief(session, item),
        source_asset_ids=[asset.id],
        force=True,
    )
    candidate.revision_notes = "Generated image option; review before posting."
    item.status = "needs_review" if _has_reviewable_copy(item) else item.status
    item.brief_status = "ready"
    item.production_error = ""
    return candidate


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


def selected_source_asset_ids_for(item: PlannedContentRecord) -> list[int]:
    values: list[int] = []
    for raw in json_list(item.selected_source_asset_ids_json):
        try:
            values.append(int(raw))
        except (TypeError, ValueError):
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
    serialized_candidates = [serialize_candidate(candidate) for candidate in item.candidates]
    products = products_for_item(session, item)
    source_assets = source_assets_for_products(session, products)
    selected_source_ids = selected_source_asset_ids_for(item)
    return {
        "id": item.id,
        "calendar_date": item.calendar_date.isoformat(),
        "destinations": destinations_for(item),
        "goals": goals_for(item),
        "products": [{"id": product.id, "name": product.name} for product in products],
        "source_assets": [_source_asset_facts(asset) for asset in source_assets],
        "selected_source_asset_ids": selected_source_ids,
        "selected_source_assets": [_source_asset_facts(asset) for asset in _selected_source_assets(source_assets, selected_source_ids)],
        "audience": item.audience,
        "occasion": item.occasion,
        "promotion": item.promotion,
        "notes": item.notes,
        "status": item.status,
        "brief_status": item.brief_status,
        "last_production_run_at": item.last_production_run_at.isoformat() if item.last_production_run_at else None,
        "production_error": item.production_error,
        "candidates": serialized_candidates,
        "copy_candidates": [candidate for candidate in serialized_candidates if candidate["candidate_type"] == "facebook_post"],
        "image_candidates": [candidate for candidate in serialized_candidates if candidate["candidate_type"] == "image_asset_option"],
        "waiting_for_generation": item.status in QUEUE_STATUSES,
        "waiting_for_copy": item.status in {"waiting_content_generation", "waiting_copy_regeneration"},
        "waiting_for_images": item.status
        in {"waiting_content_generation", "waiting_image_generation", "waiting_image_regeneration"},
        "has_current_copy": any(
            candidate["candidate_type"] == "facebook_post" and candidate["review_state"] in {"needs_review", "approved"}
            for candidate in serialized_candidates
        ),
        "has_selected_image": any(
            candidate["candidate_type"] == "image_asset_option" and candidate["review_state"] == "approved"
            for candidate in serialized_candidates
        ),
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
        "image_option": _candidate_image_option(candidate.body),
        "image_asset": _candidate_image_asset(candidate.body),
        "skill_request": _candidate_skill_request(candidate.body),
        "skill_check": _candidate_skill_check(candidate.body),
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
    if review_state == "approved" and not reviewed_by.strip():
        label = "generated copy" if candidate.candidate_type == "facebook_post" else "generated image option"
        raise ValueError(f"Approved {label} must include a reviewer.")
    if edited_copy_text.strip():
        update_facebook_candidate_copy(candidate, edited_copy_text)
    candidate.review_state = review_state
    if candidate.candidate_type == "image_asset_option":
        _sync_image_asset_review(session, candidate, review_state, revision_notes)
    if revision_notes.strip():
        candidate.revision_notes = revision_notes.strip()
    if reviewed_by.strip():
        candidate.reviewed_by = reviewed_by.strip()
    if review_state != "needs_review" or reviewed_by.strip():
        candidate.reviewed_at = utc_now()
    return candidate


def _sync_image_asset_review(
    session: Session,
    candidate: GeneratedContentCandidateRecord,
    review_state: str,
    revision_notes: str,
) -> None:
    image_asset = _candidate_image_asset(candidate.body)
    if not image_asset:
        return
    try:
        asset_id = int(image_asset.get("asset_id"))
    except (TypeError, ValueError):
        return
    asset = session.get(AssetRecord, asset_id)
    if asset is None:
        return
    if review_state == "approved":
        asset.review_state = "approved"
        asset.readiness_state = "ready to use"
    elif review_state == "rejected":
        asset.review_state = "rejected"
        asset.readiness_state = "rejected"
    else:
        asset.review_state = "needs review"
        asset.readiness_state = "needs human review"
    if revision_notes.strip():
        asset.approval_notes = revision_notes.strip()


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
    selected_image_asset = _selected_image_asset(session, item)
    if selected_image_asset is None:
        raise ValueError("Select an image before creating a posting task.")
    asset = selected_image_asset
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
        if candidate.candidate_type != "facebook_post" or candidate.review_state not in {"needs_review", "approved"}:
            raise ValueError("Choose the current generated copy before creating a posting task.")
        candidate_copy = _candidate_copy_body(candidate.body)
        if candidate_copy:
            draft_caption = candidate_copy
        cta = _candidate_cta(candidate.body) or cta
        if candidate.review_state == "needs_review":
            candidate.review_state = "approved"
            candidate.reviewed_by = "Planning"
            candidate.reviewed_at = utc_now()
            if not candidate.revision_notes:
                candidate.revision_notes = "Selected as current copy while creating posting task."

    task = TaskRecord(
        plan_id=plan.id,
        planned_content_item_id=item.id,
        due_date=item.calendar_date,
        title=_task_title(item, selected_destination, product_name),
        owner_role=owner_for(selected_destination, content_type),
        platform=selected_destination,
        content_type=content_type,
        product_name=product_name,
        asset_id=asset.id,
        draft_caption=draft_caption,
        cta=cta,
        hashtags_json="[]",
        posting_steps_json=json.dumps(playbook["steps"]),
        preview_checklist_json=json.dumps(playbook["checklist"]),
        metric_instruction=_metric_instruction(selected_destination, goals_for(item), playbook),
        metric_status="not due",
        status="ready to post",
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


def _valid_or_custom_choices(values: list[str], allowed: list[str]) -> list[str]:
    result = _valid_choices(values, allowed)
    for value in values:
        clean = str(value).strip()
        if clean and clean != "__other__" and clean not in result:
            result.append(clean)
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
        if candidate.candidate_type in {"facebook_post", "blog_outline"} and candidate.review_state in {"needs_review", "approved"}:
            return candidate
    return None


def _should_generate_copy(item: PlannedContentRecord, force: bool) -> bool:
    if force:
        return True
    if item.status in {"planned", "waiting_content_generation", "waiting_copy_regeneration"}:
        return True
    return any(candidate.review_state == "rewrite_requested" and candidate.candidate_type == "facebook_post" for candidate in item.candidates)


def _should_queue_images(item: PlannedContentRecord) -> bool:
    if item.status in {"planned", "waiting_content_generation", "waiting_image_generation", "waiting_image_regeneration"}:
        return True
    return any(
        candidate.review_state == "rewrite_requested" and candidate.candidate_type in {"image_asset_option", "image_option"}
        for candidate in item.candidates
    )


def _has_reviewable_copy(item: PlannedContentRecord) -> bool:
    return any(candidate.candidate_type == "facebook_post" and candidate.review_state in {"needs_review", "approved"} for candidate in item.candidates)


def _has_reviewable_image(item: PlannedContentRecord) -> bool:
    return any(candidate.candidate_type == "image_asset_option" and candidate.review_state in {"needs_review", "approved"} for candidate in item.candidates)


def _supersede_rewrite_requested_image_options(item: PlannedContentRecord) -> None:
    for candidate in item.candidates:
        if candidate.candidate_type == "image_asset_option" and candidate.review_state == "rewrite_requested":
            candidate.review_state = "rejected"
            candidate.revision_notes = "Superseded by a generated image regeneration run."


def _selected_image_asset(session: Session, item: PlannedContentRecord) -> AssetRecord | None:
    for candidate in item.candidates:
        if candidate.candidate_type != "image_asset_option" or candidate.review_state != "approved":
            continue
        image_asset = _candidate_image_asset(candidate.body)
        if not image_asset:
            continue
        try:
            asset_id = int(image_asset.get("asset_id"))
        except (TypeError, ValueError):
            continue
        asset = session.get(AssetRecord, asset_id)
        if asset is not None:
            return asset
    return None


def _next_status_after_production(item: PlannedContentRecord) -> str:
    if _has_reviewable_copy(item) and _has_reviewable_image(item):
        return "needs_review"
    if _has_reviewable_copy(item):
        return "waiting_image_generation"
    return "waiting_content_generation"


def _mark_image_generation_queued(item: PlannedContentRecord, brief: dict[str, object]) -> None:
    contracts = image_creator_contracts(brief, count=IMAGE_OPTION_COUNT)
    item.production_error = (
        "Image generation is queued. Enable Codex image generation automation to turn "
        f"{len(contracts)} image-creator requests into reviewable image files."
    )


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
        return f"Shop the flock on Etsy: {ETSY_SHOP_URL}"
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


def _approved_source_asset_ids(brief: dict[str, object]) -> list[int]:
    values: list[int] = []
    raw_values = brief.get("reference_source_asset_ids") or brief.get("approved_source_asset_ids")
    if isinstance(raw_values, list):
        for raw in raw_values:
            try:
                values.append(int(raw))
            except (TypeError, ValueError):
                continue
    return values


def _asset_is_approved_source(asset: AssetRecord) -> bool:
    return bool(asset.file_exists and asset.review_state == "approved")


def _selected_source_assets(source_assets: list[AssetRecord], selected_ids: list[int]) -> list[AssetRecord]:
    if not selected_ids:
        return []
    by_id = {asset.id: asset for asset in source_assets}
    return [by_id[asset_id] for asset_id in selected_ids if asset_id in by_id and _asset_is_approved_source(by_id[asset_id])]


def _valid_selected_source_asset_ids(session: Session, products: list[ProductRecord], selected_ids: list[int]) -> list[int]:
    if not selected_ids:
        return []
    product_ids = {product.id for product in products}
    valid_assets = list(
        session.scalars(
            select(AssetRecord)
            .where(AssetRecord.id.in_(selected_ids))
            .where(AssetRecord.product_id.in_(product_ids))
            .order_by(AssetRecord.id)
        )
    )
    valid_by_id = {asset.id: asset for asset in valid_assets if _asset_is_approved_source(asset)}
    return [asset_id for asset_id in selected_ids if asset_id in valid_by_id]


def _missing_inputs(
    source_assets: list[AssetRecord],
    approved_source_assets: list[AssetRecord],
    selected_source_assets: list[AssetRecord],
) -> list[str]:
    missing: list[str] = []
    if not source_assets:
        missing.append("No source assets are linked to the planned product focus.")
    elif not approved_source_assets:
        missing.append("No approved file-backed source asset is ready for image generation.")
    return missing


def _reference_selection_note(selected_source_assets: list[AssetRecord], reference_assets: list[AssetRecord]) -> str:
    if selected_source_assets:
        return "Using the reference images selected on the planned post."
    if reference_assets:
        return "No reference images were selected; approved source assets will be used as the fallback identity lock."
    return "No reference images are ready for generation."


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
    if "prompt" in data and "title" in data:
        parts = [
            str(data.get("title") or "Image option").strip(),
            "Best for: " + str(data.get("best_for") or "").strip(),
            "Aspect ratio: " + str(data.get("aspect_ratio") or "").strip(),
            "Provider path: " + str(data.get("provider_path") or "").strip(),
            "Prompt:\n" + str(data.get("prompt") or "").strip(),
        ]
        checklist = data.get("review_checklist")
        if isinstance(checklist, list) and checklist:
            parts.append("Review checklist: " + "; ".join(str(item) for item in checklist))
        actions = data.get("user_actions")
        if isinstance(actions, list) and actions:
            parts.append("Actions: " + "; ".join(str(item) for item in actions))
        return "\n\n".join(part for part in parts if part.strip())
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


def _candidate_image_option(value: str) -> dict[str, object] | None:
    data = _json_dict(value)
    if "prompt" not in data or "title" not in data:
        return None
    return data


def _candidate_image_asset(value: str) -> dict[str, object] | None:
    data = _json_dict(value)
    if "asset_id" not in data or "source_path" not in data:
        return None
    return data


def _candidate_skill_request(value: str) -> dict[str, object] | None:
    data = _json_dict(value)
    request = data.get("skill_request")
    return request if isinstance(request, dict) else None


def _candidate_skill_check(value: str) -> dict[str, object] | None:
    data = _json_dict(value)
    check = data.get("skill_check")
    return check if isinstance(check, dict) else None
