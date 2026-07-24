from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db_models import (
    AssetRecord,
    AuditEventRecord,
    PinterestAuthorityGrantRecord,
    PinterestConnectionRecord,
    PinterestMediaDeliveryRecord,
    PinterestPerformanceSnapshotRecord,
    PinterestPublishAttemptRecord,
    PinterestPublicationRecord,
    PinterestReconciliationRecord,
    PrincipalRecord,
    ShadowCreativeManifestRecord,
    ShadowPublicationRecord,
    ShadowReviewDecisionRecord,
    ShadowReviewSessionRecord,
)
from .pinterest_shadow import (
    review_manifest_evidence_hash,
    reviewed_publish_request_hash,
)


REQUIRED_WRITE_SCOPES = {"boards:read", "pins:read", "pins:write"}
LIVE_ENABLE_VALUE = "EXPLICITLY_ENABLED"
DEPLOYMENT_APPROVAL_VALUE = "EXPLICITLY_APPROVED"


class PublishInProgressError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class PublishRequest:
    idempotency_key: str
    board_id: str
    title: str
    description: str
    destination_url: str
    media_url: str
    media_checksum: str
    approved_asset_location: str


@dataclass(frozen=True)
class ProviderResult:
    status: str
    external_pin_id: str = ""
    external_url: str = ""
    retry_after_seconds: int | None = None
    error_code: str = ""
    error_message: str = ""
    raw: dict[str, Any] | None = None


class PinterestProvider(Protocol):
    contract_version: str
    fixture_only: bool

    def create_pin(self, request: PublishRequest) -> ProviderResult: ...

    def find_pin(self, idempotency_key: str) -> ProviderResult: ...


class FixturePinterestProvider:
    """Deterministic provider used for contract and recovery tests only."""

    contract_version = "pinterest-fixture-v1"
    fixture_only = True

    def __init__(
        self,
        *,
        create_status: str = "created",
        reconcile_status: str = "published",
    ) -> None:
        self.create_status = create_status
        self.reconcile_status = reconcile_status
        self.create_calls: list[PublishRequest] = []
        self.reconcile_calls: list[str] = []

    def create_pin(self, request: PublishRequest) -> ProviderResult:
        self.create_calls.append(request)
        pin_id = hashlib.sha256(request.idempotency_key.encode()).hexdigest()[:18]
        if self.create_status == "created":
            return ProviderResult(
                "created",
                external_pin_id=pin_id,
                external_url=f"https://www.pinterest.com/pin/{pin_id}/",
                raw={"fixture": True, "id": pin_id},
            )
        if self.create_status == "ambiguous":
            return ProviderResult(
                "ambiguous",
                error_code="timeout_after_submit",
                error_message="Fixture timed out after accepting the request.",
                raw={"fixture": True},
            )
        if self.create_status == "throttled":
            return ProviderResult(
                "throttled",
                retry_after_seconds=60,
                error_code="rate_limited",
                error_message="Fixture rate limit.",
            )
        if self.create_status in {"auth_error", "validation_error", "server_error"}:
            return ProviderResult(
                self.create_status,
                error_code=self.create_status,
                error_message=f"Fixture {self.create_status}.",
            )
        raise ValueError(f"unknown fixture create status: {self.create_status}")

    def find_pin(self, idempotency_key: str) -> ProviderResult:
        self.reconcile_calls.append(idempotency_key)
        pin_id = hashlib.sha256(idempotency_key.encode()).hexdigest()[:18]
        if self.reconcile_status == "published":
            return ProviderResult(
                "published",
                external_pin_id=pin_id,
                external_url=f"https://www.pinterest.com/pin/{pin_id}/",
                raw={"fixture": True, "id": pin_id},
            )
        if self.reconcile_status in {"absent", "still_unknown", "provider_error"}:
            return ProviderResult(
                self.reconcile_status,
                error_code="" if self.reconcile_status == "absent" else self.reconcile_status,
                error_message="" if self.reconcile_status == "absent" else f"Fixture {self.reconcile_status}.",
                raw={"fixture": True},
            )
        raise ValueError(f"unknown fixture reconciliation status: {self.reconcile_status}")


def authority_scope_hash(connection: PinterestConnectionRecord, policy_class: str) -> str:
    value = {
        "accountReference": connection.account_reference,
        "approvedBoardIds": sorted(json.loads(connection.approved_board_ids_json or "[]")),
        "contractVersion": connection.provider_contract_version,
        "policyClass": policy_class,
        "scopes": sorted(json.loads(connection.scopes_json or "[]")),
    }
    return hashlib.sha256(_json(value).encode()).hexdigest()


def grant_fixture_authority(
    session: Session,
    *,
    connection: PinterestConnectionRecord,
    principal_id: int,
    policy_class: str,
    expires_at: datetime,
    reason: str,
) -> PinterestAuthorityGrantRecord:
    principal = session.get(PrincipalRecord, principal_id)
    roles = set(json.loads(principal.roles_json or "[]")) if principal else set()
    if principal is None or not principal.active or "admin" not in roles:
        raise PermissionError("active admin principal is required")
    if connection.connection_state != "fixture_only":
        raise ValueError("fixture grants can only target a fixture-only connection")
    if expires_at <= _now():
        raise ValueError("authority expiry must be in the future")
    if not reason.strip():
        raise ValueError("authority reason is required")
    grant = PinterestAuthorityGrantRecord(
        policy_class=policy_class,
        principal_id=principal_id,
        scope_hash=authority_scope_hash(connection, policy_class),
        reason=reason.strip(),
        expires_at=expires_at,
    )
    session.add(grant)
    session.flush()
    _audit(
        session,
        principal_id,
        "pinterest_fixture_authority_granted",
        "pinterest_authority_grant",
        str(grant.id),
        {"policyClass": policy_class, "expiresAt": expires_at.isoformat()},
    )
    return grant


def prepare_publication(
    session: Session,
    *,
    shadow_publication_id: int,
    connection_id: int,
    board_id: str,
    media_delivery_id: int | None = None,
) -> PinterestPublicationRecord:
    shadow = session.scalar(
        select(ShadowPublicationRecord)
        .where(ShadowPublicationRecord.id == shadow_publication_id)
        .with_for_update()
    )
    connection = session.get(PinterestConnectionRecord, connection_id)
    if shadow is None or connection is None:
        raise LookupError("shadow publication or Pinterest connection was not found")
    if shadow.lifecycle_state not in {"ready_for_review", "reviewed"}:
        raise ValueError("only active reviewed shadow publications can be prepared")
    approval = _accepted_review_evidence(session, shadow)
    approved_boards = set(json.loads(connection.approved_board_ids_json or "[]"))
    if board_id not in approved_boards:
        raise ValueError("board is not in the connection's approved allowlist")

    review_asset = session.get(AssetRecord, approval.review_asset_id)
    if review_asset is None:
        raise PermissionError("approved review asset is unavailable")
    if connection.connection_state == "fixture_only":
        delivery = session.scalar(
            select(PinterestMediaDeliveryRecord).where(
                PinterestMediaDeliveryRecord.connection_id == connection.id,
                PinterestMediaDeliveryRecord.review_asset_id == review_asset.id,
                PinterestMediaDeliveryRecord.content_checksum == review_asset.file_checksum,
                PinterestMediaDeliveryRecord.content_revision == "fixture-v1",
            )
        )
        if delivery is None:
            delivery = PinterestMediaDeliveryRecord(
                connection_id=connection.id,
                review_asset_id=review_asset.id,
                media_url=f"fixture://shadow-publication/{shadow.id}/review-asset",
                content_checksum=review_asset.file_checksum,
                content_revision="fixture-v1",
                delivery_state="fixture_verified",
                verification_json=_json({"fixture": True, "networkCalls": 0}),
                verified_at=_now(),
            )
            session.add(delivery)
            session.flush()
    else:
        if media_delivery_id is None:
            raise ValueError("live preparation requires a verified media delivery record")
        delivery = session.get(PinterestMediaDeliveryRecord, media_delivery_id)
    _validate_media_delivery(connection, approval, delivery, review_asset)
    key = f"pinterest:{shadow.publication_id}:{shadow.payload_hash}:{board_id}"
    request_json = _json(
        _request_payload(
            session,
            shadow,
            approval,
                key,
                board_id,
                delivery.media_url,
            )
    )
    existing = session.scalar(
        select(PinterestPublicationRecord).where(
            PinterestPublicationRecord.shadow_publication_id == shadow.id
        )
    )
    if existing is not None:
        if (
            existing.payload_hash != shadow.payload_hash
            or existing.board_id != board_id
            or existing.connection_id != connection.id
            or existing.approval_decision_id != approval.id
            or existing.media_delivery_id != delivery.id
            or existing.provider_request_json != request_json
        ):
            raise ValueError("prepared publication no longer matches its immutable source")
        return existing

    publication = PinterestPublicationRecord(
        shadow_publication_id=shadow.id,
        connection_id=connection.id,
        approval_decision_id=approval.id,
        media_delivery_id=delivery.id,
        external_idempotency_key=key,
        payload_hash=shadow.payload_hash,
        board_id=board_id,
        provider_request_json=request_json,
    )
    session.add(publication)
    session.flush()
    return publication


def claim_publish(
    session: Session,
    *,
    publication_id: int,
    policy_class: str,
    provider: PinterestProvider,
    environment: dict[str, str] | None = None,
) -> tuple[
    PinterestPublicationRecord,
    PinterestPublishAttemptRecord | None,
    PublishRequest | None,
]:
    publication = session.scalar(
        select(PinterestPublicationRecord)
        .where(PinterestPublicationRecord.id == publication_id)
        .with_for_update()
    )
    if publication is None:
        raise LookupError("Pinterest publication was not found")
    if publication.lifecycle_state != "prepared":
        if publication.lifecycle_state == "submitted":
            latest_attempt = session.scalar(
                select(PinterestPublishAttemptRecord)
                .where(
                    PinterestPublishAttemptRecord.pinterest_publication_id == publication.id,
                    PinterestPublishAttemptRecord.state == "submitted",
                )
                .order_by(PinterestPublishAttemptRecord.attempt_number.desc())
                .limit(1)
            )
            if latest_attempt is not None and latest_attempt.claim_expires_at > _now():
                raise PublishInProgressError("Pinterest publication attempt is still in progress")
            publication.lifecycle_state = "publish_unknown"
            publication.last_error_code = "stale_submission"
            publication.last_error = "A prior submitted attempt must reconcile before another write."
            _enqueue_reconciliation(session, publication)
            session.flush()
            return publication, None, None
        raise ValueError(
            f"Create Pin requires prepared state; current state is {publication.lifecycle_state}"
        )
    shadow = publication.shadow_publication
    if (
        shadow.lifecycle_state not in {"ready_for_review", "reviewed"}
        or shadow.payload_hash != publication.payload_hash
    ):
        raise PermissionError("reviewed immutable shadow source is no longer valid")
    approval = _accepted_review_evidence(session, shadow)
    if approval.id != publication.approval_decision_id:
        raise PermissionError("publication approval evidence has changed")
    review_asset = session.get(AssetRecord, approval.review_asset_id)
    _validate_media_delivery(
        publication.connection,
        approval,
        publication.media_delivery,
        review_asset,
    )
    approved_boards = set(json.loads(publication.connection.approved_board_ids_json or "[]"))
    if publication.board_id not in approved_boards:
        raise PermissionError("prepared board is no longer approved")
    request = PublishRequest(**json.loads(publication.provider_request_json))
    expected_request_json = _json(
        _request_payload(
            session,
            shadow,
            approval,
            publication.external_idempotency_key,
            publication.board_id,
            publication.media_delivery.media_url,
        )
    )
    if expected_request_json != publication.provider_request_json:
        raise PermissionError("prepared outbound request no longer matches approved evidence")
    if request.media_url != publication.media_delivery.media_url:
        raise PermissionError("prepared media URL no longer matches verified delivery")

    connection = publication.connection
    _require_authority(
        session,
        connection=connection,
        policy_class=policy_class,
        provider=provider,
        environment=environment,
    )
    _validate_request_media(request, provider)
    attempt_number = (
        session.scalar(
            select(func.count(PinterestPublishAttemptRecord.id)).where(
                PinterestPublishAttemptRecord.pinterest_publication_id == publication.id
            )
        )
        or 0
    ) + 1
    attempt = PinterestPublishAttemptRecord(
        pinterest_publication_id=publication.id,
        attempt_number=attempt_number,
        request_hash=hashlib.sha256(publication.provider_request_json.encode()).hexdigest(),
        state="submitted",
        claim_expires_at=_now() + timedelta(minutes=5),
    )
    publication.lifecycle_state = "submitted"
    publication.submitted_at = _now()
    session.add(attempt)
    session.flush()
    return publication, attempt, request


def record_publish_result(
    session: Session,
    *,
    publication_id: int,
    attempt_id: int,
    result: ProviderResult,
) -> tuple[PinterestPublicationRecord, PinterestPublishAttemptRecord]:
    publication = session.scalar(
        select(PinterestPublicationRecord)
        .where(PinterestPublicationRecord.id == publication_id)
        .with_for_update()
    )
    attempt = session.get(PinterestPublishAttemptRecord, attempt_id)
    if publication is None or attempt is None or attempt.pinterest_publication_id != publication.id:
        raise LookupError("Pinterest publication attempt was not found")
    if attempt.state != "submitted":
        raise ValueError("Pinterest publish attempt is already terminal")
    checked_at = _now()
    attempt.provider_status = result.status
    attempt.provider_response_json = _json(asdict(result))
    attempt.error_code = result.error_code
    attempt.completed_at = checked_at
    publication.provider_response_json = attempt.provider_response_json

    identity_error = (
        _provider_identity_error(session, publication, result)
        if result.status == "created"
        else ""
    )
    if publication.lifecycle_state != "submitted":
        matching_published_identity = (
            publication.lifecycle_state == "published"
            and result.status == "created"
            and publication.external_pin_id == result.external_pin_id
            and publication.external_url == result.external_url
            and not identity_error
        )
        unresolved_late_success = (
            publication.lifecycle_state == "publish_unknown"
            and result.status == "created"
            and not identity_error
        )
        if matching_published_identity:
            attempt.state = "published"
            session.flush()
            return publication, attempt
        if not unresolved_late_success:
            attempt.state = "ambiguous"
            attempt.error_code = "late_result_conflict"
            publication.last_error_code = "late_result_conflict"
            publication.last_error = (
                "Late provider evidence conflicted with already reconciled publication state."
            )
            session.flush()
            return publication, attempt

    if identity_error:
        attempt.state = "ambiguous"
        publication.lifecycle_state = "publish_unknown"
        publication.last_error_code = "invalid_provider_identity"
        publication.last_error = identity_error
        _enqueue_reconciliation(session, publication)
    elif result.status == "created":
        attempt.state = "published"
        publication.lifecycle_state = "published"
        publication.external_pin_id = result.external_pin_id
        publication.external_url = result.external_url
        publication.published_at = checked_at
        publication.reconciled_at = checked_at
        publication.last_error_code = ""
        publication.last_error = ""
    elif result.status == "ambiguous":
        attempt.state = "ambiguous"
        publication.lifecycle_state = "publish_unknown"
        publication.last_error_code = result.error_code or "ambiguous_write"
        publication.last_error = result.error_message
        _enqueue_reconciliation(session, publication)
    elif result.status in {"auth_error", "validation_error"}:
        attempt.state = "failed"
        publication.lifecycle_state = "failed"
        publication.last_error_code = result.error_code or result.status
        publication.last_error = result.error_message
    elif result.status in {"throttled", "server_error"}:
        attempt.state = "retryable_failure"
        publication.lifecycle_state = "prepared"
        publication.last_error_code = result.error_code or result.status
        publication.last_error = result.error_message
    else:
        raise ValueError(f"unsupported provider status: {result.status}")
    session.flush()
    return publication, attempt


def reconcile_unknown(
    session: Session,
    *,
    publication_id: int,
    provider: PinterestProvider,
) -> tuple[PinterestPublicationRecord, ProviderResult]:
    publication = session.scalar(
        select(PinterestPublicationRecord)
        .where(PinterestPublicationRecord.id == publication_id)
        .with_for_update()
    )
    if publication is None:
        raise LookupError("Pinterest publication was not found")
    if publication.lifecycle_state != "publish_unknown":
        raise ValueError("only publish_unknown records can be reconciled")
    connection = publication.connection
    if provider.contract_version != connection.provider_contract_version:
        raise PermissionError("reconciliation provider contract does not match the connection")
    if provider.fixture_only and connection.connection_state != "fixture_only":
        raise PermissionError("fixture reconciliation requires fixture-only connection")
    if not provider.fixture_only and connection.connection_state != "verified":
        raise PermissionError("live reconciliation requires a verified connection")
    result = provider.find_pin(publication.external_idempotency_key)
    identity_error = (
        _provider_identity_error(session, publication, result)
        if result.status == "published"
        else ""
    )
    if identity_error:
        result = ProviderResult(
            "provider_error",
            error_code="invalid_provider_identity",
            error_message=identity_error,
            raw=result.raw,
        )
    prior_attempt_count = (
        session.scalar(
            select(func.count(PinterestReconciliationRecord.id)).where(
                PinterestReconciliationRecord.pinterest_publication_id == publication.id
            )
        )
        or 0
    )
    attempt_number = prior_attempt_count + 1
    prior_absent_count = (
        session.scalar(
            select(func.count(PinterestReconciliationRecord.id)).where(
                PinterestReconciliationRecord.pinterest_publication_id == publication.id,
                PinterestReconciliationRecord.result == "absent",
            )
        )
        or 0
    )
    session.add(
        PinterestReconciliationRecord(
            pinterest_publication_id=publication.id,
            attempt_number=attempt_number,
            result=result.status,
            provider_response_json=_json(asdict(result)),
        )
    )
    publication.provider_response_json = _json(asdict(result))
    if result.status == "published":
        publication.lifecycle_state = "published"
        publication.external_pin_id = result.external_pin_id
        publication.external_url = result.external_url
        publication.published_at = _now()
        publication.reconciled_at = _now()
        publication.last_error_code = ""
        publication.last_error = ""
    elif result.status == "absent":
        if prior_absent_count >= 1:
            publication.lifecycle_state = "confirmed_absent"
            publication.reconciled_at = _now()
        else:
            publication.last_error_code = "absence_not_mature"
            publication.last_error = "A second independent absence check is required."
    elif result.status in {"still_unknown", "provider_error"}:
        publication.last_error_code = result.error_code or result.status
        publication.last_error = result.error_message
    else:
        raise ValueError(f"unsupported reconciliation status: {result.status}")
    session.flush()
    return publication, result


def ingest_performance_snapshot(
    session: Session,
    *,
    publication_id: int,
    source_revision: str,
    window_start: datetime,
    window_end: datetime,
    metrics: dict[str, int],
    raw_metrics: dict[str, Any] | None = None,
) -> tuple[PinterestPerformanceSnapshotRecord, bool]:
    publication = session.get(PinterestPublicationRecord, publication_id)
    if publication is None:
        raise LookupError("Pinterest publication was not found")
    if publication.lifecycle_state != "published" or not publication.external_pin_id:
        raise ValueError("metrics require a reconciled published Pin")
    if not source_revision.strip():
        raise ValueError("metric source revision is required")
    if window_end <= window_start:
        raise ValueError("metric window must end after it starts")
    values = {
        key: int(metrics.get(key, 0))
        for key in ("impressions", "saves", "pin_clicks", "outbound_clicks")
    }
    if any(value < 0 for value in values.values()):
        raise ValueError("Pinterest metrics cannot be negative")
    canonical_raw = _json(raw_metrics or metrics)
    source_payload_hash = hashlib.sha256(
        _json({"metrics": values, "raw": json.loads(canonical_raw)}).encode()
    ).hexdigest()
    existing = session.scalar(
        select(PinterestPerformanceSnapshotRecord).where(
            PinterestPerformanceSnapshotRecord.pinterest_publication_id == publication_id,
            PinterestPerformanceSnapshotRecord.window_start == window_start,
            PinterestPerformanceSnapshotRecord.window_end == window_end,
            PinterestPerformanceSnapshotRecord.source_revision == source_revision,
        )
    )
    if existing is not None:
        if existing.source_payload_hash != source_payload_hash:
            raise ValueError("conflicting Pinterest metrics reuse the same source revision/window")
        return existing, False
    snapshot = PinterestPerformanceSnapshotRecord(
        pinterest_publication_id=publication_id,
        source_revision=source_revision,
        window_start=window_start,
        window_end=window_end,
        source_payload_hash=source_payload_hash,
        raw_metrics_json=canonical_raw,
        **values,
    )
    session.add(snapshot)
    session.flush()
    return snapshot, True


def _accepted_review_evidence(
    session: Session,
    shadow: ShadowPublicationRecord,
) -> ShadowReviewDecisionRecord:
    decision = session.scalar(
        select(ShadowReviewDecisionRecord)
        .join(
            ShadowReviewSessionRecord,
            ShadowReviewSessionRecord.id == ShadowReviewDecisionRecord.session_id,
        )
        .where(
            ShadowReviewDecisionRecord.publication_id == shadow.id,
            ShadowReviewDecisionRecord.decision_kind == "package",
            ShadowReviewSessionRecord.completed_at.is_not(None),
        )
        .order_by(
            ShadowReviewDecisionRecord.decided_at.desc(),
            ShadowReviewDecisionRecord.id.desc(),
        )
        .limit(1)
    )
    if (
        decision is None
        or decision.result != "accepted_for_shadow"
        or decision.manifest_id is None
        or decision.review_asset_id is None
    ):
        raise PermissionError(
            "latest completed package review must accept this publication and bind its manifest/image"
        )
    manifest = session.get(ShadowCreativeManifestRecord, decision.manifest_id)
    if (
        decision.reviewed_payload_hash != shadow.payload_hash
        or manifest is None
        or decision.reviewed_manifest_hash
        != review_manifest_evidence_hash(session, manifest, decision.review_asset_id)
        or decision.reviewed_request_hash
        != reviewed_publish_request_hash(
            session,
            shadow,
            manifest,
            decision.review_asset_id,
        )
    ):
        raise PermissionError("accepted review evidence does not match the current payload/manifest")
    return decision


def _provider_identity_error(
    session: Session,
    publication: PinterestPublicationRecord,
    result: ProviderResult,
) -> str:
    pin_id = result.external_pin_id.strip()
    external_url = result.external_url.strip()
    parsed = urlparse(external_url)
    if not pin_id or not external_url:
        return "Provider success omitted the external Pin ID or URL."
    if parsed.scheme != "https" or not (
        parsed.hostname == "pinterest.com"
        or (parsed.hostname or "").endswith(".pinterest.com")
    ):
        return "Provider success returned a non-Pinterest external URL."
    owner = session.scalar(
        select(PinterestPublicationRecord).where(
            PinterestPublicationRecord.connection_id == publication.connection_id,
            PinterestPublicationRecord.external_pin_id == pin_id,
            PinterestPublicationRecord.id != publication.id,
        )
    )
    if owner is not None:
        return f"External Pin ID is already owned by publication {owner.id}."
    return ""


def _validate_media_delivery(
    connection: PinterestConnectionRecord,
    approval: ShadowReviewDecisionRecord,
    delivery: PinterestMediaDeliveryRecord | None,
    review_asset: AssetRecord | None,
) -> None:
    if delivery is None or review_asset is None:
        raise PermissionError("verified Pinterest media delivery is unavailable")
    if (
        delivery.connection_id != connection.id
        or delivery.review_asset_id != approval.review_asset_id
        or delivery.content_checksum != review_asset.file_checksum
        or delivery.revoked_at is not None
    ):
        raise PermissionError("media delivery does not match the approved review asset")
    if connection.connection_state == "fixture_only":
        if delivery.delivery_state != "fixture_verified" or urlparse(delivery.media_url).scheme != "fixture":
            raise PermissionError("fixture connection requires fixture-verified media")
    else:
        parsed = urlparse(delivery.media_url)
        if (
            delivery.delivery_state != "verified"
            or parsed.scheme != "https"
            or not parsed.hostname
        ):
            raise PermissionError("live connection requires checksum-verified HTTPS media")


def _validate_request_media(
    request: PublishRequest,
    provider: PinterestProvider,
) -> None:
    if not request.media_checksum or not request.approved_asset_location:
        raise PermissionError("publish request is missing approved media evidence")
    parsed = urlparse(request.media_url)
    if provider.fixture_only:
        if parsed.scheme != "fixture":
            raise PermissionError("fixture provider requires fixture media")
    elif parsed.scheme != "https" or not parsed.hostname:
        raise PermissionError("live provider requires a non-fixture HTTPS media URL")


def _enqueue_reconciliation(
    session: Session,
    publication: PinterestPublicationRecord,
) -> None:
    from .durable_jobs import enqueue_job

    enqueue_job(
        session,
        job_type="pinterest.reconcile",
        payload={
            "publicationId": publication.id,
            "provider": "fixture"
            if publication.connection.connection_state == "fixture_only"
            else "live",
        },
        priority=20,
        max_attempts=6,
        idempotency_key=f"pinterest:reconcile:{publication.id}:{publication.submitted_at.isoformat()}",
        correlation_id=f"pinterest-publication:{publication.id}",
    )


def _request_payload(
    session: Session,
    shadow: ShadowPublicationRecord,
    approval: ShadowReviewDecisionRecord,
    idempotency_key: str,
    board_id: str,
    media_url: str,
) -> dict[str, str]:
    asset = session.get(AssetRecord, approval.review_asset_id)
    if asset is None:
        raise PermissionError("approved review asset is unavailable")
    return {
        "idempotency_key": idempotency_key,
        "board_id": board_id,
        "title": shadow.title,
        "description": shadow.description,
        "destination_url": shadow.tracked_destination_url,
        "media_url": media_url,
        "media_checksum": asset.file_checksum,
        "approved_asset_location": asset.source_path,
    }


def _require_authority(
    session: Session,
    *,
    connection: PinterestConnectionRecord,
    policy_class: str,
    provider: PinterestProvider,
    environment: dict[str, str] | None,
) -> None:
    values = environment if environment is not None else os.environ
    if provider.contract_version != connection.provider_contract_version:
        raise PermissionError("runtime provider contract does not match the connection")
    if provider.fixture_only:
        if connection.connection_state != "fixture_only":
            raise PermissionError("fixture provider requires fixture-only connection")
    else:
        if values.get("MARKETING_OS_ENV", "").lower() != "production":
            raise PermissionError("live Pinterest publishing requires production mode")
        if not values.get("MARKETING_OS_DB_URL", "").startswith(
            ("postgresql://", "postgresql+psycopg://")
        ):
            raise PermissionError("live Pinterest publishing requires PostgreSQL")
        application_secret = values.get("MARKETING_OS_SECRET", "")
        if len(application_secret) < 32 or application_secret == "local-dev-only":
            raise PermissionError("strong production application secret is required")
        if values.get("MARKETING_OS_PINTEREST_PUBLISH_ENABLED") != LIVE_ENABLE_VALUE:
            raise PermissionError("live Pinterest publishing is hard-disabled")
        if connection.connection_state != "verified" or connection.access_tier != "standard":
            raise PermissionError("verified Standard-access Pinterest connection is required")
        if not values.get("PINTEREST_ACCESS_TOKEN", "").strip():
            raise PermissionError("Pinterest credential is unavailable")
        if values.get("PINTEREST_ACCOUNT_ID", "") != connection.account_reference:
            raise PermissionError("Pinterest account configuration does not match the connection")
        if values.get("PINTEREST_CREDENTIAL_REFERENCE", "") != connection.credential_reference:
            raise PermissionError("Pinterest credential reference does not match the connection")
        if not values.get("MARKETING_OS_ALERT_WEBHOOK_URL", "").strip():
            raise PermissionError("alert delivery is unavailable")
        if not values.get("MARKETING_OS_ALERT_OWNER", "").strip():
            raise PermissionError("alert owner is unavailable")
        if not values.get("MARKETING_OS_BACKUP_DESTINATION", "").strip():
            raise PermissionError("off-host backup destination is unavailable")
        if not values.get("MARKETING_OS_BACKUP_KEY_CUSTODIAN", "").strip():
            raise PermissionError("backup key custodian is unavailable")
        for variable in (
            "MARKETING_OS_BACKUP_RETENTION_DAYS",
            "MARKETING_OS_BACKUP_RPO_HOURS",
            "MARKETING_OS_BACKUP_RTO_HOURS",
        ):
            if not values.get(variable, "").isdigit() or int(values[variable]) <= 0:
                raise PermissionError(f"positive {variable} is required")
        if not values.get("MARKETING_OS_PUBLIC_HOSTNAME", "").strip():
            raise PermissionError("production hostname is unavailable")
        if values.get("MARKETING_OS_ROUTE_APPROVED") != DEPLOYMENT_APPROVAL_VALUE:
            raise PermissionError("production route is not explicitly approved")
        if values.get("MARKETING_OS_DEPLOYMENT_APPROVED") != DEPLOYMENT_APPROVAL_VALUE:
            raise PermissionError("production deployment is not explicitly approved")
        if (
            not values.get("MARKETING_OS_DAILY_COST_CENTS", "").isdigit()
            or int(values["MARKETING_OS_DAILY_COST_CENTS"]) <= 0
        ):
            raise PermissionError("numeric daily cost ceiling is required")
        if values.get("PINTEREST_ACCESS_TIER", "").lower() != "standard":
            raise PermissionError("configured Pinterest access tier is not Standard")
        if values.get("PINTEREST_PROVIDER_CONTRACT_VERSION", "") != connection.provider_contract_version:
            raise PermissionError("provider contract configuration does not match the connection")
        configured_boards = {
            value.strip()
            for value in values.get("PINTEREST_APPROVED_BOARD_IDS", "").split(",")
            if value.strip()
        }
        if configured_boards != set(json.loads(connection.approved_board_ids_json or "[]")):
            raise PermissionError("configured Pinterest boards do not match the approved connection")

    scopes = set(json.loads(connection.scopes_json or "[]"))
    if not REQUIRED_WRITE_SCOPES.issubset(scopes):
        raise PermissionError("Pinterest connection lacks required read/write scopes")
    now = _now()
    expected_hash = authority_scope_hash(connection, policy_class)
    grant = session.scalar(
        select(PinterestAuthorityGrantRecord)
        .where(
            PinterestAuthorityGrantRecord.policy_class == policy_class,
            PinterestAuthorityGrantRecord.state == "active",
            PinterestAuthorityGrantRecord.revoked_at.is_(None),
            PinterestAuthorityGrantRecord.expires_at > now,
            PinterestAuthorityGrantRecord.scope_hash == expected_hash,
        )
        .order_by(PinterestAuthorityGrantRecord.expires_at.desc())
    )
    if grant is None:
        raise PermissionError("active, matching, unexpired Pinterest authority grant is required")


def _audit(
    session: Session,
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
