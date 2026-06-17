from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db_models import AssetRecord, CreativeGenerationJobRecord
from ..phase4 import refresh_asset_file_state, register_generated_asset_candidate


@dataclass(frozen=True)
class CreativeImportResult:
    job: CreativeGenerationJobRecord
    candidate: AssetRecord


def import_manual_generated_output(
    session: Session,
    source_asset_id: int,
    output_path: str | Path,
    target_format: str,
    prompt: str,
    provider: str = "magnific_manual",
    model_name: str = "",
    provider_job_id: str = "",
    output_url: str = "",
    requested_dimensions: str = "",
    response_metadata: dict[str, object] | None = None,
    notes: str = "",
) -> CreativeImportResult:
    refresh_asset_file_state(session)
    source = session.get(AssetRecord, source_asset_id)
    if source is None:
        raise ValueError(f"Source asset not found: {source_asset_id}")
    if not source.file_exists:
        raise ValueError("Source asset file is missing.")
    if source.review_state != "approved":
        raise ValueError("Source asset must be approved before generated outputs can be imported.")

    output = Path(output_path).expanduser()
    if not output.is_file():
        raise ValueError(f"Generated output file not found: {output}")

    candidate = session.scalar(select(AssetRecord).where(AssetRecord.source_path == output.as_posix()))
    if candidate is None:
        candidate = register_generated_asset_candidate(
            session,
            source,
            output,
            target_format,
            prompt,
            notes=notes or f"Imported generated output from {provider}; review before use.",
        )
    candidate.asset_type = "generated graphic"
    candidate.external_source = provider
    candidate.external_id = provider_job_id
    candidate.canonical_url = output_url
    candidate.generated_prompt = prompt
    candidate.source_asset_id = source.id
    candidate.review_state = "needs review"
    candidate.readiness_state = "needs human review"
    candidate.sync_status = "imported"
    candidate.staleness_state = "fresh"
    candidate.notes = notes or candidate.notes
    refresh_asset_file_state(session)

    job = CreativeGenerationJobRecord(
        source_asset_id=source.id,
        candidate_asset_id=candidate.id,
        target_format=target_format,
        provider=provider,
        model_name=model_name,
        prompt=prompt,
        requested_dimensions=requested_dimensions,
        provider_job_id=provider_job_id,
        provider_status="imported",
        output_url=output_url,
        output_path=output.as_posix(),
        response_metadata_json=json.dumps(response_metadata or {}, indent=2),
        review_state="needs_review",
        review_notes=notes,
    )
    session.add(job)
    session.flush()
    return CreativeImportResult(job=job, candidate=candidate)


def creative_generation_jobs(session: Session) -> list[CreativeGenerationJobRecord]:
    return list(session.scalars(select(CreativeGenerationJobRecord).order_by(CreativeGenerationJobRecord.created_at.desc(), CreativeGenerationJobRecord.id.desc())))


def serialize_creative_generation_job(record: CreativeGenerationJobRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "source_asset_id": record.source_asset_id,
        "candidate_asset_id": record.candidate_asset_id,
        "target_format": record.target_format,
        "provider": record.provider,
        "model_name": record.model_name,
        "prompt": record.prompt,
        "requested_dimensions": record.requested_dimensions,
        "provider_job_id": record.provider_job_id,
        "provider_status": record.provider_status,
        "provider_error": record.provider_error,
        "output_url": record.output_url,
        "output_path": record.output_path,
        "response_metadata": _json_dict(record.response_metadata_json),
        "review_state": record.review_state,
        "review_notes": record.review_notes,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def _json_dict(value: str) -> dict[str, object]:
    try:
        data = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}

