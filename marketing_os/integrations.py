from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
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
    draft_api_key: str = ""
    measurement_api_key: str = ""
    base_url: str = "https://mattmademe.com"

    @property
    def configured(self) -> bool:
        return bool(self.api_key or self.draft_api_key or self.measurement_api_key)

    @classmethod
    def from_env(cls) -> "WebsiteConfig":
        load_local_env()
        return cls(
            api_key=os.environ.get(
                "MARKETING_AGENT_READ_API_KEY",
                os.environ.get("MARKETING_AGENT_API_KEY", ""),
            ),
            draft_api_key=os.environ.get(
                "MARKETING_AGENT_DRAFT_API_KEY",
                os.environ.get("MARKETING_AGENT_API_KEY", ""),
            ),
            measurement_api_key=os.environ.get(
                "MARKETING_AGENT_MEASUREMENT_API_KEY",
                os.environ.get("MARKETING_AGENT_API_KEY", ""),
            ),
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

    def get_reviews_by_shop(self, shop_id: str) -> list[dict[str, object]]:
        ...

    def get_reviews_by_listing(self, listing_id: str) -> list[dict[str, object]]:
        ...


class MattMadeMeWebsiteAdapter(Protocol):
    def list_published_blog_posts(self) -> list[dict[str, object]]:
        ...

    def create_blog_draft(self, draft_request: dict[str, object]) -> dict[str, object]:
        ...

    def list_products_v2(self) -> dict[str, object]:
        ...

    def create_blog_draft_v2(
        self,
        draft_request: dict[str, object],
        idempotency_key: str,
    ) -> dict[str, object]:
        ...

    def create_editorial_draft_v2(
        self,
        draft_request: dict[str, object],
        idempotency_key: str,
    ) -> dict[str, object]:
        ...

    def list_growth_events_v2(
        self,
        after: str | None = None,
        limit: int = 200,
    ) -> dict[str, object]:
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

    def get_reviews_by_shop(self, shop_id: str) -> list[dict[str, object]]:
        return self._get_paginated(f"/shops/{shop_id}/reviews")

    def get_reviews_by_listing(self, listing_id: str) -> list[dict[str, object]]:
        return self._get_paginated(f"/listings/{listing_id}/reviews")

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
        self._last_product_revision: str | None = None

    def list_published_blog_posts(self) -> list[dict[str, object]]:
        payload = self._request("GET", "/api/agent/blog")
        return _extract_results(payload, list_keys=("posts", "items", "results"))

    def create_blog_draft(self, draft_request: dict[str, object]) -> dict[str, object]:
        return self._request(
            "POST",
            "/api/agent/blog-drafts",
            draft_request,
            api_key=self.config.draft_api_key,
        )

    def list_products_v2(self) -> dict[str, object]:
        payload = self._request("GET", "/api/agent/v2/products", api_key=self.config.api_key)
        revision = payload.get("revision")
        products = payload.get("products")
        if (
            payload.get("contractVersion") != "v2"
            or not isinstance(revision, str)
            or len(revision) != 64
            or not isinstance(products, list)
            or not all(_valid_v2_product(product) for product in products)
        ):
            raise ValueError("MattMadeMe product response does not satisfy the v2 contract.")
        self._last_product_revision = revision
        return payload

    @property
    def last_product_revision(self) -> str | None:
        return self._last_product_revision

    def create_blog_draft_v2(
        self,
        draft_request: dict[str, object],
        idempotency_key: str,
    ) -> dict[str, object]:
        if not 16 <= len(idempotency_key.strip()) <= 128:
            raise ValueError("A stable idempotency key of 16 to 128 characters is required.")
        payload = self._request(
            "POST",
            "/api/agent/v2/blog-drafts",
            draft_request,
            headers={"Idempotency-Key": idempotency_key.strip()},
            api_key=self.config.draft_api_key,
        )
        if payload.get("contractVersion") != "v2" or payload.get("success") is not True:
            raise ValueError("MattMadeMe draft response does not satisfy the v2 contract.")
        return payload

    def create_editorial_draft_v2(
        self,
        draft_request: dict[str, object],
        idempotency_key: str,
    ) -> dict[str, object]:
        if not 16 <= len(idempotency_key.strip()) <= 128:
            raise ValueError("A stable idempotency key of 16 to 128 characters is required.")
        payload = self._request(
            "POST",
            "/api/agent/v2/editorial-drafts",
            draft_request,
            headers={"Idempotency-Key": idempotency_key.strip()},
            api_key=self.config.draft_api_key,
        )
        if (
            payload.get("contractVersion") != "v2"
            or payload.get("success") is not True
            or payload.get("contentType") not in {"collection", "guide"}
            or not isinstance(payload.get("revision"), str)
            or not isinstance(payload.get("previewUrl"), str)
        ):
            raise ValueError("MattMadeMe editorial response does not satisfy the v2 contract.")
        return payload

    def list_growth_events_v2(
        self,
        after: str | None = None,
        limit: int = 200,
    ) -> dict[str, object]:
        safe_limit = min(500, max(1, int(limit)))
        query = urllib.parse.urlencode(
            {
                "limit": safe_limit,
                **({"after": after} if after else {}),
            }
        )
        payload = self._request(
            "GET",
            f"/api/agent/v2/growth-events?{query}",
            api_key=self.config.measurement_api_key,
        )
        events = payload.get("events")
        if (
            payload.get("contractVersion") != "v2"
            or not isinstance(events, list)
            or not all(_valid_growth_event(event) for event in events)
            or not isinstance(payload.get("nextCursor"), str)
            or not isinstance(payload.get("hasMore"), bool)
        ):
            raise ValueError("MattMadeMe growth-event response does not satisfy the v2 contract.")
        return payload

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        api_key: str | None = None,
    ) -> dict[str, object]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            f"{self.config.base_url}{path}",
            data=data,
            headers={
                "Authorization": f"Bearer {api_key if api_key is not None else self.config.api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                **(headers or {}),
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


def _valid_v2_product(product: object) -> bool:
    if not isinstance(product, dict):
        return False
    product_id = product.get("id")
    name = product.get("name")
    canonical_path = product.get("canonicalPath")
    product_url = product.get("productUrl")
    return (
        isinstance(product_id, int)
        and product_id > 0
        and isinstance(name, str)
        and bool(name.strip())
        and isinstance(canonical_path, str)
        and canonical_path.startswith("/products/")
        and isinstance(product_url, str)
        and product_url.startswith(("https://", "http://"))
        and product_url.endswith(canonical_path)
        and isinstance(product.get("description"), str)
        and isinstance(product.get("status"), str)
        and bool(str(product.get("status")).strip())
        and _optional_string(product, "subtitle")
        and _optional_string(product, "why")
        and _optional_string(product, "material")
        and _optional_string(product, "category")
        and _string_list(product.get("tags"))
        and _string_list(product.get("perfectFor"))
        and _string_list(product.get("sizes"))
        and _url_list(product.get("images"))
        and _optional_url(product, "hero")
        and _optional_url(product, "lifestyle")
        and _optional_url(product, "etsyUrl")
        and _optional_url(product, "makerWorldUrl")
        and _valid_size_dimensions(product.get("sizeDimensions"))
    )


def _optional_string(product: dict[str, object], key: str) -> bool:
    return key not in product or product[key] is None or isinstance(product[key], str)


def _string_list(value: object) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) and bool(item.strip()) for item in value
    )


def _optional_url(product: dict[str, object], key: str) -> bool:
    value = product.get(key)
    return value is None or (
        isinstance(value, str) and value.startswith(("https://", "http://"))
    )


def _url_list(value: object) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) and item.startswith(("https://", "http://"))
        for item in value
    )


def _valid_size_dimensions(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    for size, dimensions in value.items():
        if not isinstance(size, str) or not isinstance(dimensions, dict):
            return False
        for axis, measurement in dimensions.items():
            if axis not in {"width", "depth", "height"}:
                return False
            if not isinstance(measurement, (int, float)) or isinstance(measurement, bool):
                return False
    return True


def _valid_growth_event(event: object) -> bool:
    if not isinstance(event, dict):
        return False
    allowed_fields = {
        "eventId",
        "eventKey",
        "eventName",
        "occurredAt",
        "ingestedAt",
        "source",
        "productId",
        "destinationHost",
        "landingPath",
        "pagePath",
        "campaignId",
        "contentId",
        "publicationId",
        "pinId",
        "utmCampaign",
        "utmContent",
        "expiresAt",
    }
    if set(event) - allowed_fields:
        return False
    required_strings = (
        "eventId",
        "eventKey",
        "eventName",
        "occurredAt",
        "ingestedAt",
        "destinationHost",
    )
    if not all(
        isinstance(event.get(field), str) and bool(str(event[field]).strip())
        for field in required_strings
    ):
        return False
    if event.get("eventName") != "etsy_outbound_click":
        return False
    event_id = str(event["eventId"])
    if not re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
        event_id,
        re.IGNORECASE,
    ):
        return False
    if event["eventKey"] != f"{event['occurredAt']}#{event_id}":
        return False
    try:
        datetime.fromisoformat(str(event["occurredAt"]).replace("Z", "+00:00"))
        datetime.fromisoformat(str(event["ingestedAt"]).replace("Z", "+00:00"))
    except ValueError:
        return False
    if not str(event["destinationHost"]).endswith("etsy.com"):
        return False
    if not isinstance(event.get("expiresAt"), int):
        return False
    optional_strings = (
        "source",
        "landingPath",
        "pagePath",
        "campaignId",
        "contentId",
        "publicationId",
        "pinId",
        "utmCampaign",
        "utmContent",
    )
    if not all(_optional_string(event, field) for field in optional_strings):
        return False
    product_id = event.get("productId")
    return product_id is None or (
        isinstance(product_id, int)
        and not isinstance(product_id, bool)
        and product_id > 0
    )
