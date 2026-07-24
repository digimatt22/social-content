from __future__ import annotations

import os
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class CapabilityCheck:
    capability: str
    available: bool
    required: bool
    safe_mode: str


PROFILES = {
    "foundation": {
        "postgresql": ("MARKETING_OS_DB_URL", "local_sqlite_only"),
        "application_secret": ("MARKETING_OS_SECRET", "local_unauthenticated"),
    },
    "pinterest_shadow": {
        "postgresql": ("MARKETING_OS_DB_URL", "local_sqlite_only"),
        "application_secret": ("MARKETING_OS_SECRET", "local_unauthenticated"),
        "pinterest_api": ("PINTEREST_ACCESS_TOKEN", "export_only"),
        "alert_delivery": ("MARKETING_OS_ALERT_WEBHOOK_URL", "persist_exceptions_only"),
    },
    "pinterest_publish": {
        "postgresql": ("MARKETING_OS_DB_URL", "publishing_disabled"),
        "application_secret": ("MARKETING_OS_SECRET", "publishing_disabled"),
        "pinterest_api": ("PINTEREST_ACCESS_TOKEN", "shadow_only"),
        "pinterest_account": ("PINTEREST_ACCOUNT_ID", "shadow_only"),
        "pinterest_credential_reference": ("PINTEREST_CREDENTIAL_REFERENCE", "shadow_only"),
        "pinterest_access_tier": ("PINTEREST_ACCESS_TIER", "shadow_only"),
        "approved_boards": ("PINTEREST_APPROVED_BOARD_IDS", "shadow_only"),
        "provider_contract": ("PINTEREST_PROVIDER_CONTRACT_VERSION", "shadow_only"),
        "alert_delivery": ("MARKETING_OS_ALERT_WEBHOOK_URL", "publishing_disabled"),
        "alert_owner": ("MARKETING_OS_ALERT_OWNER", "publishing_disabled"),
        "backup_destination": ("MARKETING_OS_BACKUP_DESTINATION", "publishing_disabled"),
        "backup_key_custodian": ("MARKETING_OS_BACKUP_KEY_CUSTODIAN", "publishing_disabled"),
        "backup_retention": ("MARKETING_OS_BACKUP_RETENTION_DAYS", "publishing_disabled"),
        "backup_rpo": ("MARKETING_OS_BACKUP_RPO_HOURS", "publishing_disabled"),
        "backup_rto": ("MARKETING_OS_BACKUP_RTO_HOURS", "publishing_disabled"),
        "production_hostname": ("MARKETING_OS_PUBLIC_HOSTNAME", "publishing_disabled"),
        "route_approval": ("MARKETING_OS_ROUTE_APPROVED", "publishing_disabled"),
        "deployment_approval": ("MARKETING_OS_DEPLOYMENT_APPROVED", "publishing_disabled"),
        "cost_ceiling": ("MARKETING_OS_DAILY_COST_CENTS", "publishing_disabled"),
        "publish_authority": ("MARKETING_OS_PINTEREST_PUBLISH_ENABLED", "shadow_only"),
    },
}


def check_capabilities(profile: str, environment: dict[str, str] | None = None) -> list[CapabilityCheck]:
    if profile not in PROFILES:
        raise ValueError(f"unknown capability profile: {profile}")
    values = environment if environment is not None else os.environ
    checks = []
    for capability, (variable, safe_mode) in PROFILES[profile].items():
        value = values.get(variable, "").strip()
        available = bool(value)
        if variable == "MARKETING_OS_PINTEREST_PUBLISH_ENABLED":
            available = value == "EXPLICITLY_ENABLED"
        elif variable == "PINTEREST_ACCESS_TIER":
            available = value.lower() == "standard"
        elif variable == "MARKETING_OS_DAILY_COST_CENTS":
            available = value.isdigit() and int(value) > 0
        elif variable in {
            "MARKETING_OS_BACKUP_RETENTION_DAYS",
            "MARKETING_OS_BACKUP_RPO_HOURS",
            "MARKETING_OS_BACKUP_RTO_HOURS",
        }:
            available = value.isdigit() and int(value) > 0
        elif variable in {"MARKETING_OS_ROUTE_APPROVED", "MARKETING_OS_DEPLOYMENT_APPROVED"}:
            available = value == "EXPLICITLY_APPROVED"
        elif variable == "MARKETING_OS_DB_URL":
            available = value.startswith(("postgresql://", "postgresql+psycopg://"))
        checks.append(CapabilityCheck(capability, available, True, safe_mode))
    return checks


def capability_report(profile: str, environment: dict[str, str] | None = None) -> dict:
    checks = check_capabilities(profile, environment)
    missing = [check for check in checks if check.required and not check.available]
    return {
        "profile": profile,
        "ready": not missing,
        "degraded_mode": missing[0].safe_mode if missing else "none",
        "checks": [asdict(check) for check in checks],
    }
