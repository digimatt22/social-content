from __future__ import annotations

from datetime import date, timedelta

from .models import BusinessContext, CalendarEntry, Recommendation, WeeklyReport


class ReportBuilder:
    def __init__(self, context: BusinessContext):
        self.context = context

    def weekly_report(
        self,
        calendar: list[CalendarEntry],
        recommendations: list[Recommendation],
        week_start: date,
    ) -> WeeklyReport:
        week_end = week_start + timedelta(days=6)
        entries = [entry for entry in calendar if week_start <= entry.date <= week_end]
        planned = [
            f"{entry.date.isoformat()} - {entry.platform} {entry.content_type}: {entry.featured_product} ({entry.objective})"
            for entry in entries
        ]
        actions = [
            f"{rec.title} [{rec.aligned_business_goal}; impact={rec.impact_estimate}, effort={rec.effort_estimate}]"
            for rec in recommendations[:5]
        ]
        opportunities = [
            "Lean into products with current momentum before filling the calendar with evergreen posts.",
            "Add email-list CTAs to collector and new-release content.",
            "Use customer/community prompts to turn social posts into conversations, not just announcements.",
        ]
        seasonal = [
            f"Plan around {window}." for window in (self.context.seasonal_windows[:4] or ["new duck launch windows"])
        ]
        priorities = [
            "Publish the highest-impact, lowest-effort recommendation first.",
            "Keep new duck release content connected to Etsy sales and email capture.",
            "Review the next 7 days before adding more channels.",
        ]
        return WeeklyReport(
            week_start=week_start,
            week_end=week_end,
            planned_activities=planned,
            recommended_actions=actions,
            opportunities=opportunities,
            seasonal_opportunities=seasonal,
            priorities=priorities,
        )

