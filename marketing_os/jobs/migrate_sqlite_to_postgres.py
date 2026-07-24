from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass

from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import Engine

from ..db_models import Base


@dataclass
class TableMigration:
    table: str
    source_rows: int
    destination_rows_before: int
    copied_rows: int = 0
    destination_rows_after: int = 0
    conflict: str = ""


def plan_migration(source: Engine, destination: Engine) -> list[TableMigration]:
    source_tables = set(inspect(source).get_table_names())
    destination_tables = set(inspect(destination).get_table_names())
    report: list[TableMigration] = []
    with source.connect() as source_connection, destination.connect() as destination_connection:
        for table in Base.metadata.sorted_tables:
            if table.name not in source_tables:
                continue
            if table.name not in destination_tables:
                report.append(TableMigration(table.name, _count(source_connection, table), 0, conflict="missing_destination_table"))
                continue
            source_rows = _count(source_connection, table)
            destination_rows = _count(destination_connection, table)
            report.append(
                TableMigration(
                    table.name,
                    source_rows,
                    destination_rows,
                    conflict="destination_not_empty" if destination_rows else "",
                )
            )
    return report


def migrate(source: Engine, destination: Engine) -> list[TableMigration]:
    report = plan_migration(source, destination)
    conflicts = [entry for entry in report if entry.conflict]
    if conflicts:
        names = ", ".join(f"{entry.table}:{entry.conflict}" for entry in conflicts)
        raise RuntimeError(f"Migration refused because of destination conflicts: {names}")

    source_table_names = {entry.table for entry in report}
    with source.connect() as source_connection, destination.begin() as destination_connection:
        for table in Base.metadata.sorted_tables:
            if table.name not in source_table_names:
                continue
            rows = [dict(row._mapping) for row in source_connection.execute(select(table))]
            if rows:
                destination_connection.execute(table.insert(), rows)
            entry = next(item for item in report if item.table == table.name)
            entry.copied_rows = len(rows)
            entry.destination_rows_after = _count(destination_connection, table)
            if entry.destination_rows_after != entry.source_rows:
                raise RuntimeError(
                    f"Verification failed for {table.name}: "
                    f"source={entry.source_rows}, destination={entry.destination_rows_after}"
                )
        _reset_postgres_sequences(destination_connection)
    return report


def _count(connection, table) -> int:
    return int(connection.scalar(select(func.count()).select_from(table)) or 0)


def _reset_postgres_sequences(connection) -> None:
    if connection.dialect.name != "postgresql":
        return
    preparer = connection.dialect.identifier_preparer
    for table in Base.metadata.sorted_tables:
        primary_keys = list(table.primary_key.columns)
        if len(primary_keys) != 1:
            continue
        column = primary_keys[0]
        if not hasattr(column.type, "python_type") or column.type.python_type is not int:
            continue
        sequence = connection.scalar(
            text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
            {"table_name": table.name, "column_name": column.name},
        )
        if not sequence:
            continue
        table_name = preparer.format_table(table)
        column_name = preparer.quote(column.name)
        maximum = connection.scalar(
            text(f"SELECT MAX({column_name}) FROM {table_name}")
        )
        connection.execute(
            text("SELECT setval(CAST(:sequence AS regclass), :value, :is_called)"),
            {
                "sequence": sequence,
                "value": int(maximum or 1),
                "is_called": maximum is not None,
            },
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dry-run or perform SQLite to PostgreSQL cutover copy")
    parser.add_argument("--source", required=True, help="SQLite SQLAlchemy URL")
    parser.add_argument("--destination", required=True, help="Migrated destination SQLAlchemy URL")
    parser.add_argument("--apply", action="store_true", help="Copy data; omitted means read-only dry run")
    parser.add_argument("--report", help="Optional JSON report path")
    args = parser.parse_args(argv)
    if not args.source.startswith("sqlite:"):
        raise SystemExit("--source must be a SQLite SQLAlchemy URL")
    if os.environ.get("MARKETING_OS_ENV", "").lower() == "production" and not args.destination.startswith("postgresql"):
        raise SystemExit("Production cutover destination must be PostgreSQL")
    source = create_engine(args.source, future=True)
    destination = create_engine(args.destination, future=True)
    entries = migrate(source, destination) if args.apply else plan_migration(source, destination)
    payload = {
        "mode": "apply" if args.apply else "dry_run",
        "safe_to_apply": not any(entry.conflict for entry in entries),
        "tables": [asdict(entry) for entry in entries],
    }
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.report:
        from pathlib import Path

        Path(args.report).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if payload["safe_to_apply"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
