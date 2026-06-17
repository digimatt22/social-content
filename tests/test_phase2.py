from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path

from marketing_os.context import load_business_context
from marketing_os.phase2 import build_phase2_plan, validate_phase2_plan
from marketing_os.render_phase2 import render_phase2_plan_markdown


class Phase2MarketingPlannerTests(unittest.TestCase):
    def test_structured_product_catalog_loads_and_excludes_commentary(self) -> None:
        context = load_business_context("docs/business")

        self.assertGreaterEqual(len(context.product_entities), 10)
        product_names = {product.name for product in context.product_entities}
        self.assertIn("Bingo Duck", product_names)
        self.assertNotIn(
            "Mailman Duck remains the lifetime leader, but last-90-day units are down 38% versus the prior 90 days.",
            product_names,
        )
        for product in context.product_entities:
            self.assertTrue(product.primary_audience)
            self.assertTrue(product.best_channels)
            self.assertTrue(product.use_cases)
            self.assertTrue(product.launch_priority)

    def test_structured_product_catalog_is_editable_without_code_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp_business = Path(tmp) / "business"
            temp_business.mkdir()
            for path in Path("docs/business").glob("*"):
                if path.is_file():
                    (temp_business / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

            catalog = temp_business / "product-catalog.json"
            text = catalog.read_text(encoding="utf-8")
            catalog.write_text(text.replace('"Bingo Duck"', '"Test Metadata Duck"', 1), encoding="utf-8")

            context = load_business_context(temp_business)
            self.assertIn("Test Metadata Duck", {product.name for product in context.product_entities})

    def test_phase2_standard_plan_has_required_fields_and_validates(self) -> None:
        plan = build_phase2_plan(start_date=date(2026, 6, 17), mode="standard")

        self.assertTrue(plan.validation_report.is_valid)
        self.assertTrue(plan.weekly_theme)
        self.assertTrue(plan.campaign_narrative)
        self.assertGreaterEqual(len(plan.calendar), 12)
        for item in plan.calendar:
            self.assertTrue(item.date)
            self.assertTrue(item.platform)
            self.assertTrue(item.content_type)
            self.assertTrue(item.business_goal)
            self.assertTrue(item.objective)
            self.assertTrue(item.target_audience)
            self.assertTrue(item.featured_product)
            self.assertTrue(item.cta)
            self.assertTrue(item.draft_copy)
            self.assertNotIn("show the tiny detail", item.draft_copy)
            self.assertTrue(item.asset_brief)
            self.assertTrue(item.production_notes)
            self.assertIn(item.priority, {"must do", "should do", "optional", "blocked"})
            self.assertIn(item.effort_estimate, {"low", "medium", "high"})
            self.assertIn(item.expected_impact, {"low", "medium", "high"})
            self.assertTrue(item.success_metric)

    def test_phase2_modes_change_cadence_and_support_launch(self) -> None:
        light = build_phase2_plan(start_date=date(2026, 6, 17), mode="light")
        standard = build_phase2_plan(start_date=date(2026, 6, 17), mode="standard")
        launch = build_phase2_plan(start_date=date(2026, 6, 17), mode="launch")

        self.assertEqual(len(light.calendar), 30)
        self.assertEqual(len(standard.calendar), 30)
        self.assertEqual(len(launch.calendar), 30)
        self.assertNotEqual([item.platform for item in light.calendar[:6]], [item.platform for item in standard.calendar[:6]])
        self.assertIn("launch", launch.campaign_narrative.lower())
        self.assertTrue(any(item.business_goal == "Promote New Duck Releases" for item in launch.calendar))

    def test_validation_catches_phase2_failures(self) -> None:
        context = load_business_context("docs/business")
        plan = build_phase2_plan(start_date=date(2026, 6, 17), mode="standard")
        bad_item = replace(
            plan.calendar[0],
            featured_product="Mailman Duck remains the lifetime leader, but last-90-day units are down 38% versus the prior 90 days.",
            asset_brief="",
            success_metric="",
            draft_copy="as a Add a duck to your flock",
        )
        report = validate_phase2_plan(context, [bad_item], plan.recommendations)
        codes = {issue.code for issue in report.issues}

        self.assertIn("invalid_product", codes)
        self.assertIn("product_looks_like_sentence", codes)
        self.assertIn("missing_asset_brief", codes)
        self.assertIn("missing_success_metric", codes)
        self.assertIn("awkward_brand_voice", codes)
        self.assertFalse(report.is_valid)

    def test_recommendations_are_operational(self) -> None:
        plan = build_phase2_plan(start_date=date(2026, 6, 17), mode="launch")

        self.assertGreaterEqual(len(plan.recommendations), 5)
        goals = {rec.aligned_business_goal for rec in plan.recommendations}
        self.assertIn("Grow Etsy Sales", goals)
        self.assertIn("Build An Owned Email List", goals)
        self.assertIn("Promote New Duck Releases", goals)
        self.assertTrue(any("Repeat" in rec.aligned_business_goal or "collector" in rec.title.lower() for rec in plan.recommendations))
        for rec in plan.recommendations:
            self.assertIn(rec.impact_estimate, {"low", "medium", "high"})
            self.assertIn(rec.effort_estimate, {"low", "medium", "high"})
            self.assertIsNotNone(rec.estimated_minutes)
            self.assertLessEqual(rec.estimated_minutes or 999, 30)
            self.assertTrue(rec.rationale)
            self.assertTrue(rec.why_now)
            self.assertTrue(rec.next_step)
            self.assertTrue(rec.success_metric)

    def test_weekly_actions_and_manual_review_template(self) -> None:
        plan = build_phase2_plan(start_date=date(2026, 6, 17), mode="standard")
        sections = {action.section for action in plan.weekly_actions}

        self.assertIn("must do", sections)
        self.assertIn("should do", sections)
        self.assertIn("optional", sections)
        self.assertIn("blocked", sections)
        for action in plan.weekly_actions:
            self.assertTrue(action.owner_task)
            self.assertTrue(action.related_item)
            self.assertGreater(action.estimated_minutes, 0)
            self.assertTrue(action.needed_asset_or_input)

        fields = set(plan.review_template.fields)
        self.assertIn("posted", fields)
        self.assertIn("skipped", fields)
        self.assertIn("post URL", fields)
        self.assertIn("Etsy visits or sales note", fields)
        self.assertIn("email signups note", fields)
        self.assertIn("lesson learned", fields)
        self.assertTrue(plan.review_template.rows)

    def test_phase2_render_contains_required_sections(self) -> None:
        plan = build_phase2_plan(start_date=date(2026, 6, 17), mode="standard")
        markdown = render_phase2_plan_markdown(plan)

        self.assertIn("## Validation Report", markdown)
        self.assertIn("## Ready-To-Edit Content Drafts", markdown)
        self.assertIn("## Weekly Action List", markdown)
        self.assertIn("## Manual Weekly Review Template", markdown)
        self.assertNotIn("as a Add a duck to your flock", markdown)


if __name__ == "__main__":
    unittest.main()
