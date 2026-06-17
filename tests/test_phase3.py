from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from sqlalchemy import select

from marketing_os.db import create_db_engine, init_db, session_factory, session_scope
from marketing_os.db_models import AssetRecord, MetricRecord, PlanRecord, ProductRecord, TaskRecord, TemplateRecord
from marketing_os.phase3 import (
    TASK_STATUSES,
    add_metric,
    ensure_default_plan,
    generate_and_persist_plan,
    json_list,
    seed_database,
    update_task_status,
)
from marketing_os.web_app import create_app


class Phase3LocalWebConsoleTests(unittest.TestCase):
    def build_session(self):
        tmp = tempfile.TemporaryDirectory()
        db_path = Path(tmp.name) / "phase3.sqlite"
        engine = create_db_engine(db_path)
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

    def test_web_app_renders_operator_workflow_and_persists_forms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "web.sqlite"
            app = create_app(db_path)
            client = app.test_client()

            health = client.get("/health")
            self.assertEqual(health.status_code, 200)

            dashboard = client.get("/")
            self.assertEqual(dashboard.status_code, 200)
            self.assertIn(b"Today", dashboard.data)
            self.assertIn(b"Active Plan", dashboard.data)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                task = session.scalars(select(TaskRecord).order_by(TaskRecord.id)).first()
                self.assertIsNotNone(task)
                task_id = task.id

            detail = client.get(f"/tasks/{task_id}")
            self.assertEqual(detail.status_code, 200)
            self.assertIn(b"Posting Steps", detail.data)
            self.assertIn(b"Preview Checklist", detail.data)
            self.assertIn(b"Metric To Record Later", detail.data)

            status_response = client.post(
                f"/tasks/{task_id}/status",
                data={"status": "posted", "notes": "Posted through web test."},
                follow_redirects=True,
            )
            self.assertEqual(status_response.status_code, 200)

            metric_response = client.post(
                f"/tasks/{task_id}/metrics",
                data={"reach": "88", "likes": "12", "comments": "2", "notes": "Recorded manually."},
                follow_redirects=True,
            )
            self.assertEqual(metric_response.status_code, 200)

            with session_scope(app.config["SESSION_FACTORY"]) as session:
                task = session.get(TaskRecord, task_id)
                metric = session.scalar(select(MetricRecord).where(MetricRecord.task_id == task_id))
                self.assertEqual(task.status, "metrics needed")
                self.assertEqual(metric.reach, 88)


if __name__ == "__main__":
    unittest.main()
