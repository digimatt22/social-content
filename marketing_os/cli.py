from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from .context import load_business_context
from .render import render_plan_markdown
from .workflow import build_plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MattMadeMe local-first marketing assistant")
    parser.add_argument("--business-dir", default="docs/business", help="Path to business Markdown docs")
    parser.add_argument("--start-date", default=None, help="Calendar start date in YYYY-MM-DD format")
    parser.add_argument("--output", default=None, help="Optional Markdown output path")
    parser.add_argument("--check-context", action="store_true", help="Load business context and print a summary")
    args = parser.parse_args(argv)

    if args.check_context:
        context = load_business_context(args.business_dir)
        print(f"Loaded {len(context.source_files)} business files")
        print(f"Products: {len(context.products)}")
        print(f"Audiences: {len(context.audiences)}")
        print(f"Goals: {len(context.business_goals)}")
        return 0

    start = date.fromisoformat(args.start_date) if args.start_date else date.today()
    plan = build_plan(args.business_dir, start)
    markdown = render_plan_markdown(plan)

    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown, encoding="utf-8")
        print(f"Wrote marketing plan to {output}")
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

