from __future__ import annotations

from .models import BusinessContext, CalendarEntry, Recommendation


class RecommendationEngine:
    def __init__(self, context: BusinessContext):
        self.context = context

    def recommend(self, calendar: list[CalendarEntry], limit: int = 8) -> list[Recommendation]:
        goals = self.context.business_goals
        products = self.context.momentum_products or self.context.products
        seasonal = self.context.seasonal_windows
        audiences = self.context.audiences
        channels = self.context.channels

        candidates = [
            Recommendation(
                title=f"Build a launch checklist around {products[0]}",
                aligned_business_goal=_goal(goals, "Promote New Duck Releases", 4),
                impact_estimate="high",
                effort_estimate="medium",
                rationale="The product docs identify current momentum products and say launches should be measured across early sales windows.",
                next_step=f"Use {products[0]} as the template product and define teaser, launch, and follow-up posts.",
            ),
            Recommendation(
                title=f"Invite {audiences[2] if len(audiences) > 2 else audiences[0]} into the email list",
                aligned_business_goal=_goal(goals, "Build An Owned Email List", 3),
                impact_estimate="high",
                effort_estimate="medium",
                rationale="The audience docs identify repeat and collector behavior as disproportionately valuable.",
                next_step="Add an email-list CTA to collector-focused social posts this week.",
            ),
            Recommendation(
                title=f"Promote {products[0]} and {products[1] if len(products) > 1 else products[0]} before broad evergreen posts",
                aligned_business_goal=_goal(goals, "Grow Etsy Sales", 0),
                impact_estimate="high",
                effort_estimate="low",
                rationale="Recent sales data points to products with stronger current demand than some lifetime leaders.",
                next_step="Feature the top momentum products in the next 7 days of calendar entries.",
            ),
            Recommendation(
                title=f"Create one offer for {audiences[-1]}",
                aligned_business_goal=_goal(goals, "Grow Etsy Sales", 0),
                impact_estimate="medium",
                effort_estimate="medium",
                rationale="The audience docs identify this segment as a potentially higher-value lane than one-off orders.",
                next_step="Publish one post that explains custom or bulk giveaway options and asks planners to message for timing.",
            ),
            Recommendation(
                title=f"Ask {audiences[0]} for customer photos",
                aligned_business_goal=_goal(goals, "Grow Social Media Followers", 2),
                impact_estimate="medium",
                effort_estimate="low",
                rationale="The audience docs describe community use cases that can turn posts into conversations.",
                next_step=f"Add a customer-photo CTA to one {channels[0] if channels else 'social'} post and one follow-up post this week.",
            ),
            Recommendation(
                title="Use seasonal windows as planning anchors",
                aligned_business_goal=_goal(goals, "Grow Etsy Sales", 0),
                impact_estimate="medium",
                effort_estimate="low",
                rationale="The company profile lists priority seasonal and event windows that should shape the calendar.",
                next_step=f"Tag this week's plan with the strongest relevant window: {seasonal[0] if seasonal else 'next launch window'}.",
            ),
            Recommendation(
                title=f"Use {channels[-1] if channels else 'the lowest-priority channel'} only for reusable evergreen ideas",
                aligned_business_goal=_goal(goals, "Grow Social Media Followers", 2),
                impact_estimate="low",
                effort_estimate="medium",
                rationale="The channel docs distinguish active priorities from lower-priority channel maintenance.",
                next_step="Create reusable evergreen concepts before spending time on lower-priority channel work.",
            ),
            Recommendation(
                title="Add a CTA check to every planned post",
                aligned_business_goal=_goal(goals, "Grow Etsy Sales", 0),
                impact_estimate="medium",
                effort_estimate="low",
                rationale="The acceptance criteria require calls-to-action, and consistent CTAs make each tactic measurable.",
                next_step="Review this week's calendar and ensure each entry points to a shop, signup, or comment action.",
            ),
        ]
        return candidates[:limit]


def _goal(goals: list[str], preferred: str, fallback_index: int) -> str:
    if preferred in goals:
        return preferred
    if goals:
        return goals[min(fallback_index, len(goals) - 1)]
    return "Business Goal"
