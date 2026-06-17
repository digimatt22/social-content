from __future__ import annotations

from datetime import date

from .calendar import CalendarPlanner
from .content import ContentGenerator
from .context import load_business_context
from .models import MarketingPlan
from .recommendations import RecommendationEngine
from .reporting import ReportBuilder


def build_plan(business_dir: str = "docs/business", start_date: date | None = None) -> MarketingPlan:
    context = load_business_context(business_dir)
    start = start_date or date.today()

    generator = ContentGenerator(context)
    instagram_posts = generator.instagram_posts(30)
    facebook_posts = generator.facebook_posts(30)
    instagram_reels = generator.instagram_reels(10)
    etsy_promotions = generator.etsy_promotions(10)
    blog_topics = generator.blog_topics(10)
    email_newsletters = generator.email_newsletters(10)

    calendar_ideas = []
    for index in range(30):
        if index % 5 == 0:
            calendar_ideas.append(instagram_reels[index % len(instagram_reels)])
        elif index % 5 == 1:
            calendar_ideas.append(facebook_posts[index])
        elif index % 5 == 2:
            calendar_ideas.append(instagram_posts[index])
        elif index % 5 == 3:
            calendar_ideas.append(etsy_promotions[index % len(etsy_promotions)])
        else:
            calendar_ideas.append(email_newsletters[index % len(email_newsletters)])

    planner = CalendarPlanner(context)
    calendar = planner.generate_30_day_calendar(start, calendar_ideas)
    recommendations = RecommendationEngine(context).recommend(calendar)
    weekly_report = ReportBuilder(context).weekly_report(calendar, recommendations, start)

    return MarketingPlan(
        calendar=calendar,
        instagram_posts=instagram_posts,
        facebook_posts=facebook_posts,
        instagram_reels=instagram_reels,
        etsy_promotions=etsy_promotions,
        blog_topics=blog_topics,
        email_newsletters=email_newsletters,
        recommendations=recommendations,
        weekly_report=weekly_report,
    )

