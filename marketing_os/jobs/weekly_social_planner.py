from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from sqlalchemy import select

from ..db import create_db_engine, init_db, session_factory, session_scope
from ..db_models import SyncMetadata, utc_now
from ..services.weekly_social_planner import build_weekly_social_plan, next_monday


def run(
    db_path: str | Path | None = None,
    business_dir: str = "docs/business",
    week_start: date | None = None,
    output_dir: str | Path = "data/exports/weekly-social-plans",
    slots: int = 7,
    dry_run: bool = False,
    sales_lookback_days: int = 90,
) -> dict[str, object]:
    engine = create_db_engine(db_path)
    init_db(engine)
    factory = session_factory(engine)
    try:
        with session_scope(factory) as session:
            result = build_weekly_social_plan(
                session,
                week_start=week_start or next_monday(),
                business_dir=business_dir,
                output_dir=output_dir,
                slots=slots,
                dry_run=dry_run,
                sales_lookback_days=sales_lookback_days,
            )
            _record_automation_run(session, "weekly_social_planner", output_dir, result.__dict__)
            return result.__dict__
    finally:
        engine.dispose()


def _record_automation_run(session, source_name: str, source_path: str | Path, summary: dict[str, object]) -> None:
    record = session.scalar(select(SyncMetadata).where(SyncMetadata.source_name == source_name))
    if record is None:
        record = SyncMetadata(source_name=source_name, source_path=str(source_path), notes="")
        session.add(record)
    record.source_path = str(source_path)
    record.synced_at = utc_now()
    record.notes = json.dumps(
        {
            "created": summary.get("created", 0),
            "skipped": summary.get("skipped", 0),
            "dry_run": summary.get("dry_run", False),
            "week_start": str(summary.get("week_start", "")),
            "sales_source": summary.get("sales_source", ""),
        },
        sort_keys=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a weekly social media plan for human-reviewed Marketing OS Planning.")
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--business-dir", default="docs/business")
    parser.add_argument("--week-start", default=None, help="Monday date for the planned week, YYYY-MM-DD. Defaults to the next Monday.")
    parser.add_argument("--output-dir", default="data/exports/weekly-social-plans")
    parser.add_argument("--slots", type=int, default=7)
    parser.add_argument("--sales-lookback-days", type=int, default=90)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    print(
        json.dumps(
            run(
                db_path=args.db_path,
                business_dir=args.business_dir,
                week_start=date.fromisoformat(args.week_start) if args.week_start else None,
                output_dir=args.output_dir,
                slots=args.slots,
                dry_run=args.dry_run,
                sales_lookback_days=args.sales_lookback_days,
            ),
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
