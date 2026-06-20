from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


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
        "recommended_skill": _recommended_copy_skill(destination),
        "workflow": _copy_workflow(destination),
        "audience": str(brief.get("audience") or "collectors and gift buyers").strip(),
        "goal": ", ".join(goals) or "engagement",
        "brand_voice": voice,
        "details": _copy_details(brief),
        "social_angle": _social_angle(brief, destination),
        "content_pillar": _content_pillar(brief, destination),
        "creative_directive": _social_creative_directive(brief, destination),
        "story_thesis": _story_thesis(brief, destination),
        "proof_points": _proof_points(brief),
        "missing_proof": _missing_proof(brief),
        "story_moves": _story_moves(destination),
        "cta_type": _cta_type(goals),
        "must_include": products,
        "avoid": [
            *[str(item) for item in brief.get("avoid", []) if str(item).strip()],
            "Product-description-first body copy.",
            "Etsy listing summaries presented as social captions.",
            "A hook followed immediately by features and a CTA.",
            "Unsupported claims that the product is hot, viral, popular, or widely ordered.",
        ],
        "review_level": "polished_draft",
        "source_facts": {
            "planned_item_id": brief.get("planned_item_id"),
            "calendar_date": brief.get("calendar_date"),
            "products": products,
            "product_facts": brief.get("product_facts", []),
            "performance_context": brief.get("performance_context", {}),
        },
    }
    return SkillContract(str(request["recommended_skill"]), request, _copywriter_check(request))


def social_copy_workflow_contract(brief: dict[str, object], destination: str) -> dict[str, object]:
    """Build the scheduled automation handoff for strategy -> writing -> challenge."""
    contract = copywriter_contract(brief, destination)
    return {
        "workflow_name": "social_media_strategy_writing_challenge",
        "planned_item_id": brief.get("planned_item_id"),
        "destination": destination,
        "primary_skill": contract.skill_name,
        "steps": contract.request.get("workflow", []),
        "strategy_request": {
            "skill": "social-media-strategist",
            "input": {
                **contract.request,
                "task": "Choose platform strategy, content pillar, social angle, CTA type, story move, and variant plan. Do not write final copy.",
            },
        },
        "writing_request": {
            "skill": "social-media-copywriter",
            "input": {
                **contract.request,
                "task": "Write social copy from the strategy brief. Lead with a tiny story, surprise, opinion, scene, or community moment before product facts. Produce engagement, follower-building, and shop-click variants unless the plan says otherwise.",
            },
        },
        "challenge_request": {
            "skill": "social-media-copy-chief",
            "input": {
                **contract.request,
                "task": "Challenge the strategy and draft before human review. Reject drafts that read like hook + product description + CTA. Return ready_for_human_review, revise_before_review, or blocked.",
            },
        },
        "contract_check": contract.check,
    }


def social_media_art_director_contracts(brief: dict[str, object], count: int = 3) -> list[SkillContract]:
    """Create 2-3 social-media-art-director skill requests from a Marketing OS brief."""
    products = [str(item) for item in brief.get("products", []) if str(item).strip()]
    product_text = ", ".join(products) or "selected product"
    destinations = [str(item) for item in brief.get("destinations", []) if str(item).strip()]
    destination = destinations[0] if destinations else "social post"
    goals = [str(item) for item in brief.get("goals", []) if str(item).strip()]
    approved_ids = _approved_source_asset_ids(brief)
    references = _reference_images(brief, approved_ids)
    reference_roles = _reference_roles(references)
    copy_context = _copy_context_for_visuals(brief)
    visual_story = str(copy_context.get("visual_story") or "").strip()
    story_suffix = f" Match the post story: {visual_story}" if visual_story else ""
    concepts = [
        (
            "Product-In-Use Scene",
            "A clear product-forward social post.",
            f"Show {product_text} in a believable workspace or shelf scene tied to {brief.get('occasion') or 'an evergreen product story'}.{story_suffix}",
            "Product in the foreground, simple background, eye-level crop, strong thumbnail readability.",
            "warm, handmade, playful, natural light",
        ),
        (
            "Giftable Moment",
            "Sales growth and buyer consideration.",
            f"Present {product_text} as a small gift idea for {brief.get('audience') or 'gift buyers'}.{story_suffix}",
            "Tidy flat-lay or three-quarter tabletop scene with room for caption pairing, no baked-in text.",
            "bright, friendly, tangible, not overly polished",
        ),
        (
            "Collector Detail",
            "Engagement and comments from returning fans.",
            f"Feature the detail and personality of {product_text} for {destination}.{story_suffix}",
            "Closer crop with one focal point, shallow depth of field, visible product details, safe edges.",
            "curious, crafted, conversational",
        ),
    ]
    contracts: list[SkillContract] = []
    for index, (title, best_for, scene, composition, mood) in enumerate(concepts[:count], start=1):
        request = {
            "destination": destination,
            "platform": destination,
            "format": _image_format(destination),
            "audience": str(brief.get("audience") or "collectors and gift buyers").strip(),
            "goal": ", ".join(goals) or "engagement",
            "subject": product_text,
            "social_angle": title,
            "brand_style": "MattMadeMe handmade, playful, product-accurate, approachable",
            "details": json.dumps(
                {
                    "title": title,
                    "best_for": best_for,
                    "scene": scene,
                    "composition": composition,
                    "mood": mood,
                    "planned_item_id": brief.get("planned_item_id"),
                    "post_visual_context": copy_context,
                },
                indent=2,
            ),
            "post_visual_context": copy_context,
            "post_story_alignment": "Image must reinforce the generated copy's story move and should not feel like a generic product scene.",
            "reference_images": references,
            "reference_image_roles": reference_roles,
            "aspect_ratio": _aspect_ratio_for_destinations(destinations),
            "provider_path": "magnific-mcp",
            "fallback_provider_path": "built-in-image-edit",
            "model_preference": "Google Nano Banana 2",
            "output_path": _planning_output_path(brief.get("planned_item_id"), index),
            "must_include": products,
            "avoid": ["text overlays", "watermarks", "invented logos", "duplicate products", "distorted product details"],
            "option_number": index,
            "source_asset_ids": approved_ids,
        }
        contracts.append(SkillContract("social-media-art-director", request, _social_media_art_director_check(request)))
    return contracts


def image_option_from_contract(contract: SkillContract) -> dict[str, object]:
    request = dict(contract.request)
    details = _json_dict(str(request.get("details") or "{}"))
    copy_context = details.get("post_visual_context") if isinstance(details.get("post_visual_context"), dict) else {}
    story_alignment = _story_alignment_prompt(copy_context)
    source_ids = [int(value) for value in request.get("source_asset_ids", [])] if isinstance(request.get("source_asset_ids"), list) else []
    reference_images = request.get("reference_images")
    reference_roles = request.get("reference_image_roles")
    prompt = (
        "Create a realistic photographic scene for "
        f"{request.get('destination')} / {request.get('format')}.\n\n"
        f"{story_alignment}"
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
        "provider": f"social-media-art-director-option-{request.get('option_number')}",
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
            "Check the generated image against the post copy so the visual and caption feel like one idea.",
            "Download the finished file to the listed output path and register it with Marketing OS.",
            "Regenerate options if none fit.",
            "Upload your own image instead and review it in Assets.",
        ],
    }


def _copy_context_for_visuals(brief: dict[str, object]) -> dict[str, object]:
    raw = brief.get("reviewable_copy")
    if not isinstance(raw, dict) or not raw:
        return {}
    strategy = raw.get("social_strategy") if isinstance(raw.get("social_strategy"), dict) else {}
    hook = str(raw.get("hook") or "").strip()
    body = str(raw.get("body") or "").strip()
    cta = str(raw.get("cta") or "").strip()
    story_move = str(strategy.get("story_move") or strategy.get("social_angle") or "").strip()
    visual_story = " ".join(part for part in [hook, body] if part).strip()
    return {
        "copy_candidate_id": raw.get("candidate_id"),
        "hook": hook,
        "body": body,
        "cta": cta,
        "story_move": story_move,
        "visual_story": visual_story[:900],
    }


def _story_alignment_prompt(copy_context: dict[str, object]) -> str:
    if not copy_context:
        return ""
    parts = [
        "Post story to match:",
        f"Hook: {copy_context.get('hook')}",
        f"Body: {copy_context.get('body')}",
    ]
    if copy_context.get("story_move"):
        parts.append(f"Story move: {copy_context.get('story_move')}")
    parts.append(
        "Visual alignment rule: the scene, props, environment, and mood must support this story. "
        "Do not create a generic product image that could pair with any caption.\n\n"
    )
    return "\n".join(str(part) for part in parts if str(part).strip())


def _copywriter_check(request: dict[str, object]) -> dict[str, object]:
    missing = [field for field in ["destination", "audience", "goal", "details"] if not str(request.get(field, "")).strip()]
    warnings = [field for field in ["brand_voice", "format"] if not str(request.get(field, "")).strip()]
    return {
        "status": "blocked" if missing else ("ready_with_assumptions" if warnings else "ready"),
        "missing_required": missing,
        "missing_recommended": warnings,
        "notes": [
            f"Brief has the minimum fields needed for grounded copy generation via {request.get('recommended_skill') or 'copywriter'}."
        ]
        if not missing
        else [],
    }


def _social_media_art_director_check(request: dict[str, object]) -> dict[str, object]:
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


def _recommended_copy_skill(destination: str) -> str:
    normalized = destination.lower()
    if any(token in normalized for token in ["facebook", "instagram", "pinterest", "threads", "tiktok", "linkedin", "social"]):
        return "social-media-copywriter"
    return "copywriter"


def _copy_workflow(destination: str) -> list[dict[str, str]]:
    if _recommended_copy_skill(destination) != "social-media-copywriter":
        return [{"step": "write", "skill": "copywriter"}]
    return [
        {"step": "strategy", "skill": "social-media-strategist"},
        {"step": "writing", "skill": "social-media-copywriter"},
        {"step": "challenge", "skill": "social-media-copy-chief"},
    ]


def _social_angle(brief: dict[str, object], destination: str) -> str:
    goals = " ".join(str(item).lower() for item in brief.get("goals", []) if str(item).strip())
    occasion = str(brief.get("occasion") or "").strip()
    audience = str(brief.get("audience") or "").strip().lower()
    if "cruise" in goals or "cruise" in audience:
        return "community_prompt"
    if "flock" in goals or "collect" in goals:
        return "collectible"
    if "gift" in goals or "gift" in audience:
        return "giftable"
    if "personality" in goals or "duck personality" in goals:
        return "personality"
    if "maker" in goals or "process" in goals:
        return "maker_process"
    if "shop" in goals or "traffic" in goals or "visit" in goals:
        return "shop_action"
    if "engagement" in goals or "comment" in goals or "conversation" in goals:
        return "community_prompt"
    if occasion and occasion.lower() != "evergreen":
        return "occasion"
    if _recommended_copy_skill(destination) == "social-media-copywriter":
        return "personality"
    return ""


def _social_creative_directive(brief: dict[str, object], destination: str) -> str:
    products = [str(item) for item in brief.get("products", []) if str(item).strip()]
    product_text = products[0] if products else "the featured duck"
    occasion = str(brief.get("occasion") or "").strip()
    audience = str(brief.get("audience") or "").strip()
    destination_name = destination.strip() or "social"
    return (
        f"For {destination_name}, make {product_text} feel like a character in a tiny moment, not an item being described. "
        "Use one specific scene, joke, tension, question, or collector/community observation before naming product features. "
        f"Tie the moment to {occasion or audience or 'the planned audience'} when useful, then use source facts only when they add proof, search value, or attention value."
    )


def _story_thesis(brief: dict[str, object], destination: str) -> str:
    products = [str(item) for item in brief.get("products", []) if str(item).strip()]
    product_text = products[0] if products else "the featured product"
    audience = str(brief.get("audience") or "").strip()
    proof_points = _proof_points(brief)
    if proof_points:
        return (
            f"Tell why {product_text} is resonating with {audience or 'the intended audience'} using the supplied proof, "
            "then use product details only as support."
        )
    return (
        f"Tell why {product_text} matters to {audience or 'the intended audience'} without claiming demand; "
        "ask for proof if popularity, order volume, or customer response would strengthen the story."
    )


def _proof_points(brief: dict[str, object]) -> list[str]:
    points: list[str] = []
    for fact in brief.get("product_facts", []):
        if not isinstance(fact, dict):
            continue
        name = str(fact.get("name") or "Product").strip()
        note = str(fact.get("sales_momentum_note") or "").strip()
        if note:
            points.append(f"{name} listing/source note: {note[:500]}")
        reviews = fact.get("etsy_reviews")
        if isinstance(reviews, list):
            for review in reviews[:3]:
                if not isinstance(review, dict):
                    continue
                review_text = str(review.get("review") or "").strip()
                rating = review.get("rating")
                if review_text:
                    prefix = f"{name} Etsy review"
                    if rating:
                        prefix += f" ({rating}/5)"
                    points.append(f"{prefix}: {review_text[:240]}")
    performance = brief.get("performance_context")
    if isinstance(performance, dict):
        for key in ("winning_patterns", "top_products", "top_ctas"):
            value = performance.get(key)
            if value:
                points.append(f"Performance context {key}: {value}")
    notes = str(brief.get("notes") or "").strip()
    if any(token in notes.lower() for token in ["order", "sold", "requested", "hot", "took off", "popular"]):
        points.append(f"Planning note demand signal: {notes}")
    return points[:5]


def _missing_proof(brief: dict[str, object]) -> list[str]:
    notes = str(brief.get("notes") or "").lower()
    product_notes = " ".join(
        str(fact.get("sales_momentum_note") or "").lower()
        for fact in brief.get("product_facts", [])
        if isinstance(fact, dict)
    )
    source_text = f"{notes} {product_notes}"
    missing: list[str] = []
    if any(token in source_text for token in ["hot", "took off", "popular", "storm", "demand"]):
        missing.append("[MATT_TO_CONFIRM: order count or recent demand signal]")
        missing.append("[MATT_TO_CONFIRM: who is buying or requesting this product]")
    if "appreciat" in source_text or "thank" in source_text:
        missing.append("[MATT_TO_CONFIRM: real recipient/customer group if known]")
    return missing


def _story_moves(destination: str) -> list[str]:
    normalized = destination.lower()
    if "pinterest" in normalized:
        return [
            "Use proof-led product story when source facts show demand, gifting behavior, or a specific audience trend.",
            "Start with the search occasion or gift problem, then add one charming detail.",
            "Make the title useful, but make the description feel like a small idea someone would save.",
            "Use product facts as keywords, not as a catalog paragraph.",
        ]
    if "instagram" in normalized:
        return [
            "Use proof-led product story when source facts show demand, customer group, or why the product is resonating.",
            "Add a visual caption payoff that gives the image personality.",
            "Use a tiny imagined scene, inner monologue, or collector detail.",
            "Keep product facts secondary to the feeling someone would save or share.",
        ]
    if "facebook" in normalized:
        return [
            "Use proof-led product story when source facts show what happened, who responded, and why it matters.",
            "Open a conversation around the duck's tiny job, personality, or where it would show up.",
            "Use a small story or playful opinion before any feature list.",
            "Make the CTA feel like a reply prompt, not a shop instruction, unless shop traffic is the only goal.",
        ]
    return [
        "Choose one human moment before product facts.",
        "Use only the product details needed to ground the story.",
        "Avoid listing features in the same order as the source description.",
    ]


def _content_pillar(brief: dict[str, object], destination: str) -> str:
    goals = " ".join(str(item).lower() for item in brief.get("goals", []) if str(item).strip())
    audience = str(brief.get("audience") or "").strip().lower()
    occasion = str(brief.get("occasion") or "").strip().lower()
    promotion = str(brief.get("promotion") or "").strip().lower()
    products = " ".join(str(item).lower() for item in brief.get("products", []) if str(item).strip())
    facts = json.dumps(brief.get("product_facts", []), sort_keys=True).lower()
    source_text = " ".join([goals, audience, occasion, promotion, products, facts])
    if _recommended_copy_skill(destination) != "social-media-copywriter":
        return ""
    if any(token in source_text for token in ["cruise", "room steward", "ship", "duck hiding", "duck exchange"]):
        return "Cruise And Sharing"
    if any(token in source_text for token in ["state", "occupation", "career", "series", "collect", "flock"]):
        return "Flock Building"
    if any(token in source_text for token in ["maker", "process", "behind the scenes", "design sketch", "print video"]):
        return "Maker Process"
    if "gift" in source_text:
        return "Duck Personality"
    if "personality" in goals or "follow" in goals:
        return "Duck Personality"
    if "shop" in goals or "sales" in goals or "traffic" in goals:
        return "Flock Building"
    if occasion and occasion not in {"evergreen", "none", "n/a"}:
        return "Cruise And Sharing" if "cruise" in occasion else "Duck Personality"
    return "Cruise And Sharing"


def _cta_type(goals: list[str]) -> str:
    normalized = " ".join(goal.lower() for goal in goals)
    if any(token in normalized for token in ["shop", "traffic", "visit", "click"]):
        return "shop"
    if "follow" in normalized or "follower" in normalized:
        return "follow"
    if any(token in normalized for token in ["engagement", "comment", "reply", "community", "conversation", "cruise"]):
        return "comment"
    if any(token in normalized for token in ["flock", "collect", "gift", "sales"]):
        return "shop"
    return "comment"


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


def _planning_output_path(planned_item_id: object, option_number: int) -> str:
    root = Path(os.environ.get("MARKETING_OS_PLANNING_UPLOAD_ROOT", "outputs/graphics/planning/uploads"))
    return (root / f"planned-item-{planned_item_id}" / f"option-{option_number}.png").as_posix()


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
