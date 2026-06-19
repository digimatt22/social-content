from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db_models import AssetRecord, BlogPostRecord, ProductRecord, SyncMetadata, utc_now
from ..integrations import MattMadeMeAgentApiAdapter, MattMadeMeWebsiteAdapter, WebsiteConfig
from .product_identity import find_product_by_identity, remember_product_reference


@dataclass(frozen=True)
class WebsiteSyncSummary:
    source: str
    products_imported: int
    assets_imported: int
    blog_posts_imported: int
    errors: list[str]


def sync_mattmademe_website(
    session: Session,
    adapter: MattMadeMeWebsiteAdapter | None = None,
    config: WebsiteConfig | None = None,
) -> WebsiteSyncSummary:
    config = config or WebsiteConfig.from_env()
    if adapter is None:
        if not config.configured:
            _record_sync(session, "mattmademe_website", config.base_url, "missing_credentials: website API token is not configured.")
            return WebsiteSyncSummary("mattmademe_website", 0, 0, 0, ["MattMadeMe website API token is not configured."])
        adapter = MattMadeMeAgentApiAdapter(config)

    errors: list[str] = []
    products_imported = 0
    assets_imported = 0
    blog_posts_imported = 0
    try:
        for product_payload in adapter.list_products():
            product = upsert_website_product(session, product_payload)
            products_imported += 1
            for image_url in _image_urls(product_payload):
                upsert_website_product_image(session, product, image_url)
                assets_imported += 1
        for post_payload in adapter.list_published_blog_posts():
            upsert_website_blog_post(session, post_payload)
            blog_posts_imported += 1
        _record_sync(
            session,
            "mattmademe_website",
            config.base_url,
            f"Imported {products_imported} product(s), {assets_imported} image(s), and {blog_posts_imported} blog post(s).",
        )
    except Exception as exc:  # pragma: no cover
        message = str(exc)
        errors.append(message)
        _record_sync(session, "mattmademe_website", config.base_url, f"error: {message}")
    session.flush()
    return WebsiteSyncSummary("mattmademe_website", products_imported, assets_imported, blog_posts_imported, errors)


def upsert_website_product(session: Session, payload: dict[str, object]) -> ProductRecord:
    external_id = _text(payload, "id", "productId", "slug")
    name = _text(payload, "name", "title") or f"Website product {external_id}"
    url = _text(payload, "url", "productUrl", "canonicalUrl")
    existing = find_product_by_identity(session, "mattmademe_website", external_id, url, name)
    if existing is None:
        existing = ProductRecord(
            name=name,
            secondary_audiences_json=json.dumps(_list(payload.get("perfectFor"))),
            best_channels_json='["Website", "Facebook", "Instagram"]',
            use_cases_json=json.dumps(_list(payload.get("tags"))),
            seasonality_json="[]",
            sales_momentum_note=_text(payload, "description", "why", "story"),
        )
        session.add(existing)
    if existing.manual_override_state not in {"locked", "override"}:
        existing.name = name
        existing.secondary_audiences_json = json.dumps(_list(payload.get("perfectFor"))) or existing.secondary_audiences_json
        existing.use_cases_json = json.dumps(_list(payload.get("tags"))) or existing.use_cases_json
        existing.sales_momentum_note = _text(payload, "description", "why", "story") or existing.sales_momentum_note
        existing.sync_error = ""
    else:
        existing.sync_error = "Website sync preserved local fields because this product has a manual override."
    existing.external_source = "mattmademe_website"
    existing.external_id = external_id
    existing.canonical_url = url
    existing.last_synced_at = utc_now()
    existing.sync_status = "manual override" if existing.manual_override_state in {"locked", "override"} else "imported"
    existing.staleness_state = "fresh"
    remember_product_reference(session, existing, "mattmademe_website", external_id, url, name)
    return existing


def upsert_website_product_image(session: Session, product: ProductRecord, image_url: str) -> AssetRecord:
    external_id = image_url
    existing = session.scalar(select(AssetRecord).where(AssetRecord.external_source == "mattmademe_website", AssetRecord.external_id == external_id))
    if existing is None:
        existing = AssetRecord(
            product_id=product.id,
            name=f"{product.name} website image",
            asset_type="external listing image",
            source_path=image_url,
            preview_path=image_url,
            platform_suitability_json='["Website", "Facebook", "Instagram"]',
            readiness_state="remote website reference",
            notes="Synced from MattMadeMe.com as a remote product image reference.",
            review_state="synced",
            file_exists=0,
        )
        session.add(existing)
    existing.product_id = product.id
    existing.source_path = image_url
    existing.preview_path = image_url
    existing.external_source = "mattmademe_website"
    existing.external_id = external_id
    existing.canonical_url = image_url
    existing.last_synced_at = utc_now()
    existing.sync_status = "imported"
    existing.staleness_state = "fresh"
    existing.sync_error = ""
    if not existing.file_exists:
        existing.readiness_state = "remote website reference"
        existing.review_state = "synced"
        existing.notes = existing.notes or "Synced from MattMadeMe.com as a remote product image reference."
    return existing


def upsert_website_blog_post(session: Session, payload: dict[str, object]) -> BlogPostRecord:
    external_id = _text(payload, "id", "slug") or _text(payload, "url", "canonicalUrl")
    title = _text(payload, "headline", "title") or f"Website blog post {external_id}"
    existing = session.scalar(select(BlogPostRecord).where(BlogPostRecord.external_source == "mattmademe_website", BlogPostRecord.external_id == external_id))
    if existing is None:
        existing = BlogPostRecord(external_source="mattmademe_website", external_id=external_id, title=title)
        session.add(existing)
    existing.title = title
    existing.slug = _text(payload, "slug")
    existing.excerpt = _text(payload, "excerpt", "summary")
    existing.canonical_url = _text(payload, "url", "canonicalUrl")
    existing.tags_json = json.dumps(_list(payload.get("tags")))
    existing.raw_external_data_json = json.dumps(payload, indent=2)
    existing.last_synced_at = utc_now()
    existing.sync_status = "imported"
    existing.sync_error = ""
    existing.review_state = "imported"
    return existing


def _image_urls(payload: dict[str, object]) -> list[str]:
    urls: list[str] = []
    for key in ("heroImageUrl", "heroImage", "lifestyleImageUrl", "imageUrl"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            urls.append(value)
    for key in ("images", "imageUrls"):
        value = payload.get(key)
        if isinstance(value, list):
            urls.extend(str(item) for item in value if item)
    return list(dict.fromkeys(urls))


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


def _list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str) and value:
        return [value]
    return []


def _join(value: object) -> str:
    return ", ".join(_list(value))
