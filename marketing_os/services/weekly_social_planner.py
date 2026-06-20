from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db_models import PlannedContentRecord
from ..phase3 import json_list
from .content_briefs import create_planned_content_item, produce_content_for_item
from .etsy_sales import EtsySalesSummary, ProductSalesSignal, load_etsy_product_sales_signals


@dataclass(frozen=True)
class WeeklySlot:
    offset_days: int
    platform: str
    goal: str
    audience: str
    occasion: str
    promotion: str
    product_bucket: str
    reasoning: str


@dataclass(frozen=True)
class WeeklyPlanResult:
    week_start: str
    created: int
    skipped: int
    planned_item_ids: list[int]
    strategy_export_path: str
    sales_source: str
    sales_errors: list[str]


WEEKLY_SLOTS = [
    WeeklySlot(
        0,
        "Facebook",
        "Cruise community engagement",
        "Cruise Duckers",
        "Cruise duck hiding",
        "Find your favorite duck in our Etsy shop",
        "popular",
        "Start the week with the strongest organic community angle.",
    ),
    WeeklySlot(
        1,
        "Instagram",
        "Duck personality spotlight",
        "Collectors / Flock Builders",
        "Desk mascot moment",
        "Add a new duck to your flock",
        "slow_boost",
        "Use personality to give a slower product a better social angle.",
    ),
    WeeklySlot(
        2,
        "Pinterest",
        "Gift consideration",
        "Gift Buyers",
        "Gift idea",
        "Find your favorite duck in our Etsy shop",
        "popular",
        "Use search-friendly gift positioning around a product with proof of demand.",
    ),
    WeeklySlot(
        3,
        "Facebook",
        "Flock building",
        "Collectors / Flock Builders",
        "New flock member",
        "See the full flock on Etsy",
        "slow_boost",
        "Invite comments and collection behavior around a product that needs a lift.",
    ),
    WeeklySlot(
        4,
        "Instagram",
        "Follower growth",
        "Desk Decor Buyers",
        "Desk mascot moment",
        "Start your flock today",
        "popular",
        "Use a visually clear product to create profile-follow momentum.",
    ),
    WeeklySlot(
        5,
        "Facebook",
        "Etsy shop visits",
        "Cruise Duckers",
        "Room steward gift",
        "Find your favorite duck in our Etsy shop",
        "popular",
        "Close the week with a shop-click post that still feels community-led.",
    ),
    WeeklySlot(
        6,
        "Pinterest",
        "Flock building",
        "Collectors / Flock Builders",
        "Collection spotlight",
        "See the full flock on Etsy",
        "slow_boost",
        "Give a slower product a longer-tail collection discovery path.",
    ),
]


def build_weekly_social_plan(
    session: Session,
    week_start: date,
    business_dir: str = "docs/business",
    output_dir: str | Path = "data/exports/weekly-social-plans",
    slots: int = 7,
    dry_run: bool = False,
    sales_lookback_days: int = 90,
    freshness_lookback_days: int = 45,
) -> WeeklyPlanResult:
    sales = load_etsy_product_sales_signals(session, lookback_days=sales_lookback_days)
    selected_slots = WEEKLY_SLOTS[: max(1, min(slots, len(WEEKLY_SLOTS)))]
    recent_product_ids = _recently_featured_product_ids(session, week_start, lookback_days=freshness_lookback_days)
    assignments = _assign_products(selected_slots, sales.product_signals, recent_product_ids=recent_product_ids)
    created_ids: list[int] = []
    skipped = 0

    for slot, product in assignments:
        post_date = week_start + timedelta(days=slot.offset_days)
        if _already_planned(session, post_date, slot.platform, product.product_id, week_start):
            skipped += 1
            continue
        if dry_run:
            continue
        item = create_planned_content_item(
            session,
            calendar_date=post_date,
            destinations=[slot.platform],
            goals=[slot.goal],
            product_ids=[product.product_id],
            selected_source_asset_ids=None,
            audience=slot.audience,
            occasion=slot.occasion,
            promotion=slot.promotion,
            notes=_planning_notes(slot, product, week_start),
        )
        produce_content_for_item(session, item, business_dir=business_dir)
        created_ids.append(item.id)

    export_path = write_weekly_strategy_export(
        week_start=week_start,
        output_dir=output_dir,
        sales=sales,
        assignments=assignments,
        recent_product_ids=recent_product_ids,
        freshness_lookback_days=freshness_lookback_days,
        created_ids=created_ids,
        skipped=skipped,
        dry_run=dry_run,
    )
    return WeeklyPlanResult(
        week_start=week_start.isoformat(),
        created=len(created_ids),
        skipped=skipped,
        planned_item_ids=created_ids,
        strategy_export_path=str(export_path),
        sales_source=sales.source,
        sales_errors=sales.errors,
    )


def write_weekly_strategy_export(
    week_start: date,
    output_dir: str | Path,
    sales: EtsySalesSummary,
    assignments: list[tuple[WeeklySlot, ProductSalesSignal]],
    recent_product_ids: set[int] | None,
    freshness_lookback_days: int,
    created_ids: list[int],
    skipped: int,
    dry_run: bool = False,
) -> Path:
    recent_product_ids = recent_product_ids or set()
    target_dir = Path(output_dir) / week_start.isoformat()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "weekly-social-strategy.json"
    target.write_text(
        json.dumps(
            {
                "week_start": week_start.isoformat(),
                "role": "social-media-strategist",
                "workflow": ["social-media-strategist", "social-media-copywriter", "social-media-copy-chief", "social-media-art-director"],
                "approval_required": True,
                "sales_source": sales.source,
                "sales_lookback_days": sales.lookback_days,
                "sales_errors": sales.errors,
                "freshness_lookback_days": freshness_lookback_days,
                "recently_featured_product_ids": sorted(recent_product_ids),
                "created_planned_item_ids": created_ids,
                "skipped_existing_items": skipped,
                "strategy": {
                    "content_mix": {
                        "Cruise And Sharing": "40%",
                        "Duck Personality": "30%",
                        "Flock Building": "20%",
                        "Maker Process": "10%",
                    },
                    "product_mix": "Balance popular Etsy products with slow products that need a better social angle, while avoiding products featured in the recent lookback window when fresh alternatives exist.",
                    "platform_mix": ["Facebook", "Instagram", "Pinterest"],
                    "human_review": "All generated copy and images remain in Planning review.",
                },
                "assignments": [
                    {
                        "date": (week_start + timedelta(days=slot.offset_days)).isoformat(),
                        "platform": slot.platform,
                        "goal": slot.goal,
                        "audience": slot.audience,
                        "occasion": slot.occasion,
                        "promotion": slot.promotion,
                        "product_bucket": slot.product_bucket,
                        "recently_featured": product.product_id in recent_product_ids,
                        "reasoning": slot.reasoning,
                        "product": asdict(product),
                    }
                    for slot, product in assignments
                ],
                "dry_run": dry_run,
            },
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    return target


def next_monday(today: date | None = None) -> date:
    base = today or date.today()
    days_until_monday = (7 - base.weekday()) % 7
    return base + timedelta(days=days_until_monday or 7)


def _assign_products(
    slots: list[WeeklySlot],
    signals: list[ProductSalesSignal],
    recent_product_ids: set[int] | None = None,
) -> list[tuple[WeeklySlot, ProductSalesSignal]]:
    if not signals:
        return []
    recent_product_ids = recent_product_ids or set()
    popular = [signal for signal in signals if signal.recent_quantity > 0] or signals
    slow = [signal for signal in sorted(signals, key=lambda item: (item.recent_quantity, item.product_name.lower())) if signal_recently_selectable(signal)]
    slow = slow or list(reversed(signals))
    popular_index = 0
    slow_index = 0
    assignments: list[tuple[WeeklySlot, ProductSalesSignal]] = []
    used: set[int] = set()
    for slot in slots:
        pool = popular if slot.product_bucket == "popular" else slow
        index = popular_index if slot.product_bucket == "popular" else slow_index
        product = _next_product(pool, index, used, recent_product_ids)
        if product is None:
            product = _next_product(signals, 0, used, recent_product_ids) or _next_product(signals, 0, used, set()) or signals[0]
        assignments.append((slot, product))
        used.add(product.product_id)
        if slot.product_bucket == "popular":
            popular_index += 1
        else:
            slow_index += 1
    return assignments


def signal_recently_selectable(signal: ProductSalesSignal) -> bool:
    return signal.signal == "slow_boost" or signal.recent_quantity <= 1


def _next_product(
    pool: list[ProductSalesSignal],
    start_index: int,
    used: set[int],
    recent_product_ids: set[int],
) -> ProductSalesSignal | None:
    if not pool:
        return None
    for offset in range(len(pool)):
        candidate = pool[(start_index + offset) % len(pool)]
        if candidate.product_id not in used and candidate.product_id not in recent_product_ids:
            return candidate
    for offset in range(len(pool)):
        candidate = pool[(start_index + offset) % len(pool)]
        if candidate.product_id not in used:
            return candidate
    return pool[start_index % len(pool)]


def _recently_featured_product_ids(session: Session, week_start: date, lookback_days: int = 45) -> set[int]:
    cutoff = week_start - timedelta(days=lookback_days)
    ids: set[int] = set()
    items = session.scalars(
        select(PlannedContentRecord)
        .where(PlannedContentRecord.calendar_date >= cutoff)
        .where(PlannedContentRecord.calendar_date < week_start)
        .where(PlannedContentRecord.status.not_in(["skipped"]))
    )
    for item in items:
        for value in json_list(item.product_ids_json):
            try:
                ids.add(int(value))
            except (TypeError, ValueError):
                continue
    return ids


def _already_planned(session: Session, post_date: date, platform: str, product_id: int, week_start: date) -> bool:
    marker = f"Weekly autoplan {week_start.isoformat()}"
    items = session.scalars(select(PlannedContentRecord).where(PlannedContentRecord.calendar_date == post_date)).all()
    for item in items:
        if marker not in item.notes:
            continue
        if platform not in json_list(item.destinations_json):
            continue
        if product_id in [int(value) for value in json_list(item.product_ids_json)]:
            return True
    return False


def _planning_notes(slot: WeeklySlot, product: ProductSalesSignal, week_start: date) -> str:
    sales_note = (
        f"Recent Etsy quantity: {product.recent_quantity}; product bucket: {slot.product_bucket}; "
        f"last sale: {product.last_sale_at.isoformat() if product.last_sale_at else 'none in lookback'}."
    )
    return (
        f"Weekly autoplan {week_start.isoformat()}. "
        f"Strategist reason: {slot.reasoning} {sales_note} "
        "Use the social strategy -> writing -> challenge flow and keep outputs in human review."
    )
