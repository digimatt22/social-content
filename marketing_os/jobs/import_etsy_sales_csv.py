from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..db import create_db_engine, init_db, session_factory, session_scope
from ..services.etsy_sales_csv import import_etsy_sales_csv


def run(db_path: str | Path | None = None, csv_path: str | Path | None = None) -> dict[str, object]:
    if csv_path is None:
        raise ValueError("csv_path is required.")
    engine = create_db_engine(db_path)
    init_db(engine)
    factory = session_factory(engine)
    try:
        with session_scope(factory) as session:
            summary = import_etsy_sales_csv(session, csv_path)
            return summary.__dict__
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import a weekly Etsy sales CSV export for sales-aware social planning.")
    parser.add_argument("csv_path")
    parser.add_argument("--db-path", default=None)
    args = parser.parse_args(argv)
    print(json.dumps(run(db_path=args.db_path, csv_path=args.csv_path), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
