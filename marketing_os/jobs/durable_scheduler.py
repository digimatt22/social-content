from __future__ import annotations

import argparse
import hashlib
import os
import signal
import threading
from datetime import UTC, datetime

from sqlalchemy import text

from ..db import create_db_engine, init_db, session_factory, session_scope
from ..services.durable_jobs import enqueue_job


SCHEDULE_LOCK_ID = int(hashlib.sha256(b"marketing-os-scheduler").hexdigest()[:15], 16)


def emit_due_jobs(factory, now: datetime | None = None) -> int:
    checked_at = now or datetime.now(UTC).replace(tzinfo=None)
    slot = checked_at.replace(minute=0, second=0, microsecond=0)
    with session_scope(factory) as session:
        if session.bind.dialect.name == "postgresql":
            locked = session.scalar(text("SELECT pg_try_advisory_xact_lock(:lock_id)"), {"lock_id": SCHEDULE_LOCK_ID})
            if not locked:
                return 0
        emitted = 0
        _, created = enqueue_job(
            session,
            job_type="system.noop",
            payload={"scheduled_slot": slot.isoformat()},
            idempotency_key=f"system.noop:{slot.isoformat()}",
            correlation_id=f"scheduler:{slot.isoformat()}",
        )
        emitted += int(created)
        current_date = checked_at.date().isoformat()
        if (checked_at.hour, checked_at.minute) >= (2, 10):
            for job_type in ("catalog.reconcile", "editorial.reconcile"):
                _, created = enqueue_job(
                    session,
                    job_type=job_type,
                    payload={"utc_date": current_date},
                    idempotency_key=f"{job_type}:{current_date}",
                    correlation_id=f"daily:{current_date}",
                )
                emitted += int(created)
        if (checked_at.hour, checked_at.minute) >= (3, 10):
            _, created = enqueue_job(
                session,
                job_type="shadow.generate",
                payload={"utc_date": current_date, "trigger": "daily"},
                idempotency_key=f"shadow.generate:{current_date}",
                correlation_id=f"shadow:{current_date}",
            )
            emitted += int(created)
        if checked_at.weekday() == 0 and (checked_at.hour, checked_at.minute) >= (9, 10):
            _, created = enqueue_job(
                session,
                job_type="shadow.digest",
                payload={"utc_week": current_date, "trigger": "weekly"},
                idempotency_key=f"shadow.digest:{current_date}",
                correlation_id=f"shadow-digest:{current_date}",
            )
            emitted += int(created)
        measurement_slot = checked_at.replace(
            minute=(checked_at.minute // 15) * 15,
            second=0,
            microsecond=0,
        )
        _, created = enqueue_job(
            session,
            job_type="measurement.ingest",
            payload={"scheduled_slot": measurement_slot.isoformat()},
            idempotency_key=f"measurement.ingest:{measurement_slot.isoformat()}",
            correlation_id=f"measurement:{measurement_slot.isoformat()}",
        )
        emitted += int(created)
        return emitted


def run_scheduler(*, once: bool = False, interval_seconds: float = 60.0) -> int:
    engine = create_db_engine()
    init_db(engine)
    factory = session_factory(engine)
    stopping = threading.Event()

    def request_stop(_signum, _frame) -> None:
        stopping.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    try:
        while not stopping.is_set():
            emit_due_jobs(factory)
            if once:
                return 0
            stopping.wait(interval_seconds)
    finally:
        engine.dispose()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the durable Marketing OS scheduler")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    args = parser.parse_args(argv)
    return run_scheduler(once=args.once, interval_seconds=args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
