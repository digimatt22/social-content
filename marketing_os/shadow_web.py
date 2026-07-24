from __future__ import annotations

import json

from flask import Blueprint, abort, current_app, g, jsonify, redirect, render_template, request, url_for
from sqlalchemy import select

from .db import session_scope
from .db_models import ShadowDigestRecord
from .services.pinterest_shadow import (
    complete_review_session,
    record_review_decision,
    shadow_exceptions,
    shadow_read_model,
    start_review_session,
)


shadow_blueprint = Blueprint("pinterest_shadow", __name__)


@shadow_blueprint.get("/api/shadow")
@shadow_blueprint.get("/api/shadow-campaigns")
def api_shadow():
    with session_scope(current_app.config["SESSION_FACTORY"]) as session:
        return jsonify(shadow_read_model(session))


@shadow_blueprint.get("/api/shadow/<campaign_id>")
@shadow_blueprint.get("/api/shadow-campaigns/<campaign_id>")
def api_shadow_campaign(campaign_id: str):
    with session_scope(current_app.config["SESSION_FACTORY"]) as session:
        payload = shadow_read_model(session, campaign_id=campaign_id)
        if not payload["campaigns"]:
            return jsonify({"error": "shadow_campaign_not_found"}), 404
        return jsonify(payload["campaigns"][0])


@shadow_blueprint.get("/api/shadow/exceptions")
def api_shadow_exceptions():
    with session_scope(current_app.config["SESSION_FACTORY"]) as session:
        return jsonify(shadow_exceptions(session))


@shadow_blueprint.post("/api/shadow/review-sessions")
@shadow_blueprint.post("/api/shadow-review-sessions")
def api_start_shadow_review():
    payload = request.get_json(silent=True) or request.form
    with session_scope(current_app.config["SESSION_FACTORY"]) as session:
        try:
            review = start_review_session(
                session,
                str(payload.get("campaignId", "")),
                reviewer=g.principal.username,
                session_token=str(payload.get("sessionToken", "")).strip() or None,
            )
        except (LookupError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400
        response = {"sessionToken": review.session_token, "campaignId": payload.get("campaignId")}
    if request.is_json:
        return jsonify(response), 201
    return redirect(url_for("pinterest_shadow.shadow_campaign_page", campaign_id=payload.get("campaignId"), session=response["sessionToken"]))


@shadow_blueprint.post("/api/shadow/review-sessions/<session_token>/decisions")
@shadow_blueprint.post("/api/shadow-review-sessions/<session_token>/decisions")
def api_record_shadow_decision(session_token: str):
    payload = request.get_json(silent=True) or request.form
    reasons = payload.get("reasonCodes", [])
    if isinstance(reasons, str):
        reasons = [item.strip() for item in reasons.split(",") if item.strip()]
    with session_scope(current_app.config["SESSION_FACTORY"]) as session:
        try:
            decision = record_review_decision(
                session,
                session_token,
                str(payload.get("publicationId", "")).strip() or None,
                decision_kind=str(payload.get("decisionKind", "")),
                result=str(payload.get("result", "")),
                reason_codes=list(reasons),
                reviewer_note=str(payload.get("reviewerNote", "")),
                manifest_id=_optional_int(payload.get("manifestId")),
                review_asset_id=_optional_int(payload.get("reviewAssetId")),
            )
        except (LookupError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400
        response = {"decisionId": decision.id, "sessionToken": session_token}
    if request.is_json:
        return jsonify(response), 201
    return redirect(request.referrer or url_for("pinterest_shadow.shadow_page"))


@shadow_blueprint.post("/api/shadow/review-sessions/<session_token>/complete")
@shadow_blueprint.post("/api/shadow-review-sessions/<session_token>/complete")
def api_complete_shadow_review(session_token: str):
    with session_scope(current_app.config["SESSION_FACTORY"]) as session:
        try:
            result = complete_review_session(session, session_token)
        except (LookupError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400
    if request.is_json:
        return jsonify(result)
    return redirect(request.referrer or url_for("pinterest_shadow.shadow_page"))


@shadow_blueprint.get("/shadow")
@shadow_blueprint.get("/shadow-campaigns")
def shadow_page():
    with session_scope(current_app.config["SESSION_FACTORY"]) as session:
        return render_template(
            "shadow.html",
            active="shadow",
            shadow=shadow_read_model(session),
            exceptions=shadow_exceptions(session),
        )


@shadow_blueprint.get("/shadow/<campaign_id>")
@shadow_blueprint.get("/shadow-campaigns/<campaign_id>")
def shadow_campaign_page(campaign_id: str):
    with session_scope(current_app.config["SESSION_FACTORY"]) as session:
        payload = shadow_read_model(session, campaign_id=campaign_id)
        if not payload["campaigns"]:
            abort(404)
        return render_template(
            "shadow_campaign.html",
            active="shadow",
            campaign=payload["campaigns"][0],
            review_session_token=request.args.get("session", ""),
        )


@shadow_blueprint.get("/shadow/digest/latest")
@shadow_blueprint.get("/shadow-digests")
def shadow_digest_page():
    with session_scope(current_app.config["SESSION_FACTORY"]) as session:
        digest = session.scalar(
            select(ShadowDigestRecord).order_by(
                ShadowDigestRecord.utc_week.desc(),
                ShadowDigestRecord.created_at.desc(),
            )
        )
        return render_template(
            "shadow_digest.html",
            active="shadow",
            digest=json.loads(digest.payload_json) if digest else None,
            digest_record=digest,
        )


@shadow_blueprint.get("/api/shadow-digests/latest")
def api_shadow_digest_latest():
    with session_scope(current_app.config["SESSION_FACTORY"]) as session:
        digest = session.scalar(
            select(ShadowDigestRecord).order_by(
                ShadowDigestRecord.utc_week.desc(),
                ShadowDigestRecord.created_at.desc(),
            )
        )
        if digest is None:
            return jsonify({"error": "shadow_digest_not_found"}), 404
        return jsonify(
            {
                "id": digest.id,
                "utcWeek": digest.utc_week.isoformat(),
                "inputHash": digest.input_hash,
                "ready": digest.ready_count,
                "blocked": digest.blocked_count,
                "payload": json.loads(digest.payload_json),
            }
        )


def _optional_int(value):
    if value in {None, ""}:
        return None
    return int(value)
