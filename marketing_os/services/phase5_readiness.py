from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db_models import CreativeGenerationJobRecord, GeneratedContentCandidateRecord


@dataclass(frozen=True)
class ReadinessItem:
    key: str
    label: str
    complete: bool
    message: str
    evidence: str
    action: str


@dataclass(frozen=True)
class Phase5Readiness:
    complete: bool
    items: list[ReadinessItem]

    @property
    def remaining_count(self) -> int:
        return len([item for item in self.items if not item.complete])


def build_phase5_readiness(session: Session) -> Phase5Readiness:
    items = [
        _copy_review_item(session),
        _creative_review_item(session),
    ]
    return Phase5Readiness(complete=all(item.complete for item in items), items=items)


def serialize_phase5_readiness(readiness: Phase5Readiness) -> dict[str, object]:
    return {
        "complete": readiness.complete,
        "remaining_count": readiness.remaining_count,
        "items": [
            {
                "key": item.key,
                "label": item.label,
                "complete": item.complete,
                "message": item.message,
                "evidence": item.evidence,
                "action": item.action,
            }
            for item in readiness.items
        ],
    }


def _copy_review_item(session: Session) -> ReadinessItem:
    candidate = session.scalar(
        select(GeneratedContentCandidateRecord)
        .where(
            GeneratedContentCandidateRecord.candidate_type == "facebook_post",
            GeneratedContentCandidateRecord.review_state == "approved",
            GeneratedContentCandidateRecord.reviewed_by != "",
            GeneratedContentCandidateRecord.reviewed_at.is_not(None),
        )
        .order_by(GeneratedContentCandidateRecord.reviewed_at.desc(), GeneratedContentCandidateRecord.id.desc())
    )
    if candidate:
        return ReadinessItem(
            key="facebook_copy_review",
            label="Matt-approved Facebook copy",
            complete=True,
            message="A Facebook generated-copy candidate has reviewer evidence.",
            evidence=f"Candidate #{candidate.id} approved by {candidate.reviewed_by}.",
            action="Keep the reviewed candidate linked to a posting task.",
        )
    return ReadinessItem(
        key="facebook_copy_review",
        label="Matt-approved Facebook copy",
        complete=False,
        message="No approved Facebook generated-copy candidate has reviewer evidence yet.",
        evidence="Missing approved facebook_post candidate with reviewed_by and reviewed_at.",
        action="Open Planning, review a Facebook candidate, set Reviewed by to Matt, and save review.",
    )


def _creative_review_item(session: Session) -> ReadinessItem:
    job = session.scalar(
        select(CreativeGenerationJobRecord)
        .where(
            CreativeGenerationJobRecord.review_state == "approved",
            CreativeGenerationJobRecord.reviewed_by != "",
            CreativeGenerationJobRecord.reviewed_at.is_not(None),
            CreativeGenerationJobRecord.candidate_asset_id.is_not(None),
        )
        .order_by(CreativeGenerationJobRecord.reviewed_at.desc(), CreativeGenerationJobRecord.id.desc())
    )
    if job:
        return ReadinessItem(
            key="creative_generation_review",
            label="Matt-approved generated creative",
            complete=True,
            message="A generated creative job has reviewer evidence and a candidate asset.",
            evidence=f"Creative job #{job.id} approved by {job.reviewed_by}.",
            action="Use the approved generated asset from Creative Assets when appropriate.",
        )
    return ReadinessItem(
        key="creative_generation_review",
        label="Matt-approved generated creative",
        complete=False,
        message="No approved generated creative job has reviewer evidence yet.",
        evidence="Missing approved creative generation job with reviewed_by, reviewed_at, and candidate asset.",
        action="Import a real Magnific/MCP output, visually review it, set Reviewed by to Matt, and save creative review.",
    )
