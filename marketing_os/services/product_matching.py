from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db_models import AssetRecord, CalendarItemRecord, PlannedContentRecord, ProductRecord, TaskRecord
from .product_identity import remember_product_reference


@dataclass(frozen=True)
class ProductMatchSummary:
    source_product_id: int
    target_product_id: int
    source_name: str
    target_name: str
    assets_moved: int
    planned_items_updated: int
    tasks_updated: int


def match_product_records(session: Session, source_product_id: int, target_product_id: int) -> ProductMatchSummary:
    if source_product_id == target_product_id:
        raise ValueError("Choose two different products to match.")

    source = session.get(ProductRecord, source_product_id)
    target = session.get(ProductRecord, target_product_id)
    if source is None or target is None:
        raise ValueError("Choose existing source and target products.")

    if source.external_source and source.external_id:
        remember_product_reference(session, target, source.external_source, source.external_id, source.canonical_url, source.name)
    for reference in list(source.external_references):
        reference.product = target

    assets = list(session.scalars(select(AssetRecord).where(AssetRecord.product_id == source.id)))
    for asset in assets:
        asset.product = target

    planned_items_updated = 0
    planned_items = list(session.scalars(select(PlannedContentRecord)))
    for item in planned_items:
        product_ids = _json_int_list(item.product_ids_json)
        updated_ids = [target.id if product_id == source.id else product_id for product_id in product_ids]
        deduped_ids = list(dict.fromkeys(updated_ids))
        if deduped_ids != product_ids:
            item.product_ids_json = json.dumps(deduped_ids)
            planned_items_updated += 1

    tasks_updated = 0
    for task in session.scalars(select(TaskRecord).where(TaskRecord.product_name == source.name)):
        task.product_name = target.name
        tasks_updated += 1
    for calendar_item in session.scalars(select(CalendarItemRecord).where(CalendarItemRecord.featured_product == source.name)):
        calendar_item.featured_product = target.name

    if not target.external_source and source.external_source:
        target.external_source = source.external_source
        target.external_id = source.external_id
        target.canonical_url = source.canonical_url
        target.last_synced_at = source.last_synced_at
        target.sync_status = source.sync_status
        target.staleness_state = source.staleness_state

    summary = ProductMatchSummary(
        source_product_id=source.id,
        target_product_id=target.id,
        source_name=source.name,
        target_name=target.name,
        assets_moved=len(assets),
        planned_items_updated=planned_items_updated,
        tasks_updated=tasks_updated,
    )
    session.delete(source)
    session.flush()
    return summary


def _json_int_list(value: str) -> list[int]:
    try:
        raw_values = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return [int(item) for item in raw_values if str(item).isdigit()]
