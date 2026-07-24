from __future__ import annotations

import unittest

from marketing_os.integrations import MattMadeMeAgentApiAdapter, WebsiteConfig


class RecordingWebsiteAdapter(MattMadeMeAgentApiAdapter):
    def __init__(self) -> None:
        super().__init__(
            WebsiteConfig(
                api_key="read-test",
                draft_api_key="draft-test",
                measurement_api_key="measurement-test",
                base_url="https://example.test",
            )
        )
        self.calls: list[tuple[str, str, dict | None, dict | None, str | None]] = []
        self.responses: list[dict] = []

    def _request(self, method, path, body=None, headers=None, api_key=None):
        self.calls.append((method, path, body, headers, api_key))
        return self.responses.pop(0)


class Phase1WebsiteContractTests(unittest.TestCase):
    def test_v2_product_contract_requires_version_and_products(self) -> None:
        adapter = RecordingWebsiteAdapter()
        adapter.responses.append(
            {
                "contractVersion": "v2",
                "revision": "a" * 64,
                "complete": True,
                "productCount": 1,
                "products": [
                    {
                        "id": 9,
                        "name": "Dispatcher Duck",
                        "description": "A dispatcher duck.",
                        "status": "ACTIVE",
                        "canonicalPath": "/products/dispatcher-duck-9",
                        "productUrl": "https://example.test/products/dispatcher-duck-9",
                        "tags": [],
                        "perfectFor": [],
                        "sizes": [],
                        "images": [],
                        "sizeDimensions": {},
                    }
                ],
            }
        )
        payload = adapter.list_products_v2()
        self.assertEqual("a" * 64, payload["revision"])
        self.assertEqual(("GET", "/api/agent/v2/products"), adapter.calls[0][:2])

    def test_v2_draft_contract_sends_idempotency_and_requires_preview_response(self) -> None:
        adapter = RecordingWebsiteAdapter()
        adapter.responses.append(
            {
                "success": True,
                "idempotent": False,
                "contractVersion": "v2",
                "slug": "draft",
                "previewAdminUrl": "https://example.test/admin/cms/blog",
            }
        )
        payload = adapter.create_blog_draft_v2(
            {"headline": "Draft", "body": "Review me"},
            "phase1:blog-draft:one",
        )
        self.assertFalse(payload["idempotent"])
        self.assertEqual(
            {"Idempotency-Key": "phase1:blog-draft:one"},
            adapter.calls[0][3],
        )
        self.assertEqual("POST", adapter.calls[0][0])
        self.assertEqual("/api/agent/v2/blog-drafts", adapter.calls[0][1])

    def test_v2_contract_rejects_unversioned_or_short_idempotency(self) -> None:
        adapter = RecordingWebsiteAdapter()
        adapter.responses.append({"products": []})
        with self.assertRaisesRegex(ValueError, "v2 contract"):
            adapter.list_products_v2()
        with self.assertRaisesRegex(ValueError, "16 to 128"):
            adapter.create_blog_draft_v2({"headline": "x", "body": "y"}, "short")

    def test_malformed_catalog_preserves_last_known_revision(self) -> None:
        adapter = RecordingWebsiteAdapter()
        adapter.responses.extend(
            [
                {
                    "contractVersion": "v2",
                    "revision": "b" * 64,
                    "complete": True,
                    "productCount": 1,
                    "products": [
                        {
                            "id": 9,
                            "name": "Dispatcher Duck",
                            "description": "A dispatcher duck.",
                            "status": "ACTIVE",
                            "canonicalPath": "/products/dispatcher-duck-9",
                            "productUrl": "https://example.test/products/dispatcher-duck-9",
                            "tags": [],
                            "perfectFor": [],
                            "sizes": [],
                            "images": [],
                            "sizeDimensions": {},
                        }
                    ],
                },
                {
                    "contractVersion": "v2",
                    "revision": "c" * 64,
                    "complete": True,
                    "productCount": 1,
                    "products": [{"id": "bad"}],
                },
            ]
        )
        adapter.list_products_v2()
        with self.assertRaisesRegex(ValueError, "v2 contract"):
            adapter.list_products_v2()
        self.assertEqual("b" * 64, adapter.last_product_revision)

    def test_catalog_rejects_malformed_automation_fields(self) -> None:
        valid_product = {
            "id": 9,
            "name": "Dispatcher Duck",
            "description": "A dispatcher duck.",
            "status": "ACTIVE",
            "canonicalPath": "/products/dispatcher-duck-9",
            "productUrl": "https://example.test/products/dispatcher-duck-9",
            "tags": [],
            "perfectFor": [],
            "sizes": [],
            "images": ["https://example.test/dispatcher.jpg"],
            "sizeDimensions": {},
        }
        invalid_values = {
            "description": None,
            "status": "",
            "images": [42],
            "tags": ["ok", 42],
            "sizeDimensions": {"small": {"width": "wide"}},
            "etsyUrl": "not-a-url",
        }
        for field, value in invalid_values.items():
            with self.subTest(field=field):
                adapter = RecordingWebsiteAdapter()
                adapter.responses.append(
                    {
                        "contractVersion": "v2",
                        "revision": "e" * 64,
                        "complete": True,
                        "productCount": 1,
                        "products": [{**valid_product, field: value}],
                    }
                )
                with self.assertRaisesRegex(ValueError, "v2 contract"):
                    adapter.list_products_v2()
                self.assertIsNone(adapter.last_product_revision)

    def test_editorial_draft_contract_uses_write_credential(self) -> None:
        adapter = RecordingWebsiteAdapter()
        adapter.responses.append(
            {
                "success": True,
                "idempotent": False,
                "contractVersion": "v2",
                "contentType": "guide",
                "revision": "d" * 64,
                "previewUrl": "https://example.test/preview/editorial/guide/example",
            }
        )
        payload = adapter.create_editorial_draft_v2(
            {
                "contentType": "guide",
                "slug": "example",
                "title": "Example",
            },
            "phase1:editorial:one",
        )
        self.assertEqual("guide", payload["contentType"])
        self.assertEqual("/api/agent/v2/editorial-drafts", adapter.calls[0][1])
        self.assertEqual("draft-test", adapter.calls[0][4])

    def test_editorial_read_contract_uses_catalog_credential_and_complete_snapshot(self) -> None:
        adapter = RecordingWebsiteAdapter()
        adapter.responses.append(
            {
                "contractVersion": "v2",
                "complete": True,
                "pageCount": 1,
                "revision": "f" * 64,
                "pages": [
                    {
                        "id": "guide:mail-carrier-gifts",
                        "pageType": "guide",
                        "canonicalPath": "/guides/mail-carrier-gifts",
                        "canonicalUrl": "https://example.test/guides/mail-carrier-gifts",
                        "status": "published",
                        "productIds": [9],
                        "intentKeys": ["mail-carrier-gifts"],
                        "ready": True,
                        "readinessReason": "verified",
                        "publishedAt": None,
                        "revision": "e" * 64,
                    }
                ],
            }
        )
        payload = adapter.list_editorial_v2()
        self.assertEqual(1, payload["pageCount"])
        self.assertEqual(("GET", "/api/agent/v2/editorial"), adapter.calls[0][:2])
        self.assertEqual("read-test", adapter.calls[0][4])

    def test_growth_event_contract_uses_measurement_credential(self) -> None:
        adapter = RecordingWebsiteAdapter()
        adapter.responses.append(
            {
                "contractVersion": "v2",
                "events": [
                    {
                        "eventId": "123e4567-e89b-42d3-a456-426614174000",
                        "eventKey": "2026-07-24T12:00:00.000Z#123e4567-e89b-42d3-a456-426614174000",
                        "eventName": "etsy_outbound_click",
                        "occurredAt": "2026-07-24T12:00:00.000Z",
                        "ingestedAt": "2026-07-24T12:00:01.000Z",
                        "destinationHost": "www.etsy.com",
                        "productId": 9,
                        "publicationId": "publication-1",
                        "expiresAt": 1816430400,
                    }
                ],
                "nextCursor": "2026-07-24T12:00:00.000Z#123e4567-e89b-42d3-a456-426614174000",
                "hasMore": False,
            }
        )
        payload = adapter.list_growth_events_v2(after="cursor-1", limit=999)
        self.assertEqual("publication-1", payload["events"][0]["publicationId"])
        self.assertIn("limit=500", adapter.calls[0][1])
        self.assertIn("after=cursor-1", adapter.calls[0][1])
        self.assertEqual("measurement-test", adapter.calls[0][4])

    def test_growth_event_contract_rejects_unapproved_shape(self) -> None:
        adapter = RecordingWebsiteAdapter()
        adapter.responses.append(
            {
                "contractVersion": "v2",
                "events": [
                    {
                        "eventId": "123e4567-e89b-42d3-a456-426614174000",
                        "eventKey": "2026-07-24T12:00:00.000Z#123e4567-e89b-42d3-a456-426614174000",
                        "eventName": "pageview",
                        "occurredAt": "2026-07-24T12:00:00.000Z",
                        "ingestedAt": "2026-07-24T12:00:01.000Z",
                        "destinationHost": "example.test",
                        "expiresAt": 1816430400,
                    }
                ],
                "nextCursor": "key",
                "hasMore": False,
            }
        )
        with self.assertRaisesRegex(ValueError, "growth-event"):
            adapter.list_growth_events_v2()

    def test_growth_event_contract_rejects_unknown_fields(self) -> None:
        adapter = RecordingWebsiteAdapter()
        adapter.responses.append(
            {
                "contractVersion": "v2",
                "events": [
                    {
                        "eventId": "123e4567-e89b-42d3-a456-426614174000",
                        "eventKey": "2026-07-24T12:00:00.000Z#123e4567-e89b-42d3-a456-426614174000",
                        "eventName": "etsy_outbound_click",
                        "occurredAt": "2026-07-24T12:00:00.000Z",
                        "ingestedAt": "2026-07-24T12:00:01.000Z",
                        "destinationHost": "www.etsy.com",
                        "expiresAt": 1816430400,
                        "accidentalPii": "must-not-cross",
                    }
                ],
                "nextCursor": "key",
                "hasMore": False,
            }
        )
        with self.assertRaisesRegex(ValueError, "growth-event"):
            adapter.list_growth_events_v2()


if __name__ == "__main__":
    unittest.main()
