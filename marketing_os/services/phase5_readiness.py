from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db_models import AssetRecord, CreativeGenerationJobRecord, GeneratedContentCandidateRecord, utc_now


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
    creative_prompt_candidate: GeneratedContentCandidateRecord | None
    creative_source_asset: AssetRecord | None


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
        creative_prompt_candidate=_latest_image_prompt_candidate(session),
        creative_source_asset=_recommended_creative_source_asset(session),
    )


def serialize_phase5_approval_packet(packet: Phase5ApprovalPacket) -> dict[str, object]:
    return {
        "generated_at": packet.generated_at.isoformat(),
        "readiness": serialize_phase5_readiness(packet.readiness),
        "copy_review": _serialize_copy_candidate(packet.copy_candidate),
        "creative_review": _serialize_creative_job(packet.creative_job),
        "creative_handoff": _serialize_creative_handoff(packet.creative_prompt_candidate, packet.creative_source_asset),
        "final_actions": _final_actions(packet.readiness),
    }


def render_phase5_approval_packet_markdown(packet: Phase5ApprovalPacket) -> str:
    payload = serialize_phase5_approval_packet(packet)
    readiness = payload["readiness"]
    copy_review = payload["copy_review"]
    creative_review = payload["creative_review"]
    creative_handoff = payload["creative_handoff"]
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
                "### Copyable Post",
                "",
                str(copy_review["copy_text"] or "").strip() or "No copyable post text recorded.",
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
                "### Asset References",
                "",
                *_creative_asset_reference_lines(creative_review),
                "",
                "### Creative Approval Checklist",
                "",
                "- Product shape, color, printed details, and proportions match the source.",
                "- No invented markings, logos, text, packaging, or character references.",
                f"- Composition fits {creative_review['target_format'] or 'the target format'} without hiding the product.",
                "- File is usable from the local output path before approval.",
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
        if creative_handoff:
            source_asset = creative_handoff["source_asset"]
            lines.extend(
                [
                    "### Creative Handoff",
                    "",
                    f"- Recommended source asset ID: {source_asset['id'] if source_asset else 'not available'}",
                    f"- Source file: {source_asset['source_path'] if source_asset else 'not available'}",
                    f"- Import generated output at: {creative_handoff['manual_import_path']}",
                    "",
                    "### Prompt",
                    "",
                    str(creative_handoff["prompt"] or "").strip() or "No prompt candidate recorded.",
                    "",
                ]
            )

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


def render_phase5_creative_handoff_markdown(packet: Phase5ApprovalPacket) -> str:
    payload = serialize_phase5_approval_packet(packet)
    handoff = payload["creative_handoff"]
    creative_review = payload["creative_review"]
    if not handoff:
        return "\n".join(
            [
                "# Phase 5 Creative Handoff",
                "",
                f"Generated at: {payload['generated_at']}",
                "",
                "No creative handoff is available yet. Create a planned content item and run content production, or approve a source asset first.",
                "",
            ]
        )

    source_asset = handoff["source_asset"]
    import_defaults = handoff["import_defaults"]
    lines = [
        "# Phase 5 Creative Handoff",
        "",
        f"Generated at: {payload['generated_at']}",
        "",
        "## Purpose",
        "",
        "Use this handoff to generate one real Magnific/MCP creative candidate, save the output locally, and import it back into Marketing OS for review.",
        "",
        "## Source Asset",
        "",
    ]
    if source_asset:
        lines.extend(
            [
                f"- Asset ID: {source_asset['id']}",
                f"- Name: {source_asset['name']}",
                f"- Type: {source_asset['asset_type']}",
                f"- Local path: {source_asset['source_path']}",
                f"- File exists: {source_asset['file_exists']}",
                f"- External source: {source_asset['external_source'] or 'local'}",
                f"- Canonical URL: {source_asset['canonical_url'] or 'not recorded'}",
                "",
            ]
        )
    else:
        lines.extend(["No approved file-backed source asset was found.", ""])

    lines.extend(
        [
            "## Generation Prompt",
            "",
            str(handoff["prompt"] or "").strip() or "No generation prompt recorded.",
            "",
            "## Import Back Into Marketing OS",
            "",
            f"- Open: {handoff['manual_import_path']}",
            f"- Prefilled form: {handoff['manual_import_query']}",
            "- Use the source asset ID above.",
            "- Set provider to `magnific_mcp` or the actual provider/tool used.",
            "- Paste the prompt above into the Prompt field.",
            f"- Suggested output path: {import_defaults['output_path'] or 'choose a local path that Marketing OS can read'}",
            "- Import the output as `Facebook post image` and leave it in `needs_review` until Matt approves it.",
            "",
        ]
    )
    if creative_review:
        lines.extend(
            [
                "## Existing Creative Job",
                "",
                f"Creative job #{creative_review['id']} already exists with state `{creative_review['review_state']}`.",
                "",
            ]
        )
    return "\n".join(lines)


def write_phase5_creative_handoff(session: Session, export_dir: str | Path) -> Path:
    target_dir = Path(export_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    target = target_dir / f"phase5-creative-handoff-{stamp}.md"
    target.write_text(render_phase5_creative_handoff_markdown(build_phase5_approval_packet(session)), encoding="utf-8")
    return target


def _copy_review_item(session: Session) -> ReadinessItem:
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
        return ReadinessItem(
            key="facebook_copy_review",
            label="Matt-approved Facebook copy",
            complete=True,
            message="A Facebook generated-copy candidate has reviewer evidence.",
            evidence=f"Candidate #{approved.id} approved by {approved.reviewed_by}.",
            action="Keep the reviewed candidate linked to a posting task.",
        )
    latest = _latest_facebook_candidate(session)
    if latest and latest.review_state == "rewrite_requested":
        return ReadinessItem(
            key="facebook_copy_review",
            label="Matt-approved Facebook copy",
            complete=False,
            message="Latest Facebook copy candidate is waiting on a rewrite.",
            evidence=f"Candidate #{latest.id} has rewrite notes: {latest.revision_notes or 'no notes recorded'}.",
            action=(
                "Run `python -m marketing_os.jobs.content_production --planned-item-id "
                f"{latest.planned_item_id} --export-briefs-dir data/exports/content-briefs` to generate a revised candidate."
            ),
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


def _latest_image_prompt_candidate(session: Session) -> GeneratedContentCandidateRecord | None:
    return session.scalar(
        select(GeneratedContentCandidateRecord)
        .where(GeneratedContentCandidateRecord.candidate_type == "image_prompt_brief")
        .order_by(GeneratedContentCandidateRecord.updated_at.desc(), GeneratedContentCandidateRecord.id.desc())
    )


def _recommended_creative_source_asset(session: Session) -> AssetRecord | None:
    prompt_candidate = _latest_image_prompt_candidate(session)
    product_ids = _candidate_product_ids(prompt_candidate)
    query = (
        select(AssetRecord)
        .where(
            AssetRecord.review_state == "approved",
            AssetRecord.file_exists == 1,
            AssetRecord.asset_type.in_(["source photo", "Etsy product photo", "edited photo", "external listing image"]),
        )
        .order_by(AssetRecord.product_id.is_(None), AssetRecord.id)
    )
    if product_ids:
        matched = session.scalar(query.where(AssetRecord.product_id.in_(product_ids)))
        if matched:
            return matched
    return session.scalar(query)


def _serialize_copy_candidate(candidate: GeneratedContentCandidateRecord | None) -> dict[str, object] | None:
    if candidate is None:
        return None
    return {
        "id": candidate.id,
        "planned_item_id": candidate.planned_item_id,
        "candidate_type": candidate.candidate_type,
        "provider": candidate.provider,
        "body": candidate.body,
        "copy_text": _candidate_copy_body(candidate.body),
        "display_body": _display_body(candidate.body),
        "source_facts": _json_dict(candidate.source_facts_json),
        "source_asset_ids": _json_list(candidate.source_asset_ids_json),
        "review_state": candidate.review_state,
        "revision_notes": candidate.revision_notes,
        "reviewed_by": candidate.reviewed_by,
        "reviewed_at": candidate.reviewed_at.isoformat() if candidate.reviewed_at else None,
        "created_at": candidate.created_at.isoformat() if candidate.created_at else None,
        "updated_at": candidate.updated_at.isoformat() if candidate.updated_at else None,
        "review_path": f"/planning#candidate-{candidate.id}",
    }


def _serialize_creative_handoff(
    prompt_candidate: GeneratedContentCandidateRecord | None,
    source_asset: AssetRecord | None,
) -> dict[str, object] | None:
    if prompt_candidate is None and source_asset is None:
        return None
    return {
        "prompt_candidate_id": prompt_candidate.id if prompt_candidate else None,
        "source_prompt": prompt_candidate.body if prompt_candidate else "",
        "prompt": _creative_handoff_prompt(prompt_candidate, source_asset),
        "prompt_review_state": prompt_candidate.review_state if prompt_candidate else "",
        "prompt_review_path": f"/planning#candidate-{prompt_candidate.id}" if prompt_candidate else "",
        "source_asset": _serialize_source_asset(source_asset),
        "manual_import_path": "/creative-assets",
        "manual_import_query": "/creative-assets?phase5_handoff=1#import-magnific-output",
        "import_defaults": _creative_import_defaults(prompt_candidate, source_asset),
        "next_step": "Generate a real Magnific/MCP output from the recommended source asset, save it locally, then import it through Creative Assets.",
    }


def _creative_import_defaults(prompt_candidate: GeneratedContentCandidateRecord | None, source_asset: AssetRecord | None) -> dict[str, object]:
    source_id = source_asset.id if source_asset else ""
    source_slug = _slug(source_asset.name) if source_asset else "phase5"
    return {
        "source_asset_id": source_id,
        "output_path": f"outputs/magnific/{source_slug}-facebook-post-image.png" if source_asset else "",
        "target_format": "Facebook post image",
        "provider": "magnific_mcp",
        "model_name": "Magnific MCP",
        "provider_job_id": "",
        "output_url": "",
        "requested_dimensions": "1080x1080",
        "prompt": _creative_handoff_prompt(prompt_candidate, source_asset),
        "notes": "Phase 5 generated creative candidate. Review product accuracy, composition, and brand fit before approval.",
    }


def _creative_handoff_prompt(prompt_candidate: GeneratedContentCandidateRecord | None, source_asset: AssetRecord | None) -> str:
    base_prompt = prompt_candidate.body.strip() if prompt_candidate else ""
    source_name = source_asset.name if source_asset else "the approved source asset"
    return (
        f"Use {source_name} as the reference image. Create one product-accurate Facebook-ready image for MattMadeMe. "
        "Preserve the duck's shape, color, printed details, proportions, and 3D-printed collectible feel. "
        "Do not invent new markings, characters, logos, text overlays, or packaging. "
        "Use a clean, warm product-photo composition suitable for a Facebook post. "
        "Leave the output unapproved until Matt reviews it in Marketing OS."
        + (f"\n\nPlanning prompt context: {base_prompt}" if base_prompt else "")
    )


def _serialize_source_asset(asset: AssetRecord | None) -> dict[str, object] | None:
    if asset is None:
        return None
    return {
        "id": asset.id,
        "name": asset.name,
        "product_id": asset.product_id,
        "asset_type": asset.asset_type,
        "source_path": asset.source_path,
        "external_source": asset.external_source,
        "external_id": asset.external_id,
        "canonical_url": asset.canonical_url,
        "file_exists": bool(asset.file_exists),
        "review_state": asset.review_state,
    }


def _serialize_creative_job(job: CreativeGenerationJobRecord | None) -> dict[str, object] | None:
    if job is None:
        return None
    return {
        "id": job.id,
        "source_asset_id": job.source_asset_id,
        "candidate_asset_id": job.candidate_asset_id,
        "source_asset": _serialize_source_asset(job.source_asset),
        "candidate_asset": _serialize_source_asset(job.candidate_asset),
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
        "review_path": f"/creative-assets#creative-job-{job.id}",
    }


def _creative_asset_reference_lines(creative_review: dict[str, object]) -> list[str]:
    lines: list[str] = []
    source_asset = creative_review.get("source_asset")
    if isinstance(source_asset, dict):
        lines.extend(
            [
                f"- Source asset: #{source_asset.get('id')} · {source_asset.get('name') or 'unnamed'}",
                f"- Source file: {source_asset.get('source_path') or 'not recorded'}",
                f"- Source file exists: {source_asset.get('file_exists')}",
                f"- Source review state: {source_asset.get('review_state') or 'not recorded'}",
            ]
        )
    candidate_asset = creative_review.get("candidate_asset")
    if isinstance(candidate_asset, dict):
        lines.extend(
            [
                f"- Candidate asset: #{candidate_asset.get('id')} · {candidate_asset.get('name') or 'unnamed'}",
                f"- Candidate file: {candidate_asset.get('source_path') or 'not recorded'}",
                f"- Candidate file exists: {candidate_asset.get('file_exists')}",
                f"- Candidate review state: {candidate_asset.get('review_state') or 'not recorded'}",
            ]
        )
    return lines or ["- No source or candidate asset references recorded."]


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


def _candidate_copy_body(value: str) -> str:
    data = _json_dict(value)
    if not data:
        return value.strip()
    pieces = [str(data.get("hook") or "").strip(), str(data.get("body") or "").strip()]
    return "\n\n".join(piece for piece in pieces if piece)


def _slug(value: str) -> str:
    chars: list[str] = []
    previous_dash = False
    for char in value.lower():
        if char.isalnum():
            chars.append(char)
            previous_dash = False
        elif not previous_dash:
            chars.append("-")
            previous_dash = True
    return "".join(chars).strip("-") or "phase5"


def _candidate_product_ids(candidate: GeneratedContentCandidateRecord | None) -> list[int]:
    if candidate is None:
        return []
    facts = _json_dict(candidate.source_facts_json)
    ids: list[int] = []
    product_facts = facts.get("product_facts")
    if isinstance(product_facts, list):
        for item in product_facts:
            if isinstance(item, dict):
                try:
                    ids.append(int(item.get("id")))
                except (TypeError, ValueError):
                    continue
    return ids


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
    score = data.get("quality_score")
    if isinstance(score, dict):
        passed = score.get("passed")
        warnings = score.get("warnings")
        if isinstance(passed, list) and passed:
            parts.append("Quality passed: " + "; ".join(str(item) for item in passed))
        if isinstance(warnings, list) and warnings:
            parts.append("Quality warnings: " + "; ".join(str(item) for item in warnings))
    return "\n\n".join(parts) or value
