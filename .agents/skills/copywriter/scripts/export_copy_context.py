#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


BUSINESS_FILES = [
    "company-profile.md",
    "business-goals.md",
    "products.md",
    "audiences.md",
    "brand-voice.md",
    "marketing-channels.md",
]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Export MattMadeMe copywriting context as JSON.")
    parser.add_argument("--root", default=".", help="Marketing OS repo root.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    business_dir = root / "docs" / "business"
    context = {
        "business": {name: read_text(business_dir / name) for name in BUSINESS_FILES},
        "product_catalog": {},
        "content_briefs": [],
    }

    catalog_path = business_dir / "product-catalog.json"
    if catalog_path.exists():
        context["product_catalog"] = json.loads(catalog_path.read_text(encoding="utf-8"))

    briefs_dir = root / "data" / "exports" / "content-briefs"
    if briefs_dir.exists():
        for path in sorted(briefs_dir.glob("*.json")):
            context["content_briefs"].append(json.loads(path.read_text(encoding="utf-8")))

    print(json.dumps(context, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
