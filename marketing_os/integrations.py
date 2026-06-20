from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from .config import load_local_env
from .models import CalendarEntry, ContentIdea


class Publisher(Protocol):
    """Future extension point for external publishing integrations."""

    def publish(self, idea: ContentIdea) -> str:
        ...


class AnalyticsProvider(Protocol):
    """Future extension point for Etsy, social, website, or email analytics."""

    def summarize(self) -> dict[str, str | int | float]:
        ...


class MockPublisher:
    """Local mock publisher used in Phase 1 instead of external APIs."""

    def publish(self, idea: ContentIdea) -> str:
        return f"MOCK-PUBLISH {idea.platform}: {idea.title}"


class MockAnalyticsProvider:
    """Local mock analytics provider used until real integrations are added."""

    def summarize(self) -> dict[str, str | int | float]:
        return {
            "source": "mock",
            "status": "No external analytics configured in Phase 1",
        }


class CalendarExporter(Protocol):
    def export(self, entries: list[CalendarEntry]) -> str:
        ...


class MarkdownCalendarExporter:
    def export(self, entries: list[CalendarEntry]) -> str:
        lines = [
            "| Date | Platform | Type | Objective | CTA | Featured Product |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for entry in entries:
            lines.append(
                f"| {entry.date.isoformat()} | {entry.platform} | {entry.content_type} | "
                f"{entry.objective} | {entry.cta} | {entry.featured_product} |"
            )
        return "\n".join(lines)


@dataclass(frozen=True)
class EtsyConfig:
    keystring: str
    shared_secret: str
    shop_id: str
    shop_name: str = ""
    base_url: str = "https://openapi.etsy.com/v3/application"

    @property
    def api_key(self) -> str:
        return f"{self.keystring}:{self.shared_secret}" if self.shared_secret else self.keystring

    @property
    def configured(self) -> bool:
        return bool(self.keystring and self.shared_secret and self.shop_id)

    @classmethod
    def from_env(cls) -> "EtsyConfig":
        load_local_env()
        return cls(
            keystring=os.environ.get("ETSY_KEYSTRING", ""),
            shared_secret=os.environ.get("ETSY_SHARED_SECRET", ""),
            shop_id=os.environ.get("ETSY_SHOP_ID", ""),
            shop_name=os.environ.get("ETSY_SHOP_NAME", ""),
        )


@dataclass(frozen=True)
class WebsiteConfig:
    api_key: str
    base_url: str = "https://mattmademe.com"

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    @classmethod
    def from_env(cls) -> "WebsiteConfig":
        load_local_env()
        return cls(
            api_key=os.environ.get("MARKETING_AGENT_API_KEY", ""),
            base_url=os.environ.get("MATTMADEME_AGENT_API_BASE_URL", "https://mattmademe.com").rstrip("/"),
        )


class EtsyReadOnlyAdapter(Protocol):
    def find_shop_id_by_name(self, shop_name: str) -> str | None:
        ...

    def list_active_shop_listings(self, shop_id: str) -> list[dict[str, object]]:
        ...

    def get_listing(self, listing_id: str) -> dict[str, object]:
        ...

    def get_listing_images(self, listing_id: str) -> list[dict[str, object]]:
        ...


class MattMadeMeWebsiteAdapter(Protocol):
    def list_published_blog_posts(self) -> list[dict[str, object]]:
        ...

    def create_blog_draft(self, draft_request: dict[str, object]) -> dict[str, object]:
        ...


class EtsyOpenApiAdapter:
    MIN_REQUEST_INTERVAL_SECONDS = 0.25

    def __init__(self, config: EtsyConfig):
        if not config.configured:
            raise ValueError("Etsy API credentials are not configured.")
        self.config = config
        self._last_request_at = 0.0

    def list_active_shop_listings(self, shop_id: str) -> list[dict[str, object]]:
        return self._get_paginated(f"/shops/{shop_id}/listings/active")

    def find_shop_id_by_name(self, shop_name: str) -> str | None:
        query = urllib.parse.urlencode({"shop_name": shop_name, "limit": 5})
        payload = self._get(f"/shops?{query}")
        normalized = shop_name.casefold()
        for shop in _extract_results(payload):
            candidate_name = str(shop.get("shop_name") or "")
            if candidate_name.casefold() == normalized and shop.get("shop_id"):
                return str(shop["shop_id"])
        for shop in _extract_results(payload):
            if shop.get("shop_id"):
                return str(shop["shop_id"])
        return None

    def get_listing(self, listing_id: str) -> dict[str, object]:
        return self._get(f"/listings/{listing_id}?{urllib.parse.urlencode({'includes': 'Images'})}")

    def get_listing_images(self, listing_id: str) -> list[dict[str, object]]:
        payload = self._get(f"/listings/{listing_id}/images")
        return _extract_results(payload)

    def _get_paginated(self, path: str, limit: int = 100) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        offset = 0
        while True:
            separator = "&" if "?" in path else "?"
            payload = self._get(f"{path}{separator}{urllib.parse.urlencode({'limit': limit, 'offset': offset})}")
            page = _extract_results(payload)
            results.extend(page)
            count = _int_payload_value(payload.get("count"))
            if not page or count is None or len(results) >= count:
                return results
            offset += len(page)

    def _get(self, path: str) -> dict[str, object]:
        self._respect_rate_limit()
        request = urllib.request.Request(
            f"{self.config.base_url}{path}",
            headers={"x-api-key": self.config.api_key, "Accept": "application/json"},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def _respect_rate_limit(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_request_at
        wait_seconds = self.MIN_REQUEST_INTERVAL_SECONDS - elapsed
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        self._last_request_at = time.monotonic()


class MattMadeMeAgentApiAdapter:
    def __init__(self, config: WebsiteConfig):
        if not config.configured:
            raise ValueError("MattMadeMe website API token is not configured.")
        self.config = config

    def list_published_blog_posts(self) -> list[dict[str, object]]:
        payload = self._request("GET", "/api/agent/blog")
        return _extract_results(payload, list_keys=("posts", "items", "results"))

    def create_blog_draft(self, draft_request: dict[str, object]) -> dict[str, object]:
        return self._request("POST", "/api/agent/blog-drafts", draft_request)

    def _request(self, method: str, path: str, body: dict[str, object] | None = None) -> dict[str, object]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            f"{self.config.base_url}{path}",
            data=data,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method=method,
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))


def _extract_results(payload: dict[str, object], list_keys: tuple[str, ...] = ("results", "items")) -> list[dict[str, object]]:
    for key in list_keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _int_payload_value(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
