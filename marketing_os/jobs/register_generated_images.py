from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..db import create_db_engine, init_db, session_factory, session_scope
from ..services.content_briefs import register_generated_image_option, serialize_candidate


def run(db_path: str | Path | None = None, manifest_path: str | Path = "") -> dict[str, object]:
    manifest = _load_manifest(manifest_path)
    planned_item_id = int(manifest["planned_item_id"])
    images = manifest.get("images", [])
    if not isinstance(images, list) or not images:
        raise ValueError("Registration manifest must include at least one image.")

    engine = create_db_engine(db_path)
    init_db(engine)
    factory = session_factory(engine)
    registered: list[dict[str, object]] = []
    try:
        with session_scope(factory) as session:
            for image in images:
                if not isinstance(image, dict):
                    raise ValueError("Each manifest image must be an object.")
                candidate = register_generated_image_option(
                    session,
                    planned_item_id,
                    image_path=str(image.get("image_path") or ""),
                    option_number=int(image.get("option_number") or 0),
                    title=str(image.get("title") or ""),
                    best_for=str(image.get("best_for") or ""),
                    skill_request=_dict_value(image.get("skill_request")),
                    skill_check=_dict_value(image.get("skill_check")),
                    review_checklist=_string_list(image.get("review_checklist")),
                    provider=str(manifest.get("provider") or "codex_imagegen"),
                    notes=str(image.get("notes") or manifest.get("notes") or ""),
                )
                registered.append(serialize_candidate(candidate))
    finally:
        engine.dispose()
    return {"planned_item_id": planned_item_id, "registered": registered, "count": len(registered)}


def _load_manifest(manifest_path: str | Path) -> dict[str, object]:
    path = Path(manifest_path)
    if not path.is_file():
        raise ValueError(f"Registration manifest not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Registration manifest must be a JSON object.")
    if "planned_item_id" not in data:
        raise ValueError("Registration manifest must include planned_item_id.")
    return data


def _dict_value(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Register Codex-generated image files as Planning image options.")
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    summary = run(db_path=args.db_path, manifest_path=args.manifest)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
