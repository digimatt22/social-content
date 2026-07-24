from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, inspect, select

from marketing_os.db import create_db_engine, init_db, session_factory
from marketing_os.db_models import (
    AutomationJobRecord,
    CatalogChangeRecord,
    CatalogSnapshotRecord,
    CoverageCellRecord,
    CoverageOutcomeRecord,
    GrowthEventRecord,
    LandingPageRecord,
    MeasurementCursorRecord,
    PageOpportunityRecord,
    PrincipalRecord,
    ProductIdentityRecord,
    ProductRecord,
    PublicationOpportunityRecord,
    SearchIntentRecord,
    utc_now,
)
from marketing_os.secure_app import create_secure_app
from marketing_os.jobs.coverage_intelligence import (
    catalog_reconcile_handler,
    measurement_ingest_handler,
)
from marketing_os.services.auth import create_service_credential
from marketing_os.services.coverage_intelligence import (
    accept_catalog_snapshot,
    coverage_exceptions,
    coverage_read_model,
    enqueue_identity_materialization,
    ingest_measurement_page,
    load_coverage_config,
    materialize_product_coverage,
    reconcile_editorial_snapshot,
    reproject_editorial_product_identities,
    seed_taxonomy,
)
from marketing_os.services.job_handlers import NonRetryableJobError
from marketing_os.services.product_identity import reconcile_product_identities


REVISION_A = "a" * 64
REVISION_B = "b" * 64


class Phase2CoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.engine = create_db_engine(self.root / "coverage.sqlite")
        init_db(self.engine)
        self.factory = session_factory(self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tempdir.cleanup()

    def _seed_products(self):
        with self.factory.begin() as session:
            mailman = ProductRecord(name="Mailman Duck", external_source="etsy", external_id="1")
            mailwoman = ProductRecord(name="Mailwoman Duck", external_source="etsy", external_id="2")
            session.add_all([mailman, mailwoman])
            session.flush()
            session.add_all(
                [
                    ProductIdentityRecord(
                        product_id=mailman.id,
                        website_id="1770148417697",
                        website_slug="mailman-duck-1770148417697",
                        etsy_listing_id="1",
                        mapping_state="mapped",
                    ),
                    ProductIdentityRecord(
                        product_id=mailwoman.id,
                        website_id="1770148911584",
                        website_slug="mailwoman-duck-1770148911584",
                        etsy_listing_id="2",
                        mapping_state="mapped",
                    ),
                ]
            )
            return mailman.id, mailwoman.id

    def test_policy_and_taxonomy_are_frozen_and_hypotheses_are_visible(self) -> None:
        config = load_coverage_config()
        self.assertEqual("coverage-v1", config.policy["version"])
        self.assertEqual(10000, sum(config.policy["weights"]["page"].values()))
        self.assertEqual("passed", config.policy["review"]["status"])
        self.assertEqual("passed", config.taxonomy["review"]["status"])
        self.assertTrue(
            all(item["evidenceState"] == "hypothesis" for item in config.taxonomy["intents"])
        )

    def test_missing_service_credentials_are_nonretryable_policy_failures(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "MARKETING_AGENT_API_KEY": "",
                "MARKETING_AGENT_READ_API_KEY": "",
                "MARKETING_AGENT_MEASUREMENT_API_KEY": "",
            },
            clear=False,
        ):
            with self.assertRaises(NonRetryableJobError):
                catalog_reconcile_handler({})
            with self.assertRaises(NonRetryableJobError):
                measurement_ingest_handler({})

    def test_complete_catalog_diff_and_outbox_are_idempotent(self) -> None:
        mailman_id, mailwoman_id = self._seed_products()
        first = {
            "contractVersion": "v2",
            "complete": True,
            "productCount": 2,
            "revision": REVISION_A,
            "products": [
                {"id": 1770148417697, "name": "Mailman Duck", "status": "active"},
                {"id": 1770148911584, "name": "Mailwoman Duck", "status": "active"},
            ],
        }
        with self.factory.begin() as session:
            result = accept_catalog_snapshot(session, first)
            self.assertEqual((2, 2), (result["changes"], result["jobs"]))
        with self.factory.begin() as session:
            result = accept_catalog_snapshot(session, first)
            self.assertEqual((0, 0), (result["changes"], result["jobs"]))

        second = {
            "contractVersion": "v2",
            "complete": True,
            "productCount": 1,
            "revision": REVISION_B,
            "products": [
                {"id": 1770148417697, "name": "Mailman Duck Updated", "status": "active"}
            ],
        }
        with self.factory.begin() as session:
            result = accept_catalog_snapshot(session, second)
            self.assertEqual((2, 2), (result["changes"], result["jobs"]))
        with self.factory() as session:
            change_types = list(
                session.scalars(
                    select(CatalogChangeRecord.change_type).order_by(CatalogChangeRecord.id)
                )
            )
            self.assertEqual(["new", "new", "updated", "retired"], change_types)
            self.assertEqual(4, session.scalar(select(func.count(AutomationJobRecord.id))))
            retired = session.scalar(
                select(CatalogChangeRecord).where(
                    CatalogChangeRecord.change_type == "retired"
                )
            )
            self.assertEqual(mailwoman_id, retired.product_id)
            updated = session.scalar(
                select(CatalogChangeRecord).where(
                    CatalogChangeRecord.change_type == "updated"
                )
            )
            self.assertEqual(mailman_id, updated.product_id)

    def test_late_identity_mapping_repairs_unchanged_catalog_materialization(self) -> None:
        catalog = {
            "contractVersion": "v2",
            "complete": True,
            "productCount": 1,
            "revision": REVISION_A,
            "products": [
                {
                    "id": 1770148417697,
                    "name": "Mailman Duck",
                    "etsyUrl": "https://www.etsy.com/listing/1/mailman-duck",
                }
            ],
        }
        with self.factory.begin() as session:
            first = accept_catalog_snapshot(session, catalog)
            self.assertEqual((1, 1), (first["changes"], first["jobs"]))
            reconcile_editorial_snapshot(
                session,
                {
                    "contractVersion": "v2",
                    "complete": True,
                    "pageCount": 1,
                    "revision": REVISION_B,
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
            exceptions = coverage_exceptions(session)
            self.assertEqual(
                ["1770148417697"],
                [item["sourceProductId"] for item in exceptions["catalog"]],
            )

        with self.factory.begin() as session:
            product = ProductRecord(
                name="Mailman Duck",
                external_source="etsy",
                external_id="1",
            )
            session.add(product)
            session.flush()
            identity = reconcile_product_identities(session, catalog["products"])
            self.assertEqual([product.id], identity["newly_mapped_product_ids"])
            projection = reproject_editorial_product_identities(session)
            self.assertEqual([product.id], projection["affectedProductIds"])
            seed_taxonomy(session)
            unchanged = accept_catalog_snapshot(session, catalog)
            self.assertFalse(unchanged["accepted"])
            repair_jobs = enqueue_identity_materialization(
                session,
                identity["newly_mapped_product_ids"],
                source_revision=catalog["revision"],
            )
            self.assertEqual(1, repair_jobs)
            materialize_product_coverage(
                session, product.id, source_revision=catalog["revision"]
            )

        with self.factory() as session:
            jobs = list(
                session.scalars(
                    select(AutomationJobRecord).order_by(AutomationJobRecord.id)
                )
            )
            first_payload = json.loads(jobs[0].payload_json)
            repair_payload = json.loads(jobs[1].payload_json)
            self.assertIsNone(first_payload["productId"])
            self.assertEqual(product.id, repair_payload["productId"])
            self.assertEqual("identity_repair", repair_payload["trigger"])
            self.assertEqual([], coverage_exceptions(session)["catalog"])
            cell = session.scalar(
                select(CoverageCellRecord)
                .join(SearchIntentRecord)
                .where(SearchIntentRecord.intent_key == "mail-carrier-gifts")
            )
            self.assertEqual("published", cell.coverage_state)
            self.assertIsNotNone(cell.landing_page_id)

    def test_changed_catalog_mapping_uses_one_materialization_job(self) -> None:
        with self.factory.begin() as session:
            product = ProductRecord(
                name="Mailman Duck",
                external_source="etsy",
                external_id="1",
            )
            session.add(product)
            session.flush()
            catalog = {
                "contractVersion": "v2",
                "complete": True,
                "productCount": 1,
                "revision": REVISION_A,
                "products": [
                    {
                        "id": 1770148417697,
                        "name": "Mailman Duck",
                        "etsyUrl": "https://www.etsy.com/listing/1/mailman-duck",
                    }
                ],
            }
            identity = reconcile_product_identities(session, catalog["products"])
            result = accept_catalog_snapshot(session, catalog)
            repair_ids = sorted(
                set(identity["newly_mapped_product_ids"])
                - set(result["materializedProductIds"])
            )
            repair_jobs = enqueue_identity_materialization(
                session, repair_ids, source_revision=catalog["revision"]
            )
            self.assertEqual(1, result["jobs"])
            self.assertEqual(0, repair_jobs)
        with self.factory() as session:
            self.assertEqual(1, session.scalar(select(func.count(AutomationJobRecord.id))))

    def test_identity_loss_rematerializes_and_suppresses_existing_publication(self) -> None:
        catalog = {
            "contractVersion": "v2",
            "complete": True,
            "productCount": 1,
            "revision": REVISION_A,
            "products": [
                {
                    "id": 1770148417697,
                    "name": "Mailman Duck",
                    "etsyUrl": "https://www.etsy.com/listing/1/mailman-duck",
                }
            ],
        }
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
                    etsy_listing_id="1",
                    mapping_state="mapped",
                    mapping_revision=1,
                )
            )
            accept_catalog_snapshot(session, catalog)
            seed_taxonomy(session)
            reconcile_editorial_snapshot(
                session,
                {
                    "contractVersion": "v2",
                    "complete": True,
                    "pageCount": 1,
                    "revision": REVISION_B,
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
                session, product.id, source_revision=REVISION_A
            )
            publication = session.scalar(
                select(PublicationOpportunityRecord)
                .join(CoverageCellRecord)
                .join(SearchIntentRecord)
                .where(SearchIntentRecord.intent_key == "mail-carrier-gifts")
            )
            self.assertTrue(publication.eligible)
            self.assertEqual(
                1,
                enqueue_identity_materialization(
                    session, [product.id], source_revision=catalog["revision"]
                ),
            )

            product.external_id = "999"
            identity = reconcile_product_identities(session, catalog["products"])
            self.assertEqual([product.id], identity["transitioned_product_ids"])
            projection = reproject_editorial_product_identities(session)
            self.assertEqual([product.id], projection["affectedProductIds"])
            unchanged = accept_catalog_snapshot(session, catalog)
            repair_ids = sorted(
                (
                    set(identity["transitioned_product_ids"])
                    | set(projection["affectedProductIds"])
                )
                - set(unchanged["materializedProductIds"])
            )
            self.assertEqual(
                1,
                enqueue_identity_materialization(
                    session, repair_ids, source_revision=catalog["revision"]
                ),
            )
            refreshed_identity = session.scalar(
                select(ProductIdentityRecord).where(
                    ProductIdentityRecord.product_id == product.id
                )
            )
            self.assertEqual(2, refreshed_identity.mapping_revision)
            materialize_product_coverage(
                session, product.id, source_revision=catalog["revision"]
            )

        with self.factory() as session:
            cell = session.scalar(
                select(CoverageCellRecord)
                .join(SearchIntentRecord)
                .where(SearchIntentRecord.intent_key == "mail-carrier-gifts")
            )
            publication = session.scalar(
                select(PublicationOpportunityRecord).where(
                    PublicationOpportunityRecord.coverage_cell_id == cell.id
                )
            )
            self.assertEqual("suppressed", cell.suppression_state)
            self.assertEqual("product_identity_unresolved", cell.suppression_reason)
            self.assertFalse(publication.eligible)

    def test_incomplete_catalog_cannot_retire_or_advance_checkpoint(self) -> None:
        self._seed_products()
        complete = {
            "contractVersion": "v2",
            "complete": True,
            "productCount": 1,
            "revision": REVISION_A,
            "products": [{"id": 1770148417697, "name": "Mailman Duck"}],
        }
        with self.factory.begin() as session:
            accept_catalog_snapshot(session, complete)
        with self.factory.begin() as session:
            with self.assertRaises(ValueError):
                accept_catalog_snapshot(
                    session,
                    {
                        "contractVersion": "v2",
                        "complete": False,
                        "productCount": 0,
                        "revision": REVISION_B,
                        "products": [],
                    },
                )
        with self.factory() as session:
            checkpoint = session.scalar(select(CatalogSnapshotRecord))
            self.assertEqual(REVISION_A, checkpoint.source_revision)
            self.assertEqual(1, session.scalar(select(func.count(CatalogChangeRecord.id))))

    def test_snapshot_change_and_jobs_rollback_together(self) -> None:
        self._seed_products()
        session = self.factory()
        try:
            accept_catalog_snapshot(
                session,
                {
                    "contractVersion": "v2",
                    "complete": True,
                    "productCount": 1,
                    "revision": REVISION_A,
                    "products": [{"id": 1770148417697, "name": "Mailman Duck"}],
                },
            )
            session.rollback()
        finally:
            session.close()
        with self.factory() as session:
            self.assertEqual(0, session.scalar(select(func.count(CatalogSnapshotRecord.id))))
            self.assertEqual(0, session.scalar(select(func.count(CatalogChangeRecord.id))))
            self.assertEqual(0, session.scalar(select(func.count(AutomationJobRecord.id))))

    def test_missing_page_ranks_but_publication_waits_for_fresh_readiness(self) -> None:
        mailman_id, _ = self._seed_products()
        with self.factory.begin() as session:
            seed_taxonomy(session)
            result = materialize_product_coverage(
                session, mailman_id, source_revision=REVISION_A
            )
            self.assertGreaterEqual(result["cells"], 2)
        with self.factory() as session:
            cell = session.scalar(
                select(CoverageCellRecord)
                .join(SearchIntentRecord)
                .where(SearchIntentRecord.intent_key == "mail-carrier-gifts")
            )
            page = session.scalar(
                select(PageOpportunityRecord).where(
                    PageOpportunityRecord.coverage_cell_id == cell.id
                )
            )
            publication = session.scalar(
                select(PublicationOpportunityRecord).where(
                    PublicationOpportunityRecord.coverage_cell_id == cell.id
                )
            )
            self.assertGreater(page.score, 0)
            self.assertFalse(publication.eligible)
            self.assertIn(
                publication.eligibility_reason,
                {
                    "missing_destination_page",
                    "page_not_published",
                    "page_not_ready",
                    "page_readiness_stale",
                },
            )

        editorial = {
            "contractVersion": "v2",
            "complete": True,
            "pageCount": 1,
            "revision": REVISION_B,
            "pages": [
                {
                    "id": "guide:mail-carrier-gifts",
                    "pageType": "guide",
                    "canonicalPath": "/guides/mail-carrier-gifts",
                    "canonicalUrl": "https://mattmademe.com/guides/mail-carrier-gifts",
                    "status": "published",
                    "productIds": [1770148417697, 1770148911584],
                    "intentKeys": ["mail-carrier-gifts"],
                    "ready": True,
                    "readinessReason": "verified",
                    "publishedAt": None,
                    "revision": "c" * 64,
                }
            ],
        }
        with self.factory.begin() as session:
            reconcile_editorial_snapshot(session, editorial)
            materialize_product_coverage(session, mailman_id, source_revision=REVISION_B)
        with self.factory() as session:
            cell = session.scalar(
                select(CoverageCellRecord)
                .join(SearchIntentRecord)
                .where(SearchIntentRecord.intent_key == "mail-carrier-gifts")
            )
            publication = session.scalar(
                select(PublicationOpportunityRecord).where(
                    PublicationOpportunityRecord.coverage_cell_id == cell.id
                )
            )
            self.assertEqual("published", cell.coverage_state)
            self.assertTrue(publication.eligible)
            self.assertEqual("ready", publication.eligibility_reason)
            self.assertEqual("create_pin", publication.action_type)
            self.assertNotIn(
                "already_covered", self._components(publication)["penaltyReasons"]
            )
            read_model = coverage_read_model(session, mailman_id)
            matching = next(
                item
                for item in read_model["cells"]
                if item["intent"]["key"] == "mail-carrier-gifts"
            )
            self.assertEqual("create_pin", matching["nextAction"])

    def test_taxonomy_reseed_preserves_authoritative_editorial_readiness(self) -> None:
        mailman_id, _ = self._seed_products()
        with self.factory.begin() as session:
            seed_taxonomy(session)
            reconcile_editorial_snapshot(
                session,
                {
                    "contractVersion": "v2",
                    "complete": True,
                    "pageCount": 1,
                    "revision": REVISION_A,
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
            seed_taxonomy(session)
            materialize_product_coverage(
                session, mailman_id, source_revision=REVISION_A
            )
        with self.factory() as session:
            page = session.scalar(
                select(LandingPageRecord).where(
                    LandingPageRecord.website_id == "guide:mail-carrier-gifts"
                )
            )
            self.assertEqual(("published", "ready"), (page.lifecycle_state, page.readiness_state))

    def test_seasonal_dates_are_exactly_90_and_60_days(self) -> None:
        mailman_id, _ = self._seed_products()
        event_date = date(2026, 12, 25)
        with self.factory.begin() as session:
            intent = SearchIntentRecord(
                intent_key="holiday-mail-carrier-gifts",
                normalized_query="holiday mail carrier gifts",
                season_key="holiday",
                event_date=event_date,
                evidence_state="hypothesis",
                confidence_bps=2500,
                evidence_ids_json='["test:hypothesis"]',
                product_ids_json=f"[{mailman_id}]",
                revision_hash="d" * 64,
            )
            session.add(intent)
            session.flush()
            session.add(
                LandingPageRecord(
                    website_id="guide:holiday-mail-carrier-gifts",
                    page_type="guide",
                    canonical_path="/guides/holiday-mail-carrier-gifts",
                    canonical_url="https://mattmademe.com/guides/holiday-mail-carrier-gifts",
                    website_revision="c" * 64,
                    website_product_ids_json='["1770148417697"]',
                    product_ids_json=f"[{mailman_id}]",
                    intent_keys_json='["holiday-mail-carrier-gifts"]',
                    lifecycle_state="published",
                    readiness_state="ready",
                    readiness_reason="verified",
                    checked_at=utc_now(),
                )
            )
            session.flush()
            materialize_product_coverage(
                session,
                mailman_id,
                source_revision=REVISION_A,
                today=event_date - timedelta(days=75),
            )
        with self.factory() as session:
            cell = session.scalar(
                select(CoverageCellRecord).where(
                    CoverageCellRecord.search_intent_id == intent.id
                )
            )
            page = session.scalar(
                select(PageOpportunityRecord).where(
                    PageOpportunityRecord.coverage_cell_id == cell.id
                )
            )
            publication = session.scalar(
                select(PublicationOpportunityRecord).where(
                    PublicationOpportunityRecord.coverage_cell_id == cell.id
                )
            )
            self.assertEqual(event_date - timedelta(days=90), page.target_ready_date)
            self.assertEqual(event_date - timedelta(days=60), publication.publish_start_date)
            self.assertEqual(8000, self._components(page)["seasonalUrgency"])
            self.assertFalse(publication.eligible)
            self.assertEqual(
                "publication_window_not_open", publication.eligibility_reason
            )
        with self.factory.begin() as session:
            materialize_product_coverage(
                session,
                mailman_id,
                source_revision=REVISION_B,
                today=event_date - timedelta(days=60),
            )
        with self.factory() as session:
            publication = session.scalar(select(PublicationOpportunityRecord))
            self.assertTrue(publication.eligible)

    def test_qualified_measurement_is_deduped_cursor_checkpointed_and_rescored(self) -> None:
        mailman_id, _ = self._seed_products()
        with self.factory.begin() as session:
            seed_taxonomy(session)
            reconcile_editorial_snapshot(
                session,
                {
                    "contractVersion": "v2",
                    "complete": True,
                    "pageCount": 1,
                    "revision": REVISION_A,
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
            materialize_product_coverage(session, mailman_id, source_revision=REVISION_A)
        occurred_at = utc_now().replace(microsecond=0).isoformat() + "Z"
        event = {
            "eventId": "123e4567-e89b-42d3-a456-426614174000",
            "eventKey": f"{occurred_at}#123e4567-e89b-42d3-a456-426614174000",
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
        payload = {
            "contractVersion": "v2",
            "events": [event],
            "nextCursor": event["eventKey"],
            "hasMore": True,
        }
        with self.factory.begin() as session:
            result = ingest_measurement_page(session, payload)
            self.assertEqual(1, result["created"])
        with self.factory.begin() as session:
            result = ingest_measurement_page(session, payload)
            self.assertEqual(0, result["created"])
        with self.factory() as session:
            self.assertEqual(1, session.scalar(select(func.count(GrowthEventRecord.id))))
            self.assertEqual(3, session.scalar(select(func.count(CoverageOutcomeRecord.id))))
            self.assertEqual(
                ["24h_diagnostic", "30d_performance", "7d_diagnostic"],
                sorted(
                    session.scalars(
                        select(CoverageOutcomeRecord.maturity_window)
                    )
                ),
            )
            cursor = session.scalar(select(MeasurementCursorRecord))
            self.assertEqual(event["eventKey"], cursor.opaque_cursor)
            self.assertEqual(1, cursor.ingested_count)
            rescore_jobs = session.scalar(
                select(func.count(AutomationJobRecord.id)).where(
                    AutomationJobRecord.job_type == "coverage.materialize"
                )
            )
            self.assertEqual(1, rescore_jobs)

    def test_read_models_and_authenticated_routes_expose_explanations(self) -> None:
        mailman_id, _ = self._seed_products()
        with self.factory.begin() as session:
            seed_taxonomy(session)
            materialize_product_coverage(session, mailman_id, source_revision=REVISION_A)
            model = coverage_read_model(session, mailman_id)
            self.assertTrue(model["cells"])
            self.assertEqual(
                list(range(1, model["count"] + 1)),
                [item["rank"] for item in model["cells"]],
            )
            self.assertEqual(
                sorted(
                    [item["nextActionScore"] for item in model["cells"]],
                    reverse=True,
                ),
                [item["nextActionScore"] for item in model["cells"]],
            )
            counterfactual = model["cells"][0]["pageOpportunity"]["components"]["counterfactual"]
            self.assertIn("smallestNamedComponentChange", counterfactual)
            self.assertIn("coverage", coverage_exceptions(session))

        db_path = self.root / "secure.sqlite"
        with patch.dict(
            "os.environ",
            {"MARKETING_OS_SECRET": "phase2-test-secret-that-is-long-enough"},
            clear=False,
        ):
            app = create_secure_app(str(db_path), bootstrap_data=False)
        app.config["TESTING"] = True
        with app.config["SESSION_FACTORY"].begin() as session:
            principal = PrincipalRecord(
                principal_type="service",
                username="coverage-reader",
                roles_json='["service"]',
            )
            session.add(principal)
            session.flush()
            token, _ = create_service_credential(session, principal, scopes={"read"})
        client = app.test_client()
        self.assertEqual(401, client.get("/api/coverage").status_code)
        response = client.get(
            "/api/coverage", headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual({"cells": [], "count": 0}, {k: response.json[k] for k in ("cells", "count")})
        self.assertEqual(
            200,
            client.get("/coverage", headers={"Authorization": f"Bearer {token}"}).status_code,
        )
        app.config["SESSION_FACTORY"].kw["bind"].dispose()

    def test_migration_upgrades_and_downgrades_revision_0003(self) -> None:
        path = self.root / "migration.sqlite"
        url = f"sqlite:///{path}"
        config = Config("alembic.ini")
        with patch.dict("os.environ", {"MARKETING_OS_DB_URL": url}):
            command.upgrade(config, "head")
            engine = create_engine(url, future=True)
            self.assertIn("coverage_cells", inspect(engine).get_table_names())
            engine.dispose()
            command.downgrade(config, "0002_growth_contracts")
            engine = create_engine(url, future=True)
            self.assertNotIn("coverage_cells", inspect(engine).get_table_names())
            engine.dispose()

    @staticmethod
    def _components(item: PageOpportunityRecord) -> dict:
        import json

        return json.loads(item.score_components_json)


if __name__ == "__main__":
    unittest.main()
