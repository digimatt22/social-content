from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db_models import AssetRecord, ProductRecord, SyncMetadata, utc_now
from ..integrations import EtsyConfig, EtsyOpenApiAdapter, EtsyReadOnlyAdapter
from ..phase3 import json_list


@dataclass(frozen=True)
class EtsySyncSummary:
    source: str
    products_imported: int
    assets_imported: int
    errors: list[str]


def sync_etsy_read_only(
    session: Session,
    adapter: EtsyReadOnlyAdapter | None = None,
    config: EtsyConfig | None = None,
) -> EtsySyncSummary:
    config = config or EtsyConfig.from_env()
    if adapter is None:
        if not config.configured:
            _record_sync(session, "etsy_api", "missing_credentials", "Etsy API credentials are not configured.")
            return EtsySyncSummary("etsy", 0, 0, ["Etsy API credentials are not configured."])
        adapter = EtsyOpenApiAdapter(config)

    shop_id = config.shop_id or "fixture-shop"
    errors: list[str] = []
    products_imported = 0
    assets_imported = 0
    try:
        listings = adapter.list_active_shop_listings(shop_id)
        for listing in listings:
            product = upsert_etsy_listing_product(session, listing)
            products_imported += 1
            listing_id = _text(listing, "listing_id", "id")
            if listing_id:
                for image in adapter.get_listing_images(listing_id):
                    upsert_etsy_listing_image(session, product, listing_id, image)
                    assets_imported += 1
        _record_sync(session, "etsy_api", shop_id, f"Imported {products_imported} listing(s) and {assets_imported} image(s).")
    except Exception as exc:  # pragma: no cover - exercised via fake/service-level tests for normal flow.
        message = str(exc)
        errors.append(message)
        _record_sync(session, "etsy_api", shop_id, f"error: {message}")
    session.flush()
    return EtsySyncSummary("etsy", products_imported, assets_imported, errors)


def upsert_etsy_listing_product(session: Session, listing: dict[str, object]) -> ProductRecord:
    listing_id = _text(listing, "listing_id", "id")
    title = _text(listing, "title", "name") or f"Etsy listing {listing_id}"
    url = _text(listing, "url", "listing_url") or (f"https://www.etsy.com/listing/{listing_id}" if listing_id else "")
    state = _text(listing, "state", "status") or "active"
    existing = _find_product(session, "etsy", listing_id, url, title)
    if existing is None:
        existing = ProductRecord(
            name=title,
            status=state,
            primary_audience="Needs review",
            secondary_audiences_json="[]",
            best_channels_json='["Etsy", "Facebook", "Instagram"]',
            use_cases_json=json.dumps(_list_text(listing, "tags")[:6]),
            seasonality_json="[]",
            sales_momentum_note=_text(listing, "description")[:500],
            launch_priority="medium",
        )
        session.add(existing)
    if existing.manual_override_state not in {"locked", "override"}:
        existing.name = existing.name or title
        existing.status = state
        existing.sales_momentum_note = _text(listing, "description")[:500] or existing.sales_momentum_note
        existing.sync_error = ""
    else:
        existing.sync_error = "Etsy sync preserved local fields because this product has a manual override."
    existing.external_source = "etsy"
    existing.external_id = listing_id
    existing.canonical_url = url
    existing.last_synced_at = utc_now()
    existing.sync_status = "manual override" if existing.manual_override_state in {"locked", "override"} else "imported"
    existing.staleness_state = "fresh"
    return existing


def upsert_etsy_listing_image(session: Session, product: ProductRecord, listing_id: str, image: dict[str, object]) -> AssetRecord:
    image_id = _text(image, "listing_image_id", "image_id", "id") or f"{listing_id}-{_text(image, 'rank')}"
    full_url = _text(image, "url_fullxfull", "url_full", "url", "src")
    preview_url = _text(image, "url_570xN", "url_170x135", "url_75x75") or full_url
    existing = session.scalar(select(AssetRecord).where(AssetRecord.external_source == "etsy", AssetRecord.external_id == image_id))
    if existing is None:
        existing = AssetRecord(
            product_id=product.id,
            name=f"{product.name} Etsy image",
            asset_type="Etsy product photo",
            source_path=full_url,
            preview_path=preview_url,
            platform_suitability_json='["Etsy", "Facebook", "Instagram"]',
            readiness_state="external source needs review",
            notes="Imported as an external Etsy image reference.",
            review_state="needs review",
            file_exists=0,
        )
        session.add(existing)
    existing.product_id = product.id
    existing.source_path = full_url or existing.source_path
    existing.preview_path = preview_url or existing.preview_path
    existing.external_source = "etsy"
    existing.external_id = image_id
    existing.canonical_url = full_url or preview_url
    existing.last_synced_at = utc_now()
    existing.sync_status = "imported"
    existing.staleness_state = "fresh"
    existing.sync_error = ""
    return existing


def _find_product(session: Session, source: str, external_id: str, url: str, title: str) -> ProductRecord | None:
    if external_id:
        record = session.scalar(select(ProductRecord).where(ProductRecord.external_source == source, ProductRecord.external_id == external_id))
        if record:
            return record
    if url:
        record = session.scalar(select(ProductRecord).where(ProductRecord.canonical_url == url))
        if record:
            return record
    return session.scalar(select(ProductRecord).where(ProductRecord.name == title))


def _record_sync(session: Session, source_name: str, source_path: str, notes: str) -> None:
    record = session.scalar(select(SyncMetadata).where(SyncMetadata.source_name == source_name))
    if record is None:
        record = SyncMetadata(source_name=source_name, source_path=source_path, notes=notes)
        session.add(record)
    record.source_path = source_path
    record.notes = notes
    record.synced_at = utc_now()


def _text(payload: dict[str, object], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        return str(value)
    return ""


def _list_text(payload: dict[str, object], key: str) -> list[str]:
    value = payload.get(key)
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return json_list(value)
    return []
