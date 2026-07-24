from __future__ import annotations

from flask import Blueprint, current_app, jsonify, render_template

from .db import session_scope
from .services.coverage_intelligence import coverage_exceptions, coverage_read_model


coverage_blueprint = Blueprint("coverage_intelligence", __name__)


@coverage_blueprint.get("/api/coverage")
def api_coverage():
    with session_scope(current_app.config["SESSION_FACTORY"]) as session:
        return jsonify(coverage_read_model(session))


@coverage_blueprint.get("/api/coverage/<int:product_id>")
def api_product_coverage(product_id: int):
    with session_scope(current_app.config["SESSION_FACTORY"]) as session:
        payload = coverage_read_model(session, product_id)
        if not payload["cells"]:
            return jsonify({"error": "coverage_not_found", "productId": product_id}), 404
        return jsonify(payload)


@coverage_blueprint.get("/api/coverage/exceptions")
def api_coverage_exceptions():
    with session_scope(current_app.config["SESSION_FACTORY"]) as session:
        return jsonify(coverage_exceptions(session))


@coverage_blueprint.get("/coverage")
def coverage_page():
    with session_scope(current_app.config["SESSION_FACTORY"]) as session:
        return render_template(
            "coverage.html",
            active="coverage",
            coverage=coverage_read_model(session),
        )


@coverage_blueprint.get("/coverage/exceptions")
def coverage_exceptions_page():
    with session_scope(current_app.config["SESSION_FACTORY"]) as session:
        return render_template(
            "coverage_exceptions.html",
            active="coverage",
            exceptions=coverage_exceptions(session),
        )
