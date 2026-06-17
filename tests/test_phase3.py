from __future__ import annotations

import io
import json
import plistlib
import tempfile
import unittest
from datetime import date
from pathlib import Path

from sqlalchemy import select

from marketing_os.db import create_db_engine, init_db, session_factory, session_scope
from marketing_os.db_models import (
    AssetRecord,
    BlogPostRecord,
    CreativeGenerationJobRecord,
    GeneratedContentCandidateRecord,
    MetricRecord,
    PlanRecord,
    PlannedContentRecord,
    ProductRecord,
    SyncMetadata,
    TaskRecord,
    TemplateRecord,
)
from marketing_os.jobs.content_production import run as run_content_production_job
from marketing_os.jobs.phase5_readiness import run as run_phase5_readiness_job
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
    create_planned_content_item,
    create_task_from_planned_content,
    planned_items_needing_production,
    produce_content_for_item,
    record_candidate_review,
)
from marketing_os.services.copywriter import score_copy_against_voice
from marketing_os.services.creative_generation import import_manual_generated_output, review_creative_generation_job
from marketing_os.services.etsy_import import sync_etsy_read_only
from marketing_os.services.insights import build_learning_summary, serialize_learning_summary
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


class Phase3LocalWebConsoleTests(unittest.TestCase):
    def build_session(self):
        tmp = tempfile.TemporaryDirectory()
        db_path = Path(tmp.name) / "phase3.sqlite"
        engine = create_db_engine(db_path)
        self.addCleanup(engine.dispose)
        init_db(engine)
        factory = session_factory(engine)
        return tmp, factory

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

            second_task = next(item for item in plan.tasks if item.id != task_id and item.owner_role == "social operator")
            complete_task_status(session, second_task.id, "mark_posted", notes="Posted without URL.")
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
            app = create_app(db_path)
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

            creative_assets = client.get("/creative-assets")
            self.assertEqual(creative_assets.status_code, 200)
            self.assertIn(b"Creative Assets", creative_assets.data)

            assets = client.get("/assets")
            self.assertEqual(assets.status_code, 200)
            self.assertIn(b"Register Source Photo", assets.data)
            self.assertIn(b"Upload source photo", assets.data)
            self.assertIn(b"Used by", assets.data)

            upload_response = client.post(
                "/assets/upload-source",
                data={
                    "photo": (io.BytesIO(b"fake image bytes"), "upload-bingo.jpg"),
                    "name": "Uploaded web source",
                },
                content_type="multipart/form-data",
                follow_redirects=True,
            )
            self.assertEqual(upload_response.status_code, 200)
            self.assertIn(b"Uploaded source photo", upload_response.data)

            settings = client.get("/settings")
            self.assertEqual(settings.status_code, 200)
            self.assertIn(b"Export JSON", settings.data)
            self.assertIn(b"JSON exports", settings.data)

            export_response = client.post("/settings/export")
            self.assertEqual(export_response.status_code, 200)
            self.assertEqual(export_response.mimetype, "application/json")
            export_payload = json.loads(export_response.data.decode("utf-8"))
            self.assertEqual(export_payload["format"], "marketing_os_phase4_export")
            self.assertIn("products", export_payload)
            self.assertIn("tasks", export_payload)
            self.assertIn("assets", export_payload)
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
            app = create_app(db_path)
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

            creative_response = client.get("/api/creative-assets")
            self.assertEqual(creative_response.status_code, 200)
            creative_payload = creative_response.get_json()
            self.assertIn("plans", creative_payload)

    def test_phase4_json_api_mutations_reuse_task_services(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "api-mutations.sqlite"
            app = create_app(db_path)
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
            self.assertEqual(asset.external_source, "mattmademe_website")
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

    def test_phase5_web_manual_creative_import_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "phase5-creative.sqlite"
            source_path = Path(tmp) / "source.jpg"
            output_path = Path(tmp) / "generated.jpg"
            source_path.write_bytes(b"source image bytes")
            output_path.write_bytes(b"generated image bytes")

            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            client = app.test_client()

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
                source = register_local_source_photo(session, source_path, product_id=product.id, name="Web source")
                review_asset(session, source.id, "approved", "Source approved.")
                source_id = source.id

            page = client.get("/creative-assets")
            self.assertEqual(page.status_code, 200)
            self.assertIn(b"Import Magnific / MCP Output", page.data)

            response = client.post(
                "/api/creative-assets/manual-import",
                json={
                    "source_asset_id": source_id,
                    "output_path": output_path.as_posix(),
                    "target_format": "Square product card",
                    "prompt": "Preserve product accuracy.",
                    "provider": "magnific_manual",
                    "provider_job_id": "api-job-1",
                },
            )
            self.assertEqual(response.status_code, 201)
            self.assertIn("candidate_id", response.get_json())

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                jobs = session.scalars(select(CreativeGenerationJobRecord)).all()
                self.assertEqual(len(jobs), 1)
                self.assertEqual(jobs[0].provider_job_id, "api-job-1")
                job_id = jobs[0].id

            missing_reviewer_response = client.post(
                f"/api/creative-assets/jobs/{job_id}/review",
                json={
                    "review_state": "approved",
                    "review_notes": "Approval without proof.",
                },
            )
            self.assertEqual(missing_reviewer_response.status_code, 400)
            self.assertIn("reviewer", missing_reviewer_response.get_json()["error"])

            review_response = client.post(
                f"/api/creative-assets/jobs/{job_id}/review",
                json={
                    "review_state": "approved",
                    "review_notes": "Matt approved the generated candidate.",
                    "reviewed_by": "Matt",
                },
            )
            self.assertEqual(review_response.status_code, 200)
            review_payload = review_response.get_json()["job"]
            self.assertEqual(review_payload["review_state"], "approved")
            self.assertEqual(review_payload["reviewed_by"], "Matt")
            self.assertIsNotNone(review_payload["reviewed_at"])

    def test_phase5_web_generated_output_upload_imports_for_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "phase5-upload.sqlite"
            source_path = Path(tmp) / "source.jpg"
            generated_root = Path(tmp) / "generated"
            source_path.write_bytes(b"source image bytes")

            app = create_app(db_path)
            app.config["GENERATED_OUTPUT_ROOT"] = generated_root
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            client = app.test_client()

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Mailman Duck"))
                source = register_local_source_photo(session, source_path, product_id=product.id, name="Upload source")
                review_asset(session, source.id, "approved", "Source approved.")
                source_id = source.id

            page = client.get("/creative-assets")
            self.assertEqual(page.status_code, 200)
            self.assertIn(b"Upload generated file", page.data)

            response = client.post(
                "/creative-assets/manual-import",
                data={
                    "source_asset_id": str(source_id),
                    "output_file": (io.BytesIO(b"generated image bytes"), "magnific-output.png"),
                    "target_format": "Facebook post image",
                    "prompt": "Preserve product accuracy.",
                    "provider": "magnific_mcp",
                    "model_name": "Magnific MCP",
                    "provider_job_id": "upload-job-1",
                    "requested_dimensions": "1080x1080",
                    "notes": "Uploaded generated output for review.",
                },
                content_type="multipart/form-data",
                follow_redirects=False,
            )
            self.assertEqual(response.status_code, 302)

            saved_files = list(generated_root.glob("*-magnific-output.png"))
            self.assertEqual(len(saved_files), 1)
            self.assertEqual(saved_files[0].read_bytes(), b"generated image bytes")

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                jobs = session.scalars(select(CreativeGenerationJobRecord)).all()
                self.assertEqual(len(jobs), 1)
                self.assertEqual(jobs[0].provider, "magnific_mcp")
                self.assertEqual(jobs[0].provider_job_id, "upload-job-1")
                self.assertEqual(jobs[0].review_state, "needs_review")
                self.assertEqual(jobs[0].output_path, saved_files[0].as_posix())
                self.assertIsNotNone(jobs[0].candidate_asset_id)

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
            products = list(session.scalars(select(ProductRecord).order_by(ProductRecord.name).limit(2)))
            item = create_planned_content_item(
                session,
                calendar_date=date(2026, 6, 25),
                destinations=["Facebook", "Pinterest"],
                goals=["Sales growth", "Followers"],
                product_ids=[product.id for product in products],
                audience="gift buyers",
                occasion="summer launch",
                notes="Keep it conversational.",
            )
            self.assertEqual(item.status, "planned")
            self.assertEqual(len(planned_items_needing_production(session)), 1)

            result = produce_content_for_item(session, item)
            self.assertEqual(result.created, 2)
            self.assertEqual(item.status, "needs_review")
            self.assertEqual(item.brief_status, "ready")
            self.assertTrue(all(candidate.review_state == "needs_review" for candidate in result.candidates))
            facebook = next(candidate for candidate in result.candidates if candidate.candidate_type == "facebook_post")
            facebook_body = json.loads(facebook.body)
            self.assertIn("body", facebook_body)
            self.assertNotIn(facebook_body["hook"], facebook_body["body"])
            self.assertNotIn("..", facebook_body["body"])
            self.assertNotIn("Planning note:", facebook_body["body"])
            self.assertNotIn("Keep it conversational.", facebook_body["body"])
            self.assertNotIn("Phase 5", facebook_body["body"])
            self.assertNotIn("proof draft", facebook_body["body"].lower())
            self.assertIn("quality_score", facebook_body)
            self.assertTrue(facebook_body["quality_score"]["passed"])
            self.assertFalse(
                any("planning notes" in warning.lower() for warning in facebook_body["quality_score"]["warnings"])
            )
            self.assertIn(products[0].name, facebook.source_facts_json)
            self.assertIn("Keep it conversational.", facebook.source_facts_json)

            rerun = produce_content_for_item(session, item)
            self.assertEqual(rerun.created, 0)
            self.assertEqual(rerun.skipped, 2)
            candidates = session.scalars(select(GeneratedContentCandidateRecord)).all()
            self.assertEqual(len(candidates), 2)

            health = data_health(session)
            self.assertTrue(any(row.area == "Content Production" and row.count >= 1 for row in health))

    def test_phase5_content_production_picks_up_rewrite_requests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "phase5-rewrite.sqlite"
            app = create_app(db_path)
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
                result = produce_content_for_item(session, item)
                facebook = next(candidate for candidate in result.candidates if candidate.candidate_type == "facebook_post")
                facebook.body = "stale draft that should be replaced"
                record_candidate_review(session, facebook.id, "rewrite_requested", "Too generic; make it warmer.", reviewed_by="Matt")
                item_id = item.id
                candidate_id = facebook.id

            dry_run = run_content_production_job(db_path=db_path, dry_run=True, export_briefs_dir=Path(tmp) / "briefs")
            self.assertEqual(len(dry_run["items"]), 1)
            brief_path = Path(dry_run["items"][0]["brief_export_path"])
            rewrite_brief = json.loads(brief_path.read_text(encoding="utf-8"))
            self.assertEqual(rewrite_brief["rewrite_requests"][0]["candidate_id"], candidate_id)
            self.assertEqual(rewrite_brief["rewrite_requests"][0]["revision_notes"], "Too generic; make it warmer.")
            self.assertEqual(rewrite_brief["rewrite_requests"][0]["previous_copy_text"], "stale draft that should be replaced")

            summary = run_content_production_job(db_path=db_path, export_briefs_dir=Path(tmp) / "briefs")
            self.assertEqual(summary["processed"], 1)
            self.assertEqual(summary["created"], 0)
            self.assertTrue(summary["items"][0]["rewrite_requested"])
            self.assertTrue(summary["items"][0]["forced"])

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                rewritten = session.get(GeneratedContentCandidateRecord, candidate_id)
                self.assertEqual(rewritten.review_state, "needs_review")
                self.assertNotEqual(rewritten.body, "stale draft that should be replaced")
                self.assertIn("Bingo Duck", rewritten.body)
                self.assertIn("Too generic; make it warmer.", rewritten.source_facts_json)
                self.assertNotIn(item_id, [item.id for item in planned_items_needing_production(session)])

    def test_phase5_content_production_runner_and_launchagent_template(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        runner = repo_root / "scripts" / "run-content-production.sh"
        plist_path = repo_root / "docs" / "automation" / "com.mattmademe.marketing-os.content-production.plist"

        self.assertTrue(runner.is_file())
        self.assertIn("marketing_os.jobs.content_production", runner.read_text(encoding="utf-8"))
        self.assertTrue(plist_path.is_file())

        plist = plistlib.loads(plist_path.read_bytes())
        self.assertEqual(plist["Label"], "com.mattmademe.marketing-os.content-production")
        self.assertEqual(plist["WorkingDirectory"], "/Users/matt/Documents/marketing-os")
        self.assertIn("/Users/matt/Documents/marketing-os/scripts/run-content-production.sh", plist["ProgramArguments"])
        self.assertEqual(len(plist["StartCalendarInterval"]), 5)
        self.assertTrue(all(item["Hour"] == 2 and item["Minute"] == 30 for item in plist["StartCalendarInterval"]))

    def test_phase5_copy_quality_score_flags_internal_notes_and_unsupported_terms(self) -> None:
        score = score_copy_against_voice(
            "Planning note: Keep it conversational. This rubber duck is a licensed official Disney guaranteed bestseller. #one #two #three #four",
            {
                "products": ["Mailman Duck"],
                "notes": "Planning note: Keep it conversational.",
                "avoid": ["licensed"],
            },
        )

        self.assertTrue(any("planned product" in warning for warning in score.warnings))
        self.assertTrue(any("planning notes" in warning for warning in score.warnings))
        self.assertTrue(any("internal workflow" in warning for warning in score.warnings))
        self.assertTrue(any("unsupported" in warning for warning in score.warnings))
        self.assertTrue(any("hashtags" in warning.lower() for warning in score.warnings))

    def test_phase5_planned_intent_creates_posting_task_after_candidate_approval(self) -> None:
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
            result = produce_content_for_item(session, item)
            facebook = next(candidate for candidate in result.candidates if candidate.candidate_type == "facebook_post")

            with self.assertRaisesRegex(ValueError, "Approve"):
                create_task_from_planned_content(session, item.id, destination="Facebook", candidate_id=facebook.id)

            record_candidate_review(session, facebook.id, "approved", "Ready for task creation.", reviewed_by="Matt")
            task_result = create_task_from_planned_content(session, item.id, destination="Facebook", candidate_id=facebook.id)

            self.assertEqual(task_result.task.planned_content_item_id, item.id)
            self.assertEqual(task_result.task.generated_content_candidate_id, facebook.id)
            self.assertEqual(facebook.reviewed_by, "Matt")
            self.assertIsNotNone(facebook.reviewed_at)
            self.assertEqual(task_result.task.platform, "Facebook")
            self.assertEqual(task_result.task.content_type, "post")
            self.assertEqual(task_result.task.product_name, product.name)
            self.assertIn(product.name, task_result.task.draft_caption)
            self.assertEqual(item.status, "approved")

    def test_phase5_web_planning_api_and_job_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "phase5-web.sqlite"
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            client = app.test_client()

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                products = list(session.scalars(select(ProductRecord).order_by(ProductRecord.name).limit(2)))
                product_ids = [product.id for product in products]

            planning_page = client.get("/planning")
            self.assertEqual(planning_page.status_code, 200)
            self.assertIn(b"New Planned Item", planning_page.data)
            self.assertIn(b"Product Focus", planning_page.data)

            response = client.post(
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
            self.assertEqual(response.status_code, 201)
            item_id = response.get_json()["planned_item"]["id"]

            produce_response = client.post(f"/api/planned-content/{item_id}/produce", json={})
            self.assertEqual(produce_response.status_code, 200)
            payload = produce_response.get_json()
            self.assertEqual(payload["created"], 2)
            self.assertEqual(payload["planned_item"]["status"], "needs_review")
            self.assertTrue(any(candidate["candidate_type"] == "facebook_post" for candidate in payload["planned_item"]["candidates"]))
            facebook_payload = next(
                candidate
                for candidate in payload["planned_item"]["candidates"]
                if candidate["candidate_type"] == "facebook_post"
            )
            self.assertIn("copy_text", facebook_payload)
            self.assertIn(products[0].name, facebook_payload["copy_text"])
            self.assertNotIn("Quality checklist", facebook_payload["copy_text"])

            rendered_review = client.get("/planning")
            self.assertEqual(rendered_review.status_code, 200)
            self.assertIn(b"Facebook Post", rendered_review.data)
            self.assertIn(b"Copy post", rendered_review.data)
            self.assertIn(b"Review evidence", rendered_review.data)
            self.assertIn(b"Edit post copy", rendered_review.data)
            self.assertIn(b"Save review", rendered_review.data)
            self.assertIn(b"Required when approving generated copy", rendered_review.data)
            self.assertIn(b"Attach to task", rendered_review.data)

            calendar_page = client.get("/calendar")
            self.assertEqual(calendar_page.status_code, 200)
            self.assertIn(b"Planned Intent", calendar_page.data)
            self.assertIn(b"Review in Planning", calendar_page.data)

            second_response = client.post(f"/api/planned-content/{item_id}/produce", json={})
            self.assertEqual(second_response.status_code, 200)
            self.assertEqual(second_response.get_json()["created"], 0)

            candidate_id = next(
                candidate["id"]
                for candidate in payload["planned_item"]["candidates"]
                if candidate["candidate_type"] == "facebook_post"
            )
            edited_copy = (
                f"{products[0].name} is ready for a gift list.\n\n"
                "This edited Facebook draft keeps the warm MattMadeMe voice and mentions the product clearly.\n\n"
                "Tell me who would smile at this one."
            )
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
                item.status = "planned"

            summary = run_content_production_job(db_path=db_path, planned_item_id=item_id)
            self.assertEqual(summary["processed"], 1)
            self.assertEqual(summary["created"], 0)

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

    def test_phase5_content_production_exports_structured_briefs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "phase5-briefs.sqlite"
            export_dir = Path(tmp) / "briefs"
            source_path = Path(tmp) / "bingo-source.jpg"
            source_path.write_bytes(b"source image bytes")
            app = create_app(db_path)
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
            self.assertEqual(live_run["created"], 2)
            self.assertEqual(Path(live_run["items"][0]["brief_export_path"]), brief_path)
            self.assertTrue(all(candidate_id is not None for candidate_id in live_run["items"][0]["candidate_ids"]))

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                candidates = list(session.scalars(select(GeneratedContentCandidateRecord)))
                self.assertEqual(len(candidates), 2)
                self.assertTrue(all(str(source_id) in json_list(candidate.source_asset_ids_json) for candidate in candidates))
                prompt = next(candidate for candidate in candidates if candidate.candidate_type == "image_prompt_brief")
                self.assertIn(str(source_id), prompt.body)

    def test_phase5_learning_loop_links_generated_copy_to_outcomes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "phase5-learning.sqlite"
            app = create_app(db_path)
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
                result = produce_content_for_item(session, item)
                facebook = next(candidate for candidate in result.candidates if candidate.candidate_type == "facebook_post")
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
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            client = app.test_client()

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                product = session.scalar(select(ProductRecord).where(ProductRecord.name == "Bingo Duck"))
                product_id = product.id

            planned_response = client.post(
                "/api/planned-content",
                json={
                    "calendar_date": "2026-06-27",
                    "destinations": ["Facebook"],
                    "goals": ["Sales growth"],
                    "product_ids": [product_id],
                    "audience": "gift buyers",
                    "occasion": "new batch",
                    "notes": "Keep it conversational and specific.",
                },
            )
            self.assertEqual(planned_response.status_code, 201)
            item_id = planned_response.get_json()["planned_item"]["id"]

            production_response = client.post(f"/api/planned-content/{item_id}/produce", json={})
            self.assertEqual(production_response.status_code, 200)
            candidates = production_response.get_json()["planned_item"]["candidates"]
            candidate_id = next(candidate["id"] for candidate in candidates if candidate["candidate_type"] == "facebook_post")

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

            app = create_app(db_path)
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
                result = produce_content_for_item(session, item)
                facebook = next(candidate for candidate in result.candidates if candidate.candidate_type == "facebook_post")
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
                self.assertTrue(any(item.area == "Phase 5 Readiness" and item.status == "OK" for item in health))

    def test_phase5_approval_packet_exports_copy_and_creative_review_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "phase5-approval-packet.sqlite"
            source_path = Path(tmp) / "source.jpg"
            output_path = Path(tmp) / "generated.jpg"
            source_path.write_bytes(b"source image bytes")
            output_path.write_bytes(b"generated image bytes")

            app = create_app(db_path)
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
                result = produce_content_for_item(session, item)
                facebook = next(candidate for candidate in result.candidates if candidate.candidate_type == "facebook_post")
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
                self.assertIn("Open Creative Assets", creative_item["action"])
                self.assertEqual(payload["copy_review"]["id"], facebook.id)
                self.assertIn("copy_text", payload["copy_review"])
                self.assertIn("Bingo Duck", payload["copy_review"]["copy_text"])
                self.assertNotIn("Quality checklist", payload["copy_review"]["copy_text"])
                self.assertEqual(payload["creative_review"]["id"], creative.job.id)
                self.assertEqual(payload["creative_review"]["source_asset"]["id"], source.id)
                self.assertEqual(payload["creative_review"]["candidate_asset"]["id"], creative.candidate.id)
                self.assertIn("Matt-approved Facebook copy", markdown)
                self.assertIn("Matt-approved generated creative", markdown)
                self.assertIn("Final Proof Runbook", markdown)
                self.assertIn("/phase5-readiness#facebook-copy-review", markdown)
                self.assertIn(f"/creative-assets#creative-job-{creative.job.id}", markdown)
                self.assertIn("phase5_readiness --fail-on-incomplete", markdown)
                self.assertIn("Open Planning, review a Facebook candidate", markdown)
                self.assertIn("Open Creative Assets, compare the source and generated candidate", markdown)
                self.assertIn("Copyable Post", markdown)
                self.assertIn("Bingo Duck", markdown)
                self.assertIn("packet-job", markdown)
                self.assertIn("Creative Approval Checklist", markdown)
                self.assertIn("No invented markings", markdown)
                self.assertIn(source_path.as_posix(), markdown)
                self.assertIn(output_path.as_posix(), markdown)
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
            self.assertEqual(api_payload["creative_review"]["review_path"], f"/creative-assets#creative-job-{creative.job.id}")

            page = client.get("/phase5-readiness")
            self.assertEqual(page.status_code, 200)
            self.assertIn(f'href="/planning#candidate-{facebook.id}"'.encode(), page.data)
            self.assertIn(f'href="/creative-assets#creative-job-{creative.job.id}"'.encode(), page.data)
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

            creative_page = client.get("/creative-assets")
            self.assertEqual(creative_page.status_code, 200)
            self.assertIn(f'id="creative-job-{creative.job.id}"'.encode(), creative_page.data)
            self.assertIn(b"Generated candidate", creative_page.data)
            self.assertIn(b"Creative approval checklist", creative_page.data)
            self.assertIn(b"Required when approving generated creative", creative_page.data)
            self.assertIn(b"No invented markings", creative_page.data)
            self.assertIn(f'src="/assets/{source.id}/preview"'.encode(), creative_page.data)
            self.assertIn(f'src="/assets/{creative.candidate.id}/preview"'.encode(), creative_page.data)

            copy_review_response = client.post(
                f"/planning/candidates/{facebook.id}/review",
                data={"review_state": "needs_review", "revision_notes": "Still checking.", "reviewed_by": ""},
                follow_redirects=False,
            )
            self.assertEqual(copy_review_response.status_code, 302)
            self.assertTrue(copy_review_response.headers["Location"].endswith(f"/planning#candidate-{facebook.id}"))

            creative_review_response = client.post(
                f"/creative-assets/jobs/{creative.job.id}/review",
                data={"review_state": "needs_review", "review_notes": "Still checking.", "reviewed_by": ""},
                follow_redirects=False,
            )
            self.assertEqual(creative_review_response.status_code, 302)
            self.assertTrue(creative_review_response.headers["Location"].endswith(f"/creative-assets#creative-job-{creative.job.id}"))

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

            app = create_app(db_path)
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
                self.assertIn("/creative-assets?phase5_handoff=1#import-magnific-output", approval_markdown)
                self.assertIn("Phase 5 Creative Handoff", markdown)
                self.assertIn("Mailman source", markdown)
                self.assertIn("Preserve the duck's shape", markdown)
                self.assertTrue(export_path.is_file())
                self.assertIn("Import Back Into Marketing OS", export_path.read_text(encoding="utf-8"))

            api_response = client.get("/api/phase5-approval-packet")
            self.assertEqual(api_response.status_code, 200)
            packet = api_response.get_json()["packet"]
            self.assertIsNone(packet["creative_review"])
            self.assertIsNotNone(packet["creative_handoff"])
            self.assertEqual(packet["creative_handoff"]["source_asset"]["id"], source_id)
            self.assertIn("Mailman Duck", packet["creative_handoff"]["prompt"])
            self.assertIn("Preserve the duck's shape", packet["creative_handoff"]["prompt"])
            self.assertIn("Planning prompt context", packet["creative_handoff"]["prompt"])
            self.assertEqual(packet["creative_handoff"]["manual_import_path"], "/creative-assets")
            self.assertEqual(packet["creative_handoff"]["manual_import_query"], "/creative-assets?phase5_handoff=1#import-magnific-output")
            self.assertEqual(packet["creative_handoff"]["import_defaults"]["source_asset_id"], source_id)
            self.assertEqual(packet["creative_handoff"]["import_defaults"]["provider"], "magnific_mcp")

            page = client.get("/phase5-readiness")
            self.assertEqual(page.status_code, 200)
            self.assertIn(b"Magnific/MCP prompt handoff", page.data)
            self.assertIn(b"Mailman Duck", page.data)
            self.assertIn(b"Import prefilled handoff", page.data)
            self.assertIn(f'src="/assets/{source_id}/preview"'.encode(), page.data)
            self.assertIn(b"Copy source path", page.data)
            self.assertIn(b"Copy prompt", page.data)
            self.assertIn(b'action="/phase5-readiness/export-creative-handoff"', page.data)

            prefilled_page = client.get("/creative-assets?phase5_handoff=1")
            self.assertEqual(prefilled_page.status_code, 200)
            self.assertIn(b"Prefilled from Phase 5 creative handoff", prefilled_page.data)
            self.assertIn(f'value="{source_id}" selected'.encode(), prefilled_page.data)
            self.assertIn(b'value="magnific_mcp"', prefilled_page.data)
            self.assertIn(b"Preserve the duck&#39;s shape", prefilled_page.data)
            self.assertIn(b"outputs/magnific/mailman-source-facebook-post-image.png", prefilled_page.data)
            self.assertIn(f'src="/assets/{source_id}/preview"'.encode(), prefilled_page.data)
            self.assertIn(b"Copy source path", prefilled_page.data)
            self.assertIn(b"Copy prompt", prefilled_page.data)

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

            app = create_app(db_path)
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
                result = produce_content_for_item(session, item)
                facebook = next(candidate for candidate in result.candidates if candidate.candidate_type == "facebook_post")
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
                        "title": "Fixture Duck",
                        "url": "https://etsy.example/listing/etsy-100",
                        "state": "active",
                        "description": "A fixture listing for sync tests.",
                        "tags": ["gift", "duck"],
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
            seed_database(session)
            adapter = FakeEtsyAdapter()
            summary = sync_etsy_read_only(session, adapter=adapter)
            self.assertEqual(summary.products_imported, 1)
            self.assertEqual(summary.assets_imported, 1)
            self.assertEqual(adapter.calls, [("GET listings", "fixture-shop"), ("GET images", "etsy-100")])

            product = session.scalar(select(ProductRecord).where(ProductRecord.external_source == "etsy", ProductRecord.external_id == "etsy-100"))
            self.assertIsNotNone(product)
            self.assertEqual(product.canonical_url, "https://etsy.example/listing/etsy-100")
            self.assertEqual(product.sync_status, "imported")

            asset = session.scalar(select(AssetRecord).where(AssetRecord.external_source == "etsy", AssetRecord.external_id == "img-100"))
            self.assertIsNotNone(asset)
            self.assertEqual(asset.product_id, product.id)
            self.assertEqual(asset.review_state, "needs review")
            self.assertEqual(asset.file_exists, 0)

            sync = session.scalar(select(SyncMetadata).where(SyncMetadata.source_name == "etsy_api"))
            self.assertIsNotNone(sync)
            self.assertIn("Imported 1 listing", sync.notes)

            health = data_health(session)
            self.assertTrue(any(item.area == "Etsy Sync" and item.status == "OK" for item in health))

    def test_phase5_website_sync_imports_products_images_and_blog_posts(self) -> None:
        class FakeWebsiteAdapter:
            def list_products(self) -> list[dict[str, object]]:
                return [
                    {
                        "id": "web-200",
                        "name": "Website Fixture Duck",
                        "url": "https://mattmademe.example/products/web-200",
                        "status": "available",
                        "description": "Website product description.",
                        "tags": ["collector", "gift"],
                        "perfectFor": ["Duck collectors"],
                        "heroImageUrl": "https://mattmademe.example/images/web-200.jpg",
                    }
                ]

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
            summary = sync_mattmademe_website(session, adapter=FakeWebsiteAdapter())
            self.assertEqual(summary.products_imported, 1)
            self.assertEqual(summary.assets_imported, 1)
            self.assertEqual(summary.blog_posts_imported, 1)

            product = session.scalar(
                select(ProductRecord).where(ProductRecord.external_source == "mattmademe_website", ProductRecord.external_id == "web-200")
            )
            self.assertIsNotNone(product)
            self.assertEqual(product.status, "available")
            self.assertEqual(product.canonical_url, "https://mattmademe.example/products/web-200")

            asset = session.scalar(
                select(AssetRecord).where(
                    AssetRecord.external_source == "mattmademe_website",
                    AssetRecord.external_id == "https://mattmademe.example/images/web-200.jpg",
                )
            )
            self.assertIsNotNone(asset)
            self.assertEqual(asset.product_id, product.id)
            self.assertEqual(asset.review_state, "needs review")

            post = session.scalar(select(BlogPostRecord).where(BlogPostRecord.external_source == "mattmademe_website", BlogPostRecord.external_id == "blog-1"))
            self.assertIsNotNone(post)
            self.assertEqual(post.title, "Fixture Story")
            self.assertEqual(post.canonical_url, "https://mattmademe.example/blog/fixture-story")

            target = export_operating_data(session, Path(tmp.name) / "exports")
            payload = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["blog_posts"]), 1)
            self.assertEqual(payload["blog_posts"][0]["title"], "Fixture Story")

            health = data_health(session)
            self.assertTrue(any(item.area == "Website Sync" and item.status == "OK" for item in health))

    def test_phase5_web_settings_exposes_safe_sync_actions_without_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "phase5-integrations.sqlite"
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            client = app.test_client()

            settings = client.get("/settings")
            self.assertEqual(settings.status_code, 200)
            self.assertIn(b"Sync Etsy", settings.data)
            self.assertIn(b"Sync website", settings.data)

            etsy_response = client.post("/api/integrations/etsy/sync")
            self.assertEqual(etsy_response.status_code, 400)
            self.assertIn("credentials", etsy_response.get_json()["errors"][0])

            website_response = client.post("/api/integrations/website/sync")
            self.assertEqual(website_response.status_code, 400)
            self.assertIn("token", website_response.get_json()["errors"][0])

    def test_phase5_local_asset_library_scan_indexes_external_root(self) -> None:
        tmp, factory = self.build_session()
        self.addCleanup(tmp.cleanup)

        from PIL import Image

        asset_root = Path(tmp.name) / "MarketingAssets"
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
            asset_root = Path(tmp) / "MarketingAssets"
            product_dir = asset_root / "products" / "bingo-duck" / "source"
            product_dir.mkdir(parents=True)
            (product_dir / "photo.jpg").write_bytes(b"fake image bytes")

            app = create_app(db_path)
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
