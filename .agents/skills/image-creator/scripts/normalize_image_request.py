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
    "subject",
    "brand_style",
    "details",
    "reference_images",
    "aspect_ratio",
    "provider_path",
    "must_include",
    "avoid",
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
    parser = argparse.ArgumentParser(description="Normalize a loose image request into a reusable brief.")
    parser.add_argument("--input-json", default="")
    parser.add_argument("--destination", default="")
    parser.add_argument("--format", default="")
    parser.add_argument("--audience", default="")
    parser.add_argument("--goal", default="")
    parser.add_argument("--subject", default="")
    parser.add_argument("--brand-style", default="")
    parser.add_argument("--details", default="")
    parser.add_argument("--reference-image", action="append", default=[])
    parser.add_argument("--aspect-ratio", default="")
    parser.add_argument("--provider-path", choices=["built-in", "magnific-mcp"], default="magnific-mcp")
    parser.add_argument("--must-include", default="")
    parser.add_argument("--avoid", default="")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    brief = {field: "" for field in FIELDS}
    brief.update(load_json(args.input_json))
    for key, value in {
        "destination": args.destination,
        "format": args.format,
        "audience": args.audience,
        "goal": args.goal,
        "subject": args.subject,
        "brand_style": args.brand_style,
        "details": args.details,
        "aspect_ratio": args.aspect_ratio,
        "provider_path": args.provider_path,
    }.items():
        if value:
            brief[key] = value.strip()

    if args.reference_image:
        brief["reference_images"] = args.reference_image
    elif not isinstance(brief.get("reference_images"), list):
        brief["reference_images"] = split_csv(str(brief.get("reference_images", "")))
    brief["must_include"] = split_csv(args.must_include) if args.must_include else _ensure_list(brief.get("must_include"))
    brief["avoid"] = split_csv(args.avoid) if args.avoid else _ensure_list(brief.get("avoid"))
    brief["assumptions"] = []
    if not brief.get("aspect_ratio"):
        brief["aspect_ratio"] = _default_aspect_ratio(str(brief.get("destination", "")), str(brief.get("format", "")))
        brief["assumptions"].append(f"aspect_ratio inferred as {brief['aspect_ratio']}")
    if brief.get("provider_path") == "magnific-mcp" and not brief.get("reference_images"):
        brief["assumptions"].append("Magnific/Freepik MCP selected without reference images; prompt will be a handoff until references are supplied.")

    text = json.dumps(brief, indent=2, sort_keys=True)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


def _ensure_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return split_csv(str(value or ""))


def _default_aspect_ratio(destination: str, format_name: str) -> str:
    normalized = f"{destination} {format_name}".lower()
    if "story" in normalized or "reel" in normalized:
        return "9:16"
    if "pinterest" in normalized:
        return "2:3"
    if "blog" in normalized or "newsletter" in normalized or "hero" in normalized:
        return "16:9"
    return "1:1"


if __name__ == "__main__":
    raise SystemExit(main())
