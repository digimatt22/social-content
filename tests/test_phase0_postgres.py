from __future__ import annotations

import os
import threading
import tempfile
import unittest

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from marketing_os.db import session_factory
from marketing_os.db_models import Base, ProductRecord
from marketing_os.jobs.migrate_sqlite_to_postgres import migrate
from marketing_os.services.durable_jobs import claim_next_job, enqueue_job


POSTGRES_URL = os.environ.get("MARKETING_OS_TEST_POSTGRES_URL", "")


@unittest.skipUnless(POSTGRES_URL, "MARKETING_OS_TEST_POSTGRES_URL is not configured")
class Phase0PostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(POSTGRES_URL, future=True)
        original = os.environ.get("MARKETING_OS_DB_URL")
        os.environ["MARKETING_OS_DB_URL"] = POSTGRES_URL
        try:
            command.upgrade(Config("alembic.ini"), "head")
        finally:
            if original is None:
                os.environ.pop("MARKETING_OS_DB_URL", None)
            else:
                os.environ["MARKETING_OS_DB_URL"] = original
        cls.factory = session_factory(cls.engine)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()

    def setUp(self) -> None:
        with self.engine.begin() as connection:
            table_names = ", ".join(f'"{table.name}"' for table in reversed(Base.metadata.sorted_tables))
            connection.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))

    def test_two_workers_do_not_claim_the_same_job(self) -> None:
        with self.factory.begin() as session:
            job, _ = enqueue_job(session, job_type="system.noop")
            job_id = job.id
        barrier = threading.Barrier(2)
        results: list[int | None] = []

        def claim(worker_id: str) -> None:
            with self.factory.begin() as session:
                barrier.wait()
                claimed = claim_next_job(session, worker_id=worker_id)
                results.append(claimed.id if claimed else None)

        workers = [threading.Thread(target=claim, args=(f"worker-{index}",)) for index in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=10)
        self.assertEqual(1, results.count(job_id))
        self.assertEqual(1, results.count(None))

    def test_concurrent_idempotent_enqueues_return_one_job(self) -> None:
        barrier = threading.Barrier(2)
        results: list[tuple[int, bool]] = []

        def enqueue() -> None:
            with self.factory.begin() as session:
                barrier.wait()
                job, created = enqueue_job(
                    session,
                    job_type="system.noop",
                    idempotency_key="concurrent:one",
                )
                results.append((job.id, created))

        workers = [threading.Thread(target=enqueue) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=10)
        self.assertEqual(1, len({job_id for job_id, _ in results}))
        self.assertEqual([False, True], sorted(created for _, created in results))

    def test_cutover_advances_postgresql_sequences(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            source = create_engine(f"sqlite:///{tempdir}/source.sqlite", future=True)
            Base.metadata.create_all(source)
            with source.begin() as connection:
                connection.execute(
                    ProductRecord.__table__.insert(),
                    {
                        "id": 41,
                        "name": "Sequence source",
                        "secondary_audiences_json": "[]",
                        "best_channels_json": "[]",
                        "use_cases_json": "[]",
                        "seasonality_json": "[]",
                        "sales_momentum_note": "",
                        "external_source": "etsy",
                        "external_id": "sequence-41",
                        "canonical_url": "",
                        "sync_status": "synced",
                        "sync_error": "",
                        "staleness_state": "fresh",
                        "manual_override_state": "",
                        "manual_override_note": "",
                    },
                )
            migrate(source, self.engine)
            source.dispose()
        with self.factory.begin() as session:
            created = ProductRecord(name="After cutover")
            session.add(created)
            session.flush()
            self.assertGreater(created.id, 41)


if __name__ == "__main__":
    unittest.main()
