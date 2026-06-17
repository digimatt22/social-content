from __future__ import annotations

from datetime import date
from pathlib import Path

from marketing_os.render import render_plan_markdown
from marketing_os.workflow import build_plan


def main() -> int:
    plan = build_plan(start_date=date(2026, 6, 17))
    output = Path("outputs/demo-marketing-plan.md")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_plan_markdown(plan), encoding="utf-8")

    assert len(plan.calendar) == 30
    assert len(plan.instagram_posts) == 30
    assert len(plan.facebook_posts) == 30
    assert len(plan.instagram_reels) == 10
    assert len(plan.blog_topics) == 10
    assert len(plan.email_newsletters) == 10
    assert plan.weekly_report is not None
    assert plan.recommendations

    print("Demo workflow completed successfully.")
    print(f"Output: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
