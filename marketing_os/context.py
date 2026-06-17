from __future__ import annotations

import json
import re
from pathlib import Path

from .models import BusinessContext, ProductEntity


REQUIRED_BUSINESS_FILES = (
    "company-profile.md",
    "business-goals.md",
    "products.md",
    "audiences.md",
    "brand-voice.md",
    "marketing-channels.md",
)
PRODUCT_CATALOG_FILE = "product-catalog.json"


class BusinessContextError(RuntimeError):
    pass


def load_business_context(business_dir: str | Path = "docs/business") -> BusinessContext:
    """Load business context from Markdown files.

    The loader reads the docs on every call. This keeps business knowledge editable
    without code changes and avoids hardcoding MattMadeMe business facts.
    """

    root = Path(business_dir)
    if not root.exists():
        raise BusinessContextError(f"Business directory not found: {root}")

    raw: dict[str, str] = {}
    missing: list[str] = []
    for name in REQUIRED_BUSINESS_FILES:
        path = root / name
        if not path.exists():
            missing.append(name)
            continue
        raw[name] = path.read_text(encoding="utf-8")

    if missing:
        raise BusinessContextError("Missing business files: " + ", ".join(missing))

    product_entities = _load_product_catalog(root / PRODUCT_CATALOG_FILE)
    structured_product_names = [product.name for product in product_entities]
    products = _dedupe(
        structured_product_names
        +
        _table_products(raw["products.md"])
        + _section_bullets(raw["products.md"], "Current Public Ducks And Themes")
        + _duck_bullets(raw["products.md"])
    )
    momentum_products = _dedupe(
        [product.name for product in product_entities if product.status == "momentum"]
        + _products_from_colon_bullets(raw["products.md"], "Current Momentum")
        + _table_products(raw["products.md"])[:8]
    )
    upcoming_products = _section_bullets(raw["products.md"], "Upcoming / Work-In-Progress Designs")
    audiences = _section_headings(raw["audiences.md"], "Customer Personas")
    goals = _numbered_headings(raw["business-goals.md"])
    voice_pillars = _colon_bullet_labels(raw["brand-voice.md"], "Voice Pillars")
    useful_phrases = _section_bullets(raw["brand-voice.md"], "Useful Phrases")
    avoid = _section_bullets(raw["brand-voice.md"], "Avoid")
    channels = _active_channels(raw["marketing-channels.md"])
    seasonal = _section_bullets(raw["company-profile.md"], "Priority seasonal/event windows")

    return BusinessContext(
        source_files=[str(root / name) for name in REQUIRED_BUSINESS_FILES],
        raw_markdown=raw,
        business_goals=goals,
        products=products,
        momentum_products=momentum_products,
        upcoming_products=upcoming_products,
        audiences=audiences,
        voice_pillars=voice_pillars,
        useful_phrases=useful_phrases,
        avoid=avoid,
        channels=channels,
        seasonal_windows=seasonal,
        product_entities=product_entities,
        etsy_url=_first_url(raw["marketing-channels.md"], "Etsy"),
        website_url=_first_url(raw["marketing-channels.md"], "Website"),
    )


def _load_product_catalog(path: Path) -> list[ProductEntity]:
    if not path.exists():
        return []

    data = json.loads(path.read_text(encoding="utf-8"))
    entities: list[ProductEntity] = []
    for item in data.get("products", []):
        entities.append(
            ProductEntity(
                name=item["name"],
                status=item["status"],
                primary_audience=item["primary_audience"],
                secondary_audiences=list(item.get("secondary_audiences", [])),
                best_channels=list(item.get("best_channels", [])),
                use_cases=list(item.get("use_cases", [])),
                seasonality=list(item.get("seasonality", [])),
                sales_momentum_note=item.get("sales_momentum_note", ""),
                launch_priority=item.get("launch_priority", "medium"),
            )
        )
    return entities


def _section(markdown: str, heading: str) -> str:
    heading_pattern = re.compile(rf"^(#+)\s+{re.escape(heading)}\s*$", re.MULTILINE)
    match = heading_pattern.search(markdown)
    if not match:
        return ""

    level = len(match.group(1))
    start = match.end()
    next_heading = re.compile(r"^(#+)\s+.+$", re.MULTILINE)
    for next_match in next_heading.finditer(markdown, start):
        if len(next_match.group(1)) <= level:
            return markdown[start:next_match.start()].strip()
    return markdown[start:].strip()


def _section_bullets(markdown: str, heading: str) -> list[str]:
    body = _section(markdown, heading)
    return [line[2:].strip() for line in body.splitlines() if line.startswith("- ")]


def _section_headings(markdown: str, parent_heading: str) -> list[str]:
    body = _section(markdown, parent_heading)
    return [m.group(1).strip() for m in re.finditer(r"^###\s+(.+)$", body, re.MULTILINE)]


def _numbered_headings(markdown: str) -> list[str]:
    return [
        re.sub(r"^\d+\.\s*", "", m.group(1).strip())
        for m in re.finditer(r"^###\s+(.+)$", markdown, re.MULTILINE)
        if re.match(r"\d+\.", m.group(1).strip())
    ]


def _colon_bullet_labels(markdown: str, heading: str) -> list[str]:
    labels: list[str] = []
    for bullet in _section_bullets(markdown, heading):
        labels.append(bullet.split(":", 1)[0].strip())
    return labels


def _products_from_colon_bullets(markdown: str, heading: str) -> list[str]:
    products: list[str] = []
    for bullet in _section_bullets(markdown, heading):
        left = bullet.split(":", 1)[0].strip()
        if "Duck" in left:
            products.append(left)
    return products


def _duck_bullets(markdown: str) -> list[str]:
    products: list[str] = []
    for line in markdown.splitlines():
        if not line.startswith("- ") or "Duck" not in line:
            continue
        value = line[2:].strip()
        if ":" in value:
            value = value.split(":", 1)[0].strip()
        if len(value.split()) <= 8:
            products.append(value)
    return products


def _table_products(markdown: str) -> list[str]:
    products: list[str] = []
    for line in markdown.splitlines():
        if not line.startswith("|") or "---" in line or "Rank" in line:
            continue
        cells = [cell.strip().strip("`") for cell in line.strip("|").split("|")]
        if len(cells) > 1 and cells[0].isdigit():
            products.append(cells[1])
    return products


def _active_channels(markdown: str) -> list[str]:
    channels: list[str] = []
    for bullet in _section_bullets(markdown, "Active Channels"):
        channels.append(bullet.split(":", 1)[0].strip())
    return channels


def _first_url(markdown: str, label: str) -> str | None:
    pattern = re.compile(rf"-\s+{re.escape(label)}:\s+`([^`]+)`")
    match = pattern.search(markdown)
    return match.group(1) if match else None


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = value.strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result
