from __future__ import annotations

from .models import CalendarEntry, ContentIdea, MarketingPlan, Recommendation, WeeklyReport


def render_plan_markdown(plan: MarketingPlan) -> str:
    sections = [
        "# MattMadeMe Marketing Plan",
        "",
        "## 30-Day Content Calendar",
        "",
        _calendar_table(plan.calendar),
        "",
        "## Instagram Post Ideas",
        "",
        _ideas(plan.instagram_posts),
        "",
        "## Facebook Post Ideas",
        "",
        _ideas(plan.facebook_posts),
        "",
        "## Instagram Reel Ideas",
        "",
        _ideas(plan.instagram_reels),
        "",
        "## Etsy Promotion Ideas",
        "",
        _ideas(plan.etsy_promotions),
        "",
        "## Blog Topic Ideas",
        "",
        _ideas(plan.blog_topics),
        "",
        "## Email Newsletter Ideas",
        "",
        _ideas(plan.email_newsletters),
        "",
        "## Recommendations",
        "",
        _recommendations(plan.recommendations),
    ]
    if plan.weekly_report:
        sections.extend(["", "## Weekly Marketing Report", "", _weekly_report(plan.weekly_report)])
    return "\n".join(sections).rstrip() + "\n"


def _calendar_table(entries: list[CalendarEntry]) -> str:
    lines = [
        "| Date | Platform | Type | Objective | CTA | Featured Product |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for entry in entries:
        lines.append(
            f"| {entry.date.isoformat()} | {entry.platform} | {entry.content_type} | "
            f"{entry.objective} | {entry.cta} | {entry.featured_product} |"
        )
    return "\n".join(lines)


def _ideas(ideas: list[ContentIdea]) -> str:
    return "\n".join(
        f"{idx}. **{idea.title}**\n"
        f"   Platform: {idea.platform}; Type: {idea.content_type}; Audience: {idea.audience}; "
        f"Product: {idea.featured_product}; Goal: {idea.business_goal}; CTA: {idea.cta}\n"
        f"   Angle: {idea.angle}"
        for idx, idea in enumerate(ideas, start=1)
    )


def _recommendations(recommendations: list[Recommendation]) -> str:
    return "\n".join(
        f"{idx}. **{rec.title}**\n"
        f"   Goal: {rec.aligned_business_goal}; Impact: {rec.impact_estimate}; Effort: {rec.effort_estimate}\n"
        f"   Rationale: {rec.rationale}\n"
        f"   Next step: {rec.next_step}"
        for idx, rec in enumerate(recommendations, start=1)
    )


def _weekly_report(report: WeeklyReport) -> str:
    return "\n".join(
        [
            f"Week: {report.week_start.isoformat()} to {report.week_end.isoformat()}",
            "",
            "### Planned Activities",
            *[f"- {item}" for item in report.planned_activities],
            "",
            "### Recommended Actions",
            *[f"- {item}" for item in report.recommended_actions],
            "",
            "### Opportunities",
            *[f"- {item}" for item in report.opportunities],
            "",
            "### Seasonal Opportunities",
            *[f"- {item}" for item in report.seasonal_opportunities],
            "",
            "### Priorities",
            *[f"- {item}" for item in report.priorities],
        ]
    )

