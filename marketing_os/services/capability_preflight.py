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
        "alert_delivery": ("MARKETING_OS_ALERT_WEBHOOK_URL", "publishing_disabled"),
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
        available = bool(value) and not (
            variable == "MARKETING_OS_PINTEREST_PUBLISH_ENABLED" and value.lower() not in {"1", "true", "yes"}
        )
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
