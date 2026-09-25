"""Drain Art Studio social-image CreativeGenerationJobRecords via Magnific REST."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select

from ..db import create_db_engine, init_db, session_factory, session_scope
from ..db_models import AssetRecord, CreativeGenerationJobRecord, SyncMetadata, utc_now
from ..magnific_api import (
    MagnificApiError,
    MagnificClient,
    MagnificReferenceImage,
    MagnificUploadedFile,
    guess_mime_type,
    https_asset_url,
    magnific_api_configured,
)
from ..services.art_studio import (
    SOCIAL_JOB_FORMAT,
    register_social_image_job_output,
    slugify,
    social_image_aspect_ratio_from_job,
)
from ..services.job_handlers import NonRetryableJobError


REFERENCE_ROLE_TEXT = {
    0: "Primary visible 3/4 product angle. Preserve exactly. Place only this duck in the scene.",
    "default": "Identity lock reference only. Do not render as a second object.",
}


def art_studio_social_image_generate_handler(payload: dict[str, Any]) -> dict[str, Any] | None:
    if not magnific_api_configured():
        return {"skipped": True, "reason": "MAGNIFIC_API_KEY unset"}

    creative_job_id = int(payload.get("creativeJobId") or payload.get("creative_job_id") or 0)
    if creative_job_id < 1:
        raise NonRetryableJobError("payload.creativeJobId is required")

    client = MagnificClient()
    poll_seconds = float(payload.get("pollSeconds") or 2.0)
    timeout_seconds = float(payload.get("timeoutSeconds") or 300.0)

    engine = create_db_engine()
    init_db(engine)
    factory = session_factory(engine)
    try:
        with session_scope(factory) as session:
            job = session.get(CreativeGenerationJobRecord, creative_job_id)
            if job is None:
                raise NonRetryableJobError(f"Creative generation job not found: {creative_job_id}")
            if job.target_format != SOCIAL_JOB_FORMAT:
                raise NonRetryableJobError(
                    f"Unsupported target_format for Magnific API drain: {job.target_format}"
                )
            if job.provider_status == "generated":
                return {
                    "skipped": True,
                    "reason": "already_generated",
                    "creativeJobId": job.id,
                    "providerJobId": job.provider_job_id,
                }
            if job.provider_status == "canceled":
                return {"skipped": True, "reason": "canceled", "creativeJobId": job.id}
            if job.provider_status != "queued" and job.provider_status != "generating":
                raise NonRetryableJobError(
                    f"Creative job {job.id} is not claimable (provider_status={job.provider_status})."
                )
            if job.provider not in {"magnific_mcp", "magnific_api"}:
                raise NonRetryableJobError(
                    f"Creative job {job.id} provider {job.provider!r} is not Magnific API drainable."
                )

            references = _reference_assets(session, job)
            reference_images = _reference_images_or_raise(session, references, client)
            metadata = _json_dict(job.response_metadata_json)
            product_name = str(metadata.get("product_name") or "").strip() or "product"
            option_number = int(metadata.get("option_number") or 1)
            platform_key = str(metadata.get("platform") or "").strip()
            aspect_ratio = social_image_aspect_ratio_from_job(job)
            output_dir = Path(
                str(metadata.get("output_dir") or f"outputs/graphics/social-worthy/{slugify(product_name)}")
            )
            prompt = job.prompt

            job.provider = "magnific_api"
            job.model_name = job.model_name or "Nano Banana Pro Flash"
            job.provider_status = "generating"
            job.review_notes = (
                "marketing-os-worker is generating via Magnific API. "
                "Attach/import remains available as a fallback if needed."
            )
            staged_refs = _staged_refs_for_assets(session, references)
            metadata["magnific_api"] = {
                "endpoint": "nano-banana-pro-flash",
                "reference_count": len(reference_images),
                "reference_urls": [item.image for item in reference_images],
                "aspect_ratio": aspect_ratio,
                "platform": platform_key,
                "staged_refs": staged_refs,
            }
            job.response_metadata_json = json.dumps(metadata, indent=2)
            session.flush()
            prompt_text = prompt
            job_id = job.id
            aspect_ratio_for_api = aspect_ratio
            platform_key_for_output = platform_key

        try:
            created = client.create_nano_banana_pro_flash(
                prompt=prompt_text,
                reference_images=reference_images,
                aspect_ratio=aspect_ratio_for_api,
                resolution="2K",
            )
        except MagnificApiError as exc:
            _mark_provider_error(factory, job_id, str(exc))
            if not exc.retryable:
                raise NonRetryableJobError(str(exc)) from exc
            raise RuntimeError(str(exc)) from exc

        with session_scope(factory) as session:
            job = session.get(CreativeGenerationJobRecord, job_id)
            if job is None:
                raise NonRetryableJobError(f"Creative generation job disappeared: {job_id}")
            job.provider_job_id = created.task_id
            job.provider_status = "generating"
            session.flush()

        try:
            finished = (
                created
                if created.completed and created.generated
                else client.wait_for_nano_banana_pro_flash(
                    created.task_id,
                    poll_seconds=poll_seconds,
                    timeout_seconds=timeout_seconds,
                )
            )
        except MagnificApiError as exc:
            _mark_provider_error(factory, job_id, str(exc), provider_job_id=created.task_id)
            if not exc.retryable:
                raise NonRetryableJobError(str(exc)) from exc
            raise RuntimeError(str(exc)) from exc

        if not finished.generated:
            message = f"Magnific task {finished.task_id} completed without generated URLs."
            _mark_provider_error(factory, job_id, message, provider_job_id=finished.task_id)
            raise NonRetryableJobError(message)

        output_url = finished.generated[0]
        suffix = Path(urllib_path_name(output_url)).suffix.lower() or ".png"
        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            suffix = ".png"
        frame_slug = platform_key_for_output or aspect_ratio_for_api.replace(":", "x")
        output_path = output_dir / f"option-{option_number}-{frame_slug}{suffix}"

        try:
            client.download_to_path(output_url, output_path)
        except MagnificApiError as exc:
            _mark_provider_error(factory, job_id, str(exc), provider_job_id=finished.task_id)
            if not exc.retryable:
                raise NonRetryableJobError(str(exc)) from exc
            raise RuntimeError(str(exc)) from exc

        with session_scope(factory) as session:
            job = session.get(CreativeGenerationJobRecord, job_id)
            if job is None:
                raise NonRetryableJobError(f"Creative generation job disappeared: {job_id}")
            job.provider = "magnific_api"
            job.provider_job_id = finished.task_id
            metadata = _json_dict(job.response_metadata_json)
            metadata["magnific_api"] = {
                **(metadata.get("magnific_api") if isinstance(metadata.get("magnific_api"), dict) else {}),
                "task_id": finished.task_id,
                "status": finished.status,
                "generated": finished.generated,
            }
            job.response_metadata_json = json.dumps(metadata, indent=2)
            registered = register_social_image_job_output(
                session,
                job_id=job.id,
                output_path=output_path,
                title=f"{product_name} social image option {option_number}",
                provider_job_id=finished.task_id,
                output_url=output_url,
                notes="Generated by marketing-os-worker via Magnific API; review before planner reuse.",
            )
            # Ensure provider attribution is magnific_api after register (uses job.provider).
            registered.provider = "magnific_api"
            if registered.candidate_asset is not None:
                registered.candidate_asset.external_source = "magnific_api"
            session.flush()
            return {
                "creativeJobId": registered.id,
                "providerJobId": registered.provider_job_id,
                "providerStatus": registered.provider_status,
                "outputPath": registered.output_path,
                "outputUrl": registered.output_url,
                "candidateAssetId": registered.candidate_asset_id,
            }
    finally:
        engine.dispose()


def urllib_path_name(url: str) -> str:
    from urllib.parse import urlparse

    return Path(urlparse(url).path).name


def _reference_assets(session, job: CreativeGenerationJobRecord) -> list[AssetRecord]:
    metadata = _json_dict(job.response_metadata_json)
    ids = metadata.get("reference_asset_ids")
    asset_ids: list[int] = []
    if isinstance(ids, list):
        for value in ids:
            try:
                asset_ids.append(int(value))
            except (TypeError, ValueError):
                continue
    if not asset_ids and job.source_asset_id:
        asset_ids = [job.source_asset_id]
    if not asset_ids:
        raise NonRetryableJobError(f"Creative job {job.id} has no reference_asset_ids.")
    assets = list(session.scalars(select(AssetRecord).where(AssetRecord.id.in_(asset_ids))))
    by_id = {asset.id: asset for asset in assets}
    ordered = [by_id[asset_id] for asset_id in asset_ids if asset_id in by_id]
    if not ordered:
        raise NonRetryableJobError(f"Creative job {job.id} reference assets were not found.")
    return ordered


STAGED_REF_SOURCE_PREFIX = "magnific_upload_asset_"


def _reference_images_or_raise(
    session,
    references: list[AssetRecord],
    client: MagnificClient,
) -> list[MagnificReferenceImage]:
    """Resolve refs to Magnific-reachable https URLs; stage local files via Upload Files API."""
    images: list[MagnificReferenceImage] = []
    for index, asset in enumerate(references):
        url = https_asset_url(asset.canonical_url, asset.source_path, asset.preview_path)
        mime = (asset.mime_type or "").strip()
        if not url:
            try:
                url, mime, _staged = _stage_local_reference(session, asset, client, mime)
            except MagnificApiError as exc:
                message = f"Failed to stage local reference asset {asset.id} for Magnific: {exc}"
                if exc.retryable:
                    raise RuntimeError(message) from exc
                raise NonRetryableJobError(message) from exc
            except (OSError, ValueError) as exc:
                raise NonRetryableJobError(
                    f"Failed to stage local reference asset {asset.id} for Magnific: {exc}"
                ) from exc
        if not url:
            raise NonRetryableJobError(
                f"Reference asset {asset.id} has no https URL and no readable local image file "
                "to stage for Magnific."
            )
        mime = mime or guess_mime_type(url)
        role = REFERENCE_ROLE_TEXT[0] if index == 0 else REFERENCE_ROLE_TEXT["default"]
        images.append(MagnificReferenceImage(image=url, text=role, mime_type=mime))
    if not images:
        raise NonRetryableJobError("No https reference images available for Magnific API generation.")
    return images[:14]


def _stage_local_reference(
    session,
    asset: AssetRecord,
    client: MagnificClient,
    mime_hint: str,
) -> tuple[str, str, dict[str, object]]:
    local_path = _local_image_path(asset)
    if local_path is None:
        raise ValueError("no local image file found on disk")
    checksum = _sha256_file(local_path)
    mime = mime_hint or guess_mime_type(local_path.name)
    if mime == "image/jpg":
        mime = "image/jpeg"

    existing = _load_staged_ref(session, asset.id)
    if (
        existing
        and existing.get("checksum") == checksum
        and str(existing.get("file_id") or "").startswith("upl_")
    ):
        file_id = str(existing["file_id"])
        try:
            asset_url = client.refresh_upload_asset_url(file_id)
            return asset_url, str(existing.get("content_type") or mime), {
                "file_id": file_id,
                "checksum": checksum,
                "reused": True,
            }
        except MagnificApiError:
            # Upload expired/deleted — fall through to re-upload.
            pass

    uploaded: MagnificUploadedFile = client.upload_local_image(local_path, content_type=mime)
    meta = {
        "file_id": uploaded.file_id,
        "checksum": checksum,
        "content_type": uploaded.content_type,
        "local_path": local_path.as_posix(),
        "reused": False,
    }
    _save_staged_ref(session, asset.id, local_path.as_posix(), meta)
    return uploaded.asset_url, uploaded.content_type, meta


def _local_image_path(asset: AssetRecord) -> Path | None:
    """Prefer full-resolution source over preview thumbnails for Magnific refs."""
    for value in (asset.source_path, asset.preview_path, asset.canonical_url):
        text = (value or "").strip()
        if not text or text.startswith(("http://", "https://")):
            continue
        path = Path(text).expanduser()
        if not path.is_absolute():
            path = Path(".") / path
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            return path
    return None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _staged_source_name(asset_id: int) -> str:
    return f"{STAGED_REF_SOURCE_PREFIX}{int(asset_id)}"


def _load_staged_ref(session, asset_id: int) -> dict[str, object] | None:
    record = session.scalar(
        select(SyncMetadata).where(SyncMetadata.source_name == _staged_source_name(asset_id))
    )
    if record is None:
        return None
    try:
        data = json.loads(record.notes or "{}")
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _save_staged_ref(session, asset_id: int, source_path: str, meta: dict[str, object]) -> None:
    name = _staged_source_name(asset_id)
    record = session.scalar(select(SyncMetadata).where(SyncMetadata.source_name == name))
    notes = json.dumps(
        {
            "file_id": meta.get("file_id"),
            "checksum": meta.get("checksum"),
            "content_type": meta.get("content_type"),
            "local_path": source_path,
        },
        indent=2,
    )
    if record is None:
        session.add(
            SyncMetadata(
                source_name=name,
                source_path=source_path,
                notes=notes,
                synced_at=utc_now(),
            )
        )
    else:
        record.source_path = source_path
        record.notes = notes
        record.synced_at = utc_now()
    session.flush()



def _staged_refs_for_assets(session, references: list[AssetRecord]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for asset in references:
        existing = _load_staged_ref(session, asset.id)
        if not existing:
            continue
        out.append(
            {
                "asset_id": asset.id,
                "file_id": existing.get("file_id"),
                "checksum": existing.get("checksum"),
                "content_type": existing.get("content_type"),
            }
        )
    return out

def _mark_provider_error(
    factory,
    job_id: int,
    message: str,
    *,
    provider_job_id: str = "",
) -> None:
    with session_scope(factory) as session:
        job = session.get(CreativeGenerationJobRecord, job_id)
        if job is None:
            return
        job.provider = "magnific_api"
        job.provider_status = "queued"
        job.provider_error = message[:2000]
        if provider_job_id:
            job.provider_job_id = provider_job_id
        job.review_notes = (
            "Magnific API generation failed; job re-queued for retry or manual attach/import. "
            f"Error: {message[:400]}"
        )
        session.flush()


def _json_dict(value: str) -> dict[str, object]:
    try:
        data = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}
