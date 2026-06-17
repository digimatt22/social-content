from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from marketing_os.context import load_business_context
from marketing_os.workflow import build_plan


class Phase1MarketingOsTests(unittest.TestCase):
    def test_business_context_loads_from_docs(self) -> None:
        context = load_business_context("docs/business")

        self.assertIn("docs/business/business-goals.md", context.source_files)
        self.assertGreaterEqual(len(context.products), 10)
        self.assertGreaterEqual(len(context.audiences), 5)
        self.assertGreaterEqual(len(context.business_goals), 5)
        self.assertTrue(any("Duck" in product for product in context.products))
        self.assertTrue(all(goal for goal in context.business_goals))

    def test_business_context_reflects_file_changes_without_code_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp_docs = Path(tmp) / "business"
            temp_docs.mkdir()
            for path in Path("docs/business").glob("*.md"):
                (temp_docs / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

            products = temp_docs / "products.md"
            products.write_text(
                products.read_text(encoding="utf-8") + "\n- Test Launch Duck\n",
                encoding="utf-8",
            )

            context = load_business_context(temp_docs)
            self.assertIn("Test Launch Duck", context.products)

    def test_plan_meets_required_generation_counts(self) -> None:
        plan = build_plan(start_date=date(2026, 6, 17))

        self.assertEqual(len(plan.calendar), 30)
        self.assertEqual(len(plan.instagram_posts), 30)
        self.assertEqual(len(plan.facebook_posts), 30)
        self.assertEqual(len(plan.instagram_reels), 10)
        self.assertEqual(len(plan.blog_topics), 10)
        self.assertEqual(len(plan.email_newsletters), 10)
        self.assertEqual(len(plan.etsy_promotions), 10)

    def test_calendar_entries_include_required_fields(self) -> None:
        plan = build_plan(start_date=date(2026, 6, 17))

        for entry in plan.calendar:
            self.assertTrue(entry.date)
            self.assertTrue(entry.platform)
            self.assertTrue(entry.content_type)
            self.assertTrue(entry.objective)
            self.assertTrue(entry.cta)
            self.assertTrue(entry.featured_product)

    def test_content_has_brand_voice_product_audience_and_cta(self) -> None:
        plan = build_plan(start_date=date(2026, 6, 17))

        for idea in plan.instagram_posts + plan.facebook_posts + plan.instagram_reels:
            self.assertIn("maker-led", idea.angle)
            self.assertTrue(idea.featured_product.endswith("Duck") or "Duck" in idea.featured_product)
            self.assertTrue(idea.audience)
            self.assertTrue(idea.cta)

    def test_recommendations_include_goal_impact_effort_and_rationale(self) -> None:
        plan = build_plan(start_date=date(2026, 6, 17))
        context = load_business_context("docs/business")
        goals = set(context.business_goals)

        self.assertGreaterEqual(len(plan.recommendations), 5)
        for recommendation in plan.recommendations:
            self.assertIn(recommendation.aligned_business_goal, goals)
            self.assertIn(recommendation.impact_estimate, {"low", "medium", "high"})
            self.assertIn(recommendation.effort_estimate, {"low", "medium", "high"})
            self.assertTrue(recommendation.rationale)

    def test_weekly_report_has_required_sections(self) -> None:
        plan = build_plan(start_date=date(2026, 6, 17))
        report = plan.weekly_report

        self.assertIsNotNone(report)
        assert report is not None
        self.assertTrue(report.planned_activities)
        self.assertTrue(report.recommended_actions)
        self.assertTrue(report.opportunities)
        self.assertTrue(report.seasonal_opportunities)

    def test_demo_workflow_executes_successfully(self) -> None:
        result = subprocess.run(
            [sys.executable, "demo.py"],
            check=False,
            text=True,
            capture_output=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Demo workflow completed successfully", result.stdout)
        self.assertTrue(Path("outputs/demo-marketing-plan.md").exists())


if __name__ == "__main__":
    unittest.main()
