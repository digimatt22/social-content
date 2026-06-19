from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from ..db import create_db_engine, init_db, session_factory, session_scope
from ..db_models import PlannedContentRecord
from ..services.content_briefs import (
    build_content_brief,
    has_copy_rewrite_request,
    planned_items_needing_production,
    produce_content_for_item,
    serialize_planned_content_item,
)
from ..services.skill_adapters import image_creator_contracts, image_option_from_contract


IMAGE_QUEUE_STATUSES = {"waiting_content_generation", "waiting_image_generation", "waiting_image_regeneration"}


def run(
    db_path: str | Path | None = None,
    business_dir: str = "docs/business",
    days_ahead: int = 14,
    limit: int = 10,
    output_dir: str | Path = "data/exports/content-automation",
    dry_run: bool = False,
) -> dict[str, object]:
    engine = create_db_engine(db_path)
    init_db(engine)
    factory = session_factory(engine)
    target_date = date.today() + timedelta(days=days_ahead)
    summary: dict[str, object] = {
        "processed": 0,
        "copy_created": 0,
        "copy_skipped": 0,
        "image_request_files": [],
        "items": [],
        "filters": {
            "days_ahead": days_ahead,
            "target_date": target_date.isoformat(),
            "limit": limit,
            "dry_run": dry_run,
            "output_dir": str(output_dir),
        },
    }
    try:
        with session_scope(factory) as session:
            items = planned_items_needing_production(session, target_date=target_date, limit=limit)
            for item in items:
                item_summary = _prepare_item(session, item, business_dir, output_dir, dry_run)
                summary["items"].append(item_summary)
                if not dry_run:
                    summary["processed"] = int(summary["processed"]) + 1
                    summary["copy_created"] = int(summary["copy_created"]) + int(item_summary.get("copy_created", 0))
                    summary["copy_skipped"] = int(summary["copy_skipped"]) + int(item_summary.get("copy_skipped", 0))
                if item_summary.get("image_request_path"):
                    summary["image_request_files"].append(item_summary["image_request_path"])
    finally:
        engine.dispose()
    return summary


def _prepare_item(
    session: Session,
    item: PlannedContentRecord,
    business_dir: str,
    output_dir: str | Path,
    dry_run: bool,
) -> dict[str, object]:
    copy_created = 0
    copy_skipped = 0
    forced = has_copy_rewrite_request(item)
    if not dry_run:
        result = produce_content_for_item(session, item, business_dir=business_dir, force=forced)
        copy_created = result.created
        copy_skipped = result.skipped

    image_request_path = ""
    image_request_count = 0
    if item.status in IMAGE_QUEUE_STATUSES:
        image_request_path = str(write_image_requests(session, item, output_dir, business_dir=business_dir))
        image_request_count = 3

    return {
        "planned_item_id": item.id,
        "status": item.status,
        "brief_status": item.brief_status,
        "copy_created": copy_created,
        "copy_skipped": copy_skipped,
        "forced": forced,
        "image_request_count": image_request_count,
        "image_request_path": image_request_path,
        "planned_item": serialize_planned_content_item(session, item),
    }


def write_image_requests(
    session: Session,
    item: PlannedContentRecord,
    output_dir: str | Path,
    business_dir: str = "docs/business",
) -> Path:
    brief = build_content_brief(session, item, business_dir=business_dir)
    contracts = image_creator_contracts(brief, count=3)
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
                            "image_path": option.get("output_path") or f"outputs/graphics/planning/planned-item-{item.id}/option-{option['option_number']}.png",
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare queued Marketing OS requests for scheduled Codex automation.")
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--business-dir", default="docs/business")
    parser.add_argument("--days-ahead", type=int, default=14)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--output-dir", default="data/exports/content-automation")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    summary = run(
        db_path=args.db_path,
        business_dir=args.business_dir,
        days_ahead=args.days_ahead,
        limit=args.limit,
        output_dir=args.output_dir,
        dry_run=args.dry_run,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
