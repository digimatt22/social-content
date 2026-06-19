from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.error import HTTPError

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db_models import AssetRecord, ProductRecord, SyncMetadata, utc_now
from ..integrations import EtsyConfig, EtsyOpenApiAdapter, EtsyReadOnlyAdapter
from ..phase3 import json_list
from .product_identity import find_product_by_identity, remember_product_reference


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
    cooldown_message = _active_rate_limit_message(session)
    if cooldown_message:
        return EtsySyncSummary("etsy", 0, 0, [cooldown_message])
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
        try:
            listings = adapter.list_active_shop_listings(shop_id)
        except HTTPError as exc:
            resolved_shop_id = _resolve_shop_id_after_not_found(adapter, config, exc)
            if not resolved_shop_id:
                raise
            shop_id = resolved_shop_id
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
        if _is_rate_limit_error(exc):
            message = _record_rate_limit(session, shop_id)
            return EtsySyncSummary("etsy", products_imported, assets_imported, [message])
        message = str(exc)
        errors.append(message)
        _record_sync(session, "etsy_api", shop_id, f"error: {message}")
    session.flush()
    return EtsySyncSummary("etsy", products_imported, assets_imported, errors)


def _resolve_shop_id_after_not_found(adapter: EtsyReadOnlyAdapter, config: EtsyConfig, exc: HTTPError) -> str | None:
    if exc.code != 404 or not config.shop_name:
        return None
    resolver = getattr(adapter, "find_shop_id_by_name", None)
    if not callable(resolver):
        return None
    return resolver(config.shop_name)


def _is_rate_limit_error(exc: Exception) -> bool:
    return isinstance(exc, HTTPError) and exc.code == 429


def _active_rate_limit_message(session: Session) -> str | None:
    record = session.scalar(select(SyncMetadata).where(SyncMetadata.source_name == "etsy_api"))
    if record is None:
        return None
    until = _rate_limited_until(record.notes)
    if until is None or until <= utc_now():
        return None
    return f"Etsy API sync is paused until {until.isoformat()} UTC because Etsy returned a rate limit response."


def _record_rate_limit(session: Session, shop_id: str) -> str:
    until = utc_now() + timedelta(hours=24)
    message = f"rate_limited_until={until.isoformat()} Etsy returned 429 Too Many Requests; sync is paused for 24 hours."
    _record_sync(session, "etsy_api", shop_id, message)
    session.flush()
    return f"Etsy returned 429 Too Many Requests. Etsy API sync is paused until {until.isoformat()} UTC."


def _rate_limited_until(notes: str) -> datetime | None:
    marker = "rate_limited_until="
    if marker not in notes:
        return None
    raw_value = notes.split(marker, 1)[1].split(maxsplit=1)[0]
    try:
        return datetime.fromisoformat(raw_value)
    except ValueError:
        return None


def upsert_etsy_listing_product(session: Session, listing: dict[str, object]) -> ProductRecord:
    listing_id = _text(listing, "listing_id", "id")
    title = _text(listing, "title", "name") or f"Etsy listing {listing_id}"
    url = _text(listing, "url", "listing_url") or (f"https://www.etsy.com/listing/{listing_id}" if listing_id else "")
    state = _text(listing, "state", "status") or "active"
    existing = find_product_by_identity(session, "etsy", listing_id, url, title)
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
    remember_product_reference(session, existing, "etsy", listing_id, url, title)
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
        return _clean_text(str(value))
    return ""


def _list_text(payload: dict[str, object], key: str) -> list[str]:
    value = payload.get(key)
    if isinstance(value, list):
        return [_clean_text(str(item)) for item in value]
    if isinstance(value, str):
        return [_clean_text(item) for item in json_list(value)]
    return []


def _clean_text(value: str) -> str:
    normalized = re.sub(r"&(\d+);", r"&#\1;", value)
    return html.unescape(normalized).strip()
