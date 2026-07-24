from __future__ import annotations

import os
import threading
import unittest

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text

from marketing_os.db import session_factory
from marketing_os.db_models import (
    AutomationJobRecord,
    Base,
    CatalogChangeRecord,
    CatalogSnapshotRecord,
    CoverageOutcomeRecord,
    GrowthEventRecord,
    MeasurementCursorRecord,
    ProductIdentityRecord,
    ProductRecord,
    utc_now,
)
from marketing_os.services.coverage_intelligence import (
    accept_catalog_snapshot,
    ingest_measurement_page,
    materialize_product_coverage,
    reconcile_editorial_snapshot,
    seed_taxonomy,
)


POSTGRES_URL = os.environ.get("MARKETING_OS_TEST_POSTGRES_URL", "")


@unittest.skipUnless(POSTGRES_URL, "MARKETING_OS_TEST_POSTGRES_URL is not configured")
class Phase2PostgresIntegrationTests(unittest.TestCase):
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
            table_names = ", ".join(
                f'"{table.name}"' for table in reversed(Base.metadata.sorted_tables)
            )
            connection.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))

    def _seed_product(self) -> int:
        with self.factory.begin() as session:
            product = ProductRecord(
                name="Mailman Duck",
                external_source="etsy",
                external_id="1",
            )
            session.add(product)
            session.flush()
            session.add(
                ProductIdentityRecord(
                    product_id=product.id,
                    website_id="1770148417697",
                    website_slug="mailman-duck-1770148417697",
                    etsy_listing_id="1",
                    mapping_state="mapped",
                )
            )
            return product.id

    def test_concurrent_complete_snapshot_commits_one_change_and_outbox_job(self) -> None:
        self._seed_product()
        payload = {
            "contractVersion": "v2",
            "complete": True,
            "productCount": 1,
            "revision": "a" * 64,
            "products": [{"id": 1770148417697, "name": "Mailman Duck"}],
        }
        barrier = threading.Barrier(2)
        results: list[dict] = []

        def accept() -> None:
            with self.factory.begin() as session:
                barrier.wait()
                results.append(accept_catalog_snapshot(session, payload))

        workers = [threading.Thread(target=accept) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=15)
        self.assertEqual([False, True], sorted(result["accepted"] for result in results))
        with self.factory() as session:
            self.assertEqual(1, session.scalar(select(func.count(CatalogSnapshotRecord.id))))
            self.assertEqual(1, session.scalar(select(func.count(CatalogChangeRecord.id))))
            self.assertEqual(1, session.scalar(select(func.count(AutomationJobRecord.id))))

    def test_concurrent_measurement_page_commits_one_event_outcome_cursor_and_rescore(self) -> None:
        product_id = self._seed_product()
        with self.factory.begin() as session:
            seed_taxonomy(session)
            reconcile_editorial_snapshot(
                session,
                {
                    "contractVersion": "v2",
                    "complete": True,
                    "pageCount": 1,
                    "revision": "b" * 64,
                    "pages": [
                        {
                            "id": "guide:mail-carrier-gifts",
                            "pageType": "guide",
                            "canonicalPath": "/guides/mail-carrier-gifts",
                            "canonicalUrl": "https://mattmademe.com/guides/mail-carrier-gifts",
                            "status": "published",
                            "productIds": [1770148417697],
                            "intentKeys": ["mail-carrier-gifts"],
                            "ready": True,
                            "readinessReason": "verified",
                            "publishedAt": None,
                            "revision": "c" * 64,
                        }
                    ],
                },
            )
            materialize_product_coverage(
                session, product_id, source_revision="b" * 64
            )
        occurred_at = utc_now().replace(microsecond=0).isoformat() + "Z"
        event_id = "123e4567-e89b-42d3-a456-426614174000"
        payload = {
            "contractVersion": "v2",
            "events": [
                {
                    "eventId": event_id,
                    "eventKey": f"{occurred_at}#{event_id}",
                    "eventName": "etsy_outbound_click",
                    "occurredAt": occurred_at,
                    "ingestedAt": occurred_at,
                    "destinationHost": "www.etsy.com",
                    "landingPath": "/guides/mail-carrier-gifts",
                    "productId": 1770148417697,
                    "campaignId": "campaign-1",
                    "contentId": "content-1",
                    "publicationId": "publication-1",
                    "expiresAt": 9999999999,
                }
            ],
            "nextCursor": f"{occurred_at}#{event_id}",
            "hasMore": False,
        }
        barrier = threading.Barrier(2)
        results: list[dict] = []

        def ingest() -> None:
            with self.factory.begin() as session:
                barrier.wait()
                results.append(ingest_measurement_page(session, payload))

        workers = [threading.Thread(target=ingest) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=15)
        self.assertEqual([0, 1], sorted(result["created"] for result in results))
        with self.factory() as session:
            self.assertEqual(1, session.scalar(select(func.count(GrowthEventRecord.id))))
            self.assertEqual(3, session.scalar(select(func.count(CoverageOutcomeRecord.id))))
            cursor = session.scalar(select(MeasurementCursorRecord))
            self.assertEqual(1, cursor.ingested_count)
            self.assertEqual(f"{occurred_at}#{event_id}", cursor.opaque_cursor)
            self.assertEqual(
                1,
                session.scalar(
                    select(func.count(AutomationJobRecord.id)).where(
                        AutomationJobRecord.job_type == "coverage.materialize"
                    )
                ),
            )


if __name__ == "__main__":
    unittest.main()
