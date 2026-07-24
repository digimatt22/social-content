from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db_models import (
    AuditEventRecord,
    OperatorSessionRecord,
    PrincipalRecord,
    ServiceCredentialRecord,
    utc_now,
)


PASSWORD_HASHER = PasswordHasher()
LOGIN_FAILURE_LIMIT = 5
LOGIN_LOCK_MINUTES = 15
SESSION_IDLE_MINUTES = 30
SESSION_ABSOLUTE_HOURS = 12


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    id: int
    username: str
    roles: frozenset[str]
    principal_type: str
    scopes: frozenset[str] = frozenset()


def token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_principal(
    session: Session,
    *,
    username: str,
    password: str,
    roles: set[str],
    display_name: str = "",
) -> PrincipalRecord:
    normalized = username.strip().lower()
    if not normalized or not password:
        raise ValueError("Username and password are required.")
    principal = PrincipalRecord(
        principal_type="human",
        username=normalized,
        display_name=display_name.strip(),
        password_hash=PASSWORD_HASHER.hash(password),
        roles_json=json.dumps(sorted(roles)),
        password_changed_at=utc_now(),
    )
    session.add(principal)
    session.flush()
    record_audit(session, principal.id, "principal.created", "success", "principal", str(principal.id))
    return principal


def authenticate_password(session: Session, username: str, password: str) -> PrincipalRecord | None:
    now = utc_now()
    principal = session.scalar(
        select(PrincipalRecord).where(PrincipalRecord.username == username.strip().lower())
    )
    if principal is None or principal.principal_type != "human" or not principal.active:
        record_audit(session, None, "auth.login", "denied", detail={"reason": "invalid_credentials"})
        return None
    if principal.locked_until and principal.locked_until > now:
        record_audit(session, principal.id, "auth.login", "denied", detail={"reason": "locked"})
        return None
    try:
        valid = PASSWORD_HASHER.verify(principal.password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        valid = False
    if not valid:
        principal.failed_login_count += 1
        if principal.failed_login_count >= LOGIN_FAILURE_LIMIT:
            principal.locked_until = now + timedelta(minutes=LOGIN_LOCK_MINUTES)
        record_audit(session, principal.id, "auth.login", "denied", detail={"reason": "invalid_credentials"})
        return None
    principal.failed_login_count = 0
    principal.locked_until = None
    principal.last_login_at = now
    if PASSWORD_HASHER.check_needs_rehash(principal.password_hash):
        principal.password_hash = PASSWORD_HASHER.hash(password)
    record_audit(session, principal.id, "auth.login", "success")
    return principal


def create_operator_session(
    session: Session,
    principal: PrincipalRecord,
    *,
    user_agent: str = "",
    remote_address: str = "",
) -> tuple[str, str, OperatorSessionRecord]:
    now = utc_now()
    raw_session = secrets.token_urlsafe(48)
    raw_csrf = secrets.token_urlsafe(32)
    record = OperatorSessionRecord(
        principal_id=principal.id,
        session_token_hash=token_hash(raw_session),
        csrf_token_hash=token_hash(raw_csrf),
        idle_expires_at=now + timedelta(minutes=SESSION_IDLE_MINUTES),
        absolute_expires_at=now + timedelta(hours=SESSION_ABSOLUTE_HOURS),
        user_agent_hash=token_hash(user_agent) if user_agent else "",
        remote_address_hash=token_hash(remote_address) if remote_address else "",
    )
    session.add(record)
    session.flush()
    return raw_session, raw_csrf, record


def authenticate_session(session: Session, raw_token: str) -> tuple[AuthenticatedPrincipal, OperatorSessionRecord] | None:
    now = utc_now()
    record = session.scalar(
        select(OperatorSessionRecord).where(
            OperatorSessionRecord.session_token_hash == token_hash(raw_token)
        )
    )
    if (
        record is None
        or record.revoked_at is not None
        or record.idle_expires_at <= now
        or record.absolute_expires_at <= now
        or not record.principal.active
    ):
        return None
    record.last_seen_at = now
    record.idle_expires_at = min(
        now + timedelta(minutes=SESSION_IDLE_MINUTES),
        record.absolute_expires_at,
    )
    return _principal_view(record.principal), record


def revoke_session(session: Session, raw_token: str, reason: str = "logout") -> bool:
    record = session.scalar(
        select(OperatorSessionRecord).where(
            OperatorSessionRecord.session_token_hash == token_hash(raw_token)
        )
    )
    if record is None or record.revoked_at is not None:
        return False
    record.revoked_at = utc_now()
    record.revoke_reason = reason
    record_audit(session, record.principal_id, "auth.logout", "success", "session", str(record.id))
    return True


def change_password(
    session: Session,
    principal: PrincipalRecord,
    *,
    current_password: str,
    new_password: str,
) -> None:
    if principal.principal_type != "human" or not new_password:
        raise ValueError("A human principal and new password are required.")
    try:
        valid = PASSWORD_HASHER.verify(principal.password_hash, current_password)
    except (VerifyMismatchError, InvalidHashError):
        valid = False
    if not valid:
        record_audit(session, principal.id, "auth.password_change", "denied")
        raise PermissionError("current password is invalid")
    principal.password_hash = PASSWORD_HASHER.hash(new_password)
    principal.password_changed_at = utc_now()
    for operator_session in principal.sessions:
        if operator_session.revoked_at is None:
            operator_session.revoked_at = utc_now()
            operator_session.revoke_reason = "password_changed"
    record_audit(session, principal.id, "auth.password_change", "success")


def create_service_credential(
    session: Session,
    principal: PrincipalRecord,
    *,
    scopes: set[str],
    description: str = "",
) -> tuple[str, ServiceCredentialRecord]:
    raw = f"mos_{secrets.token_urlsafe(40)}"
    credential = ServiceCredentialRecord(
        principal_id=principal.id,
        token_prefix=raw[:16],
        token_hash=token_hash(raw),
        scopes_json=json.dumps(sorted(scopes)),
        description=description,
    )
    session.add(credential)
    session.flush()
    record_audit(
        session,
        principal.id,
        "service_credential.created",
        "success",
        "service_credential",
        str(credential.id),
        {"scopes": sorted(scopes)},
    )
    return raw, credential


def authenticate_service_token(session: Session, raw_token: str) -> AuthenticatedPrincipal | None:
    now = utc_now()
    credential = session.scalar(
        select(ServiceCredentialRecord).where(
            ServiceCredentialRecord.token_hash == token_hash(raw_token)
        )
    )
    if (
        credential is None
        or credential.revoked_at is not None
        or (credential.expires_at is not None and credential.expires_at <= now)
        or not credential.principal.active
    ):
        return None
    credential.last_used_at = now
    principal = _principal_view(credential.principal)
    return AuthenticatedPrincipal(
        id=principal.id,
        username=principal.username,
        roles=frozenset({"service"}),
        principal_type="service",
        scopes=frozenset(json.loads(credential.scopes_json)),
    )


def record_audit(
    session: Session,
    principal_id: int | None,
    event_type: str,
    outcome: str,
    target_type: str = "",
    target_id: str = "",
    detail: dict | None = None,
) -> None:
    session.add(
        AuditEventRecord(
            principal_id=principal_id,
            event_type=event_type,
            outcome=outcome,
            target_type=target_type,
            target_id=target_id,
            detail_json=json.dumps(detail or {}, sort_keys=True),
        )
    )


def _principal_view(principal: PrincipalRecord) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        id=principal.id,
        username=principal.username,
        roles=frozenset(json.loads(principal.roles_json)),
        principal_type=principal.principal_type,
    )
