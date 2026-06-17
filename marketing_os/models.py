from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal


Impact = Literal["low", "medium", "high"]
Effort = Literal["low", "medium", "high"]


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

