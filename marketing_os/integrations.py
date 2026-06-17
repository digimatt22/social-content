from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Protocol

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
        return cls(
            api_key=os.environ.get("MARKETING_AGENT_API_KEY", ""),
            base_url=os.environ.get("MATTMADEME_AGENT_API_BASE_URL", "https://mattmademe.com").rstrip("/"),
        )


class EtsyReadOnlyAdapter(Protocol):
    def list_active_shop_listings(self, shop_id: str) -> list[dict[str, object]]:
        ...

    def get_listing_images(self, listing_id: str) -> list[dict[str, object]]:
        ...


class MattMadeMeWebsiteAdapter(Protocol):
    def list_products(self) -> list[dict[str, object]]:
        ...

    def list_published_blog_posts(self) -> list[dict[str, object]]:
        ...

    def create_blog_draft(self, draft_request: dict[str, object]) -> dict[str, object]:
        ...


class EtsyOpenApiAdapter:
    def __init__(self, config: EtsyConfig):
        if not config.configured:
            raise ValueError("Etsy API credentials are not configured.")
        self.config = config

    def list_active_shop_listings(self, shop_id: str) -> list[dict[str, object]]:
        payload = self._get(f"/shops/{shop_id}/listings/active")
        return _extract_results(payload)

    def get_listing_images(self, listing_id: str) -> list[dict[str, object]]:
        payload = self._get(f"/listings/{listing_id}/images")
        return _extract_results(payload)

    def _get(self, path: str) -> dict[str, object]:
        request = urllib.request.Request(
            f"{self.config.base_url}{path}",
            headers={"x-api-key": self.config.api_key, "Accept": "application/json"},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))


class MattMadeMeAgentApiAdapter:
    def __init__(self, config: WebsiteConfig):
        if not config.configured:
            raise ValueError("MattMadeMe website API token is not configured.")
        self.config = config

    def list_products(self) -> list[dict[str, object]]:
        payload = self._request("GET", "/api/agent/products")
        return _extract_results(payload, list_keys=("products", "items", "results"))

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
