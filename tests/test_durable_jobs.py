from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from marketing_os.db import create_db_engine, init_db, session_factory
from marketing_os.db_models import AuditEventRecord, AutomationJobRecord, PrincipalRecord
from marketing_os.services.durable_jobs import (
    cancel_job,
    claim_next_job,
    enqueue_job,
    fail_job,
    heartbeat_job,
    mark_running,
    reclaim_expired_leases,
    replay_dead_letter,
    succeed_job,
)


class DurableJobTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tempdir.name) / "jobs.sqlite"
        self.engine = create_db_engine(db_path)
        init_db(self.engine)
        self.factory = session_factory(self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tempdir.cleanup()

    def test_enqueue_is_idempotent(self) -> None:
        with self.factory.begin() as session:
            first, created = enqueue_job(
                session,
                job_type="catalog.reconcile",
                payload={"product_id": 12},
                idempotency_key="catalog:12:v1",
            )
            duplicate, duplicate_created = enqueue_job(
                session,
                job_type="catalog.reconcile",
                payload={"product_id": 12},
                idempotency_key="catalog:12:v1",
            )
            self.assertTrue(created)
            self.assertFalse(duplicate_created)
            self.assertEqual(first.id, duplicate.id)

    def test_claim_heartbeat_and_success_require_lease_owner(self) -> None:
        now = datetime(2026, 7, 24, 12, 0, 0)
        with self.factory.begin() as session:
            job, _ = enqueue_job(session, job_type="health.test", scheduled_at=now)
            job_id = job.id

        with self.factory.begin() as session:
            claimed = claim_next_job(session, worker_id="worker-a", lease_seconds=30, now=now)
            self.assertIsNotNone(claimed)
            self.assertEqual(job_id, claimed.id)
            with self.assertRaises(RuntimeError):
                heartbeat_job(session, job_id=job_id, worker_id="worker-b", now=now)
            mark_running(session, job_id=job_id, worker_id="worker-a")
            heartbeat = heartbeat_job(
                session,
                job_id=job_id,
                worker_id="worker-a",
                lease_seconds=60,
                now=now + timedelta(seconds=5),
            )
            self.assertEqual(now + timedelta(seconds=65), heartbeat.lease_expires_at)
            succeeded = succeed_job(
                session,
                job_id=job_id,
                worker_id="worker-a",
                result={"ok": True},
                now=now + timedelta(seconds=10),
            )
            self.assertEqual("succeeded", succeeded.state)
            self.assertEqual("", succeeded.lease_owner)

    def test_retryable_non_retryable_and_ambiguous_failures(self) -> None:
        now = datetime(2026, 7, 24, 12, 0, 0)
        with self.factory.begin() as session:
            retry_job, _ = enqueue_job(session, job_type="retry", max_attempts=3, scheduled_at=now)
            retry_id = retry_job.id
        with self.factory.begin() as session:
            claim_next_job(session, worker_id="worker", now=now)
            failed = fail_job(
                session,
                job_id=retry_id,
                worker_id="worker",
                error_code="provider_timeout",
                error_message="temporary",
                retryable=True,
                now=now,
            )
            self.assertEqual("retry_wait", failed.state)
            self.assertGreater(failed.next_retry_at, now)

        with self.factory.begin() as session:
            invalid, _ = enqueue_job(session, job_type="invalid", scheduled_at=now)
            invalid_id = invalid.id
        with self.factory.begin() as session:
            claim_next_job(session, worker_id="worker", now=now)
            failed = fail_job(
                session,
                job_id=invalid_id,
                worker_id="worker",
                error_code="validation_error",
                error_message="invalid payload",
                retryable=False,
                now=now,
            )
            self.assertEqual("dead_letter", failed.state)

        with self.factory.begin() as session:
            ambiguous, _ = enqueue_job(session, job_type="publish", scheduled_at=now)
            ambiguous_id = ambiguous.id
        with self.factory.begin() as session:
            claim_next_job(session, worker_id="worker", now=now)
            failed = fail_job(
                session,
                job_id=ambiguous_id,
                worker_id="worker",
                error_code="response_lost",
                error_message="provider response was ambiguous",
                retryable=True,
                ambiguous_external_write=True,
                now=now,
            )
            self.assertEqual("quarantined", failed.state)

    def test_expired_lease_requeues_then_dead_letters(self) -> None:
        now = datetime(2026, 7, 24, 12, 0, 0)
        with self.factory.begin() as session:
            retry_job, _ = enqueue_job(session, job_type="retry", max_attempts=2, scheduled_at=now)
            dead_job, _ = enqueue_job(session, job_type="dead", max_attempts=1, scheduled_at=now)
            retry_id = retry_job.id
            dead_id = dead_job.id

        with self.factory.begin() as session:
            retry = session.get(AutomationJobRecord, retry_id)
            retry.state = "running"
            retry.attempt_count = 1
            retry.lease_owner = "gone-a"
            retry.lease_expires_at = now - timedelta(seconds=1)
            dead = session.get(AutomationJobRecord, dead_id)
            dead.state = "leased"
            dead.attempt_count = 1
            dead.lease_owner = "gone-b"
            dead.lease_expires_at = now - timedelta(seconds=1)

        with self.factory.begin() as session:
            requeued, dead_lettered = reclaim_expired_leases(session, now=now)
            self.assertEqual((1, 1), (requeued, dead_lettered))
            self.assertEqual("queued", session.get(AutomationJobRecord, retry_id).state)
            self.assertEqual("dead_letter", session.get(AutomationJobRecord, dead_id).state)

    def test_replay_and_cancel_are_audited(self) -> None:
        now = datetime(2026, 7, 24, 12, 0, 0)
        with self.factory.begin() as session:
            principal = PrincipalRecord(
                principal_type="human",
                username="admin",
                roles_json='["admin"]',
            )
            session.add(principal)
            session.flush()
            principal_id = principal.id
            dead, _ = enqueue_job(session, job_type="dead", scheduled_at=now)
            dead.state = "dead_letter"
            queued, _ = enqueue_job(session, job_type="queued", scheduled_at=now)
            dead_id = dead.id
            queued_id = queued.id

        with self.factory.begin() as session:
            replayed = replay_dead_letter(
                session,
                job_id=dead_id,
                principal_id=principal_id,
                reason="configuration fixed",
                now=now,
            )
            cancelled = cancel_job(
                session,
                job_id=queued_id,
                principal_id=principal_id,
                reason="superseded",
                now=now,
            )
            self.assertEqual("queued", replayed.state)
            self.assertEqual("cancelled", cancelled.state)

        with self.factory() as session:
            event_types = list(session.scalars(select(AuditEventRecord.event_type).order_by(AuditEventRecord.id)))
            self.assertEqual(
                ["automation_job_replayed", "automation_job_cancelled"],
                event_types,
            )


if __name__ == "__main__":
    unittest.main()
