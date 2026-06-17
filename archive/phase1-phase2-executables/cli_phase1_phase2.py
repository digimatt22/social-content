from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from marketing_os.context import load_business_context
from marketing_os.phase2 import build_phase2_plan
from marketing_os.render import render_plan_markdown
from marketing_os.render_phase2 import render_phase2_plan_markdown
from marketing_os.workflow import build_plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MattMadeMe local-first marketing assistant")
    parser.add_argument("--business-dir", default="docs/business", help="Path to business Markdown docs")
    parser.add_argument("--start-date", default=None, help="Calendar start date in YYYY-MM-DD format")
    parser.add_argument("--output", default=None, help="Optional Markdown output path")
    parser.add_argument("--check-context", action="store_true", help="Load business context and print a summary")
    parser.add_argument("--phase", choices=["1", "2"], default="1", help="Planner phase to run")
    parser.add_argument("--mode", choices=["light", "standard", "launch", "holiday", "event"], default="standard", help="Phase 2 planning mode")
    parser.add_argument("--weekly-capacity-minutes", type=int, default=None, help="Phase 2 owner capacity for the week")
    args = parser.parse_args(argv)

    if args.check_context:
        context = load_business_context(args.business_dir)
        print(f"Loaded {len(context.source_files)} business files")
        print(f"Products: {len(context.products)}")
        print(f"Structured products: {len(context.product_entities)}")
        print(f"Audiences: {len(context.audiences)}")
        print(f"Goals: {len(context.business_goals)}")
        return 0

    start = date.fromisoformat(args.start_date) if args.start_date else date.today()
    if args.phase == "2":
        plan = build_phase2_plan(
            args.business_dir,
            start_date=start,
            mode=args.mode,
            weekly_capacity_minutes=args.weekly_capacity_minutes,
        )
        markdown = render_phase2_plan_markdown(plan)
    else:
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
