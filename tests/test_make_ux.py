from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import select

from marketing_os.db import session_scope
from marketing_os.db_models import AssetRecord, CreativeGenerationJobRecord, ProductRecord
from marketing_os.services.art_studio import (
    SOCIAL_IMAGE_ASSET_TYPE,
    enqueue_social_image_generation,
    needs_review_social_groups,
    social_image_job_progress_phase,
    summarize_social_image_job_progress,
)
from marketing_os.web_app import create_app

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x00\x03\x00\x01\x00\x05\xfe\xd4\xef\x00\x00\x00\x00IEND\xaeB`\x82"
)


class MakeUxProgressHelpersTests(unittest.TestCase):
    def test_progress_phase_mapping(self) -> None:
        self.assertEqual(social_image_job_progress_phase(SimpleNamespace(provider_status="queued", candidate_asset_id=None)), "queued")
        self.assertEqual(
            social_image_job_progress_phase(SimpleNamespace(provider_status="generating", candidate_asset_id=None)),
            "running",
        )
        self.assertEqual(
            social_image_job_progress_phase(SimpleNamespace(provider_status="generated", candidate_asset_id=9)),
            "done",
        )
        self.assertEqual(
            social_image_job_progress_phase(SimpleNamespace(provider_status="queued", candidate_asset_id=9)),
            "done",
        )
        self.assertEqual(
            social_image_job_progress_phase(SimpleNamespace(provider_status="canceled", candidate_asset_id=None)),
            "failed",
        )

    def test_summarize_multi_platform_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "make-ux.sqlite"
            source_path = Path(tmp) / "source.png"
            source_path.write_bytes(TINY_PNG)
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = ProductRecord(name="Make UX Duck")
                session.add(product)
                session.flush()
                source = AssetRecord(
                    product_id=product.id,
                    name="Make source",
                    asset_type="source photo",
                    source_path=source_path.as_posix(),
                    preview_path=source_path.as_posix(),
                    readiness_state="ready",
                    review_state="approved",
                    default_reference=1,
                )
                session.add(source)
                session.flush()
                queued = enqueue_social_image_generation(session, product.id, source.id, platform="ig_feed")
                running = enqueue_social_image_generation(
                    session, product.id, source.id, platform="stories", option_number=2
                )
                running.provider_status = "generating"
                done = enqueue_social_image_generation(
                    session, product.id, source.id, platform="pinterest", option_number=3
                )
                candidate = AssetRecord(
                    product_id=product.id,
                    name="Pin candidate",
                    asset_type=SOCIAL_IMAGE_ASSET_TYPE,
                    source_path=(Path(tmp) / "pin.png").as_posix(),
                    preview_path=(Path(tmp) / "pin.png").as_posix(),
                    readiness_state="needs human review",
                    review_state="needs review",
                )
                session.add(candidate)
                session.flush()
                done.provider_status = "generated"
                done.candidate_asset_id = candidate.id
                failed = enqueue_social_image_generation(
                    session, product.id, source.id, platform="x", option_number=4
                )
                failed.provider_status = "canceled"
                session.flush()

                progress = summarize_social_image_job_progress([queued, running, done, failed])
                self.assertEqual(progress["total"], 4)
                self.assertEqual(progress["counts"]["queued"], 1)
                self.assertEqual(progress["counts"]["running"], 1)
                self.assertEqual(progress["counts"]["done"], 1)
                self.assertEqual(progress["counts"]["failed"], 1)
                self.assertTrue(progress["has_active"])
                self.assertTrue(progress["has_failed"])
                self.assertEqual(progress["ready_for_review_count"], 1)
                self.assertIn("IG Feed", progress["platforms"])
                self.assertIn("Stories", progress["platforms"])
                self.assertIn("Pinterest", progress["platforms"])
                self.assertIn("X", progress["platforms"])
                phases = [row["phase"] for row in progress["rows"]]
                self.assertEqual(phases, ["queued", "running", "done", "failed"])


class MakeUxNeedsReviewGroupsTests(unittest.TestCase):
    def test_groups_generated_socials_by_product_and_platform(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "make-review.sqlite"
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                duck = ProductRecord(name="Review Duck")
                goose = ProductRecord(name="Review Goose")
                session.add_all([duck, goose])
                session.flush()
                source = AssetRecord(
                    product_id=duck.id,
                    name="Review source",
                    asset_type="source photo",
                    source_path="https://example.test/source.jpg",
                    preview_path="https://example.test/source.jpg",
                    readiness_state="ready",
                    review_state="approved",
                )
                duck_ig = AssetRecord(
                    product_id=duck.id,
                    name="Duck IG",
                    asset_type=SOCIAL_IMAGE_ASSET_TYPE,
                    source_path=str(Path(tmp) / "duck-ig.png"),
                    preview_path=str(Path(tmp) / "duck-ig.png"),
                    readiness_state="needs human review",
                    review_state="needs review",
                )
                duck_stories = AssetRecord(
                    product_id=duck.id,
                    name="Duck Stories",
                    asset_type=SOCIAL_IMAGE_ASSET_TYPE,
                    source_path=str(Path(tmp) / "duck-stories.png"),
                    preview_path=str(Path(tmp) / "duck-stories.png"),
                    readiness_state="needs human review",
                    review_state="needs review",
                )
                goose_pin = AssetRecord(
                    product_id=goose.id,
                    name="Goose Pin",
                    asset_type=SOCIAL_IMAGE_ASSET_TYPE,
                    source_path=str(Path(tmp) / "goose-pin.png"),
                    preview_path=str(Path(tmp) / "goose-pin.png"),
                    readiness_state="needs human review",
                    review_state="needs review",
                )
                session.add_all([source, duck_ig, duck_stories, goose_pin])
                session.flush()
                session.add_all(
                    [
                        CreativeGenerationJobRecord(
                            source_asset_id=source.id,
                            candidate_asset_id=duck_ig.id,
                            target_format="art_studio_social_image",
                            provider="magnific_api",
                            prompt="ig",
                            requested_dimensions="1:1 IG Feed",
                            provider_status="generated",
                            response_metadata_json=json.dumps(
                                {"platform": "ig_feed", "aspect_ratio": "1:1", "platform_label": "IG Feed"}
                            ),
                        ),
                        CreativeGenerationJobRecord(
                            source_asset_id=source.id,
                            candidate_asset_id=duck_stories.id,
                            target_format="art_studio_social_image",
                            provider="magnific_api",
                            prompt="stories",
                            requested_dimensions="9:16 Stories",
                            provider_status="generated",
                            response_metadata_json=json.dumps(
                                {"platform": "stories", "aspect_ratio": "9:16", "platform_label": "Stories"}
                            ),
                        ),
                        CreativeGenerationJobRecord(
                            source_asset_id=source.id,
                            candidate_asset_id=goose_pin.id,
                            target_format="art_studio_social_image",
                            provider="magnific_api",
                            prompt="pin",
                            requested_dimensions="2:3 Pinterest",
                            provider_status="generated",
                            response_metadata_json=json.dumps(
                                {"platform": "pinterest", "aspect_ratio": "2:3", "platform_label": "Pinterest"}
                            ),
                        ),
                    ]
                )
                session.flush()

                groups = needs_review_social_groups(session)
                self.assertEqual(len(groups), 2)
                by_name = {group["product_name"]: group for group in groups}
                self.assertEqual(by_name["Review Duck"]["count"], 2)
                self.assertEqual(set(by_name["Review Duck"]["platforms"]), {"IG Feed", "Stories"})
                self.assertEqual(set(by_name["Review Duck"]["aspect_ratios"]), {"1:1", "9:16"})
                self.assertEqual(by_name["Review Goose"]["count"], 1)
                self.assertEqual(by_name["Review Goose"]["platforms"], ["Pinterest"])


class MakeUxWebSurfaceTests(unittest.TestCase):
    def test_products_queue_shows_progress_strip_and_gallery_shows_review_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "make-web.sqlite"
            source_path = tmp_path / "source.png"
            source_path.write_bytes(TINY_PNG)
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = ProductRecord(name="Progress Duck")
                session.add(product)
                session.flush()
                source = AssetRecord(
                    product_id=product.id,
                    name="Progress source",
                    asset_type="source photo",
                    source_path=source_path.as_posix(),
                    preview_path=source_path.as_posix(),
                    readiness_state="ready",
                    review_state="approved",
                    default_reference=1,
                )
                session.add(source)
                session.flush()
                product_id = product.id
                source_id = source.id

            client = app.test_client()
            queued = client.post(
                f"/products/{product_id}/social-images/queue",
                data={"option_number": "1", "platform": ["ig_feed", "stories"]},
                follow_redirects=True,
            )
            self.assertEqual(queued.status_code, 200)
            self.assertIn(b"across IG Feed, Stories", queued.data)
            self.assertIn(b"make-progress-strip", queued.data)
            self.assertIn(b"queued", queued.data)
            self.assertIn(b"Platforms:", queued.data)
            self.assertIn(b"IG Feed", queued.data)
            self.assertIn(b"Stories", queued.data)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                jobs = list(session.scalars(select(CreativeGenerationJobRecord).order_by(CreativeGenerationJobRecord.id)))
                self.assertEqual(len(jobs), 2)
                candidate = AssetRecord(
                    product_id=product_id,
                    name="Ready social",
                    asset_type=SOCIAL_IMAGE_ASSET_TYPE,
                    source_path=(tmp_path / "ready.png").as_posix(),
                    preview_path=(tmp_path / "ready.png").as_posix(),
                    readiness_state="needs human review",
                    review_state="needs review",
                )
                session.add(candidate)
                session.flush()
                jobs[0].provider_status = "generated"
                jobs[0].candidate_asset_id = candidate.id
                jobs[0].source_asset_id = source_id
                session.flush()

            gallery = client.get("/creative-assets")
            self.assertEqual(gallery.status_code, 200)
            self.assertIn(b"Make loop", gallery.data)
            self.assertIn(b"await approve/reject", gallery.data)
            self.assertIn(b"Progress Duck", gallery.data)
            self.assertIn(b"Show all needs-review socials", gallery.data)


if __name__ == "__main__":
    unittest.main()
