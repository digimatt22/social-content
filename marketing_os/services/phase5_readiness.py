from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db_models import CreativeGenerationJobRecord, GeneratedContentCandidateRecord, utc_now


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


@dataclass(frozen=True)
class Phase5ApprovalPacket:
    generated_at: datetime
    readiness: Phase5Readiness
    copy_candidate: GeneratedContentCandidateRecord | None
    creative_job: CreativeGenerationJobRecord | None


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


def build_phase5_approval_packet(session: Session) -> Phase5ApprovalPacket:
    return Phase5ApprovalPacket(
        generated_at=utc_now(),
        readiness=build_phase5_readiness(session),
        copy_candidate=_latest_facebook_candidate(session),
        creative_job=_latest_creative_job(session),
    )


def serialize_phase5_approval_packet(packet: Phase5ApprovalPacket) -> dict[str, object]:
    return {
        "generated_at": packet.generated_at.isoformat(),
        "readiness": serialize_phase5_readiness(packet.readiness),
        "copy_review": _serialize_copy_candidate(packet.copy_candidate),
        "creative_review": _serialize_creative_job(packet.creative_job),
        "final_actions": _final_actions(packet.readiness),
    }


def render_phase5_approval_packet_markdown(packet: Phase5ApprovalPacket) -> str:
    payload = serialize_phase5_approval_packet(packet)
    readiness = payload["readiness"]
    copy_review = payload["copy_review"]
    creative_review = payload["creative_review"]
    final_actions = payload["final_actions"]

    lines = [
        "# Phase 5 Approval Packet",
        "",
        f"Generated at: {payload['generated_at']}",
        f"Readiness: {'complete' if readiness['complete'] else 'needs proof'}",
        f"Remaining proof items: {readiness['remaining_count']}",
        "",
        "## Readiness Gate",
        "",
    ]
    for item in readiness["items"]:
        lines.extend(
            [
                f"### {item['label']}",
                "",
                f"- Status: {'complete' if item['complete'] else 'needs proof'}",
                f"- Evidence: {item['evidence']}",
                f"- Action: {item['action']}",
                "",
            ]
        )

    lines.extend(["## Facebook Copy Review", ""])
    if copy_review:
        lines.extend(
            [
                f"- Candidate ID: {copy_review['id']}",
                f"- Review state: {copy_review['review_state']}",
                f"- Reviewed by: {copy_review['reviewed_by'] or 'not recorded'}",
                f"- Reviewed at: {copy_review['reviewed_at'] or 'not recorded'}",
                f"- Provider: {copy_review['provider']}",
                f"- Planned item ID: {copy_review['planned_item_id']}",
                "",
                "### Draft",
                "",
                str(copy_review["display_body"] or copy_review["body"] or "").strip() or "No draft text recorded.",
                "",
                "### Source Facts",
                "",
                "```json",
                json.dumps(copy_review["source_facts"], indent=2),
                "```",
                "",
            ]
        )
    else:
        lines.extend(["No Facebook post candidate exists yet.", ""])

    lines.extend(["## Generated Creative Review", ""])
    if creative_review:
        lines.extend(
            [
                f"- Job ID: {creative_review['id']}",
                f"- Review state: {creative_review['review_state']}",
                f"- Reviewed by: {creative_review['reviewed_by'] or 'not recorded'}",
                f"- Reviewed at: {creative_review['reviewed_at'] or 'not recorded'}",
                f"- Provider: {creative_review['provider']}",
                f"- Model/tool: {creative_review['model_name'] or 'not recorded'}",
                f"- Provider job ID: {creative_review['provider_job_id'] or 'not recorded'}",
                f"- Source asset ID: {creative_review['source_asset_id']}",
                f"- Candidate asset ID: {creative_review['candidate_asset_id'] or 'not recorded'}",
                f"- Output path: {creative_review['output_path'] or 'not recorded'}",
                "",
                "### Prompt",
                "",
                str(creative_review["prompt"] or "").strip() or "No prompt recorded.",
                "",
                "### Review Notes",
                "",
                str(creative_review["review_notes"] or "").strip() or "No review notes recorded.",
                "",
            ]
        )
    else:
        lines.extend(["No generated creative job exists yet.", ""])

    lines.extend(["## Final Actions", ""])
    for action in final_actions:
        lines.append(f"- {action}")
    lines.append("")
    return "\n".join(lines)


def write_phase5_approval_packet(session: Session, export_dir: str | Path) -> Path:
    target_dir = Path(export_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    target = target_dir / f"phase5-approval-packet-{stamp}.md"
    target.write_text(render_phase5_approval_packet_markdown(build_phase5_approval_packet(session)), encoding="utf-8")
    return target


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


def _latest_facebook_candidate(session: Session) -> GeneratedContentCandidateRecord | None:
    approved = session.scalar(
        select(GeneratedContentCandidateRecord)
        .where(
            GeneratedContentCandidateRecord.candidate_type == "facebook_post",
            GeneratedContentCandidateRecord.review_state == "approved",
            GeneratedContentCandidateRecord.reviewed_by != "",
            GeneratedContentCandidateRecord.reviewed_at.is_not(None),
        )
        .order_by(GeneratedContentCandidateRecord.reviewed_at.desc(), GeneratedContentCandidateRecord.id.desc())
    )
    if approved:
        return approved
    return session.scalar(
        select(GeneratedContentCandidateRecord)
        .where(GeneratedContentCandidateRecord.candidate_type == "facebook_post")
        .order_by(GeneratedContentCandidateRecord.updated_at.desc(), GeneratedContentCandidateRecord.id.desc())
    )


def _latest_creative_job(session: Session) -> CreativeGenerationJobRecord | None:
    approved = session.scalar(
        select(CreativeGenerationJobRecord)
        .where(
            CreativeGenerationJobRecord.review_state == "approved",
            CreativeGenerationJobRecord.reviewed_by != "",
            CreativeGenerationJobRecord.reviewed_at.is_not(None),
            CreativeGenerationJobRecord.candidate_asset_id.is_not(None),
        )
        .order_by(CreativeGenerationJobRecord.reviewed_at.desc(), CreativeGenerationJobRecord.id.desc())
    )
    if approved:
        return approved
    return session.scalar(select(CreativeGenerationJobRecord).order_by(CreativeGenerationJobRecord.updated_at.desc(), CreativeGenerationJobRecord.id.desc()))


def _serialize_copy_candidate(candidate: GeneratedContentCandidateRecord | None) -> dict[str, object] | None:
    if candidate is None:
        return None
    return {
        "id": candidate.id,
        "planned_item_id": candidate.planned_item_id,
        "candidate_type": candidate.candidate_type,
        "provider": candidate.provider,
        "body": candidate.body,
        "display_body": _display_body(candidate.body),
        "source_facts": _json_dict(candidate.source_facts_json),
        "source_asset_ids": _json_list(candidate.source_asset_ids_json),
        "review_state": candidate.review_state,
        "revision_notes": candidate.revision_notes,
        "reviewed_by": candidate.reviewed_by,
        "reviewed_at": candidate.reviewed_at.isoformat() if candidate.reviewed_at else None,
        "created_at": candidate.created_at.isoformat() if candidate.created_at else None,
        "updated_at": candidate.updated_at.isoformat() if candidate.updated_at else None,
    }


def _serialize_creative_job(job: CreativeGenerationJobRecord | None) -> dict[str, object] | None:
    if job is None:
        return None
    return {
        "id": job.id,
        "source_asset_id": job.source_asset_id,
        "candidate_asset_id": job.candidate_asset_id,
        "target_format": job.target_format,
        "provider": job.provider,
        "model_name": job.model_name,
        "prompt": job.prompt,
        "requested_dimensions": job.requested_dimensions,
        "provider_job_id": job.provider_job_id,
        "provider_status": job.provider_status,
        "provider_error": job.provider_error,
        "output_url": job.output_url,
        "output_path": job.output_path,
        "review_state": job.review_state,
        "review_notes": job.review_notes,
        "reviewed_by": job.reviewed_by,
        "reviewed_at": job.reviewed_at.isoformat() if job.reviewed_at else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


def _final_actions(readiness: Phase5Readiness) -> list[str]:
    remaining = [item.action for item in readiness.items if not item.complete]
    if remaining:
        return remaining
    return [
        "Keep the reviewed Facebook copy and generated creative linked to their posting workflow evidence.",
        "Run the Phase 5 completion audit one final time before marking the goal complete.",
    ]


def _json_dict(value: str) -> dict[str, object]:
    try:
        data = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _json_list(value: str) -> list[object]:
    try:
        data = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _display_body(value: str) -> str:
    data = _json_dict(value)
    if not data:
        return value
    parts: list[str] = []
    for label, key in (("Hook", "hook"), ("Body", "body"), ("CTA", "cta")):
        text = str(data.get(key) or "").strip()
        if text:
            parts.append(f"{label}: {text}")
    checklist = data.get("quality_checklist")
    if isinstance(checklist, list) and checklist:
        parts.append("Quality checklist: " + "; ".join(str(item) for item in checklist))
    return "\n\n".join(parts) or value
