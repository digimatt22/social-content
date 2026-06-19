from __future__ import annotations

import os
from pathlib import Path


def load_local_env() -> None:
    """Load local .env values without overriding explicit shell settings."""
    if os.environ.get("MARKETING_OS_SKIP_DOTENV"):
        return

    package_root = Path(__file__).resolve().parent.parent
    candidates = [Path.cwd() / ".env", package_root / ".env"]
    seen: set[Path] = set()

    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.exists():
            _load_env_file(resolved)


def _load_env_file(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = _clean_env_value(value)


def _clean_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
