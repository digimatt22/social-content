#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED = ["destination", "subject"]
RECOMMENDED = ["audience", "goal", "format", "brand_style", "aspect_ratio"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Check a normalized image brief for missing inputs.")
    parser.add_argument("--brief", required=True)
    args = parser.parse_args()

    brief = json.loads(Path(args.brief).read_text(encoding="utf-8"))
    missing = [field for field in REQUIRED if not str(brief.get(field, "")).strip()]
    warnings = [field for field in RECOMMENDED if not str(brief.get(field, "")).strip()]
    notes: list[str] = []
    if brief.get("provider_path") == "magnific-mcp" and not brief.get("reference_images"):
        missing.append("reference_images")
        notes.append("Magnific/Freepik product-preserving work must include reference images before generation.")
    result = {
        "status": "blocked" if missing else ("ready_with_assumptions" if warnings else "ready"),
        "missing_required": missing,
        "missing_recommended": sorted(set(warnings)),
        "notes": notes,
    }
    if not missing:
        result["notes"].append("Brief has the minimum fields needed to prepare an image prompt.")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
