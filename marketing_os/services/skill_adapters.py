from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class SkillContract:
    skill_name: str
    request: dict[str, object]
    check: dict[str, object]


def copywriter_contract(brief: dict[str, object], destination: str) -> SkillContract:
    """Map Marketing OS source facts into the reusable copywriter skill shape."""
    products = [str(item) for item in brief.get("products", []) if str(item).strip()]
    goals = [str(item) for item in brief.get("goals", []) if str(item).strip()]
    voice = _brand_voice(brief)
    request = {
        "destination": destination,
        "format": _copy_format(destination),
        "audience": str(brief.get("audience") or "collectors and gift buyers").strip(),
        "goal": ", ".join(goals) or "engagement",
        "brand_voice": voice,
        "details": _copy_details(brief),
        "must_include": products,
        "avoid": [str(item) for item in brief.get("avoid", []) if str(item).strip()],
        "review_level": "polished_draft",
        "source_facts": {
            "planned_item_id": brief.get("planned_item_id"),
            "calendar_date": brief.get("calendar_date"),
            "products": products,
            "product_facts": brief.get("product_facts", []),
            "performance_context": brief.get("performance_context", {}),
        },
    }
    return SkillContract("copywriter", request, _copywriter_check(request))


def image_creator_contracts(brief: dict[str, object], count: int = 3) -> list[SkillContract]:
    """Create 2-3 image-creator skill requests from a Marketing OS brief."""
    products = [str(item) for item in brief.get("products", []) if str(item).strip()]
    product_text = ", ".join(products) or "selected product"
    destinations = [str(item) for item in brief.get("destinations", []) if str(item).strip()]
    destination = destinations[0] if destinations else "social post"
    goals = [str(item) for item in brief.get("goals", []) if str(item).strip()]
    approved_ids = _approved_source_asset_ids(brief)
    references = _reference_images(brief, approved_ids)
    reference_roles = _reference_roles(references)
    concepts = [
        (
            "Product-In-Use Scene",
            "A clear product-forward social post.",
            f"Show {product_text} in a believable workspace or shelf scene tied to {brief.get('occasion') or 'an evergreen product story'}.",
            "Product in the foreground, simple background, eye-level crop, strong thumbnail readability.",
            "warm, handmade, playful, natural light",
        ),
        (
            "Giftable Moment",
            "Sales growth and buyer consideration.",
            f"Present {product_text} as a small gift idea for {brief.get('audience') or 'gift buyers'}.",
            "Tidy flat-lay or three-quarter tabletop scene with room for caption pairing, no baked-in text.",
            "bright, friendly, tangible, not overly polished",
        ),
        (
            "Collector Detail",
            "Engagement and comments from returning fans.",
            f"Feature the detail and personality of {product_text} for {destination}.",
            "Closer crop with one focal point, shallow depth of field, visible product details, safe edges.",
            "curious, crafted, conversational",
        ),
    ]
    contracts: list[SkillContract] = []
    for index, (title, best_for, scene, composition, mood) in enumerate(concepts[:count], start=1):
        request = {
            "destination": destination,
            "format": _image_format(destination),
            "audience": str(brief.get("audience") or "collectors and gift buyers").strip(),
            "goal": ", ".join(goals) or "engagement",
            "subject": product_text,
            "brand_style": "MattMadeMe handmade, playful, product-accurate, approachable",
            "details": json.dumps(
                {
                    "title": title,
                    "best_for": best_for,
                    "scene": scene,
                    "composition": composition,
                    "mood": mood,
                    "planned_item_id": brief.get("planned_item_id"),
                },
                indent=2,
            ),
            "reference_images": references,
            "reference_image_roles": reference_roles,
            "aspect_ratio": _aspect_ratio_for_destinations(destinations),
            "provider_path": "magnific-mcp",
            "fallback_provider_path": "built-in-image-edit",
            "model_preference": "Google Nano Banana 2",
            "output_path": f"outputs/graphics/planning/planned-item-{brief.get('planned_item_id')}/option-{index}.png",
            "must_include": products,
            "avoid": ["text overlays", "watermarks", "invented logos", "duplicate products", "distorted product details"],
            "option_number": index,
            "source_asset_ids": approved_ids,
        }
        contracts.append(SkillContract("image-creator", request, _image_creator_check(request)))
    return contracts


def image_option_from_contract(contract: SkillContract) -> dict[str, object]:
    request = dict(contract.request)
    details = _json_dict(str(request.get("details") or "{}"))
    source_ids = [int(value) for value in request.get("source_asset_ids", [])] if isinstance(request.get("source_asset_ids"), list) else []
    reference_images = request.get("reference_images")
    reference_roles = request.get("reference_image_roles")
    prompt = (
        "Create a realistic photographic scene for "
        f"{request.get('destination')} / {request.get('format')}.\n\n"
        f"Scene: {details.get('scene') or request.get('details')}\n"
        "Environment: simple real-world setting with minimal props and no clutter; surrounding objects must remain full-size so the duck reads as a miniature 2.5 inch collectible.\n"
        f"Mood and lighting: {details.get('mood') or 'natural, warm, clear'}; authentic photographic lighting with believable contact shadows.\n\n"
        "Place the exact product shown in @img1 in the foreground as the only product hero. "
        "Use @img2, @img3, and any additional references only as identity locks to preserve the product's exact appearance. "
        "Do not render additional copies from secondary references unless explicitly requested.\n\n"
        "The duck is locked reference content. Do not alter it. Do not smooth, repaint, recolor, reshape, resize, stylize, reinterpret, enhance, simplify, upscale-detail, or change the material. "
        "Preserve all visible 3D print layer lines, textures, colors, accessories, facial features, clothing details, props, text elements, and proportions exactly as shown in the reference images.\n\n"
        "Generate only the surrounding environment, lighting, reflections, shadows, depth of field, and atmospheric effects. "
        f"Composition: {details.get('composition') or 'single focal point'} Platform format/aspect ratio: {request.get('aspect_ratio')}.\n"
        f"Brand style: {request.get('brand_style')}.\n"
        "Output: realistic photograph, no illustration, no cartoon styling, no added text, no watermark.\n"
        f"Reference rule: {_reference_rule(reference_images)}"
    )
    return {
        "option_number": request.get("option_number"),
        "provider": f"image-creator-option-{request.get('option_number')}",
        "title": details.get("title") or "Image Option",
        "best_for": details.get("best_for") or "Generated image direction.",
        "provider_path": "Magnific MCP primary; built-in image edit fallback only if Magnific is unavailable",
        "model_preference": request.get("model_preference"),
        "aspect_ratio": request.get("aspect_ratio"),
        "source_asset_ids": source_ids,
        "reference_images": reference_images if isinstance(reference_images, list) else [],
        "reference_image_roles": reference_roles if isinstance(reference_roles, list) else [],
        "output_path": request.get("output_path"),
        "prompt": prompt,
        "skill_request": {**request, "prompt": prompt},
        "skill_check": contract.check,
        "review_checklist": [
            "Subject is obvious at thumbnail size.",
            "Product identity is preserved against the source or uploaded image.",
            "No unwanted text, watermark, logos, or irrelevant objects.",
            "Crop fits the planned destination.",
            "Keep in review until a human approves the final image.",
        ],
        "user_actions": [
            "Generate with Magnific MCP using Google Nano Banana 2 and the listed reference images.",
            "Download the finished file to the listed output path and register it with Marketing OS.",
            "Regenerate options if none fit.",
            "Upload your own image instead and review it in Assets.",
        ],
    }


def _copywriter_check(request: dict[str, object]) -> dict[str, object]:
    missing = [field for field in ["destination", "audience", "goal", "details"] if not str(request.get(field, "")).strip()]
    warnings = [field for field in ["brand_voice", "format"] if not str(request.get(field, "")).strip()]
    return {
        "status": "blocked" if missing else ("ready_with_assumptions" if warnings else "ready"),
        "missing_required": missing,
        "missing_recommended": warnings,
        "notes": ["Brief has the minimum fields needed for grounded copy generation."] if not missing else [],
    }


def _image_creator_check(request: dict[str, object]) -> dict[str, object]:
    missing = [field for field in ["destination", "subject"] if not str(request.get(field, "")).strip()]
    warnings = [field for field in ["audience", "goal", "format", "brand_style", "aspect_ratio"] if not str(request.get(field, "")).strip()]
    if request.get("provider_path") == "magnific-mcp" and not request.get("reference_images"):
        missing.append("reference_images")
    return {
        "status": "blocked" if missing else ("ready_with_assumptions" if warnings else "ready"),
        "missing_required": missing,
        "missing_recommended": warnings,
        "notes": ["Brief has the minimum fields needed to prepare an image prompt."] if not missing else [],
    }


def _copy_details(brief: dict[str, object]) -> str:
    pieces = [
        f"Products: {', '.join(str(item) for item in brief.get('products', []) if str(item).strip())}",
        f"Occasion: {brief.get('occasion') or 'evergreen'}",
        f"Promotion: {brief.get('promotion') or 'none'}",
        f"Notes: {brief.get('notes') or 'none'}",
    ]
    product_facts = brief.get("product_facts")
    if product_facts:
        pieces.append("Product facts: " + json.dumps(product_facts, sort_keys=True))
    return "\n".join(pieces)


def _brand_voice(brief: dict[str, object]) -> str:
    pillars = [str(item) for item in brief.get("voice_pillars", []) if str(item).strip()]
    phrases = [str(item) for item in brief.get("useful_phrases", []) if str(item).strip()]
    return "; ".join([*pillars[:4], *phrases[:2]]) or "warm, playful, concise, product-specific"


def _copy_format(destination: str) -> str:
    normalized = destination.lower()
    if "email" in normalized:
        return "newsletter section"
    if "blog" in normalized or "website" in normalized:
        return "blog article"
    if "etsy" in normalized:
        return "product/listing copy"
    return "social post"


def _image_format(destination: str) -> str:
    normalized = destination.lower()
    if "pinterest" in normalized:
        return "pin"
    if "blog" in normalized or "website" in normalized:
        return "feature image"
    if "email" in normalized:
        return "newsletter image"
    return "feed image"


def _aspect_ratio_for_destinations(destinations: list[str]) -> str:
    normalized = {destination.lower() for destination in destinations}
    if "instagram" in normalized:
        return "1:1 or 4:5"
    if "facebook" in normalized:
        return "4:5 or 1:1"
    if "pinterest" in normalized:
        return "2:3"
    if "blog post" in normalized or "website" in normalized:
        return "16:9 or 3:2"
    if "email" in normalized:
        return "16:9 or 1:1"
    return "1:1"


def _approved_source_asset_ids(brief: dict[str, object]) -> list[int]:
    values: list[int] = []
    raw_values = brief.get("approved_source_asset_ids")
    if isinstance(raw_values, list):
        for raw in raw_values:
            try:
                values.append(int(raw))
            except (TypeError, ValueError):
                continue
    return values


def _reference_images(brief: dict[str, object], approved_ids: list[int]) -> list[str]:
    source_assets = [item for item in brief.get("reference_source_assets") or brief.get("source_assets", []) if isinstance(item, dict)]
    references: list[str] = []
    for asset in source_assets:
        try:
            asset_id = int(asset.get("id"))
        except (TypeError, ValueError):
            continue
        if asset_id in approved_ids:
            path = str(asset.get("source_path") or "").strip()
            if path:
                references.append(path)
    return references


def _reference_roles(reference_images: list[str]) -> list[dict[str, str]]:
    roles: list[dict[str, str]] = []
    labels = [
        "primary visible product angle",
        "identity lock side/profile angle",
        "identity lock detail angle",
        "identity lock back/top angle",
    ]
    for index, path in enumerate(reference_images, start=1):
        label = labels[index - 1] if index <= len(labels) else "additional identity lock reference"
        roles.append({"role": f"@img{index}", "path": path, "purpose": label})
    return roles


def _reference_rule(reference_images: object) -> str:
    if isinstance(reference_images, list) and reference_images:
        return "Upload/pass every listed reference image to the generation tool; @img1 is the product hero and @img2+ are identity locks."
    return "Do not generate yet. No approved reference image is ready; the user must select or approve source photos before generation."


def _json_dict(value: str) -> dict[str, object]:
    try:
        data = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}
