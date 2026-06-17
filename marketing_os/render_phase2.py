from __future__ import annotations

from .models import Phase2MarketingPlan, ValidationIssue


def render_phase2_plan_markdown(plan: Phase2MarketingPlan) -> str:
    sections = [
        "# MattMadeMe Phase 2 Marketing Plan",
        "",
        f"Mode: `{plan.mode}`",
        "",
        f"Weekly theme: {plan.weekly_theme}",
        "",
        f"Campaign narrative: {plan.campaign_narrative}",
        "",
        "## Validation Report",
        "",
        _validation(plan.validation_report.issues),
        "",
        "## 30-Day Calendar",
        "",
        _calendar(plan),
        "",
        "## Ready-To-Edit Content Drafts",
        "",
        _content(plan),
        "",
        "## Recommendations",
        "",
        _recommendations(plan),
        "",
        "## Weekly Action List",
        "",
        _actions(plan),
        "",
        "## Manual Weekly Review Template",
        "",
        _review(plan),
    ]
    return "\n".join(sections).rstrip() + "\n"


def _validation(issues: list[ValidationIssue]) -> str:
    if not issues:
        return "No validation issues found."
    lines = ["| Severity | Code | Item | Message |", "| --- | --- | --- | --- |"]
    for issue in issues:
        lines.append(f"| {issue.severity} | {issue.code} | {issue.item_title or ''} | {issue.message} |")
    return "\n".join(lines)


def _calendar(plan: Phase2MarketingPlan) -> str:
    lines = [
        "| Date | Priority | Platform | Type | Goal | Audience | Product | CTA | Asset | Metric |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in plan.calendar:
        lines.append(
            f"| {item.date.isoformat()} | {item.priority} | {item.platform} | {item.content_type} | "
            f"{item.business_goal} | {item.target_audience} | {item.featured_product} | {item.cta} | "
            f"{item.asset_type} | {item.success_metric} |"
        )
    return "\n".join(lines)


def _content(plan: Phase2MarketingPlan) -> str:
    lines: list[str] = []
    for idx, item in enumerate(plan.calendar, start=1):
        lines.extend(
            [
                f"### {idx}. {item.title}",
                "",
                f"- Platform: {item.platform}",
                f"- Type: {item.content_type}",
                f"- Goal: {item.business_goal}",
                f"- Objective: {item.objective}",
                f"- Audience: {item.target_audience}",
                f"- Product: {item.featured_product}",
                f"- Priority: {item.priority}",
                f"- Effort: {item.effort_estimate}",
                f"- Expected impact: {item.expected_impact}",
                f"- CTA: {item.cta}",
                f"- Hashtags: {' '.join(item.hashtags) if item.hashtags else 'n/a'}",
                f"- Asset brief: {item.asset_brief}",
                f"- Production notes: {item.production_notes}",
                f"- Success metric: {item.success_metric}",
                "",
                "Draft copy:",
                "",
                item.draft_copy,
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def _recommendations(plan: Phase2MarketingPlan) -> str:
    lines: list[str] = []
    for idx, rec in enumerate(plan.recommendations, start=1):
        lines.extend(
            [
                f"### {idx}. {rec.title}",
                "",
                f"- Goal: {rec.aligned_business_goal}",
                f"- Impact: {rec.impact_estimate}",
                f"- Effort: {rec.effort_estimate}",
                f"- Estimated owner time: {rec.estimated_minutes} minutes",
                f"- Linked item: {rec.linked_item or 'n/a'}",
                f"- Why now: {rec.why_now}",
                f"- Rationale: {rec.rationale}",
                f"- Next action: {rec.next_step}",
                f"- Success metric: {rec.success_metric}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def _actions(plan: Phase2MarketingPlan) -> str:
    sections = ["must do", "should do", "optional", "blocked"]
    lines: list[str] = []
    for section in sections:
        lines.extend([f"### {section.title()}", ""])
        actions = [action for action in plan.weekly_actions if action.section == section]
        if not actions:
            lines.extend(["- None", ""])
            continue
        for action in actions:
            lines.append(
                f"- [{action.completion_status}] {action.owner_task} ({action.estimated_minutes} min). "
                f"Needs: {action.needed_asset_or_input}. Related: {action.related_item}."
            )
        lines.append("")
    return "\n".join(lines).rstrip()


def _review(plan: Phase2MarketingPlan) -> str:
    fields = plan.review_template.fields
    lines = [
        "| " + " | ".join(fields) + " |",
        "| " + " | ".join("---" for _ in fields) + " |",
    ]
    for row in plan.review_template.rows:
        lines.append("| " + " | ".join(row.get(field, "") for field in fields) + " |")
    return "\n".join(lines)

