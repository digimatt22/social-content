from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db_models import ProductSalesRecord, SyncMetadata, utc_now
from .product_identity import find_product_by_identity


@dataclass(frozen=True)
class EtsySalesCsvImportSummary:
    source: str
    path: str
    rows_seen: int
    imported: int
    updated: int
    skipped: int
    unmatched: int
    errors: list[str]


def import_etsy_sales_csv(session: Session, csv_path: str | Path, source_name: str = "etsy_sales_csv") -> EtsySalesCsvImportSummary:
    path = Path(csv_path)
    rows_seen = 0
    imported = 0
    updated = 0
    skipped = 0
    unmatched = 0
    errors: list[str] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows_seen += 1
            normalized = {_normalize_key(key): (value or "").strip() for key, value in row.items() if key is not None}
            sale = _sale_from_row(normalized, source_name)
            if sale is None:
                skipped += 1
                continue
            product = find_product_by_identity(session, "etsy", sale["listing_id"], "", sale["listing_title"])
            if product is None:
                unmatched += 1
            existing = session.scalar(select(ProductSalesRecord).where(ProductSalesRecord.source_name == source_name, ProductSalesRecord.external_id == sale["external_id"]))
            if existing is None:
                existing = ProductSalesRecord(source_name=source_name, external_id=sale["external_id"])
                session.add(existing)
                imported += 1
            else:
                updated += 1
            existing.product_id = product.id if product is not None else None
            existing.listing_id = sale["listing_id"]
            existing.listing_title = sale["listing_title"]
            existing.quantity = sale["quantity"]
            existing.revenue_cents = sale["revenue_cents"]
            existing.currency_code = sale["currency_code"]
            existing.sold_at = sale["sold_at"]
            existing.raw_data_json = json.dumps(row, sort_keys=True)
            existing.imported_at = utc_now()
    _record_sales_csv_sync(session, source_name, path.as_posix(), rows_seen, imported, updated, skipped, unmatched)
    session.flush()
    return EtsySalesCsvImportSummary(
        source=source_name,
        path=path.as_posix(),
        rows_seen=rows_seen,
        imported=imported,
        updated=updated,
        skipped=skipped,
        unmatched=unmatched,
        errors=errors,
    )


def _sale_from_row(row: dict[str, str], source_name: str) -> dict[str, object] | None:
    listing_id = _first(row, "listing_id", "listing id", "listingid")
    listing_title = _first(row, "listing_title", "title", "item_name", "item name", "name")
    external_id = _first(row, "transaction_id", "transaction id", "order_id", "order id", "receipt_id", "receipt id")
    sold_at = _parse_datetime(_first(row, "sale_date", "sale date", "date", "paid_date", "paid date", "created_timestamp"))
    quantity = _parse_int(_first(row, "quantity", "qty"), default=1)
    revenue_cents = _parse_money_cents(_first(row, "price", "item total", "order value", "gross sales", "amount", "revenue"))
    currency = _first(row, "currency", "currency_code", "currency code")
    if not listing_id and not listing_title:
        return None
    if not external_id:
        external_id = _dedupe_key(source_name, listing_id, listing_title, sold_at, quantity, revenue_cents)
    return {
        "external_id": external_id,
        "listing_id": listing_id,
        "listing_title": listing_title,
        "quantity": quantity,
        "revenue_cents": revenue_cents,
        "currency_code": currency,
        "sold_at": sold_at,
    }


def _first(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = row.get(_normalize_key(key))
        if value:
            return value
    return ""


def _normalize_key(value: str) -> str:
    return value.strip().lower().replace("-", " ").replace("_", " ")


def _parse_int(value: str, default: int = 0) -> int:
    try:
        return int(float(value.replace(",", "")))
    except (AttributeError, ValueError):
        return default


def _parse_money_cents(value: str) -> int:
    cleaned = value.replace("$", "").replace(",", "").strip()
    if not cleaned:
        return 0
    try:
        return int(round(float(cleaned) * 100))
    except ValueError:
        return 0


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    try:
        timestamp = int(value)
    except ValueError:
        return None
    return datetime.utcfromtimestamp(timestamp)


def _dedupe_key(source_name: str, listing_id: str, listing_title: str, sold_at: datetime | None, quantity: int, revenue_cents: int) -> str:
    raw = "|".join([source_name, listing_id, listing_title, sold_at.isoformat() if sold_at else "", str(quantity), str(revenue_cents)])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _record_sales_csv_sync(
    session: Session,
    source_name: str,
    path: str,
    rows_seen: int,
    imported: int,
    updated: int,
    skipped: int,
    unmatched: int,
) -> None:
    record = session.scalar(select(SyncMetadata).where(SyncMetadata.source_name == source_name))
    if record is None:
        record = SyncMetadata(source_name=source_name, source_path=path, notes="")
        session.add(record)
    record.source_path = path
    record.notes = (
        f"Imported Etsy sales CSV: rows={rows_seen}, imported={imported}, "
        f"updated={updated}, skipped={skipped}, unmatched={unmatched}."
    )
    record.synced_at = utc_now()
