from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from marketing_os.integrations import EtsyConfig, EtsyOpenApiAdapter, WebsiteConfig


class ConfigTests(unittest.TestCase):
    def test_env_file_configures_etsy_and_website_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "ETSY_KEYSTRING=etsy-key",
                        "ETSY_SHARED_SECRET=etsy-secret",
                        "ETSY_SHOP_ID=123",
                        "ETSY_SHOP_NAME=MattMadeMe",
                        "MARKETING_AGENT_API_KEY=website-token",
                        "MATTMADEME_AGENT_API_BASE_URL=https://example.test",
                    ]
                ),
                encoding="utf-8",
            )

            previous_cwd = Path.cwd()
            with patch.dict("os.environ", {}, clear=True):
                try:
                    os.chdir(tmp)
                    etsy = EtsyConfig.from_env()
                    website = WebsiteConfig.from_env()
                finally:
                    os.chdir(previous_cwd)

            self.assertTrue(etsy.configured)
            self.assertEqual(etsy.api_key, "etsy-key:etsy-secret")
            self.assertEqual(etsy.shop_id, "123")
            self.assertTrue(website.configured)
            self.assertEqual(website.api_key, "website-token")
            self.assertEqual(website.base_url, "https://example.test")

    def test_etsy_active_listing_lookup_reads_all_pages(self) -> None:
        class FakePaginatedEtsyAdapter(EtsyOpenApiAdapter):
            def __init__(self) -> None:
                self.calls: list[str] = []

            def _get(self, path: str) -> dict[str, object]:
                self.calls.append(path)
                if "offset=0" in path:
                    return {"count": 3, "results": [{"listing_id": 1}, {"listing_id": 2}]}
                if "offset=2" in path:
                    return {"count": 3, "results": [{"listing_id": 3}]}
                return {"count": 3, "results": []}

        adapter = FakePaginatedEtsyAdapter()

        listings = adapter._get_paginated("/shops/123/listings/active", limit=2)

        self.assertEqual([item["listing_id"] for item in listings], [1, 2, 3])
        self.assertEqual(
            adapter.calls,
            [
                "/shops/123/listings/active?limit=2&offset=0",
                "/shops/123/listings/active?limit=2&offset=2",
            ],
        )

    def test_etsy_adapter_throttles_requests_below_five_qps(self) -> None:
        adapter = EtsyOpenApiAdapter(EtsyConfig(keystring="key", shared_secret="secret", shop_id="123"))
        adapter._last_request_at = 100.0

        with patch("marketing_os.integrations.time.monotonic", side_effect=[100.1, 100.35]):
            with patch("marketing_os.integrations.time.sleep") as sleep:
                adapter._respect_rate_limit()

        sleep.assert_called_once()
        self.assertGreaterEqual(sleep.call_args.args[0], 0.14)


if __name__ == "__main__":
    unittest.main()
