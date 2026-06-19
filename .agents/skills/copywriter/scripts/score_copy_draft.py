#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


GENERIC_PHRASES = [
    "don't miss out",
    "game changer",
    "best ever",
    "limited time only",
    "act now",
    "perfect for everyone",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic checks on a copy draft.")
    parser.add_argument("--copy", required=True, help="Path to draft text.")
    parser.add_argument("--brief", required=True, help="Path to normalized brief JSON.")
    args = parser.parse_args()

    copy = Path(args.copy).read_text(encoding="utf-8").strip()
    brief = json.loads(Path(args.brief).read_text(encoding="utf-8"))
    normalized = copy.lower()
    warnings: list[str] = []
    passed: list[str] = []

    if len(copy) <= _length_limit(str(brief.get("destination", ""))):
        passed.append("Length fits the destination guardrail.")
    else:
        warnings.append("Draft may be too long for the destination.")

    if _has_cta(copy):
        passed.append("Draft appears to include a CTA.")
    else:
        warnings.append("CTA is unclear or missing.")

    for term in brief.get("must_include", []) or []:
        if str(term).lower() in normalized:
            passed.append(f"Includes required term: {term}")
        else:
            warnings.append(f"Missing required term: {term}")

    avoided = [str(term) for term in brief.get("avoid", []) or []]
    avoided.extend(GENERIC_PHRASES)
    flagged = [term for term in avoided if term and term.lower() in normalized]
    if flagged:
        warnings.append("Contains avoided or generic wording: " + ", ".join(flagged[:8]))
    else:
        passed.append("Avoids configured banned terms and common generic phrases.")

    if _mentions_detail(copy, str(brief.get("details", ""))):
        passed.append("Uses at least one concrete detail from the brief.")
    else:
        warnings.append("Could use more concrete detail from the brief.")

    result = {
        "label": _label(warnings),
        "passed": passed,
        "warnings": warnings,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result["label"] in {"needs_rewrite", "blocked"} else 0


def _length_limit(destination: str) -> int:
    normalized = destination.lower()
    if "newsletter" in normalized or "email" in normalized:
        return 1800
    if "blog" in normalized:
        return 12000
    if "linkedin" in normalized:
        return 1300
    if any(value in normalized for value in ["instagram", "facebook", "social"]):
        return 1200
    return 2500


def _has_cta(copy: str) -> bool:
    normalized = copy.lower()
    cta_markers = ["shop", "read", "reply", "tell me", "join", "book", "download", "learn", "visit", "follow", "?"]
    return any(marker in normalized for marker in cta_markers)


def _mentions_detail(copy: str, details: str) -> bool:
    tokens = [token.lower() for token in re.findall(r"[a-zA-Z0-9]{4,}", details)]
    if not tokens:
        return True
    normalized = copy.lower()
    return any(token in normalized for token in tokens[:20])


def _label(warnings: list[str]) -> str:
    if not warnings:
        return "ready"
    if len(warnings) <= 2:
        return "needs_light_edit"
    return "needs_rewrite"


if __name__ == "__main__":
    raise SystemExit(main())
