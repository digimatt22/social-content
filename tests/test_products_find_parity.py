from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from marketing_os.db import session_scope
from marketing_os.db_models import AssetRecord, PrincipalRecord, ProductRecord
from marketing_os.secure_app import create_secure_app
from marketing_os.services.auth import create_service_credential
from marketing_os.web_app import create_app


class ProductsFindParityTests(unittest.TestCase):
    def _seed_catalog(self, factory) -> tuple[int, int]:
        with session_scope(factory) as session:
            duck = ProductRecord(
                name="Find Duck",
                use_cases_json=json.dumps(["gift", "holiday"]),
                sync_status="imported",
            )
            goose = ProductRecord(
                name="Other Goose",
                use_cases_json=json.dumps(["nursery"]),
                sync_status="local",
            )
            blank = ProductRecord(name="Untagged Widget", use_cases_json="[]", sync_status="local")
            session.add_all([duck, goose, blank])
            session.flush()
            session.add(
                AssetRecord(
                    product_id=duck.id,
                    name="Duck default ref",
                    asset_type="source photo",
                    source_path="https://example.test/duck.jpg",
                    preview_path="https://example.test/duck.jpg",
                    readiness_state="remote reference",
                    review_state="approved",
                    default_reference=1,
                )
            )
            session.add(
                AssetRecord(
                    product_id=duck.id,
                    name="Duck secondary",
                    asset_type="Etsy product photo",
                    source_path="https://example.test/duck-2.jpg",
                    preview_path="https://example.test/duck-2.jpg",
                    readiness_state="remote Etsy reference",
                    review_state="synced",
                    default_reference=0,
                )
            )
            return duck.id, goose.id

    def _secure_client(self, db_path: Path):
        with patch.dict(
            os.environ,
            {"MARKETING_OS_SECRET": "test-secret-that-is-long-and-random-enough"},
            clear=False,
        ):
            app = create_secure_app(str(db_path), bootstrap_data=False)
        app.config.update(TESTING=True)
        self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
        factory = app.config["SESSION_FACTORY"]
        with factory.begin() as session:
            service = PrincipalRecord(
                principal_type="service",
                username="agent-products-find",
                roles_json='["service"]',
                password_hash="",
            )
            session.add(service)
            session.flush()
            read_token, _ = create_service_credential(session, service, scopes={"read"})
        return app.test_client(), factory, read_token

    def test_products_ui_filters_by_q_and_tag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "products-ui.sqlite"
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            duck_id, goose_id = self._seed_catalog(app.config["SESSION_FACTORY"])
            client = app.test_client()

            page = client.get("/products")
            self.assertEqual(200, page.status_code)
            self.assertIn(b'aria-label="Product tag"', page.data)
            self.assertIn(b'aria-label="Search name"', page.data)
            self.assertIn(b"Find Duck", page.data)
            self.assertIn(b"Other Goose", page.data)

            by_q = client.get("/products?q=Duck")
            self.assertEqual(200, by_q.status_code)
            self.assertIn(b"Find Duck", by_q.data)
            self.assertNotIn(b"Other Goose", by_q.data)
            self.assertIn(b"Filtered", by_q.data)

            by_tag = client.get("/products?tag=gift")
            self.assertEqual(200, by_tag.status_code)
            self.assertIn(b"Find Duck", by_tag.data)
            self.assertNotIn(b"Other Goose", by_tag.data)
            self.assertIn(b"tag gift", by_tag.data)

            combined = client.get("/products?q=Goose&tag=nursery")
            self.assertEqual(200, combined.status_code)
            self.assertIn(b"Other Goose", combined.data)
            self.assertNotIn(b"Find Duck", combined.data)

            self.assertIsNotNone(duck_id)
            self.assertIsNotNone(goose_id)

    def test_api_products_auth_deny_and_success_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "products-api.sqlite"
            client, factory, read_token = self._secure_client(db_path)
            duck_id, _goose_id = self._seed_catalog(factory)

            anonymous = client.get("/api/products", base_url="https://localhost")
            self.assertEqual(401, anonymous.status_code)

            ok = client.get(
                "/api/products",
                headers={"Authorization": f"Bearer {read_token}"},
                base_url="https://localhost",
            )
            self.assertEqual(200, ok.status_code)
            payload = ok.get_json()
            self.assertIn("products", payload)
            self.assertIn("filters", payload)
            self.assertEqual(3, payload["count"])
            first = next(item for item in payload["products"] if item["id"] == duck_id)
            for key in ("id", "name", "sync_status", "default_ref_count", "tags"):
                self.assertIn(key, first)
            self.assertEqual("Find Duck", first["name"])
            self.assertEqual("imported", first["sync_status"])
            self.assertEqual(1, first["default_ref_count"])
            self.assertEqual(["gift", "holiday"], first["tags"])

            by_q = client.get(
                "/api/products?q=Duck",
                headers={"Authorization": f"Bearer {read_token}"},
                base_url="https://localhost",
            )
            names = {item["name"] for item in by_q.get_json()["products"]}
            self.assertEqual({"Find Duck"}, names)

            by_tag = client.get(
                "/api/products?tag=nursery",
                headers={"Authorization": f"Bearer {read_token}"},
                base_url="https://localhost",
            )
            tag_payload = by_tag.get_json()
            self.assertEqual(1, tag_payload["count"])
            self.assertEqual("Other Goose", tag_payload["products"][0]["name"])
            self.assertEqual("nursery", tag_payload["filters"]["tag"])

            paged = client.get(
                "/api/products?page=1",
                headers={"Authorization": f"Bearer {read_token}"},
                base_url="https://localhost",
            )
            page_payload = paged.get_json()
            self.assertIn("pagination", page_payload)
            self.assertEqual(1, page_payload["pagination"]["page"])
            self.assertEqual(3, page_payload["pagination"]["total"])


if __name__ == "__main__":
    unittest.main()
