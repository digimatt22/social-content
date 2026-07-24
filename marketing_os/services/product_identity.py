from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db_models import ProductExternalReference, ProductIdentityRecord, ProductRecord, utc_now


ETSY_LISTING_PATTERN = re.compile(r"/listing/(\d+)")


def find_product_by_identity(session: Session, source: str, external_id: str, url: str, name: str) -> ProductRecord | None:
    if external_id:
        reference = session.scalar(
            select(ProductExternalReference).where(
                ProductExternalReference.source_name == source,
                ProductExternalReference.external_id == external_id,
            )
        )
        if reference:
            return reference.product
        record = session.scalar(select(ProductRecord).where(ProductRecord.external_source == source, ProductRecord.external_id == external_id))
        if record:
            return record
    if url:
        reference = session.scalar(
            select(ProductExternalReference).where(
                ProductExternalReference.source_name == source,
                ProductExternalReference.canonical_url == url,
            )
        )
        if reference:
            return reference.product
        record = session.scalar(select(ProductRecord).where(ProductRecord.canonical_url == url))
        if record:
            return record
    if name:
        record = session.scalar(select(ProductRecord).where(ProductRecord.name == name))
        if record:
            return record
    return _find_by_normalized_name(session, name)


def remember_product_reference(
    session: Session,
    product: ProductRecord,
    source: str,
    external_id: str,
    url: str,
    display_name: str,
) -> ProductExternalReference | None:
    if not external_id:
        return None
    reference = session.scalar(
        select(ProductExternalReference).where(
            ProductExternalReference.source_name == source,
            ProductExternalReference.external_id == external_id,
        )
    )
    if reference is None:
        reference = ProductExternalReference(source_name=source, external_id=external_id, product=product)
        session.add(reference)
    reference.product = product
    reference.canonical_url = url or reference.canonical_url
    reference.display_name = display_name or reference.display_name
    reference.last_seen_at = utc_now()
    return reference


def normalize_product_name(value: str) -> str:
    normalized = value.lower().replace("&", " and ")
    normalized = re.sub(r"https?://\S+", " ", normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())


def _find_by_normalized_name(session: Session, name: str) -> ProductRecord | None:
    normalized = normalize_product_name(name)
    if not normalized:
        return None

    products = list(session.scalars(select(ProductRecord).order_by(ProductRecord.name)))
    normalized_products = [(product, normalize_product_name(product.name)) for product in products]
    for product, product_name in normalized_products:
        if product_name == normalized:
            return product

    incoming_tokens = normalized.split()
    candidates: list[tuple[int, ProductRecord]] = []
    for product, product_name in normalized_products:
        product_tokens = product_name.split()
        if _is_prefix_product_match(incoming_tokens, product_tokens):
            candidates.append((len(product_tokens), product))
        elif _is_prefix_product_match(product_tokens, incoming_tokens):
            candidates.append((len(incoming_tokens), product))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _is_prefix_product_match(longer_tokens: list[str], shorter_tokens: list[str]) -> bool:
    if len(shorter_tokens) < 2 or "duck" not in shorter_tokens:
        return False
    if len(shorter_tokens) > len(longer_tokens):
        return False
    return longer_tokens[: len(shorter_tokens)] == shorter_tokens


@dataclass(frozen=True)
class IdentityException:
    product_id: int
    product_name: str
    reason: str


def etsy_listing_id(value: str) -> str:
    match = ETSY_LISTING_PATTERN.search(value or "")
    return match.group(1) if match else ""


def reconcile_product_identities(
    session: Session,
    website_products: list[dict],
) -> dict:
    by_etsy = {
        etsy_listing_id(str(item.get("etsyUrl", ""))): item
        for item in website_products
        if etsy_listing_id(str(item.get("etsyUrl", "")))
    }
    exceptions: list[IdentityException] = []
    mapped = 0
    products = list(session.scalars(select(ProductRecord).order_by(ProductRecord.id)))
    for product in products:
        listing_id = product.external_id if product.external_source == "etsy" else etsy_listing_id(product.canonical_url)
        website = by_etsy.get(listing_id)
        identity = session.scalar(
            select(ProductIdentityRecord).where(ProductIdentityRecord.product_id == product.id)
        )
        if identity is None:
            identity = ProductIdentityRecord(product_id=product.id)
            session.add(identity)
        identity.etsy_listing_id = listing_id or None
        identity.checked_at = utc_now()
        if not listing_id:
            identity.website_id = None
            identity.mapping_state = "exception"
            identity.exception_reason = "missing_etsy_listing_id"
        elif website is None:
            identity.website_id = None
            identity.mapping_state = "exception"
            identity.exception_reason = "no_website_product_with_matching_etsy_listing"
        else:
            identity.website_id = str(website.get("id", ""))
            identity.website_slug = str(website.get("slug") or website.get("id") or "")
            identity.mapping_state = "mapped"
            identity.exception_reason = ""
            mapped += 1
        if identity.mapping_state != "mapped":
            exceptions.append(IdentityException(product.id, product.name, identity.exception_reason))
    session.flush()
    return {
        "marketing_products": len(products),
        "website_products": len(website_products),
        "mapped": mapped,
        "exceptions": [asdict(item) for item in exceptions],
    }
