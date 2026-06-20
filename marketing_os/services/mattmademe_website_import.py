from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db_models import BlogPostRecord, SyncMetadata, utc_now
from ..integrations import MattMadeMeAgentApiAdapter, MattMadeMeWebsiteAdapter, WebsiteConfig


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
        for post_payload in adapter.list_published_blog_posts():
            upsert_website_blog_post(session, post_payload)
            blog_posts_imported += 1
        _record_sync(
            session,
            "mattmademe_website",
            config.base_url,
            f"Imported {blog_posts_imported} published blog post(s). Website products are intentionally not imported.",
        )
    except Exception as exc:  # pragma: no cover
        message = str(exc)
        errors.append(message)
        _record_sync(session, "mattmademe_website", config.base_url, f"error: {message}")
    session.flush()
    return WebsiteSyncSummary("mattmademe_website", products_imported, assets_imported, blog_posts_imported, errors)


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
