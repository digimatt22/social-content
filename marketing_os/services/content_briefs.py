from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..context import load_business_context
from ..db_models import (
    AssetRecord,
    EtsyReviewRecord,
    GeneratedContentCandidateRecord,
    PlanRecord,
    PlannedContentRecord,
    ProductRecord,
    ProductSalesRecord,
    TaskRecord,
    utc_now,
)
from ..phase3 import json_list, link_generated_content_to_task, owner_for, playbook_for
from ..phase4 import MANAGED_PRODUCT_ASSETS_ROOT, ensure_local_asset_for_remote_image
from .insights import brief_performance_context
from .product_admin import ETSY_SHOP_URL
from .skill_adapters import copywriter_contract, social_media_art_director_contracts


DESTINATION_OPTIONS = ["Facebook", "Instagram", "Pinterest", "Blog post", "Etsy", "Website", "Email"]
PLATFORM_DEFAULT_SCHEDULED_TIMES = {
    "Facebook": "18:30",
    "Instagram": "12:30",
    "Pinterest": "20:30",
    "Blog post": "10:00",
    "Etsy": "10:00",
    "Website": "10:00",
    "Email": "09:30",
}
GOAL_OPTIONS = [
    "Cruise community engagement",
    "Duck personality spotlight",
    "Flock building",
    "Etsy shop visits",
    "Gift consideration",
    "Follower growth",
    "Maker process trust",
    "Seasonal or occasion push",
    "Sales growth",
    "Repeat customers",
    "Followers",
    "Product awareness",
    "Email signup",
    "Blog traffic",
    "Seasonal launch",
    "Engagement",
]
PLANNER_GOAL_OPTIONS = GOAL_OPTIONS[:8]
AUDIENCE_OPTIONS = [
    "Cruise Duckers",
    "Gift Buyers",
    "Collectors / Flock Builders",
    "Desk Decor Buyers",
    "Handmade Shoppers",
    "Duck Duck Jeep Community",
    "Hobby, Profession, Or Identity Buyers",
    "Event And Convention Buyers",
]
OCCASION_OPTIONS = [
    "Cruise duck hiding",
    "Room steward gift",
    "Found duck story",
    "Gift idea",
    "New flock member",
    "Collection spotlight",
    "Duck Duck Jeep",
    "Desk mascot moment",
    "Maker process",
    "Seasonal launch",
]
PROMOTION_OPTIONS = [
    "Find your favorite duck in our Etsy shop",
    "Add a new duck to your flock",
    "See the full flock on Etsy",
    "Start your flock today",
    "Available in the Etsy shop",
    "New design spotlight",
    "Good gift idea",
]
PLANNED_STATUSES = [
    "planned",
    "waiting_asset_download",
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
AUTOMATION_REFERENCE_MIN_PER_PRODUCT = 2
QUEUE_STATUSES = {
    "planned",
    "waiting_content_generation",
    "waiting_copy_regeneration",
    "waiting_image_generation",
    "waiting_image_regeneration",
}
SOCIAL_DESTINATIONS = {"Facebook", "Instagram", "Pinterest", "Threads", "TikTok", "LinkedIn"}


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
    scheduled_time: str | None = None,
    selected_source_asset_ids: list[int] | None = None,
    assets_root: str | Path = MANAGED_PRODUCT_ASSETS_ROOT,
    defer_remote_assets: bool = False,
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
    default_scheduled_time = default_scheduled_time_for_destination(valid_destinations[0])

    valid_products = list(session.scalars(select(ProductRecord).where(ProductRecord.id.in_(product_ids)).order_by(ProductRecord.id)))
    if not valid_products:
        raise ValueError("Choose at least one valid product focus.")
    automatic_source_asset_ids = (
        automation_reference_asset_ids_for_products(session, valid_products)
        if selected_source_asset_ids is None
        else []
    )
    if selected_source_asset_ids is None:
        requested_source_asset_ids = automatic_source_asset_ids or None
    else:
        requested_source_asset_ids = selected_source_asset_ids
    selected_source_ids = _valid_selected_source_asset_ids(
        session,
        valid_products,
        requested_source_asset_ids,
        assets_root=assets_root,
        defer_remote_assets=defer_remote_assets,
    )
    has_deferred_remote_assets = defer_remote_assets and _has_remote_selected_source_asset(session, selected_source_ids)

    record = PlannedContentRecord(
        calendar_date=calendar_date,
        scheduled_time=normalize_scheduled_time(scheduled_time, fallback=default_scheduled_time),
        destinations_json=json.dumps(valid_destinations),
        goals_json=json.dumps(valid_goals),
        product_ids_json=json.dumps([product.id for product in valid_products]),
        selected_source_asset_ids_json=json.dumps(selected_source_ids),
        audience=audience.strip(),
        occasion=occasion.strip(),
        promotion=promotion.strip(),
        notes=notes.strip(),
        status="waiting_asset_download" if has_deferred_remote_assets else "waiting_content_generation",
        brief_status="pending",
        production_error="Preparing selected remote image references." if has_deferred_remote_assets else "",
    )
    session.add(record)
    session.flush()
    return record


def update_planned_content_schedule(
    session: Session,
    item_id: int,
    calendar_date: date,
    scheduled_time: str = "09:00",
) -> PlannedContentRecord:
    item = session.get(PlannedContentRecord, item_id)
    if item is None:
        raise ValueError("Planned content item not found.")
    item.calendar_date = calendar_date
    item.scheduled_time = normalize_scheduled_time(scheduled_time)
    for task in _tasks_for_planned_item(session, item_id):
        task.due_date = calendar_date
        task.scheduled_time = item.scheduled_time
    session.flush()
    return item


def update_planned_content_details(
    session: Session,
    item_id: int,
    calendar_date: date,
    scheduled_time: str,
    destinations: list[str],
    goals: list[str],
    audience: str = "",
    occasion: str = "",
    promotion: str = "",
    notes: str = "",
) -> PlannedContentRecord:
    item = session.get(PlannedContentRecord, item_id)
    if item is None:
        raise ValueError("Planned content item not found.")
    valid_destinations = _valid_choices(destinations, DESTINATION_OPTIONS)[:1]
    valid_goals = _valid_or_custom_choices(goals, GOAL_OPTIONS)[:1]
    if not valid_destinations:
        raise ValueError("Choose at least one valid destination.")
    if not valid_goals:
        raise ValueError("Choose at least one valid goal.")
    item.calendar_date = calendar_date
    item.scheduled_time = normalize_scheduled_time(scheduled_time)
    item.destinations_json = json.dumps(valid_destinations)
    item.goals_json = json.dumps(valid_goals)
    item.audience = audience.strip()
    item.occasion = occasion.strip()
    item.promotion = promotion.strip()
    item.notes = notes.strip()
    for task in _tasks_for_planned_item(session, item_id):
        task.due_date = item.calendar_date
        task.scheduled_time = item.scheduled_time
        task.platform = valid_destinations[0]
    session.flush()
    return item


def localize_planned_content_reference_assets(
    session: Session,
    item_id: int,
    assets_root: str | Path = MANAGED_PRODUCT_ASSETS_ROOT,
) -> PlannedContentRecord:
    item = session.get(PlannedContentRecord, item_id)
    if item is None:
        raise ValueError(f"Planned content item not found: {item_id}")
    selected_ids = selected_source_asset_ids_for(item)
    if not selected_ids:
        raise ValueError("Planned content item has no selected reference images.")
    localized_ids: list[int] = []
    for asset_id in selected_ids:
        asset = session.get(AssetRecord, asset_id)
        if asset is None:
            continue
        if asset.hidden_from_generation:
            continue
        if _asset_is_approved_source(asset):
            localized_ids.append(asset.id)
        elif _asset_is_remote_product_image(asset):
            localized_ids.append(ensure_local_asset_for_remote_image(session, asset, assets_root).id)
    if not localized_ids:
        raise ValueError("No selected reference images could be prepared.")
    item.selected_source_asset_ids_json = json.dumps(localized_ids)
    if item.status == "waiting_asset_download":
        item.status = "waiting_content_generation"
    item.production_error = ""
    session.flush()
    return item


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
        "product_facts": [_product_facts(session, product) for product in products],
        "source_assets": [_source_asset_facts(asset) for asset in source_assets],
        "approved_source_asset_ids": [asset.id for asset in approved_source_assets],
        "selected_source_asset_ids": [asset.id for asset in selected_source_assets],
        "reference_source_asset_ids": [asset.id for asset in reference_assets],
        "reference_source_assets": [_source_asset_facts(asset) for asset in reference_assets],
        "reference_selection_note": _reference_selection_note(selected_source_assets, reference_assets),
        "missing_inputs": _missing_inputs(source_assets, approved_source_assets, selected_source_assets),
        "rewrite_requests": [_rewrite_request_facts(candidate) for candidate in item.candidates if candidate.review_state == "rewrite_requested"],
        "reviewable_copy": _reviewable_copy_facts(item),
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
    queue_copy = _should_generate_copy(item, force) and _has_social_destination(item)
    queue_images = _should_queue_images(item)

    if queue_images:
        _mark_image_generation_queued(item, brief)
    if queue_copy:
        item.production_error = _append_production_note(
            item.production_error,
            "Copy generation is queued. Use the exported social copy workflow and register the agent-written copy before review.",
        )

    item.brief_status = "ready"
    item.status = _next_status_after_production(item)
    item.last_production_run_at = utc_now()
    if not queue_images and not queue_copy:
        item.production_error = ""
    return ContentProductionResult(item, candidates, created, skipped)


def register_generated_copy_candidate(
    session: Session,
    item_id: int,
    copy_text: str,
    skill_request: dict[str, object] | None = None,
    skill_check: dict[str, object] | None = None,
    social_strategy: dict[str, object] | None = None,
    social_challenge: dict[str, object] | None = None,
    provider: str = "codex_agent",
    notes: str = "",
) -> GeneratedContentCandidateRecord:
    item = session.get(PlannedContentRecord, item_id)
    if item is None:
        raise ValueError(f"Planned content item not found: {item_id}")
    parsed = _parse_copy_text(copy_text)
    if not parsed["copy_text"]:
        raise ValueError("Generated copy cannot be blank.")
    source_facts = build_content_brief(session, item)
    body = json.dumps(
        {
            "skill": "social-media-copywriter",
            "skill_request": skill_request or copywriter_contract(source_facts, "Facebook").request,
            "skill_check": skill_check or {},
            "social_strategy": social_strategy or {},
            "hook": parsed["hook"],
            "body": parsed["body"],
            "cta": parsed["cta"],
            "social_challenge": social_challenge or {},
            "quality_score": {
                "passed": [],
                "warnings": [],
                "source": "agent_challenge",
            },
        },
        indent=2,
    )
    _supersede_rewrite_requested_copy(item)
    candidate, _ = upsert_candidate(
        session,
        item,
        candidate_type="facebook_post",
        provider=provider,
        body=body,
        source_facts=source_facts,
        source_asset_ids=_approved_source_asset_ids(source_facts),
        force=True,
    )
    candidate.revision_notes = notes.strip() or "Agent-written copy registered for human review."
    item.brief_status = "ready"
    item.status = "needs_review" if _has_reviewable_image(item) else "waiting_image_generation"
    item.production_error = ""
    return candidate


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
            .where(AssetRecord.hidden_from_generation == 0)
            .order_by((AssetRecord.review_state == "approved").desc(), AssetRecord.file_exists.desc(), AssetRecord.product_id, AssetRecord.id)
        )
    )


def default_reference_asset_ids_for_products(session: Session, products: list[ProductRecord]) -> list[int]:
    product_ids = [product.id for product in products if product.id is not None]
    if not product_ids:
        return []
    return [
        asset.id
        for asset in session.scalars(
            select(AssetRecord)
            .where(AssetRecord.product_id.in_(product_ids))
            .where(AssetRecord.default_reference == 1)
            .where(AssetRecord.asset_type.in_(["source photo", "Etsy product photo", "edited photo", "external listing image"]))
            .where(AssetRecord.hidden_from_generation == 0)
            .order_by(AssetRecord.product_id, AssetRecord.id)
        )
    ]


def automation_reference_asset_ids_for_products(
    session: Session,
    products: list[ProductRecord],
    min_per_product: int = AUTOMATION_REFERENCE_MIN_PER_PRODUCT,
) -> list[int]:
    selected_ids: list[int] = []
    seen: set[int] = set()
    for product in products:
        if product.id is None:
            continue
        product_ids: list[int] = []
        default_assets = list(
            session.scalars(
                select(AssetRecord)
                .where(AssetRecord.product_id == product.id)
                .where(AssetRecord.default_reference == 1)
                .where(AssetRecord.asset_type.in_(["source photo", "Etsy product photo", "edited photo", "external listing image"]))
                .where(AssetRecord.hidden_from_generation == 0)
                .order_by(AssetRecord.id)
            )
        )
        for asset in default_assets:
            if _asset_can_be_automation_reference(asset) and asset.id not in seen:
                product_ids.append(asset.id)
                selected_ids.append(asset.id)
                seen.add(asset.id)

        needed = max(0, min_per_product - len(product_ids))
        if needed == 0:
            continue
        fallback_assets = [
            asset
            for asset in session.scalars(
                select(AssetRecord)
                .where(AssetRecord.product_id == product.id)
                .where(AssetRecord.asset_type.in_(["source photo", "Etsy product photo", "edited photo", "external listing image"]))
                .where(AssetRecord.hidden_from_generation == 0)
                .order_by(AssetRecord.id)
            )
            if asset.id not in seen and _asset_can_be_automation_reference(asset)
        ]
        random.shuffle(fallback_assets)
        for asset in fallback_assets[:needed]:
            product_ids.append(asset.id)
            selected_ids.append(asset.id)
            seen.add(asset.id)
    return selected_ids


def update_product_default_reference_assets(session: Session, product_id: int, asset_ids: list[int]) -> list[int]:
    product = session.get(ProductRecord, product_id)
    if product is None:
        raise ValueError("Product not found.")
    assets = list(
        session.scalars(
            select(AssetRecord)
            .where(AssetRecord.product_id == product_id)
            .where(AssetRecord.asset_type.in_(["source photo", "Etsy product photo", "edited photo", "external listing image"]))
            .where(AssetRecord.hidden_from_generation == 0)
            .order_by(AssetRecord.id)
        )
    )
    valid_ids = {asset.id for asset in assets}
    selected_ids = [asset_id for asset_id in asset_ids if asset_id in valid_ids]
    selected_lookup = set(selected_ids)
    for asset in assets:
        asset.default_reference = 1 if asset.id in selected_lookup else 0
    session.flush()
    return selected_ids


def serialize_planned_content_item(session: Session, item: PlannedContentRecord) -> dict[str, object]:
    serialized_candidates = [serialize_candidate(candidate) for candidate in item.candidates]
    visible_image_candidates = [
        candidate
        for candidate in serialized_candidates
        if candidate["candidate_type"] == "image_asset_option" and _candidate_has_visible_image_asset(session, candidate)
    ]
    products = products_for_item(session, item)
    source_assets = source_assets_for_products(session, products)
    selected_source_ids = selected_source_asset_ids_for(item)
    return {
        "id": item.id,
        "calendar_date": item.calendar_date.isoformat(),
        "scheduled_time": item.scheduled_time or "09:00",
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
        "image_candidates": visible_image_candidates,
        "waiting_for_generation": item.status in QUEUE_STATUSES,
        "waiting_for_asset_download": item.status == "waiting_asset_download",
        "waiting_for_copy": item.status in {"waiting_content_generation", "waiting_copy_regeneration"},
        "waiting_for_images": item.status
        in {"waiting_content_generation", "waiting_image_generation", "waiting_image_regeneration"},
        "has_current_copy": any(
            candidate["candidate_type"] == "facebook_post" and candidate["review_state"] in {"needs_review", "approved"}
            for candidate in serialized_candidates
        ),
        "has_selected_image": any(
            candidate["review_state"] == "approved"
            for candidate in visible_image_candidates
        ),
    }


def serialize_candidate(candidate: GeneratedContentCandidateRecord) -> dict[str, object]:
    body_data = _json_dict(candidate.body)
    social_strategy = body_data.get("social_strategy") if isinstance(body_data.get("social_strategy"), dict) else {}
    selected_variant = str(social_strategy.get("selected_variant") or "").strip()
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
        "social_strategy": social_strategy,
        "copy_option_label": selected_variant or "Option",
        "source_facts": _json_dict(candidate.source_facts_json),
        "source_asset_ids": json_list(candidate.source_asset_ids_json),
        "review_state": candidate.review_state,
        "revision_notes": candidate.revision_notes,
        "reviewed_by": candidate.reviewed_by,
        "reviewed_at": candidate.reviewed_at.isoformat() if candidate.reviewed_at else None,
        "created_at": candidate.created_at.isoformat() if candidate.created_at else None,
        "updated_at": candidate.updated_at.isoformat() if candidate.updated_at else None,
    }


def _candidate_has_visible_image_asset(session: Session, candidate: dict[str, object]) -> bool:
    image_asset = candidate.get("image_asset")
    if not isinstance(image_asset, dict):
        return False
    try:
        asset_id = int(image_asset.get("asset_id") or 0)
    except (TypeError, ValueError):
        return False
    if not asset_id:
        return False
    asset = session.get(AssetRecord, asset_id)
    if asset is None:
        return False
    if asset.sync_status == "deleted" or asset.manual_override_state == "deleted":
        return False
    if asset.file_exists:
        return True
    path = Path(asset.source_path or asset.preview_path)
    if path.is_file():
        asset.file_exists = 1
        return True
    return False


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
    elif review_state == "needs_review":
        candidate.reviewed_by = ""
        candidate.reviewed_at = None
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
    parsed = _parse_copy_text(copy_text)
    if not parsed["copy_text"]:
        raise ValueError("Edited Facebook copy cannot be blank.")

    existing = _json_dict(candidate.body)
    existing.update(
        {
            "hook": parsed["hook"],
            "body": parsed["body"],
            "cta": parsed["cta"],
            "quality_score": {
                "passed": [],
                "warnings": [],
                "source": "human_edit",
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
        scheduled_time=item.scheduled_time or "09:00",
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


def default_scheduled_time_for_destination(destination: str | None) -> str:
    normalized = str(destination or "").strip().lower()
    for option, scheduled_time in PLATFORM_DEFAULT_SCHEDULED_TIMES.items():
        if option.lower() == normalized:
            return scheduled_time
    return "10:00"


def normalize_scheduled_time(value: str | None, fallback: str = "09:00") -> str:
    raw = str(value or "").strip()
    if not raw:
        return fallback
    parts = raw.split(":")
    if len(parts) != 2:
        raise ValueError("Use a valid scheduled time.")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError as exc:
        raise ValueError("Use a valid scheduled time.") from exc
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("Use a valid scheduled time.")
    return f"{hour:02d}:{minute:02d}"


def _tasks_for_planned_item(session: Session, item_id: int) -> list[TaskRecord]:
    return list(
        session.scalars(
            select(TaskRecord)
            .where(TaskRecord.planned_content_item_id == item_id)
            .order_by(TaskRecord.due_date, TaskRecord.id)
        )
    )


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


def _supersede_rewrite_requested_copy(item: PlannedContentRecord) -> None:
    for candidate in item.candidates:
        if candidate.candidate_type == "facebook_post" and candidate.review_state == "rewrite_requested":
            candidate.review_state = "rejected"
            candidate.revision_notes = "Superseded by an agent-written copy regeneration run."


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
    contracts = social_media_art_director_contracts(brief, count=IMAGE_OPTION_COUNT)
    item.production_error = _append_production_note(
        item.production_error,
        "Image generation is queued. Enable Codex image generation automation to turn "
        f"{len(contracts)} social-media-art-director requests into reviewable image files.",
    )


def _append_production_note(existing: str, note: str) -> str:
    notes = [part.strip() for part in existing.split("\n") if part.strip()] if existing else []
    if note.strip() and note.strip() not in notes:
        notes.append(note.strip())
    return "\n".join(notes)


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
    pieces = [
        str(data.get("hook") or "").strip(),
        str(data.get("body") or "").strip(),
        str(data.get("cta") or "").strip(),
    ]
    return "\n\n".join(piece for piece in pieces if piece)


def _parse_copy_text(copy_text: str) -> dict[str, str]:
    paragraphs = [part.strip() for part in copy_text.replace("\r\n", "\n").split("\n\n") if part.strip()]
    if not paragraphs:
        return {"hook": "", "body": "", "cta": "", "copy_text": ""}
    hook = paragraphs[0]
    if len(paragraphs) > 2:
        body = "\n\n".join(paragraphs[1:-1])
    else:
        body = "\n\n".join(paragraphs[1:]) if len(paragraphs) > 1 else hook
    cta = paragraphs[-1]
    return {"hook": hook, "body": body, "cta": cta, "copy_text": "\n\n".join(paragraphs)}


def _candidate_cta(value: str) -> str:
    data = _json_dict(value)
    return str(data.get("cta") or "").strip() if data else ""


def _reviewable_copy_facts(item: PlannedContentRecord) -> dict[str, object]:
    for candidate in reversed(item.candidates):
        if candidate.candidate_type != "facebook_post" or candidate.review_state not in {"needs_review", "approved"}:
            continue
        data = _json_dict(candidate.body)
        if not data:
            continue
        return {
            "candidate_id": candidate.id,
            "review_state": candidate.review_state,
            "hook": str(data.get("hook") or "").strip(),
            "body": str(data.get("body") or "").strip(),
            "cta": str(data.get("cta") or "").strip(),
            "copy_text": _candidate_copy_body(candidate.body),
            "social_strategy": data.get("social_strategy") if isinstance(data.get("social_strategy"), dict) else {},
            "social_challenge": data.get("social_challenge") if isinstance(data.get("social_challenge"), dict) else {},
        }
    return {}


def _cta_for_goals(goals: list[str]) -> str:
    normalized = " ".join(goal.lower() for goal in goals)
    if any(token in normalized for token in ["etsy", "shop", "sales", "gift", "flock", "repeat"]):
        return f"Find your favorite duck in our Etsy shop: {ETSY_SHOP_URL}"
    if any(token in normalized for token in ["followers", "follower growth", "personality"]):
        return "Follow along for more small ducks with big personality."
    if "email" in normalized:
        return "Join the email list for new releases and behind-the-scenes notes."
    if any(token in normalized for token in ["cruise", "community", "engagement"]):
        return "Tell us which duck belongs on your next cruise."
    return "Reply with which duck belongs in the flock next."


def _has_social_destination(item: PlannedContentRecord) -> bool:
    return bool(SOCIAL_DESTINATIONS.intersection(destinations_for(item)))


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


def _product_facts(session: Session, product: ProductRecord) -> dict[str, object]:
    return {
        "id": product.id,
        "name": product.name,
        "best_channels": json_list(product.best_channels_json),
        "use_cases": json_list(product.use_cases_json),
        "seasonality": json_list(product.seasonality_json),
        "sales_momentum_note": product.sales_momentum_note,
        "canonical_url": product.canonical_url,
        "sales_context": _product_sales_facts(session, product),
        "etsy_reviews": _product_review_facts(session, product),
    }


def _product_sales_facts(session: Session, product: ProductRecord) -> dict[str, object]:
    rows = list(
        session.scalars(
            select(ProductSalesRecord)
            .where(ProductSalesRecord.product_id == product.id)
            .order_by(ProductSalesRecord.sold_at.desc().nullslast(), ProductSalesRecord.id.desc())
        )
    )
    lifetime_quantity = sum(row.quantity for row in rows)
    lifetime_transactions = len(rows)
    last_sale_at = next((row.sold_at for row in rows if row.sold_at is not None), None)
    recent_cutoff = utc_now().date().toordinal() - 90
    recent_quantity = sum(
        row.quantity
        for row in rows
        if row.sold_at is not None and row.sold_at.date().toordinal() >= recent_cutoff
    )
    return {
        "source": "etsy_sales_csv",
        "lifetime_quantity": lifetime_quantity,
        "lifetime_transactions": lifetime_transactions,
        "recent_90_day_quantity": recent_quantity,
        "last_sale_at": last_sale_at.isoformat() if last_sale_at else None,
        "safe_public_claims": _safe_sales_claims(lifetime_quantity, recent_quantity),
        "usage": (
            "Sales counts are internal context. Use them to judge momentum and choose story angles. "
            "Do not publish exact unit counts, revenue, product rankings, or best-seller comparisons unless Matt explicitly approves. "
            "Prefer safe_public_claims or playful milestone language."
        ),
    }


def _safe_sales_claims(lifetime_quantity: int, recent_quantity: int) -> list[str]:
    claims: list[str] = []
    if lifetime_quantity >= 1000:
        claims.extend(["a proven flock favorite", "one of the flock's frequent flyers"])
    elif lifetime_quantity >= 250:
        claims.extend(["a steady flock favorite", "a duck that keeps finding its people"])
    elif lifetime_quantity >= 100:
        claims.append("a repeat customer pick")
    elif lifetime_quantity >= 25:
        claims.append("a duck with real order history behind it")
    if recent_quantity >= 25:
        claims.append("currently getting fresh attention")
    elif recent_quantity > 0:
        claims.append("recently ordered")
    return claims


def _product_review_facts(session: Session, product: ProductRecord, limit: int = 5) -> list[dict[str, object]]:
    reviews = session.scalars(
        select(EtsyReviewRecord)
        .where(EtsyReviewRecord.product_id == product.id)
        .order_by(EtsyReviewRecord.created_timestamp.desc().nullslast(), EtsyReviewRecord.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "rating": review.rating,
            "review": review.review,
            "language": review.language,
            "created_timestamp": review.created_timestamp,
            "has_photo": bool(review.image_url_fullxfull),
        }
        for review in reviews
        if review.review.strip()
    ]


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
        "default_reference": bool(asset.default_reference),
        "hidden_from_generation": bool(asset.hidden_from_generation),
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


def _asset_is_remote_product_image(asset: AssetRecord) -> bool:
    image_url = asset.source_path or asset.preview_path or asset.canonical_url
    return bool(
        not asset.file_exists
        and image_url.startswith(("http://", "https://", "file://"))
        and asset.asset_type in {"Etsy product photo", "external listing image"}
    )


def _asset_can_be_automation_reference(asset: AssetRecord) -> bool:
    return _asset_is_approved_source(asset) or _asset_is_remote_product_image(asset)


def _selected_source_assets(source_assets: list[AssetRecord], selected_ids: list[int]) -> list[AssetRecord]:
    if not selected_ids:
        return []
    by_id = {asset.id: asset for asset in source_assets}
    return [by_id[asset_id] for asset_id in selected_ids if asset_id in by_id and _asset_is_approved_source(by_id[asset_id])]


def _valid_selected_source_asset_ids(
    session: Session,
    products: list[ProductRecord],
    selected_ids: list[int] | None,
    assets_root: str | Path = MANAGED_PRODUCT_ASSETS_ROOT,
    defer_remote_assets: bool = False,
) -> list[int]:
    if selected_ids is None:
        return []
    if not selected_ids:
        raise ValueError("Select at least one product reference image.")
    product_ids = {product.id for product in products}
    valid_assets = list(
        session.scalars(
            select(AssetRecord)
            .where(AssetRecord.id.in_(selected_ids))
            .where(AssetRecord.product_id.in_(product_ids))
            .order_by(AssetRecord.id)
        )
    )
    valid_by_id = {asset.id: asset for asset in valid_assets}
    selected_local_ids: list[int] = []
    for asset_id in selected_ids:
        asset = valid_by_id.get(asset_id)
        if asset is None:
            continue
        if asset.hidden_from_generation:
            raise ValueError("One or more selected reference images are hidden from automation.")
        if _asset_is_approved_source(asset):
            selected_local_ids.append(asset.id)
        elif _asset_is_remote_product_image(asset):
            if defer_remote_assets:
                selected_local_ids.append(asset.id)
            else:
                selected_local_ids.append(ensure_local_asset_for_remote_image(session, asset, assets_root).id)
    if not selected_local_ids:
        raise ValueError("Select at least one approved local or remote product reference image.")
    return selected_local_ids


def _has_remote_selected_source_asset(session: Session, selected_ids: list[int]) -> bool:
    for asset_id in selected_ids:
        asset = session.get(AssetRecord, asset_id)
        if asset is not None and _asset_is_remote_product_image(asset):
            return True
    return False


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
