from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal


Impact = Literal["low", "medium", "high"]
Effort = Literal["low", "medium", "high"]
Priority = Literal["must do", "should do", "optional", "blocked"]


@dataclass(frozen=True)
class ProductEntity:
    name: str
    status: str
    primary_audience: str
    secondary_audiences: list[str]
    best_channels: list[str]
    use_cases: list[str]
    seasonality: list[str]
    sales_momentum_note: str
    launch_priority: str


@dataclass(frozen=True)
class BusinessContext:
    """Parsed business knowledge loaded from docs/business."""

    source_files: list[str]
    raw_markdown: dict[str, str]
    business_goals: list[str]
    products: list[str]
    momentum_products: list[str]
    upcoming_products: list[str]
    audiences: list[str]
    voice_pillars: list[str]
    useful_phrases: list[str]
    avoid: list[str]
    channels: list[str]
    seasonal_windows: list[str]
    product_entities: list[ProductEntity] = field(default_factory=list)
    etsy_url: str | None = None
    website_url: str | None = None


@dataclass(frozen=True)
class ContentIdea:
    platform: str
    content_type: str
    title: str
    angle: str
    audience: str
    featured_product: str
    business_goal: str
    cta: str


@dataclass(frozen=True)
class CalendarEntry:
    date: date
    platform: str
    content_type: str
    objective: str
    cta: str
    featured_product: str
    business_goal: str
    idea: str


@dataclass(frozen=True)
class Recommendation:
    title: str
    aligned_business_goal: str
    impact_estimate: Impact
    effort_estimate: Effort
    rationale: str
    next_step: str
    estimated_minutes: int | None = None
    why_now: str | None = None
    linked_item: str | None = None
    success_metric: str | None = None


@dataclass(frozen=True)
class Phase2ContentItem:
    title: str
    platform: str
    content_type: str
    business_goal: str
    objective: str
    target_audience: str
    featured_product: str
    draft_copy: str
    cta: str
    hashtags: list[str]
    asset_brief: str
    asset_type: str
    production_notes: str
    priority: Priority
    effort_estimate: Effort
    expected_impact: Impact
    success_metric: str
    status: str = "draft"


@dataclass(frozen=True)
class Phase2CalendarItem(Phase2ContentItem):
    date: date = field(default_factory=date.today)


@dataclass(frozen=True)
class ValidationIssue:
    severity: Literal["P0", "P1", "P2"]
    code: str
    message: str
    item_title: str | None = None


@dataclass(frozen=True)
class ValidationReport:
    issues: list[ValidationIssue]

    @property
    def errors(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "P0"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity != "P0"]

    @property
    def is_valid(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class WeeklyAction:
    section: Priority
    owner_task: str
    related_item: str
    estimated_minutes: int
    needed_asset_or_input: str
    completion_status: str = "not started"


@dataclass(frozen=True)
class WeeklyReviewTemplate:
    fields: list[str]
    rows: list[dict[str, str]]


@dataclass(frozen=True)
class Phase2MarketingPlan:
    mode: str
    weekly_theme: str
    campaign_narrative: str
    calendar: list[Phase2CalendarItem]
    content_items: list[Phase2ContentItem]
    recommendations: list[Recommendation]
    weekly_actions: list[WeeklyAction]
    review_template: WeeklyReviewTemplate
    validation_report: ValidationReport


@dataclass(frozen=True)
class WeeklyReport:
    week_start: date
    week_end: date
    planned_activities: list[str]
    recommended_actions: list[str]
    opportunities: list[str]
    seasonal_opportunities: list[str]
    priorities: list[str]


@dataclass(frozen=True)
class MarketingPlan:
    calendar: list[CalendarEntry]
    instagram_posts: list[ContentIdea] = field(default_factory=list)
    facebook_posts: list[ContentIdea] = field(default_factory=list)
    instagram_reels: list[ContentIdea] = field(default_factory=list)
    etsy_promotions: list[ContentIdea] = field(default_factory=list)
    blog_topics: list[ContentIdea] = field(default_factory=list)
    email_newsletters: list[ContentIdea] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
    weekly_report: WeeklyReport | None = None
