from __future__ import annotations

from datetime import date, timedelta
from itertools import cycle

from .models import BusinessContext, CalendarEntry, ContentIdea


class CalendarPlanner:
    def __init__(self, context: BusinessContext):
        self.context = context

    def generate_30_day_calendar(self, start_date: date, ideas: list[ContentIdea]) -> list[CalendarEntry]:
        if len(ideas) < 30:
            raise ValueError("At least 30 ideas are required to build a 30-day calendar.")

        objectives = [
            "Grow Etsy Sales",
            "Grow Social Media Followers",
            "Increase Repeat Customers",
            "Build An Owned Email List",
            "Promote New Duck Releases",
        ]
        calendar: list[CalendarEntry] = []
        objective_cycle = cycle([goal for goal in self.context.business_goals if goal in objectives] or self.context.business_goals)
        for offset, idea in enumerate(ideas[:30]):
            objective = next(objective_cycle)
            calendar.append(
                CalendarEntry(
                    date=start_date + timedelta(days=offset),
                    platform=idea.platform,
                    content_type=idea.content_type,
                    objective=objective,
                    cta=idea.cta,
                    featured_product=idea.featured_product,
                    business_goal=idea.business_goal,
                    idea=idea.angle,
                )
            )
        return calendar

