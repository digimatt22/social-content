from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..db import create_db_engine, init_db, session_factory, session_scope
from ..services.content_briefs import register_generated_copy_candidate, serialize_candidate


def run(db_path: str | Path | None = None, manifest_path: str | Path = "") -> dict[str, object]:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    engine = create_db_engine(db_path)
    init_db(engine)
    factory = session_factory(engine)
    try:
        with session_scope(factory) as session:
            candidates = [
                register_generated_copy_candidate(
                    session,
                    item_id=int(manifest["planned_item_id"]),
                    copy_text=str(option.get("copy_text") or ""),
                    skill_request=_option_dict(option, manifest, "skill_request"),
                    skill_check=_option_dict(option, manifest, "skill_check"),
                    social_strategy=_option_dict(option, manifest, "social_strategy"),
                    social_challenge=_option_dict(option, manifest, "social_challenge"),
                    provider=_option_provider(option, manifest, index),
                    notes=str(option.get("notes") or manifest.get("notes") or ""),
                )
                for index, option in enumerate(_copy_options(manifest), start=1)
            ]
            candidate = candidates[0]
            return {
                "planned_item_id": candidate.planned_item_id,
                "candidate_id": candidate.id,
                "candidate": serialize_candidate(candidate),
                "candidate_ids": [item.id for item in candidates],
                "candidates": [serialize_candidate(item) for item in candidates],
            }
    finally:
        engine.dispose()


def _copy_options(manifest: dict[str, object]) -> list[dict[str, object]]:
    raw_options = manifest.get("copy_options")
    if isinstance(raw_options, list) and raw_options:
        options = [option for option in raw_options if isinstance(option, dict)]
        if options:
            return options
    return [{"copy_text": manifest.get("copy_text") or ""}]


def _option_dict(option: dict[str, object], manifest: dict[str, object], key: str) -> dict[str, object] | None:
    value = option.get(key)
    if isinstance(value, dict):
        return value
    fallback = manifest.get(key)
    return fallback if isinstance(fallback, dict) else None


def _option_provider(option: dict[str, object], manifest: dict[str, object], index: int) -> str:
    if str(option.get("provider") or "").strip():
        return str(option["provider"]).strip()
    base = str(manifest.get("provider") or "codex_agent").strip() or "codex_agent"
    if isinstance(manifest.get("copy_options"), list):
        return f"{base}_option_{index}"
    return base


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Register Codex agent-written social copy as a Planning review candidate.")
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(run(db_path=args.db_path, manifest_path=args.manifest), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
