from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import select

from marketing_os.db import session_scope
from marketing_os.db_models import AssetRecord, CreativeGenerationJobRecord, ProductRecord
from marketing_os.web_app import create_app


class AssetFindabilityTests(unittest.TestCase):
    def test_api_assets_filters_by_product_type_review_platform_aspect_and_q(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "findability.sqlite"
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                duck = ProductRecord(name="Find Duck")
                goose = ProductRecord(name="Other Goose")
                session.add_all([duck, goose])
                session.flush()

                source = AssetRecord(
                    product_id=duck.id,
                    name="Find Duck source",
                    asset_type="source photo",
                    source_path="https://example.test/source.jpg",
                    preview_path="https://example.test/source.jpg",
                    readiness_state="remote reference",
                    review_state="approved",
                    canonical_url="https://example.test/source.jpg",
                    width=1000,
                    height=1000,
                )
                social = AssetRecord(
                    product_id=duck.id,
                    name="Find Duck IG portrait",
                    asset_type="generated social image",
                    source_path=str(Path(tmp) / "social.jpg"),
                    preview_path=str(Path(tmp) / "social.jpg"),
                    readiness_state="needs human review",
                    review_state="needs review",
                    platform_suitability_json=json.dumps(["instagram", "facebook"]),
                    width=1080,
                    height=1350,
                )
                other = AssetRecord(
                    product_id=goose.id,
                    name="Goose listing",
                    asset_type="Etsy product photo",
                    source_path="https://example.test/goose.jpg",
                    preview_path="https://example.test/goose.jpg",
                    readiness_state="remote Etsy reference",
                    review_state="synced",
                )
                session.add_all([source, social, other])
                session.flush()
                Path(tmp, "social.jpg").write_bytes(b"fake-image")
                social.file_exists = 1
                session.add(
                    CreativeGenerationJobRecord(
                        source_asset_id=source.id,
                        candidate_asset_id=social.id,
                        target_format="art_studio_social_image",
                        provider="magnific_api",
                        prompt="test",
                        requested_dimensions="4:5 IG Portrait",
                        provider_status="generated",
                        response_metadata_json=json.dumps(
                            {
                                "platform": "ig_portrait",
                                "aspect_ratio": "4:5",
                                "product_id": duck.id,
                            }
                        ),
                        review_state="needs_review",
                    )
                )
                duck_id = duck.id
                social_id = social.id
                source_id = source.id

            client = app.test_client()

            all_assets = client.get("/api/assets")
            self.assertEqual(all_assets.status_code, 200)
            payload = all_assets.get_json()
            self.assertEqual(payload["count"], 3)
            self.assertIn("filters", payload)
            first = payload["assets"][0]
            for key in (
                "id",
                "product_id",
                "name",
                "asset_type",
                "review_state",
                "source_path",
                "canonical_url",
                "file_exists",
                "platform",
                "aspect_ratio",
            ):
                self.assertIn(key, first)

            by_product = client.get(f"/api/assets?product_id={duck_id}")
            self.assertEqual(by_product.status_code, 200)
            names = {item["name"] for item in by_product.get_json()["assets"]}
            self.assertEqual(names, {"Find Duck source", "Find Duck IG portrait"})

            thin = client.get(f"/api/products/{duck_id}/assets")
            self.assertEqual(thin.status_code, 200)
            thin_payload = thin.get_json()
            self.assertEqual(thin_payload["product_id"], duck_id)
            self.assertEqual(thin_payload["count"], 2)

            by_type = client.get("/api/assets?asset_type=generated%20social%20image")
            self.assertEqual(by_type.get_json()["count"], 1)
            self.assertEqual(by_type.get_json()["assets"][0]["id"], social_id)

            by_review = client.get("/api/assets?review_state=approved")
            self.assertEqual(by_review.get_json()["count"], 1)
            self.assertEqual(by_review.get_json()["assets"][0]["id"], source_id)

            by_platform = client.get("/api/assets?platform=ig_portrait")
            platform_payload = by_platform.get_json()
            self.assertEqual(platform_payload["count"], 1)
            self.assertEqual(platform_payload["assets"][0]["id"], social_id)
            self.assertEqual(platform_payload["assets"][0]["platform"], "ig_portrait")
            self.assertEqual(platform_payload["assets"][0]["aspect_ratio"], "4:5")

            by_aspect = client.get("/api/assets?aspect_ratio=4:5")
            self.assertEqual(by_aspect.get_json()["count"], 1)
            self.assertEqual(by_aspect.get_json()["assets"][0]["id"], social_id)

            by_q = client.get("/api/assets?q=portrait")
            self.assertEqual(by_q.get_json()["count"], 1)
            self.assertEqual(by_q.get_json()["assets"][0]["id"], social_id)

            missing_product = client.get("/api/products/999999/assets")
            self.assertEqual(missing_product.status_code, 404)

    def test_gallery_ui_exposes_findability_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "gallery-filters.sqlite"
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = ProductRecord(name="Gallery Filter Duck")
                session.add(product)
                session.flush()
                session.add(
                    AssetRecord(
                        product_id=product.id,
                        name="Needs Review Duck",
                        asset_type="generated social image",
                        source_path="https://example.test/needs.jpg",
                        preview_path="https://example.test/needs.jpg",
                        readiness_state="needs human review",
                        review_state="needs review",
                    )
                )
                product_id = product.id

            client = app.test_client()
            gallery = client.get("/assets")
            self.assertEqual(gallery.status_code, 200)
            self.assertIn(b'aria-label="Product"', gallery.data)
            self.assertIn(b'aria-label="Asset type"', gallery.data)
            self.assertIn(b'aria-label="Review state"', gallery.data)
            self.assertIn(b'aria-label="Platform"', gallery.data)
            self.assertIn(b'aria-label="Aspect ratio"', gallery.data)
            self.assertIn(b'aria-label="Search name"', gallery.data)
            self.assertIn(b"Needs Review Duck", gallery.data)

            filtered = client.get(f"/assets?product_id={product_id}&review_state=needs%20review&q=Needs")
            self.assertEqual(filtered.status_code, 200)
            self.assertIn(b"Needs Review Duck", filtered.data)
            self.assertIn(b"Filtered", filtered.data)
            self.assertIn(b"needs review", filtered.data)


if __name__ == "__main__":
    unittest.main()
