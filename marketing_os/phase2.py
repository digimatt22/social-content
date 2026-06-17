from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from itertools import cycle

from .context import load_business_context
from .models import (
    BusinessContext,
    Effort,
    Impact,
    Phase2CalendarItem,
    Phase2ContentItem,
    Phase2MarketingPlan,
    ProductEntity,
    Recommendation,
    ValidationIssue,
    ValidationReport,
    WeeklyAction,
    WeeklyReviewTemplate,
)


Mode = str


ASSET_TYPES = [
    "finished product closeup",
    "printer plate reveal",
    "packing order",
    "desk scene",
    "cruise hiding setup",
    "bundle lineup",
    "customer photo prompt",
    "maker/process shot",
    "seasonal gift setup",
    "custom/event order concept",
]


MODE_CONFIG: dict[str, dict[str, object]] = {
    "light": {
        "weekly_capacity_minutes": 90,
        "weekly_slots": 3,
        "theme": "Light-touch week focused on the highest-value content only.",
        "cadence": ["Instagram", "Facebook", "Etsy"],
    },
    "standard": {
        "weekly_capacity_minutes": 180,
        "weekly_slots": 5,
        "theme": "Standard marketing week balancing sales, followers, collectors, and launch prep.",
        "cadence": ["Instagram", "Facebook", "Instagram", "Etsy", "Website"],
    },
    "launch": {
        "weekly_capacity_minutes": 240,
        "weekly_slots": 6,
        "theme": "Launch week built around teaser, reveal, social proof, and Etsy conversion.",
        "cadence": ["Instagram", "Facebook", "Instagram", "Etsy", "Instagram", "Website"],
    },
    "holiday": {
        "weekly_capacity_minutes": 240,
        "weekly_slots": 6,
        "theme": "Holiday push focused on giftable products and shopping deadlines.",
        "cadence": ["Instagram", "Facebook", "Etsy", "Instagram", "Facebook", "Website"],
    },
    "event": {
        "weekly_capacity_minutes": 210,
        "weekly_slots": 5,
        "theme": "Event and custom-order week focused on bulk giveaway opportunities.",
        "cadence": ["Facebook", "Instagram", "Website", "Etsy", "Facebook"],
    },
}


def build_phase2_plan(
    business_dir: str = "docs/business",
    start_date: date | None = None,
    mode: Mode = "standard",
    weekly_capacity_minutes: int | None = None,
    allow_validation_errors: bool = False,
) -> Phase2MarketingPlan:
    context = load_business_context(business_dir)
    if not context.product_entities:
        raise ValueError("Phase 2 requires structured product knowledge in docs/business/product-catalog.json")

    start = start_date or date.today()
    if mode not in MODE_CONFIG:
        raise ValueError(f"Unsupported planning mode: {mode}")

    config = MODE_CONFIG[mode]
    capacity = weekly_capacity_minutes or int(config["weekly_capacity_minutes"])
    weekly_slots = int(config["weekly_slots"])
    calendar = _build_calendar(context, start, mode, capacity, weekly_slots)
    content_items = [replace(item, date=date.today()) for item in calendar]
    recommendations = _recommendations(context, calendar, mode)
    actions = _weekly_actions(calendar, recommendations, capacity)
    review = _review_template(calendar)
    validation = validate_phase2_plan(context, calendar, recommendations)

    plan = Phase2MarketingPlan(
        mode=mode,
        weekly_theme=str(config["theme"]),
        campaign_narrative=_campaign_narrative(context, mode),
        calendar=calendar,
        content_items=content_items,
        recommendations=recommendations,
        weekly_actions=actions,
        review_template=review,
        validation_report=validation,
    )
    if validation.errors and not allow_validation_errors:
        summary = "; ".join(f"{issue.code}: {issue.message}" for issue in validation.errors)
        raise ValueError(f"Phase 2 plan has P0 validation errors: {summary}")
    return plan


def _build_calendar(
    context: BusinessContext,
    start: date,
    mode: str,
    capacity: int,
    weekly_slots: int,
) -> list[Phase2CalendarItem]:
    products = _mode_products(context, mode)
    cadence = _supported_cadence(context, list(MODE_CONFIG[mode]["cadence"]))
    goals = cycle(context.business_goals)
    items: list[Phase2CalendarItem] = []
    total_slots = 30
    spacing = 1

    for index in range(total_slots):
        product = products[index % len(products)]
        platform = cadence[index % len(cadence)]
        content_type = _content_type(platform, mode, index)
        goal = _best_goal(context, product, platform, mode, next(goals))
        objective = _objective_for_goal(goal, mode)
        audience = product.primary_audience
        cta = _cta_for(platform, goal, context)
        asset_type = _asset_type(platform, product, mode, index)
        priority = _priority(index, mode, product.launch_priority)
        effort = _effort(platform, content_type, priority)
        impact = _impact(product, priority, mode)
        item_date = start + timedelta(days=index * spacing)

        items.append(
            Phase2CalendarItem(
                date=item_date,
                title=f"{platform} {content_type}: {product.name} for {audience}",
                platform=platform,
                content_type=content_type,
                business_goal=goal,
                objective=objective,
                target_audience=audience,
                featured_product=product.name,
                draft_copy=_draft_copy(product, platform, content_type, cta, mode),
                cta=cta,
                hashtags=_hashtags(product, platform),
                asset_brief=_asset_brief(product, asset_type, mode),
                asset_type=asset_type,
                production_notes=_production_notes(platform, asset_type, product),
                priority=priority,
                effort_estimate=effort,
                expected_impact=impact,
                success_metric=_success_metric(goal, platform),
            )
        )
    return items


def _mode_products(context: BusinessContext, mode: str) -> list[ProductEntity]:
    products = context.product_entities
    if mode == "launch":
        selected = [p for p in products if p.status in {"momentum", "new"} or p.launch_priority == "high"]
    elif mode == "event":
        selected = [p for p in products if "Event" in p.primary_audience or "custom/event order concept" in p.use_cases]
    elif mode == "holiday":
        selected = [p for p in products if any("holiday" in s.lower() or "gift" in s.lower() for s in p.seasonality + p.use_cases)]
    else:
        selected = [p for p in products if p.status in {"momentum", "active", "new"}]
    return selected or products


def _supported_cadence(context: BusinessContext, desired: list[str]) -> list[str]:
    supported = set(context.channels)
    return [channel for channel in desired if channel in supported] or ["Instagram", "Facebook", "Etsy"]


def _content_type(platform: str, mode: str, index: int) -> str:
    if platform == "Instagram" and (mode == "launch" or index % 2 == 0):
        return "reel"
    if platform == "Instagram":
        return "post"
    if platform == "Facebook":
        return "post"
    if platform == "Etsy":
        return "promotion"
    if platform == "Website":
        return "blog topic"
    return "post"


def _best_goal(context: BusinessContext, product: ProductEntity, platform: str, mode: str, fallback: str) -> str:
    goals = context.business_goals
    if mode == "launch" and "Promote New Duck Releases" in goals:
        return "Promote New Duck Releases"
    if platform == "Etsy" and "Grow Etsy Sales" in goals:
        return "Grow Etsy Sales"
    if product.status in {"momentum", "new"} and "Promote New Duck Releases" in goals:
        return "Promote New Duck Releases"
    if "Collector" in product.primary_audience and "Increase Repeat Customers" in goals:
        return "Increase Repeat Customers"
    return fallback


def _objective_for_goal(goal: str, mode: str) -> str:
    if goal == "Grow Etsy Sales":
        return "Drive qualified shoppers to the Etsy listing"
    if goal == "Increase Repeat Customers":
        return "Give collectors a reason to return"
    if goal == "Grow Social Media Followers":
        return "Invite engagement and sharing"
    if goal == "Build An Owned Email List":
        return "Move interested buyers toward owned follow-up"
    if goal == "Promote New Duck Releases":
        return "Create launch momentum and early demand"
    return f"Support {mode} marketing activity"


def _cta_for(platform: str, goal: str, context: BusinessContext) -> str:
    etsy = context.etsy_url or "https://mattmademe.etsy.com"
    website = context.website_url or "https://mattmademe.com"
    if goal == "Build An Owned Email List":
        return f"Join the list for future duck drops: {website}"
    if platform == "Etsy":
        return f"Add it to your cart: {etsy}"
    if platform == "Website":
        return f"Read the full story and shop the duck: {website}"
    if goal == "Grow Social Media Followers":
        return "Follow MattMadeMe and tag someone who needs this duck"
    if goal == "Promote New Duck Releases":
        return f"See the newest duck in the Etsy shop: {etsy}"
    return f"Shop the flock on Etsy: {etsy}"


def _asset_type(platform: str, product: ProductEntity, mode: str, index: int) -> str:
    if mode == "launch" and index == 0:
        return "printer plate reveal"
    if "Cruise Duck Hunter" in [product.primary_audience, *product.secondary_audiences]:
        return "cruise hiding setup"
    if platform == "Etsy":
        return "finished product closeup"
    if product.primary_audience == "Collector / Completionist":
        return "bundle lineup"
    if "event" in " ".join(product.use_cases).lower():
        return "custom/event order concept"
    return ASSET_TYPES[index % len(ASSET_TYPES)]


def _priority(index: int, mode: str, launch_priority: str) -> str:
    if index < 2 or launch_priority == "high":
        return "must do"
    if mode == "light" and index > 4:
        return "optional"
    if index % 5 == 0:
        return "optional"
    return "should do"


def _effort(platform: str, content_type: str, priority: str) -> Effort:
    if priority == "optional":
        return "low"
    if content_type == "reel" or platform == "Website":
        return "medium"
    return "low"


def _impact(product: ProductEntity, priority: str, mode: str) -> Impact:
    if priority == "must do" or product.status in {"momentum", "new"} or mode == "launch":
        return "high"
    if product.status == "cooling":
        return "medium"
    return "medium"


def _draft_copy(product: ProductEntity, platform: str, content_type: str, cta: str, mode: str) -> str:
    use_case = product.use_cases[0] if product.use_cases else "gift"
    if content_type == "reel":
        return (
            f"Hook: A tiny {product.name} is joining the flock. "
            f"Show the {use_case} moment, then close with why it makes a personal 3D printed gift. {cta}."
        )
    if platform == "Facebook":
        return (
            f"{product.name} feels made for {product.primary_audience.lower()}s. "
            f"It is an original 3D printed duck with a specific little story, not a generic shelf filler. "
            f"Who would you gift this one to? {cta}."
        )
    if platform == "Etsy":
        return (
            f"Refresh the listing lead for {product.name} around {use_case}. "
            f"Emphasize original PETG 3D printing, giftability, and who it is for. {cta}."
        )
    if platform == "Website":
        return (
            f"Draft a short post about why {product.name} exists, who it is for, and how it fits into "
            f"the MattMadeMe flock. Include a section on {product.sales_momentum_note.lower()} {cta}."
        )
    return (
        f"Meet {product.name}: a small original 3D printed duck with a very specific job. "
        f"Perfect for {product.primary_audience.lower()}s who want a {use_case}. {cta}."
    )


def _hashtags(product: ProductEntity, platform: str) -> list[str]:
    if platform not in {"Instagram", "Facebook"}:
        return []
    tags = ["#MattMadeMe", "#3DPrinted", "#DuckCollector"]
    if "Cruise Duck Hunter" in [product.primary_audience, *product.secondary_audiences]:
        tags.append("#CruiseDucks")
    if "Gift Buyer" in [product.primary_audience, *product.secondary_audiences]:
        tags.append("#GiftIdeas")
    return tags


def _asset_brief(product: ProductEntity, asset_type: str, mode: str) -> str:
    return (
        f"Capture a {asset_type} for {product.name}. Show the finished duck clearly, keep the background simple, "
        f"and make the intended use obvious for {product.primary_audience}."
    )


def _production_notes(platform: str, asset_type: str, product: ProductEntity) -> str:
    if platform == "Instagram" and asset_type == "printer plate reveal":
        return "Shoot 3 clips: printer plate, hand pickup, finished duck closeup. Keep it under 20 seconds."
    if platform == "Instagram":
        return "Use vertical framing. Start with the duck already visible in the first second."
    if platform == "Facebook":
        return "Use a clear product photo and ask a question that invites comments."
    if platform == "Etsy":
        return "Update title or first paragraph only; do not change proven listing structure without tracking."
    if platform == "Website":
        return "Write a short evergreen post that can be linked from social and reused later."
    return "Keep the asset focused on the product and one customer use case."


def _success_metric(goal: str, platform: str) -> str:
    if goal == "Grow Etsy Sales" or platform == "Etsy":
        return "Track Etsy visits, favorites, orders, or a manual sales note for the featured product."
    if goal == "Increase Repeat Customers":
        return "Track returning-buyer comments, collector replies, or repeat-order notes."
    if goal == "Grow Social Media Followers":
        return "Track follows, comments, shares, saves, and customer photo submissions."
    if goal == "Build An Owned Email List":
        return "Track email signups or list-interest replies."
    if goal == "Promote New Duck Releases":
        return "Track first 7-day views, favorites, comments, and sales notes."
    return "Track whether the planned action was completed and what changed afterward."


def _recommendations(context: BusinessContext, calendar: list[Phase2CalendarItem], mode: str) -> list[Recommendation]:
    first = calendar[0]
    collector = next((item for item in calendar if "Collector" in item.target_audience), first)
    etsy = next((item for item in calendar if item.platform == "Etsy"), first)
    launch = next((item for item in calendar if item.business_goal == "Promote New Duck Releases"), first)
    email_goal = "Build An Owned Email List" if "Build An Owned Email List" in context.business_goals else context.business_goals[0]
    return [
        Recommendation(
            title=f"Create the asset for {first.featured_product} first",
            aligned_business_goal=first.business_goal,
            impact_estimate="high",
            effort_estimate=first.effort_estimate,
            rationale="The first must-do content item sets the tone for the week and can supply reusable product assets.",
            next_step=first.asset_brief,
            estimated_minutes=25,
            why_now=f"This is the lead item for {mode} planning mode.",
            linked_item=first.title,
            success_metric=first.success_metric,
        ),
        Recommendation(
            title=f"Give collectors a reason to respond to {collector.featured_product}",
            aligned_business_goal="Increase Repeat Customers",
            impact_estimate="high",
            effort_estimate="low",
            rationale="Collector and repeat-customer behavior is disproportionately valuable in the business docs.",
            next_step="Add a comment prompt asking which duck should join the same themed flock next.",
            estimated_minutes=10,
            why_now="Collector prompts are fast to add while drafting weekly posts.",
            linked_item=collector.title,
            success_metric="Track collector comments, repeat-buyer replies, and future product suggestions.",
        ),
        Recommendation(
            title=f"Strengthen the Etsy action for {etsy.featured_product}",
            aligned_business_goal="Grow Etsy Sales",
            impact_estimate="high",
            effort_estimate="low",
            rationale="Every sales-focused week needs at least one direct Etsy improvement or promotion.",
            next_step="Check listing hero image, first sentence, and tags against the planned customer use case.",
            estimated_minutes=20,
            why_now="The calendar already includes a traffic-driving item for this product.",
            linked_item=etsy.title,
            success_metric=etsy.success_metric,
        ),
        Recommendation(
            title="Add an owned-list CTA where it fits naturally",
            aligned_business_goal=email_goal,
            impact_estimate="medium",
            effort_estimate="low",
            rationale="The business goals prioritize email list growth, but email is not yet an active channel.",
            next_step="Use a website or social CTA that invites buyers to watch for future duck drops.",
            estimated_minutes=15,
            why_now="This builds owned reach without requiring an email platform integration.",
            linked_item=collector.title,
            success_metric="Track manual email signup notes or list-interest replies.",
        ),
        Recommendation(
            title=f"Protect the launch story for {launch.featured_product}",
            aligned_business_goal="Promote New Duck Releases",
            impact_estimate="high" if mode == "launch" else "medium",
            effort_estimate="medium",
            rationale="New releases need a teaser, reveal, and follow-up instead of a single isolated post.",
            next_step="Use the same product image across teaser, reveal, and Etsy follow-up content.",
            estimated_minutes=30,
            why_now="Launch momentum is strongest when the story is repeated across the week.",
            linked_item=launch.title,
            success_metric=launch.success_metric,
        ),
    ]


def _weekly_actions(
    calendar: list[Phase2CalendarItem],
    recommendations: list[Recommendation],
    capacity: int,
) -> list[WeeklyAction]:
    actions: list[WeeklyAction] = []
    minutes = 0
    for item in calendar[:7]:
        estimate = 30 if item.effort_estimate == "medium" else 15
        section = item.priority
        if minutes + estimate > capacity and section != "must do":
            section = "optional"
        minutes += estimate if section != "optional" else 0
        actions.append(
            WeeklyAction(
                section=section,
                owner_task=f"Create {item.platform} {item.content_type} for {item.featured_product}",
                related_item=item.title,
                estimated_minutes=estimate,
                needed_asset_or_input=item.asset_brief,
            )
        )
    if not any(action.section == "optional" for action in actions):
        optional_item = calendar[min(7, len(calendar) - 1)]
        actions.append(
            WeeklyAction(
                section="optional",
                owner_task=f"Prepare backup content for {optional_item.featured_product}",
                related_item=optional_item.title,
                estimated_minutes=15,
                needed_asset_or_input=optional_item.asset_brief,
            )
        )
    actions.append(
        WeeklyAction(
            section="blocked",
            owner_task="Confirm email platform/list status before sending newsletter-style content",
            related_item="Email setup",
            estimated_minutes=10,
            needed_asset_or_input="Email platform name and signup URL",
        )
    )
    return actions


def _review_template(calendar: list[Phase2CalendarItem]) -> WeeklyReviewTemplate:
    fields = [
        "planned",
        "approved",
        "posted",
        "skipped",
        "post URL",
        "notes",
        "views or reach",
        "likes",
        "comments",
        "shares",
        "saves",
        "Etsy visits or sales note",
        "email signups note",
        "lesson learned",
    ]
    rows = [{field: "" for field in fields} | {"planned": item.title} for item in calendar[:7]]
    return WeeklyReviewTemplate(fields=fields, rows=rows)


def _campaign_narrative(context: BusinessContext, mode: str) -> str:
    seasonal = context.seasonal_windows[0] if context.seasonal_windows else "new duck launch windows"
    if mode == "launch":
        return f"This week should build a clear launch arc: tease, reveal, drive Etsy action, then ask collectors what should come next. Tie it to {seasonal} where relevant."
    if mode == "light":
        return "This week should protect only the highest-value actions and skip optional channel maintenance."
    if mode == "event":
        return "This week should make custom and event giveaway ducks feel concrete enough for planners to ask for a quote."
    if mode == "holiday":
        return f"This week should frame ducks as specific gifts and prepare shoppers early for {seasonal}."
    return f"This week should balance Etsy sales, social engagement, collector retention, and launch prep while explaining why {seasonal} matters now."


def validate_phase2_plan(
    context: BusinessContext,
    calendar: list[Phase2CalendarItem],
    recommendations: list[Recommendation],
) -> ValidationReport:
    issues: list[ValidationIssue] = []
    products = {product.name for product in context.product_entities}
    channels = set(context.channels)
    goals = set(context.business_goals)

    for item in calendar:
        if item.featured_product not in products:
            issues.append(ValidationIssue("P0", "invalid_product", f"Unknown product: {item.featured_product}", item.title))
        if "." in item.featured_product or len(item.featured_product.split()) > 6:
            issues.append(ValidationIssue("P0", "product_looks_like_sentence", f"Featured product looks like commentary: {item.featured_product}", item.title))
        if item.platform not in channels:
            issues.append(ValidationIssue("P0", "unsupported_platform", f"Unsupported platform: {item.platform}", item.title))
        if not item.asset_brief:
            issues.append(ValidationIssue("P0", "missing_asset_brief", "Missing asset brief", item.title))
        if not item.success_metric:
            issues.append(ValidationIssue("P0", "missing_success_metric", "Missing success metric", item.title))
        if "as a Add a duck to your flock" in item.draft_copy:
            issues.append(ValidationIssue("P0", "awkward_brand_voice", "Awkward brand phrase detected", item.title))
        if item.business_goal not in goals:
            issues.append(ValidationIssue("P0", "unknown_goal", f"Unknown business goal: {item.business_goal}", item.title))
        if _goal_cta_mismatch(item):
            issues.append(ValidationIssue("P1", "goal_cta_mismatch", "Goal, platform, and CTA may be misaligned", item.title))

    for recommendation in recommendations:
        if recommendation.estimated_minutes is None:
            issues.append(ValidationIssue("P0", "missing_recommendation_minutes", "Recommendation missing estimated minutes", recommendation.title))
        if not recommendation.why_now:
            issues.append(ValidationIssue("P0", "missing_recommendation_why_now", "Recommendation missing why now", recommendation.title))
        if not recommendation.success_metric:
            issues.append(ValidationIssue("P0", "missing_recommendation_metric", "Recommendation missing success metric", recommendation.title))
    return ValidationReport(issues=issues)


def _goal_cta_mismatch(item: Phase2CalendarItem) -> bool:
    cta = item.cta.lower()
    if item.business_goal == "Build An Owned Email List":
        return "list" not in cta and "signup" not in cta and "drop" not in cta
    if item.platform == "Etsy":
        return "etsy" not in cta and "cart" not in cta
    if item.business_goal == "Grow Social Media Followers":
        return "follow" not in cta and "tag" not in cta
    return False
