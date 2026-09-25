from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from marketing_os.db import session_scope
from marketing_os.db_models import AssetRecord, ProductRecord
from marketing_os.secure_app import create_secure_app
from marketing_os.services.auth import create_principal

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x00\x03\x00\x01\x00\x05\xfe\xd4\xef\x00\x00\x00\x00IEND\xaeB`\x82"
)


class ProductsDefaultReferenceCsrfTests(unittest.TestCase):
    def test_toggle_default_reference_api_requires_csrf_and_page_wires_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "products-csrf.sqlite"
            source_path = root / "source.png"
            source_path.write_bytes(TINY_PNG)
            with patch.dict(
                os.environ,
                {"MARKETING_OS_SECRET": "test-secret-that-is-long-and-random-enough"},
                clear=False,
            ):
                app = create_secure_app(str(db_path), bootstrap_data=False)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            app.config.update(TESTING=True)
            factory = app.config["SESSION_FACTORY"]
            with factory.begin() as session:
                create_principal(
                    session,
                    username="operator",
                    password="correct horse battery staple",
                    roles={"operator", "viewer"},
                )
                product = ProductRecord(name="CSRF Duck")
                session.add(product)
                session.flush()
                asset = AssetRecord(
                    product_id=product.id,
                    name="CSRF source",
                    asset_type="source photo",
                    source_path=source_path.as_posix(),
                    preview_path=source_path.as_posix(),
                    readiness_state="ready",
                    review_state="approved",
                    default_reference=0,
                )
                session.add(asset)
                session.flush()
                product_id = product.id
                asset_id = asset.id

            client = app.test_client()
            client.get("/auth/login", base_url="https://localhost")
            login_csrf = client.get_cookie("marketing_os_login_csrf").value
            login = client.post(
                "/auth/login",
                data={
                    "username": "operator",
                    "password": "correct horse battery staple",
                    "_login_csrf": login_csrf,
                },
                base_url="https://localhost",
            )
            self.assertEqual(302, login.status_code)

            products_page = client.get("/products", base_url="https://localhost")
            self.assertEqual(200, products_page.status_code)
            body = products_page.get_data(as_text=True)
            self.assertIn('name="_csrf_token"', body)
            self.assertIn('data-reference-form', body)
            self.assertIn('"X-CSRF-Token": csrfToken(form)', body)
            self.assertIn("function csrfToken(form)", body)

            denied = client.post(
                f"/api/products/{product_id}/default-reference-assets",
                json={"asset_ids": [asset_id]},
                base_url="https://localhost",
            )
            self.assertEqual(403, denied.status_code)
            self.assertEqual({"error": "csrf_validation_failed"}, denied.get_json())

            csrf = client.get_cookie("marketing_os_csrf").value
            allowed = client.post(
                f"/api/products/{product_id}/default-reference-assets",
                json={"asset_ids": [asset_id]},
                headers={"X-CSRF-Token": csrf},
                base_url="https://localhost",
            )
            self.assertEqual(200, allowed.status_code)
            self.assertEqual([asset_id], allowed.get_json()["asset_ids"])

            with session_scope(factory) as session:
                saved = session.get(AssetRecord, asset_id)
                self.assertEqual(1, saved.default_reference)


if __name__ == "__main__":
    unittest.main()
