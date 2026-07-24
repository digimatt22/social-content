from __future__ import annotations

import hashlib
import os
import tempfile
import threading
import unittest
from pathlib import Path

from alembic import command
from alembic.config import Config
from PIL import Image
from sqlalchemy import create_engine, func, select, text

from marketing_os.db import session_factory
from marketing_os.db_models import (
    AssetRecord,
    Base,
    CoverageCellRecord,
    LandingPageRecord,
    PageOpportunityRecord,
    ProductIdentityRecord,
    ProductRecord,
    PublicationOpportunityRecord,
    SearchIntentRecord,
    ShadowCampaignRecord,
    ShadowPayloadLeaseRecord,
    ShadowPublicationRecord,
)
from marketing_os.services.pinterest_shadow import generate_shadow_packages


POSTGRES_URL = os.environ.get("MARKETING_OS_TEST_POSTGRES_URL", "")


@unittest.skipUnless(POSTGRES_URL, "MARKETING_OS_TEST_POSTGRES_URL is not configured")
class PinterestShadowPostgresTests(unittest.TestCase):
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
            table_names = ", ".join(f'"{table.name}"' for table in reversed(Base.metadata.sorted_tables))
            connection.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))
        path = self.root / "postgres-shadow-fixture.png"
        Image.new("RGB", (1000, 1500), (30, 100, 180)).save(path, format="PNG")
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.factory.begin() as session:
            product = ProductRecord(name="Concurrent Mail Carrier Duck")
            intent = SearchIntentRecord(
                intent_key="mail-carrier-gifts",
                normalized_query="mail carrier gifts",
                audience="mail carriers",
                occasion="thank-you gift",
                revision_hash="a" * 64,
            )
            session.add_all([product, intent])
            session.flush()
            session.add(
                ProductIdentityRecord(
                    product_id=product.id,
                    website_id="product:concurrent",
                    website_slug="concurrent",
                    mapping_state="mapped",
                )
            )
            page = LandingPageRecord(
                website_id="guide:concurrent",
                page_type="guide",
                canonical_path="/reads/concurrent/",
                canonical_url="https://mattmademe.com/reads/concurrent/",
                website_revision="website-a",
                lifecycle_state="published",
                readiness_state="ready",
                readiness_reason="",
            )
            session.add(page)
            session.flush()
            cell = CoverageCellRecord(
                dimensional_key="cell:concurrent",
                product_id=product.id,
                search_intent_id=intent.id,
                season_key="evergreen",
                content_format="static_pin",
                landing_page_id=page.id,
                channel="pinterest",
                coverage_state="published",
                freshness_state="fresh",
                source_revision="source-a",
            )
            session.add(cell)
            session.flush()
            session.add_all(
                [
                    PageOpportunityRecord(
                        coverage_cell_id=cell.id,
                        action_type="maintain_page",
                        score=9000,
                        score_version="coverage-v1",
                        score_components_json="{}",
                        explanation="concurrency fixture",
                        lifecycle_state="ranked",
                    ),
                    PublicationOpportunityRecord(
                        coverage_cell_id=cell.id,
                        action_type="create_pin",
                        score=8800,
                        score_version="coverage-v1",
                        score_components_json="{}",
                        explanation="concurrency fixture",
                        eligible=True,
                        eligibility_reason="ready",
                        lifecycle_state="ranked",
                    ),
                    AssetRecord(
                        product_id=product.id,
                        name="Concurrent source reference",
                        asset_type="edited photo",
                        source_path=str(path),
                        readiness_state="ready",
                        file_exists=1,
                        file_checksum=checksum,
                        mime_type="image/png",
                        width=1000,
                        height=1500,
                        asset_role="source_reference",
                        rights="owned",
                        brand_safe="approved",
                        review_state="approved",
                        default_reference=1,
                    ),
                    AssetRecord(
                        product_id=product.id,
                        name="Concurrent shadow fixture",
                        asset_type="edited photo",
                        source_path=str(path),
                        readiness_state="ready",
                        file_exists=1,
                        file_checksum=checksum,
                        mime_type="image/png",
                        width=1000,
                        height=1500,
                        asset_role="shadow_review_fixture",
                        rights="owned",
                        brand_safe="approved",
                        review_state="approved",
                    ),
                ]
            )

    def test_concurrent_replay_creates_one_campaign(self) -> None:
        barrier = threading.Barrier(2)
        results: list[dict] = []

        def generate() -> None:
            with self.factory.begin() as session:
                barrier.wait()
                results.append(
                    generate_shadow_packages(
                        session,
                        repository_revision="repo-concurrent",
                        base_dir=self.root,
                    )
                )

        workers = [threading.Thread(target=generate) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=20)
        self.assertEqual(2, len(results))
        self.assertEqual([0, 1], sorted(item.get("campaignsCreated", 0) for item in results))
        with self.factory() as session:
            self.assertEqual(1, session.scalar(select(func.count()).select_from(ShadowCampaignRecord)))
            self.assertEqual(3, session.scalar(select(func.count()).select_from(ShadowPublicationRecord)))

    def test_concurrent_changed_inputs_have_one_active_lease_per_payload(self) -> None:
        barrier = threading.Barrier(2)

        def generate(revision: str) -> None:
            with self.factory.begin() as session:
                barrier.wait()
                generate_shadow_packages(
                    session,
                    repository_revision=revision,
                    base_dir=self.root,
                )

        workers = [
            threading.Thread(target=generate, args=("repo-a",)),
            threading.Thread(target=generate, args=("repo-b",)),
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=20)
        with self.factory() as session:
            self.assertEqual(2, session.scalar(select(func.count()).select_from(ShadowCampaignRecord)))
            active_hashes = list(
                session.scalars(
                    select(ShadowPayloadLeaseRecord.payload_hash).where(
                        ShadowPayloadLeaseRecord.released_at.is_(None),
                        ShadowPayloadLeaseRecord.superseded_at.is_(None),
                    )
                )
            )
            self.assertEqual(3, len(active_hashes))
            self.assertEqual(3, len(set(active_hashes)))
            self.assertEqual(
                3,
                session.scalar(
                    select(func.count()).select_from(ShadowPublicationRecord).where(
                        ShadowPublicationRecord.lifecycle_state == "blocked"
                    )
                ),
            )


if __name__ == "__main__":
    unittest.main()
