#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


FIELDS = [
    "destination",
    "format",
    "audience",
    "goal",
    "brand_voice",
    "details",
    "must_include",
    "avoid",
    "review_level",
]


def split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def load_json(path: str) -> dict[str, object]:
    if not path:
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Input JSON must be an object.")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize a loose copywriting request into a reusable brief.")
    parser.add_argument("--input-json", default="", help="Optional JSON object with copy request fields.")
    parser.add_argument("--destination", default="")
    parser.add_argument("--format", default="")
    parser.add_argument("--audience", default="")
    parser.add_argument("--goal", default="")
    parser.add_argument("--brand-voice", default="")
    parser.add_argument("--details", default="")
    parser.add_argument("--must-include", default="", help="Comma-separated required terms or facts.")
    parser.add_argument("--avoid", default="", help="Comma-separated avoided terms or claims.")
    parser.add_argument("--review-level", default="polished_draft")
    parser.add_argument("--output", default="", help="Optional output JSON path.")
    args = parser.parse_args()

    brief = {field: "" for field in FIELDS}
    brief.update(load_json(args.input_json))
    overrides = {
        "destination": args.destination,
        "format": args.format,
        "audience": args.audience,
        "goal": args.goal,
        "brand_voice": args.brand_voice,
        "details": args.details,
        "review_level": args.review_level,
    }
    for key, value in overrides.items():
        if value:
            brief[key] = value.strip()
    if args.must_include:
        brief["must_include"] = split_csv(args.must_include)
    elif not isinstance(brief.get("must_include"), list):
        brief["must_include"] = split_csv(str(brief.get("must_include", "")))
    if args.avoid:
        brief["avoid"] = split_csv(args.avoid)
    elif not isinstance(brief.get("avoid"), list):
        brief["avoid"] = split_csv(str(brief.get("avoid", "")))

    brief["assumptions"] = []
    if not brief.get("format") and brief.get("destination"):
        brief["format"] = _default_format(str(brief["destination"]))
        brief["assumptions"].append(f"format inferred as {brief['format']}")
    if not brief.get("review_level"):
        brief["review_level"] = "polished_draft"

    text = json.dumps(brief, indent=2, sort_keys=True)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


def _default_format(destination: str) -> str:
    normalized = destination.lower()
    if "newsletter" in normalized or "email" in normalized:
        return "newsletter section"
    if "blog" in normalized:
        return "blog article"
    if "ad" in normalized:
        return "ad copy"
    if any(value in normalized for value in ["instagram", "facebook", "linkedin", "pinterest", "social"]):
        return "social post"
    return "marketing copy"


if __name__ == "__main__":
    raise SystemExit(main())
