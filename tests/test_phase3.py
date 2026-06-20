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
    task_asset_options,
    today_view,
    week_agenda,
)
from marketing_os.services.content_briefs import (
    build_content_brief,
    create_planned_content_item,
    create_task_from_planned_content,
    localize_planned_content_reference_assets,
    planned_items_needing_production,
    produce_content_for_item,
    record_candidate_review,
    register_generated_copy_candidate,
    register_uploaded_image_option,
)
from marketing_os.services.creative_generation import import_manual_generated_output, review_creative_generation_job
from marketing_os.services.etsy_import import sync_etsy_read_only
from marketing_os.services.insights import build_learning_summary, serialize_learning_summary
from marketing_os.services.skill_adapters import copywriter_contract, image_option_from_contract, social_media_art_director_contracts
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
            self.assertIn(b"Posting Guides", guides.data)
            self.assertIn(b"Instagram Reel", guides.data)

            completed = client.get("/completed")
            self.assertEqual(completed.status_code, 200)
            self.assertIn(b"Completed", completed.data)

            assets = client.get("/assets")
            self.assertEqual(assets.status_code, 200)
            self.assertIn(b"Assets", assets.data)
            self.assertIn(b"Upload Source Photo", assets.data)
            self.assertIn(b"Upload source photo", assets.data)
            self.assertNotIn(b"Register source photo", assets.data)
            self.assertNotIn(b"Photo path", assets.data)
            self.assertNotIn(b"Add Generated or Uploaded Image", assets.data)
            self.assertNotIn(b"Prepare Generation Runs", assets.data)
            self.assertNotIn(b"Generation Jobs", assets.data)
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

            products_page = client.get("/products")
            self.assertEqual(products_page.status_code, 200)
            self.assertIn(b"Products", products_page.data)
            self.assertIn(b"Sync Etsy", products_page.data)
            self.assertNotIn(b"Sync website", products_page.data)
            self.assertNotIn(b"Match duplicate products", products_page.data)
            self.assertIn(b"data-tag-combobox", products_page.data)
            self.assertIn(b"data-tag-suggestions", products_page.data)
            self.assertIn(b"Save default references", products_page.data)
            self.assertIn(b"Use for automation", products_page.data)
            self.assertNotIn(b"Local product tag", products_page.data)
            self.assertNotIn(b"Local product tags", products_page.data)
            self.assertIn(b"Description", products_page.data)
            self.assertIn(b"See more", products_page.data)
            self.assertIn(b'<div class="copybox description-preview"><span>Long imported description.', products_page.data)
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
            self.assertIn(b"Metrics Due", metrics_due.data)
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

            rerun = produce_content_for_item(session, item)
            self.assertEqual(rerun.created, 0)
            self.assertEqual(rerun.skipped, 0)
            candidates = session.scalars(select(GeneratedContentCandidateRecord)).all()
            self.assertEqual(len(candidates), 0)
            self.assertIn("Image generation is queued", item.production_error)
            self.assertIn("3 social-media-art-director requests", item.production_error)
            self.assertIn("Copy generation is queued", item.production_error)

            health = data_health(session)
            self.assertFalse(any(row.area == "Content Production" and row.count >= 1 for row in health))

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
            self.assertEqual(item.status, "waiting_image_generation")

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
            self.assertIn(b"Step 1", planning_page.data)
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
            self.assertIn(b"Delete", rendered_review.data)
            self.assertIn(b"Upload image option", rendered_review.data)
            self.assertIn(b"Waiting for generation", rendered_review.data)
            self.assertIn(b"Regenerate images", rendered_review.data)
            self.assertIn(b"Create posting task", rendered_review.data)
            self.assertIn(b"disabled>Create posting task", rendered_review.data)
            self.assertNotIn(b"Run queued copy generation now", rendered_review.data)
            self.assertNotIn(b"Review state", rendered_review.data)
            self.assertNotIn(b"Reviewed by", rendered_review.data)
            self.assertNotIn(b"Approved copy", rendered_review.data)

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
            self.assertIn(b"Use this image", upload_response.data)
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

            calendar_page = client.get("/calendar")
            self.assertEqual(calendar_page.status_code, 200)
            self.assertIn(b"Planned Intent", calendar_page.data)
            self.assertIn(b"Review in Planning", calendar_page.data)

            second_response = client.post(f"/api/planned-content/{item_id}/produce", json={})
            self.assertEqual(second_response.status_code, 200)
            self.assertEqual(second_response.get_json()["created"], 0)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                item = session.get(PlannedContentRecord, item_id)
                candidate_id = self.register_agent_copy(session, item).id
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

            rewrite_response = client.post(
                f"/planning/{item_id}/regenerate",
                data={"target": "copy", "feedback": "Make it warmer and shorter."},
                follow_redirects=True,
            )
            self.assertEqual(rewrite_response.status_code, 200)
            self.assertIn(b"data-show-panel=\"copy-", rewrite_response.data)
            self.assertIn(b"disabled>Edit", rewrite_response.data)
            self.assertIn(b"disabled>Rewrite", rewrite_response.data)
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
                self.assertEqual(len(export_payload["generated_content_candidates"]), 2)
                reviewed_candidate = next(record for record in export_payload["generated_content_candidates"] if record["id"] == candidate_id)
                self.assertEqual(reviewed_candidate["reviewed_by"], "Matt")
                self.assertIsNotNone(reviewed_candidate["reviewed_at"])
                planned_task = next(record for record in export_payload["tasks"] if record["planned_content_item_id"] == item_id)
                self.assertEqual(planned_task["generated_content_candidate_id"], candidate_id)

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
            self.assertIn(b'<div class="wizard-step active" data-step="2">', missing_reference_page.data)
            self.assertIn(b'<span class="active" data-progress-step="2">2</span>', missing_reference_page.data)
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
            self.assertEqual(len(summary["image_request_files"]), 1)
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
            request_path = Path(summary["image_request_files"][0])
            self.assertTrue(request_path.is_file())
            request_payload = json.loads(request_path.read_text(encoding="utf-8"))
            self.assertEqual(request_payload["planned_item_id"], item_id)
            self.assertEqual(len(request_payload["options"]), 3)
            self.assertEqual([option["skill_request"]["option_number"] for option in request_payload["options"]], [1, 2, 3])

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
                self.assertEqual(item.status, "waiting_content_generation")
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

            copy_manifest = {
                "planned_item_id": item_id,
                "provider": "codex_agent",
                "copy_text": "Who needs Bingo Duck in their flock?\n\nThis tiny 3D printed duck is ready for a shelf, desk, or gift box.\n\nWho would you give this one to?",
                "skill_request": copy_payload["workflow"]["writing_request"]["input"],
                "skill_check": copy_payload["workflow"]["contract_check"],
                "social_strategy": {"skill": "social-media-strategist", "social_angle": "community_prompt"},
                "social_challenge": {"skill": "social-media-copy-chief", "status": "ready_for_human_review"},
            }
            copy_manifest_path = request_path.parent / "register-copy.json"
            copy_manifest_path.write_text(json.dumps(copy_manifest, indent=2), encoding="utf-8")
            copy_registered = run_register_generated_copy_job(db_path=db_path, manifest_path=copy_manifest_path)
            self.assertEqual(copy_registered["planned_item_id"], item_id)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                item = session.get(PlannedContentRecord, item_id)
                self.assertEqual(item.status, "needs_review")
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
                destinations = [json_list(item.destinations_json)[0] for item in items]
                self.assertIn("Instagram", destinations)
                self.assertIn("Pinterest", destinations)
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
            self.assertIn(b"Matt-approved Facebook copy", page.data)
            self.assertIn(b"Matt-approved generated creative", page.data)
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
                self.assertIn("waiting for Matt review", creative_item["message"])
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
                self.assertIn("Matt-approved Facebook copy", markdown)
                self.assertIn("Matt-approved generated creative", markdown)
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
            self.assertIn(b"Required when approving for Phase 5 proof", page.data)
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


if __name__ == "__main__":
    unittest.main()
