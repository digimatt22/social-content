from __future__ import annotations

import argparse
import json
import logging
import os
import tempfile
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from shutil import copyfileobj

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_file, url_for
from sqlalchemy import func, select
from werkzeug.utils import secure_filename

from .config import load_local_env
from .db import DEFAULT_DB_PATH, create_db_engine, init_db, session_factory, session_scope
from .db_models import (
    AssetRecord,
    EtsyReviewRecord,
    GeneratedContentCandidateRecord,
    MetricRecord,
    PlanRecord,
    PlannedContentRecord,
    ProductExternalReference,
    ProductRecord,
    TaskRecord,
    TemplateRecord,
)
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
from .services.phase5_readiness import (
    build_phase5_approval_packet,
    build_phase5_readiness,
    serialize_phase5_approval_packet,
    serialize_phase5_readiness,
    write_phase5_approval_packet,
    write_phase5_creative_handoff,
)
from .phase4 import (
    OPERATOR_DEFAULT_ROLE,
    assign_asset_to_task,
    asset_inventory,
    asset_inventory_count,
    asset_path,
    asset_tag_label,
    asset_tag_options,
    complete_task_status,
    completed_tasks,
    data_health as build_data_health,
    delete_local_asset_file,
    export_operating_data,
    import_etsy_listing_csv,
    import_source_photo_to_inventory,
    metrics_due_tasks,
    platform_metric_fields,
    posting_guides,
    refresh_asset_file_state,
    review_asset,
    scan_local_asset_folder,
    serialize_asset_view,
    serialize_data_health_item,
    serialize_task_detail,
    serialize_task_view,
    serialize_today_view,
    serialize_week_agenda,
    hidden_asset_group_count,
    task_view,
    task_asset_options,
    today_view,
    week_agenda,
    set_asset_generation_visibility,
)
from .services.content_briefs import (
    AUDIENCE_OPTIONS,
    CANDIDATE_REVIEW_STATES,
    DESTINATION_OPTIONS,
    GOAL_OPTIONS,
    OCCASION_OPTIONS,
    PLANNER_GOAL_OPTIONS,
    PLATFORM_DEFAULT_SCHEDULED_TIMES,
    PROMOTION_OPTIONS,
    create_planned_content_item,
    create_task_from_planned_content,
    default_scheduled_time_for_destination,
    delete_planned_content_item,
    localize_planned_content_reference_assets,
    normalize_scheduled_time,
    planned_content_items,
    produce_content_for_item,
    record_candidate_review,
    register_uploaded_image_option,
    request_content_regeneration,
    serialize_candidate,
    serialize_planned_content_item,
    update_product_default_reference_assets,
    update_planned_content_details,
    update_planned_content_schedule,
    update_planned_copy_candidate,
)
from .services.creative_generation import review_creative_generation_job
from .services.etsy_import import sync_etsy_read_only
from .services.etsy_sales_csv import import_etsy_sales_csv
from .services.local_assets import scan_asset_root


LOCAL_ASSET_LIBRARY_ROOT = Path("assets")
LOCAL_GENERATED_OUTPUT_ROOT = Path("outputs/generated")
LOCAL_PLANNING_UPLOAD_ROOT = Path("outputs/graphics/planning/uploads")
ASSETS_PAGE_SIZE = 36
PRODUCTS_PAGE_SIZE = 20


def create_app(db_path: str | Path | None = None, business_dir: str = "docs/business", bootstrap_data: bool | None = None) -> Flask:
    load_local_env()
    app = Flask(__name__)
    app.secret_key = os.environ.get("MARKETING_OS_SECRET", "local-dev-only")
    engine = create_db_engine(db_path)
    init_db(engine)
    factory = session_factory(engine)

    should_bootstrap = (
        os.environ.get("MARKETING_OS_BOOTSTRAP_DATA", "0").lower() in {"1", "true", "yes"}
        if bootstrap_data is None
        else bootstrap_data
    )
    if should_bootstrap:
        with session_scope(factory) as session:
            seed_database(session, business_dir)
            ensure_default_plan(session, business_dir)

    app.config["SESSION_FACTORY"] = factory
    app.config["BUSINESS_DIR"] = business_dir
    app.config["DB_PATH"] = Path(os.environ.get("MARKETING_OS_DB_PATH", db_path or DEFAULT_DB_PATH))
    app.config["ASSETS_ROOT"] = Path(os.environ.get("MARKETING_OS_ASSETS_ROOT", "assets/products"))
    app.config["ASSET_LIBRARY_ROOT"] = Path(os.environ.get("MARKETING_OS_ASSET_ROOT", LOCAL_ASSET_LIBRARY_ROOT))
    app.config["EXPORT_DIR"] = Path(os.environ.get("MARKETING_OS_EXPORT_DIR", "data/exports"))
    app.config["GENERATED_OUTPUT_ROOT"] = Path(os.environ.get("MARKETING_OS_GENERATED_OUTPUT_ROOT", LOCAL_GENERATED_OUTPUT_ROOT))
    app.config["PLANNING_UPLOAD_ROOT"] = Path(os.environ.get("MARKETING_OS_PLANNING_UPLOAD_ROOT", LOCAL_PLANNING_UPLOAD_ROOT))

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
                task = assign_asset_to_task(session, task_id, asset_id, app.config["ASSETS_ROOT"])
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

    @app.get("/api/phase5-readiness")
    def api_phase5_readiness():
        with session_scope(factory) as session:
            return jsonify({"readiness": serialize_phase5_readiness(build_phase5_readiness(session))})

    @app.get("/api/phase5-approval-packet")
    def api_phase5_approval_packet():
        with session_scope(factory) as session:
            return jsonify({"packet": serialize_phase5_approval_packet(build_phase5_approval_packet(session))})

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

    @app.get("/api/product-tags")
    def api_product_tags():
        query = request.args.get("q", "").strip().lower()
        with session_scope(factory) as session:
            tags = _all_product_tags(session)
            if query:
                tags = [tag for tag in tags if query in tag.lower()]
            return jsonify({"tags": tags[:20]})

    @app.post("/api/products/<int:product_id>/tags")
    def api_add_product_tag(product_id: int):
        payload = request.get_json(silent=True) or {}
        tag = str(payload.get("tag") or "").strip()
        with session_scope(factory) as session:
            product = session.get(ProductRecord, product_id)
            if product is None:
                return jsonify({"error": "Product not found."}), 404
            if not tag:
                return jsonify({"error": "Enter a product tag to add."}), 400
            saved_tag, tags, created = _add_product_tag(product, tag)
            return jsonify({"tag": saved_tag, "tags": tags, "created": created})

    @app.post("/api/products/<int:product_id>/default-reference-assets")
    def api_product_default_reference_assets(product_id: int):
        payload = request.get_json(silent=True) or {}
        try:
            asset_ids = [int(value) for value in payload.get("asset_ids", [])]
        except (TypeError, ValueError):
            return jsonify({"error": "Use valid asset IDs."}), 400
        with session_scope(factory) as session:
            try:
                selected_ids = update_product_default_reference_assets(session, product_id, asset_ids)
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 404
            return jsonify({"product_id": product_id, "asset_ids": selected_ids})

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
            selected_source_asset_ids = [int(value) for value in payload.get("selected_source_asset_ids", [])]
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
                    scheduled_time=str(payload.get("scheduled_time") or "09:00"),
                    selected_source_asset_ids=selected_source_asset_ids,
                    assets_root=app.config["ASSETS_ROOT"],
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
                    edited_copy_text=str(payload.get("copy_text") or ""),
                )
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            return jsonify(
                {
                    "candidate": {
                        "id": candidate.id,
                        "review_state": candidate.review_state,
                        "revision_notes": candidate.revision_notes,
                        "copy_text": serialize_candidate(candidate)["copy_text"],
                        "reviewed_by": candidate.reviewed_by,
                        "reviewed_at": candidate.reviewed_at.isoformat() if candidate.reviewed_at else None,
                    }
                }
            )

    @app.get("/")
    def dashboard() -> str:
        role = request.args.get("role", "all")
        with session_scope(factory) as session:
            plan = session.scalars(select(PlanRecord).order_by(PlanRecord.generated_at.desc())).first()
            plan_tasks = list(session.scalars(select(TaskRecord).where(TaskRecord.plan_id == plan.id).order_by(TaskRecord.due_date))) if plan else []
            review_queue = _dashboard_review_queue(session)
            return render_template(
                "dashboard.html",
                active="today",
                plan=plan,
                today_model=today_view(session, role=role),
                review_queue=review_queue,
                status_counts=status_counts(plan_tasks),
                selected_role=role,
            )

    @app.get("/week")
    def week() -> str:
        role = request.args.get("role", "all")
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
        role = request.args.get("role", "all")
        with session_scope(factory) as session:
            tasks = completed_tasks(session, role=role)
            return render_template("completed.html", active="completed", tasks=tasks, selected_role=role)

    @app.get("/guides")
    def guides() -> str:
        with session_scope(factory) as session:
            guides_model = posting_guides(session)
            return render_template("guides.html", active="guides", guides=guides_model)

    def _asset_management_context(session, include_hidden: bool = False, page: int = 1, selected_tag: str = "") -> dict[str, object]:
        page = max(page, 1)
        tag_options = asset_tag_options(session, include_hidden=include_hidden)
        selected_tag = selected_tag.strip()
        if selected_tag and selected_tag.lower() not in {tag.lower() for tag in tag_options}:
            selected_tag = ""
        total_assets = asset_inventory_count(session, include_hidden=include_hidden, tag=selected_tag)
        pagination = _pagination(page, total_assets, ASSETS_PAGE_SIZE)
        return {
            "active": "assets",
            "assets": asset_inventory(
                session,
                include_hidden=include_hidden,
                limit=ASSETS_PAGE_SIZE,
                offset=pagination["offset"],
                tag=selected_tag,
            ),
            "show_hidden": include_hidden,
            "selected_tag": selected_tag,
            "tag_options": tag_options,
            "asset_tag_label": asset_tag_label,
            "pagination": pagination,
            "total_asset_count": total_assets,
            "hidden_asset_count": hidden_asset_group_count(session),
            "products": list(session.scalars(select(ProductRecord).order_by(ProductRecord.name))),
        }

    @app.get("/creative-assets")
    def creative_assets() -> str:
        show_hidden = request.args.get("show_hidden") == "1"
        page = _page_arg(request.args.get("page"))
        selected_tag = request.args.get("tag", "")
        with session_scope(factory) as session:
            return render_template("assets.html", **_asset_management_context(session, include_hidden=show_hidden, page=page, selected_tag=selected_tag))

    @app.get("/planning")
    def planning() -> str:
        active_planning_step = request.args.get("step", "1")
        if active_planning_step not in {"1", "2", "3"}:
            active_planning_step = "1"
        with session_scope(factory) as session:
            products = list(session.scalars(select(ProductRecord).order_by(ProductRecord.name)))
            tasks = list(session.scalars(select(TaskRecord).order_by(TaskRecord.due_date, TaskRecord.id)))
            items = planned_content_items(session)
            return render_template(
                "plan_intent.html",
                active="planning",
                products=products,
                product_reference_assets=_planner_reference_assets(session, products),
                tasks=tasks,
                planned_items=[serialize_planned_content_item(session, item) for item in items],
                destinations=DESTINATION_OPTIONS,
                goals=PLANNER_GOAL_OPTIONS,
                audiences=AUDIENCE_OPTIONS,
                occasions=OCCASION_OPTIONS,
                promotions=PROMOTION_OPTIONS,
                candidate_review_states=CANDIDATE_REVIEW_STATES,
                active_planning_step=active_planning_step,
                default_scheduled_time=default_scheduled_time_for_destination(DESTINATION_OPTIONS[0]),
                destination_default_times=PLATFORM_DEFAULT_SCHEDULED_TIMES,
            )

    @app.post("/planning")
    def create_planning_item() -> str:
        try:
            calendar_date = date.fromisoformat(request.form.get("calendar_date", date.today().isoformat()))
            product_ids = [int(value) for value in request.form.getlist("product_ids")]
            selected_source_asset_ids = [int(value) for value in request.form.getlist("selected_source_asset_ids")]
            item_id: int | None = None
            needs_asset_download = False
            with session_scope(factory) as session:
                item = create_planned_content_item(
                    session,
                    calendar_date=calendar_date,
                    destinations=request.form.getlist("destinations"),
                    goals=[_form_other_value(request.form.get("goals", ""), request.form.get("goals_other", ""))],
                    product_ids=product_ids,
                    scheduled_time=request.form.get("scheduled_time"),
                    selected_source_asset_ids=selected_source_asset_ids,
                    assets_root=app.config["ASSETS_ROOT"],
                    defer_remote_assets=True,
                    audience=_form_other_value(request.form.get("audience", ""), request.form.get("audience_other", "")),
                    occasion=_form_other_value(request.form.get("occasion", ""), request.form.get("occasion_other", "")),
                    promotion=_form_other_value(request.form.get("promotion", ""), request.form.get("promotion_other", "")),
                    notes=request.form.get("notes", ""),
                )
                item_id = item.id
                needs_asset_download = item.status == "waiting_asset_download"
                flash(
                    "Post queued. Preparing selected remote image references in the background."
                    if needs_asset_download
                    else "Post queued for content generation."
                )
            if item_id is not None and needs_asset_download:
                _start_reference_asset_download(factory, item_id, app.config["ASSETS_ROOT"])
        except ValueError as exc:
            flash(str(exc))
            if "reference image" in str(exc):
                return redirect(url_for("planning", step=2))
        return redirect(url_for("planning"))

    @app.post("/planning/<int:item_id>/produce")
    def produce_planning_item(item_id: int) -> str:
        with session_scope(factory) as session:
            item = session.get(PlannedContentRecord, item_id)
            if item is None:
                flash("Planned content item not found.")
                return redirect(url_for("planning"))
            result = produce_content_for_item(session, item, business_dir=business_dir, force=request.form.get("force") == "1")
            flash(f"Ran queued content generation: {result.created} copy candidate(s) created, {result.skipped} skipped.")
        return redirect(url_for("planning"))

    @app.post("/planning/<int:item_id>/regenerate")
    def regenerate_planning_item(item_id: int) -> str:
        target = request.form.get("target", "")
        feedback = request.form.get("feedback", "").strip()
        with session_scope(factory) as session:
            try:
                request_content_regeneration(session, item_id, target, feedback=feedback)
                flash("Regeneration queued.")
            except ValueError as exc:
                flash(str(exc))
        return redirect(url_for("planning", _anchor=f"planned-item-{item_id}"))

    @app.post("/planning/<int:item_id>/delete")
    def delete_planning_item(item_id: int) -> str:
        with session_scope(factory) as session:
            try:
                delete_planned_content_item(session, item_id)
                flash("Queued post deleted.")
            except ValueError as exc:
                flash(str(exc))
        return redirect(url_for("planning"))

    @app.post("/planning/candidates/<int:candidate_id>/copy")
    def update_planning_copy(candidate_id: int) -> str:
        with session_scope(factory) as session:
            try:
                candidate = update_planned_copy_candidate(session, candidate_id, request.form.get("copy_text", ""))
                flash("Copy updated.")
                return redirect(url_for("planning", _anchor=f"candidate-{candidate.id}"))
            except ValueError as exc:
                flash(str(exc))
        return redirect(url_for("planning"))

    @app.post("/planning/<int:item_id>/upload-image")
    def upload_planning_image(item_id: int) -> str:
        upload = request.files.get("image_file")
        if upload is None or not upload.filename:
            flash("Choose an image to upload.")
            return redirect(url_for("planning", _anchor=f"planned-item-{item_id}"))
        try:
            output_path = _save_image_upload(upload, app.config["PLANNING_UPLOAD_ROOT"], label="planning image option")
            with session_scope(factory) as session:
                register_uploaded_image_option(
                    session,
                    item_id,
                    output_path,
                    name=request.form.get("name", ""),
                    notes=request.form.get("notes", ""),
                )
                flash("Uploaded image option added for review.")
        except ValueError as exc:
            flash(str(exc))
        return redirect(url_for("planning", _anchor=f"planned-item-{item_id}"))

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
                    edited_copy_text=request.form.get("copy_text", ""),
                )
                flash("Candidate review saved.")
            except ValueError as exc:
                flash(str(exc))
        return redirect(url_for("planning", _anchor=f"candidate-{candidate_id}"))

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

    @app.get("/calendar")
    def calendar() -> str:
        with session_scope(factory) as session:
            plan = session.scalars(select(PlanRecord).order_by(PlanRecord.generated_at.desc())).first()
            tasks = list(session.scalars(select(TaskRecord).where(TaskRecord.plan_id == plan.id).order_by(TaskRecord.due_date))) if plan else []
            planned_items = [serialize_planned_content_item(session, item) for item in planned_content_items(session)]
            task_models = [task_view(task) for task in tasks]
            return render_template(
                "calendar.html",
                active="calendar",
                plan=plan,
                tasks=task_models,
                planned_items=planned_items,
                calendar_days=_calendar_days(task_models, planned_items),
                destinations=DESTINATION_OPTIONS,
                goals=GOAL_OPTIONS,
                audiences=AUDIENCE_OPTIONS,
                occasions=OCCASION_OPTIONS,
                promotions=PROMOTION_OPTIONS,
            )

    @app.post("/calendar/planned/<int:item_id>/update")
    def calendar_update_planned_item(item_id: int) -> str:
        try:
            calendar_date = date.fromisoformat(request.form.get("calendar_date", date.today().isoformat()))
            with session_scope(factory) as session:
                update_planned_content_details(
                    session,
                    item_id,
                    calendar_date=calendar_date,
                    scheduled_time=request.form.get("scheduled_time", "09:00"),
                    destinations=request.form.getlist("destinations") or [request.form.get("destination", "")],
                    goals=[_form_other_value(request.form.get("goals", ""), request.form.get("goals_other", ""))],
                    audience=_form_other_value(request.form.get("audience", ""), request.form.get("audience_other", "")),
                    occasion=_form_other_value(request.form.get("occasion", ""), request.form.get("occasion_other", "")),
                    promotion=_form_other_value(request.form.get("promotion", ""), request.form.get("promotion_other", "")),
                    notes=request.form.get("notes", ""),
                )
                flash("Calendar item updated.")
        except ValueError as exc:
            flash(str(exc))
        return redirect(url_for("calendar", _anchor=f"planned-item-{item_id}"))

    @app.post("/calendar/planned/<int:item_id>/delete")
    def calendar_delete_planned_item(item_id: int) -> str:
        with session_scope(factory) as session:
            try:
                delete_planned_content_item(session, item_id)
                flash("Scheduled post deleted.")
            except ValueError as exc:
                flash(str(exc))
        return redirect(url_for("calendar"))

    @app.post("/api/calendar/planned/<int:item_id>/reschedule")
    def api_calendar_reschedule_planned_item(item_id: int):
        payload = request.get_json(silent=True) or {}
        try:
            calendar_date = date.fromisoformat(str(payload.get("calendar_date") or ""))
            scheduled_time = str(payload.get("scheduled_time") or "09:00")
        except ValueError:
            return jsonify({"error": "Use a valid schedule date."}), 400
        with session_scope(factory) as session:
            try:
                item = update_planned_content_schedule(session, item_id, calendar_date, scheduled_time)
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            return jsonify({"planned_item": serialize_planned_content_item(session, item)})

    @app.post("/api/calendar/tasks/<int:task_id>/reschedule")
    def api_calendar_reschedule_task(task_id: int):
        payload = request.get_json(silent=True) or {}
        try:
            due_date = date.fromisoformat(str(payload.get("calendar_date") or ""))
            scheduled_time = str(payload.get("scheduled_time") or "09:00")
        except ValueError:
            return jsonify({"error": "Use a valid schedule date."}), 400
        with session_scope(factory) as session:
            task = session.get(TaskRecord, task_id)
            if task is None:
                return jsonify({"error": "Task not found."}), 404
            try:
                normalized_time = normalize_scheduled_time(scheduled_time)
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            task.due_date = due_date
            task.scheduled_time = normalized_time
            if task.planned_content_item_id:
                item = session.get(PlannedContentRecord, task.planned_content_item_id)
                if item is not None:
                    item.calendar_date = due_date
                    item.scheduled_time = normalized_time
            return jsonify({"task": serialize_task_view(task_view(task))})

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
                assign_asset_to_task(session, task_id, int(asset_id_text), app.config["ASSETS_ROOT"])
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
        show_hidden = request.args.get("show_hidden") == "1"
        page = _page_arg(request.args.get("page"))
        selected_tag = request.args.get("tag", "")
        with session_scope(factory) as session:
            return render_template("assets.html", **_asset_management_context(session, include_hidden=show_hidden, page=page, selected_tag=selected_tag))

    @app.get("/products")
    def products_admin() -> str:
        selected_sort = request.args.get("sort", "name").strip().lower()
        show_hidden = request.args.get("show_hidden") == "1"
        page = _page_arg(request.args.get("page"))
        with session_scope(factory) as session:
            all_tags = _all_product_tags(session)
            product_count = session.scalar(select(func.count()).select_from(ProductRecord)) or 0
            pagination = _pagination(page, product_count, PRODUCTS_PAGE_SIZE)
            product_query = select(ProductRecord)
            if selected_sort == "source":
                product_query = product_query.order_by(ProductRecord.external_source, ProductRecord.name)
            elif selected_sort == "synced":
                product_query = product_query.order_by(ProductRecord.last_synced_at.desc(), ProductRecord.name)
            else:
                selected_sort = "name"
                product_query = product_query.order_by(ProductRecord.name)
            products = list(session.scalars(product_query.offset(pagination["offset"]).limit(PRODUCTS_PAGE_SIZE)))
            product_ids = [product.id for product in products]
            assets_by_product: dict[int, list[AssetRecord]] = {product.id: [] for product in products}
            references_by_product: dict[int, list[ProductExternalReference]] = {product.id: [] for product in products}
            reviews_by_product: dict[int, list[dict[str, object]]] = {product.id: [] for product in products}
            review_counts_by_product: dict[int, int] = {product.id: 0 for product in products}
            hidden_asset_count = hidden_asset_group_count(session)
            if product_ids:
                asset_query = select(AssetRecord).where(AssetRecord.product_id.in_(product_ids)).order_by(AssetRecord.product_id, AssetRecord.id)
                if not show_hidden:
                    asset_query = asset_query.where(AssetRecord.hidden_from_generation == 0)
                assets = list(session.scalars(asset_query))
                references = list(
                    session.scalars(
                        select(ProductExternalReference)
                        .where(ProductExternalReference.product_id.in_(product_ids))
                        .order_by(ProductExternalReference.product_id, ProductExternalReference.source_name)
                    )
                )
                review_counts = session.execute(
                    select(EtsyReviewRecord.product_id, func.count())
                    .where(EtsyReviewRecord.product_id.in_(product_ids))
                    .group_by(EtsyReviewRecord.product_id)
                ).all()
                reviews = list(
                    session.scalars(
                        select(EtsyReviewRecord)
                        .where(EtsyReviewRecord.product_id.in_(product_ids))
                        .order_by(EtsyReviewRecord.product_id, EtsyReviewRecord.created_timestamp.desc(), EtsyReviewRecord.id.desc())
                    )
                )
                for asset in assets:
                    if asset.product_id is not None:
                        assets_by_product.setdefault(asset.product_id, []).append(asset)
                for reference in references:
                    references_by_product.setdefault(reference.product_id, []).append(reference)
                for product_id, count in review_counts:
                    if product_id is not None:
                        review_counts_by_product[product_id] = int(count or 0)
                for review in reviews:
                    if review.product_id is None or len(reviews_by_product.setdefault(review.product_id, [])) >= 3:
                        continue
                    reviews_by_product[review.product_id].append(_product_review_model(review))
            return render_template(
                "products.html",
                active="products",
                products=products,
                all_products_count=product_count,
                all_tags=all_tags,
                selected_sort=selected_sort,
                show_hidden=show_hidden,
                pagination=pagination,
                hidden_asset_count=hidden_asset_count,
                assets_by_product=assets_by_product,
                references_by_product=references_by_product,
                reviews_by_product=reviews_by_product,
                review_counts_by_product=review_counts_by_product,
            )

    @app.post("/products/<int:product_id>/tags")
    def update_product_tags(product_id: int) -> str:
        tags = _tag_values(request.form.get("tags", ""))
        with session_scope(factory) as session:
            product = session.get(ProductRecord, product_id)
            if product is None:
                abort(404)
            product.use_cases_json = json.dumps(tags)
            flash("Product tags saved.")
        return redirect(url_for("products_admin", _anchor=f"product-{product_id}"))

    @app.post("/products/<int:product_id>/tags/add")
    def add_product_tag(product_id: int) -> str:
        tag = _tag_values(request.form.get("tag", ""))
        with session_scope(factory) as session:
            product = session.get(ProductRecord, product_id)
            if product is None:
                abort(404)
            for value in tag:
                _add_product_tag(product, value)
            flash("Product tag added." if tag else "Enter a product tag to add.")
        return redirect(url_for("products_admin", _anchor=f"product-{product_id}"))

    @app.post("/products/<int:product_id>/default-reference-assets")
    def product_default_reference_assets(product_id: int) -> str:
        return_to = request.form.get("return_to") or url_for("products_admin", _anchor=f"product-{product_id}")
        try:
            asset_ids = [int(value) for value in request.form.getlist("asset_ids")]
            with session_scope(factory) as session:
                update_product_default_reference_assets(session, product_id, asset_ids)
                flash("Default reference images saved.")
        except ValueError as exc:
            flash(str(exc))
        return redirect(return_to)

    @app.post("/assets/scan")
    def scan_assets() -> str:
        with session_scope(factory) as session:
            imported = scan_local_asset_folder(session, app.config["ASSETS_ROOT"])
            flash(f"Scanned local assets. Found {len(imported)} image file(s).")
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
            try:
                _validate_image_file(temp_path, "source photo")
            except ValueError as exc:
                flash(str(exc))
                return redirect(url_for("assets"))
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
        return_to = request.form.get("return_to") or url_for("assets", _anchor=f"asset-{asset_id}")
        with session_scope(factory) as session:
            try:
                review_asset(session, asset_id, review_state, notes)
                flash("Asset review saved.")
            except ValueError as exc:
                flash(str(exc))
        return redirect(return_to)

    @app.post("/assets/<int:asset_id>/visibility")
    def asset_visibility(asset_id: int) -> str:
        hidden = request.form.get("hidden", "0") == "1"
        return_to = request.form.get("return_to") or url_for("assets", _anchor=f"asset-{asset_id}")
        note = request.form.get("manual_override_note", "")
        with session_scope(factory) as session:
            try:
                set_asset_generation_visibility(session, asset_id, hidden, note)
                flash("Image hidden from automation." if hidden else "Image restored for automation.")
            except ValueError as exc:
                flash(str(exc))
        return redirect(return_to)

    @app.post("/assets/<int:asset_id>/product")
    def asset_product_link(asset_id: int) -> str:
        return_to = request.form.get("return_to") or url_for("assets", _anchor=f"asset-{asset_id}")
        name = request.form.get("name", "").strip()
        product_id_text = request.form.get("product_id", "").strip()
        try:
            product_id = int(product_id_text) if product_id_text else None
        except ValueError:
            flash("Product not found.")
            return redirect(return_to)
        if "name" in request.form and not name:
            flash("Photo name is required.")
            return redirect(return_to)
        with session_scope(factory) as session:
            asset = session.get(AssetRecord, asset_id)
            if asset is None:
                flash("Asset not found.")
                return redirect(return_to)
            if product_id is not None and session.get(ProductRecord, product_id) is None:
                flash("Product not found.")
                return redirect(return_to)
            if "name" in request.form:
                asset.name = name
            asset.product_id = product_id
            if product_id is None:
                asset.default_reference = 0
            flash("Photo details saved.")
        return redirect(return_to)

    @app.post("/assets/<int:asset_id>/delete-local")
    def asset_delete_local(asset_id: int) -> str:
        return_to = request.form.get("return_to") or url_for("assets")
        with session_scope(factory) as session:
            try:
                result = delete_local_asset_file(session, asset_id)
                deleted_count = len(result.deleted_paths)
                asset_count = len(result.asset_ids)
                flash(
                    f"Deleted {deleted_count} local file{'s' if deleted_count != 1 else ''} "
                    f"and unlinked {asset_count} asset record{'s' if asset_count != 1 else ''}."
                )
            except (OSError, ValueError) as exc:
                flash(str(exc))
        return redirect(return_to)

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

    @app.get("/phase5-readiness")
    def phase5_readiness() -> str:
        with session_scope(factory) as session:
            packet = build_phase5_approval_packet(session)
            return render_template(
                "phase5_readiness.html",
                active="phase5_readiness",
                readiness=packet.readiness,
                packet=serialize_phase5_approval_packet(packet),
            )

    @app.post("/phase5-readiness/export")
    def export_phase5_approval_packet():
        with session_scope(factory) as session:
            path = write_phase5_approval_packet(session, app.config["EXPORT_DIR"])
        return send_file(path.resolve(), as_attachment=True, download_name=path.name, mimetype="text/markdown")

    @app.post("/phase5-readiness/export-creative-handoff")
    def export_phase5_creative_handoff():
        with session_scope(factory) as session:
            path = write_phase5_creative_handoff(session, app.config["EXPORT_DIR"])
        return send_file(path.resolve(), as_attachment=True, download_name=path.name, mimetype="text/markdown")

    @app.post("/phase5-readiness/copy-review")
    def phase5_copy_review() -> str:
        candidate_id = _int_or_none(request.form.get("candidate_id"))
        if candidate_id is None:
            flash("Choose a Facebook copy candidate to review.")
            return redirect(url_for("phase5_readiness"))
        with session_scope(factory) as session:
            try:
                record_candidate_review(
                    session,
                    candidate_id,
                    request.form.get("review_state", "needs_review"),
                    revision_notes=request.form.get("revision_notes", ""),
                    reviewed_by=request.form.get("reviewed_by", ""),
                    edited_copy_text=request.form.get("copy_text", ""),
                )
                flash("Copy approval saved.")
            except ValueError as exc:
                flash(str(exc))
        return redirect(url_for("phase5_readiness", _anchor="facebook-copy-review"))

    @app.post("/phase5-readiness/creative-review")
    def phase5_creative_review() -> str:
        job_id = _int_or_none(request.form.get("job_id"))
        if job_id is None:
            flash("Choose a generated creative job to review.")
            return redirect(url_for("phase5_readiness"))
        with session_scope(factory) as session:
            try:
                review_creative_generation_job(
                    session,
                    job_id,
                    review_state=request.form.get("review_state", "needs_review"),
                    review_notes=request.form.get("review_notes", ""),
                    reviewed_by=request.form.get("reviewed_by", ""),
                )
                flash("Creative approval saved.")
            except ValueError as exc:
                flash(str(exc))
        return redirect(url_for("phase5_readiness", _anchor="generated-creative-review"))

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

    @app.post("/imports/etsy-sales-csv")
    def import_etsy_sales_csv_upload() -> str:
        upload = request.files.get("sales_csv")
        if upload is None or not upload.filename:
            flash("Choose an Etsy order items CSV to upload.")
            return redirect(url_for("settings"))
        filename = secure_filename(upload.filename)
        if not filename or Path(filename).suffix.lower() != ".csv":
            flash("Choose a valid .csv file.")
            return redirect(url_for("settings"))
        with tempfile.TemporaryDirectory() as tmp:
            temp_path = Path(tmp) / filename
            upload.save(temp_path)
            with session_scope(factory) as session:
                try:
                    summary = import_etsy_sales_csv(session, temp_path)
                    flash(
                        f"Imported Etsy order items CSV: {summary.imported} new row(s), "
                        f"{summary.updated} updated, {summary.skipped} skipped, {summary.unmatched} unmatched."
                    )
                except FileNotFoundError as exc:
                    flash(str(exc))
                except ValueError as exc:
                    flash(str(exc))
        return redirect(url_for("data_health"))

    @app.post("/integrations/etsy/sync")
    def sync_etsy() -> str:
        with session_scope(factory) as session:
            summary = sync_etsy_read_only(session)
            if summary.errors:
                flash(summary.errors[0])
            else:
                flash(
                    f"Synced Etsy: {summary.products_imported} listing(s), "
                    f"{summary.assets_imported} image(s), {summary.reviews_imported} review(s)."
                )
        return redirect(_safe_return_url(request.form.get("return_to"), "data_health"))

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
        with session_scope(factory) as session:
            products = list(session.scalars(select(ProductRecord).order_by(ProductRecord.name)))
        return render_template(
            "settings.html",
            active="settings",
            business_dir=business_dir,
            db_path=app.config["DB_PATH"],
            assets_root=app.config["ASSETS_ROOT"],
            asset_library_root=app.config["ASSET_LIBRARY_ROOT"],
            export_dir=app.config["EXPORT_DIR"],
            products=products,
        )

    @app.post("/settings/export")
    def export_data():
        scope = request.form.get("scope", "all")
        with session_scope(factory) as session:
            path = export_operating_data(session, app.config["EXPORT_DIR"], scope=scope)
        return send_file(path.resolve(), as_attachment=True, download_name=path.name)

    return app


def _int_or_none(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _safe_return_url(value: object, fallback_endpoint: str) -> str:
    path = str(value or "").strip()
    if path.startswith("/") and not path.startswith("//"):
        return path
    return url_for(fallback_endpoint)


def _form_other_value(value: str, other_value: str) -> str:
    if str(value).strip() == "__other__":
        return str(other_value).strip()
    return str(value or "").strip()


def _save_image_upload(upload, output_root: Path, label: str = "image") -> Path:
    filename = secure_filename(upload.filename or "")
    if not filename:
        raise ValueError(f"Choose a {label} file with a valid filename.")
    output_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    target = output_root / f"{stamp}-{filename}"
    with tempfile.NamedTemporaryFile(delete=False, dir=output_root) as temp:
        temp_path = Path(temp.name)
        copyfileobj(upload.stream, temp)
    try:
        from PIL import Image, UnidentifiedImageError

        try:
            with Image.open(temp_path) as image:
                image.verify()
        except UnidentifiedImageError as exc:
            raise ValueError(f"Uploaded {label} must be a valid image file.") from exc
        except OSError as exc:
            raise ValueError(f"Uploaded {label} could not be read as an image.") from exc
        temp_path.replace(target)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return target


def _validate_image_file(path: Path, label: str) -> None:
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(path) as image:
            image.verify()
    except UnidentifiedImageError as exc:
        raise ValueError(f"{label.title()} must be a valid image file.") from exc
    except OSError as exc:
        raise ValueError(f"{label.title()} could not be read as an image.") from exc


def _planner_reference_assets(session, products: list[ProductRecord]) -> list[dict[str, object]]:
    product_ids = [product.id for product in products if product.id is not None]
    if not product_ids:
        return []
    assets = list(
        session.scalars(
            select(AssetRecord)
            .where(AssetRecord.product_id.in_(product_ids))
            .where(AssetRecord.asset_type.in_(["source photo", "Etsy product photo", "edited photo", "external listing image"]))
            .where(AssetRecord.hidden_from_generation == 0)
            .order_by(AssetRecord.product_id, (AssetRecord.review_state == "approved").desc(), AssetRecord.file_exists.desc(), AssetRecord.id)
        )
    )
    return [
        {
            "id": asset.id,
            "product_id": asset.product_id,
            "name": asset.name,
            "asset_type": asset.asset_type,
            "source_path": asset.source_path,
            "review_state": asset.review_state,
            "file_exists": bool(asset.file_exists),
            "preview_url": _remote_asset_preview_url(asset),
            "selectable": bool(asset.file_exists and asset.review_state == "approved") or _is_remote_product_image(asset),
            "downloads_when_selected": _is_remote_product_image(asset),
        }
        for asset in assets
    ]


def _is_remote_product_image(asset: AssetRecord) -> bool:
    image_url = asset.source_path or asset.preview_path or asset.canonical_url
    return bool(
        not asset.file_exists
        and image_url.startswith(("http://", "https://", "file://"))
        and asset.asset_type in {"Etsy product photo", "external listing image"}
    )


def _remote_asset_preview_url(asset: AssetRecord) -> str:
    if asset.file_exists:
        return ""
    for value in (asset.preview_path, asset.source_path, asset.canonical_url):
        if value.startswith(("http://", "https://", "file://")):
            return value
    return ""


def _start_reference_asset_download(factory, item_id: int, assets_root: Path) -> None:
    def worker() -> None:
        try:
            with session_scope(factory) as session:
                localize_planned_content_reference_assets(session, item_id, assets_root)
            logging.getLogger(__name__).info("Prepared remote reference images for planned item %s", item_id)
        except Exception as exc:
            logging.getLogger(__name__).exception("Failed to prepare remote reference images for planned item %s", item_id)
            with session_scope(factory) as session:
                item = session.get(PlannedContentRecord, item_id)
                if item is not None:
                    item.production_error = f"Remote image preparation failed: {exc}"

    thread = threading.Thread(target=worker, name=f"planning-reference-download-{item_id}", daemon=True)
    thread.start()


def _calendar_days(task_models: list[object], planned_items: list[dict[str, object]]) -> list[dict[str, object]]:
    today = date.today()
    dates = [today]
    for model in task_models:
        task = getattr(model, "task", None)
        if task is not None:
            dates.append(task.due_date)
    for item in planned_items:
        try:
            dates.append(date.fromisoformat(str(item.get("calendar_date"))))
        except ValueError:
            continue
    anchor = min(dates)
    start = anchor - timedelta(days=(anchor.weekday() + 1) % 7)
    days: list[dict[str, object]] = []
    for offset in range(35):
        day = start + timedelta(days=offset)
        day_tasks = [model for model in task_models if getattr(getattr(model, "task", None), "due_date", None) == day]
        day_planned = [item for item in planned_items if item.get("calendar_date") == day.isoformat()]
        day_planned.sort(key=lambda item: str(item.get("scheduled_time") or "09:00"))
        day_tasks.sort(key=lambda model: (getattr(model.task, "scheduled_time", "") or "09:00", model.task.id))
        days.append(
            {
                "date": day,
                "iso": day.isoformat(),
                "label": day.strftime("%b %-d") if os.name != "nt" else day.strftime("%b %#d"),
                "day_number": day.day,
                "is_today": day == today,
                "is_weekend": day.weekday() >= 5,
                "planned_items": day_planned,
                "tasks": day_tasks,
            }
        )
    return days


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


def _page_arg(value: str | None) -> int:
    try:
        return max(int(value or "1"), 1)
    except ValueError:
        return 1


def _pagination(page: int, total: int, page_size: int) -> dict[str, int | bool]:
    page_size = max(page_size, 1)
    total_pages = max((total + page_size - 1) // page_size, 1)
    current_page = min(max(page, 1), total_pages)
    return {
        "page": current_page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "offset": (current_page - 1) * page_size,
        "has_previous": current_page > 1,
        "has_next": current_page < total_pages,
        "previous_page": max(current_page - 1, 1),
        "next_page": min(current_page + 1, total_pages),
        "start": 0 if total == 0 else (current_page - 1) * page_size + 1,
        "end": min(current_page * page_size, total),
    }


def _dashboard_review_queue(session, limit: int = 6) -> list[dict[str, object]]:
    review_states = {"needs_review", "needs review", "rewrite_requested"}
    candidates = list(
        session.scalars(
            select(GeneratedContentCandidateRecord)
            .where(GeneratedContentCandidateRecord.review_state.in_(review_states))
            .order_by(GeneratedContentCandidateRecord.updated_at.desc(), GeneratedContentCandidateRecord.id.desc())
        )
    )
    candidates_by_item: dict[int, list[GeneratedContentCandidateRecord]] = {}
    for candidate in candidates:
        if candidate.planned_item_id is None:
            continue
        candidates_by_item.setdefault(candidate.planned_item_id, []).append(candidate)

    item_ids = set(candidates_by_item)
    item_query = select(PlannedContentRecord).where(
        (PlannedContentRecord.status == "needs_review") | (PlannedContentRecord.id.in_(item_ids) if item_ids else False)
    ).order_by(PlannedContentRecord.calendar_date, PlannedContentRecord.id)
    items = list(session.scalars(item_query).unique())[:limit]

    product_ids: set[int] = set()
    for item in items:
        for value in json_list(item.product_ids_json):
            try:
                product_ids.add(int(value))
            except (TypeError, ValueError):
                continue
    products_by_id = {
        product.id: product.name
        for product in session.scalars(select(ProductRecord).where(ProductRecord.id.in_(product_ids))).all()
    } if product_ids else {}

    queue: list[dict[str, object]] = []
    for item in items:
        item_candidates = candidates_by_item.get(item.id, [])
        first_candidate = item_candidates[0] if item_candidates else None
        destinations = json_list(item.destinations_json)
        primary_destination = destinations[0] if destinations else ""
        review_labels = sorted(
            label
            for label in {_candidate_review_label(candidate.candidate_type, primary_destination) for candidate in item_candidates}
            if label
        )
        product_names = [
            products_by_id.get(int(value))
            for value in json_list(item.product_ids_json)
            if str(value).isdigit() and products_by_id.get(int(value))
        ]
        queue.append(
            {
                "id": item.id,
                "calendar_date": item.calendar_date.isoformat(),
                "scheduled_time": item.scheduled_time or "09:00",
                "status": item.status,
                "destinations": destinations,
                "product_names": product_names,
                "candidate_count": len(item_candidates),
                "review_labels": review_labels,
                "review_path": f"/planning#candidate-{first_candidate.id}" if first_candidate else f"/planning#planned-item-{item.id}",
            }
        )
    return queue


def _candidate_review_label(candidate_type: str, destination: str) -> str:
    candidate_key = str(candidate_type or "").strip().lower()
    destination_key = str(destination or "").strip().lower()
    if candidate_key == "facebook_post":
        if destination_key == "instagram":
            return "Instagram Caption"
        if destination_key == "pinterest":
            return "Pinterest Pin Copy"
        if destination:
            return f"{destination} Post"
        return "Social Copy"
    if candidate_key == "image_asset_option":
        return ""
    return candidate_key.replace("_", " ").title() if candidate_key else ""


def _product_review_model(record: EtsyReviewRecord) -> dict[str, object]:
    created_on = ""
    if record.created_timestamp:
        try:
            created_on = datetime.fromtimestamp(record.created_timestamp).date().isoformat()
        except (OSError, OverflowError, ValueError):
            created_on = ""
    return {
        "rating": record.rating,
        "review": record.review,
        "language": record.language,
        "image_url": record.image_url_fullxfull,
        "created_on": created_on,
        "listing_id": record.listing_id,
    }


def _all_product_tags(session) -> list[str]:
    products = session.scalars(select(ProductRecord)).all()
    return sorted({tag for product in products for tag in json_list(product.use_cases_json)})


def _add_product_tag(product: ProductRecord, value: str) -> tuple[str, list[str], bool]:
    normalized = _tag_values(value)
    if not normalized:
        return "", json_list(product.use_cases_json), False
    tag = normalized[0]
    tags = json_list(product.use_cases_json)
    existing = {current.lower() for current in tags}
    created = tag.lower() not in existing
    if created:
        tags.append(tag)
        product.use_cases_json = json.dumps(tags)
    saved_tag = tag if created else next((current for current in tags if current.lower() == tag.lower()), tag)
    return saved_tag, tags, created


def main(argv: list[str] | None = None) -> int:
    load_local_env()
    parser = argparse.ArgumentParser(description="Run the MattMadeMe Marketing OS local web console")
    parser.add_argument("--host", default=os.environ.get("MARKETING_OS_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MARKETING_OS_PORT", "8000")))
    parser.add_argument("--db-path", default=os.environ.get("MARKETING_OS_DB_PATH", "data/marketing_os.sqlite"))
    parser.add_argument("--business-dir", default=os.environ.get("MARKETING_OS_BUSINESS_DIR", "docs/business"))
    parser.add_argument("--bootstrap-data", action="store_true", help="Seed business products and a default plan on startup.")
    args = parser.parse_args(argv)

    if args.bootstrap_data:
        os.environ["MARKETING_OS_BOOTSTRAP_DATA"] = "1"
    app = create_app(args.db_path, args.business_dir)
    app.run(host=args.host, port=args.port, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
