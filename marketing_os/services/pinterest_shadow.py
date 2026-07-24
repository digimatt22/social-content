from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db_models import (
    AssetRecord,
    CoverageCellRecord,
    DecisionRunRecord,
    PageOpportunityRecord,
    ProductIdentityRecord,
    PublicationOpportunityRecord,
    ShadowCampaignRecord,
    ShadowCreativeManifestRecord,
    ShadowDigestRecord,
    ShadowPayloadLeaseRecord,
    ShadowPublicationRecord,
    ShadowQADecisionRecord,
    ShadowReviewDecisionRecord,
    ShadowReviewSessionRecord,
    utc_now,
)
from .coverage_intelligence import canonical_json, stable_hash
from .growth_contracts import tracked_destination_url


POLICY_PATH = Path("config/pinterest-shadow-policy-v1.json")
SHADOW_NAMESPACE = uuid.UUID("b771fc7c-9892-5068-8798-a496fb09bb5c")
ALLOWED_REVIEW_RESULTS = {"accepted_for_shadow", "revise", "rejected", "exception"}
ALLOWED_DECISION_KINDS = {"copy", "board", "destination", "creative", "package"}


@dataclass(frozen=True)
class ShadowConfig:
    policy: dict[str, Any]
    policy_hash: str


def load_shadow_config(path: str | Path = POLICY_PATH) -> ShadowConfig:
    policy = json.loads(Path(path).read_text(encoding="utf-8"))
    _validate_policy(policy)
    return ShadowConfig(policy=policy, policy_hash=stable_hash(policy))


def generate_shadow_packages(
    session: Session,
    *,
    repository_revision: str | None = None,
    config: ShadowConfig | None = None,
    base_dir: str | Path = ".",
    today: date | None = None,
    product_id: int | None = None,
) -> dict[str, Any]:
    loaded = config or load_shadow_config()
    revision = (repository_revision or os.environ.get("MARKETING_OS_REPOSITORY_REVISION", "")).strip()
    if not revision:
        raise ValueError("repository revision is required for immutable shadow provenance")
    checked_date = today or utc_now().date()
    policy = loaded.policy
    invalidated = _reconcile_active_campaigns(
        session,
        product_id=product_id,
        qa_version=policy["qaVersion"],
        checked_date=checked_date,
    )
    query = (
        select(PageOpportunityRecord, CoverageCellRecord, PublicationOpportunityRecord)
        .join(CoverageCellRecord, PageOpportunityRecord.coverage_cell_id == CoverageCellRecord.id)
        .outerjoin(
            PublicationOpportunityRecord,
            PublicationOpportunityRecord.coverage_cell_id == CoverageCellRecord.id,
        )
        .where(
            PageOpportunityRecord.lifecycle_state == "ranked",
            CoverageCellRecord.channel == "pinterest",
            CoverageCellRecord.suppression_state == "",
        )
        .order_by(
            PageOpportunityRecord.score.desc(),
            PublicationOpportunityRecord.score.desc().nulls_last(),
            PublicationOpportunityRecord.publish_start_date.asc().nulls_last(),
            CoverageCellRecord.product_id,
            CoverageCellRecord.search_intent_id,
            CoverageCellRecord.id,
        )
    )
    if product_id is not None:
        query = query.where(CoverageCellRecord.product_id == product_id)
    result = Counter()
    result["invalidatedCampaigns"] = invalidated
    campaign_ids: list[str] = []
    scanned = 0
    for page_opportunity, cell, _publication_opportunity in session.execute(query):
        if result["campaignsCreated"] >= policy["limits"]["campaignsPerJob"]:
            break
        scanned += 1
        campaign, created = _campaign_for_cell(
            session,
            cell,
            page_opportunity,
            checked_date=checked_date,
            revision=revision,
            config=loaded,
            base_dir=Path(base_dir),
        )
        campaign_ids.append(campaign.campaign_id)
        result["campaignsCreated" if created else "campaignsReplayed"] += 1
        if campaign.lifecycle_state == "ready_for_review":
            result["readyCampaigns"] += 1
        else:
            result["blockedCampaigns"] += 1
    result["candidates"] = scanned
    result["publicWrites"] = 0
    result["providerCalls"] = 0
    return {**dict(result), "campaignIds": campaign_ids}


def _reconcile_active_campaigns(
    session: Session,
    *,
    product_id: int | None,
    qa_version: str,
    checked_date: date,
) -> int:
    query = select(ShadowCampaignRecord).where(
        ShadowCampaignRecord.lifecycle_state.in_({"ready_for_review", "reviewed"})
    )
    if product_id is not None:
        query = query.where(ShadowCampaignRecord.product_id == product_id)
    invalidated = 0
    for campaign in session.scalars(query):
        cell = campaign.coverage_cell
        identity = session.scalar(
            select(ProductIdentityRecord).where(
                ProductIdentityRecord.product_id == campaign.product_id
            )
        )
        opportunity = session.scalar(
            select(PublicationOpportunityRecord).where(
                PublicationOpportunityRecord.coverage_cell_id == cell.id
            )
        )
        page_opportunity = session.scalar(
            select(PageOpportunityRecord).where(
                PageOpportunityRecord.coverage_cell_id == cell.id
            )
        )
        reasons: list[str] = []
        if cell.suppression_state:
            reasons.append(cell.suppression_reason or "coverage_suppressed")
        if cell.freshness_state != "fresh":
            reasons.append("coverage_not_fresh")
        if (
            cell.landing_page is None
            or cell.landing_page.lifecycle_state != "published"
            or cell.landing_page.readiness_state != "ready"
        ):
            reasons.append("destination_no_longer_ready")
        if identity is None or identity.mapping_state != "mapped" or not identity.website_id:
            reasons.append("canonical_product_identity_unresolved")
        if opportunity is None or not opportunity.eligible:
            reasons.append(
                opportunity.eligibility_reason
                if opportunity is not None
                else "publication_opportunity_missing"
            )
        if page_opportunity is None or page_opportunity.lifecycle_state != "ranked":
            reasons.append("page_opportunity_no_longer_ranked")
        if opportunity is not None and opportunity.lifecycle_state != "ranked":
            reasons.append("publication_opportunity_no_longer_ranked")
        if (
            opportunity is not None
            and opportunity.publish_start_date is not None
            and checked_date < opportunity.publish_start_date
        ):
            reasons.append("publication_window_not_open")
        if (
            cell.search_intent.event_date is not None
            and checked_date > cell.search_intent.event_date
        ):
            reasons.append("publication_window_expired")
        if not reasons:
            continue
        publications = list(
            session.scalars(
                select(ShadowPublicationRecord).where(
                    ShadowPublicationRecord.campaign_id == campaign.id,
                    ShadowPublicationRecord.lifecycle_state.in_(
                        {"ready_for_review", "reviewed"}
                    ),
                )
            )
        )
        for publication in publications:
            publication.lifecycle_state = "blocked"
            lease = session.scalar(
                select(ShadowPayloadLeaseRecord).where(
                    ShadowPayloadLeaseRecord.publication_id == publication.id,
                    ShadowPayloadLeaseRecord.released_at.is_(None),
                )
            )
            if lease:
                lease.released_at = utc_now()
            _qa(
                session,
                campaign=campaign,
                publication=publication,
                manifest=None,
                gate="upstream_invalidation",
                passed=False,
                reasons=reasons,
                evidence={
                    "coverageCellId": cell.id,
                    "sourceRevision": cell.source_revision,
                    "mappingRevision": identity.mapping_revision if identity else None,
                },
                version=qa_version,
            )
        campaign.lifecycle_state = "blocked"
        invalidated += 1
    return invalidated


def _campaign_for_cell(
    session: Session,
    cell: CoverageCellRecord,
    page_opportunity: PageOpportunityRecord,
    *,
    checked_date: date,
    revision: str,
    config: ShadowConfig,
    base_dir: Path,
) -> tuple[ShadowCampaignRecord, bool]:
    policy = config.policy
    identity = session.scalar(
        select(ProductIdentityRecord).where(
            ProductIdentityRecord.product_id == cell.product_id
        )
    )
    input_value = {
        "cell": cell.dimensional_key,
        "sourceRevision": cell.source_revision,
        "identityMappingRevision": identity.mapping_revision if identity else None,
        "identityMappingState": identity.mapping_state if identity else "missing",
        "landingPageRevision": (
            cell.landing_page.website_revision if cell.landing_page else ""
        ),
        "landingPageReadiness": (
            cell.landing_page.readiness_state if cell.landing_page else "missing"
        ),
        "policyHash": config.policy_hash,
        "repositoryRevision": revision,
    }
    input_hash = stable_hash(input_value)
    campaign_uuid = _stable_uuid(f"campaign:{input_hash}")
    _lock_shadow_input(session, input_hash)
    existing = session.scalar(
        select(ShadowCampaignRecord).where(ShadowCampaignRecord.campaign_id == campaign_uuid)
    )
    if existing is not None:
        return existing, False

    page = cell.landing_page
    ready_destination = bool(
        page
        and page.lifecycle_state == "published"
        and page.readiness_state == "ready"
        and cell.freshness_state == "fresh"
    )
    page_artifact = (
        {
            "action": "reuse_page",
            "websiteId": page.website_id,
            "path": page.canonical_path,
            "websiteRevision": page.website_revision,
            "verifiedAt": page.checked_at.isoformat(),
        }
        if ready_destination
        else {
            "action": "draft_page",
            "suggestedPath": page.canonical_path if page else _suggested_path(cell),
            "title": f"{cell.search_intent.normalized_query.title()} | MattMadeMe",
            "metaDescription": (
                f"Explore a playful {cell.product.name} gift idea for "
                f"{cell.search_intent.audience or 'an everyday hero'}."
            ),
            "h1": cell.search_intent.normalized_query.title(),
            "intro": (
                f"Meet {cell.product.name}, a small 3D-printed character inspired "
                f"by {cell.search_intent.normalized_query}."
            ),
            "internalLinks": ["/products/", "/reads/"],
            "sourceOpportunityId": page_opportunity.id,
            "sourceScore": page_opportunity.score,
            "reason": page.readiness_reason if page else "missing_destination_page",
            "state": "local_shadow_draft",
        }
    )
    decision_run = session.scalar(
        select(DecisionRunRecord)
        .where(
            DecisionRunRecord.run_type == "coverage.materialize",
            DecisionRunRecord.input_revision == cell.source_revision,
        )
        .order_by(DecisionRunRecord.created_at.desc(), DecisionRunRecord.id.desc())
    )
    campaign = ShadowCampaignRecord(
        campaign_id=campaign_uuid,
        coverage_cell_id=cell.id,
        product_id=cell.product_id,
        landing_page_id=page.id if page else None,
        decision_run_id=decision_run.id if decision_run else None,
        source_revision=cell.source_revision,
        repository_revision=revision,
        policy_version=policy["version"],
        adapter_provenance_json=canonical_json(
            {
                "executionMode": policy["execution"]["mode"],
                "adapters": policy["adapters"],
                "policyHash": config.policy_hash,
                "input": input_value,
            }
        ),
        prompt_version=policy["promptVersion"],
        input_hash=input_hash,
        lifecycle_state="generating",
        page_artifact_json=canonical_json(page_artifact),
    )
    session.add(campaign)
    session.flush()

    publication_opportunity = session.scalar(
        select(PublicationOpportunityRecord).where(
            PublicationOpportunityRecord.coverage_cell_id == cell.id
        )
    )
    pin_eligible = bool(
        ready_destination
        and publication_opportunity
        and publication_opportunity.eligible
        and publication_opportunity.lifecycle_state == "ranked"
        and (
            publication_opportunity.publish_start_date is None
            or checked_date >= publication_opportunity.publish_start_date
        )
    )
    if not pin_eligible:
        campaign.lifecycle_state = "blocked"
        eligibility_reason = (
            publication_opportunity.eligibility_reason
            if publication_opportunity
            else "publication_opportunity_missing"
        )
        gate = (
            "season"
            if eligibility_reason in {"publication_window_not_open", "publication_window_expired"}
            else "destination_readiness"
        )
        _qa(
            session,
            campaign=campaign,
            publication=None,
            manifest=None,
            gate=gate,
            passed=False,
            reasons=[eligibility_reason],
            evidence={"pageArtifact": page_artifact, "pinEligible": False},
            version=policy["qaVersion"],
        )
        return campaign, True

    source_assets = _eligible_assets(session, cell.product_id, policy, base_dir)
    review_asset = _eligible_review_asset(
        session, cell.product_id, policy, base_dir
    )
    publications: list[ShadowPublicationRecord] = []
    for variant in policy["variants"]:
        publication = _build_publication(
            session,
            campaign,
            cell,
            variant,
            page_artifact,
            source_assets,
            review_asset,
            policy,
            base_dir,
            checked_date=checked_date,
            publish_start_date=publication_opportunity.publish_start_date,
        )
        publications.append(publication)
    _supersede_prior_publications(session, campaign, publications)
    campaign.lifecycle_state = (
        "ready_for_review"
        if publications and all(item.lifecycle_state == "ready_for_review" for item in publications)
        else "blocked"
    )
    return campaign, True


def _supersede_prior_publications(
    session: Session,
    campaign: ShadowCampaignRecord,
    new_publications: list[ShadowPublicationRecord],
) -> None:
    for new_publication in new_publications:
        if new_publication.lifecycle_state != "ready_for_review":
            continue
        prior = list(
            session.scalars(
                select(ShadowPublicationRecord)
                .join(
                    ShadowCampaignRecord,
                    ShadowPublicationRecord.campaign_id == ShadowCampaignRecord.id,
                )
                .where(
                    ShadowCampaignRecord.coverage_cell_id == campaign.coverage_cell_id,
                    ShadowCampaignRecord.id != campaign.id,
                    ShadowPublicationRecord.variant_role == new_publication.variant_role,
                    ShadowPublicationRecord.lifecycle_state.in_(
                        {"ready_for_review", "reviewed"}
                    ),
                    ShadowPublicationRecord.payload_hash != new_publication.payload_hash,
                )
                .order_by(ShadowPublicationRecord.created_at, ShadowPublicationRecord.id)
            )
        )
        for old_publication in prior:
            supersede_publication(
                session,
                old_publication.id,
                replacement_publication_id=new_publication.id,
            )
            old_campaign = session.get(
                ShadowCampaignRecord, old_publication.campaign_id
            )
            if old_campaign:
                remaining = session.scalar(
                    select(func.count())
                    .select_from(ShadowPublicationRecord)
                    .where(
                        ShadowPublicationRecord.campaign_id == old_campaign.id,
                        ShadowPublicationRecord.lifecycle_state.in_(
                            {"ready_for_review", "reviewed"}
                        ),
                    )
                )
                if not remaining:
                    old_campaign.lifecycle_state = "superseded"


def _build_publication(
    session: Session,
    campaign: ShadowCampaignRecord,
    cell: CoverageCellRecord,
    variant: str,
    page_artifact: dict[str, Any],
    source_assets: list[AssetRecord],
    review_asset: AssetRecord | None,
    policy: dict[str, Any],
    base_dir: Path,
    *,
    checked_date: date,
    publish_start_date: date | None,
) -> ShadowPublicationRecord:
    intent = cell.search_intent
    product = cell.product
    identity = session.scalar(
        select(ProductIdentityRecord).where(ProductIdentityRecord.product_id == cell.product_id)
    )
    content_id = _stable_uuid(f"content:{campaign.campaign_id}:{variant}")
    publication_id = _stable_uuid(f"publication:{content_id}:pinterest-shadow")
    title, description = _copy_variant(
        variant,
        product.name,
        intent.normalized_query,
        intent.audience,
        intent.occasion,
        policy["format"]["cta"],
    )
    board_key = policy["intentBoardMap"].get(intent.intent_key, "")
    boards = {item["key"]: item["name"] for item in policy["boards"]}
    board = boards.get(board_key, "")
    canonical_url = cell.landing_page.canonical_url
    destination_reasons = _destination_reasons(canonical_url, policy)
    tracked = ""
    if not destination_reasons:
        tracked = tracked_destination_url(
            canonical_url,
            campaign_id=campaign.campaign_id,
            content_id=content_id,
            publication_id=publication_id,
            source=policy["destination"]["utmSource"],
            medium=policy["destination"]["utmMedium"],
        )
    payload = {
        "board": board,
        "title": title,
        "description": description,
        "canonicalLink": canonical_url,
        "format": policy["format"]["contentFormat"],
    }
    publication = ShadowPublicationRecord(
        campaign_id=campaign.id,
        content_id=content_id,
        publication_id=publication_id,
        variant_role=variant,
        title=title,
        description=description,
        board_recommendation=board,
        canonical_destination_url=canonical_url,
        tracked_destination_url=tracked,
        page_artifact_json=canonical_json(page_artifact),
        payload_hash=stable_hash(payload),
        lifecycle_state="generating",
    )
    session.add(publication)
    session.flush()

    combined = f"{title} {description}"
    claim_reasons = _claim_reasons(combined, policy)
    placeholder_reasons = (
        ["missing_required_fact_placeholder"]
        if re.search(policy["claims"]["placeholderPattern"], combined, re.IGNORECASE)
        else []
    )
    copy_scores = _copy_scores(title, description, intent.normalized_query)
    copy_reasons = (
        ["copy_chief_score_below_threshold"] if min(copy_scores.values()) < 3 else []
    )
    board_reasons = [] if board else ["board_unreviewed"]
    asset_reasons = [] if source_assets else ["approved_file_backed_source_asset_missing"]
    review_reasons = _review_asset_reasons(review_asset, policy, base_dir)
    identity_reasons = (
        []
        if identity
        and identity.mapping_state == "mapped"
        and identity.website_id
        else ["canonical_product_identity_unresolved"]
    )
    tracking_reasons = _tracking_reasons(
        tracked,
        campaign.campaign_id,
        content_id,
        publication_id,
        policy,
    )
    manifest = ShadowCreativeManifestRecord(
        publication_id=publication.id,
        option_number=1,
        source_asset_ids_json=canonical_json([item.id for item in source_assets]),
        source_checksums_json=canonical_json([item.file_checksum for item in source_assets]),
        review_asset_id=review_asset.id if review_asset else None,
        review_asset_origin=(
            "fixture_non_provider"
            if review_asset and review_asset.asset_role == "shadow_review_fixture"
            else "real_output_needs_human_review"
            if review_asset
            else ""
        ),
        provider_path=policy["assets"]["providerPath"],
        model_preference=policy["assets"]["modelPreference"],
        prompt=_creative_prompt(product.name, variant, intent.normalized_query),
        negative_prompt=(
            "living motion, altered silhouette, changed colors or accessories, changed print "
            "texture, duplicates, text, logos, watermarks, weapons, unsafe content, generic listing photo"
        ),
        crop_ratio=policy["format"]["aspectRatio"],
        width=policy["format"]["width"],
        height=policy["format"]["height"],
        expected_output_path=f"shadow/{campaign.campaign_id}/{publication_id}.png",
        generation_state="handoff_ready",
        provenance_json=canonical_json(
            {
                "executionMode": policy["execution"]["mode"],
                "providerCalled": False,
                "websiteWritten": False,
                "pinterestWritten": False,
                "fallbackProviderPath": policy["assets"]["fallbackProviderPath"],
                "adapter": policy["adapters"]["creative"],
                "productAccuracy": "unverified_requires_human",
            }
        ),
    )
    session.add(manifest)
    session.flush()
    gate_results = [
        (
            "identity",
            identity_reasons,
            {
                "productId": cell.product_id,
                "websiteId": identity.website_id if identity else None,
                "mappingState": identity.mapping_state if identity else "missing",
            },
        ),
        ("source_claims", claim_reasons, {"claimInventory": _claim_inventory(product.name, intent)}),
        ("missing_required_fact", placeholder_reasons, {"placeholderPresent": bool(placeholder_reasons)}),
        ("destination", destination_reasons, {"canonicalUrl": canonical_url, "trackedUrl": tracked}),
        (
            "tracking",
            tracking_reasons,
            {
                "campaignId": campaign.campaign_id,
                "contentId": content_id,
                "publicationId": publication_id,
            },
        ),
        ("board", board_reasons, {"intentKey": intent.intent_key, "board": board}),
        (
            "copy_chief",
            copy_reasons,
            {
                "titleLength": len(title),
                "descriptionLength": len(description),
                "scores": copy_scores,
            },
        ),
        (
            "season",
            [],
            {
                "publishStart": publish_start_date.isoformat() if publish_start_date else None,
                "checkedDate": checked_date.isoformat(),
                "state": "within_window",
            },
        ),
        (
            "asset_lineage",
            asset_reasons,
            {"assetIds": [item.id for item in source_assets], "checksums": [item.file_checksum for item in source_assets]},
        ),
        (
            "review_fixture",
            review_reasons,
            {
                "assetId": review_asset.id if review_asset else None,
                "origin": review_asset.asset_role if review_asset else "",
                "productAccuracy": "unverified_requires_human",
            },
        ),
        (
            "crop",
            review_reasons,
            {
                "requestedRatio": policy["format"]["aspectRatio"],
                "width": review_asset.width if review_asset else None,
                "height": review_asset.height if review_asset else None,
            },
        ),
        (
            "product_preservation",
            [],
            {"identityLocks": len(source_assets), "productAccuracy": "unverified_requires_human"},
        ),
        (
            "authority",
            [],
            {
                "pinterestWrites": False,
                "websiteWrites": False,
                "providerCalls": False,
                "externalPinId": None,
                "externalBoardId": None,
            },
        ),
    ]
    for gate, reasons, evidence in gate_results:
        _qa(
            session,
            campaign=campaign,
            publication=publication,
            manifest=(
                manifest
                if gate
                in {
                    "asset_lineage",
                    "review_fixture",
                    "crop",
                    "product_preservation",
                    "authority",
                }
                else None
            ),
            gate=gate,
            passed=not reasons,
            reasons=reasons,
            evidence=evidence,
            version=policy["qaVersion"],
        )

    all_reasons = [reason for _, reasons, _ in gate_results for reason in reasons]
    if not all_reasons:
        duplicate = not _acquire_payload_lease(session, publication)
        _qa(
            session,
            campaign=campaign,
            publication=publication,
            manifest=manifest,
            gate="active_payload_uniqueness",
            passed=not duplicate,
            reasons=["duplicate_active_payload"] if duplicate else [],
            evidence={"payloadHash": publication.payload_hash},
            version=policy["qaVersion"],
        )
        if duplicate:
            all_reasons.append("duplicate_active_payload")
    else:
        _qa(
            session,
            campaign=campaign,
            publication=publication,
            manifest=manifest,
            gate="active_payload_uniqueness",
            passed=None,
            reasons=["prerequisite_gate_failed"],
            evidence={"payloadHash": publication.payload_hash},
            version=policy["qaVersion"],
        )
    publication.lifecycle_state = "blocked" if all_reasons else "ready_for_review"
    return publication


def _acquire_payload_lease(session: Session, publication: ShadowPublicationRecord) -> bool:
    existing = session.scalar(
        select(ShadowPayloadLeaseRecord).where(
            ShadowPayloadLeaseRecord.payload_hash == publication.payload_hash
        ).with_for_update()
    )
    if existing is not None:
        if existing.released_at is None and existing.superseded_at is None:
            return existing.publication_id == publication.id
        existing.publication_id = publication.id
        existing.acquired_at = utc_now()
        existing.released_at = None
        existing.superseded_at = None
        return True
    try:
        with session.begin_nested():
            session.add(
                ShadowPayloadLeaseRecord(
                    payload_hash=publication.payload_hash,
                    publication_id=publication.id,
                )
            )
            session.flush()
        return True
    except IntegrityError:
        return False


def supersede_publication(
    session: Session,
    publication_id: int,
    *,
    replacement_publication_id: int | None = None,
) -> ShadowPublicationRecord:
    publication = session.get(ShadowPublicationRecord, publication_id)
    if publication is None:
        raise LookupError("shadow publication was not found")
    if publication.lifecycle_state not in {"ready_for_review", "reviewed"}:
        raise ValueError("only ready or reviewed shadow publications can be superseded")
    publication.lifecycle_state = "superseded"
    publication.superseded_by_id = replacement_publication_id
    lease = session.scalar(
        select(ShadowPayloadLeaseRecord).where(
            ShadowPayloadLeaseRecord.publication_id == publication.id,
            ShadowPayloadLeaseRecord.released_at.is_(None),
        )
    )
    if lease:
        lease.superseded_at = utc_now()
        lease.released_at = utc_now()
    return publication


def start_review_session(
    session: Session,
    campaign_id: str,
    *,
    reviewer: str,
    session_token: str | None = None,
    started_at: datetime | None = None,
) -> ShadowReviewSessionRecord:
    campaign = session.scalar(
        select(ShadowCampaignRecord).where(ShadowCampaignRecord.campaign_id == campaign_id)
    )
    if campaign is None:
        raise LookupError("shadow campaign was not found")
    if not reviewer.strip():
        raise ValueError("reviewer is required")
    token = session_token or _stable_uuid(f"review:{campaign_id}:{reviewer}:{uuid.uuid4()}")
    existing = session.scalar(
        select(ShadowReviewSessionRecord).where(ShadowReviewSessionRecord.session_token == token)
    )
    if existing:
        return existing
    record = ShadowReviewSessionRecord(
        session_token=token,
        campaign_id=campaign.id,
        reviewer=reviewer.strip(),
        started_at=started_at or utc_now(),
    )
    session.add(record)
    session.flush()
    return record


def record_review_decision(
    session: Session,
    session_token: str,
    publication_id: str | None,
    *,
    decision_kind: str,
    result: str,
    reason_codes: list[str] | None = None,
    reviewer_note: str = "",
    manifest_id: int | None = None,
    review_asset_id: int | None = None,
) -> ShadowReviewDecisionRecord:
    review_session = session.scalar(
        select(ShadowReviewSessionRecord).where(
            ShadowReviewSessionRecord.session_token == session_token
        )
    )
    publication = (
        session.scalar(
            select(ShadowPublicationRecord).where(
                ShadowPublicationRecord.publication_id == publication_id
            )
        )
        if publication_id
        else None
    )
    if review_session is None:
        raise LookupError("review session was not found")
    if review_session.completed_at is not None:
        raise ValueError("completed review sessions are immutable")
    if publication_id and publication is None:
        raise LookupError("shadow publication was not found")
    if publication and publication.campaign_id != review_session.campaign_id:
        raise ValueError("publication does not belong to the review session campaign")
    if decision_kind not in ALLOWED_DECISION_KINDS or result not in ALLOWED_REVIEW_RESULTS:
        raise ValueError("unsupported review decision kind or result")
    if publication is None and decision_kind not in {"destination", "package"}:
        raise ValueError("campaign-level page drafts support destination or package decisions")
    if publication is None and (manifest_id is not None or review_asset_id is not None):
        raise ValueError("page-only decisions cannot link a creative manifest or review asset")
    normalized_reasons = sorted(set(reason_codes or []))
    if any(not re.fullmatch(r"[a-z0-9_]{1,80}", item) for item in normalized_reasons):
        raise ValueError("review reason codes must be normalized snake_case labels")
    manifest = session.get(ShadowCreativeManifestRecord, manifest_id) if manifest_id else None
    if manifest_id and (
        publication is None
        or manifest is None
        or manifest.publication_id != publication.id
    ):
        raise ValueError("creative manifest does not belong to the reviewed publication")
    if review_asset_id:
        if manifest is None or manifest.review_asset_id != review_asset_id:
            raise ValueError("review asset must be the publication manifest's linked review image")
    decision = ShadowReviewDecisionRecord(
        session_id=review_session.id,
        campaign_id=review_session.campaign_id,
        publication_id=publication.id if publication else None,
        manifest_id=manifest_id,
        review_asset_id=review_asset_id,
        decision_kind=decision_kind,
        result=result,
        reason_codes_json=canonical_json(normalized_reasons),
        reviewer_note=reviewer_note.strip(),
    )
    session.add(decision)
    session.flush()
    return decision


def complete_review_session(
    session: Session,
    session_token: str,
    *,
    completed_at: datetime | None = None,
) -> dict[str, Any]:
    review_session = session.scalar(
        select(ShadowReviewSessionRecord).where(
            ShadowReviewSessionRecord.session_token == session_token
        )
    )
    if review_session is None:
        raise LookupError("review session was not found")
    decisions = list(
        session.scalars(
            select(ShadowReviewDecisionRecord).where(
                ShadowReviewDecisionRecord.session_id == review_session.id
            )
        )
    )
    if not decisions:
        raise ValueError("a review session requires at least one item decision")
    if review_session.completed_at is None:
        end = completed_at or utc_now()
        if end < review_session.started_at:
            raise ValueError("review completion cannot precede its start")
        review_session.completed_at = end
        review_session.elapsed_seconds = int((end - review_session.started_at).total_seconds())
    counts = Counter(item.result for item in decisions)
    campaign = session.get(ShadowCampaignRecord, review_session.campaign_id)
    publication_ids = (
        set(
            session.scalars(
                select(ShadowPublicationRecord.id).where(
                    ShadowPublicationRecord.campaign_id == review_session.campaign_id
                )
            )
        )
        if campaign
        else set()
    )
    package_decision_ids = {
        item.publication_id for item in decisions if item.decision_kind == "package"
    }
    if campaign and publication_ids and package_decision_ids == publication_ids:
        campaign.lifecycle_state = "reviewed"
    elif campaign and not publication_ids and any(
        item.decision_kind in {"destination", "package"} for item in decisions
    ):
        campaign.lifecycle_state = "reviewed"
    return {
        "sessionToken": review_session.session_token,
        "elapsedSeconds": review_session.elapsed_seconds,
        "decisionCount": len(decisions),
        "reviewedItemCount": len(
            {
                (
                    item.publication_id
                    if item.publication_id is not None
                    else f"campaign:{item.campaign_id}",
                    item.decision_kind,
                )
                for item in decisions
            }
        ),
        "resultCounts": dict(counts),
    }


def shadow_read_model(
    session: Session,
    *,
    campaign_id: str | None = None,
) -> dict[str, Any]:
    query = select(ShadowCampaignRecord).order_by(
        ShadowCampaignRecord.created_at.desc(), ShadowCampaignRecord.id.desc()
    )
    if campaign_id:
        query = query.where(ShadowCampaignRecord.campaign_id == campaign_id)
    campaigns = list(session.scalars(query))
    items = [_serialize_campaign(session, item) for item in campaigns]
    return {
        "campaigns": items,
        "summary": dict(Counter(item["state"] for item in items)),
        "count": len(items),
        "authority": {
            "pinterestWrites": False,
            "websiteWrites": False,
            "providerCalls": False,
            "reviewApprovalIsExternalAuthority": False,
        },
    }


def shadow_exceptions(session: Session) -> dict[str, Any]:
    decisions = list(
        session.scalars(
            select(ShadowQADecisionRecord)
            .where(ShadowQADecisionRecord.result == "fail")
            .order_by(ShadowQADecisionRecord.created_at.desc())
        )
    )
    reason_counts: Counter[str] = Counter()
    items: list[dict[str, Any]] = []
    for decision in decisions:
        reasons = json.loads(decision.reason_codes_json)
        reason_counts.update(reasons)
        items.append(
            {
                "publicationRecordId": decision.publication_id,
                "campaignRecordId": decision.campaign_id,
                "gate": decision.gate_name,
                "reasons": reasons,
                "evidence": json.loads(decision.evidence_json),
                "createdAt": decision.created_at.isoformat(),
            }
        )
    return {"count": len(items), "reasonCounts": dict(reason_counts), "items": items}


def build_weekly_digest(
    session: Session,
    *,
    week: date | None = None,
) -> tuple[ShadowDigestRecord, bool]:
    week_date = week or utc_now().date()
    week_start = week_date.fromordinal(week_date.toordinal() - week_date.weekday())
    period_start = datetime.combine(week_start, datetime.min.time())
    period_end = period_start + timedelta(days=7)
    campaigns = list(
        session.scalars(
            select(ShadowCampaignRecord).where(
                ShadowCampaignRecord.created_at >= period_start,
                ShadowCampaignRecord.created_at < period_end,
            )
        )
    )
    publications = list(
        session.scalars(
            select(ShadowPublicationRecord).where(
                ShadowPublicationRecord.created_at >= period_start,
                ShadowPublicationRecord.created_at < period_end,
            )
        )
    )
    completed_sessions = list(
        session.scalars(
            select(ShadowReviewSessionRecord).where(
                ShadowReviewSessionRecord.completed_at >= period_start,
                ShadowReviewSessionRecord.completed_at < period_end,
            )
        )
    )
    review_decisions = list(
        session.scalars(
            select(ShadowReviewDecisionRecord).where(
                ShadowReviewDecisionRecord.decided_at >= period_start,
                ShadowReviewDecisionRecord.decided_at < period_end,
            )
        )
    )
    session_ids_with_decisions = {item.session_id for item in review_decisions}
    measured_sessions = [
        item
        for item in completed_sessions
        if item.id in session_ids_with_decisions and item.elapsed_seconds is not None
    ]
    elapsed = [item.elapsed_seconds for item in measured_sessions]
    qa_failures = list(
        session.scalars(
            select(ShadowQADecisionRecord).where(
                ShadowQADecisionRecord.result == "fail",
                ShadowQADecisionRecord.created_at >= period_start,
                ShadowQADecisionRecord.created_at < period_end,
            )
        )
    )
    failure_reason_counts: Counter[str] = Counter()
    for item in qa_failures:
        failure_reason_counts.update(json.loads(item.reason_codes_json))
    publications_by_id = {item.id: item for item in publications}
    reviewed_publication_ids = {
        item.publication_id
        for item in review_decisions
        if item.publication_id is not None
    }
    reviewed_publications = (
        list(
            session.scalars(
                select(ShadowPublicationRecord).where(
                    ShadowPublicationRecord.id.in_(reviewed_publication_ids)
                )
            )
        )
        if reviewed_publication_ids
        else []
    )
    reviewed_publications_by_id = {
        item.id: item for item in reviewed_publications
    }
    human_reason_counts: Counter[str] = Counter()
    human_result_reason_counts: Counter[str] = Counter()
    for item in review_decisions:
        reasons = json.loads(item.reason_codes_json)
        human_reason_counts.update(reasons)
        human_result_reason_counts.update(
            f"{item.result}:{reason}" for reason in reasons
        )
    manifests = list(
        session.scalars(
            select(ShadowCreativeManifestRecord).where(
                ShadowCreativeManifestRecord.created_at >= period_start,
                ShadowCreativeManifestRecord.created_at < period_end,
            )
        )
    )
    revision_groups = {
        "adapterVersion": "pinterest-shadow-v1",
        "qaByGate": dict(Counter(item.gate_name for item in qa_failures)),
        "qaByVariant": dict(
            Counter(
                publications_by_id[item.publication_id].variant_role
                for item in qa_failures
                if item.publication_id in publications_by_id
            )
        ),
        "qaByBoard": dict(
            Counter(
                publications_by_id[item.publication_id].board_recommendation or "unreviewed"
                for item in qa_failures
                if item.publication_id in publications_by_id
            )
        ),
        "qaByReviewAsset": dict(
            Counter(
                str(item.review_asset_id) if item.review_asset_id is not None else "missing"
                for item in manifests
                if publications_by_id.get(item.publication_id)
                and publications_by_id[item.publication_id].lifecycle_state == "blocked"
            )
        ),
        "humanByResult": dict(Counter(item.result for item in review_decisions)),
        "humanByDecisionKind": dict(
            Counter(item.decision_kind for item in review_decisions)
        ),
        "humanByReason": dict(human_reason_counts),
        "humanByResultAndReason": dict(human_result_reason_counts),
        "humanByVariant": dict(
            Counter(
                (
                    reviewed_publications_by_id[item.publication_id].variant_role
                    if item.publication_id in reviewed_publications_by_id
                    else "page_only_draft"
                )
                for item in review_decisions
            )
        ),
        "humanByBoard": dict(
            Counter(
                (
                    reviewed_publications_by_id[item.publication_id].board_recommendation
                    or "unreviewed"
                    if item.publication_id in reviewed_publications_by_id
                    else "not_applicable"
                )
                for item in review_decisions
            )
        ),
        "humanByReviewAsset": dict(
            Counter(
                str(item.review_asset_id)
                if item.review_asset_id is not None
                else "none"
                for item in review_decisions
            )
        ),
    }
    payload = {
        "utcWeek": week_start.isoformat(),
        "campaignStates": dict(Counter(item.lifecycle_state for item in campaigns)),
        "publicationStates": dict(Counter(item.lifecycle_state for item in publications)),
        "gateFailures": dict(failure_reason_counts),
        "evidenceMaturity": {
            "fixtureBacked": sum(
                item.review_asset_origin == "fixture_non_provider" for item in manifests
            ),
            "productAccuracy": "unverified_requires_human",
        },
        "reviewEffort": {
            "completedSessions": len(measured_sessions),
            "excludedEmptySessions": len(completed_sessions) - len(measured_sessions),
            "medianElapsedSeconds": _median(elapsed),
            "measuredOnly": True,
        },
        "revisionGroups": revision_groups,
        "learning": {
            "kind": "observational",
            "note": "Shadow QA and reviewer decisions guide revisions; no causal performance claim.",
        },
    }
    input_hash = stable_hash(payload)
    existing = session.scalar(
        select(ShadowDigestRecord).where(
            ShadowDigestRecord.utc_week == week_start,
            ShadowDigestRecord.input_hash == input_hash,
        )
    )
    if existing:
        return existing, False
    ready = sum(item.lifecycle_state in {"ready_for_review", "reviewed"} for item in publications)
    blocked = sum(item.lifecycle_state == "blocked" for item in publications)
    digest = ShadowDigestRecord(
        utc_week=week_start,
        input_hash=input_hash,
        ready_count=ready,
        blocked_count=blocked,
        payload_json=canonical_json(payload),
    )
    session.add(digest)
    session.flush()
    return digest, True


def _serialize_campaign(session: Session, campaign: ShadowCampaignRecord) -> dict[str, Any]:
    publications = list(
        session.scalars(
            select(ShadowPublicationRecord)
            .where(ShadowPublicationRecord.campaign_id == campaign.id)
            .order_by(ShadowPublicationRecord.variant_role)
        )
    )
    return {
        "campaignId": campaign.campaign_id,
        "state": campaign.lifecycle_state,
        "product": {"id": campaign.product.id, "name": campaign.product.name},
        "coverageCellId": campaign.coverage_cell_id,
        "sourceRevision": campaign.source_revision,
        "repositoryRevision": campaign.repository_revision,
        "policyVersion": campaign.policy_version,
        "executionMode": json.loads(campaign.adapter_provenance_json)["executionMode"],
        "provenance": json.loads(campaign.adapter_provenance_json),
        "pageArtifact": json.loads(campaign.page_artifact_json),
        "publications": [_serialize_publication(session, item) for item in publications],
    }


def _serialize_publication(
    session: Session, publication: ShadowPublicationRecord
) -> dict[str, Any]:
    manifest = session.scalar(
        select(ShadowCreativeManifestRecord).where(
            ShadowCreativeManifestRecord.publication_id == publication.id
        )
    )
    qa = list(
        session.scalars(
            select(ShadowQADecisionRecord)
            .where(ShadowQADecisionRecord.publication_id == publication.id)
            .order_by(ShadowQADecisionRecord.id)
        )
    )
    review_asset = (
        session.get(AssetRecord, manifest.review_asset_id)
        if manifest and manifest.review_asset_id
        else None
    )
    return {
        "recordId": publication.id,
        "contentId": publication.content_id,
        "publicationId": publication.publication_id,
        "variant": publication.variant_role,
        "state": publication.lifecycle_state,
        "title": publication.title,
        "description": publication.description,
        "board": publication.board_recommendation,
        "canonicalUrl": publication.canonical_destination_url,
        "trackedUrl": publication.tracked_destination_url,
        "payloadHash": publication.payload_hash,
        "manifest": (
            {
                "id": manifest.id,
                "sourceAssetIds": json.loads(manifest.source_asset_ids_json),
                "sourceChecksums": json.loads(manifest.source_checksums_json),
                "reviewAsset": (
                    {
                        "id": review_asset.id,
                        "name": review_asset.name,
                        "width": review_asset.width,
                        "height": review_asset.height,
                        "checksum": review_asset.file_checksum,
                        "origin": manifest.review_asset_origin,
                        "previewUrl": f"/assets/{review_asset.id}/preview",
                        "productAccuracy": "unverified_requires_human",
                    }
                    if review_asset
                    else None
                ),
                "providerPath": manifest.provider_path,
                "modelPreference": manifest.model_preference,
                "prompt": manifest.prompt,
                "negativePrompt": manifest.negative_prompt,
                "cropRatio": manifest.crop_ratio,
                "width": manifest.width,
                "height": manifest.height,
                "expectedOutputPath": manifest.expected_output_path,
                "generationState": manifest.generation_state,
                "provenance": json.loads(manifest.provenance_json),
            }
            if manifest
            else None
        ),
        "qa": [
            {
                "gate": item.gate_name,
                "version": item.gate_version,
                "result": item.result,
                "reasons": json.loads(item.reason_codes_json),
                "evidence": json.loads(item.evidence_json),
                "manifestId": item.manifest_id,
            }
            for item in qa
        ],
    }


def _eligible_assets(
    session: Session,
    product_id: int,
    policy: dict[str, Any],
    base_dir: Path,
) -> list[AssetRecord]:
    assets = list(
        session.scalars(
            select(AssetRecord)
            .where(
                AssetRecord.product_id == product_id,
                AssetRecord.hidden_from_generation == 0,
                AssetRecord.file_exists == 1,
                AssetRecord.review_state == policy["assets"]["requiredReviewState"],
                AssetRecord.rights.in_(policy["assets"]["allowedRights"]),
                AssetRecord.brand_safe.in_(policy["assets"]["allowedBrandSafety"]),
                AssetRecord.asset_role.not_in(
                    {"shadow_review_fixture", "approved_generated_output"}
                ),
            )
            .order_by(AssetRecord.default_reference.desc(), AssetRecord.id)
            .limit(policy["assets"]["maximumReferences"])
        )
    )
    return [asset for asset in assets if _checksum_matches(asset, base_dir)]


def _eligible_review_asset(
    session: Session,
    product_id: int,
    policy: dict[str, Any],
    base_dir: Path,
) -> AssetRecord | None:
    candidates = list(
        session.scalars(
            select(AssetRecord)
            .where(
                AssetRecord.product_id == product_id,
                AssetRecord.hidden_from_generation == 0,
                AssetRecord.file_exists == 1,
                AssetRecord.review_state == policy["assets"]["requiredReviewState"],
                AssetRecord.rights.in_(policy["assets"]["allowedRights"]),
                AssetRecord.brand_safe.in_(policy["assets"]["allowedBrandSafety"]),
                AssetRecord.asset_role.in_(
                    {"shadow_review_fixture", "approved_generated_output"}
                ),
                AssetRecord.width == policy["format"]["width"],
                AssetRecord.height == policy["format"]["height"],
            )
            .order_by(AssetRecord.id.desc())
        )
    )
    return next(
        (asset for asset in candidates if _checksum_matches(asset, base_dir)),
        None,
    )


def _checksum_matches(asset: AssetRecord, base_dir: Path) -> bool:
    if not asset.file_checksum:
        return False
    candidate = Path(asset.source_path)
    path = candidate if candidate.is_absolute() else base_dir / candidate
    if not path.is_file():
        return False
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest == asset.file_checksum


def _review_asset_reasons(
    asset: AssetRecord | None,
    policy: dict[str, Any],
    base_dir: Path,
) -> list[str]:
    if asset is None:
        return ["checksummed_1000x1500_review_fixture_missing"]
    reasons: list[str] = []
    if asset.width != policy["format"]["width"] or asset.height != policy["format"]["height"]:
        reasons.append("review_fixture_dimensions_invalid")
    if asset.asset_role not in {"shadow_review_fixture", "approved_generated_output"}:
        reasons.append("review_fixture_origin_invalid")
    if not _checksum_matches(asset, base_dir):
        reasons.append("review_fixture_checksum_invalid")
    return reasons


def _destination_reasons(url: str, policy: dict[str, Any]) -> list[str]:
    if not url:
        return ["destination_missing"]
    parsed = urlparse(url)
    allowed = urlparse(policy["destination"]["allowedOrigin"])
    reasons: list[str] = []
    if parsed.scheme != allowed.scheme or parsed.netloc != allowed.netloc:
        reasons.append("destination_origin_unapproved")
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    managed = {
        "utm_source": policy["destination"]["utmSource"],
        "utm_medium": policy["destination"]["utmMedium"],
    }
    if any(name in query and query[name] != value for name, value in managed.items()):
        reasons.append("destination_attribution_conflict")
    if any(name in query for name in {"utm_campaign", "utm_content", "publication_id"}):
        reasons.append("destination_attribution_conflict")
    return sorted(set(reasons))


def _copy_variant(
    variant: str,
    product_name: str,
    query: str,
    audience: str,
    occasion: str,
    cta: str,
) -> tuple[str, str]:
    product_type = "3D-Printed Duck"
    if variant == "search_exact":
        title = f"{query.title()}: {product_name}"
        lead = f"Explore {product_name}, a small {product_type.lower()} designed around {query}."
    elif variant == "gift_context":
        context = occasion.strip() or "appreciation gift"
        title = f"{product_name} for a Thoughtful {context.title()}"
        lead = f"A playful {product_type.lower()} idea for a thoughtful {context.lower()}."
    else:
        recipient = audience.strip() or "everyday hero"
        title = f"A Small Thank-You for {recipient.title()}"
        lead = f"Celebrate a {recipient.lower()} with {product_name}, a characterful {product_type.lower()}."
    description = f"{lead} {cta}"
    return title[:90].rstrip(), description[:400].rstrip()


def _claim_reasons(combined: str, policy: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    for pattern in policy["claims"]["bannedPatterns"]:
        if re.search(pattern, combined, re.IGNORECASE):
            reasons.append("unsupported_claim")
    for term in policy["claims"]["bannedProductTerms"]:
        if term.casefold() in combined.casefold():
            reasons.append("banned_product_term")
    if "#" in combined:
        reasons.append("hashtags_not_allowed")
    return sorted(set(reasons))


def _tracking_reasons(
    url: str,
    campaign_id: str,
    content_id: str,
    publication_id: str,
    policy: dict[str, Any],
) -> list[str]:
    if not url:
        return ["tracking_url_missing"]
    query = dict(parse_qsl(urlparse(url).query, keep_blank_values=True))
    expected = {
        "utm_source": policy["destination"]["utmSource"],
        "utm_medium": policy["destination"]["utmMedium"],
        "utm_campaign": campaign_id,
        "utm_content": content_id,
        "publication_id": publication_id,
    }
    return ["tracking_contract_incomplete"] if any(query.get(key) != value for key, value in expected.items()) else []


def _claim_inventory(product_name: str, intent) -> dict[str, Any]:
    return {
        "productName": product_name,
        "productType": "3D-printed duck",
        "searchIntent": intent.normalized_query,
        "audience": intent.audience,
        "occasion": intent.occasion,
        "excludedPrivateFacts": ["sales", "rankings", "private_reviews"],
    }


def _copy_scores(title: str, description: str, query: str) -> dict[str, int]:
    return {
        "sourceDiscipline": 5 if title and description else 1,
        "searchFit": 5 if (not query or query.casefold() in f"{title} {description}".casefold()) else 3,
        "body": 5 if 40 <= len(description) <= 400 else 2,
        "cta": 5 if "mattmademe.com" in description.casefold() else 2,
        "brandVoice": 4,
    }


def _creative_prompt(product_name: str, variant: str, query: str) -> str:
    return (
        f"Create a vertical Pinterest scene featuring @img1, the exact 2.5-inch inanimate "
        f"3D-printed {product_name}. Use a full-scale environment aligned to {query} and "
        f"the {variant} story. Preserve silhouette, colors, accessories, print texture, "
        "facial details, proportions, material, scale, and believable grounding. "
        "No text overlay. Treat every additional reference as an identity lock."
    )


def _qa(
    session: Session,
    *,
    campaign: ShadowCampaignRecord | None = None,
    publication: ShadowPublicationRecord | None,
    manifest: ShadowCreativeManifestRecord | None,
    gate: str,
    passed: bool | None,
    reasons: list[str],
    evidence: dict[str, Any],
    version: str,
) -> None:
    session.add(
        ShadowQADecisionRecord(
            campaign_id=(
                campaign.id
                if campaign is not None
                else publication.campaign_id
                if publication is not None
                else None
            ),
            publication_id=publication.id if publication else None,
            manifest_id=manifest.id if manifest else None,
            gate_name=gate,
            gate_version=version,
            result="not_evaluated" if passed is None else "pass" if passed else "fail",
            reason_codes_json=canonical_json(sorted(set(filter(None, reasons)))),
            evidence_json=canonical_json(evidence),
        )
    )


def _validate_policy(policy: dict[str, Any]) -> None:
    required = {
        "version", "review", "execution", "variants", "format", "destination",
        "boards", "intentBoardMap", "claims", "assets", "limits", "adapters",
        "promptVersion", "qaVersion",
    }
    if set(policy) != required:
        raise ValueError("Pinterest shadow policy fields do not match the reviewed schema")
    if policy["version"] != "pinterest-shadow-v1" or policy["review"]["status"] != "passed":
        raise ValueError("Pinterest shadow policy must be the independently reviewed v1")
    if policy["execution"] != {
        "mode": "deterministic_local_adapter",
        "publicWrites": False,
        "providerCalls": False,
        "websiteWrites": False,
    }:
        raise ValueError("Phase 3 execution authority must remain local and write-free")
    if policy["variants"] != ["search_exact", "gift_context", "audience_context"]:
        raise ValueError("Phase 3 variant contract changed")
    if policy["format"]["width"] != 1000 or policy["format"]["height"] != 1500:
        raise ValueError("Pinterest shadow creative must be 1000x1500")
    if (
        policy["format"].get("contentFormat") != "static_pin"
        or policy["format"].get("aspectRatio") != "2:3"
        or policy["format"].get("textOverlay") is not False
        or policy["format"].get("titleMaxCharacters") != 90
        or policy["format"].get("descriptionMaxCharacters") != 400
        or policy["format"].get("hashtagsAllowed") is not False
        or not str(policy["format"].get("cta", "")).strip()
    ):
        raise ValueError("Pinterest shadow format fields do not match the reviewed schema")
    if policy["destination"] != {
        "allowedOrigin": "https://mattmademe.com",
        "utmSource": "pinterest",
        "utmMedium": "organic_social",
    }:
        raise ValueError("Pinterest shadow destination contract changed")
    boards = {item["key"] for item in policy["boards"] if item.get("shadowOnly") is True}
    if not boards or not set(policy["intentBoardMap"].values()).issubset(boards):
        raise ValueError("intent board mappings must target reviewed shadow-only boards")
    board_names = {item.get("name") for item in policy["boards"]}
    if board_names != {
        "Everyday Heroes Gift Ideas",
        "Mail Carrier Gift Ideas",
        "First Responder Gift Ideas",
    }:
        raise ValueError("Pinterest shadow board allowlist changed")
    try:
        re.compile(policy["claims"]["placeholderPattern"])
        for pattern in policy["claims"]["bannedPatterns"]:
            re.compile(pattern)
    except (KeyError, TypeError, re.error) as exc:
        raise ValueError("Pinterest shadow claim patterns are invalid") from exc
    if "rubber duck" not in {
        str(item).casefold() for item in policy["claims"]["bannedProductTerms"]
    }:
        raise ValueError("Pinterest shadow banned product terminology changed")
    if (
        policy["assets"].get("maximumReferences") != 4
        or not policy["assets"].get("allowedRights")
        or not policy["assets"].get("allowedBrandSafety")
        or policy["assets"].get("requiredReviewState") != "approved"
        or not policy["assets"].get("modelPreference")
        or not policy["assets"].get("providerPath")
    ):
        raise ValueError("Pinterest shadow asset contract is invalid")
    for adapter in policy["adapters"].values():
        if (
            not str(adapter.get("name", "")).strip()
            or not str(adapter.get("version", "")).strip()
            or not str(adapter.get("informedBy", "")).strip()
            or not re.fullmatch(r"[0-9a-f]{64}", str(adapter.get("sourceHash", "")))
        ):
            raise ValueError("Pinterest shadow adapter provenance is invalid")
    if policy["limits"]["campaignsPerJob"] > 20 or policy["limits"]["artifactsPerJob"] > 60:
        raise ValueError("Phase 3 job budget exceeds its reviewed limit")


def _stable_uuid(value: str) -> str:
    return str(uuid.uuid5(SHADOW_NAMESPACE, value))


def _lock_shadow_input(session: Session, input_hash: str) -> None:
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        lock_id = int(input_hash[:15], 16)
        session.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})


def _suggested_path(cell: CoverageCellRecord) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", cell.search_intent.normalized_query.casefold()).strip("-")
    return f"/reads/{slug}/"


def _median(values: list[int]) -> int | None:
    if not values:
        return None
    items = sorted(values)
    middle = len(items) // 2
    if len(items) % 2:
        return items[middle]
    return (items[middle - 1] + items[middle]) // 2
