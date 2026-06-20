from __future__ import annotations

import html
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.error import HTTPError

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db_models import AssetRecord, EtsyReviewRecord, ProductRecord, SyncMetadata, utc_now
from ..integrations import EtsyConfig, EtsyOpenApiAdapter, EtsyReadOnlyAdapter
from ..phase3 import json_list
from .product_identity import find_product_by_identity, remember_product_reference


@dataclass(frozen=True)
class EtsySyncSummary:
    source: str
    products_imported: int
    assets_imported: int
    errors: list[str]
    reviews_imported: int = 0


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
    reviews_imported = 0
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
            listing_id = _text(listing, "listing_id", "id")
            listing_payload = _full_listing_payload(adapter, listing, listing_id)
            product = upsert_etsy_listing_product(session, listing_payload)
            products_imported += 1
            if listing_id:
                for image in _listing_images(adapter, listing_id, listing_payload):
                    upsert_etsy_listing_image(session, product, listing_id, image)
                    assets_imported += 1
        reviews_imported = _sync_reviews(session, adapter, shop_id)
        _record_sync(
            session,
            "etsy_api",
            shop_id,
            f"Imported {products_imported} listing(s), {assets_imported} image(s), and {reviews_imported} review(s).",
        )
    except Exception as exc:  # pragma: no cover - exercised via fake/service-level tests for normal flow.
        if _is_rate_limit_error(exc):
            message = _record_rate_limit(session, shop_id)
            return EtsySyncSummary("etsy", products_imported, assets_imported, [message], reviews_imported=reviews_imported)
        message = str(exc)
        errors.append(message)
        _record_sync(session, "etsy_api", shop_id, f"error: {message}")
    session.flush()
    return EtsySyncSummary("etsy", products_imported, assets_imported, errors, reviews_imported=reviews_imported)


def _resolve_shop_id_after_not_found(adapter: EtsyReadOnlyAdapter, config: EtsyConfig, exc: HTTPError) -> str | None:
    if exc.code != 404 or not config.shop_name:
        return None
    resolver = getattr(adapter, "find_shop_id_by_name", None)
    if not callable(resolver):
        return None
    return resolver(config.shop_name)


def _full_listing_payload(adapter: EtsyReadOnlyAdapter, listing: dict[str, object], listing_id: str) -> dict[str, object]:
    description = _text(listing, "description")
    if not listing_id or len(description) != 500:
        return listing
    detail_reader = getattr(adapter, "get_listing", None)
    if not callable(detail_reader):
        return listing
    detail = detail_reader(listing_id)
    if not isinstance(detail, dict):
        return listing
    merged = dict(listing)
    merged.update(detail)
    return merged


def _listing_images(adapter: EtsyReadOnlyAdapter, listing_id: str, listing: dict[str, object]) -> list[dict[str, object]]:
    included_images = listing.get("images")
    if isinstance(included_images, list):
        images = [image for image in included_images if isinstance(image, dict)]
        if images:
            return sorted(images, key=_image_sort_key)
    return sorted(adapter.get_listing_images(listing_id), key=_image_sort_key)


def _image_sort_key(image: dict[str, object]) -> tuple[int, str]:
    try:
        rank = int(image.get("rank") or 999)
    except (TypeError, ValueError):
        rank = 999
    image_id = _text(image, "listing_image_id", "image_id", "id")
    return (rank, image_id)


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
    description = _text(listing, "description")
    existing = find_product_by_identity(session, "etsy", listing_id, url, title)
    if existing is None:
        existing = ProductRecord(
            name=title,
            secondary_audiences_json="[]",
            best_channels_json='["Etsy", "Facebook", "Instagram"]',
            use_cases_json="[]",
            seasonality_json="[]",
            sales_momentum_note=description,
        )
        session.add(existing)
    if existing.manual_override_state not in {"locked", "override"}:
        existing.name = existing.name or title
        existing.sales_momentum_note = description or existing.sales_momentum_note
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
    image_id = _text(image, "listing_image_id", "image_id", "id") or _text(image, "rank")
    external_id = _listing_image_external_id(listing_id, image_id)
    full_url = _text(image, "url_fullxfull", "url_full", "url", "src")
    preview_url = _text(image, "url_570xN", "url_170x135", "url_75x75") or full_url
    existing = session.scalar(select(AssetRecord).where(AssetRecord.external_source == "etsy", AssetRecord.external_id == external_id))
    if existing is None:
        existing = AssetRecord(
            product_id=product.id,
            name=f"{product.name} Etsy image",
            asset_type="Etsy product photo",
            source_path=full_url,
            preview_path=preview_url,
            platform_suitability_json='["Etsy", "Facebook", "Instagram"]',
            readiness_state="remote Etsy reference",
            notes="Synced from Etsy as a remote listing image reference.",
            review_state="synced",
            file_exists=0,
        )
        session.add(existing)
    existing.product_id = product.id
    existing.source_path = full_url or existing.source_path
    existing.preview_path = preview_url or existing.preview_path
    existing.external_source = "etsy"
    existing.external_id = external_id
    existing.canonical_url = full_url or preview_url
    existing.last_synced_at = utc_now()
    existing.sync_status = "imported"
    existing.staleness_state = "fresh"
    existing.sync_error = ""
    if not existing.file_exists:
        existing.readiness_state = "remote Etsy reference"
        existing.review_state = "synced"
        existing.notes = existing.notes or "Synced from Etsy as a remote listing image reference."
    return existing


def _sync_reviews(session: Session, adapter: EtsyReadOnlyAdapter, shop_id: str) -> int:
    review_reader = getattr(adapter, "get_reviews_by_shop", None)
    if not callable(review_reader):
        return 0
    reviews = review_reader(shop_id)
    imported = 0
    for review in reviews:
        if not isinstance(review, dict):
            continue
        upsert_etsy_review(session, review)
        imported += 1
    return imported


def upsert_etsy_review(session: Session, review: dict[str, object]) -> EtsyReviewRecord:
    listing_id = _text(review, "listing_id")
    transaction_id = _text(review, "transaction_id")
    external_id = _review_external_id(review, listing_id, transaction_id)
    existing = session.scalar(
        select(EtsyReviewRecord).where(EtsyReviewRecord.external_source == "etsy_api", EtsyReviewRecord.external_id == external_id)
    )
    if existing is None:
        existing = EtsyReviewRecord(external_source="etsy_api", external_id=external_id)
        session.add(existing)
    product = _product_for_listing_id(session, listing_id)
    existing.product_id = product.id if product is not None else None
    existing.shop_id = _text(review, "shop_id")
    existing.listing_id = listing_id
    existing.transaction_id = transaction_id
    existing.buyer_user_id = _text(review, "buyer_user_id")
    existing.rating = _int_or_none(review.get("rating"))
    existing.review = _text(review, "review")
    existing.language = _text(review, "language")
    existing.image_url_fullxfull = _text(review, "image_url_fullxfull")
    existing.created_timestamp = _int_or_none(review.get("created_timestamp") or review.get("create_timestamp"))
    existing.updated_timestamp = _int_or_none(review.get("updated_timestamp") or review.get("update_timestamp"))
    existing.raw_data_json = json.dumps(review, sort_keys=True, default=str)
    existing.imported_at = existing.imported_at or utc_now()
    existing.updated_at = utc_now()
    return existing


def _product_for_listing_id(session: Session, listing_id: str) -> ProductRecord | None:
    if not listing_id:
        return None
    return session.scalar(select(ProductRecord).where(ProductRecord.external_source == "etsy", ProductRecord.external_id == listing_id))


def _review_external_id(review: dict[str, object], listing_id: str, transaction_id: str) -> str:
    if transaction_id:
        return f"transaction:{transaction_id}"
    created = _text(review, "created_timestamp", "create_timestamp")
    review_text = _text(review, "review")
    digest = hashlib.sha1(f"{listing_id}|{created}|{review_text}".encode("utf-8")).hexdigest()[:16]
    return f"listing:{listing_id or 'unknown'}:{created or 'unknown'}:{digest}"


def _listing_image_external_id(listing_id: str, image_id: str) -> str:
    return f"{listing_id}:{image_id or 'unranked'}"


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


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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
