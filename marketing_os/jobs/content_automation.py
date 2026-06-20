from __future__ import annotations

import argparse
import json
import os
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy.orm import Session
from sqlalchemy import select

from ..db import create_db_engine, init_db, session_factory, session_scope
from ..db_models import PlannedContentRecord, SyncMetadata, utc_now
from ..services.content_briefs import (
    build_content_brief,
    has_copy_rewrite_request,
    localize_planned_content_reference_assets,
    planned_items_needing_production,
    produce_content_for_item,
    serialize_planned_content_item,
)
from ..services.skill_adapters import image_option_from_contract, social_copy_workflow_contract, social_media_art_director_contracts


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


def _planning_output_path(planned_item_id: int, option_number: int) -> str:
    root = Path(os.environ.get("MARKETING_OS_PLANNING_UPLOAD_ROOT", "outputs/graphics/planning/uploads"))
    return (root / f"planned-item-{planned_item_id}" / f"option-{option_number}.png").as_posix()


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
