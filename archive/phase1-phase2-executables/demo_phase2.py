from __future__ import annotations

from datetime import date
from pathlib import Path

from marketing_os.phase2 import build_phase2_plan
from marketing_os.render_phase2 import render_phase2_plan_markdown


def write_demo(mode: str) -> Path:
    plan = build_phase2_plan(start_date=date(2026, 6, 17), mode=mode)
    output = Path(f"outputs/demo-phase2-{mode}.md")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_phase2_plan_markdown(plan), encoding="utf-8")
    assert plan.validation_report.is_valid
    assert plan.calendar
    assert plan.weekly_actions
    assert plan.review_template.rows
    return output


def main() -> int:
    standard = write_demo("standard")
    launch = write_demo("launch")
    print("Phase 2 demo workflows completed successfully.")
    print(f"Standard output: {standard}")
    print(f"Launch output: {launch}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
