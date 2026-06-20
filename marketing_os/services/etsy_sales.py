from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db_models import ProductRecord, ProductSalesRecord, SyncMetadata, utc_now


@dataclass(frozen=True)
class ProductSalesSignal:
    product_id: int
    product_name: str
    external_id: str
    canonical_url: str
    recent_quantity: int
    recent_revenue_cents: int
    last_sale_at: datetime | None
    signal: str


@dataclass(frozen=True)
class EtsySalesSummary:
    source: str
    lookback_days: int
    transactions_imported: int
    product_signals: list[ProductSalesSignal]
    errors: list[str]


def load_etsy_product_sales_signals(session: Session, lookback_days: int = 90) -> EtsySalesSummary:
    """Aggregate locally imported Etsy sales CSV rows by product.

    Sales data intentionally comes from CSV imports only. The Etsy listing API
    remains read-only for product/listing metadata.
    """
    cutoff = utc_now() - timedelta(days=lookback_days)
    sales_rows = list(
        session.scalars(
            select(ProductSalesRecord).where(
                (ProductSalesRecord.sold_at.is_(None)) | (ProductSalesRecord.sold_at >= cutoff)
            )
        )
    )
    totals: dict[int, dict[str, object]] = {}
    for row in sales_rows:
        if row.product_id is None:
            continue
        bucket = totals.setdefault(row.product_id, {"quantity": 0, "revenue_cents": 0, "last_sale_at": None})
        bucket["quantity"] = int(bucket["quantity"]) + row.quantity
        bucket["revenue_cents"] = int(bucket["revenue_cents"]) + row.revenue_cents
        last_sale_at = bucket["last_sale_at"]
        if row.sold_at is not None and (last_sale_at is None or row.sold_at > last_sale_at):
            bucket["last_sale_at"] = row.sold_at

    errors = [] if sales_rows else [_missing_sales_message(session)]
    return EtsySalesSummary("etsy_sales_csv", lookback_days, len(sales_rows), _signals_for_products(session, totals), errors)


def _signals_for_products(session: Session, totals: dict[int, dict[str, object]]) -> list[ProductSalesSignal]:
    products = list(session.scalars(select(ProductRecord).order_by(ProductRecord.name)))
    signals: list[ProductSalesSignal] = []
    for product in products:
        bucket = totals.get(product.id, {})
        quantity = int(bucket.get("quantity") or 0)
        signal = "popular" if quantity > 0 else "slow_boost"
        signals.append(
            ProductSalesSignal(
                product_id=product.id,
                product_name=product.name,
                external_id=product.external_id,
                canonical_url=product.canonical_url,
                recent_quantity=quantity,
                recent_revenue_cents=int(bucket.get("revenue_cents") or 0),
                last_sale_at=bucket.get("last_sale_at") if isinstance(bucket.get("last_sale_at"), datetime) else None,
                signal=signal,
            )
        )
    return sorted(signals, key=lambda item: (-item.recent_quantity, item.product_name.lower()))


def _missing_sales_message(session: Session) -> str:
    record = session.scalar(select(SyncMetadata).where(SyncMetadata.source_name == "etsy_sales_csv"))
    if record is None:
        return "No Etsy sales CSV has been imported yet; weekly planning is using local product data only."
    return "No Etsy sales rows were found inside the lookback window; weekly planning is using local product data only."
