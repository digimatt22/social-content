from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..db import create_db_engine, init_db, session_factory, session_scope
from ..services.art_studio import (
    register_social_image_job_output,
    register_video_art_board_job_output,
    register_video_job_output,
    serialize_art_studio_job,
)


def run(db_path: str | Path | None = None, manifest_path: str | Path = "") -> dict[str, object]:
    manifest = _load_manifest(manifest_path)
    outputs = manifest.get("outputs", [])
    if not isinstance(outputs, list) or not outputs:
        raise ValueError("Registration manifest must include at least one output.")

    engine = create_db_engine(db_path)
    init_db(engine)
    factory = session_factory(engine)
    registered: list[dict[str, object]] = []
    try:
        with session_scope(factory) as session:
            for output in outputs:
                if not isinstance(output, dict):
                    raise ValueError("Each manifest output must be an object.")
                job_id = int(output.get("job_id") or 0)
                media_type = str(output.get("media_type") or "").strip()
                if media_type == "social_image":
                    job = register_social_image_job_output(
                        session,
                        job_id=job_id,
                        output_path=str(output.get("output_path") or ""),
                        title=str(output.get("title") or ""),
                        provider_job_id=str(output.get("provider_job_id") or ""),
                        output_url=str(output.get("output_url") or ""),
                        notes=str(output.get("notes") or ""),
                    )
                elif media_type == "video_art_board":
                    job = register_video_art_board_job_output(
                        session,
                        job_id=job_id,
                        output_path=str(output.get("output_path") or ""),
                        title=str(output.get("title") or ""),
                        provider_job_id=str(output.get("provider_job_id") or ""),
                        output_url=str(output.get("output_url") or ""),
                        notes=str(output.get("notes") or ""),
                    )
                elif media_type == "product_video":
                    job = register_video_job_output(
                        session,
                        job_id=job_id,
                        video_path=str(output.get("output_path") or output.get("video_path") or ""),
                        title=str(output.get("title") or ""),
                        poster_path=str(output.get("poster_path") or "") or None,
                        provider_job_id=str(output.get("provider_job_id") or ""),
                        output_url=str(output.get("output_url") or ""),
                        notes=str(output.get("notes") or ""),
                    )
                else:
                    raise ValueError("Output media_type must be social_image, video_art_board, or product_video.")
                registered.append(serialize_art_studio_job(job))
    finally:
        engine.dispose()
    return {"registered": registered, "count": len(registered)}


def _load_manifest(manifest_path: str | Path) -> dict[str, object]:
    path = Path(manifest_path)
    if not path.is_file():
        raise ValueError(f"Registration manifest not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Registration manifest must be a JSON object.")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Register generated Art Studio files against queued jobs.")
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    summary = run(db_path=args.db_path, manifest_path=args.manifest)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
