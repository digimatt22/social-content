from __future__ import annotations

import argparse
import os
import tempfile
from datetime import date
from pathlib import Path

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_file, url_for
from sqlalchemy import select
from werkzeug.utils import secure_filename

from .db import DEFAULT_DB_PATH, create_db_engine, init_db, session_factory, session_scope
from .db_models import AssetRecord, MetricRecord, PlanRecord, PlannedContentRecord, ProductRecord, TaskRecord, TemplateRecord
from .phase3 import (
    ROLE_OPTIONS,
    TASK_STATUSES,
    add_metric,
    ensure_default_plan,
    generate_and_persist_plan,
    json_list,
    link_generated_content_to_task,
    playbook_for,
    seed_database,
    status_counts,
    template_body,
    update_task_status,
)
from .services.insights import build_learning_summary, outcome_tags, serialize_learning_summary
from .phase4 import (
    OPERATOR_DEFAULT_ROLE,
    assign_asset_to_task,
    asset_inventory,
    asset_path,
    complete_task_status,
    backup_sqlite_database,
    completed_tasks,
    creative_asset_plans,
    data_health as build_data_health,
    export_operating_data,
    import_etsy_listing_csv,
    import_source_photo_to_inventory,
    metrics_due_tasks,
    platform_metric_fields,
    posting_guides,
    prepare_creative_generation_run,
    refresh_asset_file_state,
    register_local_source_photo,
    review_asset,
    scan_local_asset_folder,
    serialize_asset_view,
    serialize_creative_asset_plan,
    serialize_data_health_item,
    serialize_task_detail,
    serialize_task_view,
    serialize_today_view,
    serialize_week_agenda,
    task_view,
    task_asset_options,
    today_view,
    week_agenda,
)
from .services.content_briefs import (
    CANDIDATE_REVIEW_STATES,
    DESTINATION_OPTIONS,
    GOAL_OPTIONS,
    create_planned_content_item,
    create_task_from_planned_content,
    planned_content_items,
    produce_content_for_item,
    record_candidate_review,
    serialize_planned_content_item,
)
from .services.creative_generation import (
    creative_generation_jobs,
    import_manual_generated_output,
    review_creative_generation_job,
    serialize_creative_generation_job,
)
from .services.etsy_import import sync_etsy_read_only
from .services.local_assets import scan_asset_root
from .services.mattmademe_website_import import sync_mattmademe_website


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
    app.config["DB_PATH"] = Path(os.environ.get("MARKETING_OS_DB_PATH", db_path or DEFAULT_DB_PATH))
    app.config["ASSETS_ROOT"] = Path(os.environ.get("MARKETING_OS_ASSETS_ROOT", "assets/products"))
    app.config["ASSET_LIBRARY_ROOT"] = Path(os.environ.get("MARKETING_OS_ASSET_ROOT", "/Volumes/MarketingAssets"))
    app.config["EXPORT_DIR"] = Path(os.environ.get("MARKETING_OS_EXPORT_DIR", "data/exports"))

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

    @app.get("/api/today")
    def api_today():
        role = request.args.get("role", OPERATOR_DEFAULT_ROLE)
        with session_scope(factory) as session:
            return jsonify(serialize_today_view(today_view(session, role=role)))

    @app.get("/api/week")
    def api_week():
        role = request.args.get("role", OPERATOR_DEFAULT_ROLE)
        status = request.args.get("status", "open")
        platform = request.args.get("platform", "all")
        with session_scope(factory) as session:
            return jsonify({"agendas": serialize_week_agenda(week_agenda(session, role=role, status=status, platform=platform))})

    @app.get("/api/tasks/<int:task_id>")
    def api_task_detail(task_id: int):
        with session_scope(factory) as session:
            task = session.get(TaskRecord, task_id)
            if task is None:
                return jsonify({"error": "Task not found."}), 404
            show_metrics = task.status in {"posted", "metrics needed"} or bool(task.metric_due_date and task.metric_due_date <= date.today())
            return jsonify(
                serialize_task_detail(
                    task_view(task),
                    task_asset_options(session, task),
                    platform_metric_fields(task.platform),
                    show_metrics,
                    playbook_for(task.platform, task.content_type),
                )
            )

    @app.post("/api/tasks/<int:task_id>/finish")
    def api_task_finish(task_id: int):
        payload = request.get_json(silent=True) or {}
        with session_scope(factory) as session:
            try:
                task = complete_task_status(
                    session,
                    task_id,
                    str(payload.get("action") or "ready to post"),
                    notes=str(payload.get("notes") or ""),
                    post_url=str(payload.get("post_url") or ""),
                )
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 404
            return jsonify({"task": serialize_task_view(task_view(task))})

    @app.post("/api/tasks/<int:task_id>/metrics")
    def api_task_metrics(task_id: int):
        payload = request.get_json(silent=True) or {}
        with session_scope(factory) as session:
            try:
                metric = add_metric(
                    session,
                    task_id=task_id,
                    post_url=str(payload.get("post_url") or ""),
                    reach=_int_or_none(payload.get("reach")),
                    likes=_int_or_none(payload.get("likes")),
                    comments=_int_or_none(payload.get("comments")),
                    shares=_int_or_none(payload.get("shares")),
                    saves=_int_or_none(payload.get("saves")),
                    etsy_visits=_int_or_none(payload.get("etsy_visits")),
                    etsy_orders=_int_or_none(payload.get("etsy_orders")),
                    email_signups=_int_or_none(payload.get("email_signups")),
                    outcome_tags=_tag_values(payload.get("outcome_tags")),
                    notes=str(payload.get("notes") or ""),
                )
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 404
            task = session.get(TaskRecord, task_id)
            return jsonify(
                {
                    "task": serialize_task_view(task_view(task)),
                    "metric": {
                        "id": metric.id,
                        "task_id": metric.task_id,
                        "recorded_on": metric.recorded_on.isoformat(),
                        "post_url": metric.post_url,
                        "outcome_tags": outcome_tags(metric),
                    },
                }
            )

    @app.post("/api/tasks/<int:task_id>/generated-content")
    def api_task_generated_content(task_id: int):
        payload = request.get_json(silent=True) or {}
        candidate_id = _int_or_none(payload.get("candidate_id"))
        if candidate_id is None:
            return jsonify({"error": "Choose a generated content candidate."}), 400
        with session_scope(factory) as session:
            try:
                task = link_generated_content_to_task(session, task_id, candidate_id)
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 404
            return jsonify({"task": serialize_task_view(task_view(task))})

    @app.post("/api/tasks/<int:task_id>/asset")
    def api_task_asset(task_id: int):
        payload = request.get_json(silent=True) or {}
        asset_id = _int_or_none(payload.get("asset_id"))
        if asset_id is None:
            return jsonify({"error": "Choose an approved asset to assign."}), 400
        with session_scope(factory) as session:
            try:
                task = assign_asset_to_task(session, task_id, asset_id)
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            return jsonify({"task": serialize_task_view(task_view(task))})

    @app.get("/api/metrics-due")
    def api_metrics_due():
        with session_scope(factory) as session:
            return jsonify({"tasks": [serialize_task_view(task) for task in metrics_due_tasks(session)]})

    @app.get("/api/assets")
    def api_assets():
        with session_scope(factory) as session:
            return jsonify({"assets": [serialize_asset_view(model) for model in asset_inventory(session)]})

    @app.get("/api/data-health")
    def api_data_health():
        with session_scope(factory) as session:
            refresh_asset_file_state(session)
            return jsonify({"items": [serialize_data_health_item(item) for item in build_data_health(session, app.config["ASSET_LIBRARY_ROOT"])]})

    @app.get("/api/insights")
    def api_insights():
        with session_scope(factory) as session:
            return jsonify({"summary": serialize_learning_summary(build_learning_summary(session))})

    @app.post("/api/assets/library/scan")
    def api_scan_asset_library():
        with session_scope(factory) as session:
            summary = scan_asset_root(session, app.config["ASSET_LIBRARY_ROOT"])
            return jsonify(summary.__dict__), 200 if not summary.missing_root else 400

    @app.post("/api/integrations/etsy/sync")
    def api_sync_etsy():
        with session_scope(factory) as session:
            summary = sync_etsy_read_only(session)
            return jsonify(summary.__dict__), 200 if not summary.errors else 400

    @app.post("/api/integrations/website/sync")
    def api_sync_website():
        with session_scope(factory) as session:
            summary = sync_mattmademe_website(session)
            return jsonify(summary.__dict__), 200 if not summary.errors else 400

    @app.get("/api/creative-assets")
    def api_creative_assets():
        with session_scope(factory) as session:
            refresh_asset_file_state(session)
            return jsonify(
                {
                    "plans": [serialize_creative_asset_plan(plan) for plan in creative_asset_plans(session)],
                    "jobs": [serialize_creative_generation_job(job) for job in creative_generation_jobs(session)],
                }
            )

    @app.post("/api/creative-assets/manual-import")
    def api_creative_assets_manual_import():
        payload = request.get_json(silent=True) or {}
        try:
            source_asset_id = int(payload.get("source_asset_id"))
            with session_scope(factory) as session:
                result = import_manual_generated_output(
                    session=session,
                    source_asset_id=source_asset_id,
                    output_path=str(payload.get("output_path") or ""),
                    target_format=str(payload.get("target_format") or "Generated output"),
                    prompt=str(payload.get("prompt") or ""),
                    provider=str(payload.get("provider") or "magnific_manual"),
                    model_name=str(payload.get("model_name") or ""),
                    provider_job_id=str(payload.get("provider_job_id") or ""),
                    output_url=str(payload.get("output_url") or ""),
                    requested_dimensions=str(payload.get("requested_dimensions") or ""),
                    notes=str(payload.get("notes") or ""),
                )
                return jsonify({"job": serialize_creative_generation_job(result.job), "candidate_id": result.candidate.id}), 201
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/creative-assets/jobs/<int:job_id>/review")
    def api_creative_assets_job_review(job_id: int):
        payload = request.get_json(silent=True) or {}
        with session_scope(factory) as session:
            try:
                job = review_creative_generation_job(
                    session,
                    job_id,
                    review_state=str(payload.get("review_state") or "needs_review"),
                    review_notes=str(payload.get("review_notes") or ""),
                    reviewed_by=str(payload.get("reviewed_by") or ""),
                )
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            return jsonify({"job": serialize_creative_generation_job(job)})

    @app.get("/api/planned-content")
    def api_planned_content():
        with session_scope(factory) as session:
            return jsonify({"planned_items": [serialize_planned_content_item(session, item) for item in planned_content_items(session)]})

    @app.post("/api/planned-content")
    def api_create_planned_content():
        payload = request.get_json(silent=True) or {}
        try:
            calendar_date = date.fromisoformat(str(payload.get("calendar_date") or date.today().isoformat()))
            product_ids = [int(value) for value in payload.get("product_ids", [])]
        except (TypeError, ValueError):
            return jsonify({"error": "Use a valid date and product IDs."}), 400
        with session_scope(factory) as session:
            try:
                item = create_planned_content_item(
                    session,
                    calendar_date=calendar_date,
                    destinations=[str(value) for value in payload.get("destinations", [])],
                    goals=[str(value) for value in payload.get("goals", [])],
                    product_ids=product_ids,
                    audience=str(payload.get("audience") or ""),
                    occasion=str(payload.get("occasion") or ""),
                    promotion=str(payload.get("promotion") or ""),
                    notes=str(payload.get("notes") or ""),
                )
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            return jsonify({"planned_item": serialize_planned_content_item(session, item)}), 201

    @app.post("/api/planned-content/<int:item_id>/produce")
    def api_produce_planned_content(item_id: int):
        payload = request.get_json(silent=True) or {}
        with session_scope(factory) as session:
            item = session.get(PlannedContentRecord, item_id)
            if item is None:
                return jsonify({"error": "Planned content item not found."}), 404
            result = produce_content_for_item(session, item, business_dir=business_dir, force=bool(payload.get("force")))
            return jsonify(
                {
                    "planned_item": serialize_planned_content_item(session, item),
                    "created": result.created,
                    "skipped": result.skipped,
                }
            )

    @app.post("/api/planned-content/<int:item_id>/task")
    def api_create_task_from_planned_content(item_id: int):
        payload = request.get_json(silent=True) or {}
        candidate_id = _int_or_none(payload.get("candidate_id"))
        with session_scope(factory) as session:
            try:
                result = create_task_from_planned_content(
                    session,
                    item_id,
                    destination=str(payload.get("destination") or "") or None,
                    candidate_id=candidate_id,
                )
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            return jsonify({"task": serialize_task_view(task_view(result.task)), "candidate_id": result.candidate.id if result.candidate else None}), 201

    @app.post("/api/generated-content/<int:candidate_id>/review")
    def api_review_generated_content(candidate_id: int):
        payload = request.get_json(silent=True) or {}
        with session_scope(factory) as session:
            try:
                candidate = record_candidate_review(
                    session,
                    candidate_id,
                    str(payload.get("review_state") or "needs_review"),
                    revision_notes=str(payload.get("revision_notes") or ""),
                    reviewed_by=str(payload.get("reviewed_by") or ""),
                )
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            return jsonify(
                {
                    "candidate": {
                        "id": candidate.id,
                        "review_state": candidate.review_state,
                        "revision_notes": candidate.revision_notes,
                        "reviewed_by": candidate.reviewed_by,
                        "reviewed_at": candidate.reviewed_at.isoformat() if candidate.reviewed_at else None,
                    }
                }
            )

    @app.get("/")
    def dashboard() -> str:
        role = request.args.get("role", OPERATOR_DEFAULT_ROLE)
        with session_scope(factory) as session:
            plan = session.scalars(select(PlanRecord).order_by(PlanRecord.generated_at.desc())).first()
            plan_tasks = list(session.scalars(select(TaskRecord).where(TaskRecord.plan_id == plan.id).order_by(TaskRecord.due_date))) if plan else []
            return render_template(
                "dashboard.html",
                active="today",
                plan=plan,
                today_model=today_view(session, role=role),
                status_counts=status_counts(plan_tasks),
                selected_role=role,
            )

    @app.get("/week")
    def week() -> str:
        role = request.args.get("role", OPERATOR_DEFAULT_ROLE)
        status = request.args.get("status", "open")
        platform = request.args.get("platform", "all")
        with session_scope(factory) as session:
            agendas = week_agenda(session, role=role, status=status, platform=platform)
            platforms = sorted({task.platform for task in session.scalars(select(TaskRecord)).all() if task.platform})
            return render_template(
                "week.html",
                active="week",
                agendas=agendas,
                selected_role=role,
                selected_status=status,
                selected_platform=platform,
                platforms=platforms,
            )

    @app.get("/completed")
    def completed() -> str:
        role = request.args.get("role", OPERATOR_DEFAULT_ROLE)
        with session_scope(factory) as session:
            tasks = completed_tasks(session, role=role)
            return render_template("completed.html", active="completed", tasks=tasks, selected_role=role)

    @app.get("/guides")
    def guides() -> str:
        with session_scope(factory) as session:
            guides_model = posting_guides(session)
            return render_template("guides.html", active="guides", guides=guides_model)

    @app.get("/creative-assets")
    def creative_assets() -> str:
        with session_scope(factory) as session:
            refresh_asset_file_state(session)
            plans = creative_asset_plans(session)
            source_assets = [plan.source_asset for plan in plans if plan.source_ready]
            jobs = creative_generation_jobs(session)
            return render_template("creative_assets.html", active="creative_assets", plans=plans, source_assets=source_assets, jobs=jobs)

    @app.get("/planning")
    def planning() -> str:
        with session_scope(factory) as session:
            products = list(session.scalars(select(ProductRecord).order_by(ProductRecord.name)))
            tasks = list(session.scalars(select(TaskRecord).order_by(TaskRecord.due_date, TaskRecord.id)))
            items = planned_content_items(session)
            return render_template(
                "plan_intent.html",
                active="planning",
                products=products,
                tasks=tasks,
                planned_items=[serialize_planned_content_item(session, item) for item in items],
                destinations=DESTINATION_OPTIONS,
                goals=GOAL_OPTIONS,
                candidate_review_states=CANDIDATE_REVIEW_STATES,
            )

    @app.post("/planning")
    def create_planning_item() -> str:
        try:
            calendar_date = date.fromisoformat(request.form.get("calendar_date", date.today().isoformat()))
            product_ids = [int(value) for value in request.form.getlist("product_ids")]
            with session_scope(factory) as session:
                create_planned_content_item(
                    session,
                    calendar_date=calendar_date,
                    destinations=request.form.getlist("destinations"),
                    goals=request.form.getlist("goals"),
                    product_ids=product_ids,
                    audience=request.form.get("audience", ""),
                    occasion=request.form.get("occasion", ""),
                    promotion=request.form.get("promotion", ""),
                    notes=request.form.get("notes", ""),
                )
                flash("Planned marketing item saved.")
        except ValueError as exc:
            flash(str(exc))
        return redirect(url_for("planning"))

    @app.post("/planning/<int:item_id>/produce")
    def produce_planning_item(item_id: int) -> str:
        with session_scope(factory) as session:
            item = session.get(PlannedContentRecord, item_id)
            if item is None:
                flash("Planned content item not found.")
                return redirect(url_for("planning"))
            result = produce_content_for_item(session, item, business_dir=business_dir, force=request.form.get("force") == "1")
            flash(f"Prepared {len(result.candidates)} candidate(s): {result.created} new, {result.skipped} already present.")
        return redirect(url_for("planning"))

    @app.post("/planning/<int:item_id>/create-task")
    def create_task_from_planning_item(item_id: int) -> str:
        candidate_id = _int_or_none(request.form.get("candidate_id"))
        with session_scope(factory) as session:
            try:
                result = create_task_from_planned_content(
                    session,
                    item_id,
                    destination=request.form.get("destination", ""),
                    candidate_id=candidate_id,
                )
                flash(f"Created posting task: {result.task.title}.")
                return redirect(url_for("task_detail", task_id=result.task.id))
            except ValueError as exc:
                flash(str(exc))
        return redirect(url_for("planning"))

    @app.post("/planning/candidates/<int:candidate_id>/review")
    def review_planning_candidate(candidate_id: int) -> str:
        with session_scope(factory) as session:
            try:
                record_candidate_review(
                    session,
                    candidate_id,
                    request.form.get("review_state", "needs_review"),
                    revision_notes=request.form.get("revision_notes", ""),
                    reviewed_by=request.form.get("reviewed_by", ""),
                )
                flash("Candidate review saved.")
            except ValueError as exc:
                flash(str(exc))
        return redirect(url_for("planning"))

    @app.post("/planning/candidates/<int:candidate_id>/link-task")
    def link_planning_candidate_to_task(candidate_id: int) -> str:
        task_id = _int_or_none(request.form.get("task_id"))
        if task_id is None:
            flash("Choose a task to receive this candidate.")
            return redirect(url_for("planning"))
        with session_scope(factory) as session:
            try:
                task = link_generated_content_to_task(session, task_id, candidate_id)
                flash(f"Candidate attached to task: {task.title}.")
            except ValueError as exc:
                flash(str(exc))
        return redirect(url_for("task_detail", task_id=task_id))

    @app.post("/creative-assets/register")
    def creative_assets_register() -> str:
        source_asset_id = int(request.form.get("source_asset_id", "0"))
        selected_templates = request.form.getlist("template_name")
        with session_scope(factory) as session:
            try:
                run = prepare_creative_generation_run(session, source_asset_id, selected_templates)
                flash(
                    f"Prepared {len(run.candidates)} generated output candidate(s). "
                    f"Generation manifest: {run.manifest_path}."
                )
            except ValueError as exc:
                flash(str(exc))
        return redirect(url_for("creative_assets"))

    @app.post("/creative-assets/manual-import")
    def creative_assets_manual_import() -> str:
        try:
            source_asset_id = int(request.form.get("source_asset_id", "0"))
            with session_scope(factory) as session:
                result = import_manual_generated_output(
                    session,
                    source_asset_id=source_asset_id,
                    output_path=request.form.get("output_path", "").strip(),
                    target_format=request.form.get("target_format", "Generated output").strip(),
                    prompt=request.form.get("prompt", "").strip(),
                    provider=request.form.get("provider", "magnific_manual").strip(),
                    model_name=request.form.get("model_name", "").strip(),
                    provider_job_id=request.form.get("provider_job_id", "").strip(),
                    output_url=request.form.get("output_url", "").strip(),
                    requested_dimensions=request.form.get("requested_dimensions", "").strip(),
                    notes=request.form.get("notes", "").strip(),
                )
                flash(f"Imported generated candidate #{result.candidate.id}. Review it in Assets before use.")
        except ValueError as exc:
            flash(str(exc))
        return redirect(url_for("creative_assets"))

    @app.post("/creative-assets/jobs/<int:job_id>/review")
    def creative_assets_job_review(job_id: int) -> str:
        with session_scope(factory) as session:
            try:
                review_creative_generation_job(
                    session,
                    job_id,
                    review_state=request.form.get("review_state", "needs_review"),
                    review_notes=request.form.get("review_notes", ""),
                    reviewed_by=request.form.get("reviewed_by", ""),
                )
                flash("Creative review saved.")
            except ValueError as exc:
                flash(str(exc))
        return redirect(url_for("creative_assets"))

    @app.get("/calendar")
    def calendar() -> str:
        with session_scope(factory) as session:
            plan = session.scalars(select(PlanRecord).order_by(PlanRecord.generated_at.desc())).first()
            tasks = list(session.scalars(select(TaskRecord).where(TaskRecord.plan_id == plan.id).order_by(TaskRecord.due_date))) if plan else []
            planned_items = [serialize_planned_content_item(session, item) for item in planned_content_items(session)]
            return render_template("calendar.html", active="calendar", plan=plan, tasks=[task_view(task) for task in tasks], planned_items=planned_items)

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
            metric_fields = platform_metric_fields(task.platform)
            show_metrics = task.status in {"posted", "metrics needed"} or bool(task.metric_due_date and task.metric_due_date <= date.today())
            return render_template(
                "task_detail.html",
                active="today",
                task=task,
                task_model=task_view(task),
                asset_options=task_asset_options(session, task),
                playbook=playbook,
                metrics=metrics,
                metric_fields=metric_fields,
                show_metrics=show_metrics,
                outcome_tags=outcome_tags,
            )

    @app.post("/tasks/<int:task_id>/status")
    def task_status(task_id: int) -> str:
        status = request.form.get("status", "ready to post")
        notes = request.form.get("notes", "")
        with session_scope(factory) as session:
            update_task_status(session, task_id, status, notes)
            flash("Task status saved.")
        return redirect(url_for("task_detail", task_id=task_id))

    @app.post("/tasks/<int:task_id>/finish")
    def task_finish(task_id: int) -> str:
        action = request.form.get("action", "ready to post")
        notes = request.form.get("notes", "")
        post_url = request.form.get("post_url", "")
        with session_scope(factory) as session:
            complete_task_status(session, task_id, action, notes=notes, post_url=post_url)
            flash("Task updated.")
        return redirect(url_for("task_detail", task_id=task_id))

    @app.post("/tasks/<int:task_id>/asset")
    def task_asset(task_id: int) -> str:
        asset_id_text = request.form.get("asset_id", "").strip()
        if not asset_id_text:
            flash("Choose an approved asset to assign.")
            return redirect(url_for("task_detail", task_id=task_id))
        with session_scope(factory) as session:
            try:
                assign_asset_to_task(session, task_id, int(asset_id_text))
                flash("Task asset updated.")
            except ValueError as exc:
                flash(str(exc))
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
                outcome_tags=_tag_values(request.form.get("outcome_tags", "")),
                notes=request.form.get("notes", ""),
            )
            flash("Metrics saved.")
        return redirect(url_for("task_detail", task_id=task_id))

    @app.get("/metrics-due")
    def metrics_due() -> str:
        with session_scope(factory) as session:
            tasks = metrics_due_tasks(session)
            return render_template("metrics_due.html", active="metrics_due", tasks=tasks)

    @app.get("/assets")
    def assets() -> str:
        with session_scope(factory) as session:
            records = asset_inventory(session)
            products = list(session.scalars(select(ProductRecord).order_by(ProductRecord.name)))
            return render_template("assets.html", active="assets", assets=records, products=products)

    @app.post("/assets/scan")
    def scan_assets() -> str:
        with session_scope(factory) as session:
            imported = scan_local_asset_folder(session, app.config["ASSETS_ROOT"])
            flash(f"Scanned local assets. Found {len(imported)} image file(s).")
        return redirect(url_for("assets"))

    @app.post("/assets/register-source")
    def register_source_asset() -> str:
        file_path = request.form.get("file_path", "").strip()
        product_id_text = request.form.get("product_id", "").strip()
        product_id = int(product_id_text) if product_id_text else None
        name = request.form.get("name", "").strip()
        notes = request.form.get("notes", "").strip()
        if not file_path:
            flash("Enter a local source photo path.")
            return redirect(url_for("assets"))
        with session_scope(factory) as session:
            try:
                asset = register_local_source_photo(session, file_path, product_id=product_id, name=name, notes=notes)
                flash(f"Registered source photo: {asset.name}.")
            except (FileNotFoundError, ValueError) as exc:
                flash(str(exc))
        return redirect(url_for("assets"))

    @app.post("/assets/upload-source")
    def upload_source_asset() -> str:
        upload = request.files.get("photo")
        product_id_text = request.form.get("product_id", "").strip()
        product_id = int(product_id_text) if product_id_text else None
        name = request.form.get("name", "").strip()
        notes = request.form.get("notes", "").strip()
        if upload is None or not upload.filename:
            flash("Choose a product photo to upload.")
            return redirect(url_for("assets"))
        filename = secure_filename(upload.filename)
        if not filename:
            flash("Choose a product photo with a valid filename.")
            return redirect(url_for("assets"))
        with tempfile.TemporaryDirectory() as tmp:
            temp_path = Path(tmp) / filename
            upload.save(temp_path)
            with session_scope(factory) as session:
                try:
                    asset = import_source_photo_to_inventory(
                        session,
                        temp_path,
                        product_id=product_id,
                        name=name,
                        notes=notes,
                        assets_root=app.config["ASSETS_ROOT"],
                    )
                    flash(f"Uploaded source photo: {asset.name}.")
                except (FileNotFoundError, ValueError) as exc:
                    flash(str(exc))
        return redirect(url_for("assets"))

    @app.post("/assets/<int:asset_id>/review")
    def asset_review(asset_id: int) -> str:
        review_state = request.form.get("review_state", "needs review")
        notes = request.form.get("approval_notes", "")
        with session_scope(factory) as session:
            try:
                review_asset(session, asset_id, review_state, notes)
                flash("Asset review saved.")
            except ValueError as exc:
                flash(str(exc))
        return redirect(url_for("assets"))

    @app.get("/assets/<int:asset_id>/preview")
    def asset_preview(asset_id: int):
        with session_scope(factory) as session:
            asset = session.get(AssetRecord, asset_id)
            if asset is None:
                abort(404)
            path = asset_path(asset).resolve()
            if not path.is_file():
                abort(404)
            return send_file(path)

    @app.get("/templates")
    def templates() -> str:
        with session_scope(factory) as session:
            records = list(session.scalars(select(TemplateRecord).order_by(TemplateRecord.template_type, TemplateRecord.name)))
            return render_template("templates.html", active="templates", templates=records, template_body=template_body)

    @app.get("/metrics")
    def metrics() -> str:
        with session_scope(factory) as session:
            records = list(session.scalars(select(MetricRecord).order_by(MetricRecord.recorded_on.desc(), MetricRecord.id.desc())))
            return render_template("metrics.html", active="metrics", metrics=records, outcome_tags=outcome_tags)

    @app.get("/insights")
    def insights() -> str:
        with session_scope(factory) as session:
            summary = build_learning_summary(session)
            return render_template("insights.html", active="insights", summary=summary)

    @app.get("/data-health")
    def data_health() -> str:
        with session_scope(factory) as session:
            refresh_asset_file_state(session)
            items = build_data_health(session, app.config["ASSET_LIBRARY_ROOT"])
            return render_template("data_health.html", active="data_health", items=items)

    @app.post("/imports/etsy-csv")
    def import_etsy_csv() -> str:
        csv_path = request.form.get("csv_path", "").strip()
        if not csv_path:
            flash("Enter a local Etsy CSV path to import.")
            return redirect(url_for("settings"))
        with session_scope(factory) as session:
            try:
                imported = import_etsy_listing_csv(session, csv_path)
                flash(f"Imported {len(imported)} Etsy listing record(s).")
            except FileNotFoundError as exc:
                flash(str(exc))
        return redirect(url_for("data_health"))

    @app.post("/integrations/etsy/sync")
    def sync_etsy() -> str:
        with session_scope(factory) as session:
            summary = sync_etsy_read_only(session)
            if summary.errors:
                flash(summary.errors[0])
            else:
                flash(f"Synced Etsy: {summary.products_imported} listing(s), {summary.assets_imported} image(s).")
        return redirect(url_for("data_health"))

    @app.post("/integrations/website/sync")
    def sync_website() -> str:
        with session_scope(factory) as session:
            summary = sync_mattmademe_website(session)
            if summary.errors:
                flash(summary.errors[0])
            else:
                flash(
                    f"Synced website: {summary.products_imported} product(s), "
                    f"{summary.assets_imported} image(s), {summary.blog_posts_imported} blog post(s)."
                )
        return redirect(url_for("data_health"))

    @app.post("/assets/library/scan")
    def scan_asset_library() -> str:
        with session_scope(factory) as session:
            summary = scan_asset_root(session, app.config["ASSET_LIBRARY_ROOT"])
            if summary.missing_root:
                flash(f"Asset library root not found: {summary.root_path}.")
            else:
                flash(f"Indexed {summary.indexed} asset library file(s). Manifest: {summary.manifest_path}.")
        return redirect(url_for("assets"))

    @app.get("/settings")
    def settings() -> str:
        return render_template(
            "settings.html",
            active="settings",
            business_dir=business_dir,
            db_path=app.config["DB_PATH"],
            assets_root=app.config["ASSETS_ROOT"],
            asset_library_root=app.config["ASSET_LIBRARY_ROOT"],
            export_dir=app.config["EXPORT_DIR"],
        )

    @app.post("/settings/backup")
    def backup_database() -> str:
        try:
            path = backup_sqlite_database(app.config["DB_PATH"])
            flash(f"Database backup created at {path}.")
        except FileNotFoundError as exc:
            flash(str(exc))
        return redirect(url_for("settings"))

    @app.post("/settings/export")
    def export_data():
        with session_scope(factory) as session:
            path = export_operating_data(session, app.config["EXPORT_DIR"])
        return send_file(path.resolve(), as_attachment=True, download_name=path.name)

    return app


def _int_or_none(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _tag_values(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw_values = value
    else:
        raw_values = str(value).replace("\n", ",").split(",")
    tags: list[str] = []
    for raw in raw_values:
        tag = str(raw).strip().lower()
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the MattMadeMe Marketing OS local web console")
    parser.add_argument("--host", default=os.environ.get("MARKETING_OS_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MARKETING_OS_PORT", "8000")))
    parser.add_argument("--db-path", default=os.environ.get("MARKETING_OS_DB_PATH", "data/marketing_os.sqlite"))
    parser.add_argument("--business-dir", default=os.environ.get("MARKETING_OS_BUSINESS_DIR", "docs/business"))
    args = parser.parse_args(argv)

    app = create_app(args.db_path, args.business_dir)
    app.run(host=args.host, port=args.port, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
