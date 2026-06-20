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
            candidate = register_generated_copy_candidate(
                session,
                item_id=int(manifest["planned_item_id"]),
                copy_text=str(manifest.get("copy_text") or ""),
                skill_request=manifest.get("skill_request") if isinstance(manifest.get("skill_request"), dict) else None,
                skill_check=manifest.get("skill_check") if isinstance(manifest.get("skill_check"), dict) else None,
                social_strategy=manifest.get("social_strategy") if isinstance(manifest.get("social_strategy"), dict) else None,
                social_challenge=manifest.get("social_challenge") if isinstance(manifest.get("social_challenge"), dict) else None,
                provider=str(manifest.get("provider") or "codex_agent"),
                notes=str(manifest.get("notes") or ""),
            )
            return {
                "planned_item_id": candidate.planned_item_id,
                "candidate_id": candidate.id,
                "candidate": serialize_candidate(candidate),
            }
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Register Codex agent-written social copy as a Planning review candidate.")
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(run(db_path=args.db_path, manifest_path=args.manifest), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
