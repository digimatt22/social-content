#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def _handoff_steps(provider_path: str) -> list[str]:
    if provider_path == "built-in":
        return [
            "Use the built-in image editing fallback with the prompt, aspect ratio, and any supplied reference images.",
            "Review the image for destination fit, brand fit, and unwanted text/artifacts.",
            "Keep the output reviewable before production use.",
        ]
    return [
        "Confirm Magnific/Freepik MCP tools are available and the user is logged in.",
        "Upload or select every reference image and assign @img roles.",
        "Generate with Google Nano Banana 2 when available.",
        "Wait for completion, download the output file locally, and show it for product-accuracy review.",
        "Keep the output in needs_review until approved.",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a reusable image-generation handoff manifest.")
    parser.add_argument("--product-slug", required=True)
    parser.add_argument("--destination", default="")
    parser.add_argument("--target-format", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--source", action="append", default=[], help="Source image path. Repeat for multiple angles.")
    parser.add_argument("--provider-path", choices=["built-in", "magnific-mcp"], default="magnific-mcp")
    parser.add_argument("--provider", default="")
    parser.add_argument("--model", default="Google Nano Banana 2")
    parser.add_argument("--aspect-ratio", default="1:1")
    parser.add_argument("--resolution", default="2K")
    parser.add_argument("--output", default="", help="Optional manifest output path.")
    args = parser.parse_args()

    provider = args.provider or ("magnific" if args.provider_path == "magnific-mcp" else "built-in-image-generation")
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "product_slug": args.product_slug,
        "destination": args.destination,
        "target_format": args.target_format,
        "provider_path": args.provider_path,
        "provider": provider,
        "model": args.model,
        "aspect_ratio": args.aspect_ratio,
        "resolution": args.resolution,
        "review_state": "needs_review",
        "source_images": [Path(path).expanduser().as_posix() for path in args.source],
        "primary_reference": Path(args.source[0]).expanduser().as_posix() if args.source else "",
        "reference_image_roles": [
            {"role": f"@img{index}", "path": Path(path).expanduser().as_posix()}
            for index, path in enumerate(args.source, start=1)
        ],
        "prompt": args.prompt,
        "product_preservation_rules": [
            "Preserve the exact duck silhouette, colors, texture, accessories, facial features, and proportions.",
            "Use secondary images only as identity locks unless explicitly asked to render multiple products.",
            "Keep the duck miniature inside a full-size realistic environment.",
            "Do not smooth, repaint, recolor, reshape, stylize, or reinterpret the duck.",
            "Generated output requires human product-accuracy review before approval.",
        ],
        "handoff_steps": _handoff_steps(args.provider_path),
    }

    text = json.dumps(manifest, indent=2, sort_keys=True)
    if args.output:
        output = Path(args.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
