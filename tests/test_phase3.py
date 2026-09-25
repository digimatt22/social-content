from __future__ import annotations

import io
import json
import tempfile
import time
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import func, inspect, select

from marketing_os.db import create_db_engine, init_db, session_factory, session_scope
from marketing_os.db_models import (
    AssetRecord,
    BlogPostRecord,
    CreativeGenerationJobRecord,
    EtsyReviewRecord,
    GeneratedContentCandidateRecord,
    MetricRecord,
    PlanRecord,
    PlannedContentRecord,
    ProductExternalReference,
    ProductRecord,
    ProductSalesRecord,
    SyncMetadata,
    TaskRecord,
    TemplateRecord,
    utc_now,
)
from marketing_os.integrations import EtsyConfig
from marketing_os.jobs.content_automation import run as run_content_automation_job
from marketing_os.jobs.content_production import run as run_content_production_job
from marketing_os.jobs.import_etsy_sales_csv import run as run_import_etsy_sales_csv_job
from marketing_os.jobs.phase5_readiness import run as run_phase5_readiness_job
from marketing_os.jobs.register_art_studio_outputs import run as run_register_art_studio_outputs_job
from marketing_os.jobs.register_art_studio_video_workflow import run as run_register_art_studio_video_workflow_job
from marketing_os.jobs.register_generated_copy import run as run_register_generated_copy_job
from marketing_os.jobs.register_generated_images import run as run_register_generated_images_job
from marketing_os.jobs.weekly_social_planner import run as run_weekly_social_planner_job
from marketing_os.phase3 import (
    TASK_STATUSES,
    add_metric,
    ensure_default_plan,
    generate_and_persist_plan,
    json_list,
    link_generated_content_to_task,
    seed_database,
    update_task_status,
)
from marketing_os.phase4 import (
    asset_inventory,
    assign_asset_to_task,
    backup_sqlite_database,
    completed_tasks,
    complete_task_status,
    creative_asset_plans,
    data_health,
    export_operating_data,
    generate_creative_output_files_for_source,
    import_external_product_image,
    import_etsy_listing_csv,
    import_source_photo_to_inventory,
    metrics_due_tasks,
    posting_guides,
    prepare_creative_generation_run,
    register_creative_outputs_for_source,
    register_generated_asset_candidate,
    register_local_source_photo,
    review_asset,
    scan_local_asset_folder,
    set_asset_generation_visibility,
    task_asset_options,
    today_view,
    week_agenda,
)
from marketing_os.services.content_briefs import (
    build_content_brief,
    create_planned_content_item,
    create_task_from_planned_content,
    default_reference_asset_ids_for_products,
    localize_planned_content_reference_assets,
    planned_items_needing_production,
    produce_content_for_item,
    record_candidate_review,
    register_generated_copy_candidate,
    register_generated_image_option,
    register_uploaded_image_option,
)
from marketing_os.services.art_studio import (
    DEFAULT_VIDEO_NEGATIVE_PROMPT,
    approve_video_request_for_generation,
    art_studio_queue,
    art_studio_video_requests,
    create_video_request,
    enqueue_social_image_generation,
    enqueue_video_art_board_generation,
    enqueue_video_generation,
    enqueue_video_storyboard_generation,
    register_social_image_output,
    register_video_output,
    social_image_handoff,
    social_image_scene_direction,
    social_image_scene_variation,
    validate_video_motion_prompt,
)
from marketing_os.services.creative_generation import import_manual_generated_output, review_creative_generation_job
from marketing_os.services.etsy_import import sync_etsy_read_only
from marketing_os.services.insights import build_learning_summary, serialize_learning_summary
from marketing_os.services.skill_adapters import (
    copywriter_contract,
    image_option_from_contract,
    social_copy_workflow_contract,
    social_media_art_director_contracts,
)
from marketing_os.services.local_assets import scan_asset_root
from marketing_os.services.mattmademe_website_import import sync_mattmademe_website
from marketing_os.services.phase5_readiness import (
    build_phase5_approval_packet,
    build_phase5_readiness,
    render_phase5_creative_handoff_markdown,
    render_phase5_approval_packet_markdown,
    serialize_phase5_approval_packet,
    serialize_phase5_readiness,
    write_phase5_approval_packet,
    write_phase5_creative_handoff,
)
from marketing_os.web_app import create_app


def tiny_png_bytes(color: str = "#38bdf8") -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buffer, format="PNG")
    return buffer.getvalue()


class Phase3LocalWebConsoleTests(unittest.TestCase):
    def build_session(self):
        tmp = tempfile.TemporaryDirectory()
        db_path = Path(tmp.name) / "phase3.sqlite"
        engine = create_db_engine(db_path)
        self.addCleanup(engine.dispose)
        init_db(engine)
        factory = session_factory(engine)
        return tmp, factory

    def register_agent_copy(self, session, item, copy_text: str | None = None) -> GeneratedContentCandidateRecord:
        product_ids = json_list(item.product_ids_json)
        product_name = "this duck"
        if product_ids:
            try:
                product = session.get(ProductRecord, int(product_ids[0]))
                if product is not None:
                    product_name = product.name
            except (TypeError, ValueError):
                pass
        return register_generated_copy_candidate(
            session,
            item.id,
            copy_text
            or f"Who needs {product_name} in their flock?\n\nThis tiny 3D printed duck is ready for a shelf, desk, or gift box.\n\nWho would you give this one to?",
            social_strategy={"skill": "social-media-strategist", "social_angle": "community_prompt"},
            social_challenge={"skill": "social-media-copy-chief", "status": "ready_for_human_review"},
        )

    def test_web_app_does_not_seed_data_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "empty-start.sqlite"
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                self.assertEqual(session.scalar(select(func.count()).select_from(ProductRecord)), 0)
                self.assertEqual(session.scalar(select(func.count()).select_from(PlanRecord)), 0)
            self.assertEqual(app.config["ASSETS_ROOT"], Path("assets/products"))
            self.assertEqual(app.config["GENERATED_OUTPUT_ROOT"], Path("outputs/generated"))
            self.assertEqual(app.config["PLANNING_UPLOAD_ROOT"], Path("outputs/graphics/planning/uploads"))
            columns = {column["name"] for column in inspect(app.config["SESSION_FACTORY"].kw["bind"]).get_columns("products")}
            self.assertFalse({"status", "primary_audience", "launch_priority"} & columns)

    def test_database_initializes_and_seeds_business_templates_and_assets(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        with session_scope(factory) as session:
            seed_database(session)
            products = session.scalars(select(ProductRecord)).all()
            templates = session.scalars(select(TemplateRecord)).all()
            assets = session.scalars(select(AssetRecord)).all()

            self.assertGreaterEqual(len(products), 10)
            self.assertGreaterEqual(len(templates), 10)
            self.assertGreaterEqual(len(assets), 10)
            self.assertTrue(any(t.platform == "Instagram" and t.format == "reel" for t in templates))
            self.assertTrue(any(t.template_type == "graphic" for t in templates))

    def test_gallery_page_paginates_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "asset-pages.sqlite"
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = ProductRecord(name="Pagination Duck")
                session.add(product)
                session.flush()
                for index in range(50):
                    session.add(
                        AssetRecord(
                            product_id=product.id,
                            name=f"Paged Asset {index:03d}",
                            asset_type="source photo",
                            source_path=f"missing/paged-asset-{index:03d}.jpg",
                            readiness_state="needs review",
                        )
                    )

            client = app.test_client()
            first_page = client.get("/assets")
            second_page = client.get("/assets?page=2")

            self.assertEqual(first_page.status_code, 200)
            self.assertEqual(second_page.status_code, 200)
            self.assertIn(b"1-36 of 50 assets", first_page.data)
            self.assertIn(b"37-50 of 50 assets", second_page.data)
            self.assertIn(b"Paged Asset 000", first_page.data)
            self.assertNotIn(b"Paged Asset 036", first_page.data)
            self.assertIn(b"Paged Asset 036", second_page.data)

    def test_gallery_filters_assets_by_image_tag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "asset-tags.sqlite"
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                gift_product = ProductRecord(name="Gift Duck", use_cases_json=json.dumps(["gift buyer"]))
                display_product = ProductRecord(name="Display Duck", use_cases_json=json.dumps(["desk display"]))
                session.add_all([gift_product, display_product])
                session.flush()
                session.add_all(
                    [
                        AssetRecord(
                            product_id=gift_product.id,
                            name="Gift Duck image",
                            asset_type="Etsy product photo",
                            source_path="https://example.test/gift.jpg",
                            preview_path="https://example.test/gift-preview.jpg",
                            readiness_state="remote Etsy reference",
                            review_state="synced",
                        ),
                        AssetRecord(
                            product_id=display_product.id,
                            name="Display Duck image",
                            asset_type="generated post image",
                            source_path="https://example.test/display.jpg",
                            preview_path="https://example.test/display-preview.jpg",
                            readiness_state="remote Etsy reference",
                            review_state="synced",
                        ),
                    ]
                )

            client = app.test_client()
            gallery = client.get("/assets")
            self.assertEqual(gallery.status_code, 200)
            self.assertIn(b"Image tag", gallery.data)
            self.assertIn(b"etsy", gallery.data)
            self.assertIn(b"magnific", gallery.data)
            self.assertNotIn(b"Etsy product photo", gallery.data)
            self.assertNotIn(b"generated post image", gallery.data)
            self.assertIn(b"Gift Duck image", gallery.data)
            self.assertIn(b"Display Duck image", gallery.data)

            filtered = client.get("/assets?tag=etsy")
            self.assertEqual(filtered.status_code, 200)
            self.assertIn(b"Filtered to image tag: etsy", filtered.data)
            self.assertIn(b"Gift Duck image", filtered.data)
            self.assertNotIn(b"Display Duck image", filtered.data)

    def test_gallery_groups_duplicate_images_and_visibility_applies_everywhere(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "duplicate-gallery.sqlite"
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            shared_url = "https://images.example/shared-duck.jpg"

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                first_product = ProductRecord(name="First Shared Duck")
                second_product = ProductRecord(name="Second Shared Duck")
                session.add_all([first_product, second_product])
                session.flush()
                first_asset = AssetRecord(
                    product_id=first_product.id,
                    name="Shared Duck Etsy image A",
                    asset_type="Etsy product photo",
                    source_path=shared_url,
                    preview_path=shared_url,
                    canonical_url=shared_url,
                    readiness_state="remote Etsy reference",
                    external_source="etsy",
                    review_state="synced",
                    file_exists=0,
                )
                second_asset = AssetRecord(
                    product_id=second_product.id,
                    name="Shared Duck Etsy image B",
                    asset_type="Etsy product photo",
                    source_path=shared_url,
                    preview_path=shared_url,
                    canonical_url=shared_url,
                    readiness_state="remote Etsy reference",
                    external_source="etsy",
                    review_state="synced",
                    file_exists=0,
                )
                session.add_all([first_asset, second_asset])
                session.flush()
                first_asset_id = first_asset.id
                second_asset_id = second_asset.id

            client = app.test_client()
            gallery = client.get("/assets")
            self.assertEqual(gallery.status_code, 200)
            self.assertIn(b"1-1 of 1 asset", gallery.data)
            self.assertIn(b"Shared Duck Etsy image A", gallery.data)
            self.assertNotIn(b"Shared Duck Etsy image B", gallery.data)
            self.assertIn(b"Shared across 2 product records", gallery.data)
            self.assertIn(b"First Shared Duck, Second Shared Duck", gallery.data)

            products = client.get("/products")
            self.assertEqual(products.status_code, 200)
            self.assertIn(b"Shared Duck Etsy image A", products.data)
            self.assertIn(b"Shared Duck Etsy image B", products.data)

            response = client.post(
                f"/assets/{first_asset_id}/visibility",
                data={"hidden": "1", "return_to": "/assets?show_hidden=1"},
                follow_redirects=True,
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Image hidden from automation.", response.data)
            self.assertIn(b"Restore image for automation", response.data)
            self.assertNotIn(b"Automation visibility", response.data)
            with session_scope(app.config["SESSION_FACTORY"]) as session:
                first = session.get(AssetRecord, first_asset_id)
                second = session.get(AssetRecord, second_asset_id)
                self.assertEqual(first.hidden_from_generation, 1)
                self.assertEqual(second.hidden_from_generation, 1)

            gallery_without_hidden = client.get("/assets")
            self.assertNotIn(b"Shared Duck Etsy image A", gallery_without_hidden.data)
            products_without_hidden = client.get("/products")
            self.assertNotIn(b"Shared Duck Etsy image A", products_without_hidden.data)
            self.assertNotIn(b"Shared Duck Etsy image B", products_without_hidden.data)

    def test_products_page_hides_remote_image_when_local_download_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "product-local-remote-duplicate.sqlite"
            local_path = tmp_path / "downloaded-duck.jpg"
            local_path.write_bytes(b"downloaded remote duck image")
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            shared_url = "https://images.example/downloaded-duck.jpg"

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = ProductRecord(name="Downloaded Duck")
                session.add(product)
                session.flush()
                remote_asset = AssetRecord(
                    product_id=product.id,
                    name="Remote Downloaded Duck",
                    asset_type="Etsy product photo",
                    source_path=shared_url,
                    preview_path=shared_url,
                    canonical_url=shared_url,
                    readiness_state="remote Etsy reference",
                    external_source="etsy",
                    review_state="synced",
                    file_exists=0,
                )
                session.add(remote_asset)
                session.flush()
                session.add(
                    AssetRecord(
                        product_id=product.id,
                        name="Local Downloaded Duck",
                        asset_type="source photo",
                        source_path=local_path.as_posix(),
                        preview_path=local_path.as_posix(),
                        canonical_url=shared_url,
                        readiness_state="existing Etsy photo ready",
                        external_source="etsy",
                        review_state="approved",
                        file_exists=1,
                        source_asset_id=remote_asset.id,
                    )
                )

            products = app.test_client().get("/products")
            self.assertEqual(products.status_code, 200)
            self.assertIn(b"Local Downloaded Duck", products.data)
            self.assertNotIn(b"Remote Downloaded Duck", products.data)

    def test_gallery_deletes_local_shared_file_and_unlinks_asset_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "delete-local-gallery.sqlite"
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            first_path = tmp_path / "shared-local-a.jpg"
            second_path = tmp_path / "shared-local-b.jpg"
            first_path.write_bytes(b"same local duck image")
            second_path.write_bytes(b"same local duck image")

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                first_product = ProductRecord(name="First Local Duck")
                second_product = ProductRecord(name="Second Local Duck")
                session.add_all([first_product, second_product])
                session.flush()
                first_asset = register_local_source_photo(session, first_path, product_id=first_product.id, name="Shared local duck A")
                second_asset = register_local_source_photo(session, second_path, product_id=second_product.id, name="Shared local duck B")
                review_asset(session, first_asset.id, "approved", "Approved local source.")
                review_asset(session, second_asset.id, "approved", "Approved local source.")
                first_asset.default_reference = 1
                second_asset.default_reference = 1
                item = create_planned_content_item(
                    session,
                    calendar_date=date(2026, 6, 28),
                    destinations=["Facebook"],
                    goals=["Sales growth"],
                    product_ids=[first_product.id, second_product.id],
                    selected_source_asset_ids=[first_asset.id, second_asset.id],
                )
                first_asset_id = first_asset.id
                second_asset_id = second_asset.id
                planned_item_id = item.id

            client = app.test_client()
            gallery = client.get("/assets")
            self.assertEqual(gallery.status_code, 200)
            self.assertIn(b'aria-label="Delete local image"', gallery.data)
            self.assertIn(b"Delete this local image file and unlink it from products?", gallery.data)
            self.assertIn(b'aria-label="Close drawer"', gallery.data)
            self.assertNotIn(b"<h3>Local file</h3>", gallery.data)

            response = client.post(f"/assets/{first_asset_id}/delete-local", follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Deleted 2 local files and unlinked 2 asset records.", response.data)
            self.assertFalse(first_path.exists())
            self.assertFalse(second_path.exists())

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                first = session.get(AssetRecord, first_asset_id)
                second = session.get(AssetRecord, second_asset_id)
                item = session.get(PlannedContentRecord, planned_item_id)
                for asset in (first, second):
                    self.assertIsNone(asset.product_id)
                    self.assertEqual(asset.file_exists, 0)
                    self.assertEqual(asset.default_reference, 0)
                    self.assertEqual(asset.hidden_from_generation, 1)
                    self.assertEqual(asset.manual_override_state, "deleted")
                self.assertEqual(json.loads(item.selected_source_asset_ids_json), [])

            products = client.get("/products")
            self.assertEqual(products.status_code, 200)
            self.assertNotIn(b"Shared local duck A", products.data)
            self.assertNotIn(b"Shared local duck B", products.data)

    def test_planning_hides_deleted_image_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "deleted-planning-image.sqlite"
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            reference_path = tmp_path / "deleted-planning-reference.jpg"
            option_path = tmp_path / "deleted-planning-image.jpg"
            reference_path.write_bytes(b"deleted planning reference bytes")
            option_path.write_bytes(b"deleted planning image bytes")

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = ProductRecord(name="Deleted Planning Image Duck")
                session.add(product)
                session.flush()
                reference_asset = register_local_source_photo(
                    session,
                    reference_path,
                    product_id=product.id,
                    name="Deleted planning reference",
                )
                review_asset(session, reference_asset.id, "approved", "Approved planning reference.")
                item = create_planned_content_item(
                    session,
                    calendar_date=date(2026, 6, 30),
                    destinations=["Facebook"],
                    goals=["Sales growth"],
                    product_ids=[product.id],
                    selected_source_asset_ids=[reference_asset.id],
                )
                image_candidate = register_uploaded_image_option(session, item.id, option_path, name="Deleted planning image option")
                image_asset_id = json.loads(image_candidate.body)["asset_id"]

            client = app.test_client()
            planning_before_delete = client.get("/planning")
            self.assertEqual(planning_before_delete.status_code, 200)
            self.assertIn(b"Deleted planning image option", planning_before_delete.data)
            self.assertIn(b"class=\"image-select-button\"", planning_before_delete.data)

            delete_response = client.post(f"/assets/{image_asset_id}/delete-local", follow_redirects=True)
            self.assertEqual(delete_response.status_code, 200)

            planning_after_delete = client.get("/planning")
            self.assertEqual(planning_after_delete.status_code, 200)
            self.assertNotIn(b"Deleted planning image option", planning_after_delete.data)
            self.assertNotIn(f"/assets/{image_asset_id}/preview".encode(), planning_after_delete.data)
            self.assertIn(b"class=\"image-upload-card\"", planning_after_delete.data)
            self.assertNotIn(b"Waiting for generation", planning_after_delete.data)

    def test_products_page_paginates_products_and_page_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "product-pages.sqlite"
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                for index in range(25):
                    product = ProductRecord(name=f"Paged Product {index:03d}")
                    session.add(product)
                    session.flush()
                    session.add(
                        AssetRecord(
                            product_id=product.id,
                            name=f"Paged Product Asset {index:03d}",
                            asset_type="Etsy product photo",
                            source_path=f"https://example.test/product-{index:03d}.jpg",
                            readiness_state="remote Etsy reference",
                        )
                    )

            client = app.test_client()
            first_page = client.get("/products")
            second_page = client.get("/products?page=2")

            self.assertEqual(first_page.status_code, 200)
            self.assertEqual(second_page.status_code, 200)
            self.assertIn(b"1-20 of 25 products", first_page.data)
            self.assertIn(b"21-25 of 25 products", second_page.data)
            self.assertIn(b"Paged Product 000", first_page.data)
            self.assertNotIn(b"Paged Product 020", first_page.data)
            self.assertNotIn(b"Paged Product Asset 020", first_page.data)
            self.assertIn(b"Paged Product 020", second_page.data)
            self.assertIn(b"Paged Product Asset 020", second_page.data)

    def test_dashboard_surfaces_planned_review_queue_without_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "review-queue.sqlite"
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = ProductRecord(name="Review Queue Duck")
                session.add(product)
                session.flush()
                item = PlannedContentRecord(
                    calendar_date=date(2026, 6, 26),
                    scheduled_time="14:30",
                    destinations_json='["Facebook"]',
                    goals_json='["Sales growth"]',
                    product_ids_json=json.dumps([product.id]),
                    status="needs_review",
                    brief_status="generated",
                )
                session.add(item)
                session.flush()
                session.add(
                    GeneratedContentCandidateRecord(
                        planned_item_id=item.id,
                        candidate_type="facebook_post",
                        provider="codex",
                        body="Draft copy waiting for review.",
                        review_state="needs_review",
                    )
                )

            dashboard = app.test_client().get("/")

            self.assertEqual(dashboard.status_code, 200)
            self.assertIn(b"Review Queue", dashboard.data)
            self.assertIn(b"Start review", dashboard.data)
            self.assertIn(b"Review Queue Duck", dashboard.data)
            self.assertIn(b"/planning#candidate-", dashboard.data)
            self.assertNotIn(b"The desk is clear", dashboard.data)

    def test_dashboard_review_queue_uses_destination_specific_candidate_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "review-queue-labels.sqlite"
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = ProductRecord(name="Platform Label Duck")
                session.add(product)
                session.flush()
                item = PlannedContentRecord(
                    calendar_date=date(2026, 6, 26),
                    scheduled_time="12:30",
                    destinations_json='["Instagram"]',
                    goals_json='["Follower growth"]',
                    product_ids_json=json.dumps([product.id]),
                    status="needs_review",
                    brief_status="generated",
                )
                session.add(item)
                session.flush()
                session.add(
                    GeneratedContentCandidateRecord(
                        planned_item_id=item.id,
                        candidate_type="facebook_post",
                        provider="codex",
                        body="Instagram draft waiting for review.",
                        review_state="needs_review",
                    )
                )
                session.add(
                    GeneratedContentCandidateRecord(
                        planned_item_id=item.id,
                        candidate_type="image_asset_option",
                        provider="codex",
                        body="Image option waiting for review.",
                        review_state="needs_review",
                    )
                )

            dashboard = app.test_client().get("/")

            self.assertEqual(dashboard.status_code, 200)
            self.assertIn(b"Instagram Caption", dashboard.data)
            self.assertNotIn(b"Facebook Post", dashboard.data)
            self.assertNotIn(b"Image Option", dashboard.data)
            self.assertNotIn(b"2 candidates", dashboard.data)

    def test_planned_content_uses_platform_default_schedule_when_time_is_blank(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        with session_scope(factory) as session:
            product = ProductRecord(name="Timed Duck")
            session.add(product)
            session.flush()
            facebook = create_planned_content_item(
                session,
                calendar_date=date(2026, 6, 22),
                destinations=["Facebook"],
                goals=["Follower growth"],
                product_ids=[product.id],
            )
            instagram = create_planned_content_item(
                session,
                calendar_date=date(2026, 6, 23),
                destinations=["Instagram"],
                goals=["Follower growth"],
                product_ids=[product.id],
            )
            pinterest = create_planned_content_item(
                session,
                calendar_date=date(2026, 6, 24),
                destinations=["Pinterest"],
                goals=["Gift consideration"],
                product_ids=[product.id],
            )

            self.assertEqual(facebook.scheduled_time, "18:30")
            self.assertEqual(instagram.scheduled_time, "12:30")
            self.assertEqual(pinterest.scheduled_time, "20:30")

    def test_calendar_planned_items_are_drawer_triggers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "calendar-drawers.sqlite"
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = ProductRecord(name="Calendar Drawer Duck")
                session.add(product)
                session.flush()
                item = PlannedContentRecord(
                    calendar_date=date(2026, 6, 26),
                    scheduled_time="11:15",
                    destinations_json='["Facebook"]',
                    goals_json='["Sales growth"]',
                    product_ids_json=json.dumps([product.id]),
                    status="needs_review",
                    brief_status="generated",
                )
                session.add(item)
                session.flush()
                item_id = item.id

            calendar_page = app.test_client().get("/calendar")

            self.assertEqual(calendar_page.status_code, 200)
            self.assertLess(calendar_page.data.index(b">Sun<"), calendar_page.data.index(b">Mon<"))
            self.assertLess(calendar_page.data.index(b">Mon<"), calendar_page.data.index(b">Sat<"))
            self.assertIn(f'data-open-drawer="#planned-drawer-{item_id}"'.encode(), calendar_page.data)
            self.assertIn(f'id="planned-drawer-{item_id}"'.encode(), calendar_page.data)
            self.assertIn(b"Review in Planning", calendar_page.data)

    def test_plan_generation_persists_calendar_tasks_and_beginner_fields(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        with session_scope(factory) as session:
            seed_database(session)
            plan = generate_and_persist_plan(session, mode="standard", start_date=date(2026, 6, 17))
            self.assertEqual(plan.mode, "standard")
            self.assertEqual(len(plan.calendar_items), 30)
            self.assertGreaterEqual(len(plan.tasks), 30)

            social_task = next(task for task in plan.tasks if task.owner_role == "social operator")
            self.assertIn(social_task.status, TASK_STATUSES)
            self.assertTrue(social_task.draft_caption)
            self.assertTrue(social_task.cta)
            self.assertTrue(json_list(social_task.posting_steps_json))
            self.assertTrue(json_list(social_task.preview_checklist_json))
            self.assertTrue(social_task.metric_instruction)

    def test_task_status_and_metrics_persist(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        with session_scope(factory) as session:
            seed_database(session)
            plan = ensure_default_plan(session, start_date=date(2026, 6, 17))
            task_id = plan.tasks[0].id
            update_task_status(session, task_id, "posted", "Posted from the test flow.")
            add_metric(session, task_id, reach=120, likes=14, comments=3, etsy_visits=7, notes="Good first test.")

        with session_scope(factory) as session:
            task = session.get(TaskRecord, task_id)
            metric = session.scalar(select(MetricRecord).where(MetricRecord.task_id == task_id))

            self.assertIsNotNone(task)
            self.assertEqual(task.status, "metrics needed")
            self.assertEqual(task.notes, "Posted from the test flow.")
            self.assertIsNotNone(metric)
            self.assertEqual(metric.reach, 120)
            self.assertEqual(metric.etsy_visits, 7)

    def test_phase4_operator_services_prioritize_and_track_metrics_due(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        with session_scope(factory) as session:
            seed_database(session)
            plan = ensure_default_plan(session, start_date=date(2026, 6, 17))
            operator_model = today_view(session, today=date(2026, 6, 17))
            self.assertIsNotNone(operator_model.recommended)
            self.assertEqual(operator_model.role, "social operator")
            self.assertIn("Post", operator_model.recommended.action_title)

            task_id = operator_model.recommended.task.id
            complete_task_status(session, task_id, "mark_posted", notes="Posted.", post_url="https://example.com/post")

            task = session.get(TaskRecord, task_id)
            self.assertEqual(task.status, "posted")
            self.assertEqual(task.metric_status, "pending")
            self.assertEqual(task.published_url, "https://example.com/post")
            self.assertIsNotNone(task.metric_due_date)
            task.metric_due_date = date(2026, 6, 18)

            second_task = next(item for item in plan.tasks if item.id != task_id and item.owner_role == "social operator")
            complete_task_status(session, second_task.id, "mark_posted", notes="Posted without URL.")
            second_task.metric_due_date = date(2026, 6, 18)
            due_models = metrics_due_tasks(session, today=date(2026, 6, 18))
            reasons_by_id = {model.task.id: model.metric_followup_reason for model in due_models}
            self.assertEqual(reasons_by_id[task_id], "missing_metrics")
            self.assertEqual(reasons_by_id[second_task.id], "missing_post_url")

            agenda = week_agenda(session, today=date(2026, 6, 17))
            self.assertTrue(agenda)
            self.assertTrue(any(day.tasks for day in agenda))

            instagram_agenda = week_agenda(session, today=date(2026, 6, 17), platform="Instagram")
            self.assertTrue(instagram_agenda)
            self.assertTrue(all(task.task.platform == "Instagram" for day in instagram_agenda for task in day.tasks))

            posted_agenda = week_agenda(session, today=date(2026, 6, 17), status="posted")
            self.assertTrue(any(task.task.id == task_id for day in posted_agenda for task in day.tasks))

    def test_web_app_renders_operator_workflow_and_persists_forms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "web.sqlite"
            app = create_app(db_path, bootstrap_data=True)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            app.config["ASSETS_ROOT"] = Path(tmp) / "assets" / "products"
            app.config["EXPORT_DIR"] = Path(tmp) / "exports"
            client = app.test_client()

            health = client.get("/health")
            self.assertEqual(health.status_code, 200)

            dashboard = client.get("/")
            self.assertEqual(dashboard.status_code, 200)
            self.assertIn(b"Today", dashboard.data)
            self.assertIn(b"Recommended next action", dashboard.data)
            self.assertIn(b"Start task", dashboard.data)

            week = client.get("/week")
            self.assertEqual(week.status_code, 200)
            self.assertIn(b"This Week", week.data)

            guides = client.get("/guides")
            self.assertEqual(guides.status_code, 200)
            self.assertIn(b"Posting Help", guides.data)
            self.assertIn(b"Instagram Reel", guides.data)

            completed = client.get("/completed")
            self.assertEqual(completed.status_code, 200)
            self.assertIn(b"Completed", completed.data)

            assets = client.get("/assets")
            self.assertEqual(assets.status_code, 200)
            self.assertIn(b"Assets", assets.data)
            self.assertIn(b"data-photo-dropzone", assets.data)
            self.assertIn(b"Drop image", assets.data)
            self.assertIn(b"Upload</button>", assets.data)
            self.assertNotIn(b"Upload Photo", assets.data)
            self.assertNotIn(b"Upload Source Photo", assets.data)
            self.assertNotIn(b"Feed the assistant", assets.data)
            self.assertNotIn(b"Review or source notes", assets.data)
            self.assertNotIn(b"Register source photo", assets.data)
            self.assertNotIn(b"Photo path", assets.data)
            self.assertNotIn(b"Add Generated or Uploaded Image", assets.data)
            self.assertNotIn(b"Prepare Generation Runs", assets.data)
            self.assertNotIn(b"Generation Jobs", assets.data)
            self.assertIn(b"Photo Details", assets.data)
            self.assertIn(b"Save details", assets.data)
            self.assertIn(b"Used by", assets.data)

            upload_response = client.post(
                "/assets/upload-source",
                data={
                    "photo": (io.BytesIO(tiny_png_bytes("#0f766e")), "upload-bingo.png"),
                    "name": "Uploaded web source",
                },
                content_type="multipart/form-data",
                follow_redirects=True,
            )
            self.assertEqual(upload_response.status_code, 200)
            self.assertIn(b"Uploaded source photo", upload_response.data)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                uploaded = session.scalar(select(AssetRecord).where(AssetRecord.name == "Uploaded web source"))
                product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
                self.assertIsNotNone(uploaded)
                self.assertIsNotNone(product)
                uploaded_id = uploaded.id
                product_id = product.id

            link_response = client.post(
                f"/assets/{uploaded_id}/product",
                data={"product_id": str(product_id), "name": "Renamed web source"},
                follow_redirects=True,
            )
            self.assertEqual(link_response.status_code, 200)
            self.assertIn(b"Photo details saved.", link_response.data)
            with session_scope(app.config["SESSION_FACTORY"]) as session:
                uploaded = session.get(AssetRecord, uploaded_id)
                self.assertEqual(uploaded.product_id, product_id)
                self.assertEqual(uploaded.name, "Renamed web source")

            settings = client.get("/settings")
            self.assertEqual(settings.status_code, 200)
            self.assertIn(b"Export scope", settings.data)
            self.assertIn(b"Products and images", settings.data)
            self.assertIn(b"JSON exports", settings.data)
            self.assertNotIn(b"<option value=\"json\">JSON</option>", settings.data)
            self.assertNotIn(b"Create backup", settings.data)
            self.assertNotIn(b"Sync Etsy", settings.data)
            self.assertNotIn(b"Sync website", settings.data)
            self.assertNotIn(b"Etsy CSV Import", settings.data)
            self.assertNotIn(b"Network Use", settings.data)
            self.assertNotIn(b"Product Matching", settings.data)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
                self.assertIsNotNone(product)
                product.sales_momentum_note = "Long imported description. " * 30
                session.add(
                    EtsyReviewRecord(
                        product_id=product.id,
                        external_source="etsy_api",
                        external_id="transaction:web-products-review",
                        shop_id="fixture-shop",
                        listing_id=product.external_id,
                        transaction_id="web-products-review",
                        buyer_user_id="buyer-1",
                        rating=5,
                        review="Exactly the kind of tiny duck joy I wanted.",
                        language="en",
                        created_timestamp=1_725_321_600,
                    )
                )

            products_page = client.get("/products")
            self.assertEqual(products_page.status_code, 200)
            self.assertIn(b"Products", products_page.data)
            self.assertIn(b"Sync Etsy", products_page.data)
            self.assertNotIn(b"Sync website", products_page.data)
            self.assertNotIn(b"Match duplicate products", products_page.data)
            self.assertIn(b"data-tag-combobox", products_page.data)
            self.assertIn(b"data-tag-suggestions", products_page.data)
            self.assertIn(b"vendor/lucide.min.js", products_page.data)
            self.assertIn(b"aria-label=\"Product sort\"", products_page.data)
            self.assertIn(b"data-auto-submit", products_page.data)
            self.assertNotIn(b"data-lucide=\"filter-x\"", products_page.data)
            self.assertNotIn(b"Reset product sort", products_page.data)
            self.assertNotIn(b"<button type=\"submit\">Apply</button>", products_page.data)
            self.assertNotIn(b"Save default references", products_page.data)
            self.assertIn(b"data-reference-form", products_page.data)
            self.assertIn(b"data-reference-checkbox", products_page.data)
            self.assertIn(b"reference-toggle", products_page.data)
            self.assertIn(b"Toggle default reference image", products_page.data)
            self.assertIn(b"Edit image details in Gallery", products_page.data)
            self.assertIn(b"Generate social images", products_page.data)
            self.assertIn(b"Uses the default reference images selected above", products_page.data)
            self.assertIn(b"data-product-social-studio", products_page.data)
            self.assertIn(b"data-social-reference-count", products_page.data)
            self.assertIn(b"data-social-generate-button", products_page.data)
            self.assertIn(b"open_asset=", products_page.data)
            self.assertNotIn(b"product-image-link-", products_page.data)
            self.assertIn(b"data-lucide=\"image\"", products_page.data)
            self.assertIn(b"data-lucide=\"badge-check\"", products_page.data)
            self.assertNotIn(b"Local product tag", products_page.data)
            self.assertNotIn(b"Local product tags", products_page.data)
            self.assertIn(b"Description", products_page.data)
            self.assertIn(b"See more", products_page.data)
            self.assertIn(b'<div class="copybox description-preview"><span>Long imported description.', products_page.data)
            self.assertIn(b"Reviews", products_page.data)
            self.assertIn(b"1 review", products_page.data)
            self.assertIn(b"class=\"product-review-disclosure\"", products_page.data)
            self.assertIn(b"Latest customer language and social proof", products_page.data)
            self.assertIn(b"5/5", products_page.data)
            self.assertIn(b"Exactly the kind of tiny duck joy I wanted.", products_page.data)
            self.assertIn(b"product-source-footer", products_page.data)
            self.assertNotIn(b"Source identities", products_page.data)
            self.assertNotIn(b"Share Etsy shop", products_page.data)
            self.assertNotIn(b"Open source", products_page.data)
            self.assertNotIn(b"Edit product fields", products_page.data)
            self.assertNotIn(b"Audience:", products_page.data)
            self.assertNotIn(b"Priority:", products_page.data)
            self.assertNotIn(b'<span class="pill">fresh</span>', products_page.data)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
                self.assertIsNotNone(product)
                product_id = product.id

            tags_response = client.post(
                f"/products/{product_id}/tags/add",
                data={"tag": "desk gift"},
                follow_redirects=True,
            )
            self.assertEqual(tags_response.status_code, 200)
            self.assertIn(b"Product tag added.", tags_response.data)
            self.assertIn(b"desk gift", tags_response.data)

            tag_search_response = client.get("/api/product-tags?q=desk")
            self.assertEqual(tag_search_response.status_code, 200)
            self.assertIn("desk gift", tag_search_response.get_json()["tags"])

            api_tag_response = client.post(
                f"/api/products/{product_id}/tags",
                json={"tag": "planning guide"},
            )
            self.assertEqual(api_tag_response.status_code, 200)
            self.assertEqual(api_tag_response.get_json()["tag"], "planning guide")
            self.assertTrue(api_tag_response.get_json()["created"])

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                source = session.scalar(select(AssetRecord).where(AssetRecord.product_id == product_id).order_by(AssetRecord.id))
                self.assertIsNotNone(source)
                source_id = source.id

            defaults_response = client.post(
                f"/products/{product_id}/default-reference-assets",
                data={"asset_ids": str(source_id)},
                follow_redirects=True,
            )
            self.assertEqual(defaults_response.status_code, 200)
            self.assertIn(b"Default reference images saved.", defaults_response.data)
            self.assertIn(b"default reference", defaults_response.data)

            api_defaults_response = client.post(
                f"/api/products/{product_id}/default-reference-assets",
                json={"asset_ids": [source_id]},
            )
            self.assertEqual(api_defaults_response.status_code, 200)
            self.assertEqual(api_defaults_response.get_json()["asset_ids"], [source_id])

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                replacement_product = ProductRecord(name="Corrected Image Product")
                session.add(replacement_product)
                session.flush()
                replacement_product_id = replacement_product.id

            asset_gallery_response = client.get(f"/assets?open_asset={source_id}&return_to=/products%23product-{product_id}")
            self.assertEqual(asset_gallery_response.status_code, 200)
            self.assertIn(f'data-auto-open-drawer="#asset-drawer-{source_id}"'.encode(), asset_gallery_response.data)
            self.assertIn(b"Back to products", asset_gallery_response.data)
            self.assertIn(b"/products#product-", asset_gallery_response.data)

            image_edit_response = client.post(
                f"/assets/{source_id}/product",
                data={
                    "product_id": str(replacement_product_id),
                    "name": "Corrected product image",
                    "return_to": f"/assets?open_asset={source_id}&return_to=/products%23product-{product_id}#asset-{source_id}",
                },
                follow_redirects=True,
            )
            self.assertEqual(image_edit_response.status_code, 200)
            self.assertIn(b"Photo details saved.", image_edit_response.data)
            with session_scope(app.config["SESSION_FACTORY"]) as session:
                source = session.get(AssetRecord, source_id)
                self.assertEqual(source.product_id, replacement_product_id)
                self.assertEqual(source.name, "Corrected product image")

            export_response = client.post("/settings/export", data={"scope": "products"})
            self.assertEqual(export_response.status_code, 200)
            self.assertEqual(export_response.mimetype, "application/json")
            export_payload = json.loads(export_response.data.decode("utf-8"))
            self.assertEqual(export_payload["format"], "marketing_os_phase4_export")
            self.assertEqual(export_payload["scope"], "products")
            self.assertIn("products", export_payload)
            self.assertIn("assets", export_payload)
            self.assertNotIn("tasks", export_payload)
            export_response.close()

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                task = session.scalars(select(TaskRecord).order_by(TaskRecord.id)).first()
                self.assertIsNotNone(task)
                task_id = task.id

            detail = client.get(f"/tasks/{task_id}")
            self.assertEqual(detail.status_code, 200)
            self.assertIn(b"Prepare", detail.data)
            self.assertIn(b"Post", detail.data)
            self.assertIn(b"Finish", detail.data)
            self.assertIn(b"Metrics Later", detail.data)
            self.assertIn(b"Copy caption", detail.data)
            self.assertIn(b"Preview Checklist", detail.data)
            self.assertIn(b"Common mistake to avoid", detail.data)

            finish_response = client.post(
                f"/tasks/{task_id}/finish",
                data={"action": "mark_posted", "notes": "Posted through web test.", "post_url": "https://example.com/post"},
                follow_redirects=True,
            )
            self.assertEqual(finish_response.status_code, 200)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                task = session.get(TaskRecord, task_id)
                task.metric_due_date = date.today()

            metrics_due = client.get("/metrics-due")
            self.assertEqual(metrics_due.status_code, 200)
            self.assertIn(b"Follow-Ups", metrics_due.data)
            self.assertIn(b"Metrics needed", metrics_due.data)

            metric_response = client.post(
                f"/tasks/{task_id}/metrics",
                data={"reach": "88", "likes": "12", "comments": "2", "notes": "Recorded manually."},
                follow_redirects=True,
            )
            self.assertEqual(metric_response.status_code, 200)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                task = session.get(TaskRecord, task_id)
                metric = session.scalar(select(MetricRecord).where(MetricRecord.task_id == task_id))
                self.assertEqual(task.metric_status, "complete")
                self.assertEqual(task.published_url, "https://example.com/post")
            self.assertEqual(metric.reach, 88)

    def test_phase4_json_api_reuses_operator_view_models(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "api.sqlite"
            app = create_app(db_path, bootstrap_data=True)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            app.config["ASSETS_ROOT"] = Path(tmp) / "assets" / "products"
            client = app.test_client()

            today_response = client.get("/api/today")
            self.assertEqual(today_response.status_code, 200)
            today_payload = today_response.get_json()
            self.assertEqual(today_payload["role"], "social operator")
            self.assertIn("attention_count", today_payload)
            self.assertIsNotNone(today_payload["recommended"])
            self.assertIn("action_title", today_payload["recommended"])
            self.assertIn("metric_status", today_payload["recommended"])
            self.assertIn("metric_followup_reason", today_payload["recommended"])

            task_id = today_payload["recommended"]["id"]
            task_response = client.get(f"/api/tasks/{task_id}")
            self.assertEqual(task_response.status_code, 200)
            task_payload = task_response.get_json()
            self.assertEqual(task_payload["id"], task_id)
            self.assertIn("posting_steps", task_payload)
            self.assertIn("preview_checklist", task_payload)
            self.assertIn("post_guidance", task_payload)
            self.assertIn("common_mistake", task_payload["post_guidance"])
            self.assertTrue(task_payload["post_guidance"]["common_mistake"])
            self.assertIn("metric_fields", task_payload)
            self.assertIn("asset_options", task_payload)

            week_response = client.get("/api/week")
            self.assertEqual(week_response.status_code, 200)
            self.assertIn("agendas", week_response.get_json())

            metrics_response = client.get("/api/metrics-due")
            self.assertEqual(metrics_response.status_code, 200)
            self.assertIn("tasks", metrics_response.get_json())

            assets_response = client.get("/api/assets")
            self.assertEqual(assets_response.status_code, 200)
            assets_payload = assets_response.get_json()
            self.assertIn("assets", assets_payload)
            self.assertIn("sync_status", assets_payload["assets"][0])
            self.assertIn("manual_override_state", assets_payload["assets"][0])
            self.assertIn("file_checksum", assets_payload["assets"][0])

            health_response = client.get("/api/data-health")
            self.assertEqual(health_response.status_code, 200)
            health_payload = health_response.get_json()
            self.assertTrue(any(item["area"] == "Assets" for item in health_payload["items"]))
            self.assertFalse(any(item["area"] == "Phase 5 Readiness" for item in health_payload["items"]))

    def test_phase4_json_api_mutations_reuse_task_services(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "api-mutations.sqlite"
            app = create_app(db_path, bootstrap_data=True)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            client = app.test_client()

            today_payload = client.get("/api/today").get_json()
            task_id = today_payload["recommended"]["id"]

            finish_response = client.post(
                f"/api/tasks/{task_id}/finish",
                json={"action": "mark_posted", "notes": "Posted through API.", "post_url": "https://example.com/api-post"},
            )
            self.assertEqual(finish_response.status_code, 200)
            finished_task = finish_response.get_json()["task"]
            self.assertEqual(finished_task["status"], "posted")
            self.assertEqual(finished_task["published_url"], "https://example.com/api-post")
            self.assertEqual(finished_task["metric_status"], "pending")

            metrics_response = client.post(
                f"/api/tasks/{task_id}/metrics",
                json={"reach": 321, "likes": 44, "comments": 5, "notes": "API metrics."},
            )
            self.assertEqual(metrics_response.status_code, 200)
            metrics_payload = metrics_response.get_json()
            self.assertEqual(metrics_payload["task"]["metric_status"], "complete")
            self.assertEqual(metrics_payload["metric"]["task_id"], task_id)

            source_path = Path(tmp) / "approved-bingo.jpg"
            source_path.write_bytes(b"fake image bytes")
            with session_scope(app.config["SESSION_FACTORY"]) as session:
                task = session.get(TaskRecord, task_id)
                product = session.scalar(select(ProductRecord).where(ProductRecord.name == task.product_name))
                asset = register_local_source_photo(session, source_path, product_id=product.id, name="API approved asset")
                asset_id = asset.id

            rejected_asset_response = client.post(f"/api/tasks/{task_id}/asset", json={"asset_id": asset_id})
            self.assertEqual(rejected_asset_response.status_code, 400)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                review_asset(session, asset_id, "approved", "Accurate.")

            asset_response = client.post(f"/api/tasks/{task_id}/asset", json={"asset_id": asset_id})
            self.assertEqual(asset_response.status_code, 200)
            self.assertEqual(asset_response.get_json()["task"]["asset_id"], asset_id)

    def test_phase4_task_asset_assignment_requires_approved_file_backed_asset(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        source_path = Path(tmp.name) / "photos" / "approved-bingo.jpg"
        source_path.parent.mkdir(parents=True)
        source_path.write_bytes(b"fake image bytes")

        with session_scope(factory) as session:
            seed_database(session)
            plan = ensure_default_plan(session, start_date=date(2026, 6, 17))
            task = next(task for task in plan.tasks if task.product_name == "Bingo Duck")
            product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
            asset = register_local_source_photo(session, source_path, product_id=product.id, name="Approved Bingo photo")

            with self.assertRaises(ValueError):
                assign_asset_to_task(session, task.id, asset.id)

            review_asset(session, asset.id, "approved", "Accurate source photo.")
            assign_asset_to_task(session, task.id, asset.id)
            self.assertEqual(task.asset_id, asset.id)

            options = task_asset_options(session, task)
            self.assertTrue(any(option.asset.id == asset.id for option in options))

    def test_phase4_task_asset_assignment_downloads_remote_product_image_once(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        remote_path = Path(tmp.name) / "remote" / "bingo-etsy.jpg"
        remote_path.parent.mkdir(parents=True)
        remote_path.write_bytes(b"remote etsy image bytes")
        assets_root = Path(tmp.name) / "assets" / "products"

        with session_scope(factory) as session:
            seed_database(session)
            plan = ensure_default_plan(session, start_date=date(2026, 6, 17))
            task = next(task for task in plan.tasks if task.product_name == "Bingo Duck")
            product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
            remote_asset = AssetRecord(
                product_id=product.id,
                name="Bingo Etsy remote",
                asset_type="Etsy product photo",
                source_path=remote_path.as_uri(),
                preview_path=remote_path.as_uri(),
                platform_suitability_json='["Etsy", "Facebook", "Instagram"]',
                readiness_state="external source needs review",
                notes="Remote Etsy image reference.",
                external_source="etsy",
                external_id="remote-bingo",
                canonical_url=remote_path.as_uri(),
                sync_status="imported",
                staleness_state="fresh",
                review_state="needs review",
                file_exists=0,
            )
            session.add(remote_asset)
            session.flush()

            options = task_asset_options(session, task)
            self.assertTrue(any(option.asset.id == remote_asset.id for option in options))

            assign_asset_to_task(session, task.id, remote_asset.id, assets_root=assets_root)

            self.assertNotEqual(task.asset_id, remote_asset.id)
            local_asset = session.get(AssetRecord, task.asset_id)
            self.assertIsNotNone(local_asset)
            self.assertEqual(local_asset.canonical_url, remote_path.as_uri())
            self.assertEqual(local_asset.source_asset_id, remote_asset.id)
            self.assertEqual(local_asset.review_state, "approved")
            self.assertTrue(Path(local_asset.source_path).exists())
            self.assertTrue(str(local_asset.source_path).startswith(str(assets_root)))

            first_local_id = local_asset.id
            task.asset_id = None
            assign_asset_to_task(session, task.id, remote_asset.id, assets_root=assets_root)
            self.assertEqual(task.asset_id, first_local_id)
            local_copies = list(session.scalars(select(AssetRecord).where(AssetRecord.canonical_url == remote_path.as_uri(), AssetRecord.file_exists == 1)))
            self.assertEqual(len(local_copies), 1)

    def test_phase4_asset_scan_and_data_health(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        asset_root = Path(tmp.name) / "assets" / "products"
        source_dir = asset_root / "bingo-duck" / "source"
        source_dir.mkdir(parents=True)
        (source_dir / "etsy-photo.jpg").write_bytes(b"fake image bytes")

        with session_scope(factory) as session:
            seed_database(session)
            ensure_default_plan(session, start_date=date(2026, 6, 17))
            imported = scan_local_asset_folder(session, asset_root)
            self.assertEqual(len(imported), 1)
            self.assertEqual(imported[0].external_source, "local_folder")
            self.assertEqual(imported[0].file_exists, 1)
            self.assertTrue(imported[0].file_checksum)
            self.assertEqual(imported[0].review_state, "needs review")

            health = data_health(session)
            self.assertTrue(any(item.area == "Asset Review" and item.count >= 1 for item in health))
            self.assertTrue(any(item.area == "Templates" and item.status == "OK" for item in health))
            self.assertTrue(any(item.area == "Imports" for item in health))

            inventory = asset_inventory(session)
            self.assertTrue(any(model.used_by for model in inventory))

    def test_phase4_manual_source_photo_registration(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        source_path = Path(tmp.name) / "photos" / "manual-bingo.jpg"
        source_path.parent.mkdir(parents=True)
        source_path.write_bytes(b"fake image bytes")

        with session_scope(factory) as session:
            seed_database(session)
            product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
            asset = register_local_source_photo(
                session,
                source_path,
                product_id=product.id,
                name="Manual Bingo source",
                notes="Registered by path.",
            )

            self.assertEqual(asset.product_id, product.id)
            self.assertEqual(asset.name, "Manual Bingo source")
            self.assertEqual(asset.asset_type, "source photo")
            self.assertEqual(asset.external_source, "local_file")
            self.assertEqual(asset.sync_status, "registered")
            self.assertEqual(asset.review_state, "needs review")
            self.assertEqual(asset.file_exists, 1)
            self.assertTrue(asset.file_checksum)

            with self.assertRaises(FileNotFoundError):
                register_local_source_photo(session, Path(tmp.name) / "missing.jpg")

    def test_phase4_source_photo_upload_copy_uses_inventory_structure(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        source_path = Path(tmp.name) / "incoming" / "Bingo Upload.JPG"
        source_path.parent.mkdir(parents=True)
        source_path.write_bytes(b"fake image bytes")
        assets_root = Path(tmp.name) / "assets" / "products"

        with session_scope(factory) as session:
            seed_database(session)
            product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
            asset = import_source_photo_to_inventory(
                session,
                source_path,
                product_id=product.id,
                name="Uploaded Bingo source",
                assets_root=assets_root,
            )

            self.assertEqual(asset.product_id, product.id)
            self.assertEqual(asset.name, "Uploaded Bingo source")
            self.assertIn("assets/products/bingo-duck/source", asset.source_path)
            self.assertTrue(Path(asset.source_path).exists())
            self.assertTrue(asset.file_checksum)
            self.assertEqual(asset.review_state, "needs review")

    def test_phase4_external_product_image_import_creates_listing_asset(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        from PIL import Image

        source_path = Path(tmp.name) / "remote" / "mailman.png"
        source_path.parent.mkdir(parents=True)
        Image.new("RGB", (320, 320), "#38bdf8").save(source_path)
        assets_root = Path(tmp.name) / "assets" / "products"

        with session_scope(factory) as session:
            seed_database(session)
            product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Mailman Duck"))
            asset = import_external_product_image(
                session,
                source_path.as_uri(),
                product_id=product.id,
                name="Mailman website hero",
                assets_root=assets_root,
            )

            self.assertEqual(asset.product_id, product.id)
            self.assertEqual(asset.asset_type, "external listing image")
            self.assertEqual(asset.external_source, "external_image")
            self.assertEqual(asset.sync_status, "imported")
            self.assertEqual(asset.canonical_url, source_path.as_uri())
            self.assertTrue(Path(asset.source_path).exists())
            self.assertTrue(asset.file_checksum)

    def test_phase4_generated_asset_candidate_requires_review_then_approval(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        with session_scope(factory) as session:
            seed_database(session)
            source = session.scalars(select(AssetRecord).order_by(AssetRecord.id)).first()
            candidate = register_generated_asset_candidate(
                session,
                source,
                Path(tmp.name) / "outputs" / "graphics" / "bingo-square.jpg",
                "Square Product Card",
                "Preserve the duck and create a square product card.",
            )

            self.assertEqual(candidate.asset_type, "generated graphic")
            self.assertEqual(candidate.review_state, "needs review")
            self.assertEqual(candidate.source_asset_id, source.id)
            self.assertIn("Preserve the duck", candidate.generated_prompt)

            with self.assertRaises(ValueError):
                review_asset(session, candidate.id, "approved", "Looks accurate.")

            Path(candidate.source_path).parent.mkdir(parents=True)
            Path(candidate.source_path).write_bytes(b"generated image bytes")
            review_asset(session, candidate.id, "approved", "Looks accurate.")
            self.assertEqual(candidate.review_state, "approved")
            self.assertEqual(candidate.readiness_state, "ready to use")

    def test_phase4_creative_asset_plans_require_approved_source_and_register_three_outputs(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        source_path = Path(tmp.name) / "assets" / "products" / "bingo-duck" / "source" / "photo.jpg"
        source_path.parent.mkdir(parents=True)
        source_path.write_bytes(b"fake image bytes")

        with session_scope(factory) as session:
            seed_database(session)
            product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
            source = AssetRecord(
                product_id=product.id,
                name="Bingo Duck source photo",
                asset_type="source photo",
                source_path=source_path.as_posix(),
                preview_path=source_path.as_posix(),
                platform_suitability_json='["Instagram", "Facebook"]',
                readiness_state="needs review",
                review_state="needs review",
            )
            session.add(source)
            session.flush()

            plans = [plan for plan in creative_asset_plans(session) if plan.source_asset.id == source.id]
            self.assertEqual(len(plans), 1)
            self.assertFalse(plans[0].source_ready)
            self.assertEqual(len(plans[0].formats), 3)

            with self.assertRaises(ValueError):
                register_creative_outputs_for_source(session, source.id)

            review_asset(session, source.id, "approved", "Source photo is accurate.")
            plans = [plan for plan in creative_asset_plans(session) if plan.source_asset.id == source.id]
            self.assertTrue(plans[0].source_ready)

            candidates = register_creative_outputs_for_source(session, source.id)
            self.assertEqual(len(candidates), 3)
            self.assertTrue(all(candidate.review_state == "needs review" for candidate in candidates))
            self.assertTrue(all(candidate.source_asset_id == source.id for candidate in candidates))
            self.assertTrue(any("Square Product Card" in candidate.name for candidate in candidates))

    def test_phase4_creative_generation_run_writes_manifest(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        source_path = Path(tmp.name) / "assets" / "products" / "bingo-duck" / "source" / "photo.jpg"
        source_path.parent.mkdir(parents=True)
        source_path.write_bytes(b"fake image bytes")
        output_root = Path(tmp.name) / "outputs" / "graphics"
        manifest_dir = Path(tmp.name) / "outputs" / "manifests"

        with session_scope(factory) as session:
            seed_database(session)
            product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
            source = AssetRecord(
                product_id=product.id,
                name="Bingo Duck source photo",
                asset_type="source photo",
                source_path=source_path.as_posix(),
                preview_path=source_path.as_posix(),
                platform_suitability_json='["Instagram", "Facebook"]',
                readiness_state="ready to use",
                review_state="approved",
            )
            session.add(source)
            session.flush()

            run = prepare_creative_generation_run(
                session,
                source.id,
                output_root=output_root,
                manifest_dir=manifest_dir,
            )
            self.assertEqual(len(run.candidates), 3)
            self.assertTrue(run.manifest_path.exists())
            payload = json.loads(run.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["source_asset"]["id"], source.id)
            self.assertEqual(len(payload["outputs"]), 3)
            self.assertTrue(all("prompt" in output for output in payload["outputs"]))
            self.assertTrue(all(output["review_state"] == "needs review" for output in payload["outputs"]))
            self.assertTrue(all(str(output_root) in output["output_path"] for output in payload["outputs"]))

    def test_phase4_creative_output_generation_writes_three_files(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        from PIL import Image

        source_path = Path(tmp.name) / "assets" / "products" / "bingo-duck" / "source" / "photo.jpg"
        source_path.parent.mkdir(parents=True)
        Image.new("RGB", (600, 500), "#facc15").save(source_path)
        output_root = Path(tmp.name) / "outputs" / "graphics"
        manifest_dir = Path(tmp.name) / "outputs" / "manifests"

        with session_scope(factory) as session:
            seed_database(session)
            product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
            source = register_local_source_photo(session, source_path, product_id=product.id, name="Bingo Duck source photo")
            review_asset(session, source.id, "approved", "Source photo is accurate.")

            run = generate_creative_output_files_for_source(
                session,
                source.id,
                output_root=output_root,
                manifest_dir=manifest_dir,
            )
            self.assertEqual(len(run.candidates), 3)
            self.assertTrue(run.manifest_path.exists())
            self.assertTrue(all(Path(candidate.source_path).exists() for candidate in run.candidates))
            self.assertTrue(all(candidate.file_checksum for candidate in run.candidates))
            self.assertTrue(all(candidate.review_state == "needs review" for candidate in run.candidates))

    def test_phase5_manual_magnific_import_requires_approved_source_and_review(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        source_path = Path(tmp.name) / "assets" / "products" / "bingo-duck" / "source" / "photo.jpg"
        output_path = Path(tmp.name) / "outputs" / "bingo-facebook.jpg"
        source_path.parent.mkdir(parents=True)
        output_path.parent.mkdir(parents=True)
        source_path.write_bytes(b"source image bytes")
        output_path.write_bytes(b"generated image bytes")

        with session_scope(factory) as session:
            seed_database(session)
            plan = ensure_default_plan(session, start_date=date(2026, 6, 17))
            product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
            source = register_local_source_photo(session, source_path, product_id=product.id, name="Bingo approved source")

            with self.assertRaises(ValueError):
                import_manual_generated_output(
                    session,
                    source.id,
                    output_path,
                    target_format="Facebook post image",
                    prompt="Preserve product accuracy.",
                    provider="magnific_manual",
                )

            review_asset(session, source.id, "approved", "Source is accurate.")
            result = import_manual_generated_output(
                session,
                source.id,
                output_path,
                target_format="Facebook post image",
                prompt="Preserve product accuracy.",
                provider="magnific_manual",
                model_name="Magnific MCP",
                provider_job_id="job-123",
                output_url="https://magnific.example/jobs/job-123",
                requested_dimensions="1080x1080",
                notes="Check product shape before approving.",
            )

            self.assertEqual(result.job.provider, "magnific_manual")
            self.assertEqual(result.job.provider_job_id, "job-123")
            self.assertEqual(result.job.review_state, "needs_review")
            self.assertEqual(result.candidate.review_state, "needs review")
            self.assertEqual(result.candidate.source_asset_id, source.id)
            self.assertEqual(result.candidate.external_source, "magnific_manual")
            self.assertEqual(result.candidate.external_id, "job-123")

            health_before_review = data_health(session)
            self.assertTrue(any(item.area == "Creative Generation" and item.count >= 1 for item in health_before_review))

            reviewed_job = review_creative_generation_job(
                session,
                result.job.id,
                "approved",
                review_notes="Matt approved the generated output for product accuracy.",
                reviewed_by="Matt",
            )
            self.assertEqual(reviewed_job.review_state, "approved")
            self.assertEqual(reviewed_job.reviewed_by, "Matt")
            self.assertIsNotNone(reviewed_job.reviewed_at)
            self.assertEqual(result.candidate.review_state, "approved")

            health_after_review = data_health(session)
            self.assertTrue(any(item.area == "Creative Generation" and item.status == "OK" for item in health_after_review))

            task = next(task for task in plan.tasks if task.product_name == "Bingo Duck")
            assign_asset_to_task(session, task.id, result.candidate.id)
            self.assertEqual(task.asset_id, result.candidate.id)

            target = export_operating_data(session, Path(tmp.name) / "exports")
            payload = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["creative_generation_jobs"]), 1)
            self.assertEqual(payload["creative_generation_jobs"][0]["provider_job_id"], "job-123")
            self.assertEqual(payload["creative_generation_jobs"][0]["reviewed_by"], "Matt")
            self.assertIsNotNone(payload["creative_generation_jobs"][0]["reviewed_at"])

    def test_phase4_sqlite_backup_copies_database_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "phase4.sqlite"
            backup_dir = Path(tmp) / "backups"
            engine = create_db_engine(db_path)
            self.addCleanup(engine.dispose)
            init_db(engine)
            target = backup_sqlite_database(db_path, backup_dir)
            self.assertTrue(target.exists())
            self.assertEqual(target.parent, backup_dir)

    def test_phase4_operating_data_export_writes_portable_json(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        with session_scope(factory) as session:
            seed_database(session)
            ensure_default_plan(session, start_date=date(2026, 6, 17))
            target = export_operating_data(session, Path(tmp.name) / "exports")

            self.assertTrue(target.exists())
            payload = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(payload["format"], "marketing_os_phase4_export")
            self.assertEqual(payload["scope"], "all")
            self.assertEqual(payload["version"], 1)
            self.assertTrue(payload["products"])
            self.assertTrue(payload["templates"])
            self.assertTrue(payload["plans"])
            self.assertTrue(payload["tasks"])
            self.assertIn("metrics", payload)
            self.assertIn("sync_metadata", payload)
            self.assertIn("planned_content_items", payload)
            self.assertIn("generated_content_candidates", payload)
            self.assertIn("external_source", payload["products"][0])
            self.assertIn("manual_override_state", payload["products"][0])
            self.assertIn("metric_status", payload["tasks"][0])
            self.assertIn("manual_override_state", payload["tasks"][0])
            self.assertIn("file_checksum", payload["assets"][0])

            scoped = export_operating_data(session, Path(tmp.name) / "exports", scope="templates")
            scoped_payload = json.loads(scoped.read_text(encoding="utf-8"))
            self.assertEqual(scoped_payload["scope"], "templates")
            self.assertIn("templates", scoped_payload)
            self.assertNotIn("products", scoped_payload)
            self.assertNotIn("tasks", scoped_payload)

    def test_phase4_posting_guides_completed_tasks_and_etsy_csv_import(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        csv_path = Path(tmp.name) / "etsy-listings.csv"
        csv_path.write_text(
            "Title,Listing ID,Listing URL,Status\n"
            "Imported Duck,12345,https://etsy.example/listing/12345,active\n",
            encoding="utf-8",
        )

        with session_scope(factory) as session:
            seed_database(session)
            guides = posting_guides(session)
            self.assertTrue(any(guide.name == "Instagram Reel" for guide in guides))

            imported = import_etsy_listing_csv(session, csv_path)
            self.assertEqual(len(imported), 1)
            self.assertEqual(imported[0].name, "Imported Duck")
            self.assertEqual(imported[0].external_source, "etsy_csv")
            self.assertEqual(imported[0].external_id, "12345")
            self.assertEqual(imported[0].canonical_url, "https://etsy.example/listing/12345")
            self.assertEqual(imported[0].staleness_state, "fresh")

            imported[0].manual_override_state = "locked"
            imported[0].manual_override_note = "Keep local status while testing imports."
            imported[0].status = "local custom"
            csv_path.write_text(
                "Title,Listing ID,Listing URL,Status\n"
                "Imported Duck,12345,https://etsy.example/listing/12345,inactive\n",
                encoding="utf-8",
            )
            imported_again = import_etsy_listing_csv(session, csv_path)
            self.assertEqual(imported_again[0].status, "local custom")
            self.assertEqual(imported_again[0].sync_status, "manual override")
            self.assertIn("manual override", imported_again[0].sync_error)

            health = data_health(session)
            self.assertTrue(any(item.area == "Manual Overrides" and item.count >= 1 for item in health))

            plan = ensure_default_plan(session, start_date=date(2026, 6, 17))
            task_id = plan.tasks[0].id
            complete_task_status(session, task_id, "complete", notes="Done.")
            completed = completed_tasks(session, role="all")
            self.assertTrue(any(model.task.id == task_id for model in completed))

    def test_phase5_planning_intent_generates_review_candidates_idempotently(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        with session_scope(factory) as session:
            seed_database(session)
            product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
            self.assertIsNotNone(product)
            item = create_planned_content_item(
                session,
                calendar_date=date(2026, 6, 25),
                destinations=["Facebook"],
                goals=["Bring craft fair shoppers back"],
                product_ids=[product.id],
                audience="gift buyers",
                occasion="new batch",
                notes="Keep it conversational.",
            )
            self.assertEqual(item.status, "waiting_content_generation")
            self.assertEqual(json.loads(item.destinations_json), ["Facebook"])
            self.assertEqual(json.loads(item.goals_json), ["Bring craft fair shoppers back"])
            self.assertEqual(len(planned_items_needing_production(session)), 1)

            result = produce_content_for_item(session, item)
            self.assertEqual(result.created, 0)
            self.assertEqual(item.status, "waiting_content_generation")
            self.assertEqual(item.brief_status, "ready")
            self.assertEqual(result.candidates, [])
            image_contracts = social_media_art_director_contracts(build_content_brief(session, item), count=3)
            self.assertEqual(len(image_contracts), 3)
            self.assertTrue(all(contract.skill_name == "social-media-art-director" for contract in image_contracts))
            self.assertTrue(all(contract.request["goal"] == "Bring craft fair shoppers back" for contract in image_contracts))
            self.assertTrue(all(contract.request["destination"] == "Facebook" for contract in image_contracts))
            self.assertEqual([contract.request["option_number"] for contract in image_contracts], [1, 2, 3])
            image_options = [image_option_from_contract(contract) for contract in image_contracts]
            self.assertTrue(all(option["skill_request"]["goal"] == "Bring craft fair shoppers back" for option in image_options))
            self.assertTrue(all("Magnific MCP primary" in option["provider_path"] for option in image_options))
            self.assertTrue(all(option["model_preference"] == "Google Nano Banana 2" for option in image_options))
            self.assertEqual(session.scalars(select(GeneratedContentCandidateRecord).where(GeneratedContentCandidateRecord.candidate_type == "image_option")).all(), [])
            self.assertEqual(session.scalars(select(GeneratedContentCandidateRecord).where(GeneratedContentCandidateRecord.candidate_type == "image_asset_option")).all(), [])
            self.assertEqual(session.scalars(select(GeneratedContentCandidateRecord).where(GeneratedContentCandidateRecord.candidate_type == "facebook_post")).all(), [])

    def test_phase5_image_contract_matches_reviewable_copy_story(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        with session_scope(factory) as session:
            seed_database(session)
            product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
            item = create_planned_content_item(
                session,
                calendar_date=date(2026, 6, 28),
                destinations=["Instagram"],
                goals=["Follower growth"],
                product_ids=[product.id],
                audience="Collectors / Flock Builders",
                occasion="Desk mascot moment",
            )
            register_generated_copy_candidate(
                session,
                item.id,
                "This duck looks like it has a lucky table and a tiny victory dance ready.\n\nGive the image a bingo-night desk moment, not a plain product shelf.\n\nFollow for more small ducks with big personality.",
                social_strategy={"story_move": "tiny_scene", "social_angle": "community_prompt"},
            )

            contracts = social_media_art_director_contracts(build_content_brief(session, item), count=1)
            option = image_option_from_contract(contracts[0])

            self.assertIn("Post story to match", option["prompt"])
            self.assertIn("lucky table", option["prompt"])
            self.assertIn("tiny_scene", option["prompt"])
            self.assertIn("post_visual_context", option["skill_request"])

    def test_phase5_planning_page_uses_social_strategy_options(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(Path(tmp) / "phase5-planning-options.sqlite", bootstrap_data=True)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            response = app.test_client().get("/planning")

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Cruise Duckers", response.data)
            self.assertIn(b"Collectors / Flock Builders", response.data)
            self.assertIn(b"Cruise duck community engagement", response.data)
            self.assertIn(b"Duck personality spotlight", response.data)
            self.assertIn(b"Cruise duck hiding", response.data)
            self.assertIn(b"Find your favorite duck in our Etsy shop", response.data)

    def test_phase5_copy_contract_uses_cruise_strategy_defaults(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        with session_scope(factory) as session:
            seed_database(session)
            product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Room Steward Duck"))
            self.assertIsNotNone(product)
            session.add(
                EtsyReviewRecord(
                    product_id=product.id,
                    external_source="etsy_api",
                    external_id="transaction:copy-contract-review",
                    shop_id="fixture-shop",
                    listing_id=product.external_id,
                    transaction_id="copy-contract-review",
                    buyer_user_id="buyer-hidden",
                    rating=5,
                    review="Perfect thank-you gift for our cruise room steward.",
                    language="en",
                    created_timestamp=1_783_123_200,
                )
            )
            session.add(
                EtsyReviewRecord(
                    product_id=product.id,
                    external_source="etsy_api",
                    external_id="transaction:copy-contract-negative-review",
                    shop_id="fixture-shop",
                    listing_id=product.external_id,
                    transaction_id="copy-contract-negative-review",
                    buyer_user_id="buyer-hidden-2",
                    rating=4,
                    review="It is soo small, it won't fit secure on my jeep dashboard.",
                    language="en",
                    created_timestamp=1_783_123_100,
                )
            )
            item = create_planned_content_item(
                session,
                calendar_date=date(2026, 6, 25),
                destinations=["Facebook"],
                goals=["Cruise community engagement"],
                product_ids=[product.id],
                audience="Cruise Duckers",
                occasion="Cruise duck hiding",
            )
            contract = copywriter_contract(build_content_brief(session, item), "Facebook")

            self.assertEqual(contract.skill_name, "social-media-copywriter")
            self.assertEqual(contract.request["workflow"][0]["skill"], "social-media-strategist")
            self.assertEqual(contract.request["audience"], "Cruise Duckers")
            self.assertEqual(contract.request["content_pillar"], "Cruise And Sharing")
            self.assertEqual(contract.request["social_angle"], "community_prompt")
            self.assertEqual(contract.request["cta_type"], "comment")
            self.assertIn("creative_directive", contract.request)
            self.assertIn("story_thesis", contract.request)
            self.assertIn("proof_points", contract.request)
            self.assertIn("review_context", contract.request)
            self.assertIn("missing_proof", contract.request)
            self.assertIn("story_moves", contract.request)
            self.assertIn("tiny moment", contract.request["creative_directive"])
            self.assertIn("using the supplied proof", contract.request["story_thesis"])
            self.assertEqual(contract.request["review_context"]["snippets"][0]["review"], "Perfect thank-you gift for our cruise room steward.")
            self.assertEqual(contract.request["review_context"]["cautions"][0]["social_use"], "caution")
            self.assertIn("Perfect thank-you gift for our cruise room steward.", " ".join(contract.request["proof_points"]))
            self.assertNotIn("won't fit secure", " ".join(contract.request["proof_points"]))
            self.assertEqual(
                contract.request["source_facts"]["review_context"]["snippets"][0]["product"],
                "Room Steward Duck",
            )
            self.assertTrue(any("community" in move.lower() or "conversation" in move.lower() for move in contract.request["story_moves"]))
            self.assertIn("Product-description-first body copy.", contract.request["avoid"])
            self.assertIn("Unsupported claims that the product is hot, viral, popular, or widely ordered.", contract.request["avoid"])

    def test_phase5_copy_contract_exposes_private_sales_context_with_safe_claims(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        with session_scope(factory) as session:
            seed_database(session)
            product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
            self.assertIsNotNone(product)
            session.add_all(
                [
                    ProductSalesRecord(
                        product_id=product.id,
                        source_name="etsy_sales_csv",
                        external_id="bingo-sale-1",
                        listing_id=product.external_id,
                        listing_title=product.name,
                        quantity=75,
                        revenue_cents=75000,
                        currency_code="USD",
                    ),
                    ProductSalesRecord(
                        product_id=product.id,
                        source_name="etsy_sales_csv",
                        external_id="bingo-sale-2",
                        listing_id=product.external_id,
                        listing_title=product.name,
                        quantity=50,
                        revenue_cents=50000,
                        currency_code="USD",
                    ),
                ]
            )
            item = create_planned_content_item(
                session,
                calendar_date=date(2026, 6, 26),
                destinations=["Facebook"],
                goals=["Etsy shop visits"],
                product_ids=[product.id],
                audience="Cruise Duckers",
                occasion="Gift idea",
            )
            contract = copywriter_contract(build_content_brief(session, item), "Facebook")

            sales_context = contract.request["sales_context"]
            self.assertIn("Do not reveal exact unit counts", sales_context["usage"])
            self.assertEqual(sales_context["products"][0]["internal_lifetime_quantity"], 125)
            self.assertIn("a repeat customer pick", sales_context["products"][0]["safe_public_claims"])
            self.assertIn("sales_context", contract.request["source_facts"])
            self.assertIn("Do not publish exact counts", " ".join(contract.request["proof_points"]))

    def test_phase5_social_copy_workflow_rejects_listing_summary_pattern(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        with session_scope(factory) as session:
            seed_database(session)
            product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
            item = create_planned_content_item(
                session,
                calendar_date=date(2026, 6, 27),
                destinations=["Instagram"],
                goals=["Follower growth"],
                product_ids=[product.id],
                audience="Collectors / Flock Builders",
                occasion="Desk mascot moment",
            )
            workflow = social_copy_workflow_contract(build_content_brief(session, item), "Instagram")

            writing_task = workflow["writing_request"]["input"]["task"]
            challenge_task = workflow["challenge_request"]["input"]["task"]
            strategy_task = workflow["strategy_request"]["input"]["task"]
            self.assertIn("review_context", strategy_task)
            self.assertIn("review_context", writing_task)
            self.assertIn("tiny story", writing_task)
            self.assertIn("product facts", writing_task)
            self.assertIn("hook + product description + CTA", challenge_task)
            self.assertIn("story_moves", workflow["writing_request"]["input"])
            self.assertIn("creative_directive", workflow["strategy_request"]["input"])

    def test_phase5_copy_contract_requests_proof_for_hot_product_story(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        with session_scope(factory) as session:
            seed_database(session)
            product = session.scalar(select(ProductRecord).where(ProductRecord.name.ilike("%Mailman Duck%")))
            item = create_planned_content_item(
                session,
                calendar_date=date(2026, 6, 29),
                destinations=["Facebook"],
                goals=["Follower growth"],
                product_ids=[product.id],
                audience="mail carriers and postal coworkers",
                occasion="postal worker appreciation",
                notes="Mail Duck took the world by storm and is hot with people appreciating carriers.",
            )
            contract = copywriter_contract(build_content_brief(session, item), "Facebook")

            self.assertIn("proof-led product story", " ".join(contract.request["story_moves"]).lower())
            self.assertIn("[MATT_TO_CONFIRM: order count or recent demand signal]", contract.request["missing_proof"])
            self.assertIn("[MATT_TO_CONFIRM: who is buying or requesting this product]", contract.request["missing_proof"])
            self.assertIn("Planning note demand signal", " ".join(contract.request["proof_points"]))

    def test_phase5_content_production_picks_up_rewrite_requests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "phase5-rewrite.sqlite"
            app = create_app(db_path, bootstrap_data=True)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
                item = create_planned_content_item(
                    session,
                    calendar_date=date(2026, 7, 1),
                    destinations=["Facebook"],
                    goals=["Sales growth"],
                    product_ids=[product.id],
                    audience="gift buyers",
                )
                produce_content_for_item(session, item)
                facebook = self.register_agent_copy(session, item)
                facebook.body = "stale draft that should be replaced"
                record_candidate_review(session, facebook.id, "rewrite_requested", "Too generic; make it warmer.", reviewed_by="Matt")
                item_id = item.id
                candidate_id = facebook.id

            dry_run = run_content_production_job(db_path=db_path, dry_run=True, export_briefs_dir=Path(tmp) / "briefs")
            self.assertEqual(len(dry_run["items"]), 1)
            self.assertEqual(dry_run["filters"]["dry_run"], True)
            self.assertEqual(dry_run["filters"]["export_briefs_dir"], str(Path(tmp) / "briefs"))
            brief_path = Path(dry_run["items"][0]["brief_export_path"])
            rewrite_brief = json.loads(brief_path.read_text(encoding="utf-8"))
            self.assertEqual(rewrite_brief["rewrite_requests"][0]["candidate_id"], candidate_id)
            self.assertEqual(rewrite_brief["rewrite_requests"][0]["revision_notes"], "Too generic; make it warmer.")
            self.assertEqual(rewrite_brief["rewrite_requests"][0]["previous_copy_text"], "stale draft that should be replaced")

            summary = run_content_production_job(db_path=db_path, export_briefs_dir=Path(tmp) / "briefs")
            self.assertEqual(summary["processed"], 1)
            self.assertEqual(summary["created"], 0)
            self.assertEqual(summary["filters"]["export_briefs_dir"], str(Path(tmp) / "briefs"))
            self.assertTrue(summary["items"][0]["rewrite_requested"])
            self.assertTrue(summary["items"][0]["forced"])

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                rewritten = session.get(GeneratedContentCandidateRecord, candidate_id)
                self.assertEqual(rewritten.review_state, "rewrite_requested")
                self.assertEqual(rewritten.body, "stale draft that should be replaced")
                item = session.get(PlannedContentRecord, item_id)
                self.assertEqual(item.status, "waiting_content_generation")
                self.assertIn(item_id, [item.id for item in planned_items_needing_production(session)])

    def test_phase5_content_production_runner(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        runner = repo_root / "scripts" / "run-content-production.sh"
        codex_runner = repo_root / "scripts" / "run-codex-content-automation.sh"
        weekly_runner = repo_root / "scripts" / "run-weekly-social-planner.sh"
        sales_import_runner = repo_root / "scripts" / "import-etsy-sales-csv.sh"
        weekly_codex_prompt = repo_root / "docs" / "operating-guides" / "codex-weekly-automation-prompt.md"

        self.assertTrue(runner.is_file())
        runner_text = runner.read_text(encoding="utf-8")
        self.assertIn("marketing_os.jobs.content_production", runner_text)
        self.assertIn("--days-ahead", runner_text)
        self.assertIn("MARKETING_OS_CONTENT_DAYS_AHEAD", runner_text)
        self.assertTrue(codex_runner.is_file())
        self.assertTrue(codex_runner.stat().st_mode & 0o111)
        codex_runner_text = codex_runner.read_text(encoding="utf-8")
        self.assertIn("marketing_os.jobs.content_automation", codex_runner_text)
        self.assertIn("MARKETING_OS_CODEX_AUTOMATION_DIR", codex_runner_text)
        self.assertIn("codex-content-automation.log", codex_runner_text)
        self.assertTrue(weekly_codex_prompt.is_file())
        weekly_codex_prompt_text = weekly_codex_prompt.read_text(encoding="utf-8")
        self.assertIn("$social-media-strategist", weekly_codex_prompt_text)
        self.assertIn("$social-media-copywriter", weekly_codex_prompt_text)
        self.assertIn("$social-media-copy-chief", weekly_codex_prompt_text)
        self.assertIn("$social-media-art-director", weekly_codex_prompt_text)
        self.assertIn("$video-content-planner", weekly_codex_prompt_text)
        self.assertIn("$video-editor", weekly_codex_prompt_text)
        self.assertIn("video-workflow.json", weekly_codex_prompt_text)
        self.assertTrue(weekly_runner.is_file())
        self.assertTrue(weekly_runner.stat().st_mode & 0o111)
        weekly_runner_text = weekly_runner.read_text(encoding="utf-8")
        self.assertIn("marketing_os.jobs.weekly_social_planner", weekly_runner_text)
        self.assertIn("weekly-social-planner.log", weekly_runner_text)
        self.assertTrue(sales_import_runner.is_file())
        self.assertTrue(sales_import_runner.stat().st_mode & 0o111)
        sales_import_runner_text = sales_import_runner.read_text(encoding="utf-8")
        self.assertIn("marketing_os.jobs.import_etsy_sales_csv", sales_import_runner_text)
        self.assertIn("etsy-sales-csv-import.log", sales_import_runner_text)

    def test_phase5_content_production_days_ahead_limits_nightly_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "phase5-days-ahead.sqlite"
            app = create_app(db_path, bootstrap_data=True)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)

            today = date.today()
            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
                near = create_planned_content_item(
                    session,
                    calendar_date=today + timedelta(days=7),
                    destinations=["Facebook"],
                    goals=["Sales growth"],
                    product_ids=[product.id],
                )
                far = create_planned_content_item(
                    session,
                    calendar_date=today + timedelta(days=30),
                    destinations=["Facebook"],
                    goals=["Sales growth"],
                    product_ids=[product.id],
                )
                near_id = near.id
                far_id = far.id

            dry_run = run_content_production_job(db_path=db_path, dry_run=True, days_ahead=14)
            item_ids = [item["planned_item"]["id"] for item in dry_run["items"]]
            self.assertEqual(dry_run["filters"]["days_ahead"], 14)
            self.assertEqual(dry_run["filters"]["target_date"], (today + timedelta(days=14)).isoformat())
            self.assertIn(near_id, item_ids)
            self.assertNotIn(far_id, item_ids)

    def test_phase5_register_generated_copy_candidate_from_agent_manifest(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        with session_scope(factory) as session:
            seed_database(session)
            product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
            item = create_planned_content_item(
                session,
                calendar_date=date(2026, 6, 25),
                destinations=["Facebook"],
                goals=["Engagement"],
                product_ids=[product.id],
                audience="gift buyers",
            )
            candidate = register_generated_copy_candidate(
                session,
                item.id,
                "Who needs Bingo Duck in their flock?\n\nThis tiny 3D printed duck is ready for a shelf, desk, or gift box.\n\nWho would you give this one to?",
                social_strategy={"skill": "social-media-strategist", "social_angle": "community_prompt"},
                social_challenge={"skill": "social-media-copy-chief", "status": "ready_for_human_review"},
            )

            self.assertEqual(candidate.candidate_type, "facebook_post")
            self.assertEqual(candidate.provider, "codex_agent")
            body = json.loads(candidate.body)
            self.assertEqual(body["skill"], "social-media-copywriter")
            self.assertEqual(body["social_strategy"]["skill"], "social-media-strategist")
            self.assertEqual(body["social_challenge"]["skill"], "social-media-copy-chief")
            self.assertEqual(body["hook"], "Who needs Bingo Duck in their flock?")
            self.assertEqual(body["body"], "This tiny 3D printed duck is ready for a shelf, desk, or gift box.")
            self.assertEqual(body["cta"], "Who would you give this one to?")
            self.assertNotIn("Who would you give this one to?", body["body"])
            self.assertEqual(item.status, "waiting_image_generation")

    def test_phase5_register_generated_copy_manifest_supports_options(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)
        db_path = Path(tmp.name) / "copy-options.sqlite"
        app = create_app(db_path)
        self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)

        with session_scope(app.config["SESSION_FACTORY"]) as session:
            seed_database(session)
            product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
            item = create_planned_content_item(
                session,
                calendar_date=date(2026, 6, 25),
                destinations=["Facebook"],
                goals=["Engagement"],
                product_ids=[product.id],
                audience="gift buyers",
            )
            item_id = item.id

        manifest_path = Path(tmp.name) / "register-copy-options.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "planned_item_id": item_id,
                    "provider": "codex_agent",
                    "copy_options": [
                        {
                            "copy_text": "Who gets the lucky duck?\n\nThis option starts a comment thread for Bingo Duck.\n\nTell us your bingo number.",
                            "social_strategy": {"selected_variant": "Engagement"},
                        },
                        {
                            "copy_text": "Bingo Duck gift idea\n\nThis option is written for shop clicks and gift consideration.\n\nFind your favorite duck in our Etsy shop.",
                            "social_strategy": {"selected_variant": "Shop-click"},
                        },
                    ],
                    "social_challenge": {"status": "ready_for_human_review"},
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        result = run_register_generated_copy_job(db_path=db_path, manifest_path=manifest_path)
        self.assertEqual(result["planned_item_id"], item_id)
        self.assertEqual(len(result["candidate_ids"]), 2)
        with session_scope(app.config["SESSION_FACTORY"]) as session:
            candidates = list(
                session.scalars(
                    select(GeneratedContentCandidateRecord)
                    .where(GeneratedContentCandidateRecord.planned_item_id == item_id)
                    .where(GeneratedContentCandidateRecord.candidate_type == "facebook_post")
                    .order_by(GeneratedContentCandidateRecord.provider)
                )
            )
            self.assertEqual([candidate.provider for candidate in candidates], ["codex_agent_option_1", "codex_agent_option_2"])
            self.assertTrue(all(candidate.review_state == "needs_review" for candidate in candidates))

    def test_phase5_planned_intent_creates_posting_task_from_current_copy(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        with session_scope(factory) as session:
            seed_database(session)
            ensure_default_plan(session, start_date=date(2026, 6, 17))
            product = session.scalar(select(ProductRecord).order_by(ProductRecord.name))
            item = create_planned_content_item(
                session,
                calendar_date=date(2026, 6, 27),
                destinations=["Facebook"],
                goals=["Sales growth"],
                product_ids=[product.id],
                audience="gift buyers",
                occasion="new batch",
            )
            produce_content_for_item(session, item)
            facebook = self.register_agent_copy(session, item)
            source_image = Path(tmp.name) / "selected-image.jpg"
            source_image.write_bytes(b"selected image bytes")
            image_candidate = register_uploaded_image_option(session, item.id, source_image, name="Selected post image")

            with self.assertRaisesRegex(ValueError, "Select an image"):
                create_task_from_planned_content(session, item.id, destination="Facebook", candidate_id=facebook.id)

            record_candidate_review(session, image_candidate.id, "approved", "Selected image.", reviewed_by="Matt")

            task_result = create_task_from_planned_content(session, item.id, destination="Facebook", candidate_id=facebook.id)

            self.assertEqual(task_result.task.planned_content_item_id, item.id)
            self.assertEqual(task_result.task.generated_content_candidate_id, facebook.id)
            self.assertEqual(task_result.task.asset_id, json.loads(image_candidate.body)["asset_id"])
            self.assertEqual(facebook.review_state, "approved")
            self.assertEqual(facebook.reviewed_by, "Planning")
            self.assertIsNotNone(facebook.reviewed_at)
            self.assertEqual(task_result.task.platform, "Facebook")
            self.assertEqual(task_result.task.content_type, "post")
            self.assertEqual(task_result.task.product_name, product.name)
            self.assertIn(product.name, task_result.task.draft_caption)
            self.assertEqual(item.status, "approved")

    def test_phase5_web_planning_api_and_job_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "phase5-web.sqlite"
            app = create_app(db_path, bootstrap_data=True)
            app.config["PLANNING_UPLOAD_ROOT"] = Path(tmp) / "planning-uploads"
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            client = app.test_client()

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                products = list(session.scalars(select(ProductRecord).order_by(ProductRecord.name).limit(2)))
                product_ids = [product.id for product in products]
                source_path = Path(tmp) / "planning-source.jpg"
                source_path.write_bytes(b"planning source image bytes")
                source = register_local_source_photo(session, source_path, product_id=products[0].id, name="Planning approved source")
                review_asset(session, source.id, "approved", "Planning source approved.")
                source_id = source.id

            planning_page = client.get("/planning")
            self.assertEqual(planning_page.status_code, 200)
            self.assertIn(b"Where should this post go", planning_page.data)
            self.assertIn(b"Destination and intent", planning_page.data)
            self.assertIn(b"What should it be about", planning_page.data)

            missing_reference_response = client.post(
                "/api/planned-content",
                json={
                    "calendar_date": "2026-06-26",
                    "destinations": ["Facebook"],
                    "goals": ["Sales growth"],
                    "product_ids": product_ids,
                    "audience": "repeat customers",
                    "notes": "Use a warm voice.",
                },
            )
            self.assertEqual(missing_reference_response.status_code, 400)
            self.assertIn("Select at least one product reference image", missing_reference_response.get_json()["error"])

            response = client.post(
                "/api/planned-content",
                json={
                    "calendar_date": "2026-06-26",
                    "scheduled_time": "14:30",
                    "destinations": ["Facebook"],
                    "goals": ["Sales growth"],
                    "product_ids": product_ids,
                    "selected_source_asset_ids": [source_id],
                    "audience": "repeat customers",
                    "notes": "Use a warm voice.",
                },
            )
            self.assertEqual(response.status_code, 201)
            created_item = response.get_json()["planned_item"]
            item_id = created_item["id"]
            self.assertEqual(created_item["status"], "waiting_content_generation")
            self.assertEqual(created_item["scheduled_time"], "14:30")
            self.assertTrue(created_item["waiting_for_generation"])

            produce_response = client.post(f"/api/planned-content/{item_id}/produce", json={})
            self.assertEqual(produce_response.status_code, 200)
            payload = produce_response.get_json()
            self.assertEqual(payload["created"], 0)
            self.assertEqual(payload["planned_item"]["status"], "waiting_content_generation")
            self.assertFalse(any(candidate["candidate_type"] == "facebook_post" for candidate in payload["planned_item"]["candidates"]))
            self.assertEqual(len(payload["planned_item"]["image_candidates"]), 0)

            rendered_review = client.get("/planning")
            self.assertEqual(rendered_review.status_code, 200)
            self.assertIn(b"<h3>Copy</h3>", rendered_review.data)
            self.assertIn(b"Waiting Content Generation", rendered_review.data)
            self.assertIn(b"<dt>Intent</dt>", rendered_review.data)
            self.assertIn(b"<dd>Sales growth</dd>", rendered_review.data)
            self.assertIn(b"<dt>Audience</dt>", rendered_review.data)
            self.assertIn(b"aria-label=\"Delete queued post\"", rendered_review.data)
            self.assertIn(b"class=\"warn icon-button\"", rendered_review.data)
            self.assertIn(b"class=\"image-upload-card\"", rendered_review.data)
            self.assertIn(b"Upload a finished visual", rendered_review.data)
            self.assertIn(b"Upload image option", rendered_review.data)
            self.assertNotIn(b"Waiting for generation", rendered_review.data)
            self.assertIn(b"class=\"text-link\" type=\"button\"", rendered_review.data)
            self.assertIn(b"Regenerate images", rendered_review.data)
            self.assertIn(b"Create posting task", rendered_review.data)
            self.assertIn(b"disabled title=\"A post can be created after fresh copy is ready and an image is selected.\"", rendered_review.data)
            self.assertNotIn(b"<div class=\"subtle\" style=\"margin-top: 6px;\">A post can be created", rendered_review.data)
            self.assertNotIn(b"Run queued copy generation now", rendered_review.data)
            self.assertNotIn(b"Review state", rendered_review.data)
            self.assertNotIn(b"Reviewed by", rendered_review.data)
            self.assertNotIn(b"Approved copy", rendered_review.data)
            self.assertIn(b'aria-label="Close image preview"', rendered_review.data)
            self.assertNotIn(b'data-image-modal-close>Close</button>', rendered_review.data)
            self.assertIn(b'typeof refreshIcons === "function"', rendered_review.data)

            upload_response = client.post(
                f"/planning/{item_id}/upload-image",
                data={
                    "image_file": (io.BytesIO(tiny_png_bytes("#22c55e")), "custom-post.jpg"),
                    "name": "Custom planned post image",
                    "notes": "Uploaded image test.",
                },
                content_type="multipart/form-data",
                follow_redirects=True,
            )
            self.assertEqual(upload_response.status_code, 200)
            self.assertIn(b"Custom planned post image", upload_response.data)
            self.assertIn(b"class=\"image-select-button\"", upload_response.data)
            self.assertIn(b"Select image: Custom planned post image", upload_response.data)
            self.assertIn(b"data-image-zoom-src", upload_response.data)
            self.assertIn(b'data-lucide="search"', upload_response.data)
            self.assertIn(b"data-image-modal", upload_response.data)
            with session_scope(app.config["SESSION_FACTORY"]) as session:
                item = session.get(PlannedContentRecord, item_id)
                image_candidate = next(candidate for candidate in item.candidates if candidate.candidate_type == "image_asset_option")
                image_candidate_id = image_candidate.id
                image_asset_id = json.loads(image_candidate.body)["asset_id"]
                asset = session.get(AssetRecord, image_asset_id)
                self.assertEqual(asset.review_state, "needs review")

            image_review_response = client.post(
                f"/api/generated-content/{image_candidate_id}/review",
                json={"review_state": "approved", "revision_notes": "Use this image.", "reviewed_by": "Matt"},
            )
            self.assertEqual(image_review_response.status_code, 200)
            with session_scope(app.config["SESSION_FACTORY"]) as session:
                asset = session.get(AssetRecord, image_asset_id)
                self.assertEqual(asset.review_state, "approved")
                self.assertEqual(asset.readiness_state, "ready to use")
                image_candidate = session.get(GeneratedContentCandidateRecord, image_candidate_id)
                self.assertEqual(image_candidate.review_state, "approved")

            planning_with_selected_image = client.get("/planning")
            self.assertEqual(planning_with_selected_image.status_code, 200)
            self.assertIn(b"Deselect image: Custom planned post image", planning_with_selected_image.data)

            deselect_response = client.post(
                f"/planning/candidates/{image_candidate_id}/review",
                data={"review_state": "needs_review", "revision_notes": "Deselected in test."},
                follow_redirects=True,
            )
            self.assertEqual(deselect_response.status_code, 200)
            self.assertIn(b"Select image: Custom planned post image", deselect_response.data)
            self.assertNotIn(b"Deselect image: Custom planned post image", deselect_response.data)
            with session_scope(app.config["SESSION_FACTORY"]) as session:
                asset = session.get(AssetRecord, image_asset_id)
                image_candidate = session.get(GeneratedContentCandidateRecord, image_candidate_id)
                self.assertEqual(asset.review_state, "needs review")
                self.assertEqual(asset.readiness_state, "needs human review")
                self.assertEqual(image_candidate.review_state, "needs_review")
                self.assertEqual(image_candidate.reviewed_by, "")
                self.assertIsNone(image_candidate.reviewed_at)

            calendar_page = client.get("/calendar")
            self.assertEqual(calendar_page.status_code, 200)
            self.assertIn(b"Planned Intent", calendar_page.data)
            self.assertIn(b"Review in Planning", calendar_page.data)
            self.assertIn(b"14:30", calendar_page.data)

            reschedule_response = client.post(
                f"/api/calendar/planned/{item_id}/reschedule",
                json={"calendar_date": "2026-06-28", "scheduled_time": "15:45"},
            )
            self.assertEqual(reschedule_response.status_code, 200)
            rescheduled_item = reschedule_response.get_json()["planned_item"]
            self.assertEqual(rescheduled_item["calendar_date"], "2026-06-28")
            self.assertEqual(rescheduled_item["scheduled_time"], "15:45")

            update_response = client.post(
                f"/calendar/planned/{item_id}/update",
                data={
                    "calendar_date": "2026-06-29",
                    "scheduled_time": "10:15",
                    "destinations": "Facebook",
                    "goals": "Sales growth",
                    "audience": "returning collectors",
                    "occasion": "Gift season",
                    "promotion": "Feature the flock story.",
                    "notes": "Updated from calendar drawer.",
                },
                follow_redirects=True,
            )
            self.assertEqual(update_response.status_code, 200)
            with session_scope(app.config["SESSION_FACTORY"]) as session:
                item = session.get(PlannedContentRecord, item_id)
                self.assertEqual(item.calendar_date, date(2026, 6, 29))
                self.assertEqual(item.scheduled_time, "10:15")
                self.assertEqual(item.audience, "returning collectors")
                self.assertEqual(item.notes, "Updated from calendar drawer.")

            second_response = client.post(f"/api/planned-content/{item_id}/produce", json={})
            self.assertEqual(second_response.status_code, 200)
            self.assertEqual(second_response.get_json()["created"], 0)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                item = session.get(PlannedContentRecord, item_id)
                candidate_id = self.register_agent_copy(session, item).id
                second_candidate = register_generated_copy_candidate(
                    session,
                    item.id,
                    f"{products[0].name} gift idea\n\nThis second copy option is more shop-click oriented.\n\nFind your favorite duck in our Etsy shop.",
                    social_strategy={"skill": "social-media-strategist", "selected_variant": "Shop-click"},
                    social_challenge={"skill": "social-media-copy-chief", "status": "ready_for_human_review"},
                    provider="codex_agent_option_2",
                )
                second_candidate_id = second_candidate.id
            edited_copy = (
                f"{products[0].name} is ready for a gift list.\n\n"
                "This edited Facebook draft keeps the warm MattMadeMe voice and mentions the product clearly.\n\n"
                "Tell me who would smile at this one."
            )
            edit_response = client.post(
                f"/planning/candidates/{candidate_id}/copy",
                data={"copy_text": edited_copy},
                follow_redirects=True,
            )
            self.assertEqual(edit_response.status_code, 200)
            self.assertIn(b"This edited Facebook draft", edit_response.data)
            self.assertIn(b'data-copy-options', edit_response.data)
            self.assertIn(b'class="copy-option-rail"', edit_response.data)
            self.assertIn(b'aria-pressed="true"', edit_response.data)
            self.assertIn(f'data-copy-candidate-id="{candidate_id}"'.encode(), edit_response.data)
            self.assertIn(f'data-copy-candidate-id="{second_candidate_id}"'.encode(), edit_response.data)
            self.assertIn(b'data-selected-copy-candidate', edit_response.data)

            rewrite_response = client.post(
                f"/planning/{item_id}/regenerate",
                data={"target": "copy", "feedback": "Make it warmer and shorter."},
                follow_redirects=True,
            )
            self.assertEqual(rewrite_response.status_code, 200)
            self.assertIn(b"data-show-panel=\"copy-", rewrite_response.data)
            self.assertIn(b"class=\"secondary icon-button\"", rewrite_response.data)
            self.assertIn(b"aria-label=\"Edit copy\"", rewrite_response.data)
            self.assertIn(b"aria-label=\"Rewrite copy\"", rewrite_response.data)
            self.assertIn(b"disabled", rewrite_response.data)
            with session_scope(app.config["SESSION_FACTORY"]) as session:
                item = session.get(PlannedContentRecord, item_id)
                self.assertEqual(item.status, "waiting_copy_regeneration")
                candidate = session.get(GeneratedContentCandidateRecord, candidate_id)
                self.assertEqual(candidate.revision_notes, "Make it warmer and shorter.")

            produce_again = client.post(f"/api/planned-content/{item_id}/produce", json={})
            self.assertEqual(produce_again.status_code, 200)

            review_response = client.post(
                f"/api/generated-content/{candidate_id}/review",
                json={
                    "review_state": "approved",
                    "revision_notes": "Ready for posting test after edit.",
                    "reviewed_by": "Matt",
                    "copy_text": edited_copy,
                },
            )
            self.assertEqual(review_response.status_code, 200)
            self.assertEqual(review_response.get_json()["candidate"]["review_state"], "approved")
            self.assertEqual(review_response.get_json()["candidate"]["copy_text"], edited_copy)
            self.assertEqual(review_response.get_json()["candidate"]["reviewed_by"], "Matt")
            self.assertIsNotNone(review_response.get_json()["candidate"]["reviewed_at"])

            reselect_image_response = client.post(
                f"/planning/candidates/{image_candidate_id}/review",
                data={"review_state": "approved", "revision_notes": "Selected again for task creation.", "reviewed_by": "Matt"},
                follow_redirects=True,
            )
            self.assertEqual(reselect_image_response.status_code, 200)
            with session_scope(app.config["SESSION_FACTORY"]) as session:
                image_candidate = session.get(GeneratedContentCandidateRecord, image_candidate_id)
                self.assertEqual(image_candidate.review_state, "approved")

            task_response = client.post(
                f"/api/planned-content/{item_id}/task",
                json={"destination": "Facebook", "candidate_id": candidate_id},
            )
            self.assertEqual(task_response.status_code, 201)
            task_payload = task_response.get_json()["task"]
            self.assertEqual(task_payload["platform"], "Facebook")
            self.assertEqual(task_payload["planned_content_item_id"], item_id)
            self.assertEqual(task_payload["generated_content_candidate_id"], candidate_id)
            with session_scope(app.config["SESSION_FACTORY"]) as session:
                task = session.get(TaskRecord, task_payload["id"])
                self.assertIn("This edited Facebook draft", task.draft_caption)
                self.assertNotIn("Quality checklist", task.draft_caption)
                self.assertEqual(task.due_date, date(2026, 6, 29))
                self.assertEqual(task.scheduled_time, "10:15")

            task_reschedule_response = client.post(
                f"/api/calendar/tasks/{task_payload['id']}/reschedule",
                json={"calendar_date": "2026-06-30", "scheduled_time": "16:05"},
            )
            self.assertEqual(task_reschedule_response.status_code, 200)
            self.assertEqual(task_reschedule_response.get_json()["task"]["due_date"], "2026-06-30")
            self.assertEqual(task_reschedule_response.get_json()["task"]["scheduled_time"], "16:05")
            with session_scope(app.config["SESSION_FACTORY"]) as session:
                task = session.get(TaskRecord, task_payload["id"])
                item = session.get(PlannedContentRecord, item_id)
                self.assertEqual(task.due_date, date(2026, 6, 30))
                self.assertEqual(task.scheduled_time, "16:05")
                self.assertEqual(item.calendar_date, date(2026, 6, 30))
                self.assertEqual(item.scheduled_time, "16:05")

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                item = session.get(PlannedContentRecord, item_id)
                item.status = "waiting_content_generation"

            summary = run_content_production_job(db_path=db_path, planned_item_id=item_id)
            self.assertEqual(summary["processed"], 1)
            self.assertEqual(summary["created"], 0)
            self.assertEqual(summary["filters"]["planned_item_id"], item_id)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                target = export_operating_data(session, Path(tmp) / "exports")
                export_payload = json.loads(target.read_text(encoding="utf-8"))
                self.assertEqual(len(export_payload["planned_content_items"]), 1)
                self.assertEqual(len(export_payload["generated_content_candidates"]), 3)
                reviewed_candidate = next(record for record in export_payload["generated_content_candidates"] if record["id"] == candidate_id)
                self.assertEqual(reviewed_candidate["reviewed_by"], "Matt")
                self.assertIsNotNone(reviewed_candidate["reviewed_at"])
                planned_task = next(record for record in export_payload["tasks"] if record["planned_content_item_id"] == item_id)
                self.assertEqual(planned_task["generated_content_candidate_id"], candidate_id)

    def test_calendar_delete_removes_planned_item_from_schedule(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "calendar-delete.sqlite"
            app = create_app(db_path, bootstrap_data=True)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            client = app.test_client()

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
                source_path = Path(tmp) / "calendar-delete-source.jpg"
                source_path.write_bytes(b"calendar source image bytes")
                source = register_local_source_photo(session, source_path, product_id=product.id, name="Calendar delete source")
                review_asset(session, source.id, "approved", "Calendar delete source approved.")
                product_id = product.id
                source_id = source.id

            response = client.post(
                "/api/planned-content",
                json={
                    "calendar_date": "2026-07-03",
                    "scheduled_time": "11:20",
                    "destinations": ["Instagram"],
                    "goals": ["Engagement"],
                    "product_ids": [product_id],
                    "selected_source_asset_ids": [source_id],
                    "notes": "Delete from calendar test.",
                },
            )
            self.assertEqual(response.status_code, 201)
            item_id = response.get_json()["planned_item"]["id"]

            delete_response = client.post(f"/calendar/planned/{item_id}/delete", follow_redirects=True)
            self.assertEqual(delete_response.status_code, 200)
            self.assertIn(b"Scheduled post deleted.", delete_response.data)
            with session_scope(app.config["SESSION_FACTORY"]) as session:
                self.assertIsNone(session.get(PlannedContentRecord, item_id))

    def test_phase5_web_planning_remote_reference_images_download_on_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "phase5-remote-planning.sqlite"
            remote_path = Path(tmp) / "remote" / "bingo-etsy.jpg"
            remote_path.parent.mkdir(parents=True)
            remote_path.write_bytes(b"remote etsy planning image")
            app = create_app(db_path, bootstrap_data=True)
            app.config["ASSETS_ROOT"] = Path(tmp) / "assets" / "products"
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            client = app.test_client()

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
                remote_asset = AssetRecord(
                    product_id=product.id,
                    name="Bingo Etsy remote planning image",
                    asset_type="Etsy product photo",
                    source_path=remote_path.as_uri(),
                    preview_path=remote_path.as_uri(),
                    platform_suitability_json='["Etsy", "Facebook", "Instagram"]',
                    readiness_state="remote Etsy reference",
                    notes="Remote Etsy image reference.",
                    external_source="etsy",
                    external_id="remote-planning-bingo",
                    canonical_url=remote_path.as_uri(),
                    sync_status="imported",
                    staleness_state="fresh",
                    review_state="synced",
                    file_exists=0,
                )
                session.add(remote_asset)
                session.flush()
                product_id = product.id
                remote_asset_id = remote_asset.id

            planning_page = client.get("/planning")
            self.assertEqual(planning_page.status_code, 200)
            self.assertIn(b"Bingo Etsy remote planning image", planning_page.data)
            self.assertIn(remote_path.as_uri().encode(), planning_page.data)
            self.assertIn(f'aria-label="Bingo Etsy remote planning image"'.encode(), planning_page.data)

            missing_reference = client.post(
                "/planning",
                data={
                    "calendar_date": "2026-06-26",
                    "destinations": "Facebook",
                    "goals": "Sales growth",
                    "product_ids": str(product_id),
                    "audience": "gift buyers",
                },
                follow_redirects=False,
            )
            self.assertEqual(missing_reference.status_code, 302)
            self.assertTrue(missing_reference.headers["Location"].endswith("/planning?step=2"))

            missing_reference_page = client.get(missing_reference.headers["Location"])
            self.assertEqual(missing_reference_page.status_code, 200)
            self.assertIn(b'<div class="wizard-step brief-section-body active" data-step="2">', missing_reference_page.data)
            self.assertIn(b'<section class="brief-section active" data-step-section="2">', missing_reference_page.data)
            self.assertIn(b"Select at least one product reference image", missing_reference_page.data)

            queued = client.post(
                "/planning",
                data={
                    "calendar_date": "2026-06-26",
                    "destinations": "Facebook",
                    "goals": "Sales growth",
                    "product_ids": str(product_id),
                    "selected_source_asset_ids": str(remote_asset_id),
                    "audience": "gift buyers",
                    "notes": "Use the Etsy listing angle.",
                },
                follow_redirects=True,
            )
            self.assertEqual(queued.status_code, 200)
            self.assertIn(b"Post queued. Preparing selected remote image references in the background.", queued.data)

            item_id = None
            selected_ids = [remote_asset_id]
            for _ in range(30):
                with session_scope(app.config["SESSION_FACTORY"]) as session:
                    item = session.scalar(select(PlannedContentRecord).order_by(PlannedContentRecord.id.desc()))
                    item_id = item.id
                    selected_ids = json.loads(item.selected_source_asset_ids_json)
                    if item.status == "waiting_content_generation" and selected_ids != [remote_asset_id]:
                        break
                time.sleep(0.05)
            with session_scope(app.config["SESSION_FACTORY"]) as session:
                item = session.get(PlannedContentRecord, item_id)
                selected_ids = json.loads(item.selected_source_asset_ids_json)
                self.assertEqual(len(selected_ids), 1)
                self.assertNotEqual(selected_ids[0], remote_asset_id)
                local_asset = session.get(AssetRecord, selected_ids[0])
                self.assertTrue(local_asset.file_exists)
                self.assertEqual(local_asset.review_state, "approved")
                self.assertEqual(local_asset.source_asset_id, remote_asset_id)
                self.assertEqual(local_asset.canonical_url, remote_path.as_uri())
                self.assertTrue(Path(local_asset.source_path).exists())

    def test_hidden_remote_assets_are_excluded_from_post_generation_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "hidden-remote-reference.sqlite"
            remote_path = Path(tmp) / "remote" / "hidden-bingo-etsy.jpg"
            remote_path.parent.mkdir(parents=True)
            remote_path.write_bytes(b"remote etsy hidden planning image")
            app = create_app(db_path, bootstrap_data=True)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            client = app.test_client()

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
                hidden_asset = AssetRecord(
                    product_id=product.id,
                    name="Hidden Bingo Etsy remote image",
                    asset_type="Etsy product photo",
                    source_path=remote_path.as_uri(),
                    preview_path=remote_path.as_uri(),
                    platform_suitability_json='["Etsy", "Facebook", "Instagram"]',
                    readiness_state="remote Etsy reference",
                    notes="Remote Etsy image reference.",
                    external_source="etsy",
                    external_id="hidden-remote-planning-bingo",
                    canonical_url=remote_path.as_uri(),
                    sync_status="imported",
                    staleness_state="fresh",
                    review_state="synced",
                    file_exists=0,
                    default_reference=1,
                )
                session.add(hidden_asset)
                session.flush()
                product_id = product.id
                asset_id = hidden_asset.id

                set_asset_generation_visibility(session, asset_id, True, "Bad crop for generated posts.")
                self.assertEqual(hidden_asset.hidden_from_generation, 1)
                self.assertEqual(hidden_asset.default_reference, 0)
                self.assertEqual(hidden_asset.manual_override_state, "hidden")

                default_ids = default_reference_asset_ids_for_products(session, [product])
                self.assertNotIn(asset_id, default_ids)

                with self.assertRaisesRegex(ValueError, "hidden from automation"):
                    create_planned_content_item(
                        session,
                        calendar_date=date(2026, 6, 26),
                        destinations=["Facebook"],
                        goals=["Sales growth"],
                        product_ids=[product_id],
                        selected_source_asset_ids=[asset_id],
                    )

            planning_page = client.get("/planning")
            self.assertEqual(planning_page.status_code, 200)
            self.assertNotIn(b"Hidden Bingo Etsy remote image", planning_page.data)

            assets_page = client.get("/assets")
            self.assertEqual(assets_page.status_code, 200)
            self.assertNotIn(b"Hidden Bingo Etsy remote image", assets_page.data)
            self.assertIn(b"Show hidden images", assets_page.data)

            assets_with_hidden = client.get("/assets?show_hidden=1")
            self.assertEqual(assets_with_hidden.status_code, 200)
            self.assertIn(b"Hidden Bingo Etsy remote image", assets_with_hidden.data)
            self.assertIn(b"Restore image for automation", assets_with_hidden.data)
            self.assertNotIn(b"Automation visibility", assets_with_hidden.data)

            products_page = client.get("/products")
            self.assertEqual(products_page.status_code, 200)
            self.assertNotIn(b"Hidden Bingo Etsy remote image", products_page.data)

            products_with_hidden = client.get("/products?show_hidden=1")
            self.assertEqual(products_with_hidden.status_code, 200)
            self.assertIn(b"Hidden Bingo Etsy remote image", products_with_hidden.data)
            self.assertIn(b"Hidden", products_with_hidden.data)
            self.assertIn(b"Restore image for automation", products_with_hidden.data)

            hidden_response = client.post(
                "/api/planned-content",
                json={
                    "calendar_date": "2026-06-26",
                    "destinations": ["Facebook"],
                    "goals": ["Sales growth"],
                    "product_ids": [product_id],
                    "selected_source_asset_ids": [asset_id],
                },
            )
            self.assertEqual(hidden_response.status_code, 400)
            self.assertIn("hidden from automation", hidden_response.get_json()["error"])

            restore_response = client.post(
                f"/assets/{asset_id}/visibility",
                data={"hidden": "0", "return_to": "/products"},
                follow_redirects=True,
            )
            self.assertEqual(restore_response.status_code, 200)
            with session_scope(app.config["SESSION_FACTORY"]) as session:
                restored = session.get(AssetRecord, asset_id)
                self.assertEqual(restored.hidden_from_generation, 0)

    def test_phase5_planned_item_auto_selects_two_automation_references_per_product(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "phase5-auto-reference-selection.sqlite"
            app = create_app(db_path, bootstrap_data=True)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
                source_paths = []
                for index in range(4):
                    source_path = tmp_path / f"bingo-source-{index}.jpg"
                    source_path.write_bytes(f"source {index}".encode("utf-8"))
                    source_paths.append(source_path)
                assets = [
                    register_local_source_photo(session, source_path, product_id=product.id, name=f"Bingo source {index}")
                    for index, source_path in enumerate(source_paths)
                ]
                for asset in assets:
                    review_asset(session, asset.id, "approved", "Approved for generation.")
                assets[0].default_reference = 1
                set_asset_generation_visibility(session, assets[3].id, True, "Do not use this crop.")
                default_asset_id = assets[0].id
                fallback_asset_ids = {assets[1].id, assets[2].id}
                hidden_asset_id = assets[3].id

                item = create_planned_content_item(
                    session,
                    calendar_date=date(2026, 6, 26),
                    destinations=["Facebook"],
                    goals=["Sales growth"],
                    product_ids=[product.id],
                )
                selected_ids = json.loads(item.selected_source_asset_ids_json)

            self.assertEqual(len(selected_ids), 2)
            self.assertEqual(selected_ids[0], default_asset_id)
            self.assertIn(selected_ids[1], fallback_asset_ids)
            self.assertNotIn(hidden_asset_id, selected_ids)

    def test_phase5_planned_item_random_selects_two_visible_references_without_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "phase5-auto-reference-random.sqlite"
            app = create_app(db_path, bootstrap_data=True)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
                source_paths = []
                for index in range(4):
                    source_path = tmp_path / f"bingo-random-{index}.jpg"
                    source_path.write_bytes(f"source {index}".encode("utf-8"))
                    source_paths.append(source_path)
                assets = [
                    register_local_source_photo(session, source_path, product_id=product.id, name=f"Bingo random source {index}")
                    for index, source_path in enumerate(source_paths)
                ]
                for asset in assets:
                    review_asset(session, asset.id, "approved", "Approved for generation.")
                set_asset_generation_visibility(session, assets[3].id, True, "Do not use this crop.")
                visible_ids = {asset.id for asset in assets[:3]}
                hidden_asset_id = assets[3].id

                item = create_planned_content_item(
                    session,
                    calendar_date=date(2026, 6, 27),
                    destinations=["Facebook"],
                    goals=["Sales growth"],
                    product_ids=[product.id],
                )
                selected_ids = json.loads(item.selected_source_asset_ids_json)

            self.assertEqual(len(selected_ids), 2)
            self.assertTrue(set(selected_ids).issubset(visible_ids))
            self.assertNotIn(hidden_asset_id, selected_ids)

    def test_phase5_planning_can_defer_remote_reference_download(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            remote_path = tmp_path / "remote" / "bingo-etsy.jpg"
            remote_path.parent.mkdir(parents=True)
            remote_path.write_bytes(b"remote etsy planning image")
            assets_root = tmp_path / "assets" / "products"
            app = create_app(tmp_path / "phase5-deferred-remote-planning.sqlite", bootstrap_data=True)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
                remote_asset = AssetRecord(
                    product_id=product.id,
                    name="Bingo Etsy remote planning image",
                    asset_type="Etsy product photo",
                    source_path=remote_path.as_uri(),
                    preview_path=remote_path.as_uri(),
                    platform_suitability_json='["Etsy", "Facebook", "Instagram"]',
                    readiness_state="remote Etsy reference",
                    notes="Remote Etsy image reference.",
                    external_source="etsy",
                    external_id="remote-planning-bingo",
                    canonical_url=remote_path.as_uri(),
                    sync_status="imported",
                    staleness_state="fresh",
                    review_state="synced",
                    file_exists=0,
                )
                session.add(remote_asset)
                session.flush()

                item = create_planned_content_item(
                    session,
                    calendar_date=date(2026, 6, 26),
                    destinations=["Facebook"],
                    goals=["Sales growth"],
                    product_ids=[product.id],
                    selected_source_asset_ids=[remote_asset.id],
                    assets_root=assets_root,
                    defer_remote_assets=True,
                    audience="gift buyers",
                )
                item_id = item.id
                remote_asset_id = remote_asset.id

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                item = session.get(PlannedContentRecord, item_id)
                self.assertEqual(item.status, "waiting_asset_download")
                self.assertEqual(json.loads(item.selected_source_asset_ids_json), [remote_asset_id])
                self.assertFalse(any(assets_root.rglob("*")))

                localize_planned_content_reference_assets(session, item_id, assets_root)
                selected_ids = json.loads(item.selected_source_asset_ids_json)
                self.assertEqual(len(selected_ids), 1)
                self.assertNotEqual(selected_ids[0], remote_asset_id)
                self.assertEqual(item.status, "waiting_content_generation")
                self.assertEqual(item.production_error, "")
                local_asset = session.get(AssetRecord, selected_ids[0])
                self.assertTrue(local_asset.file_exists)
                self.assertEqual(local_asset.review_state, "approved")
                self.assertEqual(local_asset.source_asset_id, remote_asset_id)
                self.assertEqual(local_asset.canonical_url, remote_path.as_uri())

    def test_phase5_content_automation_prepares_deferred_remote_reference_downloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "phase5-automation-remote-download.sqlite"
            remote_path = tmp_path / "remote" / "bingo-etsy.jpg"
            remote_path.parent.mkdir(parents=True)
            remote_path.write_bytes(b"remote etsy planning image")
            assets_root = tmp_path / "assets" / "products"
            app = create_app(db_path, bootstrap_data=True)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
                remote_asset = AssetRecord(
                    product_id=product.id,
                    name="Bingo automation remote planning image",
                    asset_type="Etsy product photo",
                    source_path=remote_path.as_uri(),
                    preview_path=remote_path.as_uri(),
                    platform_suitability_json='["Etsy", "Facebook", "Instagram"]',
                    readiness_state="remote Etsy reference",
                    notes="Remote Etsy image reference.",
                    external_source="etsy",
                    external_id="remote-automation-bingo",
                    canonical_url=remote_path.as_uri(),
                    sync_status="imported",
                    staleness_state="fresh",
                    review_state="synced",
                    file_exists=0,
                )
                session.add(remote_asset)
                session.flush()
                item = create_planned_content_item(
                    session,
                    calendar_date=date.today() + timedelta(days=2),
                    destinations=["Facebook"],
                    goals=["Sales growth"],
                    product_ids=[product.id],
                    selected_source_asset_ids=[remote_asset.id],
                    assets_root=assets_root,
                    defer_remote_assets=True,
                    audience="gift buyers",
                )
                item_id = item.id
                remote_asset_id = remote_asset.id

            summary = run_content_automation_job(
                db_path=db_path,
                output_dir=tmp_path / "content-automation",
                assets_root=assets_root,
                limit=10,
                days_ahead=14,
            )
            self.assertEqual(summary["asset_downloaded"], 1)
            self.assertEqual(summary["asset_download_errors"], [])

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                item = session.get(PlannedContentRecord, item_id)
                selected_ids = json.loads(item.selected_source_asset_ids_json)
                self.assertNotEqual(selected_ids, [remote_asset_id])
                self.assertIn(item.status, {"waiting_image_generation", "waiting_content_generation"})
                local_asset = session.get(AssetRecord, selected_ids[0])
                self.assertTrue(local_asset.file_exists)
                self.assertEqual(local_asset.review_state, "approved")
                self.assertEqual(local_asset.source_asset_id, remote_asset_id)

    def test_phase5_content_production_exports_structured_briefs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "phase5-briefs.sqlite"
            export_dir = Path(tmp) / "briefs"
            source_path = Path(tmp) / "bingo-source.jpg"
            source_path.write_bytes(b"source image bytes")
            app = create_app(db_path, bootstrap_data=True)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
                source = register_local_source_photo(session, source_path, product_id=product.id, name="Bingo approved source")
                review_asset(session, source.id, "approved", "Source approved for Codex brief.")
                item = create_planned_content_item(
                    session,
                    calendar_date=date(2026, 6, 30),
                    destinations=["Facebook"],
                    goals=["Sales growth"],
                    product_ids=[product.id],
                    audience="gift buyers",
                    notes="Use this for a Codex handoff test.",
                )
                item_id = item.id
                source_id = source.id

            dry_run = run_content_production_job(
                db_path=db_path,
                planned_item_id=item_id,
                dry_run=True,
                export_briefs_dir=export_dir,
            )
            self.assertEqual(dry_run["processed"], 0)
            self.assertEqual(len(dry_run["items"]), 1)
            self.assertEqual(dry_run["filters"]["planned_item_id"], item_id)
            self.assertEqual(dry_run["filters"]["dry_run"], True)
            self.assertEqual(dry_run["filters"]["export_briefs_dir"], str(export_dir))
            brief_path = Path(dry_run["items"][0]["brief_export_path"])
            self.assertEqual(brief_path, export_dir / f"planned-item-{item_id}-content-brief.json")
            self.assertTrue(brief_path.is_file())
            brief = json.loads(brief_path.read_text(encoding="utf-8"))
            self.assertEqual(brief["planned_item_id"], item_id)
            self.assertIn("Facebook", brief["destinations"])
            self.assertIn("Bingo Duck", brief["products"])
            self.assertEqual(brief["approved_source_asset_ids"], [source_id])
            self.assertEqual(brief["missing_inputs"], [])
            self.assertEqual(brief["source_assets"][0]["id"], source_id)
            self.assertEqual(brief["source_assets"][0]["review_state"], "approved")
            self.assertTrue(brief["source_assets"][0]["file_exists"])
            self.assertIn("performance_context", brief)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                self.assertEqual(len(list(session.scalars(select(GeneratedContentCandidateRecord)))), 0)

            live_run = run_content_production_job(
                db_path=db_path,
                planned_item_id=item_id,
                export_briefs_dir=export_dir,
            )
            self.assertEqual(live_run["processed"], 1)
            self.assertEqual(live_run["created"], 0)
            self.assertEqual(live_run["filters"]["planned_item_id"], item_id)
            self.assertEqual(live_run["filters"]["export_briefs_dir"], str(export_dir))
            self.assertEqual(Path(live_run["items"][0]["brief_export_path"]), brief_path)
            self.assertEqual(live_run["items"][0]["candidate_ids"], [])

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                candidates = list(session.scalars(select(GeneratedContentCandidateRecord)))
                self.assertEqual(len(candidates), 0)
                item = session.get(PlannedContentRecord, item_id)
                self.assertEqual(item.status, "waiting_content_generation")
                self.assertIn("Image generation is queued", item.production_error)
                self.assertIn("Copy generation is queued", item.production_error)

    def test_phase5_codex_content_automation_exports_and_registers_image_options(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "phase5-codex-automation.sqlite"
            app = create_app(db_path, bootstrap_data=True)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            output_dir = Path(tmp) / "content-automation"
            planning_upload_root = Path(tmp) / "planning-uploads"

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
                item = create_planned_content_item(
                    session,
                    calendar_date=date.today() + timedelta(days=2),
                    destinations=["Facebook"],
                    goals=["Bring craft fair shoppers back"],
                    product_ids=[product.id],
                    audience="gift buyers",
                    occasion="new batch",
                    notes="Keep it warm.",
                )
                item_id = item.id

            with patch.dict("os.environ", {"MARKETING_OS_PLANNING_UPLOAD_ROOT": planning_upload_root.as_posix()}):
                summary = run_content_automation_job(db_path=db_path, output_dir=output_dir, limit=10, days_ahead=14)
            self.assertEqual(summary["processed"], 1)
            self.assertNotIn("copy_created", summary)
            self.assertEqual(len(summary["copy_request_files"]), 1)
            self.assertEqual(len(summary["image_request_files"]), 0)
            copy_request_path = Path(summary["copy_request_files"][0])
            self.assertTrue(copy_request_path.is_file())
            copy_payload = json.loads(copy_request_path.read_text(encoding="utf-8"))
            self.assertEqual(copy_payload["planned_item_id"], item_id)
            self.assertEqual(copy_payload["workflow"]["workflow_name"], "social_media_strategy_writing_challenge")
            self.assertEqual(
                [step["skill"] for step in copy_payload["workflow"]["steps"]],
                ["social-media-strategist", "social-media-copywriter", "social-media-copy-chief"],
            )
            self.assertEqual(copy_payload["workflow"]["strategy_request"]["skill"], "social-media-strategist")
            self.assertEqual(copy_payload["workflow"]["writing_request"]["skill"], "social-media-copywriter")
            self.assertEqual(copy_payload["workflow"]["challenge_request"]["skill"], "social-media-copy-chief")

            copy_manifest = {
                "planned_item_id": item_id,
                "provider": "codex_agent",
                "copy_text": "Who needs Bingo Duck in their flock?\n\nThis duck looks like it has a lucky table, a favorite number, and a tiny victory dance ready to go.\n\nWho would you give this one to?",
                "skill_request": copy_payload["workflow"]["writing_request"]["input"],
                "skill_check": copy_payload["workflow"]["contract_check"],
                "social_strategy": {"skill": "social-media-strategist", "social_angle": "community_prompt", "story_move": "tiny_scene"},
                "social_challenge": {"skill": "social-media-copy-chief", "status": "ready_for_human_review"},
            }
            copy_manifest_path = copy_request_path.parent / "register-copy.json"
            copy_manifest_path.write_text(json.dumps(copy_manifest, indent=2), encoding="utf-8")
            copy_registered = run_register_generated_copy_job(db_path=db_path, manifest_path=copy_manifest_path)
            self.assertEqual(copy_registered["planned_item_id"], item_id)

            image_summary = run_content_automation_job(db_path=db_path, output_dir=output_dir, limit=10, days_ahead=14)
            self.assertEqual(len(image_summary["copy_request_files"]), 0)
            self.assertEqual(len(image_summary["image_request_files"]), 1)
            request_path = Path(image_summary["image_request_files"][0])
            self.assertTrue(request_path.is_file())
            request_payload = json.loads(request_path.read_text(encoding="utf-8"))
            self.assertEqual(request_payload["planned_item_id"], item_id)
            self.assertEqual(len(request_payload["options"]), 3)
            self.assertEqual([option["skill_request"]["option_number"] for option in request_payload["options"]], [1, 2, 3])
            self.assertIn("Post story to match", request_payload["options"][0]["prompt"])
            self.assertIn("lucky table", request_payload["options"][0]["prompt"])

            manifest = request_payload["registration_manifest_example"]
            for image in manifest["images"]:
                image_path = Path(tmp) / image["image_path"]
                image_path.parent.mkdir(parents=True, exist_ok=True)
                image_path.write_bytes(f"generated image {image['option_number']}".encode("utf-8"))
                image["image_path"] = image_path.as_posix()
            manifest_path = request_path.parent / "register-images.json"
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

            registered = run_register_generated_images_job(db_path=db_path, manifest_path=manifest_path)
            self.assertEqual(registered["planned_item_id"], item_id)
            self.assertEqual(registered["count"], 3)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                item = session.get(PlannedContentRecord, item_id)
                self.assertEqual(item.status, "needs_review")
                sync = session.scalar(select(SyncMetadata).where(SyncMetadata.source_name == "content_automation"))
                self.assertIsNotNone(sync)
                self.assertIn("image_request_files", sync.notes)
                health = data_health(session)
                automation_row = next(row for row in health if row.area == "Automation: Content Production")
                self.assertEqual(automation_row.status, "OK")
                self.assertIn("Last ran", automation_row.message)
                candidates = list(
                    session.scalars(
                        select(GeneratedContentCandidateRecord)
                        .where(GeneratedContentCandidateRecord.planned_item_id == item_id)
                        .where(GeneratedContentCandidateRecord.candidate_type == "image_asset_option")
                    )
                )
                self.assertEqual(len(candidates), 3)
                self.assertTrue(all(candidate.review_state == "needs_review" for candidate in candidates))
                asset_ids = [json.loads(candidate.body)["asset_id"] for candidate in candidates]
                assets = list(session.scalars(select(AssetRecord).where(AssetRecord.id.in_(asset_ids))))
                self.assertEqual(len(assets), 3)
                copy_candidates = list(
                    session.scalars(
                        select(GeneratedContentCandidateRecord)
                        .where(GeneratedContentCandidateRecord.planned_item_id == item_id)
                        .where(GeneratedContentCandidateRecord.candidate_type == "facebook_post")
                    )
                )
                self.assertEqual(len(copy_candidates), 1)
                self.assertTrue(all(asset.external_source == "magnific_mcp" for asset in assets))
                self.assertTrue(all(asset.review_state == "needs review" for asset in assets))

    def test_phase5_etsy_sales_csv_import_dedupes_weekly_exports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "phase5-sales-csv.sqlite"
            app = create_app(db_path, bootstrap_data=True)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            csv_path = Path(tmp) / "etsy-sales.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "Transaction ID,Listing ID,Item Name,Quantity,Price,Sale Date,Currency",
                        "tx-100,etsy-room-steward,Room Steward Duck,3,12.50,2026-06-18,USD",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            first = run_import_etsy_sales_csv_job(db_path=db_path, csv_path=csv_path)
            second = run_import_etsy_sales_csv_job(db_path=db_path, csv_path=csv_path)

            self.assertEqual(first["imported"], 1)
            self.assertEqual(first["updated"], 0)
            self.assertEqual(first["unmatched"], 0)
            self.assertEqual(second["imported"], 0)
            self.assertEqual(second["updated"], 1)
            with session_scope(app.config["SESSION_FACTORY"]) as session:
                rows = list(session.scalars(select(ProductSalesRecord)))
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0].quantity, 3)
                self.assertEqual(rows[0].revenue_cents, 1250)
                self.assertEqual(rows[0].product.name, "Room Steward Duck")

    def test_phase5_etsy_sold_order_items_csv_uses_item_total_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "phase5-etsy-sold-order-items.sqlite"
            app = create_app(db_path, bootstrap_data=True)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            csv_path = Path(tmp) / "EtsySoldOrderItems2025.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "Sale Date,Item Name,Buyer,Quantity,Price,Coupon Code,Coupon Details,Discount Amount,Shipping Discount,Order Shipping,Order Sales Tax,Item Total,Currency,Transaction ID,Listing ID,Date Paid,Date Shipped,Ship Name,Ship Address1,Ship Address2,Ship City,Ship State,Ship Zipcode,Ship Country,Order ID,Variations,Order Type,Listings Type,Payment Type,InPerson Discount,InPerson Location,VAT Paid by Buyer,SKU",
                        "12/31/25,Room Steward Duck: Cruise Ship Crew Gift,Example Buyer,2,8.99,,,0.00,0.00,5,0,17.98,USD,4899651532,4303896622,12/31/2025,01/01/2026,Example Buyer,123 Main St,,Orlando,FL,32808,United States,3936341005,\"Size:Medium - 2.5 inches\",online,listing,online_cc,,,0,",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            summary = run_import_etsy_sales_csv_job(db_path=db_path, csv_path=csv_path)

            self.assertEqual(summary["rows_seen"], 1)
            self.assertEqual(summary["imported"], 1)
            self.assertEqual(summary["skipped"], 0)
            with session_scope(app.config["SESSION_FACTORY"]) as session:
                sale = session.scalar(select(ProductSalesRecord).where(ProductSalesRecord.external_id == "4899651532"))
                self.assertIsNotNone(sale)
                self.assertEqual(sale.listing_id, "4303896622")
                self.assertEqual(sale.listing_title, "Room Steward Duck: Cruise Ship Crew Gift")
                self.assertEqual(sale.quantity, 2)
                self.assertEqual(sale.revenue_cents, 1798)
                self.assertEqual(sale.currency_code, "USD")
                self.assertEqual(sale.sold_at.date(), date(2025, 12, 31))
                self.assertEqual(sale.product.name, "Room Steward Duck")
                raw = json.loads(sale.raw_data_json)
                self.assertEqual(raw["Order ID"], "3936341005")
                self.assertEqual(raw["Variations"], "Size:Medium - 2.5 inches")

    def test_phase5_settings_uploads_etsy_sales_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "phase5-sales-upload.sqlite"
            app = create_app(db_path, bootstrap_data=True)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            client = app.test_client()
            settings = client.get("/settings")
            self.assertEqual(settings.status_code, 200)
            self.assertIn(b"data-etsy-order-items-form", settings.data)
            self.assertIn(b"data-etsy-order-items-modal", settings.data)
            self.assertIn(b"Importing Etsy order items", settings.data)
            self.assertIn(b"Keep this page open", settings.data)

            response = client.post(
                "/imports/etsy-sales-csv",
                data={
                    "sales_csv": (
                        io.BytesIO(
                            b"Transaction ID,Listing ID,Item Name,Quantity,Price,Sale Date,Currency\n"
                            b"tx-200,etsy-room-steward,Room Steward Duck,2,13.00,2026-06-19,USD\n"
                        ),
                        "sold-order-items.csv",
                    )
                },
                content_type="multipart/form-data",
                follow_redirects=True,
            )

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Import complete. Etsy order items CSV processed", response.data)
            self.assertIn(b"Sales signals are ready for planning.", response.data)
            self.assertIn(b"Data Health", response.data)
            with session_scope(app.config["SESSION_FACTORY"]) as session:
                sale = session.scalar(select(ProductSalesRecord).where(ProductSalesRecord.external_id == "tx-200"))
                self.assertIsNotNone(sale)
                self.assertEqual(sale.quantity, 2)
                self.assertEqual(sale.product.name, "Room Steward Duck")

    def test_phase5_weekly_social_planner_creates_review_queue_from_sales_mix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "phase5-weekly-social.sqlite"
            app = create_app(db_path, bootstrap_data=True)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            output_dir = Path(tmp) / "weekly-plans"
            csv_path = Path(tmp) / "etsy-sales.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "Transaction ID,Listing ID,Item Name,Quantity,Price,Sale Date,Currency",
                        "tx-100,etsy-room-steward,Room Steward Duck,4,12.50,2026-06-18,USD",
                        "tx-101,etsy-bingo,Bingo Duck,1,10.00,2026-06-18,USD",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            run_import_etsy_sales_csv_job(db_path=db_path, csv_path=csv_path)
            source_path = Path(tmp) / "room-steward-source.png"
            source_path.write_bytes(tiny_png_bytes("#facc15"))
            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Room Steward Duck"))
                source = register_local_source_photo(session, source_path, product_id=product.id, name="Room Steward default source")
                review_asset(session, source.id, "approved", "Default source approved.")
                source.default_reference = 1
                source_id = source.id

            summary = run_weekly_social_planner_job(
                db_path=db_path,
                week_start=date(2026, 6, 22),
                output_dir=output_dir,
                slots=7,
            )

            self.assertEqual(summary["created"], 7)
            self.assertEqual(summary["skipped"], 0)
            self.assertEqual(summary["sales_source"], "etsy_sales_csv")
            strategy_path = Path(summary["strategy_export_path"])
            self.assertTrue(strategy_path.is_file())
            payload = json.loads(strategy_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["workflow"][0], "social-media-strategist")
            self.assertEqual(payload["assignments"][0]["product"]["product_name"], "Room Steward Duck")
            self.assertTrue(any(item["product_bucket"] == "slow_boost" for item in payload["assignments"]))
            with session_scope(app.config["SESSION_FACTORY"]) as session:
                items = list(session.scalars(select(PlannedContentRecord).order_by(PlannedContentRecord.calendar_date)))
                self.assertEqual(len(items), 7)
                sync = session.scalar(select(SyncMetadata).where(SyncMetadata.source_name == "weekly_social_planner"))
                self.assertIsNotNone(sync)
                self.assertIn("week_start", sync.notes)
                health = data_health(session)
                automation_row = next(row for row in health if row.area == "Automation: Weekly Planner")
                self.assertEqual(automation_row.status, "OK")
                self.assertIn("Last ran", automation_row.message)
                destinations = [json_list(item.destinations_json)[0] for item in items]
                self.assertIn("Instagram", destinations)
                self.assertIn("Pinterest", destinations)
                scheduled_by_destination = {json_list(item.destinations_json)[0]: item.scheduled_time for item in items}
                self.assertEqual(scheduled_by_destination["Facebook"], "18:30")
                self.assertEqual(scheduled_by_destination["Instagram"], "12:30")
                self.assertEqual(scheduled_by_destination["Pinterest"], "20:30")
                first_item = items[0]
                self.assertEqual([int(value) for value in json_list(first_item.selected_source_asset_ids_json)], [source_id])
                self.assertTrue(all(item.status in {"waiting_image_generation", "waiting_content_generation"} for item in items))

            rerun = run_weekly_social_planner_job(
                db_path=db_path,
                week_start=date(2026, 6, 22),
                output_dir=output_dir,
                slots=7,
            )
            self.assertEqual(rerun["created"], 0)
            self.assertEqual(rerun["skipped"], 7)

    def test_phase5_weekly_social_planner_avoids_recently_featured_products_when_possible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "phase5-weekly-social-freshness.sqlite"
            app = create_app(db_path, bootstrap_data=True)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            output_dir = Path(tmp) / "weekly-plans"
            csv_path = Path(tmp) / "etsy-sales.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "Transaction ID,Listing ID,Item Name,Quantity,Price,Sale Date,Currency",
                        "tx-100,etsy-room-steward,Room Steward Duck,4,12.50,2026-06-18,USD",
                        "tx-101,etsy-bingo,Bingo Duck,2,10.00,2026-06-18,USD",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            run_import_etsy_sales_csv_job(db_path=db_path, csv_path=csv_path)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                room_steward = session.scalar(select(ProductRecord).where(ProductRecord.name == "Room Steward Duck"))
                recent = create_planned_content_item(
                    session,
                    calendar_date=date(2026, 6, 10),
                    destinations=["Facebook"],
                    goals=["Cruise community engagement"],
                    product_ids=[room_steward.id],
                )
                recent.status = "posted"

            summary = run_weekly_social_planner_job(
                db_path=db_path,
                week_start=date(2026, 6, 22),
                output_dir=output_dir,
                slots=1,
            )

            self.assertEqual(summary["created"], 1)
            payload = json.loads(Path(summary["strategy_export_path"]).read_text(encoding="utf-8"))
            self.assertEqual(payload["freshness_lookback_days"], 45)
            self.assertIn(room_steward.id, payload["recently_featured_product_ids"])
            self.assertEqual(payload["assignments"][0]["product"]["product_name"], "Bingo Duck")
            self.assertFalse(payload["assignments"][0]["recently_featured"])

    def test_phase5_learning_loop_links_generated_copy_to_outcomes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "phase5-learning.sqlite"
            app = create_app(db_path, bootstrap_data=True)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            client = app.test_client()

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                products = list(session.scalars(select(ProductRecord).order_by(ProductRecord.name).limit(1)))
                plan = ensure_default_plan(session, start_date=date(2026, 6, 17))
                task = plan.tasks[0]
                asset = session.scalar(select(AssetRecord).order_by(AssetRecord.id))
                task.platform = "Facebook"
                task.content_type = "post"
                task.product_name = products[0].name
                task.asset_id = asset.id if asset else None
                item = create_planned_content_item(
                    session,
                    calendar_date=date(2026, 6, 26),
                    destinations=["Facebook"],
                    goals=["Sales growth"],
                    product_ids=[products[0].id],
                    audience="gift buyers",
                )
                produce_content_for_item(session, item)
                facebook = self.register_agent_copy(session, item)
                record_candidate_review(session, facebook.id, "approved", "Approved for learning-loop test.", reviewed_by="Matt")
                link_generated_content_to_task(session, task.id, facebook.id)
                update_task_status(session, task.id, "posted", "Posted generated Facebook draft.")
                add_metric(
                    session,
                    task.id,
                    reach=420,
                    likes=34,
                    comments=8,
                    etsy_orders=1,
                    outcome_tags=["sold item", "got comments"],
                    notes="Sold item after a good comment thread.",
                )
                task_id = task.id
                candidate_id = facebook.id

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                summary = build_learning_summary(session)
                payload = serialize_learning_summary(summary)
                self.assertEqual(summary.metrics_count, 1)
                self.assertEqual(summary.linked_metric_count, 1)
                self.assertEqual(summary.generated_candidate_outcomes[0].candidate_id, candidate_id)
                self.assertEqual(summary.generated_candidate_outcomes[0].product_name, products[0].name)
                self.assertEqual(summary.generated_candidate_outcomes[0].asset_id, task.asset_id)
                self.assertIn("sold item", summary.generated_candidate_outcomes[0].outcome_tags)
                self.assertTrue(any("worked" in item for item in summary.what_worked))
                self.assertIn("top_channels", payload)

                health = data_health(session)
                self.assertTrue(any(row.area == "Learning Loop" for row in health))

                target = export_operating_data(session, Path(tmp) / "exports")
                export_payload = json.loads(target.read_text(encoding="utf-8"))
                task_export = next(record for record in export_payload["tasks"] if record["id"] == task_id)
                self.assertEqual(task_export["generated_content_candidate_id"], candidate_id)
                self.assertEqual(export_payload["metrics"][0]["outcome_tags"], ["sold item", "got comments"])
                self.assertEqual(export_payload["learning_summary"]["linked_metric_count"], 1)

            insights_response = client.get("/api/insights")
            self.assertEqual(insights_response.status_code, 200)
            self.assertEqual(insights_response.get_json()["summary"]["linked_metric_count"], 1)

            insights_page = client.get("/insights")
            self.assertEqual(insights_page.status_code, 200)
            self.assertIn(b"Generated Content Outcomes", insights_page.data)

            metric_response = client.post(
                f"/api/tasks/{task_id}/metrics",
                json={"reach": 5, "outcome_tags": ["no engagement"], "notes": "Second check was quiet."},
            )
            self.assertEqual(metric_response.status_code, 200)
            self.assertEqual(metric_response.get_json()["metric"]["outcome_tags"], ["no engagement"])

    def test_phase5_web_operator_workflow_posts_generated_copy_and_records_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "phase5-operator.sqlite"
            app = create_app(db_path, bootstrap_data=True)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            client = app.test_client()

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
                product_id = product.id
                source_path = Path(tmp) / "operator-source.jpg"
                source_path.write_bytes(b"operator source image bytes")
                source = register_local_source_photo(session, source_path, product_id=product.id, name="Operator approved source")
                review_asset(session, source.id, "approved", "Operator source approved.")
                source_id = source.id

            planned_response = client.post(
                "/api/planned-content",
                json={
                    "calendar_date": "2026-06-27",
                    "destinations": ["Facebook"],
                    "goals": ["Sales growth"],
                    "product_ids": [product_id],
                    "selected_source_asset_ids": [source_id],
                    "audience": "gift buyers",
                    "occasion": "new batch",
                    "notes": "Keep it conversational and specific.",
                },
            )
            self.assertEqual(planned_response.status_code, 201)
            item_id = planned_response.get_json()["planned_item"]["id"]

            production_response = client.post(f"/api/planned-content/{item_id}/produce", json={})
            self.assertEqual(production_response.status_code, 200)
            with session_scope(app.config["SESSION_FACTORY"]) as session:
                item = session.get(PlannedContentRecord, item_id)
                facebook = self.register_agent_copy(session, item)
                candidate_id = facebook.id

            missing_reviewer_response = client.post(
                f"/api/generated-content/{candidate_id}/review",
                json={"review_state": "approved", "revision_notes": "Approval without proof."},
            )
            self.assertEqual(missing_reviewer_response.status_code, 400)
            self.assertIn("reviewer", missing_reviewer_response.get_json()["error"])

            review_response = client.post(
                f"/api/generated-content/{candidate_id}/review",
                json={"review_state": "approved", "revision_notes": "Operator proof approval.", "reviewed_by": "Matt"},
            )
            self.assertEqual(review_response.status_code, 200)
            self.assertEqual(review_response.get_json()["candidate"]["reviewed_by"], "Matt")

            selected_image = Path(tmp) / "operator-selected-image.jpg"
            selected_image.write_bytes(b"operator selected image")
            with session_scope(app.config["SESSION_FACTORY"]) as session:
                image_candidate = register_uploaded_image_option(session, item_id, selected_image, name="Operator selected image")
                record_candidate_review(session, image_candidate.id, "approved", "Operator image approval.", reviewed_by="Matt")

            task_response = client.post(
                f"/api/planned-content/{item_id}/task",
                json={"destination": "Facebook", "candidate_id": candidate_id},
            )
            self.assertEqual(task_response.status_code, 201)
            task_payload = task_response.get_json()["task"]
            task_id = task_payload["id"]
            self.assertEqual(task_payload["planned_content_item_id"], item_id)
            self.assertEqual(task_payload["generated_content_candidate_id"], candidate_id)

            finish_response = client.post(
                f"/api/tasks/{task_id}/finish",
                json={"action": "mark_posted", "notes": "Operator proof marked posted.", "post_url": "https://facebook.example/mattmademe/proof"},
            )
            self.assertEqual(finish_response.status_code, 200)
            self.assertEqual(finish_response.get_json()["task"]["status"], "posted")

            metric_response = client.post(
                f"/api/tasks/{task_id}/metrics",
                json={
                    "post_url": "https://facebook.example/mattmademe/proof",
                    "reach": 420,
                    "likes": 34,
                    "comments": 8,
                    "etsy_orders": 1,
                    "outcome_tags": ["sold item", "got comments"],
                    "notes": "Operator proof outcome: comment thread and sale note recorded.",
                },
            )
            self.assertEqual(metric_response.status_code, 200)
            self.assertEqual(metric_response.get_json()["task"]["metric_status"], "complete")
            self.assertEqual(metric_response.get_json()["metric"]["outcome_tags"], ["sold item", "got comments"])

            insights_response = client.get("/api/insights")
            self.assertEqual(insights_response.status_code, 200)
            summary = insights_response.get_json()["summary"]
            self.assertEqual(summary["linked_metric_count"], 1)
            self.assertTrue(summary["what_worked"])
            self.assertEqual(summary["generated_candidate_outcomes"][0]["candidate_id"], candidate_id)
            self.assertEqual(summary["generated_candidate_outcomes"][0]["task_id"], task_id)

    def test_phase5_readiness_tracks_remaining_human_proof_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "phase5-readiness.sqlite"
            source_path = Path(tmp) / "source.jpg"
            output_path = Path(tmp) / "generated.jpg"
            source_path.write_bytes(b"source image bytes")
            output_path.write_bytes(b"generated image bytes")

            app = create_app(db_path, bootstrap_data=True)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            client = app.test_client()

            initial_response = client.get("/api/phase5-readiness")
            self.assertEqual(initial_response.status_code, 200)
            self.assertFalse(initial_response.get_json()["readiness"]["complete"])
            self.assertEqual(initial_response.get_json()["readiness"]["remaining_count"], 2)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
                source = register_local_source_photo(session, source_path, product_id=product.id, name="Readiness source")
                review_asset(session, source.id, "approved", "Source approved.")
                item = create_planned_content_item(
                    session,
                    calendar_date=date(2026, 6, 27),
                    destinations=["Facebook"],
                    goals=["Sales growth"],
                    product_ids=[product.id],
                    audience="gift buyers",
                )
                produce_content_for_item(session, item)
                facebook = self.register_agent_copy(session, item)
                record_candidate_review(session, facebook.id, "approved", "Matt approved copy.", reviewed_by="Matt")
                creative = import_manual_generated_output(
                    session,
                    source.id,
                    output_path,
                    target_format="Facebook post image",
                    prompt="Preserve product accuracy.",
                    provider="magnific_manual",
                    provider_job_id="readiness-job",
                )
                review_creative_generation_job(
                    session,
                    creative.job.id,
                    "approved",
                    review_notes="Matt approved generated output.",
                    reviewed_by="Matt",
                )

                readiness = build_phase5_readiness(session)
                payload = serialize_phase5_readiness(readiness)
                self.assertTrue(readiness.complete)
                self.assertEqual(payload["remaining_count"], 0)

            ready_response = client.get("/api/phase5-readiness")
            self.assertEqual(ready_response.status_code, 200)
            self.assertTrue(ready_response.get_json()["readiness"]["complete"])

            page = client.get("/phase5-readiness")
            self.assertEqual(page.status_code, 200)
            self.assertIn(b"Human-approved Facebook copy", page.data)
            self.assertIn(b"Human-approved generated creative", page.data)
            self.assertIn(b"Edit post copy", page.data)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                health = data_health(session)
                self.assertFalse(any(item.area == "Phase 5 Readiness" for item in health))

    def test_phase5_approval_packet_exports_copy_and_creative_review_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "phase5-approval-packet.sqlite"
            source_path = Path(tmp) / "source.jpg"
            output_path = Path(tmp) / "generated.jpg"
            source_path.write_bytes(b"source image bytes")
            output_path.write_bytes(b"generated image bytes")

            app = create_app(db_path, bootstrap_data=True)
            app.config["EXPORT_DIR"] = Path(tmp) / "exports"
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            client = app.test_client()

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
                source = register_local_source_photo(session, source_path, product_id=product.id, name="Packet source")
                review_asset(session, source.id, "approved", "Source approved.")
                item = create_planned_content_item(
                    session,
                    calendar_date=date(2026, 6, 28),
                    destinations=["Facebook"],
                    goals=["Sales growth"],
                    product_ids=[product.id],
                    audience="gift buyers",
                )
                produce_content_for_item(session, item)
                facebook = self.register_agent_copy(session, item)
                creative = import_manual_generated_output(
                    session,
                    source.id,
                    output_path,
                    target_format="Facebook post image",
                    prompt="Preserve product accuracy and make this ready for a Facebook post.",
                    provider="magnific_manual",
                    provider_job_id="packet-job",
                )

                packet = build_phase5_approval_packet(session)
                payload = serialize_phase5_approval_packet(packet)
                markdown = render_phase5_approval_packet_markdown(packet)
                target = write_phase5_approval_packet(session, app.config["EXPORT_DIR"])

                self.assertEqual(payload["readiness"]["remaining_count"], 2)
                creative_item = next(item for item in payload["readiness"]["items"] if item["key"] == "creative_generation_review")
                self.assertIn("waiting for human review", creative_item["message"])
                self.assertIn(f"Creative job #{creative.job.id}", creative_item["evidence"])
                self.assertIn("Open Assets", creative_item["action"])
                self.assertEqual(payload["copy_review"]["id"], facebook.id)
                self.assertIn("copy_text", payload["copy_review"])
                self.assertIn("Bingo Duck", payload["copy_review"]["copy_text"])
                self.assertNotIn("Quality checklist", payload["copy_review"]["copy_text"])
                self.assertEqual(payload["creative_review"]["id"], creative.job.id)
                self.assertEqual(payload["creative_review"]["source_asset"]["id"], source.id)
                self.assertEqual(payload["creative_review"]["source_asset"]["absolute_source_path"], source_path.resolve(strict=False).as_posix())
                self.assertEqual(payload["creative_review"]["candidate_asset"]["id"], creative.candidate.id)
                self.assertEqual(payload["creative_review"]["candidate_asset"]["absolute_source_path"], output_path.resolve(strict=False).as_posix())
                self.assertEqual(payload["creative_review"]["absolute_output_path"], output_path.resolve(strict=False).as_posix())
                self.assertIn("Human-approved Facebook copy", markdown)
                self.assertIn("Human-approved generated creative", markdown)
                self.assertIn("Final Proof Runbook", markdown)
                self.assertIn("/phase5-readiness#facebook-copy-review", markdown)
                self.assertIn(f"/assets#asset-{creative.candidate.id}", markdown)
                self.assertIn("phase5_readiness --fail-on-incomplete", markdown)
                self.assertIn("Open Planning, review a Facebook candidate", markdown)
                self.assertIn("Open Assets, compare the source and generated candidate", markdown)
                self.assertIn("Copyable Post", markdown)
                self.assertIn("Bingo Duck", markdown)
                self.assertIn("packet-job", markdown)
                self.assertIn("Creative Approval Checklist", markdown)
                self.assertIn("No invented markings", markdown)
                self.assertIn(source_path.as_posix(), markdown)
                self.assertIn(output_path.as_posix(), markdown)
                self.assertIn("Absolute source file", markdown)
                self.assertIn("Absolute candidate file", markdown)
                self.assertTrue(target.is_file())
                exported_markdown = target.read_text(encoding="utf-8")
                self.assertIn("Phase 5 Approval Packet", exported_markdown)
                self.assertIn("Creative Approval Checklist", exported_markdown)

            api_response = client.get("/api/phase5-approval-packet")
            self.assertEqual(api_response.status_code, 200)
            api_payload = api_response.get_json()["packet"]
            self.assertFalse(api_payload["readiness"]["complete"])
            self.assertEqual(api_payload["copy_review"]["candidate_type"], "facebook_post")
            self.assertEqual(api_payload["copy_review"]["review_path"], f"/planning#candidate-{facebook.id}")
            self.assertEqual(api_payload["creative_review"]["provider_job_id"], "packet-job")
            self.assertEqual(api_payload["creative_review"]["review_path"], f"/assets#asset-{creative.candidate.id}")

            page = client.get("/phase5-readiness")
            self.assertEqual(page.status_code, 200)
            self.assertIn(f'href="/planning#candidate-{facebook.id}"'.encode(), page.data)
            self.assertIn(f'href="/assets#asset-{creative.candidate.id}"'.encode(), page.data)
            self.assertIn(b"Generated candidate", page.data)
            self.assertIn(b"Creative approval checklist", page.data)
            self.assertIn(b"No invented markings", page.data)
            self.assertIn(b"Rewrite Requested", page.data)
            self.assertIn(b"Required when approving generated copy", page.data)
            self.assertIn(b"Required when approving generated creative", page.data)
            self.assertIn(f'src="/assets/{source.id}/preview"'.encode(), page.data)
            self.assertIn(f'src="/assets/{creative.candidate.id}/preview"'.encode(), page.data)
            self.assertIn(b'action="/phase5-readiness/copy-review"', page.data)
            self.assertIn(b'action="/phase5-readiness/creative-review"', page.data)

            planning_page = client.get("/planning")
            self.assertEqual(planning_page.status_code, 200)
            self.assertIn(f'id="candidate-{facebook.id}"'.encode(), planning_page.data)

            creative_page = client.get("/assets")
            self.assertEqual(creative_page.status_code, 200)
            self.assertIn(f'id="asset-{creative.candidate.id}"'.encode(), creative_page.data)
            self.assertIn(b"Packet source Facebook post image", creative_page.data)
            self.assertIn(b"generated graphic", creative_page.data)
            self.assertIn(b"needs review", creative_page.data)
            self.assertIn(f'src="/assets/{source.id}/preview"'.encode(), creative_page.data)
            self.assertIn(f'src="/assets/{creative.candidate.id}/preview"'.encode(), creative_page.data)

            copy_review_response = client.post(
                f"/planning/candidates/{facebook.id}/review",
                data={"review_state": "needs_review", "revision_notes": "Still checking.", "reviewed_by": ""},
                follow_redirects=False,
            )
            self.assertEqual(copy_review_response.status_code, 302)
            self.assertTrue(copy_review_response.headers["Location"].endswith(f"/planning#candidate-{facebook.id}"))

            readiness_copy_response = client.post(
                "/phase5-readiness/copy-review",
                data={
                    "candidate_id": str(facebook.id),
                    "review_state": "rewrite_requested",
                    "revision_notes": "Make it warmer and less salesy.",
                    "reviewed_by": "Matt",
                },
                follow_redirects=False,
            )
            self.assertEqual(readiness_copy_response.status_code, 302)
            rewrite_ready_response = client.get("/api/phase5-readiness")
            self.assertEqual(rewrite_ready_response.status_code, 200)
            rewrite_payload = rewrite_ready_response.get_json()["readiness"]
            rewrite_item = next(item for item in rewrite_payload["items"] if item["key"] == "facebook_copy_review")
            self.assertIn("waiting on a rewrite", rewrite_item["message"])
            self.assertIn("content_production --planned-item-id", rewrite_item["action"])

            readiness_copy_response = client.post(
                "/phase5-readiness/copy-review",
                data={
                    "candidate_id": str(facebook.id),
                    "review_state": "approved",
                    "revision_notes": "Matt approved the voice and facts.",
                    "reviewed_by": "Matt",
                },
                follow_redirects=False,
            )
            self.assertEqual(readiness_copy_response.status_code, 302)
            self.assertTrue(readiness_copy_response.headers["Location"].endswith("/phase5-readiness#facebook-copy-review"))

            readiness_creative_response = client.post(
                "/phase5-readiness/creative-review",
                data={
                    "job_id": str(creative.job.id),
                    "review_state": "approved",
                    "review_notes": "Matt approved product accuracy and composition.",
                    "reviewed_by": "Matt",
                },
                follow_redirects=False,
            )
            self.assertEqual(readiness_creative_response.status_code, 302)
            self.assertTrue(readiness_creative_response.headers["Location"].endswith("/phase5-readiness#generated-creative-review"))

            ready_response = client.get("/api/phase5-readiness")
            self.assertEqual(ready_response.status_code, 200)
            self.assertTrue(ready_response.get_json()["readiness"]["complete"])
            self.assertEqual(ready_response.get_json()["readiness"]["remaining_count"], 0)

            export_response = client.post("/phase5-readiness/export")
            self.assertEqual(export_response.status_code, 200)
            self.assertIn("text/markdown", export_response.content_type)
            self.assertIn(b"Phase 5 Approval Packet", export_response.data)
            self.assertIn(b"Final Actions", export_response.data)
            export_response.close()

    def test_phase5_readiness_surfaces_creative_handoff_when_no_job_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "phase5-creative-handoff.sqlite"
            source_path = Path(tmp) / "source.jpg"
            source_path.write_bytes(b"source image bytes")

            app = create_app(db_path, bootstrap_data=True)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            client = app.test_client()

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Mailman Duck"))
                source = register_local_source_photo(session, source_path, product_id=product.id, name="Mailman source")
                review_asset(session, source.id, "approved", "Source approved for creative handoff.")
                item = create_planned_content_item(
                    session,
                    calendar_date=date(2026, 6, 30),
                    destinations=["Facebook"],
                    goals=["Product awareness"],
                    product_ids=[product.id],
                    audience="postal worker gift buyers",
                    notes="Internal reviewer setup note.",
                )
                produce_content_for_item(session, item)
                source_id = source.id
                packet = build_phase5_approval_packet(session)
                approval_markdown = render_phase5_approval_packet_markdown(packet)
                markdown = render_phase5_creative_handoff_markdown(packet)
                export_path = write_phase5_creative_handoff(session, Path(tmp) / "exports")
                self.assertIn("Final Proof Runbook", approval_markdown)
                self.assertIn("--export-creative-handoff", approval_markdown)
                self.assertIn("Use Planning for post-specific image generation", approval_markdown)
                self.assertIn("Phase 5 Creative Handoff", markdown)
                self.assertIn("Mailman source", markdown)
                self.assertIn("Preserve the duck's shape", markdown)
                self.assertTrue(export_path.is_file())
                self.assertIn("Planning Review", export_path.read_text(encoding="utf-8"))

            api_response = client.get("/api/phase5-approval-packet")
            self.assertEqual(api_response.status_code, 200)
            packet = api_response.get_json()["packet"]
            self.assertIsNone(packet["creative_review"])
            self.assertIsNotNone(packet["creative_handoff"])
            self.assertEqual(packet["creative_handoff"]["source_asset"]["id"], source_id)
            self.assertEqual(packet["creative_handoff"]["source_asset"]["absolute_source_path"], source_path.resolve(strict=False).as_posix())
            self.assertIn("Mailman Duck", packet["creative_handoff"]["prompt"])
            self.assertIn("Preserve the duck's shape", packet["creative_handoff"]["prompt"])
            self.assertNotIn("Planning prompt context", packet["creative_handoff"]["prompt"])
            self.assertEqual(packet["creative_handoff"]["import_defaults"]["source_asset_id"], source_id)
            self.assertEqual(packet["creative_handoff"]["import_defaults"]["provider"], "image_generation")
            self.assertEqual(
                packet["creative_handoff"]["import_defaults"]["absolute_output_path"],
                (Path.cwd() / "outputs/generated/mailman-source-facebook-post-image.png").resolve(strict=False).as_posix(),
            )

            page = client.get("/phase5-readiness")
            self.assertEqual(page.status_code, 200)
            self.assertIn(b"Selected image option handoff", page.data)
            self.assertIn(b"Mailman Duck", page.data)
            self.assertIn(b"Open Planning", page.data)
            self.assertIn(f'src="/assets/{source_id}/preview"'.encode(), page.data)
            self.assertIn(b"Copy source path", page.data)
            self.assertIn(b"Copy absolute source path", page.data)
            self.assertIn(b"Copy output path", page.data)
            self.assertIn(b"Copy prompt", page.data)
            self.assertIn(b'action="/phase5-readiness/export-creative-handoff"', page.data)

            export_response = client.post("/phase5-readiness/export-creative-handoff")
            self.assertEqual(export_response.status_code, 200)
            self.assertIn("text/markdown", export_response.content_type)
            self.assertIn(b"Phase 5 Creative Handoff", export_response.data)
            self.assertIn(b"Mailman source", export_response.data)
            export_response.close()

    def test_phase5_readiness_job_reports_and_exports_packet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "phase5-readiness-job.sqlite"
            source_path = Path(tmp) / "source.jpg"
            output_path = Path(tmp) / "generated.jpg"
            export_dir = Path(tmp) / "exports"
            source_path.write_bytes(b"source image bytes")
            output_path.write_bytes(b"generated image bytes")

            app = create_app(db_path, bootstrap_data=True)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
                source = register_local_source_photo(session, source_path, product_id=product.id, name="Job source")
                review_asset(session, source.id, "approved", "Source approved.")
                item = create_planned_content_item(
                    session,
                    calendar_date=date(2026, 6, 29),
                    destinations=["Facebook"],
                    goals=["Sales growth"],
                    product_ids=[product.id],
                    audience="gift buyers",
                )
                produce_content_for_item(session, item)
                facebook = self.register_agent_copy(session, item)
                record_candidate_review(session, facebook.id, "approved", "Matt approved copy.", reviewed_by="Matt")
                creative = import_manual_generated_output(
                    session,
                    source.id,
                    output_path,
                    target_format="Facebook post image",
                    prompt="Preserve product accuracy.",
                    provider="magnific_manual",
                    provider_job_id="readiness-job-command",
                )
                review_creative_generation_job(
                    session,
                    creative.job.id,
                    "approved",
                    review_notes="Matt approved generated output.",
                    reviewed_by="Matt",
                )

            summary = run_phase5_readiness_job(db_path=db_path, export_dir=export_dir, export_markdown=True)
            self.assertTrue(summary["readiness"]["complete"])
            self.assertEqual(summary["readiness"]["remaining_count"], 0)
            self.assertEqual(summary["packet"]["copy_review"]["reviewed_by"], "Matt")
            self.assertEqual(summary["packet"]["creative_review"]["provider_job_id"], "readiness-job-command")
            export_path = Path(str(summary["export_path"]))
            self.assertTrue(export_path.is_file())
            self.assertEqual(export_path.parent, export_dir)
            self.assertIn("Phase 5 Approval Packet", export_path.read_text(encoding="utf-8"))

    def test_phase5_etsy_read_only_sync_imports_products_and_images(self) -> None:
        class FakeEtsyAdapter:
            def __init__(self):
                self.calls: list[tuple[str, str]] = []

            def list_active_shop_listings(self, shop_id: str) -> list[dict[str, object]]:
                self.calls.append(("GET listings", shop_id))
                return [
                    {
                        "listing_id": "etsy-100",
                        "title": "Fixture Duck &#39;Special&#39; &amp; Co",
                        "url": "https://etsy.example/listing/etsy-100",
                        "state": "active",
                        "description": (
                            "A fixture listing for sync tests &39;with escaped text&39;. "
                            + ("Full Etsy listing detail. " * 40)
                            + "Final untrimmed sentence."
                        ),
                        "tags": ["gift &amp; collector", "duck", "desk", "handmade", "small batch", "office", "funny", "collector shelf"],
                    }
                ]

            def get_listing_images(self, listing_id: str) -> list[dict[str, object]]:
                self.calls.append(("GET images", listing_id))
                return [
                    {
                        "listing_image_id": "img-100",
                        "url_fullxfull": "https://images.example/fixture-duck.jpg",
                        "url_75x75": "https://images.example/fixture-duck-thumb.jpg",
                    }
                ]

        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        with session_scope(factory) as session:
            adapter = FakeEtsyAdapter()
            config = EtsyConfig(keystring="fixture-key", shared_secret="fixture-secret", shop_id="fixture-shop")
            summary = sync_etsy_read_only(session, adapter=adapter, config=config)
            self.assertEqual(summary.products_imported, 1)
            self.assertEqual(summary.assets_imported, 1)
            self.assertEqual(adapter.calls, [("GET listings", "fixture-shop"), ("GET images", "etsy-100")])

            product = session.scalar(select(ProductRecord).where(ProductRecord.external_source == "etsy", ProductRecord.external_id == "etsy-100"))
            self.assertIsNotNone(product)
            self.assertEqual(product.name, "Fixture Duck 'Special' & Co")
            self.assertIn("'with escaped text'", product.sales_momentum_note)
            self.assertIn("Final untrimmed sentence.", product.sales_momentum_note)
            self.assertGreater(len(product.sales_momentum_note), 500)
            self.assertEqual(product.use_cases_json, "[]")
            self.assertEqual(product.canonical_url, "https://etsy.example/listing/etsy-100")
            self.assertEqual(product.sync_status, "imported")

            asset = session.scalar(select(AssetRecord).where(AssetRecord.external_source == "etsy", AssetRecord.external_id == "etsy-100:img-100"))
            self.assertIsNotNone(asset)
            self.assertEqual(asset.product_id, product.id)
            self.assertEqual(asset.review_state, "synced")
            self.assertEqual(asset.readiness_state, "remote Etsy reference")
            self.assertEqual(asset.file_exists, 0)

            sync = session.scalar(select(SyncMetadata).where(SyncMetadata.source_name == "etsy_api"))
            self.assertIsNotNone(sync)

    def test_phase5_etsy_sync_hydrates_capped_listing_descriptions_and_images(self) -> None:
        class FakeEtsyAdapter:
            def __init__(self):
                self.calls: list[tuple[str, str]] = []

            def list_active_shop_listings(self, shop_id: str) -> list[dict[str, object]]:
                self.calls.append(("GET listings", shop_id))
                return [
                    {
                        "listing_id": "etsy-500",
                        "title": "Hydrated Description Duck",
                        "url": "https://etsy.example/listing/etsy-500",
                        "description": "x" * 500,
                    }
                ]

            def get_listing(self, listing_id: str) -> dict[str, object]:
                self.calls.append(("GET listing", listing_id))
                return {
                    "listing_id": listing_id,
                    "title": "Hydrated Description Duck",
                    "url": "https://etsy.example/listing/etsy-500",
                    "description": ("Full Etsy description. " * 60).strip(),
                    "images": [
                        {
                            "listing_image_id": "img-rank-2",
                            "rank": 2,
                            "url_fullxfull": "https://images.example/rank-2.jpg",
                        },
                        {
                            "listing_image_id": "img-rank-1",
                            "rank": 1,
                            "url_fullxfull": "https://images.example/rank-1.jpg",
                        },
                    ],
                }

            def get_listing_images(self, listing_id: str) -> list[dict[str, object]]:
                raise AssertionError("Hydrated listing images should be used when present.")

        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        with session_scope(factory) as session:
            adapter = FakeEtsyAdapter()
            config = EtsyConfig(keystring="fixture-key", shared_secret="fixture-secret", shop_id="fixture-shop")
            summary = sync_etsy_read_only(session, adapter=adapter, config=config)

            self.assertEqual(summary.products_imported, 1)
            self.assertEqual(summary.assets_imported, 2)
            self.assertEqual(adapter.calls, [("GET listings", "fixture-shop"), ("GET listing", "etsy-500")])
            product = session.scalar(select(ProductRecord).where(ProductRecord.external_id == "etsy-500"))
            self.assertIsNotNone(product)
            self.assertGreater(len(product.sales_momentum_note), 500)
            assets = list(session.scalars(select(AssetRecord).where(AssetRecord.product_id == product.id).order_by(AssetRecord.id)))
            self.assertEqual([asset.external_id for asset in assets], ["etsy-500:img-rank-1", "etsy-500:img-rank-2"])

    def test_phase5_etsy_sync_imports_reviews_for_social_proof(self) -> None:
        class FakeEtsyAdapter:
            def __init__(self):
                self.calls: list[tuple[str, str]] = []

            def list_active_shop_listings(self, shop_id: str) -> list[dict[str, object]]:
                self.calls.append(("GET listings", shop_id))
                return [
                    {
                        "listing_id": "etsy-review-1",
                        "title": "Review Proof Duck",
                        "url": "https://etsy.example/listing/etsy-review-1",
                        "description": "A duck with useful review proof.",
                    }
                ]

            def get_listing_images(self, listing_id: str) -> list[dict[str, object]]:
                self.calls.append(("GET images", listing_id))
                return []

            def get_reviews_by_shop(self, shop_id: str) -> list[dict[str, object]]:
                self.calls.append(("GET reviews", shop_id))
                return [
                    {
                        "shop_id": shop_id,
                        "listing_id": "etsy-review-1",
                        "transaction_id": "txn-1",
                        "buyer_user_id": "buyer-hidden-in-copy",
                        "rating": 5,
                        "review": "Perfect tiny gift for our cruise group.",
                        "language": "en",
                        "image_url_fullxfull": "https://images.example/review.jpg",
                        "created_timestamp": 1782000000,
                        "updated_timestamp": 1782000100,
                    }
                ]

        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        with session_scope(factory) as session:
            adapter = FakeEtsyAdapter()
            config = EtsyConfig(keystring="fixture-key", shared_secret="fixture-secret", shop_id="fixture-shop")
            summary = sync_etsy_read_only(session, adapter=adapter, config=config)
            second_summary = sync_etsy_read_only(session, adapter=adapter, config=config)

            self.assertEqual(summary.products_imported, 1)
            self.assertEqual(summary.reviews_imported, 1)
            self.assertEqual(second_summary.reviews_imported, 1)
            self.assertEqual(session.scalar(select(func.count()).select_from(EtsyReviewRecord)), 1)
            product = session.scalar(select(ProductRecord).where(ProductRecord.external_id == "etsy-review-1"))
            self.assertIsNotNone(product)
            review = session.scalar(select(EtsyReviewRecord))
            self.assertIsNotNone(review)
            self.assertEqual(review.product_id, product.id)
            self.assertEqual(review.external_id, "transaction:txn-1")
            self.assertEqual(review.rating, 5)
            self.assertEqual(review.review, "Perfect tiny gift for our cruise group.")
            self.assertEqual(review.image_url_fullxfull, "https://images.example/review.jpg")

            item = create_planned_content_item(
                session,
                calendar_date=date(2026, 6, 30),
                destinations=["Facebook"],
                goals=["Engagement"],
                product_ids=[product.id],
            )
            brief = build_content_brief(session, item)
            self.assertEqual(brief["product_facts"][0]["etsy_reviews"][0]["review"], "Perfect tiny gift for our cruise group.")

    def test_phase5_etsy_sync_keeps_shared_images_linked_to_each_listing(self) -> None:
        class FakeEtsyAdapter:
            def list_active_shop_listings(self, shop_id: str) -> list[dict[str, object]]:
                return [
                    {
                        "listing_id": "etsy-one",
                        "title": "First Shared Image Duck",
                        "url": "https://etsy.example/listing/etsy-one",
                        "description": "First listing.",
                    },
                    {
                        "listing_id": "etsy-two",
                        "title": "Second Shared Image Duck",
                        "url": "https://etsy.example/listing/etsy-two",
                        "description": "Second listing.",
                    },
                ]

            def get_listing_images(self, listing_id: str) -> list[dict[str, object]]:
                return [
                    {
                        "listing_image_id": "shared-image",
                        "rank": 1,
                        "url_fullxfull": "https://images.example/shared.jpg",
                    },
                    {
                        "listing_image_id": f"{listing_id}-unique",
                        "rank": 2,
                        "url_fullxfull": f"https://images.example/{listing_id}.jpg",
                    },
                ]

        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        with session_scope(factory) as session:
            config = EtsyConfig(keystring="fixture-key", shared_secret="fixture-secret", shop_id="fixture-shop")
            summary = sync_etsy_read_only(session, adapter=FakeEtsyAdapter(), config=config)

            self.assertEqual(summary.products_imported, 2)
            self.assertEqual(summary.assets_imported, 4)
            first = session.scalar(select(ProductRecord).where(ProductRecord.external_id == "etsy-one"))
            second = session.scalar(select(ProductRecord).where(ProductRecord.external_id == "etsy-two"))
            self.assertIsNotNone(first)
            self.assertIsNotNone(second)
            first_assets = list(session.scalars(select(AssetRecord).where(AssetRecord.product_id == first.id).order_by(AssetRecord.external_id)))
            second_assets = list(session.scalars(select(AssetRecord).where(AssetRecord.product_id == second.id).order_by(AssetRecord.external_id)))
            self.assertEqual([asset.external_id for asset in first_assets], ["etsy-one:etsy-one-unique", "etsy-one:shared-image"])
            self.assertEqual([asset.external_id for asset in second_assets], ["etsy-two:etsy-two-unique", "etsy-two:shared-image"])

    def test_phase5_etsy_read_only_sync_preserves_local_product_tags(self) -> None:
        class FakeEtsyAdapter:
            def list_active_shop_listings(self, shop_id: str) -> list[dict[str, object]]:
                return [
                    {
                        "listing_id": "etsy-100",
                        "title": "Tagged Local Duck",
                        "url": "https://etsy.example/listing/etsy-100",
                        "description": "Updated Etsy listing description.",
                        "tags": ["etsy gift", "etsy collector"],
                    }
                ]

            def get_listing_images(self, listing_id: str) -> list[dict[str, object]]:
                return []

        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        with session_scope(factory) as session:
            product = ProductRecord(
                name="Tagged Local Duck",
                secondary_audiences_json="[]",
                best_channels_json="[]",
                use_cases_json=json.dumps(["local planning", "desk display"]),
                seasonality_json="[]",
                external_source="etsy",
                external_id="etsy-100",
                canonical_url="https://etsy.example/listing/etsy-100",
            )
            session.add(product)
            session.flush()

            config = EtsyConfig(keystring="fixture-key", shared_secret="fixture-secret", shop_id="fixture-shop")
            summary = sync_etsy_read_only(session, adapter=FakeEtsyAdapter(), config=config)

            self.assertEqual(summary.products_imported, 1)
            self.assertEqual(json_list(product.use_cases_json), ["local planning", "desk display"])
            sync = session.scalar(select(SyncMetadata).where(SyncMetadata.source_name == "etsy_api"))
            self.assertIsNotNone(sync)
            self.assertIn("Imported 1 listing", sync.notes)

            health = data_health(session)
            self.assertFalse(any(item.area == "Asset Review" and item.count for item in health))
            self.assertTrue(any(item.area == "Etsy Sync" and item.status == "OK" for item in health))

    def test_phase5_etsy_sync_recovers_from_wrong_shop_id_with_shop_name(self) -> None:
        from urllib.error import HTTPError

        class FakeEtsyAdapter:
            def __init__(self):
                self.calls: list[tuple[str, str]] = []

            def find_shop_id_by_name(self, shop_name: str) -> str | None:
                self.calls.append(("find shop", shop_name))
                return "fixture-shop"

            def list_active_shop_listings(self, shop_id: str) -> list[dict[str, object]]:
                self.calls.append(("GET listings", shop_id))
                if shop_id == "wrong-shop":
                    raise HTTPError("https://etsy.example", 404, "Not Found", {}, io.BytesIO(b'{"error":"not found"}'))
                return [
                    {
                        "listing_id": "etsy-100",
                        "title": "Fixture Duck",
                        "url": "https://etsy.example/listing/etsy-100",
                        "state": "active",
                    }
                ]

            def get_listing_images(self, listing_id: str) -> list[dict[str, object]]:
                self.calls.append(("GET images", listing_id))
                return []

        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        with session_scope(factory) as session:
            seed_database(session)
            adapter = FakeEtsyAdapter()
            config = EtsyConfig(
                keystring="fixture-key",
                shared_secret="fixture-secret",
                shop_id="wrong-shop",
                shop_name="MattMadeMe",
            )
            summary = sync_etsy_read_only(session, adapter=adapter, config=config)

            self.assertEqual(summary.errors, [])
            self.assertEqual(summary.products_imported, 1)
            self.assertEqual(
                adapter.calls,
                [
                    ("GET listings", "wrong-shop"),
                    ("find shop", "MattMadeMe"),
                    ("GET listings", "fixture-shop"),
                    ("GET images", "etsy-100"),
                ],
            )

            sync = session.scalar(select(SyncMetadata).where(SyncMetadata.source_name == "etsy_api"))
            self.assertIsNotNone(sync)
            self.assertEqual(sync.source_path, "fixture-shop")

    def test_phase5_etsy_sync_pauses_for_24_hours_after_rate_limit(self) -> None:
        from urllib.error import HTTPError

        class RateLimitedEtsyAdapter:
            def __init__(self):
                self.calls = 0

            def list_active_shop_listings(self, shop_id: str) -> list[dict[str, object]]:
                self.calls += 1
                raise HTTPError("https://etsy.example", 429, "Too Many Requests", {}, io.BytesIO(b""))

            def get_listing_images(self, listing_id: str) -> list[dict[str, object]]:
                raise AssertionError("Image lookup should not run after a listing rate limit.")

        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        with session_scope(factory) as session:
            seed_database(session)
            adapter = RateLimitedEtsyAdapter()
            config = EtsyConfig(keystring="fixture-key", shared_secret="fixture-secret", shop_id="fixture-shop")

            summary = sync_etsy_read_only(session, adapter=adapter, config=config)

            self.assertEqual(adapter.calls, 1)
            self.assertEqual(summary.products_imported, 0)
            self.assertIn("paused until", summary.errors[0])
            sync = session.scalar(select(SyncMetadata).where(SyncMetadata.source_name == "etsy_api"))
            self.assertIsNotNone(sync)
            self.assertIn("rate_limited_until=", sync.notes)

            second_adapter = RateLimitedEtsyAdapter()
            second_summary = sync_etsy_read_only(session, adapter=second_adapter, config=config)

            self.assertEqual(second_adapter.calls, 0)
            self.assertIn("paused until", second_summary.errors[0])

    def test_phase5_etsy_sync_skips_requests_during_active_rate_limit_cooldown(self) -> None:
        class FakeEtsyAdapter:
            def __init__(self):
                self.calls = 0

            def list_active_shop_listings(self, shop_id: str) -> list[dict[str, object]]:
                self.calls += 1
                return []

            def get_listing_images(self, listing_id: str) -> list[dict[str, object]]:
                return []

        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        with session_scope(factory) as session:
            seed_database(session)
            future = utc_now() + timedelta(hours=23)
            session.add(
                SyncMetadata(
                    source_name="etsy_api",
                    source_path="fixture-shop",
                    notes=f"rate_limited_until={future.isoformat()} Etsy returned 429 Too Many Requests.",
                )
            )
            adapter = FakeEtsyAdapter()
            config = EtsyConfig(keystring="fixture-key", shared_secret="fixture-secret", shop_id="fixture-shop")

            summary = sync_etsy_read_only(session, adapter=adapter, config=config)

            self.assertEqual(adapter.calls, 0)
            self.assertIn("paused until", summary.errors[0])

    def test_phase5_website_sync_imports_blog_posts_only(self) -> None:
        class FakeWebsiteAdapter:
            def list_published_blog_posts(self) -> list[dict[str, object]]:
                return [
                    {
                        "id": "blog-1",
                        "slug": "fixture-story",
                        "headline": "Fixture Story",
                        "excerpt": "A synced blog post.",
                        "url": "https://mattmademe.example/blog/fixture-story",
                        "tags": ["behind the scenes"],
                    }
                ]

            def create_blog_draft(self, draft_request: dict[str, object]) -> dict[str, object]:
                raise AssertionError("Read sync must not create drafts.")

        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        with session_scope(factory) as session:
            seed_database(session)
            initial_products = session.scalar(select(func.count()).select_from(ProductRecord))
            initial_assets = session.scalar(select(func.count()).select_from(AssetRecord))
            summary = sync_mattmademe_website(session, adapter=FakeWebsiteAdapter())
            self.assertEqual(summary.products_imported, 0)
            self.assertEqual(summary.assets_imported, 0)
            self.assertEqual(summary.blog_posts_imported, 1)
            self.assertEqual(session.scalar(select(func.count()).select_from(ProductRecord)), initial_products)
            self.assertEqual(session.scalar(select(func.count()).select_from(AssetRecord)), initial_assets)

            post = session.scalar(select(BlogPostRecord).where(BlogPostRecord.external_source == "mattmademe_website", BlogPostRecord.external_id == "blog-1"))
            self.assertIsNotNone(post)
            self.assertEqual(post.title, "Fixture Story")
            self.assertEqual(post.canonical_url, "https://mattmademe.example/blog/fixture-story")

            target = export_operating_data(session, Path(tmp.name) / "exports")
            payload = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["blog_posts"]), 1)
            self.assertEqual(payload["blog_posts"][0]["title"], "Fixture Story")

            health = data_health(session)
            self.assertFalse(any(item.area == "Website Sync" for item in health))

    def test_phase5_web_settings_exposes_safe_sync_actions_without_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "phase5-integrations.sqlite"
            with patch.dict(
                "os.environ",
                {
                    "MARKETING_OS_SKIP_DOTENV": "1",
                    "ETSY_KEYSTRING": "",
                    "ETSY_SHARED_SECRET": "",
                    "ETSY_SHOP_ID": "",
                    "MARKETING_AGENT_API_KEY": "",
                },
                clear=False,
            ):
                app = create_app(db_path, bootstrap_data=True)
                self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
                client = app.test_client()

                settings = client.get("/settings")
                self.assertEqual(settings.status_code, 200)
                self.assertNotIn(b"Sync Etsy", settings.data)
                self.assertNotIn(b"Sync website", settings.data)

                etsy_response = client.post("/api/integrations/etsy/sync")
                self.assertEqual(etsy_response.status_code, 400)
                self.assertIn("credentials", etsy_response.get_json()["errors"][0])

                website_response = client.post("/api/integrations/website/sync")
                self.assertEqual(website_response.status_code, 404)

    def test_phase5_settings_cleanup_removes_rejected_or_canceled_generated_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "phase5-cleanup.sqlite"
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            client = app.test_client()

            source_path = Path(tmp) / "approved-source.png"
            source_path.write_bytes(tiny_png_bytes("#0f766e"))
            rejected_image_path = Path(tmp) / "rejected-generated.png"
            rejected_image_path.write_bytes(tiny_png_bytes("#ef4444"))
            canceled_output_path = Path(tmp) / "canceled-video.mp4"
            canceled_output_path.write_bytes(b"fake-video")

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = ProductRecord(name="Cleanup Duck")
                session.add(product)
                session.flush()

                source = AssetRecord(
                    product_id=product.id,
                    name="Approved source",
                    asset_type="source photo",
                    source_path=source_path.as_posix(),
                    preview_path=source_path.as_posix(),
                    readiness_state="needs human review",
                    review_state="needs review",
                    file_exists=1,
                )
                session.add(source)
                session.flush()
                review_asset(session, source.id, "approved", "Source approved.")

                item = create_planned_content_item(
                    session,
                    calendar_date=date.today(),
                    destinations=["Facebook"],
                    goals=["Follower growth"],
                    product_ids=[product.id],
                    selected_source_asset_ids=[source.id],
                    audience="Gift Buyers",
                    occasion="Test cleanup",
                )
                copy_candidate = self.register_agent_copy(session, item, "Cleanup test hook.\n\nCleanup test body.\n\nCleanup CTA.")
                record_candidate_review(session, copy_candidate.id, "rejected", "Rejected test copy.")

                image_candidate = register_generated_image_option(
                    session,
                    item.id,
                    rejected_image_path,
                    option_number=1,
                    title="Rejected generated option",
                    provider="codex_imagegen",
                )
                record_candidate_review(session, image_candidate.id, "rejected", "Rejected generated image.")
                rejected_asset_id = json.loads(image_candidate.body)["asset_id"]

                canceled_job = CreativeGenerationJobRecord(
                    source_asset_id=source.id,
                    target_format="video_request",
                    provider="magnific_mcp",
                    prompt="Canceled output.",
                    provider_status="canceled",
                    output_path=canceled_output_path.as_posix(),
                    review_state="rejected",
                    review_notes="Canceled in test.",
                )
                session.add(canceled_job)
                session.flush()

                item_id = item.id
                copy_candidate_id = copy_candidate.id
                image_candidate_id = image_candidate.id
                source_id = source.id
                canceled_job_id = canceled_job.id

            settings = client.get("/settings")
            self.assertEqual(settings.status_code, 200)
            self.assertIn(b"Clean rejected or canceled items", settings.data)
            self.assertIn(b"Rejected candidates:", settings.data)

            response = client.post("/settings/cleanup-rejected", follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Cleanup removed", response.data)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                self.assertIsNone(session.get(PlannedContentRecord, item_id))
                self.assertIsNone(session.get(GeneratedContentCandidateRecord, copy_candidate_id))
                self.assertIsNone(session.get(GeneratedContentCandidateRecord, image_candidate_id))
                self.assertIsNone(session.get(AssetRecord, rejected_asset_id))
                self.assertIsNone(session.get(CreativeGenerationJobRecord, canceled_job_id))
                self.assertIsNotNone(session.get(AssetRecord, source_id))

            self.assertTrue(source_path.exists())
            self.assertFalse(rejected_image_path.exists())
            self.assertFalse(canceled_output_path.exists())

    def test_phase5_local_asset_library_scan_indexes_local_root(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        from PIL import Image

        asset_root = Path(tmp.name) / "assets"
        product_dir = asset_root / "products" / "bingo-duck" / "source"
        product_dir.mkdir(parents=True)
        source_path = product_dir / "bingo-source.jpg"
        Image.new("RGB", (900, 700), "#0f766e").save(source_path)

        brand_dir = asset_root / "brand" / "logos"
        brand_dir.mkdir(parents=True)
        logo_path = brand_dir / "logo.png"
        Image.new("RGB", (300, 120), "#ffffff").save(logo_path)

        with session_scope(factory) as session:
            seed_database(session)
            summary = scan_asset_root(session, asset_root)
            self.assertFalse(summary.missing_root)
            self.assertEqual(summary.indexed, 2)
            self.assertTrue(Path(summary.manifest_path).exists())

            product_asset = session.scalar(
                select(AssetRecord).where(
                    AssetRecord.external_source == "local_asset_library",
                    AssetRecord.relative_path == "products/bingo-duck/source/bingo-source.jpg",
                )
            )
            self.assertIsNotNone(product_asset)
            self.assertEqual(product_asset.asset_role, "product_photo")
            self.assertEqual(product_asset.width, 900)
            self.assertEqual(product_asset.height, 700)
            self.assertTrue(product_asset.preview_path)
            self.assertTrue(Path(product_asset.preview_path).exists())
            self.assertEqual(product_asset.review_state, "needs review")

            logo_asset = session.scalar(select(AssetRecord).where(AssetRecord.asset_role == "logo"))
            self.assertIsNotNone(logo_asset)
            self.assertEqual(logo_asset.asset_type, "logo")

            target = export_operating_data(session, Path(tmp.name) / "exports")
            payload = json.loads(target.read_text(encoding="utf-8"))
            exported = next(item for item in payload["assets"] if item["relative_path"] == "products/bingo-duck/source/bingo-source.jpg")
            self.assertEqual(exported["width"], 900)
            self.assertEqual(exported["asset_role"], "product_photo")

            health = data_health(session, asset_library_root=asset_root)
            self.assertTrue(any(item.area == "Local Asset Library" and item.status == "OK" for item in health))

    def test_phase5_local_asset_library_missing_root_is_visible(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        missing_root = Path(tmp.name) / "MissingAssets"
        with session_scope(factory) as session:
            seed_database(session)
            summary = scan_asset_root(session, missing_root)
            self.assertTrue(summary.missing_root)
            health = data_health(session, asset_library_root=missing_root)
            row = next(item for item in health if item.area == "Local Asset Library")
            self.assertEqual(row.status, "Needs attention")
            self.assertIn("missing", row.message)

    def test_phase5_web_asset_library_scan_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "phase5-assets.sqlite"
            asset_root = Path(tmp) / "assets"
            product_dir = asset_root / "products" / "bingo-duck" / "source"
            product_dir.mkdir(parents=True)
            (product_dir / "photo.jpg").write_bytes(b"fake image bytes")

            app = create_app(db_path, bootstrap_data=True)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            app.config["ASSET_LIBRARY_ROOT"] = asset_root
            client = app.test_client()

            settings = client.get("/settings")
            self.assertEqual(settings.status_code, 200)
            self.assertIn(b"Scan asset library", settings.data)

            response = client.post("/api/assets/library/scan")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["indexed"], 1)

    def test_art_studio_queue_prioritizes_products_with_approved_references_and_sales_signal(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)
        source_path = Path(tmp.name) / "source.png"
        source_path.write_bytes(tiny_png_bytes())

        with session_scope(factory) as session:
            strong = ProductRecord(name="Strong Duck")
            weak = ProductRecord(name="Weak Duck")
            session.add_all([strong, weak])
            session.flush()
            session.add(
                AssetRecord(
                    product_id=strong.id,
                    name="Strong approved source",
                    asset_type="source photo",
                    source_path=source_path.as_posix(),
                    preview_path=source_path.as_posix(),
                    readiness_state="ready",
                    review_state="approved",
                    default_reference=1,
                )
            )
            session.add(
                ProductSalesRecord(
                    product_id=strong.id,
                    source_name="test",
                    external_id="sale-1",
                    quantity=12,
                    revenue_cents=1200,
                )
            )
            session.flush()

            queue = art_studio_queue(session, limit=2)
            self.assertEqual(queue[0].product.name, "Strong Duck")
            self.assertEqual(queue[0].approved_reference_count, 1)
            self.assertIn("$social-media-art-director", queue[0].image_handoff)
            self.assertIn("video_plan", queue[0].video_handoff)

    def test_art_studio_generation_jobs_queue_and_attach_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "art-studio-jobs.sqlite"
            source_path = tmp_path / "source.png"
            output_path = tmp_path / "generated.png"
            manifest_path = tmp_path / "manifest.json"
            source_path.write_bytes(tiny_png_bytes("#facc15"))
            output_path.write_bytes(tiny_png_bytes("#22c55e"))

            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = ProductRecord(name="Queued Duck")
                session.add(product)
                session.flush()
                source = AssetRecord(
                    product_id=product.id,
                    name="Queued source",
                    asset_type="source photo",
                    source_path=source_path.as_posix(),
                    preview_path=source_path.as_posix(),
                    readiness_state="ready",
                    review_state="approved",
                    default_reference=1,
                )
                session.add(source)
                session.flush()
                job = enqueue_social_image_generation(session, product.id, source.id)
                job_id = job.id

            client = app.test_client()
            api_response = client.get("/api/art-studio/jobs")
            self.assertEqual(api_response.status_code, 200)
            payload = api_response.get_json()
            self.assertEqual(payload["count"], 1)
            self.assertEqual(payload["jobs"][0]["provider_status"], "queued")

            page = client.get("/products")
            self.assertEqual(page.status_code, 200)
            self.assertIn(f"Job #{job_id}".encode(), page.data)
            self.assertIn(b"Social image jobs", page.data)
            self.assertIn(b"Generation request", page.data)

            manifest_path.write_text(
                json.dumps(
                    {
                        "outputs": [
                            {
                                "job_id": job_id,
                                "media_type": "social_image",
                                "output_path": output_path.as_posix(),
                                "title": "Queued generated image",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            summary = run_register_art_studio_outputs_job(db_path=db_path, manifest_path=manifest_path)
            self.assertEqual(summary["count"], 1)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                queued = session.get(CreativeGenerationJobRecord, job_id)
                self.assertEqual(queued.provider_status, "generated")
                self.assertIsNotNone(queued.candidate_asset_id)
                self.assertEqual(queued.candidate_asset.asset_type, "generated social image")
                self.assertEqual(queued.candidate_asset.review_state, "needs review")

    def test_social_image_prompt_uses_product_theme_scene_context(self) -> None:
        product = ProductRecord(
            name="Construction Duck: 3D Printed Builder Gift",
            sales_momentum_note="Meet Construction Duck, wearing a hard hat and ready for the job site with tools and worksite attitude.",
        )
        direction = social_image_scene_direction(product)
        self.assertIn("construction site", direction)
        self.assertIn("tools", direction)
        self.assertIn("bowling alley", social_image_scene_direction(ProductRecord(name="Bowling Duck: Cruise Duck, 3D Printed")))
        self.assertIn("woodland", social_image_scene_direction(ProductRecord(name="Chipmunk Duck: Animal Costume Duck, 3D Printed")))

        prompt = social_image_handoff(product, [], "outputs/test")
        self.assertIn("Product theme context:", prompt)
        self.assertIn("Scene direction:", prompt)
        self.assertIn("Scene variation:", prompt)
        self.assertIn("construction site", prompt)
        self.assertIn("do not put the duck in a generic office", prompt)
        self.assertIn("no weapons, ammunition, shell casings", prompt)
        self.assertIn("adult themes", prompt)
        self.assertNotIn("After generation", prompt)
        self.assertNotIn("download the file", prompt)
        self.assertNotEqual(social_image_scene_variation(1), social_image_scene_variation(2))

    def test_content_automation_exports_art_studio_social_image_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "art-studio-social-export.sqlite"
            output_dir = tmp_path / "content-automation"
            source_path = tmp_path / "source.png"
            generated_path = tmp_path / "generated-social.png"
            source_path.write_bytes(tiny_png_bytes("#facc15"))
            generated_path.write_bytes(tiny_png_bytes("#22c55e"))

            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = ProductRecord(
                    name="Construction Duck: 3D Printed Builder Gift",
                    sales_momentum_note="Hard hat, tools, and job-site attitude.",
                )
                session.add(product)
                session.flush()
                source = AssetRecord(
                    product_id=product.id,
                    name="Construction source",
                    asset_type="source photo",
                    source_path=source_path.as_posix(),
                    preview_path=source_path.as_posix(),
                    readiness_state="ready",
                    review_state="approved",
                    default_reference=1,
                )
                session.add(source)
                session.flush()
                job = enqueue_social_image_generation(session, product.id, source.id)
                job_id = job.id

            summary = run_content_automation_job(db_path=db_path, output_dir=output_dir, limit=10, days_ahead=14)
            self.assertEqual(len(summary["art_studio_social_image_files"]), 1)
            request_path = Path(summary["art_studio_social_image_files"][0])
            self.assertTrue(request_path.is_file())
            payload = json.loads(request_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["workflow_name"], "art_studio_social_worthy_images")
            self.assertEqual(payload["job_count"], 1)
            self.assertEqual(payload["jobs"][0]["id"], job_id)
            self.assertIn("construction site", payload["jobs"][0]["prompt"])
            self.assertIn("no weapons, ammunition, shell casings", payload["jobs"][0]["prompt"])
            self.assertIn("adult themes", payload["jobs"][0]["prompt"])
            self.assertNotIn("After generation", payload["jobs"][0]["prompt"])
            self.assertNotIn("download the file", payload["jobs"][0]["prompt"])
            self.assertIn("recommended_output_path", payload["jobs"][0])
            self.assertEqual(payload["registration_manifest_example"]["outputs"][0]["media_type"], "social_image")
            self.assertIn("Download each completed image", " ".join(payload["instructions"]))
            self.assertIn("register_art_studio_outputs", " ".join(payload["instructions"]))

            manifest = payload["registration_manifest_example"]
            manifest["outputs"][0]["output_path"] = generated_path.as_posix()
            manifest_path = request_path.parent / "register-social-images.json"
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            registered = run_register_art_studio_outputs_job(db_path=db_path, manifest_path=manifest_path)
            self.assertEqual(registered["count"], 1)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                completed = session.get(CreativeGenerationJobRecord, job_id)
                self.assertEqual(completed.provider_status, "generated")
                self.assertIsNotNone(completed.candidate_asset_id)
                self.assertEqual(completed.candidate_asset.asset_type, "generated social image")

    def test_art_studio_video_art_board_queue_and_attach_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "art-board-jobs.sqlite"
            source_path = tmp_path / "source.png"
            art_board_path = tmp_path / "art-board.png"
            manifest_path = tmp_path / "manifest.json"
            source_path.write_bytes(tiny_png_bytes("#facc15"))
            art_board_path.write_bytes(tiny_png_bytes("#22c55e"))

            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = ProductRecord(name="Storyboard Duck")
                session.add(product)
                session.flush()
                source = AssetRecord(
                    product_id=product.id,
                    name="Storyboard source",
                    asset_type="source photo",
                    source_path=source_path.as_posix(),
                    preview_path=source_path.as_posix(),
                    readiness_state="ready",
                    review_state="approved",
                    default_reference=1,
                )
                session.add(source)
                session.flush()
                job = enqueue_video_art_board_generation(
                    session,
                    product.id,
                    source.id,
                    scene="festive picnic setup",
                    aspect_ratio="9:16",
                )
                job_id = job.id
                self.assertEqual(job.target_format, "art_studio_video_art_board")
                self.assertIn("$social-media-art-director", job.prompt)
                self.assertIn("festive picnic setup", job.prompt)

            manifest_path.write_text(
                json.dumps(
                    {
                        "outputs": [
                            {
                                "job_id": job_id,
                                "media_type": "video_art_board",
                                "output_path": art_board_path.as_posix(),
                                "title": "Storyboard Duck picnic art board",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            summary = run_register_art_studio_outputs_job(db_path=db_path, manifest_path=manifest_path)
            self.assertEqual(summary["count"], 1)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                queued = session.get(CreativeGenerationJobRecord, job_id)
                self.assertEqual(queued.provider_status, "generated")
                self.assertEqual(queued.candidate_asset.asset_type, "generated video art board")
                self.assertEqual(queued.candidate_asset.asset_role, "video opening card")
                queue = art_studio_queue(session, limit=1)
                self.assertEqual(queue[0].video_start_assets[0].id, queued.candidate_asset_id)

    def test_art_studio_video_storyboard_queues_opening_and_ending_cards(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)
        source_path = Path(tmp.name) / "source.png"
        source_path.write_bytes(tiny_png_bytes("#facc15"))

        with session_scope(factory) as session:
            product = ProductRecord(name="Strategist Duck")
            session.add(product)
            session.flush()
            source = AssetRecord(
                product_id=product.id,
                name="Strategist source",
                asset_type="source photo",
                source_path=source_path.as_posix(),
                preview_path=source_path.as_posix(),
                readiness_state="ready",
                review_state="approved",
                default_reference=1,
            )
            session.add(source)
            session.flush()

            jobs = enqueue_video_storyboard_generation(
                session,
                product.id,
                source.id,
                scene_guidance="festive picnic setup with red gingham tablecloth",
                aspect_ratio="9:16",
                option_number=2,
            )

            self.assertEqual(len(jobs), 2)
            self.assertEqual({json.loads(job.response_metadata_json)["board_role"] for job in jobs}, {"opening_card", "ending_card"})
            self.assertEqual(len({json.loads(job.response_metadata_json)["storyboard_id"] for job in jobs}), 1)
            self.assertTrue(all("festive picnic setup" in job.prompt for job in jobs))
            self.assertTrue(all("exact silhouette" in job.prompt for job in jobs))

            rerun = enqueue_video_storyboard_generation(
                session,
                product.id,
                source.id,
                scene_guidance="festive picnic setup with red gingham tablecloth",
                aspect_ratio="9:16",
                option_number=2,
            )
            self.assertEqual([job.id for job in rerun], [job.id for job in jobs])

    def test_art_studio_video_request_approval_uses_generated_cards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "video-request.sqlite"
            source_path = tmp_path / "source.png"
            opening_path = tmp_path / "opening.png"
            workflow_manifest_path = tmp_path / "workflow-manifest.json"
            output_manifest_path = tmp_path / "output-manifest.json"
            output_dir = tmp_path / "content-automation"
            source_path.write_bytes(tiny_png_bytes("#facc15"))
            opening_path.write_bytes(tiny_png_bytes("#22c55e"))

            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = ProductRecord(name="Approval Duck")
                session.add(product)
                session.flush()
                source = AssetRecord(
                    product_id=product.id,
                    name="Approval source",
                    asset_type="source photo",
                    source_path=source_path.as_posix(),
                    preview_path=source_path.as_posix(),
                    readiness_state="ready",
                    review_state="approved",
                    default_reference=1,
                )
                session.add(source)
                session.flush()
                request_job = create_video_request(
                    session,
                    product.id,
                    [source.id],
                    duration_seconds=6,
                    aspect_ratio="9:16",
                    resolution="720p",
                    scene_guidance="festive picnic setup",
                )
                request_id = request_job.id
                request_rows = art_studio_video_requests(session)
                self.assertEqual(request_rows[0].status, "queued")
                self.assertIsNone(request_rows[0].opening_job)
                self.assertIsNone(request_rows[0].ending_job)
                metadata = json.loads(request_job.response_metadata_json)
                self.assertEqual(metadata["storyboard_mode"], "single_start_frame")
                self.assertFalse(metadata["ending_card_required"])
                self.assertEqual(metadata["video_template_slug"], "focus_pull")
                self.assertEqual(metadata["video_template_name"], "Focus pull")
                self.assertNotIn("video_effect_name", metadata)
                self.assertIn("Queued for agent-run video planning", request_job.prompt)

            export_summary = run_content_automation_job(db_path=db_path, output_dir=output_dir, limit=10, days_ahead=14)
            self.assertEqual(len(export_summary["video_request_files"]), 1)
            workflow_path = Path(export_summary["video_request_files"][0])
            self.assertTrue(workflow_path.is_file())
            workflow_payload = json.loads(workflow_path.read_text(encoding="utf-8"))
            self.assertEqual(workflow_payload["request_job_id"], request_id)
            self.assertEqual(workflow_payload["workflow"]["planner_request"]["skill"], "video-content-planner")
            self.assertEqual(workflow_payload["workflow"]["art_direction_request"]["skill"], "social-media-art-director")
            self.assertEqual(workflow_payload["workflow"]["editor_request"]["skill"], "video-editor")
            self.assertEqual(workflow_payload["workflow"]["editor_request"]["input"]["model_selection"]["mode"], "fidelity_first")
            self.assertEqual(
                workflow_payload["workflow"]["editor_request"]["input"]["model_selection"]["suggested_model"],
                "kling-25",
            )
            self.assertIn("audio_direction", workflow_payload["registration_manifest_example"]["planner_result"])
            self.assertIn("tail_rule", workflow_payload["registration_manifest_example"]["planner_result"])

            workflow_manifest_path.write_text(
                json.dumps(
                    {
                        "request_job_id": request_id,
                        "provider": "codex_agent",
                        "notes": "Planner brief registered from agent automation.",
                        "planner_result": {
                            "summary": "Create a 6 second 9:16 product-safe social video for Approval Duck in a festive picnic scene with a focus pull.",
                            "scene_strategy": "festive picnic setup",
                            "selected_effect": {
                                "slug": "focus_pull",
                                "name": "Focus pull",
                                "risk": "low",
                                "value": "Use shallow depth and a rack focus while the duck stays frozen.",
                            },
                            "opening_card_brief": "Build a realistic picnic opening frame with foreground depth and a scroll-stopping product placement.",
                            "ending_card_brief": "Not needed for this effect.",
                            "video_motion_prompt": "Slow rack focus from the foreground texture to the unchanged duck.",
                            "audio_direction": "Subtle picnic ambience only.",
                            "style_direction": "Photorealistic high-detail product video, clean social frame, 9:16, no text.",
                            "tail_rule": "End with the duck physically unchanged while focus settles on the hero product.",
                            "storyboard_mode": "single_start_frame",
                            "ending_card_required": False,
                        },
                        "opening_card": {
                            "title": "Approval Duck opening card",
                            "prompt": "Use $video-content-planner and $social-media-art-director. Create a realistic opening scene card for Approval Duck in a festive picnic setup. Preserve the exact duck from the references. Add foreground depth for a focus pull. No text, no watermark, no changed accessories.",
                            "provider": "magnific_mcp",
                            "model_name": "Google Nano Banana 2",
                        },
                        "ending_card": {
                            "required": False,
                            "title": "Approval Duck ending card",
                            "prompt": "",
                            "provider": "magnific_mcp",
                            "model_name": "Google Nano Banana 2",
                        },
                        "video_editor_request": workflow_payload["workflow"]["editor_request"]["input"],
                    }
                ),
                encoding="utf-8",
            )
            workflow_summary = run_register_art_studio_video_workflow_job(db_path=db_path, manifest_path=workflow_manifest_path)
            self.assertEqual(workflow_summary["status"], "cards_in_progress")
            opening_id = workflow_summary["opening_card_job_id"]
            self.assertIsNotNone(opening_id)

            output_manifest_path.write_text(
                json.dumps(
                    {
                        "outputs": [
                            {
                                "job_id": opening_id,
                                "media_type": "video_art_board",
                                "output_path": opening_path.as_posix(),
                                "title": "Approval Duck opening card",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            summary = run_register_art_studio_outputs_job(db_path=db_path, manifest_path=output_manifest_path)
            self.assertEqual(summary["count"], 1)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                request_rows = art_studio_video_requests(session)
                self.assertEqual(request_rows[0].status, "ready_for_approval")
                self.assertIn("Selected template: Focus pull", request_rows[0].details["strategist_direction"])
                self.assertIn("Video motion direction: Slow rack focus", request_rows[0].details["strategist_direction"])
                video_job = approve_video_request_for_generation(session, request_id)
                self.assertEqual(video_job.target_format, "art_studio_product_video")
                self.assertIn(f'"video_request_job_id": {request_id}', video_job.response_metadata_json)
                self.assertIn('"end_frame_asset_id": null', video_job.response_metadata_json)
                self.assertIn("Suggested model: kling-25.", video_job.prompt)
                self.assertIn("Subtle picnic ambience only.", video_job.prompt)
                self.assertIn("End with the duck physically unchanged while focus settles on the hero product.", video_job.prompt)

    def test_art_studio_video_request_exports_agent_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "video-export.sqlite"
            source_path = Path(tmp) / "source.png"
            output_dir = Path(tmp) / "content-automation"
            source_path.write_bytes(tiny_png_bytes("#facc15"))

            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = ProductRecord(name="Tattoo Duck")
                session.add(product)
                session.flush()
                source = AssetRecord(
                    product_id=product.id,
                    name="Tattoo Duck source",
                    asset_type="source photo",
                    source_path=source_path.as_posix(),
                    preview_path=source_path.as_posix(),
                    readiness_state="ready",
                    review_state="approved",
                    default_reference=1,
                )
                session.add(source)
                session.flush()
                create_video_request(
                    session,
                    product.id,
                    [source.id],
                    duration_seconds=8,
                    aspect_ratio="9:16",
                    resolution="1080p",
                    scene_guidance="tattoo parlor shelf with moody practical lighting",
                )

            summary = run_content_automation_job(db_path=db_path, output_dir=output_dir, limit=10, days_ahead=14)
            self.assertEqual(len(summary["video_request_files"]), 1)
            payload = json.loads(Path(summary["video_request_files"][0]).read_text(encoding="utf-8"))
            self.assertEqual(payload["workflow"]["workflow_name"], "art_studio_video_planner_art_direction_editor")
            self.assertEqual(payload["workflow"]["planner_request"]["skill"], "video-content-planner")
            self.assertEqual(payload["workflow"]["art_direction_request"]["skill"], "social-media-art-director")
            self.assertEqual(payload["workflow"]["editor_request"]["skill"], "video-editor")
            self.assertEqual(payload["request"]["video_template_slug"], "focus_pull")
            self.assertEqual(payload["request"]["suggested_video_model"], "kling-25")
            self.assertIn("register-video-workflow.json", "\n".join(payload["instructions"]))

    def test_social_media_ad_request_preserves_voice_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "video-social-ad.sqlite"
            source_path = tmp_path / "source.png"
            opening_path = tmp_path / "opening.png"
            workflow_manifest_path = tmp_path / "workflow-manifest.json"
            output_manifest_path = tmp_path / "output-manifest.json"
            output_dir = tmp_path / "content-automation"
            source_path.write_bytes(tiny_png_bytes("#facc15"))
            opening_path.write_bytes(tiny_png_bytes("#22c55e"))

            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = ProductRecord(name="Ad Voice Duck")
                session.add(product)
                session.flush()
                source = AssetRecord(
                    product_id=product.id,
                    name="Ad Voice Duck source",
                    asset_type="source photo",
                    source_path=source_path.as_posix(),
                    preview_path=source_path.as_posix(),
                    readiness_state="ready",
                    review_state="approved",
                    default_reference=1,
                )
                session.add(source)
                session.flush()
                request_job = create_video_request(
                    session,
                    product.id,
                    [source.id],
                    duration_seconds=6,
                    aspect_ratio="9:16",
                    resolution="1080p",
                    scene_guidance="clean cruise-ship artist workstation with printed art cards",
                    template_slug="social_media_ad",
                    voice_script="Limited edition drop now live.",
                    voice_tone="serious and neutral",
                )
                request_id = request_job.id

            export_summary = run_content_automation_job(db_path=db_path, output_dir=output_dir, limit=10, days_ahead=14)
            payload = json.loads(Path(export_summary["video_request_files"][0]).read_text(encoding="utf-8"))
            self.assertEqual(payload["request"]["video_template_slug"], "social_media_ad")
            self.assertEqual(payload["request"]["requested_voice_script"], "Limited edition drop now live.")
            self.assertEqual(payload["workflow"]["planner_request"]["input"]["requested_voice_tone"], "serious and neutral")

            workflow_manifest_path.write_text(
                json.dumps(
                    {
                        "request_job_id": request_id,
                        "provider": "codex_agent",
                        "notes": "Planner brief registered from agent automation.",
                        "planner_result": {
                            "summary": "Create a 6 second 9:16 product-safe social ad video for Ad Voice Duck from one start frame.",
                            "scene_strategy": "clean cruise-ship artist workstation with printed art cards",
                            "selected_effect": {
                                "slug": "social_media_ad",
                                "name": "Social Media Ad",
                                "risk": "medium-high",
                                "value": "Use clean ad pacing while preserving product identity.",
                            },
                            "opening_card_brief": "Build a bright hero opening card that reads instantly in 9:16.",
                            "ending_card_brief": "Not needed for this effect.",
                            "video_motion_prompt": "Create a scroll-stopping 9:16 social media ad with clean, realistic camera motion and one punchier emphasis change while keeping the duck exact.",
                            "style_direction": "Photorealistic high-detail product video, clean social frame, 9:16, no text.",
                            "tail_rule": "End on the clearest hero product frame with the duck still exact and unchanged.",
                            "storyboard_mode": "single_start_frame",
                            "ending_card_required": False,
                        },
                        "opening_card": {
                            "title": "Ad Voice Duck opening card",
                            "prompt": "Create a bright 9:16 social ad opening card for Ad Voice Duck on a clean cruise-ship artist workstation. Preserve the exact duck and keep the scene product-safe.",
                            "provider": "magnific_mcp",
                            "model_name": "Google Nano Banana 2",
                        },
                        "ending_card": {
                            "required": False,
                            "title": "Ad Voice Duck ending card",
                            "prompt": "",
                            "provider": "magnific_mcp",
                            "model_name": "Google Nano Banana 2",
                        },
                        "video_editor_request": payload["workflow"]["editor_request"]["input"],
                    }
                ),
                encoding="utf-8",
            )
            workflow_summary = run_register_art_studio_video_workflow_job(db_path=db_path, manifest_path=workflow_manifest_path)
            opening_id = workflow_summary["opening_card_job_id"]
            output_manifest_path.write_text(
                json.dumps(
                    {
                        "outputs": [
                            {
                                "job_id": opening_id,
                                "media_type": "video_art_board",
                                "output_path": opening_path.as_posix(),
                                "title": "Ad Voice Duck opening card",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            run_register_art_studio_outputs_job(db_path=db_path, manifest_path=output_manifest_path)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                video_job = approve_video_request_for_generation(session, request_id)
                self.assertIn('Add a short serious and neutral voice saying "Limited edition drop now live."', video_job.prompt)
                self.assertEqual(video_job.model_name, "bytedance-seedance-pro-2.0")

    def test_art_studio_approved_video_request_exports_generation_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "video-generation-export.sqlite"
            source_path = tmp_path / "source.png"
            opening_path = tmp_path / "opening.png"
            workflow_manifest_path = tmp_path / "workflow-manifest.json"
            output_manifest_path = tmp_path / "output-manifest.json"
            output_dir = tmp_path / "content-automation"
            source_path.write_bytes(tiny_png_bytes("#facc15"))
            opening_path.write_bytes(tiny_png_bytes("#22c55e"))

            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = ProductRecord(name="Export Video Duck")
                session.add(product)
                session.flush()
                source = AssetRecord(
                    product_id=product.id,
                    name="Export video source",
                    asset_type="source photo",
                    source_path=source_path.as_posix(),
                    preview_path=source_path.as_posix(),
                    readiness_state="ready",
                    review_state="approved",
                    default_reference=1,
                )
                session.add(source)
                session.flush()
                request_job = create_video_request(
                    session,
                    product.id,
                    [source.id],
                    duration_seconds=6,
                    aspect_ratio="9:16",
                    resolution="1080p",
                    scene_guidance="tattoo station counter with ocean light",
                )
                request_id = request_job.id

            export_summary = run_content_automation_job(db_path=db_path, output_dir=output_dir, limit=10, days_ahead=14)
            workflow_payload = json.loads(Path(export_summary["video_request_files"][0]).read_text(encoding="utf-8"))
            workflow_manifest_path.write_text(
                json.dumps(
                    {
                        "request_job_id": request_id,
                        "provider": "codex_agent",
                        "notes": "Planner brief registered from agent automation.",
                        "planner_result": {
                            "summary": "Create a 6 second 9:16 product-safe social video for Export Video Duck in a tattoo station scene with a focus pull.",
                            "scene_strategy": "tattoo station counter with ocean light",
                            "selected_effect": {
                                "slug": "focus_pull",
                                "name": "Focus pull",
                                "risk": "low",
                                "value": "Use shallow depth and a rack focus while the duck stays frozen.",
                            },
                            "opening_card_brief": "Build a realistic tattoo-station opening frame with foreground depth and a clear hero placement.",
                            "ending_card_brief": "Not needed for this effect.",
                            "video_motion_prompt": "Slow rack focus from a foreground station detail to the unchanged duck.",
                            "audio_direction": "Subtle room tone with distant ship ambience.",
                            "style_direction": "Photorealistic high-detail product video, clean social frame, 9:16, no text.",
                            "tail_rule": "End with the duck unchanged while the focus settles into a clean final frame.",
                            "storyboard_mode": "single_start_frame",
                            "ending_card_required": False,
                        },
                        "opening_card": {
                            "title": "Export Video Duck opening card",
                            "prompt": "Create a realistic opening scene card for Export Video Duck in a tattoo station counter scene. Preserve the exact duck from the references. Add foreground depth for a focus pull. No text or watermark.",
                            "provider": "magnific_mcp",
                            "model_name": "Google Nano Banana 2",
                        },
                        "ending_card": {
                            "required": False,
                            "title": "Export Video Duck ending card",
                            "prompt": "",
                            "provider": "magnific_mcp",
                            "model_name": "Google Nano Banana 2",
                        },
                        "video_editor_request": workflow_payload["workflow"]["editor_request"]["input"],
                    }
                ),
                encoding="utf-8",
            )
            workflow_summary = run_register_art_studio_video_workflow_job(db_path=db_path, manifest_path=workflow_manifest_path)
            opening_id = workflow_summary["opening_card_job_id"]
            output_manifest_path.write_text(
                json.dumps(
                    {
                        "outputs": [
                            {
                                "job_id": opening_id,
                                "media_type": "video_art_board",
                                "output_path": opening_path.as_posix(),
                                "title": "Export Video Duck opening card",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            run_register_art_studio_outputs_job(db_path=db_path, manifest_path=output_manifest_path)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                video_job = approve_video_request_for_generation(session, request_id)
                self.assertEqual(video_job.target_format, "art_studio_product_video")

            summary = run_content_automation_job(db_path=db_path, output_dir=output_dir, limit=10, days_ahead=14)
            self.assertEqual(summary["video_request_files"], [])
            self.assertEqual(len(summary["video_generation_files"]), 1)
            payload = json.loads(Path(summary["video_generation_files"][0]).read_text(encoding="utf-8"))
            self.assertEqual(payload["request_job_id"], request_id)
            self.assertEqual(payload["status"], "video_queued")
            self.assertEqual(payload["video_job"]["target_format"], "art_studio_product_video")
            self.assertEqual(payload["registration_manifest_example"]["outputs"][0]["media_type"], "product_video")
            self.assertIn("Use video-editor and Magnific MCP", payload["instructions"][0])
            self.assertEqual(payload["video_editor_request"]["model_selection"]["mode"], "fidelity_first")
            self.assertTrue(payload["brief"]["audio_direction"])
            self.assertTrue(payload["brief"]["style_direction"])
            self.assertTrue(payload["brief"]["tail_rule"])

    def test_art_studio_social_image_import_is_review_gated_and_reusable_after_approval(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)
        source_path = Path(tmp.name) / "source.png"
        output_path = Path(tmp.name) / "social.png"
        source_path.write_bytes(tiny_png_bytes("#facc15"))
        output_path.write_bytes(tiny_png_bytes("#22c55e"))

        with session_scope(factory) as session:
            product = ProductRecord(name="Reusable Duck")
            session.add(product)
            session.flush()
            source = AssetRecord(
                product_id=product.id,
                name="Reusable source",
                asset_type="source photo",
                source_path=source_path.as_posix(),
                preview_path=source_path.as_posix(),
                readiness_state="ready",
                review_state="approved",
                default_reference=1,
            )
            session.add(source)
            session.flush()

            asset = register_social_image_output(
                session,
                product_id=product.id,
                source_asset_id=source.id,
                output_path=output_path,
                title="Reusable social image",
                prompt="Create a product-safe social image.",
            )
            self.assertEqual(asset.asset_type, "generated social image")
            self.assertEqual(asset.asset_role, "social worthy image")
            self.assertEqual(asset.review_state, "needs review")
            self.assertEqual(asset.source_asset_id, source.id)

            review_asset(session, asset.id, "approved", "Looks accurate.")
            from marketing_os.services.content_briefs import _best_task_asset

            selected = _best_task_asset(session, product)
            self.assertIsNotNone(selected)
            self.assertEqual(selected.id, asset.id)

    def test_art_studio_video_queue_prefers_generated_scene_start_frame(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)
        source_path = Path(tmp.name) / "source.png"
        scene_path = Path(tmp.name) / "scene.png"
        source_path.write_bytes(tiny_png_bytes("#0ea5e9"))
        scene_path.write_bytes(tiny_png_bytes("#22c55e"))

        with session_scope(factory) as session:
            product = ProductRecord(name="Scene First Duck")
            session.add(product)
            session.flush()
            source = AssetRecord(
                product_id=product.id,
                name="Plain source",
                asset_type="source photo",
                source_path=source_path.as_posix(),
                preview_path=source_path.as_posix(),
                readiness_state="ready",
                review_state="approved",
                default_reference=1,
            )
            scene = AssetRecord(
                product_id=product.id,
                name="Generated picnic scene",
                asset_type="generated social image",
                asset_role="social worthy image",
                source_path=scene_path.as_posix(),
                preview_path=scene_path.as_posix(),
                readiness_state="needs human review",
                review_state="needs review",
            )
            session.add_all([source, scene])
            session.flush()

            queue = art_studio_queue(session, limit=1)
            self.assertEqual(queue[0].video_start_assets[0].id, scene.id)
            self.assertIn("start frame", queue[0].video_handoff.lower())
            self.assertIn("extra yellow pieces", queue[0].video_handoff)

            job = enqueue_video_generation(session, product.id, scene.id)
            self.assertEqual(job.source_asset_id, scene.id)
            self.assertEqual(job.model_name, "kling-25")
            self.assertIn("start_frame_strategy", job.response_metadata_json)
            self.assertIn("extra yellow pieces", job.prompt)
            for section in [
                "SCENE:",
                "SUBJECT:",
                "REFERENCE / PRODUCT LOCK:",
                "MOTION:",
                "AUDIO:",
                "STYLE:",
                "NEGATIVE PROMPT:",
                "TAIL (Ending Rule):",
            ]:
                self.assertIn(section, job.prompt)
            self.assertIn("Product video for Scene First Duck. 8 seconds. 9:16. 1080p.", job.prompt)
            self.assertIn("Use the approved opening card as the first frame.", job.prompt)
            self.assertIn("Keep the duck identical", job.prompt)
            self.assertIn("0-2s -", job.prompt)
            self.assertIn("2-5s -", job.prompt)
            self.assertIn("5-8s -", job.prompt)
            self.assertIn("Subtle realistic ambient sound", job.prompt)
            self.assertIn("Photorealistic high-detail product video", job.prompt)
            self.assertIn("plain product-photo opening card", job.prompt)
            self.assertIn(DEFAULT_VIDEO_NEGATIVE_PROMPT, job.prompt)

            end_scene = AssetRecord(
                product_id=product.id,
                name="Generated picnic ending",
                asset_type="generated video art board",
                asset_role="video ending card",
                source_path=scene_path.as_posix(),
                preview_path=scene_path.as_posix(),
                readiness_state="needs human review",
                review_state="needs review",
            )
            session.add(end_scene)
            session.flush()
            paired_job = enqueue_video_generation(session, product.id, scene.id, end_asset_id=end_scene.id)
            self.assertIn(f'"end_frame_asset_id": {end_scene.id}', paired_job.response_metadata_json)
            self.assertIn("End frame:", paired_job.prompt)

    def test_art_studio_video_guardrails_and_registration_metadata(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)
        source_path = Path(tmp.name) / "source.png"
        video_path = Path(tmp.name) / "video.mp4"
        source_path.write_bytes(tiny_png_bytes("#0ea5e9"))
        video_path.write_bytes(b"\x00\x00\x00\x18ftypmp42")

        safe = validate_video_motion_prompt(
            "The camera slowly pushes in. No walking, talking, blinking, flapping, or transformation."
        )
        self.assertTrue(safe["passed"])
        safe_with_negative_section = validate_video_motion_prompt(
            "The camera slowly pushes in while the duck remains still.\n\n"
            f"NEGATIVE PROMPT:\n{DEFAULT_VIDEO_NEGATIVE_PROMPT}"
        )
        self.assertTrue(safe_with_negative_section["passed"])
        unsafe = validate_video_motion_prompt("The duck rides down the highway and talks to camera.")
        self.assertFalse(unsafe["passed"])
        self.assertIn("rides", unsafe["disallowed_motion_terms"])
        self.assertIn("talks", unsafe["disallowed_motion_terms"])

        with session_scope(factory) as session:
            product = ProductRecord(name="Video Duck")
            session.add(product)
            session.flush()
            source = AssetRecord(
                product_id=product.id,
                name="Video source",
                asset_type="source photo",
                source_path=source_path.as_posix(),
                preview_path=source_path.as_posix(),
                readiness_state="ready",
                review_state="approved",
                default_reference=1,
            )
            session.add(source)
            session.flush()

            video = register_video_output(
                session,
                product_id=product.id,
                source_asset_id=source.id,
                video_path=video_path,
                title="Video Duck pilot",
                prompt="The camera slowly pushes in while road lights pass in the background. The duck remains still.",
                duration_seconds=8,
                aspect_ratio="9:16",
                resolution="1080p",
            )
            self.assertEqual(video.asset_type, "generated product video")
            self.assertEqual(video.asset_role, "social video option")
            self.assertEqual(video.mime_type, "video/mp4")
            self.assertEqual(video.review_state, "needs review")
            self.assertIn(DEFAULT_VIDEO_NEGATIVE_PROMPT, video.notes)

    def test_long_art_studio_video_uses_seedance_default_model(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)
        source_path = Path(tmp.name) / "source.png"
        source_path.write_bytes(tiny_png_bytes("#0ea5e9"))

        with session_scope(factory) as session:
            product = ProductRecord(name="Long Clip Duck")
            session.add(product)
            session.flush()
            source = AssetRecord(
                product_id=product.id,
                name="Long clip source",
                asset_type="generated video art board",
                asset_role="video opening card",
                source_path=source_path.as_posix(),
                preview_path=source_path.as_posix(),
                readiness_state="needs human review",
                review_state="needs review",
            )
            session.add(source)
            session.flush()

            job = enqueue_video_generation(session, product.id, source.id, duration_seconds=10, aspect_ratio="9:16", resolution="1080p")
            self.assertEqual(job.model_name, "bytedance-seedance-pro-2.0")

    def test_products_queue_social_images_from_default_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "products-social-images.sqlite"
            source_paths = [tmp_path / f"source-{index}.png" for index in range(1, 4)]
            for source_path in source_paths:
                source_path.write_bytes(tiny_png_bytes("#facc15"))
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = ProductRecord(name="Social Duck")
                session.add(product)
                session.flush()
                for index, source_path in enumerate(source_paths, start=1):
                    session.add(
                        AssetRecord(
                            product_id=product.id,
                            name=f"Social source {index}",
                            asset_type="source photo",
                            source_path=source_path.as_posix(),
                            preview_path=source_path.as_posix(),
                            readiness_state="ready",
                            review_state="approved",
                            default_reference=1,
                        )
                    )
                product_id = product.id

            client = app.test_client()
            page = client.get("/products")
            self.assertEqual(page.status_code, 200)
            self.assertIn(b"Social Images", page.data)
            self.assertIn(b"3 default refs", page.data)

            response = client.post(
                f"/products/{product_id}/social-images/queue",
                data={"option_number": "3"},
                follow_redirects=True,
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Queued 3 Social Worthy image jobs for Social Duck.", response.data)
            self.assertIn(b"Social image jobs", response.data)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                jobs = list(session.scalars(select(CreativeGenerationJobRecord).order_by(CreativeGenerationJobRecord.id)))
                self.assertEqual(len(jobs), 3)
                prompts = [job.prompt for job in jobs]
                for index, job in enumerate(jobs, start=1):
                    metadata = json.loads(job.response_metadata_json)
                    self.assertEqual(job.target_format, "art_studio_social_image")
                    self.assertEqual(metadata["option_number"], index)
                    self.assertEqual(len(metadata["reference_asset_ids"]), 3)
                    self.assertIn("@img1 primary visible product angle", job.prompt)
                    self.assertIn("@img2 identity lock side/profile angle", job.prompt)
                    self.assertIn("@img3 identity lock detail angle", job.prompt)
                    self.assertIn(f"Option {index}:", job.prompt)
                    self.assertIn("Social Duck", job.prompt)
                self.assertEqual(len(set(prompts)), 3)

    def test_video_studio_page_renders_video_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "art-studio.sqlite"
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            client = app.test_client()

            legacy_social = client.get("/art-studio?tab=social-images")
            self.assertEqual(legacy_social.status_code, 302)
            self.assertIn("/products", legacy_social.headers["Location"])

            video = client.get("/art-studio")
            self.assertEqual(video.status_code, 200)
            self.assertIn(b"Video Studio", video.data)
            self.assertNotIn(b">Social Images</a>", video.data)
            self.assertIn(b"Create product video", video.data)
            self.assertIn(b'data-duration-slider', video.data)
            self.assertIn(b'aspect-picker', video.data)
            self.assertIn(b'Motion template', video.data)
            self.assertIn(b'Dolly In', video.data)
            self.assertIn(b'Vertigo Zoom', video.data)
            self.assertIn(b'Fidelity-first flow', video.data)
            self.assertIn(b'Voice script', video.data)
            self.assertIn(b'serious and neutral', video.data)
            self.assertIn(b'type="hidden" name="resolution" value="1080p"', video.data)
            self.assertNotIn(b"1080p final", video.data)
            self.assertNotIn(b"Three-step flow", video.data)

    def test_art_studio_video_product_picker_includes_products_beyond_display_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "art-studio-products.sqlite"
            source_path = tmp_path / "source.png"
            source_path.write_bytes(tiny_png_bytes("#facc15"))
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                for index in range(35):
                    product = ProductRecord(name=f"Video Product {index:02d}")
                    session.add(product)
                    session.flush()
                    session.add(
                        AssetRecord(
                            product_id=product.id,
                            name=f"Reference {index:02d}",
                            asset_type="source photo",
                            source_path=source_path.as_posix(),
                            preview_path=source_path.as_posix(),
                            readiness_state="ready",
                            review_state="approved",
                            default_reference=1,
                        )
                    )

            response = app.test_client().get("/art-studio?tab=video")
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Video Product 00", response.data)
            self.assertIn(b"Video Product 34", response.data)

    def test_art_studio_video_product_picker_sorts_products_by_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "art-studio-video-sort.sqlite"
            source_path = tmp_path / "source.png"
            source_path.write_bytes(tiny_png_bytes("#22c55e"))
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                for name in ["Zulu Duck", "Alpha Duck", "Bravo Duck"]:
                    product = ProductRecord(name=name)
                    session.add(product)
                    session.flush()
                    session.add(
                        AssetRecord(
                            product_id=product.id,
                            name=f"{name} Reference",
                            asset_type="source photo",
                            source_path=source_path.as_posix(),
                            preview_path=source_path.as_posix(),
                            readiness_state="ready",
                            review_state="approved",
                            default_reference=1,
                        )
                    )

            response = app.test_client().get("/art-studio?tab=video")
            self.assertEqual(response.status_code, 200)
            page = response.data.decode("utf-8")
            self.assertLess(page.index("Alpha Duck"), page.index("Bravo Duck"))
            self.assertLess(page.index("Bravo Duck"), page.index("Zulu Duck"))


if __name__ == "__main__":
    unittest.main()
