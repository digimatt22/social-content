from __future__ import annotations

import argparse
import os
from datetime import date, timedelta
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, url_for
from sqlalchemy import select

from .db import create_db_engine, init_db, session_factory, session_scope
from .db_models import AssetRecord, MetricRecord, PlanRecord, TaskRecord, TemplateRecord
from .phase3 import (
    ROLE_OPTIONS,
    TASK_STATUSES,
    add_metric,
    ensure_default_plan,
    generate_and_persist_plan,
    json_list,
    playbook_for,
    seed_database,
    status_counts,
    template_body,
    update_task_status,
)


def create_app(db_path: str | Path | None = None, business_dir: str = "docs/business") -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("MARKETING_OS_SECRET", "local-dev-only")
    engine = create_db_engine(db_path)
    init_db(engine)
    factory = session_factory(engine)

    with session_scope(factory) as session:
        seed_database(session, business_dir)
        ensure_default_plan(session, business_dir)

    app.config["SESSION_FACTORY"] = factory
    app.config["BUSINESS_DIR"] = business_dir

    @app.context_processor
    def inject_helpers() -> dict[str, object]:
        return {
            "today": date.today(),
            "json_list": json_list,
            "playbook_for": playbook_for,
            "statuses": TASK_STATUSES,
            "roles": ROLE_OPTIONS,
        }

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/")
    def dashboard() -> str:
        today = date.today()
        week_end = today + timedelta(days=6)
        role = request.args.get("role", "all")
        with session_scope(factory) as session:
            plan = session.scalars(select(PlanRecord).order_by(PlanRecord.generated_at.desc())).first()
            query = select(TaskRecord).where(TaskRecord.due_date <= week_end).order_by(TaskRecord.due_date, TaskRecord.id)
            if role != "all":
                query = query.where(TaskRecord.owner_role == role)
            tasks = list(session.scalars(query))
            today_tasks = [task for task in tasks if task.due_date <= today and task.status not in {"complete", "skipped"}]
            plan_tasks = list(session.scalars(select(TaskRecord).where(TaskRecord.plan_id == plan.id).order_by(TaskRecord.due_date))) if plan else []
            return render_template(
                "dashboard.html",
                active="today",
                plan=plan,
                today_tasks=today_tasks,
                week_tasks=tasks,
                status_counts=status_counts(plan_tasks),
                selected_role=role,
            )

    @app.get("/calendar")
    def calendar() -> str:
        with session_scope(factory) as session:
            plan = session.scalars(select(PlanRecord).order_by(PlanRecord.generated_at.desc())).first()
            tasks = list(session.scalars(select(TaskRecord).where(TaskRecord.plan_id == plan.id).order_by(TaskRecord.due_date))) if plan else []
            return render_template("calendar.html", active="calendar", plan=plan, tasks=tasks)

    @app.get("/plans")
    def plans() -> str:
        with session_scope(factory) as session:
            all_plans = list(session.scalars(select(PlanRecord).order_by(PlanRecord.generated_at.desc())))
            return render_template("plans.html", active="plans", plans=all_plans)

    @app.post("/plans/generate")
    def generate_plan() -> str:
        mode = request.form.get("mode", "standard")
        start_text = request.form.get("start_date") or date.today().isoformat()
        start = date.fromisoformat(start_text)
        with session_scope(factory) as session:
            plan = generate_and_persist_plan(session, app.config["BUSINESS_DIR"], mode=mode, start_date=start)
            flash(f"Generated {mode} plan starting {start.isoformat()}.")
            return redirect(url_for("task_detail", task_id=plan.tasks[0].id))

    @app.get("/tasks/<int:task_id>")
    def task_detail(task_id: int) -> str:
        with session_scope(factory) as session:
            task = session.get(TaskRecord, task_id)
            if task is None:
                return render_template("not_found.html", active="today"), 404
            metrics = list(session.scalars(select(MetricRecord).where(MetricRecord.task_id == task_id).order_by(MetricRecord.recorded_on.desc())))
            playbook = playbook_for(task.platform, task.content_type)
            return render_template("task_detail.html", active="today", task=task, playbook=playbook, metrics=metrics)

    @app.post("/tasks/<int:task_id>/status")
    def task_status(task_id: int) -> str:
        status = request.form.get("status", "ready to post")
        notes = request.form.get("notes", "")
        with session_scope(factory) as session:
            update_task_status(session, task_id, status, notes)
            flash("Task status saved.")
        return redirect(url_for("task_detail", task_id=task_id))

    @app.post("/tasks/<int:task_id>/metrics")
    def task_metrics(task_id: int) -> str:
        def int_or_none(name: str) -> int | None:
            value = request.form.get(name, "").strip()
            return int(value) if value else None

        with session_scope(factory) as session:
            add_metric(
                session,
                task_id=task_id,
                post_url=request.form.get("post_url", ""),
                reach=int_or_none("reach"),
                likes=int_or_none("likes"),
                comments=int_or_none("comments"),
                shares=int_or_none("shares"),
                saves=int_or_none("saves"),
                etsy_visits=int_or_none("etsy_visits"),
                etsy_orders=int_or_none("etsy_orders"),
                email_signups=int_or_none("email_signups"),
                notes=request.form.get("notes", ""),
            )
            flash("Metrics saved.")
        return redirect(url_for("task_detail", task_id=task_id))

    @app.get("/assets")
    def assets() -> str:
        with session_scope(factory) as session:
            records = list(session.scalars(select(AssetRecord).order_by(AssetRecord.name)))
            return render_template("assets.html", active="assets", assets=records)

    @app.get("/templates")
    def templates() -> str:
        with session_scope(factory) as session:
            records = list(session.scalars(select(TemplateRecord).order_by(TemplateRecord.template_type, TemplateRecord.name)))
            return render_template("templates.html", active="templates", templates=records, template_body=template_body)

    @app.get("/metrics")
    def metrics() -> str:
        with session_scope(factory) as session:
            records = list(session.scalars(select(MetricRecord).order_by(MetricRecord.recorded_on.desc(), MetricRecord.id.desc())))
            return render_template("metrics.html", active="metrics", metrics=records)

    @app.get("/settings")
    def settings() -> str:
        return render_template("settings.html", active="settings", business_dir=business_dir)

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the MattMadeMe Marketing OS local web console")
    parser.add_argument("--host", default=os.environ.get("MARKETING_OS_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MARKETING_OS_PORT", "8000")))
    parser.add_argument("--db-path", default=os.environ.get("MARKETING_OS_DB_PATH", "data/marketing_os.sqlite"))
    parser.add_argument("--business-dir", default=os.environ.get("MARKETING_OS_BUSINESS_DIR", "docs/business"))
    args = parser.parse_args(argv)

    app = create_app(args.db_path, args.business_dir)
    app.run(host=args.host, port=args.port, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
