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
    has_rewrite_request,
    planned_items_needing_production,
    produce_content_for_item,
    serialize_planned_content_item,
)


def run(
    db_path: str | Path | None = None,
    business_dir: str = "docs/business",
    target_date: date | None = None,
    days_ahead: int | None = None,
    channel: str | None = None,
    planned_item_id: int | None = None,
    limit: int = 10,
    force: bool = False,
    dry_run: bool = False,
    export_briefs_dir: str | Path | None = None,
) -> dict[str, object]:
    engine = create_db_engine(db_path)
    init_db(engine)
    factory = session_factory(engine)
    summary: dict[str, object] = {"processed": 0, "created": 0, "skipped": 0, "items": []}
    try:
        with session_scope(factory) as session:
            production_target_date = target_date
            if production_target_date is None and days_ahead is not None:
                production_target_date = date.today() + timedelta(days=days_ahead)
            summary["filters"] = {
                "target_date": production_target_date.isoformat() if production_target_date else None,
                "days_ahead": days_ahead,
                "channel": channel,
                "planned_item_id": planned_item_id,
                "limit": limit,
                "force": force,
                "dry_run": dry_run,
                "export_briefs_dir": str(export_briefs_dir) if export_briefs_dir is not None else None,
            }
            if planned_item_id is not None:
                item = session.get(PlannedContentRecord, planned_item_id)
                items = [item] if item is not None else []
            else:
                items = planned_items_needing_production(session, target_date=production_target_date, channel=channel, limit=limit)

            for item in items:
                brief_export_path = None
                if export_briefs_dir is not None:
                    brief_export_path = str(write_content_brief(session, item, export_briefs_dir, business_dir=business_dir))
                if dry_run:
                    serialized = serialize_planned_content_item(session, item)
                    summary["items"].append(
                        {
                            "planned_item": serialized,
                            "dry_run": True,
                            "brief_export_path": brief_export_path,
                        }
                    )
                    continue
                rewrite_requested = has_rewrite_request(item)
                result = produce_content_for_item(session, item, business_dir=business_dir, force=force or rewrite_requested)
                summary["processed"] = int(summary["processed"]) + 1
                summary["created"] = int(summary["created"]) + result.created
                summary["skipped"] = int(summary["skipped"]) + result.skipped
                summary["items"].append(
                    {
                        "planned_item_id": item.id,
                        "status": item.status,
                        "brief_status": item.brief_status,
                        "candidate_ids": [candidate.id for candidate in result.candidates],
                        "brief_export_path": brief_export_path,
                        "rewrite_requested": rewrite_requested,
                        "forced": bool(force or rewrite_requested),
                    }
                )
    finally:
        engine.dispose()
    return summary


def write_content_brief(
    session: Session,
    item: PlannedContentRecord,
    export_dir: str | Path,
    business_dir: str = "docs/business",
) -> Path:
    target_dir = Path(export_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"planned-item-{item.id}-content-brief.json"
    target.write_text(json.dumps(build_content_brief(session, item, business_dir=business_dir), indent=2), encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare Codex-assisted content candidates for planned marketing items.")
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--business-dir", default="docs/business")
    parser.add_argument("--date", dest="target_date", default=None)
    parser.add_argument("--days-ahead", type=int, default=None)
    parser.add_argument("--channel", default=None)
    parser.add_argument("--planned-item-id", type=int, default=None)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--export-briefs-dir", default=None)
    args = parser.parse_args(argv)

    summary = run(
        db_path=args.db_path,
        business_dir=args.business_dir,
        target_date=date.fromisoformat(args.target_date) if args.target_date else None,
        days_ahead=args.days_ahead,
        channel=args.channel,
        planned_item_id=args.planned_item_id,
        limit=args.limit,
        force=args.force,
        dry_run=args.dry_run,
        export_briefs_dir=args.export_briefs_dir,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
