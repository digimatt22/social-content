from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import func, select

from marketing_os.db import create_db_engine, init_db, session_factory
from marketing_os.db_models import (
    AssetRecord,
    AutomationJobRecord,
    CoverageCellRecord,
    LandingPageRecord,
    PinterestConnectionRecord,
    PinterestMediaDeliveryRecord,
    PinterestPerformanceSnapshotRecord,
    PinterestPublishAttemptRecord,
    PinterestPublicationRecord,
    PinterestReconciliationRecord,
    PrincipalRecord,
    ProductRecord,
    SearchIntentRecord,
    ShadowCampaignRecord,
    ShadowCreativeManifestRecord,
    ShadowPublicationRecord,
    ShadowReviewDecisionRecord,
    ShadowReviewSessionRecord,
)
from marketing_os.services.capability_preflight import capability_report
from marketing_os.services.job_handlers import default_registry
from marketing_os.services.job_handlers import AmbiguousExternalWriteError
from marketing_os.jobs.pinterest_control import pinterest_publish_handler
from marketing_os.services.pinterest_connector import (
    FixturePinterestProvider,
    PublishInProgressError,
    ProviderResult,
    claim_publish,
    grant_fixture_authority,
    ingest_performance_snapshot,
    prepare_publication,
    record_publish_result,
    reconcile_unknown,
)
from marketing_os.services.pinterest_shadow import (
    review_manifest_evidence_hash,
    reviewed_publish_request_hash,
)


class PinterestConnectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.engine = create_db_engine(self.root / "phase4.sqlite")
        init_db(self.engine)
        self.factory = session_factory(self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tempdir.cleanup()

    def _seed(self) -> tuple[int, int, int]:
        with self.factory.begin() as session:
            admin = PrincipalRecord(
                principal_type="human",
                username="phase4-admin",
                roles_json='["admin"]',
            )
            product = ProductRecord(name="Phase 4 Mail Carrier Duck")
            intent = SearchIntentRecord(
                intent_key="phase4-mail-carrier-gift",
                normalized_query="mail carrier gift",
                revision_hash=hashlib.sha256(b"phase4-intent").hexdigest(),
            )
            session.add_all([admin, product, intent])
            session.flush()
            page = LandingPageRecord(
                website_id="guide:phase4",
                page_type="guide",
                canonical_path="/reads/phase4-mail-carrier-gifts/",
                canonical_url="https://mattmademe.com/reads/phase4-mail-carrier-gifts/",
                website_revision="phase4-page-1",
                lifecycle_state="published",
                readiness_state="ready",
            )
            session.add(page)
            session.flush()
            cell = CoverageCellRecord(
                dimensional_key="phase4:cell",
                product_id=product.id,
                search_intent_id=intent.id,
                landing_page_id=page.id,
                content_format="static_pin",
                channel="pinterest",
                coverage_state="published",
                freshness_state="fresh",
                source_revision="phase4-source",
            )
            session.add(cell)
            session.flush()
            campaign = ShadowCampaignRecord(
                campaign_id="phase4-campaign",
                coverage_cell_id=cell.id,
                product_id=product.id,
                landing_page_id=page.id,
                source_revision="phase4-source",
                repository_revision="phase4-repo",
                policy_version="pinterest-shadow-v1",
                adapter_provenance_json="{}",
                prompt_version="pinterest-shadow-prompt-v1",
                input_hash=hashlib.sha256(b"phase4-input").hexdigest(),
                lifecycle_state="reviewed",
                page_artifact_json="{}",
            )
            session.add(campaign)
            session.flush()
            shadow = ShadowPublicationRecord(
                campaign_id=campaign.id,
                content_id="phase4-content",
                publication_id="phase4-publication",
                variant_role="search_exact",
                title="Mail Carrier Gift Idea",
                description="A cheerful thank-you gift for the person who delivers every day.",
                board_recommendation="Mail Carrier Gift Ideas",
                canonical_destination_url=page.canonical_url,
                tracked_destination_url=(
                    page.canonical_url
                    + "?utm_source=pinterest&utm_medium=organic_social"
                    "&utm_campaign=phase4-campaign&utm_content=phase4-content"
                    "&publication_id=phase4-publication"
                ),
                page_artifact_json=json.dumps({"reviewAssetUrl": "fixture://phase4.png"}),
                payload_hash=hashlib.sha256(b"phase4-payload").hexdigest(),
                lifecycle_state="ready_for_review",
            )
            connection = PinterestConnectionRecord(
                account_reference="fixture-account",
                credential_reference="fixture://no-secret",
                access_tier="trial",
                scopes_json='["boards:read","pins:read","pins:write"]',
                approved_board_ids_json='["board-mail-carrier"]',
                connection_state="fixture_only",
                provider_contract_version="pinterest-fixture-v1",
                last_verified_at=datetime.now(UTC).replace(tzinfo=None),
            )
            session.add_all([shadow, connection])
            session.flush()
            review_asset = AssetRecord(
                product_id=product.id,
                name="Phase 4 accepted review image",
                asset_type="edited photo",
                source_path=str(self.root / "phase4-review.png"),
                readiness_state="ready",
                file_exists=1,
                file_checksum=hashlib.sha256(b"phase4-review").hexdigest(),
                mime_type="image/png",
                width=1000,
                height=1500,
                asset_role="shadow_review_fixture",
                rights="owned",
                brand_safe="approved",
                review_state="approved",
            )
            session.add(review_asset)
            session.flush()
            manifest = ShadowCreativeManifestRecord(
                publication_id=shadow.id,
                option_number=1,
                source_asset_ids_json="[]",
                source_checksums_json="[]",
                review_asset_id=review_asset.id,
                review_asset_origin="registered_fixture",
                provider_path="fixture",
                model_preference="fixture",
                prompt="fixture",
                negative_prompt="fixture",
                crop_ratio="2:3",
                width=1000,
                height=1500,
                expected_output_path="fixture://phase4.png",
                generation_state="fixture_ready",
                provenance_json="{}",
            )
            review_session = ShadowReviewSessionRecord(
                session_token="phase4-review-session",
                campaign_id=campaign.id,
                reviewer="phase4-reviewer",
                started_at=datetime(2026, 7, 24, 12, 0),
                completed_at=datetime(2026, 7, 24, 12, 5),
                elapsed_seconds=300,
            )
            session.add_all([manifest, review_session])
            session.flush()
            session.add(
                ShadowReviewDecisionRecord(
                    session_id=review_session.id,
                    campaign_id=campaign.id,
                    publication_id=shadow.id,
                    manifest_id=manifest.id,
                    review_asset_id=review_asset.id,
                    decision_kind="package",
                    result="accepted_for_shadow",
                    reason_codes_json="[]",
                    reviewer_note="Accepted fixture package.",
                    reviewed_payload_hash=shadow.payload_hash,
                    reviewed_manifest_hash=review_manifest_evidence_hash(
                        session, manifest, review_asset.id
                    ),
                    reviewed_request_hash=reviewed_publish_request_hash(
                        session, shadow, manifest, review_asset.id
                    ),
                )
            )
            return shadow.id, connection.id, admin.id

    def _prepare_and_grant(self) -> tuple[int, int]:
        shadow_id, connection_id, admin_id = self._seed()
        with self.factory.begin() as session:
            connection = session.get(PinterestConnectionRecord, connection_id)
            publication = prepare_publication(
                session,
                shadow_publication_id=shadow_id,
                connection_id=connection_id,
                board_id="board-mail-carrier",
            )
            grant_fixture_authority(
                session,
                connection=connection,
                principal_id=admin_id,
                policy_class="sampled_low_risk_static_pin",
                expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1),
                reason="Fixture-only Phase 4 contract test.",
            )
            return publication.id, connection_id

    def _publish(
        self,
        publication_id: int,
        provider: FixturePinterestProvider,
    ) -> tuple[str, str]:
        with self.factory.begin() as session:
            _, attempt, request = claim_publish(
                session,
                publication_id=publication_id,
                policy_class="sampled_low_risk_static_pin",
                provider=provider,
            )
            attempt_id = attempt.id
        result = provider.create_pin(request)
        with self.factory.begin() as session:
            publication, _ = record_publish_result(
                session,
                publication_id=publication_id,
                attempt_id=attempt_id,
                result=result,
            )
            return publication.lifecycle_state, result.status

    def test_default_publish_profile_is_hard_disabled_and_value_validated(self) -> None:
        self.assertFalse(capability_report("pinterest_publish", {})["ready"])
        fake_presence = {
            "MARKETING_OS_DB_URL": "sqlite:///not-production.sqlite",
            "MARKETING_OS_SECRET": "configured",
            "PINTEREST_ACCESS_TOKEN": "configured",
            "PINTEREST_ACCOUNT_ID": "configured",
            "PINTEREST_ACCESS_TIER": "trial",
            "PINTEREST_APPROVED_BOARD_IDS": "board",
            "PINTEREST_PROVIDER_CONTRACT_VERSION": "v1",
            "MARKETING_OS_ALERT_WEBHOOK_URL": "configured",
            "MARKETING_OS_ALERT_OWNER": "configured",
            "MARKETING_OS_BACKUP_DESTINATION": "configured",
            "MARKETING_OS_BACKUP_KEY_CUSTODIAN": "configured",
            "MARKETING_OS_DAILY_COST_CENTS": "zero",
            "MARKETING_OS_PINTEREST_PUBLISH_ENABLED": "true",
        }
        self.assertFalse(capability_report("pinterest_publish", fake_presence)["ready"])

    def test_prepare_is_idempotent_and_rejects_unapproved_board(self) -> None:
        shadow_id, connection_id, _ = self._seed()
        with self.factory.begin() as session:
            first = prepare_publication(
                session,
                shadow_publication_id=shadow_id,
                connection_id=connection_id,
                board_id="board-mail-carrier",
            )
            replay = prepare_publication(
                session,
                shadow_publication_id=shadow_id,
                connection_id=connection_id,
                board_id="board-mail-carrier",
            )
            self.assertEqual(first.id, replay.id)
            with self.assertRaisesRegex(ValueError, "approved allowlist"):
                prepare_publication(
                    session,
                    shadow_publication_id=shadow_id,
                    connection_id=connection_id,
                    board_id="unapproved-board",
                )

    def test_prepare_rejects_payload_changed_after_review(self) -> None:
        shadow_id, connection_id, _ = self._seed()
        with self.factory.begin() as session:
            shadow = session.get(ShadowPublicationRecord, shadow_id)
            shadow.tracked_destination_url += "&tampered=1"
        with self.factory.begin() as session:
            with self.assertRaisesRegex(PermissionError, "does not match"):
                prepare_publication(
                    session,
                    shadow_publication_id=shadow_id,
                    connection_id=connection_id,
                    board_id="board-mail-carrier",
                )

    def test_late_conflicting_result_cannot_overwrite_reconciled_identity(self) -> None:
        publication_id, _ = self._prepare_and_grant()
        provider = FixturePinterestProvider()
        with self.factory.begin() as session:
            _, attempt, _ = claim_publish(
                session,
                publication_id=publication_id,
                policy_class="sampled_low_risk_static_pin",
                provider=provider,
            )
            attempt_id = attempt.id
        with self.factory.begin() as session:
            attempt = session.get(PinterestPublishAttemptRecord, attempt_id)
            attempt.claim_expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        with self.factory.begin() as session:
            _, replay_attempt, _ = claim_publish(
                session,
                publication_id=publication_id,
                policy_class="sampled_low_risk_static_pin",
                provider=provider,
            )
            self.assertIsNone(replay_attempt)
        with self.factory.begin() as session:
            reconciled, _ = reconcile_unknown(
                session,
                publication_id=publication_id,
                provider=FixturePinterestProvider(reconcile_status="published"),
            )
            established_id = reconciled.external_pin_id
            established_url = reconciled.external_url
        with self.factory.begin() as session:
            publication, persisted_attempt = record_publish_result(
                session,
                publication_id=publication_id,
                attempt_id=attempt_id,
                result=ProviderResult(
                    "created",
                    external_pin_id="conflicting-late-id",
                    external_url="https://www.pinterest.com/pin/conflicting-late-id/",
                ),
            )
            self.assertEqual("ambiguous", persisted_attempt.state)
            self.assertEqual(established_id, publication.external_pin_id)
            self.assertEqual(established_url, publication.external_url)
            self.assertEqual("published", publication.lifecycle_state)

    def test_fixture_publish_requires_explicit_expiring_authority(self) -> None:
        shadow_id, connection_id, _ = self._seed()
        provider = FixturePinterestProvider()
        with self.factory.begin() as session:
            publication = prepare_publication(
                session,
                shadow_publication_id=shadow_id,
                connection_id=connection_id,
                board_id="board-mail-carrier",
            )
            with self.assertRaisesRegex(PermissionError, "authority grant"):
                claim_publish(
                    session,
                    publication_id=publication.id,
                    policy_class="sampled_low_risk_static_pin",
                    provider=provider,
                )
        self.assertEqual([], provider.create_calls)

    def test_successful_fixture_publish_is_idempotent(self) -> None:
        publication_id, _ = self._prepare_and_grant()
        provider = FixturePinterestProvider()
        self.assertEqual(("published", "created"), self._publish(publication_id, provider))
        with self.factory.begin() as session:
            with self.assertRaisesRegex(ValueError, "requires prepared state"):
                claim_publish(
                    session,
                    publication_id=publication_id,
                    policy_class="sampled_low_risk_static_pin",
                    provider=provider,
                )
        self.assertEqual(1, len(provider.create_calls))

    def test_malformed_provider_success_is_quarantined(self) -> None:
        class MalformedProvider(FixturePinterestProvider):
            def create_pin(self, request):
                self.create_calls.append(request)
                return ProviderResult("created", external_pin_id="", external_url="")

        publication_id, _ = self._prepare_and_grant()
        provider = MalformedProvider()
        self.assertEqual(
            ("publish_unknown", "created"),
            self._publish(publication_id, provider),
        )
        with self.factory() as session:
            publication = session.get(PinterestPublicationRecord, publication_id)
            self.assertEqual("invalid_provider_identity", publication.last_error_code)

    def test_media_delivery_tampering_invalidates_prepared_write(self) -> None:
        publication_id, _ = self._prepare_and_grant()
        with self.factory.begin() as session:
            publication = session.get(PinterestPublicationRecord, publication_id)
            delivery = session.get(PinterestMediaDeliveryRecord, publication.media_delivery_id)
            delivery.media_url = "https://example.com/unreviewed.png"
        with self.factory.begin() as session:
            with self.assertRaisesRegex(PermissionError, "fixture-verified media"):
                claim_publish(
                    session,
                    publication_id=publication_id,
                    policy_class="sampled_low_risk_static_pin",
                    provider=FixturePinterestProvider(),
                )

    def test_ambiguous_write_quarantines_until_reconciliation(self) -> None:
        publication_id, _ = self._prepare_and_grant()
        write_provider = FixturePinterestProvider(create_status="ambiguous")
        self.assertEqual(
            ("publish_unknown", "ambiguous"),
            self._publish(publication_id, write_provider),
        )
        with self.factory.begin() as session:
            with self.assertRaisesRegex(ValueError, "publish_unknown"):
                claim_publish(
                    session,
                    publication_id=publication_id,
                    policy_class="sampled_low_risk_static_pin",
                    provider=write_provider,
                )
        reconcile_provider = FixturePinterestProvider(reconcile_status="published")
        with self.factory.begin() as session:
            publication, result = reconcile_unknown(
                session,
                publication_id=publication_id,
                provider=reconcile_provider,
            )
            self.assertEqual(("published", "published"), (publication.lifecycle_state, result.status))
        self.assertEqual(1, len(write_provider.create_calls))
        with self.factory() as session:
            self.assertEqual(
                1,
                session.scalar(select(func.count()).select_from(PinterestReconciliationRecord)),
            )
            self.assertEqual(
                1,
                session.scalar(
                    select(func.count())
                    .select_from(AutomationJobRecord)
                    .where(AutomationJobRecord.job_type == "pinterest.reconcile")
                ),
            )

    def test_crash_after_submit_recovers_to_unknown_without_second_create(self) -> None:
        publication_id, _ = self._prepare_and_grant()
        provider = FixturePinterestProvider()
        with self.factory.begin() as session:
            _, attempt, _ = claim_publish(
                session,
                publication_id=publication_id,
                policy_class="sampled_low_risk_static_pin",
                provider=provider,
            )
            attempt_id = attempt.id
        with self.factory.begin() as session:
            with self.assertRaises(PublishInProgressError):
                claim_publish(
                    session,
                    publication_id=publication_id,
                    policy_class="sampled_low_risk_static_pin",
                    provider=provider,
                )
        with self.factory.begin() as session:
            attempt = session.get(PinterestPublishAttemptRecord, attempt_id)
            attempt.claim_expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        with self.factory.begin() as session:
            publication, attempt, request = claim_publish(
                session,
                publication_id=publication_id,
                policy_class="sampled_low_risk_static_pin",
                provider=provider,
            )
            self.assertEqual("publish_unknown", publication.lifecycle_state)
            self.assertIsNone(attempt)
            self.assertIsNone(request)
        self.assertEqual([], provider.create_calls)
        with self.factory() as session:
            publication = session.get(PinterestPublicationRecord, publication_id)
            self.assertEqual("publish_unknown", publication.lifecycle_state)
            self.assertEqual(
                1,
                session.scalar(select(func.count()).select_from(PinterestPublishAttemptRecord)),
            )
            self.assertEqual(
                1,
                session.scalar(
                    select(func.count())
                    .select_from(AutomationJobRecord)
                    .where(AutomationJobRecord.job_type == "pinterest.reconcile")
                ),
            )

    def test_absence_requires_two_checks_and_never_recreates_automatically(self) -> None:
        publication_id, _ = self._prepare_and_grant()
        self._publish(publication_id, FixturePinterestProvider(create_status="ambiguous"))
        provider = FixturePinterestProvider(reconcile_status="absent")
        with self.factory.begin() as session:
            publication, _ = reconcile_unknown(
                session,
                publication_id=publication_id,
                provider=provider,
            )
            self.assertEqual("publish_unknown", publication.lifecycle_state)
        with self.factory.begin() as session:
            publication, _ = reconcile_unknown(
                session,
                publication_id=publication_id,
                provider=provider,
            )
            self.assertEqual("confirmed_absent", publication.lifecycle_state)
            with self.assertRaisesRegex(ValueError, "confirmed_absent"):
                claim_publish(
                    session,
                    publication_id=publication_id,
                    policy_class="sampled_low_risk_static_pin",
                    provider=FixturePinterestProvider(),
                )

    def test_durable_handler_commits_unknown_state_before_quarantine_signal(self) -> None:
        publication_id, _ = self._prepare_and_grant()
        with patch.dict(
            "os.environ",
            {
                "MARKETING_OS_DB_URL": f"sqlite:///{self.root / 'phase4.sqlite'}",
                "MARKETING_OS_ENV": "test",
            },
            clear=False,
        ):
            with self.assertRaises(AmbiguousExternalWriteError):
                pinterest_publish_handler(
                    {
                        "publicationId": publication_id,
                        "policyClass": "sampled_low_risk_static_pin",
                        "provider": "fixture",
                        "fixtureStatus": "ambiguous",
                    }
                )
        with self.factory() as session:
            publication = session.get(PinterestPublicationRecord, publication_id)
            self.assertEqual("publish_unknown", publication.lifecycle_state)

    def test_metrics_are_append_only_and_idempotent_by_window_revision(self) -> None:
        publication_id, _ = self._prepare_and_grant()
        provider = FixturePinterestProvider()
        self._publish(publication_id, provider)
        with self.factory.begin() as session:
            start = datetime(2026, 7, 1)
            end = datetime(2026, 7, 8)
            first, created = ingest_performance_snapshot(
                session,
                publication_id=publication_id,
                source_revision="fixture-metrics-1",
                window_start=start,
                window_end=end,
                metrics={"impressions": 100, "saves": 4, "pin_clicks": 3, "outbound_clicks": 2},
            )
            replay, replay_created = ingest_performance_snapshot(
                session,
                publication_id=publication_id,
                source_revision="fixture-metrics-1",
                window_start=start,
                window_end=end,
                metrics={"impressions": 100, "saves": 4, "pin_clicks": 3, "outbound_clicks": 2},
            )
            self.assertTrue(created)
            self.assertFalse(replay_created)
            self.assertEqual(first.id, replay.id)
            with self.assertRaisesRegex(ValueError, "conflicting Pinterest metrics"):
                ingest_performance_snapshot(
                    session,
                    publication_id=publication_id,
                    source_revision="fixture-metrics-1",
                    window_start=start,
                    window_end=end,
                    metrics={"impressions": 999},
                )
        with self.factory() as session:
            self.assertEqual(
                1,
                session.scalar(
                    select(func.count()).select_from(PinterestPerformanceSnapshotRecord)
                ),
            )

    def test_durable_registry_contains_disabled_pinterest_handlers(self) -> None:
        registry = default_registry()
        self.assertIsNotNone(registry.resolve("pinterest.publish", 1))
        self.assertIsNotNone(registry.resolve("pinterest.reconcile", 1))


if __name__ == "__main__":
    unittest.main()
