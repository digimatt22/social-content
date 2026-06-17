from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .context import load_business_context
from .db_models import (
    AssetRecord,
    CalendarItemRecord,
    MetricRecord,
    PlanRecord,
    ProductRecord,
    SyncMetadata,
    TaskRecord,
    TemplateRecord,
    utc_now,
)
from .models import Phase2CalendarItem, Phase2MarketingPlan, ProductEntity, WeeklyAction
from .phase2 import build_phase2_plan


PLATFORM_TEMPLATE_DIR = Path("docs/templates/platform")
COPY_TEMPLATE_DIR = Path("docs/templates/copy")
GRAPHIC_TEMPLATE_DIR = Path("docs/templates/graphics")

TASK_STATUSES = [
    "needs asset",
    "needs copy review",
    "ready to post",
    "scheduled",
    "posted",
    "metrics needed",
    "complete",
    "skipped",
    "blocked",
]

ROLE_OPTIONS = ["Matt", "social operator", "either", "blocked until owner input"]

PLAYBOOKS: dict[tuple[str, str], dict[str, Any]] = {
    ("Instagram", "reel"): {
        "explanation": "A short vertical video for discovery, launches, and process moments.",
        "device": "phone",
        "media": "Vertical video or 3-5 quick clips.",
        "steps": [
            "Open Instagram on the phone.",
            "Tap create, choose Reel, and select the prepared clips.",
            "Keep the duck visible in the first second.",
            "Paste the caption, CTA, and hashtags.",
            "Preview once with sound off before posting or scheduling.",
        ],
        "checklist": [
            "Duck is visible immediately.",
            "Caption includes the CTA.",
            "Hashtags are present.",
            "No text covers the product.",
        ],
        "mistakes": "Do not start with a blank printer bed or long setup. Do not cover the duck with text.",
        "metric": "Check views, likes, comments, follows, shares, saves, and any Etsy click/sales note later.",
    },
    ("Instagram", "post"): {
        "explanation": "A feed post is a product photo plus caption for followers and profile visitors.",
        "device": "phone",
        "media": "Square or portrait product image.",
        "steps": [
            "Open Instagram on the phone.",
            "Tap create, choose Post, and select the product image.",
            "Crop so the duck is clear and not clipped.",
            "Paste the caption, CTA, and hashtags.",
            "Review the preview and post or schedule.",
        ],
        "checklist": [
            "Duck is sharp and centered.",
            "Caption sounds like MattMadeMe.",
            "CTA is easy to find.",
            "No typo in product name.",
        ],
        "mistakes": "Do not use a tiny product crop or bury the CTA.",
        "metric": "Check likes, comments, saves, profile follows, and Etsy sales notes later.",
    },
    ("Instagram", "carousel"): {
        "explanation": "A carousel is several swipeable images for gift guides, detail shots, or mini stories.",
        "device": "phone",
        "media": "3-6 coordinated images.",
        "steps": [
            "Open Instagram and choose Post.",
            "Tap multiple select and choose slides in the planned order.",
            "Put the strongest duck image first.",
            "Paste the caption and hashtags.",
            "Preview each slide before posting.",
        ],
        "checklist": [
            "First slide works alone.",
            "Slide order makes sense.",
            "CTA appears in caption.",
            "No important detail is cropped.",
        ],
        "mistakes": "Do not mix unrelated products without a clear reason.",
        "metric": "Check likes, comments, saves, shares, and collector replies later.",
    },
    ("Facebook", "post"): {
        "explanation": "A Page post is a conversational product update that can invite comments.",
        "device": "either",
        "media": "Clear product image.",
        "steps": [
            "Open the MattMadeMe Facebook Page.",
            "Create a post and add the prepared product image.",
            "Paste the caption and CTA.",
            "Make sure the question is easy to answer.",
            "Preview and publish or schedule.",
        ],
        "checklist": [
            "Image looks clear at small size.",
            "Question invites comments.",
            "CTA is natural.",
            "No hashtags overload the post.",
        ],
        "mistakes": "Do not make the post feel like only an ad; ask a real question.",
        "metric": "Check reach, reactions, comments, shares, and any Etsy sales note later.",
    },
    ("Etsy", "promotion"): {
        "explanation": "An Etsy task improves or promotes a listing; it is not an automated publish step.",
        "device": "desktop",
        "media": "Best available listing photo.",
        "steps": [
            "Open Etsy shop manager.",
            "Find the featured product listing.",
            "Review the first photo, first paragraph, title, and tags.",
            "Apply only the planned improvement.",
            "Write a note about what changed.",
        ],
        "checklist": [
            "Listing still matches the product accurately.",
            "Buyer use case is clear.",
            "No proven listing structure was changed without a note.",
            "Metric note is ready for later review.",
        ],
        "mistakes": "Do not change multiple listing variables at once if you want to know what helped.",
        "metric": "Track Etsy visits, favorites, orders, and listing notes later.",
    },
    ("Website", "blog topic"): {
        "explanation": "A website/blog task creates reusable content for search, social links, and launch stories.",
        "device": "desktop",
        "media": "Product image plus optional process image.",
        "steps": [
            "Open the website editor.",
            "Create a short draft using the planned topic.",
            "Add product photo and Etsy/shop link.",
            "Preview on desktop and phone width if possible.",
            "Save draft for Matt review or publish if approved.",
        ],
        "checklist": [
            "Product story is clear.",
            "Shop link works.",
            "Post can be reused from social.",
            "No placeholder text remains.",
        ],
        "mistakes": "Do not write a long essay when a clear short product story is enough.",
        "metric": "Track published URL, traffic notes, Etsy clicks, and follow-up content ideas later.",
    },
}

DEFAULT_PLAYBOOK = {
    "explanation": "A planned marketing task with plain steps for the assigned owner.",
    "device": "either",
    "media": "Use the asset listed on the task.",
    "steps": ["Review the draft.", "Prepare the listed asset.", "Post or complete the action.", "Record a note."],
    "checklist": ["Product is clear.", "CTA is included.", "Metric can be checked later."],
    "mistakes": "Do not post if the product, asset, or CTA looks wrong.",
    "metric": "Record the result and any useful notes later.",
}


def seed_database(session: Session, business_dir: str = "docs/business") -> None:
    context = load_business_context(business_dir)
    for product in context.product_entities:
        upsert_product(session, product)
    session.flush()
    seed_templates(session)
    seed_assets(session)
    _upsert_sync(session, "business_context", business_dir, f"{len(context.product_entities)} products loaded")


def ensure_default_plan(session: Session, business_dir: str = "docs/business", start_date: date | None = None) -> PlanRecord:
    plan = session.scalars(select(PlanRecord).order_by(PlanRecord.generated_at.desc())).first()
    if plan:
        return plan
    phase2_plan = build_phase2_plan(business_dir, start_date=start_date or date.today(), mode="standard")
    return persist_phase2_plan(session, phase2_plan, start_date or date.today())


def generate_and_persist_plan(
    session: Session,
    business_dir: str = "docs/business",
    mode: str = "standard",
    start_date: date | None = None,
) -> PlanRecord:
    start = start_date or date.today()
    phase2_plan = build_phase2_plan(business_dir, start_date=start, mode=mode)
    return persist_phase2_plan(session, phase2_plan, start)


def persist_phase2_plan(session: Session, phase2_plan: Phase2MarketingPlan, start_date: date) -> PlanRecord:
    record = PlanRecord(
        mode=phase2_plan.mode,
        start_date=start_date,
        weekly_theme=phase2_plan.weekly_theme,
        campaign_narrative=phase2_plan.campaign_narrative,
        validation_report_json=json.dumps([asdict(issue) for issue in phase2_plan.validation_report.issues]),
    )
    session.add(record)
    session.flush()

    calendar_lookup: dict[str, CalendarItemRecord] = {}
    for item in phase2_plan.calendar:
        calendar_record = calendar_item_from_phase2(record.id, item)
        session.add(calendar_record)
        session.flush()
        calendar_lookup[item.title] = calendar_record
        session.add(task_from_calendar_item(session, record.id, calendar_record))

    for action in phase2_plan.weekly_actions:
        if action.section == "blocked":
            session.add(task_from_weekly_action(record.id, action, start_date))
    session.flush()
    return record


def upsert_product(session: Session, product: ProductEntity) -> ProductRecord:
    existing = session.scalar(select(ProductRecord).where(ProductRecord.name == product.name))
    payload = {
        "status": product.status,
        "primary_audience": product.primary_audience,
        "secondary_audiences_json": json.dumps(product.secondary_audiences),
        "best_channels_json": json.dumps(product.best_channels),
        "use_cases_json": json.dumps(product.use_cases),
        "seasonality_json": json.dumps(product.seasonality),
        "sales_momentum_note": product.sales_momentum_note,
        "launch_priority": product.launch_priority,
    }
    if existing:
        for key, value in payload.items():
            setattr(existing, key, value)
        return existing
    record = ProductRecord(name=product.name, **payload)
    session.add(record)
    return record


def seed_templates(session: Session) -> None:
    for template_type, directory in (
        ("platform", PLATFORM_TEMPLATE_DIR),
        ("copy", COPY_TEMPLATE_DIR),
        ("graphic", GRAPHIC_TEMPLATE_DIR),
    ):
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            name = data.get("name") or path.stem.replace("-", " ").title()
            existing = session.scalar(
                select(TemplateRecord).where(
                    TemplateRecord.template_type == template_type,
                    TemplateRecord.name == name,
                )
            )
            payload = {
                "platform": data.get("platform", ""),
                "format": data.get("format", ""),
                "source_path": str(path),
                "body_json": json.dumps(data, indent=2),
            }
            if existing:
                for key, value in payload.items():
                    setattr(existing, key, value)
            else:
                session.add(TemplateRecord(template_type=template_type, name=name, **payload))


def seed_assets(session: Session) -> None:
    products = session.scalars(select(ProductRecord)).all()
    for product in products:
        existing = session.scalar(select(AssetRecord).where(AssetRecord.product_id == product.id, AssetRecord.asset_type == "Etsy product photo"))
        if existing:
            continue
        slug = slugify(product.name)
        session.add(
            AssetRecord(
                product_id=product.id,
                name=f"{product.name} Etsy photo",
                asset_type="Etsy product photo",
                source_path=f"assets/products/{slug}/source/etsy-photo.jpg",
                preview_path=f"assets/products/{slug}/preview.jpg",
                platform_suitability_json=json.dumps(["Instagram", "Facebook", "Etsy", "Website"]),
                readiness_state="existing Etsy photo ready",
                notes="Placeholder inventory record for existing Etsy product photography. Replace path when local assets are organized.",
            )
        )


def calendar_item_from_phase2(plan_id: int, item: Phase2CalendarItem) -> CalendarItemRecord:
    return CalendarItemRecord(
        plan_id=plan_id,
        date=item.date,
        title=item.title,
        platform=item.platform,
        content_type=item.content_type,
        business_goal=item.business_goal,
        objective=item.objective,
        target_audience=item.target_audience,
        featured_product=item.featured_product,
        draft_copy=item.draft_copy,
        cta=item.cta,
        hashtags_json=json.dumps(item.hashtags),
        asset_brief=item.asset_brief,
        asset_type=item.asset_type,
        production_notes=item.production_notes,
        priority=item.priority,
        effort_estimate=item.effort_estimate,
        expected_impact=item.expected_impact,
        success_metric=item.success_metric,
    )


def task_from_calendar_item(session: Session, plan_id: int, item: CalendarItemRecord) -> TaskRecord:
    playbook = playbook_for(item.platform, item.content_type)
    asset = _best_asset(session, item.featured_product)
    return TaskRecord(
        plan_id=plan_id,
        calendar_item_id=item.id,
        due_date=item.date,
        title=item.title,
        owner_role=owner_for(item.platform, item.content_type),
        platform=item.platform,
        content_type=item.content_type,
        product_name=item.featured_product,
        asset_id=asset.id if asset else None,
        draft_caption=item.draft_copy,
        cta=item.cta,
        hashtags_json=item.hashtags_json,
        posting_steps_json=json.dumps(playbook["steps"]),
        preview_checklist_json=json.dumps(playbook["checklist"]),
        metric_instruction=item.success_metric or playbook["metric"],
        status="ready to post" if asset else "needs asset",
        notes="",
    )


def task_from_weekly_action(plan_id: int, action: WeeklyAction, start_date: date) -> TaskRecord:
    return TaskRecord(
        plan_id=plan_id,
        due_date=start_date,
        title=action.owner_task,
        owner_role="blocked until owner input",
        platform="Admin",
        content_type="owner input",
        product_name="",
        draft_caption=action.needed_asset_or_input,
        cta="Resolve owner input before this can move forward.",
        hashtags_json="[]",
        posting_steps_json=json.dumps(["Ask Matt for the missing decision or account detail.", "Record the answer in task notes."]),
        preview_checklist_json=json.dumps(["Owner input is documented.", "Task can be reassigned or completed."]),
        metric_instruction="Track whether the blocker was resolved this week.",
        status="blocked",
        notes=action.related_item,
    )


def add_metric(
    session: Session,
    task_id: int,
    post_url: str = "",
    reach: int | None = None,
    likes: int | None = None,
    comments: int | None = None,
    shares: int | None = None,
    saves: int | None = None,
    etsy_visits: int | None = None,
    etsy_orders: int | None = None,
    email_signups: int | None = None,
    notes: str = "",
) -> MetricRecord:
    metric = MetricRecord(
        task_id=task_id,
        post_url=post_url,
        reach=reach,
        likes=likes,
        comments=comments,
        shares=shares,
        saves=saves,
        etsy_visits=etsy_visits,
        etsy_orders=etsy_orders,
        email_signups=email_signups,
        notes=notes,
    )
    session.add(metric)
    task = session.get(TaskRecord, task_id)
    if task and task.status == "posted":
        task.status = "metrics needed"
    return metric


def update_task_status(session: Session, task_id: int, status: str, notes: str = "") -> TaskRecord:
    if status not in TASK_STATUSES:
        raise ValueError(f"Unsupported task status: {status}")
    task = session.get(TaskRecord, task_id)
    if task is None:
        raise ValueError(f"Task not found: {task_id}")
    task.status = status
    task.notes = notes
    return task


def playbook_for(platform: str, content_type: str) -> dict[str, Any]:
    if platform == "Instagram" and content_type == "reel":
        return PLAYBOOKS[("Instagram", "reel")]
    if platform == "Instagram" and content_type == "carousel":
        return PLAYBOOKS[("Instagram", "carousel")]
    if platform == "Instagram":
        return PLAYBOOKS[("Instagram", "post")]
    if platform == "Facebook":
        return PLAYBOOKS[("Facebook", "post")]
    if platform == "Etsy":
        return PLAYBOOKS[("Etsy", "promotion")]
    if platform == "Website":
        return PLAYBOOKS[("Website", "blog topic")]
    return DEFAULT_PLAYBOOK


def owner_for(platform: str, content_type: str) -> str:
    if platform in {"Instagram", "Facebook"}:
        return "social operator"
    if platform in {"Etsy", "Website"}:
        return "Matt"
    if content_type == "owner input":
        return "blocked until owner input"
    return "either"


def status_counts(tasks: list[TaskRecord]) -> dict[str, int]:
    counts = {status: 0 for status in TASK_STATUSES}
    for task in tasks:
        counts[task.status] = counts.get(task.status, 0) + 1
    return counts


def json_list(value: str) -> list[str]:
    try:
        data = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return [str(item) for item in data] if isinstance(data, list) else []


def template_body(template: TemplateRecord) -> dict[str, Any]:
    try:
        return json.loads(template.body_json)
    except json.JSONDecodeError:
        return {}


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "asset"


def _best_asset(session: Session, product_name: str) -> AssetRecord | None:
    product = session.scalar(select(ProductRecord).where(ProductRecord.name == product_name))
    if not product:
        return None
    return session.scalar(select(AssetRecord).where(AssetRecord.product_id == product.id).order_by(AssetRecord.id))


def _upsert_sync(session: Session, name: str, path: str, notes: str) -> None:
    existing = session.scalar(select(SyncMetadata).where(SyncMetadata.source_name == name))
    if existing:
        existing.source_path = path
        existing.notes = notes
        existing.synced_at = utc_now()
    else:
        session.add(SyncMetadata(source_name=name, source_path=path, notes=notes))
