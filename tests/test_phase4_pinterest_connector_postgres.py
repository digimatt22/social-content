from __future__ import annotations

import os
import tempfile
import threading
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text

from marketing_os.db import session_factory
from marketing_os.db_models import (
    AutomationJobRecord,
    Base,
    PinterestConnectionRecord,
    PinterestPublicationRecord,
    PinterestPublishAttemptRecord,
)
from marketing_os.services.pinterest_connector import (
    FixturePinterestProvider,
    PublishInProgressError,
    claim_publish,
    grant_fixture_authority,
    prepare_publication,
)
from tests import test_phase4_pinterest_connector as phase4_fixture


POSTGRES_URL = os.environ.get("MARKETING_OS_TEST_POSTGRES_URL", "")


@unittest.skipUnless(POSTGRES_URL, "MARKETING_OS_TEST_POSTGRES_URL is not configured")
class PinterestConnectorPostgresTests(unittest.TestCase):
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
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tempdir.name)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()
        cls.tempdir.cleanup()

    def setUp(self) -> None:
        with self.engine.begin() as connection:
            tables = ", ".join(f'"{table.name}"' for table in reversed(Base.metadata.sorted_tables))
            connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        helper = phase4_fixture.PinterestConnectorTests(
            methodName="test_default_publish_profile_is_hard_disabled_and_value_validated"
        )
        helper.factory = self.factory
        helper.root = self.root
        self.shadow_id, self.connection_id, self.admin_id = helper._seed()

    def _grant(self) -> None:
        with self.factory.begin() as session:
            grant_fixture_authority(
                session,
                connection=session.get(PinterestConnectionRecord, self.connection_id),
                principal_id=self.admin_id,
                policy_class="sampled_low_risk_static_pin",
                expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1),
                reason="PostgreSQL concurrency fixture.",
            )

    def test_concurrent_prepare_converges_on_one_publication(self) -> None:
        barrier = threading.Barrier(2)
        results: list[int] = []
        errors: list[Exception] = []

        def prepare() -> None:
            try:
                with self.factory.begin() as session:
                    barrier.wait()
                    publication = prepare_publication(
                        session,
                        shadow_publication_id=self.shadow_id,
                        connection_id=self.connection_id,
                        board_id="board-mail-carrier",
                    )
                    results.append(publication.id)
            except Exception as exc:
                errors.append(exc)

        workers = [threading.Thread(target=prepare) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=15)
        self.assertEqual([], errors)
        self.assertEqual(1, len(set(results)))
        with self.factory() as session:
            self.assertEqual(
                1,
                session.scalar(select(func.count()).select_from(PinterestPublicationRecord)),
            )

    def test_concurrent_claim_allows_one_submit_and_quarantines_the_race(self) -> None:
        with self.factory.begin() as session:
            publication = prepare_publication(
                session,
                shadow_publication_id=self.shadow_id,
                connection_id=self.connection_id,
                board_id="board-mail-carrier",
            )
            publication_id = publication.id
        self._grant()
        barrier = threading.Barrier(2)
        outcomes: list[str] = []

        def claim() -> None:
            try:
                with self.factory.begin() as session:
                    barrier.wait()
                    _, attempt, _ = claim_publish(
                        session,
                        publication_id=publication_id,
                        policy_class="sampled_low_risk_static_pin",
                        provider=FixturePinterestProvider(),
                    )
                outcomes.append("claimed" if attempt is not None else "quarantined")
            except PublishInProgressError:
                outcomes.append("in_progress")

        workers = [threading.Thread(target=claim) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=15)
        self.assertEqual(["claimed", "in_progress"], sorted(outcomes))
        with self.factory() as session:
            publication = session.get(PinterestPublicationRecord, publication_id)
            self.assertEqual("submitted", publication.lifecycle_state)
            self.assertEqual(
                1,
                session.scalar(select(func.count()).select_from(PinterestPublishAttemptRecord)),
            )
            self.assertEqual(
                0,
                session.scalar(
                    select(func.count())
                    .select_from(AutomationJobRecord)
                    .where(AutomationJobRecord.job_type == "pinterest.reconcile")
                ),
            )


if __name__ == "__main__":
    unittest.main()
