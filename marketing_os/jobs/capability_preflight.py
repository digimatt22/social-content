from __future__ import annotations

import argparse
import json

from ..services.capability_preflight import PROFILES, capability_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Marketing OS automation capabilities")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="foundation")
    args = parser.parse_args(argv)
    report = capability_report(args.profile)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
