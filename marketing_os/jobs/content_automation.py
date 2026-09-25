from __future__ import annotations

import argparse
import json
import os
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy.orm import Session
from sqlalchemy import select

from ..db import create_db_engine, init_db, session_factory, session_scope
from ..db_models import CreativeGenerationJobRecord, PlannedContentRecord, SyncMetadata, utc_now
from ..services.art_studio import SOCIAL_JOB_FORMAT, art_studio_video_requests, serialize_art_studio_job
from ..services.content_briefs import (
    build_content_brief,
    has_copy_rewrite_request,
    localize_planned_content_reference_assets,
    planned_items_needing_production,
    produce_content_for_item,
    serialize_planned_content_item,
)
from ..services.skill_adapters import (
    art_studio_video_workflow_contract,
    image_option_from_contract,
    social_copy_workflow_contract,
    social_media_art_director_contracts,
)


IMAGE_QUEUE_STATUSES = {"waiting_content_generation", "waiting_image_generation", "waiting_image_regeneration"}
SOCIAL_DESTINATIONS = {"Facebook", "Instagram", "Pinterest", "Threads", "TikTok", "LinkedIn"}


def run(
    db_path: str | Path | None = None,
    business_dir: str = "docs/business",
    days_ahead: int = 14,
    limit: int = 10,
    output_dir: str | Path = "data/exports/content-automation",
    assets_root: str | Path | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    engine = create_db_engine(db_path)
    init_db(engine)
    factory = session_factory(engine)
    target_date = date.today() + timedelta(days=days_ahead)
    summary: dict[str, object] = {
        "processed": 0,
        "asset_downloaded": 0,
        "asset_download_errors": [],
        "image_request_files": [],
        "copy_request_files": [],
        "art_studio_social_image_files": [],
        "video_request_files": [],
        "video_generation_files": [],
        "items": [],
        "filters": {
            "days_ahead": days_ahead,
            "target_date": target_date.isoformat(),
            "limit": limit,
            "dry_run": dry_run,
            "output_dir": str(output_dir),
            "assets_root": str(_assets_root(assets_root)),
        },
    }
    try:
        with session_scope(factory) as session:
            asset_items = _asset_download_items(session, target_date=target_date, limit=limit)
            for item in asset_items:
                item_summary = _prepare_remote_assets(session, item, _assets_root(assets_root), dry_run)
                summary["items"].append(item_summary)
                if not dry_run:
                    session.commit()
                    if item_summary.get("asset_downloaded"):
                        summary["asset_downloaded"] = int(summary["asset_downloaded"]) + 1
                    if item_summary.get("asset_download_error"):
                        summary["asset_download_errors"].append(item_summary["asset_download_error"])
            items = planned_items_needing_production(session, target_date=target_date, limit=limit)
            for item in items:
                item_summary = _prepare_item(session, item, business_dir, output_dir, dry_run)
                summary["items"].append(item_summary)
                if not dry_run:
                    summary["processed"] = int(summary["processed"]) + 1
                if item_summary.get("image_request_path"):
                    summary["image_request_files"].append(item_summary["image_request_path"])
                if item_summary.get("copy_request_path"):
                    summary["copy_request_files"].append(item_summary["copy_request_path"])
            social_image_jobs = queued_art_studio_social_image_jobs(session, limit=limit)
            if social_image_jobs:
                social_image_path = str(write_art_studio_social_image_requests(social_image_jobs, output_dir))
                summary["art_studio_social_image_files"].append(social_image_path)
            for video_request in art_studio_video_requests(session, limit=limit):
                if video_request.status != "queued":
                    if video_request.status == "video_queued" and video_request.video_job is not None:
                        generation_path = str(write_art_studio_video_generation_request(video_request, output_dir))
                        summary["video_generation_files"].append(generation_path)
                    continue
                workflow_path = str(write_art_studio_video_workflow_request(video_request, output_dir))
                summary["video_request_files"].append(workflow_path)
            _record_automation_run(session, "content_automation", output_dir, summary)
    finally:
        engine.dispose()
    return summary


def _record_automation_run(session: Session, source_name: str, source_path: str | Path, summary: dict[str, object]) -> None:
    record = session.scalar(select(SyncMetadata).where(SyncMetadata.source_name == source_name))
    if record is None:
        record = SyncMetadata(source_name=source_name, source_path=str(source_path), notes="")
        session.add(record)
    record.source_path = str(source_path)
    record.synced_at = utc_now()
    record.notes = json.dumps(
        {
            "processed": summary.get("processed", 0),
            "asset_downloaded": summary.get("asset_downloaded", 0),
            "asset_download_errors": len(summary.get("asset_download_errors", [])),
            "copy_request_files": len(summary.get("copy_request_files", [])),
            "image_request_files": len(summary.get("image_request_files", [])),
            "art_studio_social_image_files": len(summary.get("art_studio_social_image_files", [])),
            "video_request_files": len(summary.get("video_request_files", [])),
            "video_generation_files": len(summary.get("video_generation_files", [])),
            "dry_run": dict(summary.get("filters", {})).get("dry_run", False),
        },
        sort_keys=True,
    )


def _asset_download_items(session: Session, target_date: date, limit: int) -> list[PlannedContentRecord]:
    return list(
        session.scalars(
            select(PlannedContentRecord)
            .where(PlannedContentRecord.status == "waiting_asset_download")
            .where(PlannedContentRecord.calendar_date <= target_date)
            .order_by(PlannedContentRecord.calendar_date, PlannedContentRecord.id)
            .limit(limit)
        )
    )


def _assets_root(value: str | Path | None = None) -> Path:
    return Path(value or os.environ.get("MARKETING_OS_ASSETS_ROOT", "assets/products"))


def _prepare_remote_assets(session: Session, item: PlannedContentRecord, assets_root: Path, dry_run: bool) -> dict[str, object]:
    item_summary: dict[str, object] = {
        "planned_item_id": item.id,
        "status": item.status,
        "brief_status": item.brief_status,
        "asset_downloaded": False,
        "asset_download_error": "",
        "planned_item": serialize_planned_content_item(session, item),
    }
    if dry_run:
        return item_summary
    try:
        localize_planned_content_reference_assets(session, item.id, assets_root)
        item_summary["asset_downloaded"] = True
        item_summary["status"] = item.status
        item_summary["brief_status"] = item.brief_status
        item_summary["planned_item"] = serialize_planned_content_item(session, item)
    except Exception as exc:
        item.production_error = f"Remote image preparation failed: {exc}"
        item_summary["asset_download_error"] = item.production_error
        item_summary["planned_item"] = serialize_planned_content_item(session, item)
    return item_summary


def _prepare_item(
    session: Session,
    item: PlannedContentRecord,
    business_dir: str,
    output_dir: str | Path,
    dry_run: bool,
) -> dict[str, object]:
    forced = has_copy_rewrite_request(item)
    if not dry_run:
        result = produce_content_for_item(session, item, business_dir=business_dir, force=forced)

    image_request_path = ""
    image_request_count = 0
    copy_request_path = ""
    needs_copy_workflow = _needs_copy_workflow(item)
    if needs_copy_workflow:
        copy_request_path = str(write_copy_workflow_request(session, item, output_dir, business_dir=business_dir))
    if item.status in IMAGE_QUEUE_STATUSES and not needs_copy_workflow and _has_reviewable_copy(item):
        image_request_path = str(write_image_requests(session, item, output_dir, business_dir=business_dir))
        image_request_count = 3

    return {
        "planned_item_id": item.id,
        "status": item.status,
        "brief_status": item.brief_status,
        "forced": forced,
        "image_request_count": image_request_count,
        "image_request_path": image_request_path,
        "copy_request_path": copy_request_path,
        "planned_item": serialize_planned_content_item(session, item),
    }


def write_copy_workflow_request(
    session: Session,
    item: PlannedContentRecord,
    output_dir: str | Path,
    business_dir: str = "docs/business",
) -> Path:
    brief = build_content_brief(session, item, business_dir=business_dir)
    destinations = [str(value) for value in brief.get("destinations", []) if str(value).strip()]
    destination = "Facebook" if "Facebook" in destinations else (destinations[0] if destinations else "social")
    workflow = social_copy_workflow_contract(brief, destination)
    target_dir = Path(output_dir) / f"planned-item-{item.id}"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "copy-workflow.json"
    target.write_text(
        json.dumps(
            {
                "planned_item_id": item.id,
                "calendar_date": item.calendar_date.isoformat(),
                "status": item.status,
                "brief": brief,
                "workflow": workflow,
                "instructions": [
                    "Run social-media-strategist first and save the strategy decision.",
                    "Run social-media-copywriter second using the strategy decision and source facts.",
                    "Run social-media-copy-chief third to challenge the draft before human review.",
                    "Register 2-3 challenged copy options in copy_options when useful so Planning can show option tabs.",
                    "Do not approve, post, or publish generated copy.",
                    "Use placeholders for missing MattMadeMe facts instead of inventing them.",
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return target


def _needs_copy_workflow(item: PlannedContentRecord) -> bool:
    if not SOCIAL_DESTINATIONS.intersection({str(value) for value in json.loads(item.destinations_json or "[]")}):
        return False
    if item.status in {"planned", "waiting_content_generation", "waiting_copy_regeneration"}:
        return True
    return any(candidate.candidate_type == "facebook_post" and candidate.review_state == "rewrite_requested" for candidate in item.candidates)


def _has_reviewable_copy(item: PlannedContentRecord) -> bool:
    return any(
        candidate.candidate_type == "facebook_post" and candidate.review_state in {"needs_review", "approved"}
        for candidate in item.candidates
    )


def write_image_requests(
    session: Session,
    item: PlannedContentRecord,
    output_dir: str | Path,
    business_dir: str = "docs/business",
) -> Path:
    brief = build_content_brief(session, item, business_dir=business_dir)
    contracts = social_media_art_director_contracts(brief, count=3)
    options = [image_option_from_contract(contract) for contract in contracts]
    target_dir = Path(output_dir) / f"planned-item-{item.id}"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "image-requests.json"
    target.write_text(
        json.dumps(
            {
                "planned_item_id": item.id,
                "calendar_date": item.calendar_date.isoformat(),
                "status": item.status,
                "brief": brief,
                "options": options,
                "registration_manifest_example": {
                    "planned_item_id": item.id,
                    "provider": "magnific_mcp",
                    "notes": "Downloaded Magnific MCP outputs registered for human review in Marketing OS.",
                    "images": [
                        {
                            "option_number": option["option_number"],
                            "image_path": option.get("output_path") or _planning_output_path(item.id, option["option_number"]),
                            "title": option["title"],
                            "best_for": option["best_for"],
                            "skill_request": option["skill_request"],
                            "skill_check": option["skill_check"],
                            "provider_path": option["provider_path"],
                            "model_preference": option.get("model_preference"),
                            "reference_images": option.get("reference_images", []),
                            "reference_image_roles": option.get("reference_image_roles", []),
                            "review_checklist": option["review_checklist"],
                        }
                        for option in options
                    ],
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return target


def write_art_studio_video_workflow_request(video_request, output_dir: str | Path) -> Path:
    details = dict(video_request.details)
    reference_images = [asset.source_path for asset in video_request.reference_assets if str(asset.source_path).strip()]
    source_asset_ids = [asset.id for asset in video_request.reference_assets if asset.id is not None]
    workflow = art_studio_video_workflow_contract(
        request_job_id=video_request.request_job.id,
        product_id=video_request.product.id,
        product_name=video_request.product.name,
        duration_seconds=int(details.get("duration_seconds") or 8),
        aspect_ratio=str(details.get("aspect_ratio") or "9:16"),
        resolution=str(details.get("resolution") or "1080p"),
        scene_guidance=str(details.get("scene_guidance") or ""),
        requested_template_slug=str(details.get("video_template_slug") or "focus_pull"),
        requested_template_name=str(details.get("video_template_name") or "Focus pull"),
        suggested_model=str(details.get("suggested_video_model") or ""),
        requested_voice_script=str(details.get("requested_voice_script") or ""),
        requested_voice_tone=str(details.get("requested_voice_tone") or ""),
        reference_images=reference_images,
        source_asset_ids=source_asset_ids,
    )
    target_dir = Path(output_dir) / f"video-request-{video_request.request_job.id}"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "video-workflow.json"
    target.write_text(
        json.dumps(
            {
                "request_job_id": video_request.request_job.id,
                "product_id": video_request.product.id,
                "product_name": video_request.product.name,
                "status": video_request.status,
                "request": {
                    "duration_seconds": int(details.get("duration_seconds") or 8),
                    "aspect_ratio": str(details.get("aspect_ratio") or "9:16"),
                    "resolution": str(details.get("resolution") or "1080p"),
                    "scene_guidance": str(details.get("scene_guidance") or ""),
                    "video_template_slug": str(details.get("video_template_slug") or "focus_pull"),
                    "video_template_name": str(details.get("video_template_name") or "Focus pull"),
                    "suggested_video_model": str(details.get("suggested_video_model") or ""),
                    "requested_voice_script": str(details.get("requested_voice_script") or ""),
                    "requested_voice_tone": str(details.get("requested_voice_tone") or ""),
                    "reference_asset_ids": source_asset_ids,
                    "reference_images": reference_images,
                },
                "workflow": workflow,
                "instructions": [
                    "Run video-content-planner first and save the planner decision.",
                    "Use social-media-art-director second to write the opening scene-card prompt from that planner decision.",
                    "Only include an ending card when the planner explicitly requires first/last-frame control.",
                    "Keep the duck inanimate and physically unchanged.",
                    "Build register-video-workflow.json beside this file using the registration_manifest_example shape.",
                    "Register the planner result and queue the scene-card jobs: python -m marketing_os.jobs.register_art_studio_video_workflow --manifest data/exports/content-automation/video-request-<id>/register-video-workflow.json",
                    "Generate the queued opening scene card immediately through Magnific MCP, download it locally, and register it through python -m marketing_os.jobs.register_art_studio_outputs.",
                    "Generate the ending card only when the planner explicitly required it, then register it the same way.",
                    "Leave the request waiting for human video approval after the card assets are attached.",
                ],
                "registration_manifest_example": {
                    "request_job_id": video_request.request_job.id,
                    "provider": "codex_agent",
                    "notes": "Planner brief registered from agent-run video workflow. Scene cards remain in human review.",
                    "planner_result": {
                        "summary": "",
                        "scene_strategy": "",
                        "selected_effect": {
                            "slug": "",
                            "name": "",
                            "risk": "",
                            "value": "",
                        },
                        "opening_card_brief": "",
                        "ending_card_brief": "",
                        "video_motion_prompt": "",
                        "audio_direction": "",
                        "style_direction": "",
                        "tail_rule": "",
                        "storyboard_mode": "single_start_frame",
                        "ending_card_required": False,
                    },
                    "opening_card": {
                        "title": f"{video_request.product.name} opening card",
                        "output_path": _art_studio_video_card_output_path(video_request.request_job.id, "opening"),
                        "prompt": "",
                        "provider": "magnific_mcp",
                        "model_name": "Google Nano Banana 2",
                    },
                    "ending_card": {
                        "required": False,
                        "title": f"{video_request.product.name} ending card",
                        "output_path": _art_studio_video_card_output_path(video_request.request_job.id, "ending"),
                        "prompt": "",
                        "provider": "magnific_mcp",
                        "model_name": "Google Nano Banana 2",
                    },
                    "video_editor_request": workflow["editor_request"]["input"],
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return target


def queued_art_studio_social_image_jobs(session: Session, limit: int = 10) -> list[CreativeGenerationJobRecord]:
    return list(
        session.scalars(
            select(CreativeGenerationJobRecord)
            .where(CreativeGenerationJobRecord.target_format == SOCIAL_JOB_FORMAT)
            .where(CreativeGenerationJobRecord.provider_status == "queued")
            .order_by(CreativeGenerationJobRecord.created_at, CreativeGenerationJobRecord.id)
            .limit(limit)
        )
    )


def write_art_studio_social_image_requests(jobs: list[CreativeGenerationJobRecord], output_dir: str | Path) -> Path:
    target_dir = Path(output_dir) / "art-studio-social-images"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "social-image-jobs.json"
    serialized_jobs = []
    outputs = []
    for job in jobs:
        job_payload = serialize_art_studio_job(job)
        output_path = _art_studio_social_image_output_path(job)
        job_payload["recommended_output_path"] = output_path
        serialized_jobs.append(job_payload)
        product_name = _art_studio_job_product_name(job)
        outputs.append(
            {
                "job_id": job.id,
                "media_type": "social_image",
                "output_path": output_path,
                "title": f"{product_name} Social Worthy image",
                "provider_job_id": "",
                "output_url": "",
                "notes": "Generated from Product Social Images queue. Keep in human review until product accuracy is approved.",
            }
        )
    target.write_text(
        json.dumps(
            {
                "workflow_name": "art_studio_social_worthy_images",
                "status": "queued",
                "job_count": len(serialized_jobs),
                "jobs": serialized_jobs,
                "instructions": [
                    "For each queued job, use $social-media-art-director and Magnific MCP to generate one real PNG/JPG social image.",
                    "Pass every listed reference image to Magnific for each option. Treat @img1 as the primary visible product and @img2+ as identity locks.",
                    "Use the job prompt exactly as the source brief; it contains product theme context, scene direction, a unique option scene variation, and product-preservation guardrails.",
                    "Do not add automation instructions, skill names, download steps, import steps, or review workflow text to the prompt sent to Magnific.",
                    "Download each completed image to its recommended_output_path.",
                    "Build register-social-images.json beside this file using registration_manifest_example, filling provider_job_id or output_url when available.",
                    "Register generated files with: python -m marketing_os.jobs.register_art_studio_outputs --manifest data/exports/content-automation/art-studio-social-images/register-social-images.json",
                    "Do not approve, publish, or post generated images automatically.",
                ],
                "registration_manifest_example": {
                    "outputs": outputs,
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return target


def write_art_studio_video_generation_request(video_request, output_dir: str | Path) -> Path:
    details = dict(video_request.details)
    if video_request.video_job is None:
        raise ValueError("Video request is missing a queued video job.")
    opening_asset = video_request.opening_job.candidate_asset if video_request.opening_job is not None else None
    ending_asset = video_request.ending_job.candidate_asset if video_request.ending_job is not None else None
    target_dir = Path(output_dir) / f"video-request-{video_request.request_job.id}"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "video-generation.json"
    target.write_text(
        json.dumps(
            {
                "request_job_id": video_request.request_job.id,
                "video_job_id": video_request.video_job.id,
                "product_id": video_request.product.id,
                "product_name": video_request.product.name,
                "status": video_request.status,
                "brief": {
                    "planner_summary": str(details.get("planner_summary") or ""),
                    "strategist_direction": str(details.get("strategist_direction") or ""),
                    "scene_strategy": str(details.get("scene_strategy") or ""),
                    "video_template_slug": str(details.get("video_template_slug") or ""),
                    "video_template_name": str(details.get("video_template_name") or ""),
                    "suggested_video_model": str(details.get("suggested_video_model") or ""),
                    "video_effect_name": str(details.get("video_effect_name") or ""),
                    "video_effect_risk": str(details.get("video_effect_risk") or ""),
                    "video_effect_value": str(details.get("video_effect_value") or ""),
                    "video_motion_prompt": str(details.get("video_motion_prompt") or ""),
                    "requested_voice_script": str(details.get("requested_voice_script") or ""),
                    "requested_voice_tone": str(details.get("requested_voice_tone") or ""),
                    "audio_direction": str(details.get("audio_direction") or ""),
                    "style_direction": str(details.get("style_direction") or ""),
                    "tail_rule": str(details.get("tail_rule") or ""),
                },
                "start_frame": {
                    "job_id": video_request.opening_job.id if video_request.opening_job is not None else None,
                    "asset": {
                        "id": opening_asset.id if opening_asset is not None else None,
                        "name": opening_asset.name if opening_asset is not None else "",
                        "source_path": opening_asset.source_path if opening_asset is not None else "",
                    },
                },
                "end_frame": {
                    "job_id": video_request.ending_job.id if video_request.ending_job is not None else None,
                    "required": bool(details.get("ending_card_required")),
                    "asset": {
                        "id": ending_asset.id if ending_asset is not None else None,
                        "name": ending_asset.name if ending_asset is not None else "",
                        "source_path": ending_asset.source_path if ending_asset is not None else "",
                    },
                },
                "video_job": serialize_art_studio_job(video_request.video_job),
                "video_editor_request": details.get("video_editor_request", {}),
                "instructions": [
                    "Use video-editor and Magnific MCP to generate the approved product video.",
                    "Call video_plan before video_generate unless the user explicitly requested a one-shot generation.",
                    "Pin the suggested fidelity-first model by default; change it only when video_plan validation or review requires a different supported slug.",
                    "Use the generated opening card as the first frame and the ending card only when one was required and attached.",
                    "Keep the duck inanimate and physically unchanged.",
                    "Download the generated MP4 locally and build register-video-output.json beside this file using the registration_manifest_example shape.",
                    "Register the generated video through python -m marketing_os.jobs.register_art_studio_outputs --manifest data/exports/content-automation/video-request-<id>/register-video-output.json",
                    "Do not approve, publish, or post the generated video automatically.",
                ],
                "registration_manifest_example": {
                    "outputs": [
                        {
                            "job_id": video_request.video_job.id,
                            "media_type": "product_video",
                            "output_path": _art_studio_video_output_path(video_request.request_job.id),
                            "poster_path": _art_studio_video_poster_path(video_request.request_job.id),
                            "title": f"{video_request.product.name} product video",
                            "notes": "Generated from approved Art Studio video request. Keep in human review.",
                        }
                    ]
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return target


def _planning_output_path(planned_item_id: int, option_number: int) -> str:
    root = Path(os.environ.get("MARKETING_OS_PLANNING_UPLOAD_ROOT", "outputs/graphics/planning/uploads"))
    return (root / f"planned-item-{planned_item_id}" / f"option-{option_number}.png").as_posix()


def _art_studio_social_image_output_path(job: CreativeGenerationJobRecord) -> str:
    metadata = {}
    try:
        metadata = json.loads(job.response_metadata_json or "{}")
    except json.JSONDecodeError:
        metadata = {}
    output_dir = Path(str(metadata.get("output_dir") or "outputs/graphics/social-worthy/queued"))
    option_number = int(metadata.get("option_number") or 1)
    return (output_dir / f"social-image-job-{job.id}-option-{option_number}.png").as_posix()


def _art_studio_job_product_name(job: CreativeGenerationJobRecord) -> str:
    source = job.source_asset
    product = source.product if source is not None else None
    return product.name if product is not None else "Product"


def _art_studio_video_card_output_path(request_job_id: int, card_role: str) -> str:
    root = Path(os.environ.get("MARKETING_OS_ART_STUDIO_OUTPUT_ROOT", "outputs/graphics/art-studio"))
    suffix = "opening-card.png" if card_role == "opening" else "ending-card.png"
    return (root / f"video-request-{request_job_id}" / suffix).as_posix()


def _art_studio_video_output_path(request_job_id: int) -> str:
    root = Path(os.environ.get("MARKETING_OS_ART_STUDIO_OUTPUT_ROOT", "outputs/graphics/art-studio"))
    return (root / f"video-request-{request_job_id}" / "product-video.mp4").as_posix()


def _art_studio_video_poster_path(request_job_id: int) -> str:
    root = Path(os.environ.get("MARKETING_OS_ART_STUDIO_OUTPUT_ROOT", "outputs/graphics/art-studio"))
    return (root / f"video-request-{request_job_id}" / "product-video-poster.png").as_posix()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare queued Marketing OS requests for scheduled Codex automation.")
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--business-dir", default="docs/business")
    parser.add_argument("--days-ahead", type=int, default=14)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--output-dir", default="data/exports/content-automation")
    parser.add_argument("--assets-root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    summary = run(
        db_path=args.db_path,
        business_dir=args.business_dir,
        days_ahead=args.days_ahead,
        limit=args.limit,
        output_dir=args.output_dir,
        assets_root=args.assets_root,
        dry_run=args.dry_run,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
