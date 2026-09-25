from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db_models import AssetRecord, CreativeGenerationJobRecord, GeneratedContentCandidateRecord, PlannedContentRecord, TaskRecord
from ..phase4 import asset_path, refresh_asset_file_state


PURGEABLE_ASSET_ROLES = {
    "post image option",
    "social worthy image",
    "social video option",
    "video opening card",
    "video ending card",
}


@dataclass(frozen=True)
class RejectedCleanupSummary:
    deleted_planned_item_ids: list[int]
    deleted_candidate_ids: list[int]
    deleted_asset_ids: list[int]
    deleted_creative_job_ids: list[int]
    deleted_paths: list[str]


def purge_rejected_and_canceled_items(session: Session, base_dir: str | Path = ".") -> RejectedCleanupSummary:
    refresh_asset_file_state(session)

    candidates = list(session.scalars(select(GeneratedContentCandidateRecord).order_by(GeneratedContentCandidateRecord.id)))
    assets = list(session.scalars(select(AssetRecord).order_by(AssetRecord.id)))
    jobs = list(session.scalars(select(CreativeGenerationJobRecord).order_by(CreativeGenerationJobRecord.id)))
    tasks = list(session.scalars(select(TaskRecord).order_by(TaskRecord.id)))

    assets_by_id = {asset.id: asset for asset in assets}
    rejected_candidates = [candidate for candidate in candidates if candidate.review_state == "rejected"]
    purge_candidate_ids = {candidate.id for candidate in rejected_candidates}
    affected_planned_item_ids = {candidate.planned_item_id for candidate in rejected_candidates}

    purge_asset_ids: set[int] = set()
    for candidate in rejected_candidates:
        asset_id = _candidate_asset_id(candidate)
        if asset_id is None:
            continue
        asset = assets_by_id.get(asset_id)
        if asset is not None and _is_purgeable_generated_asset(asset):
            purge_asset_ids.add(asset_id)

    for asset in assets:
        if asset.review_state == "rejected" and _is_purgeable_generated_asset(asset):
            purge_asset_ids.add(asset.id)

    purge_job_ids = {
        job.id
        for job in jobs
        if job.review_state == "rejected" or str(job.provider_status or "").strip().lower() == "canceled"
    }
    canceled_request_job_ids = {
        job.id
        for job in jobs
        if str(job.provider_status or "").strip().lower() == "canceled"
    }
    for _ in range(2):
        for job in jobs:
            metadata = _json_dict(job.response_metadata_json)
            if (
                job.id in purge_job_ids
                or job.candidate_asset_id in purge_asset_ids
                or job.source_asset_id in purge_asset_ids
                or _int_value(metadata.get("video_request_job_id")) in canceled_request_job_ids
            ):
                purge_job_ids.add(job.id)
                asset = assets_by_id.get(job.candidate_asset_id or 0)
                if asset is not None and _is_purgeable_generated_asset(asset):
                    purge_asset_ids.add(asset.id)

    deleted_paths = _delete_local_cleanup_files(
        assets=assets,
        jobs=jobs,
        purge_asset_ids=purge_asset_ids,
        purge_job_ids=purge_job_ids,
        base_dir=base_dir,
    )

    for task in tasks:
        if task.generated_content_candidate_id in purge_candidate_ids:
            task.generated_content_candidate_id = None
            if task.status == "ready to post":
                task.status = "needs copy review"
        if task.asset_id in purge_asset_ids:
            task.asset_id = None
            if task.status == "ready to post":
                task.status = "needs asset"

    for job in jobs:
        if job.id in purge_job_ids:
            session.delete(job)

    for candidate in rejected_candidates:
        session.delete(candidate)

    deleted_planned_item_ids: list[int] = []
    remaining_candidate_counts: dict[int, int] = {}
    for candidate in candidates:
        if candidate.id in purge_candidate_ids:
            continue
        remaining_candidate_counts[candidate.planned_item_id] = remaining_candidate_counts.get(candidate.planned_item_id, 0) + 1

    tasks_by_planned_item: dict[int, int] = {}
    for task in tasks:
        if task.planned_content_item_id is None:
            continue
        tasks_by_planned_item[task.planned_content_item_id] = tasks_by_planned_item.get(task.planned_content_item_id, 0) + 1

    for item_id in sorted(affected_planned_item_ids):
        if remaining_candidate_counts.get(item_id, 0):
            continue
        if tasks_by_planned_item.get(item_id, 0):
            continue
        item = session.get(PlannedContentRecord, item_id)
        if item is None:
            continue
        session.delete(item)
        deleted_planned_item_ids.append(item_id)

    deleted_assets: list[int] = []
    for asset in assets:
        if asset.id not in purge_asset_ids:
            continue
        session.delete(asset)
        deleted_assets.append(asset.id)

    session.flush()
    return RejectedCleanupSummary(
        deleted_planned_item_ids=deleted_planned_item_ids,
        deleted_candidate_ids=sorted(purge_candidate_ids),
        deleted_asset_ids=sorted(deleted_assets),
        deleted_creative_job_ids=sorted(purge_job_ids),
        deleted_paths=deleted_paths,
    )


def _candidate_asset_id(candidate: GeneratedContentCandidateRecord) -> int | None:
    body = _json_dict(candidate.body)
    try:
        return int(body.get("asset_id"))
    except (TypeError, ValueError):
        return None


def _is_purgeable_generated_asset(asset: AssetRecord) -> bool:
    if asset.asset_role in PURGEABLE_ASSET_ROLES:
        return True
    if asset.asset_type.startswith("generated "):
        return True
    if asset.asset_type == "user uploaded post image":
        return True
    if asset.source_asset_id is not None:
        return True
    return False


def _delete_local_cleanup_files(
    assets: list[AssetRecord],
    jobs: list[CreativeGenerationJobRecord],
    purge_asset_ids: set[int],
    purge_job_ids: set[int],
    base_dir: str | Path,
) -> list[str]:
    keep_paths = {
        path.resolve(strict=False)
        for asset in assets
        if asset.id not in purge_asset_ids
        for path in _local_asset_paths(asset, base_dir)
    }
    keep_paths.update(
        path.resolve(strict=False)
        for job in jobs
        if job.id not in purge_job_ids
        for path in _local_job_paths(job, base_dir)
    )

    deleted: list[str] = []
    seen: set[Path] = set()
    for asset in assets:
        if asset.id not in purge_asset_ids:
            continue
        for path in _local_asset_paths(asset, base_dir):
            resolved = path.resolve(strict=False)
            if resolved in seen or resolved in keep_paths:
                continue
            seen.add(resolved)
            if path.is_file():
                path.unlink()
                deleted.append(path.as_posix())
    for job in jobs:
        if job.id not in purge_job_ids:
            continue
        for path in _local_job_paths(job, base_dir):
            resolved = path.resolve(strict=False)
            if resolved in seen or resolved in keep_paths:
                continue
            seen.add(resolved)
            if path.is_file():
                path.unlink()
                deleted.append(path.as_posix())
    return sorted(deleted)


def _local_asset_paths(asset: AssetRecord, base_dir: str | Path) -> list[Path]:
    paths: list[Path] = []
    for value, use_asset_path in ((asset.preview_path, True), (asset.source_path, False)):
        if not _is_local_path_text(value):
            continue
        path = asset_path(asset, base_dir) if use_asset_path else _path_from_text(value, base_dir)
        if path not in paths:
            paths.append(path)
    return paths


def _local_job_paths(job: CreativeGenerationJobRecord, base_dir: str | Path) -> list[Path]:
    path = _path_from_text(job.output_path, base_dir)
    return [path] if path is not None else []


def _is_local_path_text(value: str | None) -> bool:
    text = str(value or "").strip()
    return bool(text) and not text.startswith(("http://", "https://", "file://"))


def _path_from_text(value: str | None, base_dir: str | Path) -> Path | None:
    if not _is_local_path_text(value):
        return None
    raw = Path(str(value).strip())
    if raw.is_absolute():
        return raw
    return Path(base_dir) / raw


def _json_dict(value: str | None) -> dict[str, object]:
    try:
        data = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _int_value(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
