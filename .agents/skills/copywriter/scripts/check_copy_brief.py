#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED = ["destination", "audience", "goal", "details"]
RECOMMENDED = ["brand_voice", "format"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Check a normalized copywriting brief for missing inputs.")
    parser.add_argument("--brief", required=True)
    args = parser.parse_args()

    brief = json.loads(Path(args.brief).read_text(encoding="utf-8"))
    missing = [field for field in REQUIRED if not str(brief.get(field, "")).strip()]
    warnings = [field for field in RECOMMENDED if not str(brief.get(field, "")).strip()]
    result = {
        "status": "blocked" if missing else "ready",
        "missing_required": missing,
        "missing_recommended": warnings,
        "notes": [],
    }
    if not missing and warnings:
        result["status"] = "ready_with_assumptions"
        result["notes"].append("Missing recommended fields can be inferred, but output should label assumptions.")
    if not missing:
        result["notes"].append("Brief has the minimum fields needed for grounded copy generation.")

    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
