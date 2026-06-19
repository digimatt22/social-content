from __future__ import annotations

import json

from sqlalchemy.orm import Session

from ..db_models import ProductRecord


ETSY_SHOP_URL = "https://mattmademe.etsy.com"
LAUNCH_PRIORITIES = ["high", "medium", "low"]


def update_product_fields(
    session: Session,
    product_id: int,
    *,
    status: str,
    primary_audience: str,
    launch_priority: str,
    use_cases_text: str,
    sales_momentum_note: str,
) -> ProductRecord:
    product = session.get(ProductRecord, product_id)
    if product is None:
        raise ValueError(f"Product not found: {product_id}")

    product.status = status.strip() or product.status
    product.primary_audience = primary_audience.strip() or "Needs review"
    product.launch_priority = launch_priority.strip() if launch_priority.strip() in LAUNCH_PRIORITIES else "medium"
    product.use_cases_json = json.dumps(_split_tags(use_cases_text))
    product.sales_momentum_note = sales_momentum_note.strip()
    product.manual_override_state = "override"
    product.manual_override_note = "Product fields edited in Marketing OS."
    product.sync_status = "manual override"
    product.sync_error = ""
    session.flush()
    return product


def _split_tags(value: str) -> list[str]:
    tags: list[str] = []
    for raw_value in value.replace("\n", ",").split(","):
        tag = raw_value.strip()
        if tag and tag not in tags:
            tags.append(tag)
    return tags
