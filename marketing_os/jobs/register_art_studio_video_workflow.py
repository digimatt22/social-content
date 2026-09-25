from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..db import create_db_engine, init_db, session_factory, session_scope
from ..services.art_studio import art_studio_video_requests, register_video_request_workflow


def run(db_path: str | Path | None = None, manifest_path: str | Path = "") -> dict[str, object]:
    manifest = _load_manifest(manifest_path)
    request_job_id = int(manifest.get("request_job_id") or 0)
    planner_result = _dict_value(manifest.get("planner_result"))
    opening_card = _dict_value(manifest.get("opening_card"))
    ending_card = _dict_value(manifest.get("ending_card"))
    video_editor_request = _dict_value(manifest.get("video_editor_request"))

    engine = create_db_engine(db_path)
    init_db(engine)
    factory = session_factory(engine)
    try:
        with session_scope(factory) as session:
            request_job = register_video_request_workflow(
                session,
                request_job_id=request_job_id,
                planner_result=planner_result,
                opening_card_prompt=str(opening_card.get("prompt") or ""),
                opening_card_title=str(opening_card.get("title") or ""),
                ending_card_required=bool(ending_card.get("required")),
                ending_card_prompt=str(ending_card.get("prompt") or ""),
                ending_card_title=str(ending_card.get("title") or ""),
                provider=str(manifest.get("provider") or "codex_agent"),
                opening_provider=str(opening_card.get("provider") or "magnific_mcp"),
                opening_model_name=str(opening_card.get("model_name") or "Google Nano Banana 2"),
                ending_provider=str(ending_card.get("provider") or "magnific_mcp"),
                ending_model_name=str(ending_card.get("model_name") or "Google Nano Banana 2"),
                video_editor_request=video_editor_request,
                notes=str(manifest.get("notes") or ""),
            )
            row = next((item for item in art_studio_video_requests(session, limit=200) if item.request_job.id == request_job_id), None)
            if row is None:
                raise ValueError("Video request was not available after registration.")
            return {
                "request_job_id": request_job.id,
                "status": row.status,
                "status_label": row.status_label,
                "opening_card_job_id": row.opening_job.id if row.opening_job else None,
                "ending_card_job_id": row.ending_job.id if row.ending_job else None,
                "planner_summary": row.details.get("planner_summary"),
            }
    finally:
        engine.dispose()


def _load_manifest(manifest_path: str | Path) -> dict[str, object]:
    path = Path(manifest_path)
    if not path.is_file():
        raise ValueError(f"Registration manifest not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Registration manifest must be a JSON object.")
    return data


def _dict_value(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Register agent-written Art Studio video planning outputs and queue scene-card jobs.")
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(run(db_path=args.db_path, manifest_path=args.manifest), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
