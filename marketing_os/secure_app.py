from __future__ import annotations

import hmac
import os
import re
import secrets

from flask import Flask, Response, g, make_response, redirect, render_template_string, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import text
from werkzeug.middleware.proxy_fix import ProxyFix

from .db import database_url, session_scope
from .services.auth import (
    authenticate_password,
    authenticate_service_token,
    authenticate_session,
    create_operator_session,
    revoke_session,
    token_hash,
)
from .web_app import create_app
from .services.capability_preflight import capability_report


SESSION_COOKIE = "marketing_os_session"
CSRF_COOKIE = "marketing_os_csrf"
LOGIN_CSRF_COOKIE = "marketing_os_login_csrf"
PUBLIC_ENDPOINTS = {"health", "ready", "login", "static"}
LOGIN_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Marketing OS sign in</title></head>
<body><main><h1>Marketing OS</h1>{% if error %}<p role="alert">{{ error }}</p>{% endif %}
<form method="post"><input type="hidden" name="_login_csrf" value="{{ login_csrf }}">
<label>Username <input name="username" autocomplete="username" required></label>
<label>Password <input type="password" name="password" autocomplete="current-password" required></label>
<button type="submit">Sign in</button></form></main></body></html>"""


def create_secure_app(
    db_path: str | None = None,
    business_dir: str = "docs/business",
    bootstrap_data: bool | None = None,
) -> Flask:
    secret = os.environ.get("MARKETING_OS_SECRET", "")
    if secret in {"", "local-dev-only"} or len(secret) < 24:
        raise RuntimeError("MARKETING_OS_SECRET must be set for the authenticated service.")
    production = os.environ.get("MARKETING_OS_ENV", "").lower() == "production"
    if production:
        if not database_url(db_path).startswith("postgresql"):
            raise RuntimeError("Production authenticated service requires PostgreSQL.")
        trusted_hosts = [item.strip() for item in os.environ.get("MARKETING_OS_TRUSTED_HOSTS", "").split(",") if item.strip()]
        if not trusted_hosts:
            raise RuntimeError("MARKETING_OS_TRUSTED_HOSTS is required in production.")
        proxy_hops = os.environ.get("MARKETING_OS_PROXY_HOPS", "")
        if not proxy_hops.isdigit():
            raise RuntimeError("MARKETING_OS_PROXY_HOPS must explicitly describe the trusted proxy chain.")
    app = create_app(db_path, business_dir, bootstrap_data)
    app.config.update(
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if production:
        app.config["TRUSTED_HOSTS"] = trusted_hosts
        hops = int(os.environ["MARKETING_OS_PROXY_HOPS"])
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=hops, x_host=hops)
    factory = app.config["SESSION_FACTORY"]
    login_csrf_signer = URLSafeTimedSerializer(app.secret_key, salt="marketing-os-login-csrf")

    @app.before_request
    def enforce_auth():
        if request.endpoint in PUBLIC_ENDPOINTS:
            return None
        principal = None
        auth_kind = ""
        bearer = request.headers.get("Authorization", "")
        with session_scope(factory) as session:
            if bearer.startswith("Bearer "):
                principal = authenticate_service_token(session, bearer.removeprefix("Bearer ").strip())
                auth_kind = "service"
            else:
                raw_session = request.cookies.get(SESSION_COOKIE, "")
                authenticated = authenticate_session(session, raw_session) if raw_session else None
                if authenticated:
                    principal, session_record = authenticated
                    g.operator_session_id = session_record.id
                    g.csrf_token_hash = session_record.csrf_token_hash
                    auth_kind = "browser"
        if principal is None:
            if request.path.startswith("/api/"):
                return {"error": "authentication_required"}, 401
            return redirect("/auth/login")
        g.principal = principal
        g.auth_kind = auth_kind
        if not _authorized(principal, request.method, request.path):
            return {"error": "forbidden"}, 403
        if auth_kind == "browser" and request.method not in {"GET", "HEAD", "OPTIONS"}:
            submitted = request.headers.get("X-CSRF-Token") or request.form.get("_csrf_token", "")
            cookie_token = request.cookies.get(CSRF_COOKIE, "")
            stored_hash = getattr(g, "csrf_token_hash", "")
            if (
                not submitted
                or not cookie_token
                or not stored_hash
                or not hmac.compare_digest(submitted, cookie_token)
                or not hmac.compare_digest(token_hash(cookie_token), stored_hash)
            ):
                return {"error": "csrf_validation_failed"}, 403
        return None

    @app.after_request
    def security_headers(response: Response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: https:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'"
        )
        if request.is_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        csrf = request.cookies.get(CSRF_COOKIE, "")
        if csrf and response.mimetype == "text/html" and response.direct_passthrough is False:
            body = response.get_data(as_text=True)
            hidden = f'<input type="hidden" name="_csrf_token" value="{csrf}">'
            body = re.sub(r'(<form\b[^>]*\bmethod=["\']post["\'][^>]*>)', rf"\1{hidden}", body, flags=re.I)
            response.set_data(body)
            response.headers["Content-Length"] = str(len(response.get_data()))
        return response

    @app.route("/auth/login", methods=["GET", "POST"], endpoint="login")
    def login():
        error = ""
        if request.method == "POST":
            submitted_login_csrf = request.form.get("_login_csrf", "")
            cookie_login_csrf = request.cookies.get(LOGIN_CSRF_COOKIE, "")
            try:
                login_csrf_signer.loads(cookie_login_csrf, max_age=600)
                login_csrf_valid = hmac.compare_digest(submitted_login_csrf, cookie_login_csrf)
            except (BadSignature, SignatureExpired):
                login_csrf_valid = False
            if not login_csrf_valid:
                return {"error": "login_csrf_validation_failed"}, 403
            with session_scope(factory) as session:
                principal = authenticate_password(
                    session,
                    request.form.get("username", ""),
                    request.form.get("password", ""),
                )
                if principal is not None:
                    raw_session, raw_csrf, _ = create_operator_session(
                        session,
                        principal,
                        user_agent=request.user_agent.string,
                        remote_address=request.remote_addr or "",
                    )
                    response = redirect("/")
                    response.set_cookie(
                        SESSION_COOKIE,
                        raw_session,
                        secure=True,
                        httponly=True,
                        samesite="Lax",
                        max_age=12 * 60 * 60,
                    )
                    response.set_cookie(
                        CSRF_COOKIE,
                        raw_csrf,
                        secure=True,
                        httponly=True,
                        samesite="Lax",
                        max_age=12 * 60 * 60,
                    )
                    response.delete_cookie(LOGIN_CSRF_COOKIE)
                    return response
            error = "Invalid credentials or account temporarily locked."
        login_csrf = login_csrf_signer.dumps(secrets.token_urlsafe(24))
        response = make_response(
            render_template_string(LOGIN_TEMPLATE, error=error, login_csrf=login_csrf)
        )
        response.set_cookie(
            LOGIN_CSRF_COOKIE,
            login_csrf,
            secure=True,
            httponly=True,
            samesite="Strict",
            max_age=600,
        )
        return response

    @app.post("/auth/logout", endpoint="logout")
    def logout():
        raw_session = request.cookies.get(SESSION_COOKIE, "")
        with session_scope(factory) as session:
            if raw_session:
                revoke_session(session, raw_session)
        response = redirect("/auth/login")
        response.delete_cookie(SESSION_COOKIE)
        response.delete_cookie(CSRF_COOKIE)
        return response

    @app.get("/ready", endpoint="ready")
    def ready():
        try:
            with session_scope(factory) as session:
                session.execute(text("SELECT 1"))
        except Exception:
            return {"status": "not_ready"}, 503
        if production and not capability_report("foundation")["ready"]:
            return {"status": "not_ready"}, 503
        return {"status": "ready"}

    return app


def _authorized(principal, method: str, path: str) -> bool:
    if principal.principal_type == "service":
        needed = "read" if method in {"GET", "HEAD", "OPTIONS"} else "write"
        return needed in principal.scopes or "*" in principal.scopes
    if "admin" in principal.roles:
        return True
    if method in {"GET", "HEAD", "OPTIONS"}:
        return bool(principal.roles & {"viewer", "operator"})
    if path.startswith("/admin") or path.startswith("/api/admin"):
        return False
    return "operator" in principal.roles


app = None


def production_app() -> Flask:
    return create_secure_app()
