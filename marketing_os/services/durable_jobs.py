from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db_models import AuditEventRecord, AutomationJobRecord, AutomationRunRecord, PrincipalRecord


ACTIVE_JOB_STATES = {"queued", "retry_wait", "leased", "running"}
TERMINAL_JOB_STATES = {"succeeded", "dead_letter", "quarantined", "cancelled"}


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _json(value: dict[str, Any] | None) -> str:
    return json.dumps(value or {}, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class ClaimedJob:
    id: int
    run_id: int | None
    job_type: str
    schema_version: int
    payload: dict[str, Any]
    attempt_count: int
    max_attempts: int
    correlation_id: str


def create_run(
    session: Session,
    *,
    run_type: str,
    trigger_type: str,
    correlation_id: str,
    input_revision: str = "",
) -> AutomationRunRecord:
    run = AutomationRunRecord(
        run_type=run_type,
        trigger_type=trigger_type,
        correlation_id=correlation_id,
        input_revision=input_revision,
    )
    session.add(run)
    session.flush()
    return run


def enqueue_job(
    session: Session,
    *,
    job_type: str,
    payload: dict[str, Any] | None = None,
    schema_version: int = 1,
    priority: int = 100,
    scheduled_at: datetime | None = None,
    max_attempts: int = 3,
    idempotency_key: str | None = None,
    correlation_id: str = "",
    run_id: int | None = None,
) -> tuple[AutomationJobRecord, bool]:
    if not job_type.strip():
        raise ValueError("job_type is required")
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    if idempotency_key:
        existing = session.scalar(
            select(AutomationJobRecord).where(AutomationJobRecord.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return existing, False

    job = AutomationJobRecord(
        run_id=run_id,
        job_type=job_type.strip(),
        schema_version=schema_version,
        payload_json=_json(payload),
        priority=priority,
        scheduled_at=scheduled_at or _utc_now(),
        max_attempts=max_attempts,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
    )
    session.add(job)
    try:
        with session.begin_nested():
            session.flush()
    except IntegrityError:
        if not idempotency_key:
            raise
        existing = session.scalar(
            select(AutomationJobRecord).where(AutomationJobRecord.idempotency_key == idempotency_key)
        )
        if existing is None:
            raise
        return existing, False
    return job, True


def claim_next_job(
    session: Session,
    *,
    worker_id: str,
    lease_seconds: int = 120,
    now: datetime | None = None,
) -> ClaimedJob | None:
    if not worker_id.strip():
        raise ValueError("worker_id is required")
    if lease_seconds < 1:
        raise ValueError("lease_seconds must be positive")

    checked_at = now or _utc_now()
    statement = (
        select(AutomationJobRecord)
        .where(
            AutomationJobRecord.state.in_(("queued", "retry_wait")),
            AutomationJobRecord.scheduled_at <= checked_at,
            or_(AutomationJobRecord.next_retry_at.is_(None), AutomationJobRecord.next_retry_at <= checked_at),
        )
        .order_by(AutomationJobRecord.priority.asc(), AutomationJobRecord.scheduled_at.asc(), AutomationJobRecord.id.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    job = session.scalar(statement)
    if job is None:
        return None

    job.state = "leased"
    job.lease_owner = worker_id
    job.lease_expires_at = checked_at + timedelta(seconds=lease_seconds)
    job.heartbeat_at = checked_at
    job.attempt_count += 1
    session.flush()
    return ClaimedJob(
        id=job.id,
        run_id=job.run_id,
        job_type=job.job_type,
        schema_version=job.schema_version,
        payload=json.loads(job.payload_json or "{}"),
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
        correlation_id=job.correlation_id,
    )


def mark_running(session: Session, *, job_id: int, worker_id: str) -> AutomationJobRecord:
    job = _owned_job(session, job_id=job_id, worker_id=worker_id)
    job.state = "running"
    session.flush()
    return job


def heartbeat_job(
    session: Session,
    *,
    job_id: int,
    worker_id: str,
    lease_seconds: int = 120,
    now: datetime | None = None,
) -> AutomationJobRecord:
    checked_at = now or _utc_now()
    job = _owned_job(session, job_id=job_id, worker_id=worker_id)
    if job.lease_expires_at is not None and job.lease_expires_at < checked_at:
        raise RuntimeError("job lease has expired")
    job.heartbeat_at = checked_at
    job.lease_expires_at = checked_at + timedelta(seconds=lease_seconds)
    session.flush()
    return job


def succeed_job(
    session: Session,
    *,
    job_id: int,
    worker_id: str,
    result: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> AutomationJobRecord:
    job = _owned_job(session, job_id=job_id, worker_id=worker_id)
    job.state = "succeeded"
    job.result_json = _json(result)
    job.completed_at = now or _utc_now()
    _clear_lease(job)
    session.flush()
    return job


def fail_job(
    session: Session,
    *,
    job_id: int,
    worker_id: str,
    error_code: str,
    error_message: str,
    retryable: bool,
    ambiguous_external_write: bool = False,
    base_delay_seconds: int = 30,
    now: datetime | None = None,
) -> AutomationJobRecord:
    checked_at = now or _utc_now()
    job = _owned_job(session, job_id=job_id, worker_id=worker_id)
    job.last_error_code = error_code[:120]
    job.last_error = error_message
    _clear_lease(job)

    if ambiguous_external_write:
        job.state = "quarantined"
        job.completed_at = checked_at
    elif retryable and job.attempt_count < job.max_attempts:
        job.state = "retry_wait"
        job.next_retry_at = checked_at + timedelta(
            seconds=_retry_delay(base_delay_seconds, job.attempt_count, job.id)
        )
    else:
        job.state = "dead_letter"
        job.completed_at = checked_at
    session.flush()
    return job


def reclaim_expired_leases(session: Session, *, now: datetime | None = None) -> tuple[int, int]:
    checked_at = now or _utc_now()
    jobs = list(
        session.scalars(
            select(AutomationJobRecord)
            .where(
                AutomationJobRecord.state.in_(("leased", "running")),
                AutomationJobRecord.lease_expires_at.is_not(None),
                AutomationJobRecord.lease_expires_at < checked_at,
            )
            .with_for_update(skip_locked=True)
        )
    )
    requeued = 0
    dead_lettered = 0
    for job in jobs:
        job.last_error_code = "lease_expired"
        job.last_error = "Worker lease expired before completion."
        _clear_lease(job)
        if job.attempt_count < job.max_attempts:
            job.state = "queued"
            job.next_retry_at = checked_at
            requeued += 1
        else:
            job.state = "dead_letter"
            job.completed_at = checked_at
            dead_lettered += 1
    session.flush()
    return requeued, dead_lettered


def replay_dead_letter(
    session: Session,
    *,
    job_id: int,
    principal_id: int,
    reason: str,
    now: datetime | None = None,
) -> AutomationJobRecord:
    _require_job_control(session, principal_id, "automation_job_replay_denied", job_id, reason)
    job = session.get(AutomationJobRecord, job_id)
    if job is None:
        raise LookupError(f"job {job_id} was not found")
    if job.state not in {"dead_letter", "quarantined"}:
        raise ValueError("only dead-lettered or quarantined jobs can be replayed")
    if not reason.strip():
        raise ValueError("replay reason is required")

    job.state = "queued"
    job.attempt_count = 0
    job.next_retry_at = now or _utc_now()
    job.completed_at = None
    job.last_error_code = ""
    job.last_error = ""
    _clear_lease(job)
    _audit(
        session,
        principal_id=principal_id,
        event_type="automation_job_replayed",
        target_type="automation_job",
        target_id=str(job.id),
        detail={"reason": reason},
    )
    session.flush()
    return job


def cancel_job(
    session: Session,
    *,
    job_id: int,
    principal_id: int,
    reason: str,
    now: datetime | None = None,
) -> AutomationJobRecord:
    _require_job_control(session, principal_id, "automation_job_cancel_denied", job_id, reason)
    job = session.get(AutomationJobRecord, job_id)
    if job is None:
        raise LookupError(f"job {job_id} was not found")
    if job.state in TERMINAL_JOB_STATES:
        raise ValueError(f"job is already terminal: {job.state}")
    if not reason.strip():
        raise ValueError("cancellation reason is required")
    job.state = "cancelled"
    job.completed_at = now or _utc_now()
    _clear_lease(job)
    _audit(
        session,
        principal_id=principal_id,
        event_type="automation_job_cancelled",
        target_type="automation_job",
        target_id=str(job.id),
        detail={"reason": reason},
    )
    session.flush()
    return job


def reconcile_run(session: Session, run_id: int, *, now: datetime | None = None) -> AutomationRunRecord:
    run = session.get(AutomationRunRecord, run_id)
    if run is None:
        raise LookupError(f"run {run_id} was not found")
    counts = dict(
        session.execute(
            select(AutomationJobRecord.state, func.count(AutomationJobRecord.id))
            .where(AutomationJobRecord.run_id == run_id)
            .group_by(AutomationJobRecord.state)
        ).all()
    )
    run.queued_count = sum(counts.get(state, 0) for state in ("queued", "retry_wait", "leased", "running"))
    run.succeeded_count = counts.get("succeeded", 0)
    run.failed_count = counts.get("cancelled", 0)
    run.dead_letter_count = counts.get("dead_letter", 0) + counts.get("quarantined", 0)
    if run.queued_count == 0:
        run.state = "failed" if run.dead_letter_count or run.failed_count else "succeeded"
        run.completed_at = now or _utc_now()
    session.flush()
    return run


def _owned_job(session: Session, *, job_id: int, worker_id: str) -> AutomationJobRecord:
    job = session.get(AutomationJobRecord, job_id)
    if job is None:
        raise LookupError(f"job {job_id} was not found")
    if job.state not in {"leased", "running"} or job.lease_owner != worker_id:
        raise RuntimeError("job is not leased by this worker")
    return job


def _clear_lease(job: AutomationJobRecord) -> None:
    job.lease_owner = ""
    job.lease_expires_at = None
    job.heartbeat_at = None


def _retry_delay(base_seconds: int, attempt_count: int, job_id: int) -> int:
    capped = min(base_seconds * (2 ** max(attempt_count - 1, 0)), 3600)
    seed = int(hashlib.sha256(f"{job_id}:{attempt_count}".encode()).hexdigest()[:8], 16)
    return capped + random.Random(seed).randint(0, max(base_seconds, 1))


def _audit(
    session: Session,
    *,
    principal_id: int | None,
    event_type: str,
    target_type: str,
    target_id: str,
    detail: dict[str, Any],
) -> None:
    session.add(
        AuditEventRecord(
            principal_id=principal_id,
            event_type=event_type,
            outcome="success",
            target_type=target_type,
            target_id=target_id,
            detail_json=_json(detail),
        )
    )


def _require_job_control(
    session: Session,
    principal_id: int,
    denied_event: str,
    job_id: int,
    reason: str,
) -> None:
    principal = session.get(PrincipalRecord, principal_id)
    roles = set(json.loads(principal.roles_json)) if principal is not None else set()
    if principal is not None and principal.active and "admin" in roles:
        return
    _audit(
        session,
        principal_id=principal.id if principal is not None else None,
        event_type=denied_event,
        target_type="automation_job",
        target_id=str(job_id),
        detail={"reason": reason, "required_role": "admin"},
    )
    session.flush()
    raise PermissionError("admin role is required for job replay or cancellation")
