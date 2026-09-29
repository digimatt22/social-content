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
from marketing_os.secure_app import create_secure_app
from marketing_os.services.auth import create_service_credential
from marketing_os.web_app import create_app

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x00\x03\x00\x01\x00\x05\xfe\xd4\xef\x00\x00\x00\x00IEND\xaeB`\x82"
)


class AgentMakeLoopApiTests(unittest.TestCase):
    def _seed_product_with_default_ref(self, factory, root: Path) -> tuple[int, int]:
        source_path = root / "source.png"
        source_path.write_bytes(TINY_PNG)
        with session_scope(factory) as session:
            product = ProductRecord(name="Agent Loop Duck")
            session.add(product)
            session.flush()
            source = AssetRecord(
                product_id=product.id,
                name="Agent source",
                asset_type="source photo",
                source_path=source_path.as_posix(),
                preview_path=source_path.as_posix(),
                readiness_state="ready to use",
                review_state="approved",
                default_reference=1,
                file_exists=1,
            )
            session.add(source)
            session.flush()
            return product.id, source.id

    def _secure_client(self, db_path: Path) -> tuple:
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
                username="agent-make-loop",
                roles_json='["service"]',
                password_hash="",
            )
            session.add(service)
            session.flush()
            read_token, _ = create_service_credential(session, service, scopes={"read"})
            write_token, _ = create_service_credential(session, service, scopes={"read", "write"})
        return app.test_client(), factory, read_token, write_token

    def test_queue_and_review_require_write_bearer_and_succeed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "agent-make.sqlite"
            client, factory, read_token, write_token = self._secure_client(db_path)
            product_id, source_id = self._seed_product_with_default_ref(factory, root)

            queue_path = "/api/art-studio/social-images/queue"
            body = {
                "product_id": product_id,
                "platforms": ["ig_feed", "stories"],
                "option_count": 2,
            }

            anonymous = client.post(queue_path, json=body, base_url="https://localhost")
            self.assertEqual(401, anonymous.status_code)

            read_denied = client.post(
                queue_path,
                json=body,
                headers={"Authorization": f"Bearer {read_token}"},
                base_url="https://localhost",
            )
            self.assertEqual(403, read_denied.status_code)

            queued = client.post(
                queue_path,
                json=body,
                headers={"Authorization": f"Bearer {write_token}"},
                base_url="https://localhost",
            )
            self.assertEqual(201, queued.status_code)
            payload = queued.get_json()
            self.assertEqual(product_id, payload["product_id"])
            self.assertEqual(4, payload["count"])
            self.assertEqual(4, len(payload["jobs"]))
            platforms = {(job["platform"], job["aspect_ratio"], job["status"]) for job in payload["jobs"]}
            self.assertEqual(
                {
                    ("ig_feed", "1:1", "queued"),
                    ("stories", "9:16", "queued"),
                },
                {(p, a, s) for p, a, s in platforms},
            )
            for job in payload["jobs"]:
                self.assertEqual(source_id, job["source_asset_id"])
                self.assertIn(job["option_number"], {1, 2})
                self.assertIn("id", job)

            with session_scope(factory) as session:
                jobs = list(session.scalars(select(CreativeGenerationJobRecord)))
                self.assertEqual(4, len(jobs))
                candidate = AssetRecord(
                    product_id=product_id,
                    name="Needs review social",
                    asset_type="generated social image",
                    source_path=(root / "out.png").as_posix(),
                    preview_path=(root / "out.png").as_posix(),
                    readiness_state="needs human review",
                    review_state="needs review",
                    file_exists=1,
                )
                (root / "out.png").write_bytes(TINY_PNG)
                session.add(candidate)
                session.flush()
                candidate_id = candidate.id

            review_path = f"/api/assets/{candidate_id}/review"
            review_body = {"review_state": "approved", "approval_notes": "Looks accurate"}

            self.assertEqual(
                401,
                client.post(review_path, json=review_body, base_url="https://localhost").status_code,
            )
            self.assertEqual(
                403,
                client.post(
                    review_path,
                    json=review_body,
                    headers={"Authorization": f"Bearer {read_token}"},
                    base_url="https://localhost",
                ).status_code,
            )

            reviewed = client.post(
                review_path,
                json=review_body,
                headers={"Authorization": f"Bearer {write_token}"},
                base_url="https://localhost",
            )
            self.assertEqual(200, reviewed.status_code)
            asset_payload = reviewed.get_json()["asset"]
            self.assertEqual(candidate_id, asset_payload["id"])
            self.assertEqual("approved", asset_payload["review_state"])
            self.assertEqual("ready to use", asset_payload["readiness_state"])

            with session_scope(factory) as session:
                asset = session.get(AssetRecord, candidate_id)
                self.assertEqual("approved", asset.review_state)
                self.assertEqual("Looks accurate", asset.approval_notes)

    def test_html_form_queue_and_review_still_work_without_bearer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "form-make.sqlite"
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            factory = app.config["SESSION_FACTORY"]
            product_id, source_id = self._seed_product_with_default_ref(factory, root)
            client = app.test_client()

            queued = client.post(
                f"/products/{product_id}/social-images/queue",
                data={"option_number": "1", "platform": ["ig_feed", "stories"]},
                follow_redirects=False,
            )
            self.assertEqual(302, queued.status_code)
            with session_scope(factory) as session:
                jobs = list(session.scalars(select(CreativeGenerationJobRecord)))
                self.assertEqual(2, len(jobs))
                metas = [json.loads(job.response_metadata_json) for job in jobs]
                self.assertEqual({"ig_feed", "stories"}, {meta["platform"] for meta in metas})
                self.assertTrue(all(meta["option_number"] == 1 for meta in metas))
                self.assertTrue(all(job.source_asset_id == source_id for job in jobs))

                candidate = AssetRecord(
                    product_id=product_id,
                    name="Form review social",
                    asset_type="generated social image",
                    source_path=(root / "form-out.png").as_posix(),
                    preview_path=(root / "form-out.png").as_posix(),
                    readiness_state="needs human review",
                    review_state="needs review",
                    file_exists=1,
                )
                (root / "form-out.png").write_bytes(TINY_PNG)
                session.add(candidate)
                session.flush()
                candidate_id = candidate.id

            reviewed = client.post(
                f"/assets/{candidate_id}/review",
                data={"review_state": "rejected", "approval_notes": "Wrong color"},
                follow_redirects=False,
            )
            self.assertEqual(302, reviewed.status_code)
            with session_scope(factory) as session:
                asset = session.get(AssetRecord, candidate_id)
                self.assertEqual("rejected", asset.review_state)
                self.assertEqual("Wrong color", asset.approval_notes)
                self.assertEqual("do not use", asset.readiness_state)

    def test_queue_rejects_missing_default_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "no-refs.sqlite"
            client, factory, _read_token, write_token = self._secure_client(db_path)
            with session_scope(factory) as session:
                product = ProductRecord(name="No Refs Duck")
                session.add(product)
                session.flush()
                product_id = product.id
            response = client.post(
                "/api/art-studio/social-images/queue",
                json={"product_id": product_id, "platforms": ["ig_feed"], "option_count": 1},
                headers={"Authorization": f"Bearer {write_token}"},
                base_url="https://localhost",
            )
            self.assertEqual(400, response.status_code)
            self.assertIn("default reference", response.get_json()["error"].lower())


if __name__ == "__main__":
    unittest.main()
