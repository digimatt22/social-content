from __future__ import annotations

import json
import mimetypes
import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db_models import AssetRecord, ProductRecord, SyncMetadata, utc_now
from ..phase3 import slugify
from ..phase4 import refresh_asset_file_state


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
VIDEO_EXTENSIONS = {".mov", ".mp4", ".m4v"}
SCAN_EXTENSIONS = IMAGE_EXTENSIONS | DOCUMENT_EXTENSIONS | VIDEO_EXTENSIONS


@dataclass(frozen=True)
class LocalAssetLibrarySummary:
    root_path: str
    indexed: int
    missing_root: bool
    manifest_path: str


def scan_asset_root(session: Session, root_path: str | Path) -> LocalAssetLibrarySummary:
    root = Path(root_path).expanduser()
    if not root.exists():
        _record_sync(session, "local_asset_library", root.as_posix(), "missing_root: configured asset root was not found.")
        return LocalAssetLibrarySummary(root.as_posix(), 0, True, "")

    index_dir = root / "_index"
    thumb_dir = index_dir / "thumbnails"
    thumb_dir.mkdir(parents=True, exist_ok=True)

    products = list(session.scalars(select(ProductRecord).order_by(ProductRecord.name)))
    product_by_slug = {slugify(product.name): product for product in products}
    records: list[AssetRecord] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or "_index" in path.relative_to(root).parts:
            continue
        if path.suffix.lower() not in SCAN_EXTENSIONS:
            continue
        records.append(upsert_local_asset(session, root, path, thumb_dir, product_by_slug))

    session.flush()
    refresh_asset_file_state(session)
    manifest_path = index_dir / "assets-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "indexed_at": utc_now().isoformat(),
                "root_path": root.as_posix(),
                "asset_count": len(records),
                "assets": [_manifest_asset(record) for record in records],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    _record_sync(session, "local_asset_library", root.as_posix(), f"Indexed {len(records)} asset(s).")
    return LocalAssetLibrarySummary(root.as_posix(), len(records), False, manifest_path.as_posix())


def upsert_local_asset(
    session: Session,
    root: Path,
    path: Path,
    thumb_dir: Path,
    product_by_slug: dict[str, ProductRecord],
) -> AssetRecord:
    relative = path.relative_to(root).as_posix()
    role = _asset_role(path, root)
    product = _product_for_path(path, root, product_by_slug)
    external_id = relative
    existing = session.scalar(select(AssetRecord).where(AssetRecord.external_source == "local_asset_library", AssetRecord.external_id == external_id))
    if existing is None:
        existing = AssetRecord(
            product_id=product.id if product else None,
            name=path.stem.replace("-", " ").replace("_", " ").title(),
            asset_type=_asset_type(path, role),
            source_path=path.as_posix(),
            preview_path="",
            platform_suitability_json=json.dumps(_platform_fit(path, role)),
            readiness_state="indexed needs review",
            notes="Indexed from the local asset library.",
            external_source="local_asset_library",
            external_id=external_id,
            canonical_url=path.as_posix(),
            review_state="needs review",
            file_exists=1,
        )
        session.add(existing)

    stat = path.stat()
    dimensions = _image_dimensions(path)
    thumbnail = _thumbnail_for(path, thumb_dir) if path.suffix.lower() in IMAGE_EXTENSIONS else ""
    existing.product_id = product.id if product else existing.product_id
    existing.source_path = path.as_posix()
    existing.preview_path = thumbnail or existing.preview_path or path.as_posix()
    existing.external_source = "local_asset_library"
    existing.external_id = external_id
    existing.canonical_url = path.as_posix()
    existing.relative_path = relative
    existing.asset_role = role
    existing.rights = existing.rights or "owned"
    existing.brand_safe = existing.brand_safe or "review"
    existing.mime_type = mimetypes.guess_type(path.name)[0] or ""
    existing.file_size_bytes = stat.st_size
    existing.file_modified_at = datetime.fromtimestamp(stat.st_mtime)
    existing.file_checked_at = utc_now()
    existing.file_exists = 1
    existing.width = dimensions[0]
    existing.height = dimensions[1]
    existing.indexed_at = utc_now()
    existing.last_synced_at = utc_now()
    existing.sync_status = "indexed"
    existing.staleness_state = "fresh"
    existing.sync_error = ""
    return existing


def _product_for_path(path: Path, root: Path, product_by_slug: dict[str, ProductRecord]) -> ProductRecord | None:
    parts = path.relative_to(root).parts
    if len(parts) >= 3 and parts[0] == "products":
        return product_by_slug.get(parts[1])
    return None


def _asset_role(path: Path, root: Path) -> str:
    parts = path.relative_to(root).parts
    if not parts:
        return "asset"
    if parts[0] == "brand":
        return "logo" if "logos" in parts else "brand"
    if parts[0] == "products" and len(parts) >= 3:
        mapping = {
            "source": "product_photo",
            "edited": "edited_photo",
            "listing": "listing_image",
            "generated": "generated_output",
        }
        return mapping.get(parts[2], "product_asset")
    if parts[0] == "campaigns":
        return "campaign_asset"
    if parts[0] == "videos":
        return "video"
    if parts[0] == "templates":
        return "template"
    return "asset"


def _asset_type(path: Path, role: str) -> str:
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        if role == "logo":
            return "logo"
        if role == "generated_output":
            return "generated graphic"
        return "image"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    if suffix in DOCUMENT_EXTENSIONS:
        return "document"
    return "asset"


def _platform_fit(path: Path, role: str) -> list[str]:
    if role in {"product_photo", "edited_photo", "listing_image", "generated_output"}:
        return ["instagram_feed", "facebook", "etsy", "website"]
    if role == "logo":
        return ["website", "email"]
    return []


def _thumbnail_for(path: Path, thumb_dir: Path) -> str:
    digest = hashlib.sha1(path.as_posix().encode("utf-8")).hexdigest()[:12]
    target = thumb_dir / f"{path.stem}-{digest}.jpg"
    try:
        from PIL import Image

        with Image.open(path) as image:
            image.thumbnail((600, 600))
            rgb = image.convert("RGB")
            rgb.save(target, "JPEG", quality=86)
        return target.as_posix()
    except Exception:
        return ""


def _image_dimensions(path: Path) -> tuple[int | None, int | None]:
    if path.suffix.lower() not in IMAGE_EXTENSIONS:
        return (None, None)
    try:
        from PIL import Image

        with Image.open(path) as image:
            return image.size
    except Exception:
        return (None, None)


def _record_sync(session: Session, source_name: str, source_path: str, notes: str) -> None:
    record = session.scalar(select(SyncMetadata).where(SyncMetadata.source_name == source_name))
    if record is None:
        record = SyncMetadata(source_name=source_name, source_path=source_path, notes=notes)
        session.add(record)
    record.source_path = source_path
    record.notes = notes
    record.synced_at = utc_now()


def _manifest_asset(record: AssetRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "name": record.name,
        "relative_path": record.relative_path,
        "source_path": record.source_path,
        "thumbnail_path": record.preview_path,
        "asset_type": record.asset_type,
        "asset_role": record.asset_role,
        "product_id": record.product_id,
        "review_state": record.review_state,
        "width": record.width,
        "height": record.height,
        "mime_type": record.mime_type,
        "file_size_bytes": record.file_size_bytes,
    }
