from __future__ import annotations

import csv
import hashlib
import json
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from shutil import copy2

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db_models import (
    AssetRecord,
    BlogPostRecord,
    CalendarItemRecord,
    GeneratedContentCandidateRecord,
    MetricRecord,
    PlanRecord,
    PlannedContentRecord,
    ProductRecord,
    SyncMetadata,
    TaskRecord,
    TemplateRecord,
    utc_now,
)
from .phase3 import ROLE_OPTIONS, TASK_STATUSES, json_list, slugify, update_task_status


OPERATOR_DEFAULT_ROLE = "social operator"
OPEN_STATUSES = {"needs asset", "needs copy review", "ready to post", "scheduled", "posted", "metrics needed", "blocked"}
FINISHED_STATUSES = {"complete", "skipped"}
METRIC_RELEVANT_STATUS = {"posted", "metrics needed"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


@dataclass(frozen=True)
class TaskView:
    task: TaskRecord
    action_title: str
    status_label: str
    status_tone: str
    is_blocked: bool
    asset_ready: bool
    metric_due: bool
    metric_followup_reason: str
    metric_followup_label: str


@dataclass(frozen=True)
class TodayView:
    role: str
    recommended: TaskView | None
    remaining: list[TaskView]
    upcoming: list[TaskView]
    attention_count: int


@dataclass(frozen=True)
class DayAgenda:
    day: date
    tasks: list[TaskView]


@dataclass(frozen=True)
class DataHealthItem:
    area: str
    status: str
    count: int
    message: str
    action: str


@dataclass(frozen=True)
class PlatformGuide:
    name: str
    platform: str
    format: str
    difficulty: str
    dimensions: str
    media_count: str
    caption_structure: str
    cta_placement: str
    asset_requirements: str
    text_overlay_rules: str
    example_layout: str
    reuse_notes: str


@dataclass(frozen=True)
class CreativeFormatPlan:
    template_name: str
    dimensions: str
    output_path: str
    prompt: str


@dataclass(frozen=True)
class CreativeAssetPlan:
    source_asset: AssetRecord
    source_ready: bool
    readiness_message: str
    formats: list[CreativeFormatPlan]


@dataclass(frozen=True)
class CreativeGenerationRun:
    manifest_path: Path
    candidates: list[AssetRecord]


@dataclass(frozen=True)
class AssetView:
    asset: AssetRecord
    used_by: list[TaskView]


@dataclass(frozen=True)
class AssetOption:
    asset: AssetRecord
    label: str


JsonDict = dict[str, object]


def task_view(task: TaskRecord, today: date | None = None) -> TaskView:
    today = today or date.today()
    asset_ready = bool(task.asset and task.asset.file_exists and task.asset.review_state in {"approved", "unreviewed"})
    metric_due = is_metric_due(task, today)
    return TaskView(
        task=task,
        action_title=action_title(task),
        status_label=plain_status(task.status),
        status_tone=status_tone(task.status),
        is_blocked=task.status == "blocked" or task.owner_role == "blocked until owner input",
        asset_ready=asset_ready,
        metric_due=metric_due,
        metric_followup_reason=metric_followup_reason(task, today),
        metric_followup_label=metric_followup_label(task, today),
    )


def today_view(session: Session, role: str = OPERATOR_DEFAULT_ROLE, today: date | None = None) -> TodayView:
    today = today or date.today()
    normalized_role = role if role in ROLE_OPTIONS or role == "all" else OPERATOR_DEFAULT_ROLE
    week_end = today + timedelta(days=6)

    query = select(TaskRecord).where(TaskRecord.due_date <= week_end).order_by(TaskRecord.due_date, TaskRecord.id)
    if normalized_role != "all":
        query = query.where(TaskRecord.owner_role == normalized_role)
    tasks = list(session.scalars(query))
    open_due = [task for task in tasks if task.due_date <= today and task.status not in FINISHED_STATUSES]
    upcoming = [task for task in tasks if task.due_date > today and task.status not in FINISHED_STATUSES]

    sorted_due = sorted(open_due, key=_task_priority_key)
    views = [task_view(task, today) for task in sorted_due]
    return TodayView(
        role=normalized_role,
        recommended=views[0] if views else None,
        remaining=views[1:],
        upcoming=[task_view(task, today) for task in upcoming[:5]],
        attention_count=len(open_due),
    )


def serialize_today_view(model: TodayView) -> JsonDict:
    return {
        "role": model.role,
        "attention_count": model.attention_count,
        "recommended": serialize_task_view(model.recommended) if model.recommended else None,
        "remaining": [serialize_task_view(task) for task in model.remaining],
        "upcoming": [serialize_task_view(task) for task in model.upcoming],
    }


def serialize_task_view(model: TaskView) -> JsonDict:
    task = model.task
    return {
        "id": task.id,
        "action_title": model.action_title,
        "title": task.title,
        "due_date": task.due_date.isoformat(),
        "owner_role": task.owner_role,
        "platform": task.platform,
        "content_type": task.content_type,
        "product_name": task.product_name,
        "status": task.status,
        "status_label": model.status_label,
        "status_tone": model.status_tone,
        "is_blocked": model.is_blocked,
        "asset_ready": model.asset_ready,
        "asset_id": task.asset_id,
        "metric_due": model.metric_due,
        "metric_followup_reason": model.metric_followup_reason,
        "metric_followup_label": model.metric_followup_label,
        "metric_due_date": task.metric_due_date.isoformat() if task.metric_due_date else None,
        "metric_status": task.metric_status,
        "published_url": task.published_url,
        "sync_status": task.sync_status,
        "sync_error": task.sync_error,
        "manual_override_state": task.manual_override_state,
        "manual_override_note": task.manual_override_note,
    }


def serialize_task_detail(
    model: TaskView,
    asset_options: list[AssetOption],
    metric_fields: list[tuple[str, str]],
    show_metrics: bool,
    playbook: dict[str, object] | None = None,
) -> JsonDict:
    task = model.task
    playbook = playbook or {}
    return {
        **serialize_task_view(model),
        "draft_caption": task.draft_caption,
        "cta": task.cta,
        "hashtags": json_list(task.hashtags_json),
        "posting_steps": json_list(task.posting_steps_json),
        "preview_checklist": json_list(task.preview_checklist_json),
        "post_guidance": {
            "explanation": str(playbook.get("explanation") or ""),
            "device": str(playbook.get("device") or ""),
            "media": str(playbook.get("media") or ""),
            "common_mistake": str(playbook.get("mistakes") or ""),
        },
        "metric_instruction": task.metric_instruction,
        "show_metrics": show_metrics,
        "metric_fields": [{"name": name, "label": label} for name, label in metric_fields],
        "asset_options": [serialize_asset_option(option) for option in asset_options],
    }


def serialize_asset_option(option: AssetOption) -> JsonDict:
    return {
        "asset_id": option.asset.id,
        "label": option.label,
        "name": option.asset.name,
        "asset_type": option.asset.asset_type,
        "review_state": option.asset.review_state,
    }


def serialize_week_agenda(agendas: list[DayAgenda]) -> list[JsonDict]:
    return [
        {
            "day": agenda.day.isoformat(),
            "tasks": [serialize_task_view(task) for task in agenda.tasks],
        }
        for agenda in agendas
    ]


def serialize_asset_view(model: AssetView) -> JsonDict:
    asset = model.asset
    return {
        "id": asset.id,
        "name": asset.name,
        "product": asset.product.name if asset.product else "",
        "asset_type": asset.asset_type,
        "source_path": asset.source_path,
        "preview_path": asset.preview_path,
        "readiness_state": asset.readiness_state,
        "review_state": asset.review_state,
        "file_exists": bool(asset.file_exists),
        "file_checked_at": asset.file_checked_at.isoformat() if asset.file_checked_at else None,
        "file_checksum": asset.file_checksum,
        "external_source": asset.external_source,
        "external_id": asset.external_id,
        "sync_status": asset.sync_status,
        "sync_error": asset.sync_error,
        "staleness_state": asset.staleness_state,
        "manual_override_state": asset.manual_override_state,
        "manual_override_note": asset.manual_override_note,
        "source_asset_id": asset.source_asset_id,
        "used_by": [serialize_task_view(task) for task in model.used_by],
    }


def serialize_data_health_item(item: DataHealthItem) -> JsonDict:
    return {
        "area": item.area,
        "status": item.status,
        "count": item.count,
        "message": item.message,
        "action": item.action,
    }


def serialize_creative_asset_plan(plan: CreativeAssetPlan) -> JsonDict:
    return {
        "source_asset": serialize_asset_view(AssetView(plan.source_asset, [])),
        "source_ready": plan.source_ready,
        "readiness_message": plan.readiness_message,
        "formats": [
            {
                "template_name": item.template_name,
                "dimensions": item.dimensions,
                "output_path": item.output_path,
                "prompt": item.prompt,
            }
            for item in plan.formats
        ],
    }


def week_agenda(
    session: Session,
    role: str = OPERATOR_DEFAULT_ROLE,
    today: date | None = None,
    status: str = "open",
    platform: str = "all",
) -> list[DayAgenda]:
    today = today or date.today()
    week_end = today + timedelta(days=6)
    normalized_role = role if role in ROLE_OPTIONS or role == "all" else OPERATOR_DEFAULT_ROLE
    query = select(TaskRecord).where(TaskRecord.due_date >= today, TaskRecord.due_date <= week_end).order_by(TaskRecord.due_date, TaskRecord.id)
    if normalized_role != "all":
        query = query.where(TaskRecord.owner_role == normalized_role)
    if platform != "all":
        query = query.where(TaskRecord.platform == platform)

    tasks = list(session.scalars(query))
    if status == "open":
        tasks = [task for task in tasks if task.status not in FINISHED_STATUSES]
    elif status != "all":
        tasks = [task for task in tasks if task.status == status]

    grouped: dict[date, list[TaskView]] = defaultdict(list)
    for task in tasks:
        grouped[task.due_date].append(task_view(task, today))
    return [DayAgenda(day=day, tasks=grouped[day]) for day in sorted(grouped)]


def completed_tasks(session: Session, role: str = OPERATOR_DEFAULT_ROLE, limit: int = 60) -> list[TaskView]:
    normalized_role = role if role in ROLE_OPTIONS or role == "all" else OPERATOR_DEFAULT_ROLE
    query = select(TaskRecord).where(TaskRecord.status.in_(FINISHED_STATUSES)).order_by(TaskRecord.updated_at.desc(), TaskRecord.id.desc())
    if normalized_role != "all":
        query = query.where(TaskRecord.owner_role == normalized_role)
    return [task_view(task) for task in list(session.scalars(query).all())[:limit]]


def posting_guides(session: Session) -> list[PlatformGuide]:
    templates = list(
        session.scalars(
            select(TemplateRecord)
            .where(TemplateRecord.template_type == "platform")
            .order_by(TemplateRecord.platform, TemplateRecord.name)
        )
    )
    guides: list[PlatformGuide] = []
    for template in templates:
        body = _json_dict(template.body_json)
        guides.append(
            PlatformGuide(
                name=str(body.get("name") or template.name),
                platform=str(body.get("platform") or template.platform),
                format=str(body.get("format") or template.format),
                difficulty=str(body.get("difficulty_level") or "medium"),
                dimensions=str(body.get("recommended_dimensions") or ""),
                media_count=str(body.get("media_count") or ""),
                caption_structure=str(body.get("caption_structure") or ""),
                cta_placement=str(body.get("cta_placement") or ""),
                asset_requirements=str(body.get("asset_requirements") or ""),
                text_overlay_rules=str(body.get("text_overlay_rules") or ""),
                example_layout=str(body.get("example_layout") or ""),
                reuse_notes=str(body.get("reuse_notes") or ""),
            )
        )
    return guides


def creative_asset_plans(session: Session, output_root: str | Path = "outputs/graphics") -> list[CreativeAssetPlan]:
    refresh_asset_file_state(session)
    templates = list(
        session.scalars(
            select(TemplateRecord)
            .where(TemplateRecord.template_type == "graphic")
            .order_by(TemplateRecord.name)
        )
    )
    source_assets = list(
        session.scalars(
            select(AssetRecord)
            .where(AssetRecord.asset_type.in_(["source photo", "Etsy product photo", "edited photo", "external listing image"]))
            .order_by(AssetRecord.name)
        )
    )
    plans: list[CreativeAssetPlan] = []
    for asset in source_assets:
        ready = bool(asset.file_exists and asset.review_state == "approved")
        formats = [_creative_format_plan(asset, template, output_root) for template in templates]
        plans.append(
            CreativeAssetPlan(
                source_asset=asset,
                source_ready=ready,
                readiness_message=_creative_readiness_message(asset),
                formats=formats,
            )
        )
    return plans


def register_creative_outputs_for_source(
    session: Session,
    source_asset_id: int,
    selected_templates: list[str] | None = None,
    output_root: str | Path = "outputs/graphics",
) -> list[AssetRecord]:
    refresh_asset_file_state(session)
    source = session.get(AssetRecord, source_asset_id)
    if source is None:
        raise ValueError(f"Source asset not found: {source_asset_id}")
    if not source.file_exists:
        raise ValueError("Source asset file is missing.")
    if source.review_state != "approved":
        raise ValueError("Source asset must be approved before generated outputs can be registered.")

    templates_query = select(TemplateRecord).where(TemplateRecord.template_type == "graphic").order_by(TemplateRecord.name)
    templates = list(session.scalars(templates_query))
    selected = set(selected_templates or [])
    if selected:
        templates = [template for template in templates if template.name in selected]
    records: list[AssetRecord] = []
    for template in templates:
        plan = _creative_format_plan(source, template, output_root)
        existing = session.scalar(select(AssetRecord).where(AssetRecord.source_path == plan.output_path))
        if existing:
            records.append(existing)
            continue
        records.append(
            register_generated_asset_candidate(
                session,
                source,
                plan.output_path,
                plan.template_name,
                plan.prompt,
                notes="Registered as a generated-output candidate. Create or place the image at the output path, then review it.",
            )
        )
    return records


def prepare_creative_generation_run(
    session: Session,
    source_asset_id: int,
    selected_templates: list[str] | None = None,
    output_root: str | Path = "outputs/graphics",
    manifest_dir: str | Path = "outputs/graphics/manifests",
) -> CreativeGenerationRun:
    """Register candidates and write a manifest for the image-generation pass."""
    candidates = register_creative_outputs_for_source(session, source_asset_id, selected_templates, output_root)
    source = session.get(AssetRecord, source_asset_id)
    if source is None:
        raise ValueError(f"Source asset not found: {source_asset_id}")

    slug = slugify(source.product.name if source.product else source.name)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    manifest_path = Path(manifest_dir) / f"{slug}-{stamp}.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source_asset": {
            "id": source.id,
            "name": source.name,
            "product": source.product.name if source.product else "",
            "source_path": source.source_path,
            "preview_path": source.preview_path,
            "review_state": source.review_state,
        },
        "guardrails": [
            "Preserve product shape, color, printed details, and proportions.",
            "Do not add misleading product details.",
            "Do not imply licensed characters or protected brands.",
            "Do not obscure the product.",
            "Do not use generated text inside images unless it can be verified.",
            "Mark outputs as needing human review until Matt approves them.",
        ],
        "outputs": [
            {
                "asset_id": candidate.id,
                "template_name": _template_name_from_candidate(candidate),
                "output_path": candidate.source_path,
                "prompt": candidate.generated_prompt,
                "review_state": candidate.review_state,
            }
            for candidate in candidates
        ],
    }
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return CreativeGenerationRun(manifest_path=manifest_path, candidates=candidates)


def import_external_product_image(
    session: Session,
    image_url: str,
    product_id: int | None = None,
    name: str = "",
    notes: str = "",
    assets_root: str | Path = "assets/products",
    external_source: str = "mattmademe_website",
) -> AssetRecord:
    product = session.get(ProductRecord, product_id) if product_id else None
    parsed = urllib.parse.urlparse(image_url)
    source_name = Path(parsed.path).name or "external-product-image.jpg"
    suffix = Path(source_name).suffix.lower() or ".jpg"
    if suffix not in IMAGE_EXTENSIONS:
        raise ValueError(f"Unsupported image file type: {suffix}")
    product_slug = slugify(product.name) if product else "external"
    target_dir = Path(assets_root) / product_slug / "source"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = _unique_path(target_dir / source_name)
    with urllib.request.urlopen(image_url, timeout=30) as response:
        target.write_bytes(response.read())

    asset = register_local_source_photo(
        session,
        target,
        product_id=product_id,
        name=name or _asset_name(target, product),
        notes=notes or f"Imported from {image_url}.",
    )
    asset.asset_type = "external listing image"
    asset.external_source = external_source
    asset.external_id = source_name
    asset.canonical_url = image_url
    asset.sync_status = "imported"
    asset.staleness_state = "fresh"
    asset.last_synced_at = utc_now()
    return asset


def generate_creative_output_files_for_source(
    session: Session,
    source_asset_id: int,
    selected_templates: list[str] | None = None,
    output_root: str | Path = "outputs/graphics",
    manifest_dir: str | Path = "outputs/graphics/manifests",
) -> CreativeGenerationRun:
    run = prepare_creative_generation_run(session, source_asset_id, selected_templates, output_root, manifest_dir)
    source = session.get(AssetRecord, source_asset_id)
    if source is None:
        raise ValueError(f"Source asset not found: {source_asset_id}")
    source_path = asset_path(source)
    for candidate in run.candidates:
        dimensions = _dimensions_for_candidate(session, candidate)
        _render_generated_candidate(source_path, Path(candidate.source_path), source.product.name if source.product else source.name, dimensions)
        candidate.file_exists = 1
        candidate.file_checked_at = utc_now()
        candidate.file_modified_at = datetime.fromtimestamp(Path(candidate.source_path).stat().st_mtime)
        candidate.file_checksum = _file_checksum(Path(candidate.source_path))
    return run


def asset_inventory(session: Session) -> list[AssetView]:
    refresh_asset_file_state(session)
    assets = list(session.scalars(select(AssetRecord).order_by(AssetRecord.name)))
    tasks_by_asset: dict[int, list[TaskView]] = defaultdict(list)
    tasks = list(session.scalars(select(TaskRecord).where(TaskRecord.asset_id.is_not(None)).order_by(TaskRecord.due_date, TaskRecord.id)))
    for task in tasks:
        if task.asset_id is not None:
            tasks_by_asset[task.asset_id].append(task_view(task))
    return [AssetView(asset=asset, used_by=tasks_by_asset.get(asset.id, [])) for asset in assets]


def task_asset_options(session: Session, task: TaskRecord) -> list[AssetOption]:
    refresh_asset_file_state(session)
    product = session.scalar(select(ProductRecord).where(ProductRecord.name == task.product_name)) if task.product_name else None
    assets = list(
        session.scalars(
            select(AssetRecord)
            .where(AssetRecord.file_exists == 1, AssetRecord.review_state == "approved")
            .order_by(AssetRecord.name)
        )
    )
    options: list[AssetOption] = []
    for asset in assets:
        if product and asset.product_id not in {product.id, None}:
            continue
        label_bits = [asset.name, asset.asset_type, asset.readiness_state]
        if asset.product:
            label_bits.insert(1, asset.product.name)
        options.append(AssetOption(asset=asset, label=" · ".join(bit for bit in label_bits if bit)))
    return options


def assign_asset_to_task(session: Session, task_id: int, asset_id: int) -> TaskRecord:
    task = session.get(TaskRecord, task_id)
    if task is None:
        raise ValueError(f"Task not found: {task_id}")
    asset = session.get(AssetRecord, asset_id)
    if asset is None:
        raise ValueError(f"Asset not found: {asset_id}")
    refresh_asset_file_state(session)
    if not asset.file_exists:
        raise ValueError("Asset file is missing.")
    if asset.review_state != "approved":
        raise ValueError("Asset must be approved before it can be assigned to a task.")
    task.asset_id = asset.id
    if task.status == "needs asset":
        task.status = "ready to post"
    return task


def metrics_due_tasks(session: Session, today: date | None = None) -> list[TaskView]:
    today = today or date.today()
    tasks = list(
        session.scalars(
            select(TaskRecord)
            .where(TaskRecord.status.in_(METRIC_RELEVANT_STATUS))
            .order_by(TaskRecord.metric_due_date, TaskRecord.due_date, TaskRecord.id)
        )
    )
    return [task_view(task, today) for task in tasks if task.metric_status != "complete" and is_metric_due(task, today)]


def is_metric_due(task: TaskRecord, today: date) -> bool:
    if task.status not in METRIC_RELEVANT_STATUS:
        return False
    if task.metric_status in {"complete", "not needed"}:
        return False
    return task.metric_due_date is None or task.metric_due_date <= today


def metric_followup_reason(task: TaskRecord, today: date | None = None) -> str:
    today = today or date.today()
    if not is_metric_due(task, today):
        return "not_due"
    if not task.published_url:
        return "missing_post_url"
    return "missing_metrics"


def metric_followup_label(task: TaskRecord, today: date | None = None) -> str:
    labels = {
        "missing_post_url": "Post URL needed",
        "missing_metrics": "Metrics needed",
        "not_due": "Not due",
    }
    return labels[metric_followup_reason(task, today)]


def platform_metric_fields(platform: str) -> list[tuple[str, str]]:
    fields = [("post_url", "Post URL")]
    if platform in {"Instagram", "Facebook"}:
        fields.extend(
            [
                ("reach", "Reach / Views"),
                ("likes", "Likes"),
                ("comments", "Comments"),
                ("shares", "Shares"),
            ]
        )
    if platform == "Instagram":
        fields.append(("saves", "Saves"))
    if platform in {"Etsy", "Website"}:
        fields.extend([("etsy_visits", "Etsy Visits"), ("etsy_orders", "Etsy Orders")])
    if platform == "Website":
        fields.append(("email_signups", "Email Signups"))
    return fields


def complete_task_status(session: Session, task_id: int, action: str, notes: str = "", post_url: str = "") -> TaskRecord:
    status_by_action = {
        "mark_posted": "posted",
        "scheduled": "scheduled",
        "needs_help": "blocked",
        "skip": "skipped",
        "complete": "complete",
    }
    status = status_by_action.get(action, action if action in TASK_STATUSES else "ready to post")
    task = update_task_status(session, task_id, status, notes)
    if post_url:
        task.published_url = post_url
    if status == "posted":
        task.metric_status = "pending"
        task.metric_due_date = date.today() + timedelta(days=1)
    elif status in {"complete", "skipped"}:
        task.metric_status = "complete"
    return task


def mark_metric_recorded(task: TaskRecord) -> None:
    task.metric_status = "complete"


def action_title(task: TaskRecord) -> str:
    if task.platform in {"Instagram", "Facebook"}:
        product = task.product_name or "a product"
        content = {
            "reel": "short Reel",
            "carousel": "carousel",
            "post": "post",
        }.get(task.content_type, task.content_type or "post")
        return f"Post a {content} for {product} on {task.platform}"
    if task.platform == "Etsy":
        return f"Review the Etsy listing for {task.product_name or 'a product'}"
    if task.platform == "Website":
        return f"Work on the website story for {task.product_name or 'a product'}"
    if task.status == "blocked":
        return task.title
    return task.title


def plain_status(status: str) -> str:
    labels = {
        "needs asset": "Needs an asset",
        "needs copy review": "Needs copy review",
        "ready to post": "Ready",
        "scheduled": "Scheduled",
        "posted": "Posted",
        "metrics needed": "Metrics due",
        "complete": "Complete",
        "skipped": "Skipped",
        "blocked": "Needs help",
    }
    return labels.get(status, status.replace("_", " ").title())


def status_tone(status: str) -> str:
    if status in {"complete", "posted"}:
        return "complete"
    if status in {"blocked", "needs asset", "needs copy review"}:
        return "blocked"
    if status in {"ready to post", "scheduled", "metrics needed"}:
        return "ready"
    return ""


def refresh_asset_file_state(session: Session, base_dir: str | Path = ".") -> list[AssetRecord]:
    base = Path(base_dir)
    assets = list(session.scalars(select(AssetRecord).order_by(AssetRecord.id)))
    now = utc_now()
    for asset in assets:
        path = asset_path(asset, base)
        exists = path.is_file()
        asset.file_exists = 1 if exists else 0
        asset.file_checked_at = now
        asset.file_modified_at = datetime.fromtimestamp(path.stat().st_mtime) if exists else None
        asset.file_checksum = _file_checksum(path) if exists else ""
        if exists and asset.review_state == "unreviewed" and asset.readiness_state == "existing Etsy photo ready":
            asset.review_state = "approved"
    return assets


def scan_local_asset_folder(session: Session, assets_root: str | Path = "assets/products") -> list[AssetRecord]:
    root = Path(assets_root)
    if not root.exists():
        return refresh_asset_file_state(session)

    products = list(session.scalars(select(ProductRecord)))
    product_by_slug = {slugify(product.name): product for product in products}
    imported: list[AssetRecord] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        relative = path.as_posix()
        product = _product_for_asset_path(path, product_by_slug)
        existing = session.scalar(select(AssetRecord).where(AssetRecord.source_path == relative))
        if existing:
            asset = existing
        else:
            asset = AssetRecord(
                product_id=product.id if product else None,
                name=_asset_name(path, product),
                asset_type=_asset_type(path),
                source_path=relative,
                preview_path=relative,
                platform_suitability_json="[]",
                readiness_state="needs review",
                notes="Imported from local product asset folder.",
                external_source="local_folder",
                sync_status="imported",
                staleness_state="fresh",
                review_state="needs review",
            )
            session.add(asset)
        asset.product_id = product.id if product else asset.product_id
        asset.preview_path = asset.preview_path or relative
        asset.file_exists = 1
        asset.file_checked_at = utc_now()
        asset.file_modified_at = datetime.fromtimestamp(path.stat().st_mtime)
        asset.file_checksum = _file_checksum(path)
        imported.append(asset)
    session.flush()
    refresh_asset_file_state(session)
    return imported


def register_local_source_photo(
    session: Session,
    file_path: str | Path,
    product_id: int | None = None,
    name: str = "",
    notes: str = "",
) -> AssetRecord:
    path = Path(file_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"Source photo file not found: {path}")
    if path.suffix.lower() not in IMAGE_EXTENSIONS:
        raise ValueError(f"Unsupported image file type: {path.suffix}")

    product = session.get(ProductRecord, product_id) if product_id else None
    source_path = path.as_posix()
    existing = session.scalar(select(AssetRecord).where(AssetRecord.source_path == source_path))
    if existing:
        existing.product_id = product.id if product else existing.product_id
        existing.name = name or existing.name
        existing.notes = notes or existing.notes
        existing.file_exists = 1
        existing.file_checked_at = utc_now()
        existing.file_modified_at = datetime.fromtimestamp(path.stat().st_mtime)
        existing.file_checksum = _file_checksum(path)
        return existing

    asset = AssetRecord(
        product_id=product.id if product else None,
        name=name or _asset_name(path, product),
        asset_type="source photo",
        source_path=source_path,
        preview_path=source_path,
        platform_suitability_json='["Instagram", "Facebook", "Etsy", "Website"]',
        readiness_state="needs review",
        notes=notes or "Registered from a local source photo path.",
        external_source="local_file",
        sync_status="registered",
        staleness_state="fresh",
        review_state="needs review",
        file_exists=1,
        file_checked_at=utc_now(),
        file_modified_at=datetime.fromtimestamp(path.stat().st_mtime),
        file_checksum=_file_checksum(path),
    )
    session.add(asset)
    session.flush()
    return asset


def import_source_photo_to_inventory(
    session: Session,
    file_path: str | Path,
    product_id: int | None = None,
    name: str = "",
    notes: str = "",
    assets_root: str | Path = "assets/products",
) -> AssetRecord:
    source = Path(file_path).expanduser()
    if not source.is_file():
        raise FileNotFoundError(f"Source photo file not found: {source}")
    if source.suffix.lower() not in IMAGE_EXTENSIONS:
        raise ValueError(f"Unsupported image file type: {source.suffix}")

    product = session.get(ProductRecord, product_id) if product_id else None
    product_slug = slugify(product.name) if product else "unassigned"
    target_dir = Path(assets_root) / product_slug / "source"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = _unique_path(target_dir / source.name)
    copy2(source, target)
    return register_local_source_photo(
        session,
        target,
        product_id=product_id,
        name=name or _asset_name(target, product),
        notes=notes or "Copied into the local product asset inventory.",
    )


def asset_path(asset: AssetRecord, base_dir: str | Path = ".") -> Path:
    raw = Path(asset.preview_path or asset.source_path)
    if raw.is_absolute():
        return raw
    return Path(base_dir) / raw


def data_health(session: Session) -> list[DataHealthItem]:
    products = list(session.scalars(select(ProductRecord)))
    assets = list(session.scalars(select(AssetRecord)))
    templates = list(session.scalars(select(TemplateRecord)))
    metric_tasks = list(session.scalars(select(TaskRecord).where(TaskRecord.status.in_(METRIC_RELEVANT_STATUS))))
    planned_items = list(session.scalars(select(PlannedContentRecord)))
    generated_candidates = list(session.scalars(select(GeneratedContentCandidateRecord)))
    sync_metadata = list(session.scalars(select(SyncMetadata)))
    stale_products = [product for product in products if product.staleness_state in {"stale", "unknown"} and product.external_source]
    imported_products = [product for product in products if product.external_source]
    sync_errors = [product for product in products if product.sync_error or product.sync_status == "error"]
    manual_overrides = [
        record
        for record in [*products, *assets, *metric_tasks]
        if getattr(record, "manual_override_state", "") in {"locked", "override"}
    ]
    missing_assets = [asset for asset in assets if not asset.file_exists]
    unreviewed_assets = [asset for asset in assets if asset.review_state in {"needs review", "unreviewed"}]
    metrics_due = [task for task in metric_tasks if task.metric_status != "complete"]
    planned_without_candidates = [item for item in planned_items if item.status == "planned" and not item.candidates]
    candidates_needing_review = [candidate for candidate in generated_candidates if candidate.review_state == "needs_review"]
    etsy_sync = next((record for record in sync_metadata if record.source_name == "etsy_api"), None)
    website_sync = next((record for record in sync_metadata if record.source_name == "mattmademe_website"), None)
    template_types = {template.template_type for template in templates}
    missing_template_types = [kind for kind in ["platform", "copy", "graphic"] if kind not in template_types]

    return [
        DataHealthItem(
            "Products",
            "Needs review" if stale_products else "OK",
            len(stale_products),
            "Imported product records need review or have stale sync state." if stale_products else "Product records are local or current.",
            "Review imported product sync state.",
        ),
        DataHealthItem(
            "Imports",
            "Errors" if sync_errors else "OK",
            len(sync_errors) if sync_errors else len(imported_products),
            "Some imported records have sync errors." if sync_errors else f"{len(imported_products)} imported record(s) are tracked with source metadata.",
            "Use Settings to import Etsy CSV records or review sync errors.",
        ),
        DataHealthItem(
            "Templates",
            "Needs attention" if missing_template_types else "OK",
            len(missing_template_types),
            f"Missing template categories: {', '.join(missing_template_types)}." if missing_template_types else "Platform, copy, and graphic templates are loaded.",
            "Review docs/templates if a template category is missing.",
        ),
        DataHealthItem(
            "Assets",
            "Needs attention" if missing_assets else "OK",
            len(missing_assets),
            "Some asset records point to files that were not found." if missing_assets else "Asset file checks did not find missing files.",
            "Run local asset scan or update asset paths.",
        ),
        DataHealthItem(
            "Manual Overrides",
            "Review" if manual_overrides else "OK",
            len(manual_overrides),
            "Some imported or synced records are protected by local manual overrides."
            if manual_overrides
            else "No imported or synced records are currently locked by manual overrides.",
            "Review override notes before running future imports.",
        ),
        DataHealthItem(
            "Asset Review",
            "Needs review" if unreviewed_assets else "OK",
            len(unreviewed_assets),
            "Some assets need human approval before they should be used confidently." if unreviewed_assets else "Assets are approved or intentionally complete.",
            "Review source and generated assets.",
        ),
        DataHealthItem(
            "Metrics",
            "Follow up" if metrics_due else "OK",
            len(metrics_due),
            "Posted tasks still need metrics or final review." if metrics_due else "No posted tasks are waiting for metric follow-up.",
            "Open Metrics Due.",
        ),
        DataHealthItem(
            "Content Production",
            "Needs review" if planned_without_candidates or candidates_needing_review else "OK",
            len(planned_without_candidates) + len(candidates_needing_review),
            "Planned content needs candidates or generated candidates need review."
            if planned_without_candidates or candidates_needing_review
            else "No planned content is waiting for production review.",
            "Open Planning.",
        ),
        DataHealthItem(
            "Etsy Sync",
            _sync_status_label(etsy_sync),
            0 if etsy_sync and "error:" not in etsy_sync.notes and "missing_credentials" not in etsy_sync.notes else 1,
            _sync_message(etsy_sync, "Etsy API has not been synced yet."),
            "Configure Etsy credentials in .env or run sync from Settings.",
        ),
        DataHealthItem(
            "Website Sync",
            _sync_status_label(website_sync),
            0 if website_sync and "error:" not in website_sync.notes and "missing_credentials" not in website_sync.notes else 1,
            _sync_message(website_sync, "MattMadeMe website API has not been synced yet."),
            "Configure website API credentials in .env or run sync from Settings.",
        ),
    ]


def import_etsy_listing_csv(session: Session, csv_path: str | Path) -> list[ProductRecord]:
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    imported: list[ProductRecord] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            title = _first_present(row, ["title", "name", "listing_title", "Title", "Name", "Listing Title"])
            if not title:
                continue
            listing_id = _first_present(row, ["listing_id", "id", "Listing ID", "Listing Id", "ID"])
            url = _first_present(row, ["url", "listing_url", "URL", "Listing URL"])
            status = _first_present(row, ["state", "status", "Status", "State"]) or "imported"
            existing = _find_product_for_import(session, title, listing_id)
            if existing is None:
                existing = ProductRecord(
                    name=title,
                    status=status,
                    primary_audience="Needs review",
                    secondary_audiences_json="[]",
                    best_channels_json='["Etsy"]',
                    use_cases_json="[]",
                    seasonality_json="[]",
                    sales_momentum_note="Imported from Etsy CSV; review audience, seasonality, and launch priority.",
                    launch_priority="medium",
                )
                session.add(existing)
            if existing.manual_override_state not in {"locked", "override"}:
                existing.status = status
                existing.sync_error = ""
            else:
                existing.sync_error = "Import skipped local fields because this product has a manual override."
            existing.external_source = "etsy_csv"
            existing.external_id = listing_id
            existing.canonical_url = url
            existing.last_synced_at = utc_now()
            existing.sync_status = "manual override" if existing.manual_override_state in {"locked", "override"} else "imported"
            existing.staleness_state = "fresh"
            imported.append(existing)
    session.flush()
    return imported


def backup_sqlite_database(db_path: str | Path, backup_dir: str | Path = "data/backups") -> Path:
    source = Path(db_path)
    if not source.exists():
        raise FileNotFoundError(f"Database file not found: {source}")
    target_dir = Path(backup_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = target_dir / f"{source.stem}-{stamp}{source.suffix}"
    copy2(source, target)
    return target


def export_operating_data(session: Session, export_dir: str | Path = "data/exports") -> Path:
    target_dir = Path(export_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = target_dir / f"marketing-os-export-{stamp}.json"
    payload = {
        "exported_at": utc_now().isoformat(),
        "format": "marketing_os_phase4_export",
        "version": 1,
        "products": [_export_product(record) for record in session.scalars(select(ProductRecord).order_by(ProductRecord.name))],
        "templates": [_export_template(record) for record in session.scalars(select(TemplateRecord).order_by(TemplateRecord.template_type, TemplateRecord.name))],
        "assets": [_export_asset(record) for record in session.scalars(select(AssetRecord).order_by(AssetRecord.name))],
        "plans": [_export_plan(record) for record in session.scalars(select(PlanRecord).order_by(PlanRecord.generated_at, PlanRecord.id))],
        "calendar_items": [_export_calendar_item(record) for record in session.scalars(select(CalendarItemRecord).order_by(CalendarItemRecord.date, CalendarItemRecord.id))],
        "planned_content_items": [
            _export_planned_content_item(record) for record in session.scalars(select(PlannedContentRecord).order_by(PlannedContentRecord.calendar_date, PlannedContentRecord.id))
        ],
        "generated_content_candidates": [
            _export_generated_content_candidate(record)
            for record in session.scalars(select(GeneratedContentCandidateRecord).order_by(GeneratedContentCandidateRecord.created_at, GeneratedContentCandidateRecord.id))
        ],
        "tasks": [_export_task(record) for record in session.scalars(select(TaskRecord).order_by(TaskRecord.due_date, TaskRecord.id))],
        "metrics": [_export_metric(record) for record in session.scalars(select(MetricRecord).order_by(MetricRecord.recorded_on, MetricRecord.id))],
        "blog_posts": [_export_blog_post(record) for record in session.scalars(select(BlogPostRecord).order_by(BlogPostRecord.title, BlogPostRecord.id))],
        "sync_metadata": [_export_sync(record) for record in session.scalars(select(SyncMetadata).order_by(SyncMetadata.source_name))],
    }
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target


def register_generated_asset_candidate(
    session: Session,
    source_asset: AssetRecord,
    output_path: str | Path,
    template_name: str,
    prompt: str,
    notes: str = "",
) -> AssetRecord:
    output = Path(output_path)
    record = AssetRecord(
        product_id=source_asset.product_id,
        name=f"{source_asset.name} {template_name}",
        asset_type="generated graphic",
        source_path=output.as_posix(),
        preview_path=output.as_posix(),
        platform_suitability_json=source_asset.platform_suitability_json,
        readiness_state="needs human review",
        notes=notes or f"Generated candidate from {source_asset.name}.",
        external_source="creative_asset_agent",
        sync_status="generated",
        staleness_state="fresh",
        review_state="needs review",
        generated_prompt=prompt,
        source_asset_id=source_asset.id,
    )
    session.add(record)
    session.flush()
    refresh_asset_file_state(session)
    return record


def _creative_format_plan(asset: AssetRecord, template: TemplateRecord, output_root: str | Path) -> CreativeFormatPlan:
    body = _json_dict(template.body_json)
    product_slug = slugify(asset.product.name if asset.product else asset.name)
    template_slug = slugify(str(body.get("name") or template.name))
    dimensions = str(body.get("dimensions") or body.get("recommended_dimensions") or "")
    output_path = (Path(output_root) / product_slug / f"{template_slug}.jpg").as_posix()
    rules = str(body.get("rules") or body.get("text_overlay_rules") or "")
    prompt = (
        f"Create a {body.get('name') or template.name} for {asset.product.name if asset.product else asset.name}. "
        f"Use source image {asset.source_path}. Preserve product shape, color, printed details, and proportions. "
        f"Do not add misleading product details. {rules}".strip()
    )
    return CreativeFormatPlan(
        template_name=str(body.get("name") or template.name),
        dimensions=dimensions,
        output_path=output_path,
        prompt=prompt,
    )


def _creative_readiness_message(asset: AssetRecord) -> str:
    if not asset.file_exists:
        return "Source file is missing. Add or scan the product photo before generating graphics."
    if asset.review_state != "approved":
        return "Source photo needs human approval before generation."
    return "Ready for generated-output registration."


def review_asset(session: Session, asset_id: int, review_state: str, notes: str = "") -> AssetRecord:
    if review_state not in {"approved", "needs review", "rejected"}:
        raise ValueError(f"Unsupported review state: {review_state}")
    asset = session.get(AssetRecord, asset_id)
    if asset is None:
        raise ValueError(f"Asset not found: {asset_id}")
    refresh_asset_file_state(session)
    if review_state == "approved" and not asset.file_exists:
        raise ValueError("Asset file must exist before it can be approved.")
    asset.review_state = review_state
    asset.approval_notes = notes
    if review_state == "approved":
        asset.readiness_state = "ready to use"
    elif review_state == "rejected":
        asset.readiness_state = "do not use"
    return asset


def _task_priority_key(task: TaskRecord) -> tuple[int, date, int]:
    status_rank = {
        "ready to post": 0,
        "scheduled": 1,
        "needs copy review": 2,
        "needs asset": 3,
        "metrics needed": 4,
        "posted": 5,
        "blocked": 6,
    }
    return (status_rank.get(task.status, 9), task.due_date, task.id)


def _product_for_asset_path(path: Path, product_by_slug: dict[str, ProductRecord]) -> ProductRecord | None:
    parts = path.parts
    for part in reversed(parts):
        if part in product_by_slug:
            return product_by_slug[part]
    return None


def _asset_name(path: Path, product: ProductRecord | None) -> str:
    stem = path.stem.replace("-", " ").replace("_", " ").title()
    return f"{product.name} {stem}" if product else stem


def _asset_type(path: Path) -> str:
    parts = {part.lower() for part in path.parts}
    if "generated" in parts:
        return "generated graphic"
    if "edited" in parts:
        return "edited photo"
    if "template" in parts or "templates" in parts:
        return "template output"
    return "source photo"


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 2
    while True:
        candidate = parent / f"{stem}-{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _file_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dimensions_for_candidate(session: Session, candidate: AssetRecord) -> tuple[int, int]:
    templates = list(session.scalars(select(TemplateRecord).where(TemplateRecord.template_type == "graphic")))
    template = next((item for item in templates if candidate.name.endswith(item.name)), None)
    body = _json_dict(template.body_json) if template else {}
    raw = str(body.get("dimensions") or "1080x1080")
    try:
        width, height = raw.lower().split("x", 1)
        return int(width), int(height)
    except ValueError:
        return (1080, 1080)


def _render_generated_candidate(source_path: Path, output_path: Path, product_name: str, dimensions: tuple[int, int]) -> None:
    from PIL import Image, ImageDraw, ImageFont, ImageOps

    width, height = dimensions
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas = Image.new("RGB", (width, height), "#f7f8f5")
    draw = ImageDraw.Draw(canvas)
    accent = "#0f766e"
    ink = "#202124"
    soft = "#d7f3ee"

    draw.rectangle((0, 0, width, max(18, height // 90)), fill=accent)
    source = Image.open(source_path).convert("RGB")
    margin = max(54, width // 18)
    header_space = max(140, height // 8)
    footer_space = max(130, height // 10)
    image_box = (margin, header_space, width - margin, height - footer_space)
    contained = ImageOps.contain(source, (image_box[2] - image_box[0], image_box[3] - image_box[1]))
    image_x = image_box[0] + ((image_box[2] - image_box[0]) - contained.width) // 2
    image_y = image_box[1] + ((image_box[3] - image_box[1]) - contained.height) // 2
    draw.rounded_rectangle((image_x - 18, image_y - 18, image_x + contained.width + 18, image_y + contained.height + 18), radius=28, fill="white")
    canvas.paste(contained, (image_x, image_y))

    title_font = _font(size=max(42, width // 18))
    small_font = _font(size=max(28, width // 34))
    title = product_name
    draw.text((margin, margin), title, fill=ink, font=title_font)
    draw.rounded_rectangle((margin, height - footer_space + 32, width - margin, height - margin), radius=22, fill=soft)
    draw.text((margin + 28, height - footer_space + 58), "MattMadeMe.com", fill=accent, font=small_font)
    canvas.save(output_path, quality=92)


def _font(size: int):
    from PIL import ImageFont

    for candidate in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ):
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def _json_dict(value: str) -> dict[str, object]:
    try:
        data = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _sync_status_label(record: SyncMetadata | None) -> str:
    if record is None:
        return "Missing"
    if "error:" in record.notes or "missing_credentials" in record.notes:
        return "Needs attention"
    return "OK"


def _sync_message(record: SyncMetadata | None, empty_message: str) -> str:
    if record is None:
        return empty_message
    return f"{record.notes} Last checked {record.synced_at.isoformat()}."


def _date_text(value: date | datetime | None) -> str | None:
    return value.isoformat() if value else None


def _export_product(record: ProductRecord) -> JsonDict:
    return {
        "id": record.id,
        "name": record.name,
        "status": record.status,
        "primary_audience": record.primary_audience,
        "secondary_audiences": json_list(record.secondary_audiences_json),
        "best_channels": json_list(record.best_channels_json),
        "use_cases": json_list(record.use_cases_json),
        "seasonality": json_list(record.seasonality_json),
        "sales_momentum_note": record.sales_momentum_note,
        "launch_priority": record.launch_priority,
        "external_source": record.external_source,
        "external_id": record.external_id,
        "canonical_url": record.canonical_url,
        "last_synced_at": _date_text(record.last_synced_at),
        "sync_status": record.sync_status,
        "sync_error": record.sync_error,
        "staleness_state": record.staleness_state,
        "manual_override_state": record.manual_override_state,
        "manual_override_note": record.manual_override_note,
        "updated_at": _date_text(record.updated_at),
    }


def _export_template(record: TemplateRecord) -> JsonDict:
    return {
        "id": record.id,
        "template_type": record.template_type,
        "name": record.name,
        "platform": record.platform,
        "format": record.format,
        "source_path": record.source_path,
        "body": _json_dict(record.body_json),
        "updated_at": _date_text(record.updated_at),
    }


def _export_asset(record: AssetRecord) -> JsonDict:
    return {
        "id": record.id,
        "product_id": record.product_id,
        "name": record.name,
        "asset_type": record.asset_type,
        "source_path": record.source_path,
        "preview_path": record.preview_path,
        "platform_suitability": json_list(record.platform_suitability_json),
        "readiness_state": record.readiness_state,
        "notes": record.notes,
        "date_added": _date_text(record.date_added),
        "external_source": record.external_source,
        "external_id": record.external_id,
        "canonical_url": record.canonical_url,
        "last_synced_at": _date_text(record.last_synced_at),
        "sync_status": record.sync_status,
        "sync_error": record.sync_error,
        "staleness_state": record.staleness_state,
        "manual_override_state": record.manual_override_state,
        "manual_override_note": record.manual_override_note,
        "file_exists": bool(record.file_exists),
        "file_checked_at": _date_text(record.file_checked_at),
        "file_modified_at": _date_text(record.file_modified_at),
        "file_checksum": record.file_checksum,
        "review_state": record.review_state,
        "approval_notes": record.approval_notes,
        "generated_prompt": record.generated_prompt,
        "source_asset_id": record.source_asset_id,
    }


def _export_plan(record: PlanRecord) -> JsonDict:
    return {
        "id": record.id,
        "mode": record.mode,
        "start_date": _date_text(record.start_date),
        "generated_at": _date_text(record.generated_at),
        "weekly_theme": record.weekly_theme,
        "campaign_narrative": record.campaign_narrative,
        "validation_report": _json_dict(record.validation_report_json),
        "status": record.status,
    }


def _export_calendar_item(record: CalendarItemRecord) -> JsonDict:
    return {
        "id": record.id,
        "plan_id": record.plan_id,
        "date": _date_text(record.date),
        "title": record.title,
        "platform": record.platform,
        "content_type": record.content_type,
        "business_goal": record.business_goal,
        "objective": record.objective,
        "target_audience": record.target_audience,
        "featured_product": record.featured_product,
        "draft_copy": record.draft_copy,
        "cta": record.cta,
        "hashtags": json_list(record.hashtags_json),
        "asset_brief": record.asset_brief,
        "asset_type": record.asset_type,
        "production_notes": record.production_notes,
        "priority": record.priority,
        "effort_estimate": record.effort_estimate,
        "expected_impact": record.expected_impact,
        "success_metric": record.success_metric,
    }


def _export_planned_content_item(record: PlannedContentRecord) -> JsonDict:
    return {
        "id": record.id,
        "calendar_date": _date_text(record.calendar_date),
        "destinations": json_list(record.destinations_json),
        "goals": json_list(record.goals_json),
        "product_ids": json_list(record.product_ids_json),
        "audience": record.audience,
        "occasion": record.occasion,
        "promotion": record.promotion,
        "notes": record.notes,
        "status": record.status,
        "brief_status": record.brief_status,
        "last_production_run_at": _date_text(record.last_production_run_at),
        "production_error": record.production_error,
        "created_at": _date_text(record.created_at),
        "updated_at": _date_text(record.updated_at),
    }


def _export_generated_content_candidate(record: GeneratedContentCandidateRecord) -> JsonDict:
    return {
        "id": record.id,
        "planned_item_id": record.planned_item_id,
        "candidate_type": record.candidate_type,
        "provider": record.provider,
        "body": record.body,
        "source_facts": _json_dict(record.source_facts_json),
        "source_asset_ids": json_list(record.source_asset_ids_json),
        "review_state": record.review_state,
        "revision_notes": record.revision_notes,
        "created_at": _date_text(record.created_at),
        "updated_at": _date_text(record.updated_at),
    }


def _export_blog_post(record: BlogPostRecord) -> JsonDict:
    return {
        "id": record.id,
        "external_source": record.external_source,
        "external_id": record.external_id,
        "title": record.title,
        "slug": record.slug,
        "excerpt": record.excerpt,
        "canonical_url": record.canonical_url,
        "published_at": _date_text(record.published_at),
        "updated_external_at": _date_text(record.updated_external_at),
        "tags": json_list(record.tags_json),
        "raw_external_data": _json_dict(record.raw_external_data_json),
        "last_synced_at": _date_text(record.last_synced_at),
        "sync_status": record.sync_status,
        "sync_error": record.sync_error,
        "review_state": record.review_state,
        "created_at": _date_text(record.created_at),
        "updated_at": _date_text(record.updated_at),
    }


def _export_task(record: TaskRecord) -> JsonDict:
    return {
        "id": record.id,
        "plan_id": record.plan_id,
        "calendar_item_id": record.calendar_item_id,
        "due_date": _date_text(record.due_date),
        "title": record.title,
        "owner_role": record.owner_role,
        "platform": record.platform,
        "content_type": record.content_type,
        "product_name": record.product_name,
        "asset_id": record.asset_id,
        "draft_caption": record.draft_caption,
        "cta": record.cta,
        "hashtags": json_list(record.hashtags_json),
        "posting_steps": json_list(record.posting_steps_json),
        "preview_checklist": json_list(record.preview_checklist_json),
        "metric_instruction": record.metric_instruction,
        "published_url": record.published_url,
        "platform_post_id": record.platform_post_id,
        "metric_due_date": _date_text(record.metric_due_date),
        "metric_status": record.metric_status,
        "external_source": record.external_source,
        "external_id": record.external_id,
        "canonical_url": record.canonical_url,
        "last_synced_at": _date_text(record.last_synced_at),
        "sync_status": record.sync_status,
        "sync_error": record.sync_error,
        "staleness_state": record.staleness_state,
        "manual_override_state": record.manual_override_state,
        "manual_override_note": record.manual_override_note,
        "status": record.status,
        "notes": record.notes,
        "created_at": _date_text(record.created_at),
        "updated_at": _date_text(record.updated_at),
    }


def _export_metric(record: MetricRecord) -> JsonDict:
    return {
        "id": record.id,
        "task_id": record.task_id,
        "recorded_on": _date_text(record.recorded_on),
        "post_url": record.post_url,
        "reach": record.reach,
        "likes": record.likes,
        "comments": record.comments,
        "shares": record.shares,
        "saves": record.saves,
        "etsy_visits": record.etsy_visits,
        "etsy_orders": record.etsy_orders,
        "email_signups": record.email_signups,
        "notes": record.notes,
        "collection_status": record.collection_status,
        "external_source": record.external_source,
        "external_id": record.external_id,
        "last_synced_at": _date_text(record.last_synced_at),
        "sync_status": record.sync_status,
        "sync_error": record.sync_error,
        "manual_override_state": record.manual_override_state,
        "manual_override_note": record.manual_override_note,
        "created_at": _date_text(record.created_at),
    }


def _export_sync(record: SyncMetadata) -> JsonDict:
    return {
        "id": record.id,
        "source_name": record.source_name,
        "source_path": record.source_path,
        "synced_at": _date_text(record.synced_at),
        "notes": record.notes,
    }


def _template_name_from_candidate(candidate: AssetRecord) -> str:
    if candidate.name:
        return candidate.name
    return Path(candidate.source_path).stem.replace("-", " ").title()


def _first_present(row: dict[str, str], names: list[str]) -> str:
    for name in names:
        value = row.get(name)
        if value and value.strip():
            return value.strip()
    lower_lookup = {key.lower().strip(): value for key, value in row.items()}
    for name in names:
        value = lower_lookup.get(name.lower().strip())
        if value and value.strip():
            return value.strip()
    return ""


def _find_product_for_import(session: Session, title: str, listing_id: str) -> ProductRecord | None:
    if listing_id:
        existing = session.scalar(
            select(ProductRecord).where(
                ProductRecord.external_source == "etsy_csv",
                ProductRecord.external_id == listing_id,
            )
        )
        if existing:
            return existing
    return session.scalar(select(ProductRecord).where(ProductRecord.name == title))
