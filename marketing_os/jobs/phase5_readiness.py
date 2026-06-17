from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..db import create_db_engine, init_db, session_factory, session_scope
from ..services.phase5_readiness import (
    build_phase5_approval_packet,
    serialize_phase5_approval_packet,
    serialize_phase5_readiness,
    write_phase5_approval_packet,
)


def run(
    db_path: str | Path | None = None,
    export_dir: str | Path = "data/exports",
    export_markdown: bool = False,
) -> dict[str, object]:
    engine = create_db_engine(db_path)
    init_db(engine)
    factory = session_factory(engine)
    try:
        with session_scope(factory) as session:
            packet = build_phase5_approval_packet(session)
            payload = serialize_phase5_approval_packet(packet)
            summary: dict[str, object] = {
                "readiness": serialize_phase5_readiness(packet.readiness),
                "packet": payload,
                "export_path": None,
            }
            if export_markdown:
                summary["export_path"] = str(write_phase5_approval_packet(session, export_dir))
            return summary
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report or export Phase 5 final-proof readiness.")
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--export-dir", default="data/exports")
    parser.add_argument("--export-markdown", action="store_true")
    parser.add_argument(
        "--fail-on-incomplete",
        action="store_true",
        help="Return exit code 2 when final Phase 5 proof items are still incomplete.",
    )
    args = parser.parse_args(argv)

    summary = run(db_path=args.db_path, export_dir=args.export_dir, export_markdown=args.export_markdown)
    print(json.dumps(summary, indent=2))
    if args.fail_on_incomplete and not summary["readiness"]["complete"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
