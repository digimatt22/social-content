from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from sqlalchemy import func, select

from marketing_os.db import create_db_engine, init_db, session_factory
from marketing_os.db_models import (
    AssetRecord,
    AutomationJobRecord,
    CoverageCellRecord,
    LandingPageRecord,
    PageOpportunityRecord,
    ProductIdentityRecord,
    ProductRecord,
    PrincipalRecord,
    PublicationOpportunityRecord,
    SearchIntentRecord,
    ShadowCampaignRecord,
    ShadowCreativeManifestRecord,
    ShadowDigestRecord,
    ShadowPayloadLeaseRecord,
    ShadowPublicationRecord,
    ShadowQADecisionRecord,
    ShadowReviewDecisionRecord,
    ShadowReviewSessionRecord,
)
from marketing_os.jobs.durable_scheduler import emit_due_jobs
from marketing_os.secure_app import create_secure_app
from marketing_os.services.auth import create_service_credential
from marketing_os.services.job_handlers import default_registry
from marketing_os.services.pinterest_shadow import (
    build_weekly_digest,
    complete_review_session,
    generate_shadow_packages,
    load_shadow_config,
    ShadowConfig,
    record_review_decision,
    shadow_exceptions,
    shadow_read_model,
    start_review_session,
    supersede_publication,
)


class PinterestShadowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.engine = create_db_engine(self.root / "shadow.sqlite")
        init_db(self.engine)
        self.factory = session_factory(self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tempdir.cleanup()

    def _fixture(self, name: str, color: tuple[int, int, int] = (20, 90, 170)) -> tuple[Path, str]:
        path = self.root / name
        Image.new("RGB", (1000, 1500), color).save(path, format="PNG")
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def _seed_cell(
        self,
        *,
        suffix: str = "1",
        intent_key: str = "mail-carrier-gifts",
        ready: bool = True,
        with_asset: bool = True,
        product_name: str | None = None,
        canonical_url: str | None = None,
        asset_role: str = "shadow_review_fixture",
    ) -> int:
        with self.factory.begin() as session:
            product = ProductRecord(name=product_name or f"Mail Carrier Duck {suffix}")
            session.add(product)
            session.flush()
            session.add(
                ProductIdentityRecord(
                    product_id=product.id,
                    website_id=f"product:{suffix}",
                    website_slug=f"product-{suffix}",
                    mapping_state="mapped",
                )
            )
            intent = session.scalar(
                select(SearchIntentRecord).where(SearchIntentRecord.intent_key == intent_key)
            )
            if intent is None:
                intent = SearchIntentRecord(
                    intent_key=intent_key,
                    normalized_query=intent_key.replace("-", " "),
                    audience="mail carriers",
                    occasion="thank-you gift",
                    revision_hash=hashlib.sha256(intent_key.encode()).hexdigest(),
                )
                session.add(intent)
                session.flush()
            page = LandingPageRecord(
                website_id=f"guide:{suffix}",
                page_type="guide",
                canonical_path=f"/reads/mail-carrier-gifts-{suffix}/",
                canonical_url=canonical_url or f"https://mattmademe.com/reads/mail-carrier-gifts-{suffix}/",
                website_revision="website-" + suffix,
                lifecycle_state="published" if ready else "draft",
                readiness_state="ready" if ready else "not_ready",
                readiness_reason="" if ready else "awaiting editorial verification",
            )
            session.add(page)
            session.flush()
            cell = CoverageCellRecord(
                dimensional_key=f"cell:{suffix}",
                product_id=product.id,
                search_intent_id=intent.id,
                season_key="evergreen",
                content_format="static_pin",
                landing_page_id=page.id,
                channel="pinterest",
                coverage_state="published" if ready else "missing",
                freshness_state="fresh" if ready else "stale",
                source_revision="source-" + suffix,
            )
            session.add(cell)
            session.flush()
            session.add(
                PageOpportunityRecord(
                    coverage_cell_id=cell.id,
                    action_type="maintain_page" if ready else "refresh_page",
                    score=9000,
                    score_version="coverage-v1",
                    score_components_json="{}",
                    explanation="representative fixture",
                    lifecycle_state="ranked",
                )
            )
            session.add(
                PublicationOpportunityRecord(
                    coverage_cell_id=cell.id,
                    action_type="create_pin",
                    score=8800,
                    score_version="coverage-v1",
                    score_components_json="{}",
                    explanation="representative fixture",
                    eligible=ready,
                    eligibility_reason="ready" if ready else "page_not_ready",
                    lifecycle_state="ranked" if ready else "blocked",
                )
            )
            if with_asset:
                path, checksum = self._fixture(f"fixture-{suffix}.png")
                common = {
                    "product_id": product.id,
                    "asset_type": "edited photo",
                    "source_path": str(path),
                    "readiness_state": "ready",
                    "file_exists": 1,
                    "file_checksum": checksum,
                    "mime_type": "image/png",
                    "width": 1000,
                    "height": 1500,
                    "rights": "owned",
                    "brand_safe": "approved",
                    "review_state": "approved",
                }
                session.add_all(
                    [
                        AssetRecord(
                            **common,
                            name=f"Source reference {suffix}",
                            asset_role="source_reference",
                            default_reference=1,
                        ),
                        AssetRecord(
                            **common,
                            name=f"Review fixture {suffix}",
                            asset_role=asset_role,
                        ),
                    ]
                )
            return cell.id

    def test_reviewed_policy_is_schema_valid_and_write_free(self) -> None:
        policy = load_shadow_config().policy
        self.assertEqual("pinterest-shadow-v1", policy["version"])
        self.assertEqual("passed", policy["review"]["status"])
        self.assertFalse(policy["execution"]["publicWrites"])
        self.assertFalse(policy["execution"]["providerCalls"])
        self.assertFalse(policy["execution"]["websiteWrites"])

    def test_ready_cell_generates_three_complete_pinterest_variants(self) -> None:
        self._seed_cell()
        with self.factory.begin() as session:
            result = generate_shadow_packages(
                session, repository_revision="repo-a", base_dir=self.root
            )
            self.assertEqual(1, result["readyCampaigns"])
            self.assertEqual(0, result["publicWrites"])
            self.assertEqual(0, result["providerCalls"])
        with self.factory() as session:
            campaign = session.scalar(select(ShadowCampaignRecord))
            publications = list(session.scalars(select(ShadowPublicationRecord)))
            manifests = list(session.scalars(select(ShadowCreativeManifestRecord)))
            self.assertEqual("ready_for_review", campaign.lifecycle_state)
            self.assertEqual(
                {"search_exact", "gift_context", "audience_context"},
                {item.variant_role for item in publications},
            )
            self.assertEqual(3, len(manifests))
            self.assertTrue(all(item.width == 1000 and item.height == 1500 for item in manifests))
            self.assertTrue(all("utm_source=pinterest" in item.tracked_destination_url for item in publications))
            self.assertTrue(all(item.board_recommendation == "Mail Carrier Gift Ideas" for item in publications))

    def test_replay_is_noop_and_changed_revision_is_immutable_new_input(self) -> None:
        self._seed_cell()
        with self.factory.begin() as session:
            first = generate_shadow_packages(session, repository_revision="repo-a", base_dir=self.root)
            replay = generate_shadow_packages(session, repository_revision="repo-a", base_dir=self.root)
            changed = generate_shadow_packages(session, repository_revision="repo-b", base_dir=self.root)
            self.assertEqual(1, first["campaignsCreated"])
            self.assertEqual(1, replay["campaignsReplayed"])
            self.assertEqual(1, changed["campaignsCreated"])
        with self.factory() as session:
            self.assertEqual(2, session.scalar(select(func.count()).select_from(ShadowCampaignRecord)))

    def test_daily_catch_up_skips_replays_and_drains_beyond_first_twenty(self) -> None:
        for index in range(25):
            self._seed_cell(suffix=f"catchup-{index:02d}")
        with self.factory.begin() as session:
            first = generate_shadow_packages(
                session, repository_revision="repo-catchup", base_dir=self.root
            )
            self.assertEqual(20, first["campaignsCreated"])
        with self.factory.begin() as session:
            second = generate_shadow_packages(
                session, repository_revision="repo-catchup", base_dir=self.root
            )
            self.assertEqual(5, second["campaignsCreated"])
            self.assertEqual(20, second["campaignsReplayed"])
        with self.factory() as session:
            self.assertEqual(
                25,
                session.scalar(select(func.count()).select_from(ShadowCampaignRecord)),
            )

    def test_upstream_suppression_invalidates_ready_package_and_releases_leases(self) -> None:
        cell_id = self._seed_cell()
        with self.factory.begin() as session:
            generate_shadow_packages(session, repository_revision="repo-a", base_dir=self.root)
        with self.factory.begin() as session:
            cell = session.get(CoverageCellRecord, cell_id)
            cell.suppression_state = "suppressed"
            cell.suppression_reason = "identity_mapping_unresolved"
            result = generate_shadow_packages(
                session, repository_revision="repo-a", base_dir=self.root
            )
            self.assertEqual(1, result["invalidatedCampaigns"])
        with self.factory() as session:
            campaign = session.scalar(select(ShadowCampaignRecord))
            self.assertEqual("blocked", campaign.lifecycle_state)
            self.assertTrue(
                all(
                    item.lifecycle_state == "blocked"
                    for item in session.scalars(select(ShadowPublicationRecord))
                )
            )
            self.assertEqual(
                3,
                session.scalar(
                    select(func.count())
                    .select_from(ShadowPayloadLeaseRecord)
                    .where(ShadowPayloadLeaseRecord.released_at.is_not(None))
                ),
            )
            self.assertIn("identity_mapping_unresolved", shadow_exceptions(session)["reasonCounts"])

    def test_changed_semantic_payload_automatically_supersedes_prior_variants(self) -> None:
        cell_id = self._seed_cell(product_name="Original Mail Duck")
        with self.factory.begin() as session:
            generate_shadow_packages(session, repository_revision="repo-a", base_dir=self.root)
        with self.factory.begin() as session:
            cell = session.get(CoverageCellRecord, cell_id)
            cell.product.name = "Updated Mail Duck"
            cell.source_revision = "source-updated"
            identity = session.scalar(
                select(ProductIdentityRecord).where(
                    ProductIdentityRecord.product_id == cell.product_id
                )
            )
            identity.mapping_revision += 1
            generate_shadow_packages(session, repository_revision="repo-a", base_dir=self.root)
        with self.factory() as session:
            publications = list(session.scalars(select(ShadowPublicationRecord)))
            self.assertEqual(3, sum(item.lifecycle_state == "superseded" for item in publications))
            self.assertEqual(3, sum(item.lifecycle_state == "ready_for_review" for item in publications))
            old_campaign = session.scalar(
                select(ShadowCampaignRecord).where(
                    ShadowCampaignRecord.source_revision == "source-1"
                )
            )
            self.assertEqual("superseded", old_campaign.lifecycle_state)

    def test_unready_destination_creates_page_only_blocked_package(self) -> None:
        self._seed_cell(ready=False)
        with self.factory.begin() as session:
            generate_shadow_packages(session, repository_revision="repo-a", base_dir=self.root)
            campaign = session.scalar(select(ShadowCampaignRecord))
            review = start_review_session(
                session,
                campaign.campaign_id,
                reviewer="matthew",
                session_token="page-only-review",
            )
            record_review_decision(
                session,
                review.session_token,
                None,
                decision_kind="destination",
                result="revise",
                reason_codes=["intro_needs_detail"],
            )
            completed = complete_review_session(session, review.session_token)
            self.assertEqual(1, completed["reviewedItemCount"])
        with self.factory() as session:
            campaign = session.scalar(select(ShadowCampaignRecord))
            self.assertEqual("reviewed", campaign.lifecycle_state)
            self.assertEqual("draft_page", json.loads(campaign.page_artifact_json)["action"])
            self.assertEqual(0, session.scalar(select(func.count()).select_from(ShadowPublicationRecord)))

    def test_deranked_or_future_window_opportunity_invalidates_active_package(self) -> None:
        self._seed_cell()
        with self.factory.begin() as session:
            generate_shadow_packages(
                session,
                repository_revision="repo-a",
                base_dir=self.root,
                today=date(2026, 7, 24),
            )
        with self.factory.begin() as session:
            opportunity = session.scalar(select(PublicationOpportunityRecord))
            opportunity.lifecycle_state = "blocked"
            opportunity.publish_start_date = date(2026, 8, 1)
            result = generate_shadow_packages(
                session,
                repository_revision="repo-a",
                base_dir=self.root,
                today=date(2026, 7, 24),
            )
            self.assertEqual(1, result["invalidatedCampaigns"])
        with self.factory() as session:
            reasons = shadow_exceptions(session)["reasonCounts"]
            self.assertIn("publication_opportunity_no_longer_ranked", reasons)
            self.assertIn("publication_window_not_open", reasons)

    def test_unknown_board_and_missing_fixture_are_explicit_qa_failures(self) -> None:
        self._seed_cell(intent_key="unreviewed-intent", with_asset=False)
        with self.factory.begin() as session:
            generate_shadow_packages(session, repository_revision="repo-a", base_dir=self.root)
        with self.factory() as session:
            failures = shadow_exceptions(session)
            self.assertIn("board_unreviewed", failures["reasonCounts"])
            self.assertIn("approved_file_backed_source_asset_missing", failures["reasonCounts"])
            self.assertIn("checksummed_1000x1500_review_fixture_missing", failures["reasonCounts"])
            self.assertEqual(0, session.scalar(select(func.count()).select_from(ShadowPayloadLeaseRecord)))
            self.assertEqual(
                3,
                session.scalar(
                    select(func.count())
                    .select_from(ShadowQADecisionRecord)
                    .where(
                        ShadowQADecisionRecord.gate_name == "active_payload_uniqueness",
                        ShadowQADecisionRecord.result == "not_evaluated",
                    )
                ),
            )

    def test_conflicting_attribution_is_blocked_not_overwritten(self) -> None:
        self._seed_cell(canonical_url="https://mattmademe.com/reads/x/?utm_source=email")
        with self.factory.begin() as session:
            generate_shadow_packages(session, repository_revision="repo-a", base_dir=self.root)
        with self.factory() as session:
            publication = session.scalar(select(ShadowPublicationRecord))
            self.assertEqual("", publication.tracked_destination_url)
            self.assertEqual("blocked", publication.lifecycle_state)
            self.assertIn("destination_attribution_conflict", shadow_exceptions(session)["reasonCounts"])

    def test_non_fixture_asset_cannot_count_as_review_ready(self) -> None:
        self._seed_cell(asset_role="source_reference")
        with self.factory.begin() as session:
            generate_shadow_packages(session, repository_revision="repo-a", base_dir=self.root)
        with self.factory() as session:
            self.assertTrue(
                all(item.lifecycle_state == "blocked" for item in session.scalars(select(ShadowPublicationRecord)))
            )
            self.assertIn("checksummed_1000x1500_review_fixture_missing", shadow_exceptions(session)["reasonCounts"])

    def test_unresolved_identity_blocks_every_variant(self) -> None:
        self._seed_cell()
        with self.factory.begin() as session:
            identity = session.scalar(select(ProductIdentityRecord))
            identity.mapping_state = "unresolved"
            identity.website_id = None
            generate_shadow_packages(session, repository_revision="repo-a", base_dir=self.root)
        with self.factory() as session:
            self.assertEqual(
                3,
                session.scalar(
                    select(func.count()).select_from(ShadowPublicationRecord).where(
                        ShadowPublicationRecord.lifecycle_state == "blocked"
                    )
                ),
            )
            self.assertIn("canonical_product_identity_unresolved", shadow_exceptions(session)["reasonCounts"])

    def test_changed_fixture_bytes_block_without_job_filesystem_mutation(self) -> None:
        self._seed_cell()
        fixture = self.root / "fixture-1.png"
        before_files = sorted(path.name for path in self.root.iterdir())
        fixture.write_bytes(fixture.read_bytes() + b"changed")
        with self.factory.begin() as session:
            generate_shadow_packages(session, repository_revision="repo-a", base_dir=self.root)
        self.assertEqual(before_files, sorted(path.name for path in self.root.iterdir()))
        with self.factory() as session:
            self.assertIn("approved_file_backed_source_asset_missing", shadow_exceptions(session)["reasonCounts"])

    def test_claim_and_placeholder_failures_are_persisted_not_silently_removed(self) -> None:
        self._seed_cell()
        loaded = load_shadow_config()
        policy = deepcopy(loaded.policy)
        policy["format"]["cta"] = "Buy now. [MATT_TO_CONFIRM: discount]"
        altered = ShadowConfig(policy=policy, policy_hash=hashlib.sha256(b"altered").hexdigest())
        with self.factory.begin() as session:
            generate_shadow_packages(
                session,
                repository_revision="repo-claims",
                base_dir=self.root,
                config=altered,
            )
        with self.factory() as session:
            reasons = shadow_exceptions(session)["reasonCounts"]
            self.assertIn("unsupported_claim", reasons)
            self.assertIn("missing_required_fact_placeholder", reasons)
            self.assertEqual(
                3,
                session.scalar(
                    select(func.count()).select_from(ShadowPublicationRecord).where(
                        ShadowPublicationRecord.lifecycle_state == "blocked"
                    )
                ),
            )

    def test_authority_policy_mutation_is_rejected_at_load(self) -> None:
        policy = deepcopy(load_shadow_config().policy)
        policy["execution"]["publicWrites"] = True
        path = self.root / "unsafe-policy.json"
        path.write_text(json.dumps(policy), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "write-free"):
            load_shadow_config(path)

    def test_representative_batch_exceeds_twenty_variants_across_ten_cells(self) -> None:
        intent_keys = [
            "mail-carrier-gifts",
            "everyday-heroes-gifts",
            "first-responder-gifts",
        ]
        for index in range(10):
            self._seed_cell(
                suffix=str(index + 1),
                intent_key=intent_keys[index % len(intent_keys)],
            )
        self._seed_cell(suffix="draft-1", ready=False)
        self._seed_cell(suffix="draft-2", ready=False)
        with self.factory.begin() as session:
            result = generate_shadow_packages(session, repository_revision="repo-batch", base_dir=self.root)
            self.assertEqual(10, result["readyCampaigns"])
            self.assertEqual(2, result["blockedCampaigns"])
        with self.factory() as session:
            ready = list(
                session.scalars(
                    select(ShadowPublicationRecord).where(
                        ShadowPublicationRecord.lifecycle_state == "ready_for_review"
                    )
                )
            )
            self.assertGreaterEqual(len(ready), 20)
            self.assertGreaterEqual(len({item.campaign_id for item in ready}), 10)
            self.assertEqual(
                {
                    "Mail Carrier Gift Ideas",
                    "Everyday Heroes Gift Ideas",
                    "First Responder Gift Ideas",
                },
                {item.board_recommendation for item in ready},
            )

    def test_timed_item_level_review_is_append_only_and_counts_are_derived(self) -> None:
        self._seed_cell()
        with self.factory.begin() as session:
            generate_shadow_packages(session, repository_revision="repo-a", base_dir=self.root)
            campaign = session.scalar(select(ShadowCampaignRecord))
            publication = session.scalar(select(ShadowPublicationRecord))
            started = datetime(2026, 7, 24, 12, 0, 0)
            review = start_review_session(
                session,
                campaign.campaign_id,
                reviewer="matthew",
                session_token="review-1",
                started_at=started,
            )
            record_review_decision(
                session,
                review.session_token,
                publication.publication_id,
                decision_kind="package",
                result="revise",
                reason_codes=["creative_needs_check"],
            )
            summary = complete_review_session(
                session, review.session_token, completed_at=started + timedelta(seconds=73)
            )
            self.assertEqual(73, summary["elapsedSeconds"])
            self.assertEqual({"revise": 1}, summary["resultCounts"])
            with self.assertRaises(ValueError):
                record_review_decision(
                    session,
                    review.session_token,
                    publication.publication_id,
                    decision_kind="copy",
                    result="accepted_for_shadow",
                )
            digest, _ = build_weekly_digest(session, week=date(2026, 7, 24))
            groups = json.loads(digest.payload_json)["revisionGroups"]
            self.assertEqual(1, groups["humanByReason"]["creative_needs_check"])
            self.assertEqual(1, groups["humanByResult"]["revise"])
            self.assertEqual(1, groups["humanByDecisionKind"]["package"])
            self.assertIn(publication.variant_role, groups["humanByVariant"])
            self.assertIn(publication.board_recommendation, groups["humanByBoard"])
        with self.factory() as session:
            self.assertEqual(1, session.scalar(select(func.count()).select_from(ShadowReviewDecisionRecord)))
            review = session.scalar(select(ShadowReviewSessionRecord))
            self.assertEqual(73, review.elapsed_seconds)

    def test_duplicate_payload_is_blocked_until_prior_publication_is_superseded(self) -> None:
        self._seed_cell(suffix="same", product_name="Same Duck", canonical_url="https://mattmademe.com/reads/same/")
        with self.factory.begin() as session:
            generate_shadow_packages(session, repository_revision="repo-a", base_dir=self.root)
            generate_shadow_packages(session, repository_revision="repo-b", base_dir=self.root)
        with self.factory.begin() as session:
            publications = list(session.scalars(select(ShadowPublicationRecord).order_by(ShadowPublicationRecord.id)))
            blocked = [item for item in publications if item.lifecycle_state == "blocked"]
            self.assertEqual(3, len(blocked))
            ready = [item for item in publications if item.lifecycle_state == "ready_for_review"]
            supersede_publication(session, ready[0].id)
        with self.factory() as session:
            self.assertEqual(3, session.scalar(select(func.count()).select_from(ShadowPayloadLeaseRecord)))
            self.assertEqual(
                1,
                session.scalar(
                    select(func.count())
                    .select_from(ShadowPayloadLeaseRecord)
                    .where(ShadowPayloadLeaseRecord.released_at.is_not(None))
                ),
            )
            self.assertIn("duplicate_active_payload", shadow_exceptions(session)["reasonCounts"])

    def test_digest_is_idempotent_and_reports_observational_maturity(self) -> None:
        self._seed_cell()
        with self.factory.begin() as session:
            generate_shadow_packages(session, repository_revision="repo-a", base_dir=self.root)
            first, created = build_weekly_digest(session, week=date(2026, 7, 24))
            second, replay_created = build_weekly_digest(session, week=date(2026, 7, 24))
            self.assertTrue(created)
            self.assertFalse(replay_created)
            self.assertEqual(first.id, second.id)
            payload = json.loads(first.payload_json)
            self.assertEqual("observational", payload["learning"]["kind"])
            self.assertEqual("unverified_requires_human", payload["evidenceMaturity"]["productAccuracy"])

    def test_digest_filters_to_requested_week_and_empty_review_cannot_complete(self) -> None:
        self._seed_cell()
        with self.factory.begin() as session:
            generate_shadow_packages(session, repository_revision="repo-a", base_dir=self.root)
            campaign = session.scalar(select(ShadowCampaignRecord))
            start_review_session(
                session,
                campaign.campaign_id,
                reviewer="matthew",
                session_token="empty-review",
            )
            with self.assertRaisesRegex(ValueError, "at least one item decision"):
                complete_review_session(session, "empty-review")
            future, _ = build_weekly_digest(session, week=date(2026, 8, 10))
            payload = json.loads(future.payload_json)
            self.assertEqual({}, payload["campaignStates"])
            self.assertEqual({}, payload["publicationStates"])
            self.assertEqual(0, payload["reviewEffort"]["completedSessions"])
            self.assertIsNone(payload["reviewEffort"]["medianElapsedSeconds"])

    def test_review_model_exposes_image_manifest_qa_and_provenance(self) -> None:
        self._seed_cell()
        with self.factory.begin() as session:
            generate_shadow_packages(session, repository_revision="repo-a", base_dir=self.root)
        with self.factory() as session:
            publication = shadow_read_model(session)["campaigns"][0]["publications"][0]
            self.assertEqual(1000, publication["manifest"]["reviewAsset"]["width"])
            self.assertEqual("fixture_non_provider", publication["manifest"]["reviewAsset"]["origin"])
            self.assertTrue(publication["manifest"]["prompt"])
            self.assertTrue(publication["manifest"]["provenance"])
            self.assertGreaterEqual(len(publication["qa"]), 14)
            source_ids = set(publication["manifest"]["sourceAssetIds"])
            self.assertNotIn(publication["manifest"]["reviewAsset"]["id"], source_ids)

    def test_scheduler_and_registry_include_shadow_jobs(self) -> None:
        registry = default_registry()
        self.assertIsNotNone(registry.resolve("shadow.generate", 1))
        self.assertIsNotNone(registry.resolve("shadow.digest", 1))
        emitted = emit_due_jobs(self.factory, datetime(2026, 7, 27, 10, 15, 0))
        self.assertGreaterEqual(emitted, 6)
        with self.factory() as session:
            types = set(session.scalars(select(AutomationJobRecord.job_type)))
            self.assertIn("shadow.generate", types)
            self.assertIn("shadow.digest", types)

    def test_read_model_declares_zero_external_authority(self) -> None:
        self._seed_cell()
        with self.factory.begin() as session:
            generate_shadow_packages(session, repository_revision="repo-a", base_dir=self.root)
        with self.factory() as session:
            model = shadow_read_model(session)
            self.assertFalse(model["authority"]["pinterestWrites"])
            self.assertFalse(model["authority"]["websiteWrites"])
            self.assertFalse(model["authority"]["providerCalls"])

    def test_shadow_routes_require_auth_and_review_mutations_require_write_scope(self) -> None:
        self._seed_cell()
        with self.factory.begin() as session:
            generate_shadow_packages(session, repository_revision="repo-a", base_dir=self.root)
            campaign = session.scalar(select(ShadowCampaignRecord))
            publication = session.scalar(select(ShadowPublicationRecord))
            campaign_id = campaign.campaign_id
            publication_id = publication.publication_id
        with patch.dict(
            os.environ,
            {"MARKETING_OS_SECRET": "shadow-test-secret-that-is-long-enough"},
            clear=False,
        ):
            app = create_secure_app(str(self.root / "shadow.sqlite"), bootstrap_data=False)
        app.config.update(TESTING=True)
        app_factory = app.config["SESSION_FACTORY"]
        with app_factory.begin() as session:
            service = PrincipalRecord(
                principal_type="service",
                username="shadow-service",
                roles_json='["service"]',
                password_hash="",
            )
            session.add(service)
            session.flush()
            read_token, _ = create_service_credential(session, service, scopes={"read"})
            write_token, _ = create_service_credential(session, service, scopes={"read", "write"})
        client = app.test_client()
        self.assertEqual(401, client.get("/api/shadow-campaigns", base_url="https://localhost").status_code)
        self.assertEqual(302, client.get("/shadow-campaigns", base_url="https://localhost").status_code)
        read_headers = {"Authorization": f"Bearer {read_token}"}
        write_headers = {"Authorization": f"Bearer {write_token}"}
        self.assertEqual(
            200,
            client.get("/api/shadow-campaigns", headers=read_headers, base_url="https://localhost").status_code,
        )
        self.assertEqual(
            404,
            client.get("/api/shadow-digests/latest", headers=read_headers, base_url="https://localhost").status_code,
        )
        with app_factory() as session:
            self.assertEqual(0, session.scalar(select(func.count()).select_from(ShadowDigestRecord)))
        self.assertEqual(
            403,
            client.post(
                "/api/shadow-review-sessions",
                json={"campaignId": campaign_id, "sessionToken": "api-review"},
                headers=read_headers,
                base_url="https://localhost",
            ).status_code,
        )
        started = client.post(
            "/api/shadow-review-sessions",
            json={"campaignId": campaign_id, "sessionToken": "api-review"},
            headers=write_headers,
            base_url="https://localhost",
        )
        self.assertEqual(201, started.status_code)
        decided = client.post(
            "/api/shadow-review-sessions/api-review/decisions",
            json={
                "publicationId": publication_id,
                "decisionKind": "package",
                "result": "accepted_for_shadow",
                "reasonCodes": [],
            },
            headers=write_headers,
            base_url="https://localhost",
        )
        self.assertEqual(201, decided.status_code)
        completed = client.post(
            "/api/shadow-review-sessions/api-review/complete",
            json={},
            headers=write_headers,
            base_url="https://localhost",
        )
        self.assertEqual(200, completed.status_code)
        app_factory.kw["bind"].dispose()


if __name__ == "__main__":
    unittest.main()
