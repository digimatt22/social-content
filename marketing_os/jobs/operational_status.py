from __future__ import annotations

import argparse
import json
from datetime import timedelta

from sqlalchemy import func, select

from ..db import create_db_engine, init_db, session_factory
from ..db_models import AutomationJobRecord, DemandEvidenceRecord, utc_now


def collect_status(factory, *, stale_hours: int = 48) -> dict:
    now = utc_now()
    with factory() as session:
        job_counts = dict(
            session.execute(
                select(AutomationJobRecord.state, func.count(AutomationJobRecord.id)).group_by(AutomationJobRecord.state)
            ).all()
        )
        oldest_due = session.scalar(
            select(func.min(AutomationJobRecord.scheduled_at)).where(
                AutomationJobRecord.state.in_(("queued", "retry_wait"))
            )
        )
        stale_evidence = session.scalar(
            select(func.count(DemandEvidenceRecord.id)).where(
                (DemandEvidenceRecord.source_timestamp.is_(None))
                | (DemandEvidenceRecord.source_timestamp < now - timedelta(hours=stale_hours))
            )
        )
    queue_lag_seconds = max(int((now - oldest_due).total_seconds()), 0) if oldest_due else 0
    unhealthy = bool(job_counts.get("dead_letter") or job_counts.get("quarantined"))
    return {
        "status": "attention_required" if unhealthy else "ok",
        "job_counts": job_counts,
        "queue_lag_seconds": queue_lag_seconds,
        "stale_or_undated_evidence": int(stale_evidence or 0),
        "checked_at": now.isoformat(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit machine-readable Marketing OS operational status")
    parser.add_argument("--stale-hours", type=int, default=48)
    parser.add_argument("--fail-on-attention", action="store_true")
    args = parser.parse_args(argv)
    engine = create_db_engine()
    init_db(engine)
    try:
        report = collect_status(session_factory(engine), stale_hours=args.stale_hours)
    finally:
        engine.dispose()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2 if args.fail_on_attention and report["status"] != "ok" else 0


if __name__ == "__main__":
    raise SystemExit(main())
