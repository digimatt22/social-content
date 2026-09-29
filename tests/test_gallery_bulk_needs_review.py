from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select

from marketing_os.db import session_scope
from marketing_os.db_models import AssetRecord, CreativeGenerationJobRecord, PrincipalRecord, ProductRecord
from marketing_os.phase4 import review_assets
from marketing_os.secure_app import create_secure_app
from marketing_os.services.art_studio import SOCIAL_IMAGE_ASSET_TYPE
from marketing_os.services.auth import create_service_credential
from marketing_os.web_app import create_app

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x00\x03\x00\x01\x00\x05\xfe\xd4\xef\x00\x00\x00\x00IEND\xaeB`\x82"
)


class ReviewAssetsHelperTests(unittest.TestCase):
    def test_review_assets_applies_same_state_and_dedupes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "bulk-helper.sqlite"
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            factory = app.config["SESSION_FACTORY"]

            paths = []
            with session_scope(factory) as session:
                product = ProductRecord(name="Bulk Helper Duck")
                session.add(product)
                session.flush()
                ids = []
                for index in range(2):
                    path = root / f"out-{index}.png"
                    path.write_bytes(TINY_PNG)
                    paths.append(path)
                    asset = AssetRecord(
                        product_id=product.id,
                        name=f"Social {index}",
                        asset_type=SOCIAL_IMAGE_ASSET_TYPE,
                        source_path=path.as_posix(),
                        preview_path=path.as_posix(),
                        readiness_state="needs human review",
                        review_state="needs review",
                        file_exists=1,
                    )
                    session.add(asset)
                    session.flush()
                    ids.append(asset.id)
                reviewed = review_assets(session, [ids[0], ids[0], ids[1]], "approved", "bulk ok")
                self.assertEqual([ids[0], ids[1]], [asset.id for asset in reviewed])
                self.assertTrue(all(asset.review_state == "approved" for asset in reviewed))
                self.assertTrue(all(asset.approval_notes == "bulk ok" for asset in reviewed))

            with self.assertRaises(ValueError):
                with session_scope(factory) as session:
                    review_assets(session, [], "approved")


class GalleryBulkNeedsReviewWebTests(unittest.TestCase):
    def _seed_needs_review_group(self, factory, root: Path) -> tuple[int, list[int]]:
        with session_scope(factory) as session:
            product = ProductRecord(name="Bulk Review Duck")
            session.add(product)
            session.flush()
            asset_ids: list[int] = []
            for index, platform in enumerate(("ig_feed", "stories")):
                path = root / f"social-{index}.png"
                path.write_bytes(TINY_PNG)
                asset = AssetRecord(
                    product_id=product.id,
                    name=f"Needs {platform}",
                    asset_type=SOCIAL_IMAGE_ASSET_TYPE,
                    source_path=path.as_posix(),
                    preview_path=path.as_posix(),
                    readiness_state="needs human review",
                    review_state="needs review",
                    file_exists=1,
                )
                session.add(asset)
                session.flush()
                session.add(
                    CreativeGenerationJobRecord(
                        source_asset_id=asset.id,
                        candidate_asset_id=asset.id,
                        target_format="art_studio_social_image",
                        provider="magnific_api",
                        prompt=platform,
                        requested_dimensions="1:1" if platform == "ig_feed" else "9:16",
                        provider_status="generated",
                        response_metadata_json=json.dumps(
                            {
                                "platform": platform,
                                "aspect_ratio": "1:1" if platform == "ig_feed" else "9:16",
                                "platform_label": "IG Feed" if platform == "ig_feed" else "Stories",
                            }
                        ),
                    )
                )
                asset_ids.append(asset.id)
            session.flush()
            return product.id, asset_ids

    def test_gallery_strip_shows_bulk_controls_and_form_bulk_approves(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "bulk-web.sqlite"
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            factory = app.config["SESSION_FACTORY"]
            _product_id, asset_ids = self._seed_needs_review_group(factory, root)
            client = app.test_client()

            gallery = client.get("/assets")
            self.assertEqual(200, gallery.status_code)
            self.assertIn(b"Approve selected", gallery.data)
            self.assertIn(b"Reject selected", gallery.data)
            self.assertIn(b"Approve all", gallery.data)
            self.assertIn(b"Reject all", gallery.data)
            self.assertIn(b"make-review-bulk-form", gallery.data)
            self.assertIn(b'name="asset_id"', gallery.data)
            self.assertIn(b"/assets/review/bulk", gallery.data)

            empty = client.post(
                "/assets/review/bulk",
                data={"review_state": "approved", "return_to": "/assets"},
                follow_redirects=True,
            )
            self.assertEqual(200, empty.status_code)
            self.assertIn(b"Select at least one", empty.data)

            approved = client.post(
                "/assets/review/bulk",
                data={
                    "review_state": "approved",
                    "approval_notes": "group looks good",
                    "asset_id": [str(asset_ids[0]), str(asset_ids[1])],
                    "return_to": "/assets",
                },
                follow_redirects=True,
            )
            self.assertEqual(200, approved.status_code)
            self.assertIn(b"Bulk review saved for 2 assets", approved.data)

            with session_scope(factory) as session:
                states = {
                    asset.id: asset.review_state
                    for asset in session.scalars(select(AssetRecord).where(AssetRecord.id.in_(asset_ids)))
                }
                self.assertEqual({asset_ids[0]: "approved", asset_ids[1]: "approved"}, states)
                notes = {
                    asset.id: asset.approval_notes
                    for asset in session.scalars(select(AssetRecord).where(AssetRecord.id.in_(asset_ids)))
                }
                self.assertEqual("group looks good", notes[asset_ids[0]])

    def test_gallery_group_reject_all_form(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "bulk-reject.sqlite"
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            factory = app.config["SESSION_FACTORY"]
            _product_id, asset_ids = self._seed_needs_review_group(factory, root)
            client = app.test_client()

            rejected = client.post(
                "/assets/review/bulk",
                data={
                    "review_state": "rejected",
                    "asset_ids": f"{asset_ids[0]},{asset_ids[1]}",
                    "return_to": "/assets",
                },
                follow_redirects=True,
            )
            self.assertEqual(200, rejected.status_code)
            self.assertIn(b"Bulk review saved for 2 assets", rejected.data)
            with session_scope(factory) as session:
                for asset_id in asset_ids:
                    asset = session.get(AssetRecord, asset_id)
                    self.assertEqual("rejected", asset.review_state)
                    self.assertEqual("do not use", asset.readiness_state)


class GalleryBulkNeedsReviewApiTests(unittest.TestCase):
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
                username="agent-bulk-review",
                roles_json='["service"]',
                password_hash="",
            )
            session.add(service)
            session.flush()
            read_token, _ = create_service_credential(session, service, scopes={"read"})
            write_token, _ = create_service_credential(session, service, scopes={"read", "write"})
        return app.test_client(), factory, read_token, write_token

    def test_json_bulk_review_requires_write_and_updates_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "bulk-api.sqlite"
            client, factory, read_token, write_token = self._secure_client(db_path)

            with session_scope(factory) as session:
                product = ProductRecord(name="API Bulk Duck")
                session.add(product)
                session.flush()
                ids = []
                for index in range(2):
                    path = root / f"api-{index}.png"
                    path.write_bytes(TINY_PNG)
                    asset = AssetRecord(
                        product_id=product.id,
                        name=f"API social {index}",
                        asset_type=SOCIAL_IMAGE_ASSET_TYPE,
                        source_path=path.as_posix(),
                        preview_path=path.as_posix(),
                        readiness_state="needs human review",
                        review_state="needs review",
                        file_exists=1,
                    )
                    session.add(asset)
                    session.flush()
                    ids.append(asset.id)

            body = {"asset_ids": ids, "review_state": "approved", "approval_notes": "api bulk"}
            self.assertEqual(
                401,
                client.post("/api/assets/review", json=body, base_url="https://localhost").status_code,
            )
            self.assertEqual(
                403,
                client.post(
                    "/api/assets/review",
                    json=body,
                    headers={"Authorization": f"Bearer {read_token}"},
                    base_url="https://localhost",
                ).status_code,
            )

            reviewed = client.post(
                "/api/assets/review",
                json=body,
                headers={"Authorization": f"Bearer {write_token}"},
                base_url="https://localhost",
            )
            self.assertEqual(200, reviewed.status_code)
            payload = reviewed.get_json()
            self.assertEqual(2, payload["count"])
            self.assertEqual(2, len(payload["assets"]))
            self.assertEqual({"approved"}, {row["review_state"] for row in payload["assets"]})

            with session_scope(factory) as session:
                for asset_id in ids:
                    asset = session.get(AssetRecord, asset_id)
                    self.assertEqual("approved", asset.review_state)
                    self.assertEqual("api bulk", asset.approval_notes)

            bad = client.post(
                "/api/assets/review",
                json={"asset_ids": [], "review_state": "approved"},
                headers={"Authorization": f"Bearer {write_token}"},
                base_url="https://localhost",
            )
            self.assertEqual(400, bad.status_code)


if __name__ == "__main__":
    unittest.main()
