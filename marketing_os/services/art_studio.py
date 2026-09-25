from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db_models import AssetRecord, CreativeGenerationJobRecord, ProductRecord, ProductSalesRecord
from ..magnific_api import magnific_api_configured
from ..phase3 import json_list
from ..phase4 import refresh_asset_file_state
from .durable_jobs import enqueue_job


SOURCE_ASSET_TYPES = {"source photo", "Etsy product photo", "edited photo", "external listing image"}
SOCIAL_IMAGE_ASSET_TYPE = "generated social image"
POST_IMAGE_ASSET_TYPE = "generated post image"
VIDEO_ART_BOARD_ASSET_TYPE = "generated video art board"
SOCIAL_IMAGE_ROLE = "social worthy image"
VIDEO_ART_BOARD_ROLE = "video art board"
VIDEO_OPENING_CARD_ROLE = "video opening card"
VIDEO_ENDING_CARD_ROLE = "video ending card"
VIDEO_ASSET_TYPE = "generated product video"
VIDEO_ASSET_ROLE = "social video option"
SOCIAL_JOB_FORMAT = "art_studio_social_image"
DEFAULT_SOCIAL_IMAGE_PLATFORM = "ig_feed"
DEFAULT_SOCIAL_IMAGE_ASPECT_RATIO = "1:1"
# Canonical platform -> aspect for Art Studio / Products social-image generation.
# Pinterest is generator frame only; Brand Lab owns pin posting (no Pinterest publish).
SOCIAL_IMAGE_PLATFORM_ASPECT_RATIOS: dict[str, str] = {
    "ig_feed": "1:1",
    "fb_feed": "1:1",
    "ig_portrait": "4:5",
    "fb_portrait": "4:5",
    "stories": "9:16",
    "reels": "9:16",
    "tiktok": "9:16",
    "x": "16:9",
    "landscape_link": "16:9",
    "pinterest": "2:3",
}
SOCIAL_IMAGE_PLATFORM_LABELS: dict[str, str] = {
    "ig_feed": "IG Feed",
    "fb_feed": "FB Feed",
    "ig_portrait": "IG Portrait",
    "fb_portrait": "FB Portrait",
    "stories": "Stories",
    "reels": "Reels",
    "tiktok": "TikTok",
    "x": "X",
    "landscape_link": "Landscape link",
    "pinterest": "Pinterest",
}
SOCIAL_IMAGE_ASPECT_FORMAT_BLURBS: dict[str, str] = {
    "1:1": "1:1 square social image",
    "4:5": "4:5 portrait social image",
    "9:16": "9:16 vertical stories/reels social image",
    "16:9": "16:9 landscape social image",
    "2:3": "2:3 Pinterest pin social image",
}
VIDEO_REQUEST_FORMAT = "art_studio_product_video_request"
VIDEO_ART_BOARD_JOB_FORMAT = "art_studio_video_art_board"
VIDEO_JOB_FORMAT = "art_studio_product_video"
DEFAULT_VIDEO_NEGATIVE_PROMPT = (
    "walking, riding by itself, flapping, talking, blinking, changing expression, living creature, "
    "animated face, transforming, changed accessories, changed material, resized product, distorted product, "
    "extra yellow pieces, extra parts, extra products, duplicate products, plain product-photo opening card, "
    "boring fade-in from listing photo, blurry, low quality, watermark, text"
)
DEFAULT_VIDEO_AUDIO_DIRECTION = (
    "Subtle realistic ambient sound matched to the scene, such as soft room tone, distant outdoor ambience, "
    "light surface sounds, or gentle environmental texture. No music and no voices unless the user explicitly asks."
)
DEFAULT_VIDEO_VOICE_TONE = "serious and neutral"
DEFAULT_VIDEO_STYLE_TEMPLATE = (
    "Photorealistic high-detail product video, cinematic natural-light look, clean social frame, "
    "{aspect_ratio} aspect ratio, no on-screen text, no logos, no watermarks, no product duplication."
)
DEFAULT_VIDEO_TAIL_RULE = (
    "End with the duck still physically unchanged in the same product-safe scene, letting the selected camera, "
    "light, focus, or environmental motion settle into a clean final frame. Do not invent a new pose, action, "
    "expression, accessory, material, duplicate product, or living-character behavior."
)
FANTASTICAL_MOTION_TERMS = {
    "walk",
    "walking",
    "runs",
    "running",
    "ride",
    "rides",
    "riding",
    "drives",
    "driving",
    "flap",
    "flapping",
    "talk",
    "talks",
    "talking",
    "speak",
    "speaking",
    "blink",
    "blinking",
    "winks",
    "winking",
    "dance",
    "dancing",
    "flies",
    "flying",
    "transforms",
    "transforming",
}

VIDEO_EFFECT_STYLES = {
    "focus_pull": {
        "name": "Focus pull",
        "ui_description": "Rack focus from foreground detail to the duck while the camera stays nearly locked.",
        "risk": "low",
        "base_score": 92,
        "suggested_model": "kling-25",
        "reference_strategy": "start_frame_only",
        "keywords": {"desk", "shelf", "display", "detail", "macro", "collector", "gift", "picnic"},
        "value": "Safest product-preserving motion. It creates visual change through depth of field while the duck and scene stay locked.",
        "ending_card_required": False,
        "opening_card_brief": (
            "Compose a realistic product-in-scene frame with clear foreground, midground, and background depth. "
            "Keep the duck unchanged and placed in the final scene; let a nearby prop or foreground texture carry the initial attention."
        ),
        "ending_card_brief": (
            "Use the opening card as the composition reference. Keep the same product placement, scene layout, props, background, and lighting. "
            "Change only the focus plane so the duck or one important product detail becomes the crisp final point of attention."
        ),
        "video_motion_prompt": (
            "A slow rack focus moves from foreground or background texture to the unchanged duck. Camera is almost locked with only a tiny push-in."
        ),
        "cinematic_motion": (
            "Use a nearly locked macro camera with a tiny push-in. Let depth of field and foreground texture create the movement while the duck stays rigid."
        ),
    },
    "dolly_in": {
        "name": "Dolly In",
        "ui_description": "Smooth cinematic push straight toward the duck with stable framing and natural parallax.",
        "risk": "low",
        "base_score": 88,
        "suggested_model": "kling-25",
        "reference_strategy": "start_frame_only",
        "keywords": {"hero", "close", "detail", "display", "shelf", "counter", "product", "ad"},
        "value": "Good for social awareness because it feels deliberate and premium while keeping the product centered and stable.",
        "ending_card_required": False,
        "opening_card_brief": (
            "Create a clear product-hero frame with enough surrounding depth for a smooth forward camera move. "
            "Keep the duck centered, readable, and unchanged in the scene."
        ),
        "ending_card_brief": (
            "Usually not needed. If later required, keep the same scene and product lock, changing only the final camera distance."
        ),
        "video_motion_prompt": (
            "Smooth cinematic dolly-in camera move, physically pushing straight forward toward the duck on-axis, "
            "tightening the framing from wide to closer while keeping the duck centered and stable, with natural parallax and no zoom."
        ),
        "cinematic_motion": (
            "Camera pushes forward smoothly on-axis toward the unchanged duck. Keep framing stable, movement clean, and parallax natural with no zoom."
        ),
    },
    "dolly_out": {
        "name": "Dolly Out",
        "ui_description": "Clean backward camera move that reveals more scene while the duck stays locked and centered.",
        "risk": "low",
        "base_score": 74,
        "suggested_model": "kling-25",
        "reference_strategy": "start_frame_only",
        "keywords": {"reveal", "space", "shelf", "window", "counter", "scene", "hero"},
        "value": "Useful when the scene itself carries story value and you want to reveal context without changing the product.",
        "ending_card_required": False,
        "opening_card_brief": (
            "Start in a closer hero composition with the duck already readable and enough surrounding environment to reveal as the camera pulls back."
        ),
        "ending_card_brief": (
            "Usually not needed. If later required, keep the same scene and product lock, changing only the final camera distance."
        ),
        "video_motion_prompt": (
            "Smooth cinematic dolly-out camera move, physically pulling straight backward away from the duck on-axis, "
            "widening the framing to reveal more of the environment while keeping the duck centered and stable, with natural parallax and no zoom."
        ),
        "cinematic_motion": (
            "Camera pulls back smoothly from the unchanged duck, widening the scene with natural parallax while keeping the duck centered and steady."
        ),
    },
    "living_painting": {
        "name": "Living painting",
        "ui_description": "Micro movement in light and atmosphere while the duck remains completely still.",
        "risk": "low",
        "base_score": 86,
        "suggested_model": "kling-25",
        "reference_strategy": "start_frame_only",
        "keywords": {"art", "print", "paint", "seasonal", "holiday", "picnic", "patriotic", "collector"},
        "value": "Good for charming seasonal posts because the environment feels alive without animating the product.",
        "ending_card_required": False,
        "opening_card_brief": (
            "Create a polished still-life scene with the unchanged duck as a miniature collectible. Build rich light, texture, and small environmental details."
        ),
        "ending_card_brief": (
            "Use the opening card as the composition reference. Preserve layout and product placement. Shift only ambient light, tiny highlights, shadows, "
            "or background texture so the frame feels like the same still life has gently breathed."
        ),
        "video_motion_prompt": (
            "Subtle living-painting motion: light shimmer, soft shadow movement, background texture movement, tiny sparkle or fabric movement. The duck stays still."
        ),
        "cinematic_motion": (
            "Keep the camera calm and let highlights, shadows, fabric, sparkle, steam, or background texture breathe gently around the unchanged product."
        ),
    },
    "time_freeze_timelapse": {
        "name": "Time-freeze timelapse",
        "ui_description": "Time passes around a frozen duck through light, shadow, and environmental change.",
        "risk": "medium",
        "base_score": 82,
        "suggested_model": "bytedance-seedance-pro-2.0",
        "reference_strategy": "start_frame_only",
        "keywords": {"holiday", "seasonal", "sunset", "morning", "night", "party", "picnic", "porch", "window"},
        "value": "Useful when the scene can show time passing around a frozen product, creating story without character motion.",
        "ending_card_required": False,
        "opening_card_brief": (
            "Create the first moment of a realistic scene with the unchanged duck locked in place. Include environmental cues that can evolve over time."
        ),
        "ending_card_brief": (
            "Use the opening card as the composition reference. Keep product, props, staging surface or plane, and camera angle consistent. "
            "Change only time-of-day cues, light direction softness, background activity blur, condensation, shadows, or small celebratory atmosphere."
        ),
        "video_motion_prompt": (
            "A locked-off timelapse happens around the still duck: shifting light, moving shadows, soft background motion, and ambient atmosphere. Product remains frozen."
        ),
        "cinematic_motion": (
            "Hold product placement locked while time passes in the scene through light shifts, shadow travel, condensation, background blur, or atmospheric details."
        ),
    },
    "bullet_time": {
        "name": "Bullet time",
        "ui_description": "Small orbit around a frozen duck with controlled parallax.",
        "risk": "medium-high",
        "base_score": 72,
        "suggested_model": "kling-25",
        "reference_strategy": "start_frame_only",
        "keywords": {"hero", "dramatic", "collector", "limited", "patriotic", "display", "shelf"},
        "value": "Adds premium energy for hero products, but should be used sparingly because camera orbit increases product-drift risk.",
        "ending_card_required": False,
        "opening_card_brief": (
            "Create a strong hero first frame with the duck unchanged and the scene readable. Leave enough side/background context for a small camera orbit."
        ),
        "ending_card_brief": (
            "Use the opening card and product references as identity locks. Keep the exact same scene, props, lighting, and product scale. "
            "Change only the camera position by roughly 15 to 25 degrees around the static duck, as if the camera moved while time stayed frozen."
        ),
        "video_motion_prompt": (
            "A slow bullet-time orbit around the frozen duck, no product motion. Background parallax changes slightly while the object remains rigid and unchanged."
        ),
        "cinematic_motion": (
            "Move the camera in a small controlled orbit with gentle parallax. Keep the duck rigid, grounded, and identical across the camera move."
        ),
    },
    "vertigo_effect": {
        "name": "Vertigo Zoom",
        "ui_description": "Sharp push-pull perspective effect while the duck stays the same size and locked in place.",
        "risk": "medium",
        "base_score": 76,
        "suggested_model": "kling-25",
        "reference_strategy": "start_frame_only",
        "keywords": {"dramatic", "limited", "announcement", "collector", "shelf", "display"},
        "value": "Creates a distinctive social hook through perspective change while keeping product size and identity stable.",
        "ending_card_required": False,
        "opening_card_brief": (
            "Create a realistic scene with strong depth behind the unchanged duck. Keep the duck centered enough that its on-screen size can remain stable."
        ),
        "ending_card_brief": (
            "Use the opening card as the composition reference. Keep the duck the same on-screen size, shape, color, and placement. "
            "Change only background perspective/compression so the background feels closer or farther for a dolly-zoom finish."
        ),
        "video_motion_prompt": (
            "The camera performs a single, fast crash zoom toward the duck followed by one sharp pullback to the original wide framing, "
            "while the duck stays the same size, perfectly still, and locked in place as the background perspective compresses and releases."
        ),
        "cinematic_motion": (
            "Perform one sharp push-pull vertigo zoom while keeping the duck identical in size and position and allowing only the background perspective to distort."
        ),
    },
    "hyperlapse_sweep": {
        "name": "Hyperlapse sweep",
        "ui_description": "Energetic environment sweep around a stationary duck.",
        "risk": "medium-high",
        "base_score": 68,
        "suggested_model": "bytedance-seedance-pro-2.0",
        "reference_strategy": "start_frame_only",
        "keywords": {"road", "highway", "vehicle", "bike", "dashboard", "shelf", "market", "fair", "parade"},
        "value": "Best when the environment should feel energetic while the product remains a displayed object, not an actor.",
        "ending_card_required": False,
        "opening_card_brief": (
            "Create a product-in-scene first frame with a clear path for camera travel through the environment. Keep the duck unchanged and physically grounded."
        ),
        "ending_card_brief": (
            "Use the opening card as the scene reference. Keep product identity, scale, and scene logic consistent. "
            "Move the camera viewpoint along the same path or arc and introduce only environmental streaks, passing background, or light trails."
        ),
        "video_motion_prompt": (
            "A short hyperlapse camera sweep through the scene around the stationary duck, with background motion and light streaks only. The duck does not travel by itself."
        ),
        "cinematic_motion": (
            "Let the camera sweep through the surrounding environment with passing background streaks or light trails while the duck remains a displayed object."
        ),
    },
    "social_media_ad": {
        "name": "Social Media Ad",
        "ui_description": "Scroll-stopping 9:16 ad motion with punchier pacing and optional native voiceover.",
        "risk": "medium-high",
        "base_score": 66,
        "suggested_model": "bytedance-seedance-pro-2.0",
        "reference_strategy": "identity_refs_plus_start_frame",
        "keywords": {"ad", "social", "promo", "launch", "campaign", "awareness", "scroll"},
        "value": "Best when the goal is awareness and follower growth with a more overt ad cadence while still protecting the product.",
        "ending_card_required": False,
        "opening_card_brief": (
            "Create a high-clarity hero frame that reads instantly in a 9:16 feed. Keep the duck large enough in frame that identity remains obvious even with punchier pacing."
        ),
        "ending_card_brief": (
            "Usually not needed. If later required, keep the product locked and change only the final crop emphasis or camera distance."
        ),
        "video_motion_prompt": (
            "Create a scroll-stopping 9:16 social media ad with clean, realistic camera motion and one or two punchier framing changes. "
            "Keep the duck's shape, colors, and details perfectly accurate at every moment."
        ),
        "cinematic_motion": (
            "Use one clear hero move plus one small emphasis change. Keep cuts or reframing clean and realistic while the duck stays exact."
        ),
    },
}

VIDEO_TEMPLATE_ORDER = (
    "focus_pull",
    "dolly_in",
    "dolly_out",
    "vertigo_effect",
    "social_media_ad",
)


def default_video_models(duration_seconds: int) -> dict[str, str]:
    if duration_seconds > 8:
        return {
            "draft": "bytedance-seedance-fast-2.0",
            "final": "bytedance-seedance-pro-2.0",
        }
    return {
        "draft": "kling-25",
        "final": "kling-25",
    }


def requested_voice_direction(voice_script: str = "", voice_tone: str = "") -> str:
    script = voice_script.strip()
    if not script:
        return ""
    tone = voice_tone.strip() or DEFAULT_VIDEO_VOICE_TONE
    return (
        f'Add a short {tone} voice saying "{script}". '
        "Keep it clean, believable, and ad-ready. No extra dialogue, singing, or character acting."
    )


def video_prompt_defaults(aspect_ratio: str) -> dict[str, str]:
    return {
        "audio_direction": DEFAULT_VIDEO_AUDIO_DIRECTION,
        "style_direction": DEFAULT_VIDEO_STYLE_TEMPLATE.format(aspect_ratio=aspect_ratio),
        "tail_rule": DEFAULT_VIDEO_TAIL_RULE,
    }


def video_template_options() -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    for slug in VIDEO_TEMPLATE_ORDER:
        effect = VIDEO_EFFECT_STYLES[slug]
        options.append(
            {
                "slug": slug,
                "name": str(effect["name"]),
                "description": str(effect.get("ui_description") or effect.get("value") or ""),
                "suggested_model": str(effect.get("suggested_model") or ""),
            }
        )
    return options


@dataclass(frozen=True)
class ArtStudioProduct:
    product: ProductRecord
    reference_assets: list[AssetRecord]
    video_start_assets: list[AssetRecord]
    approved_reference_count: int
    default_reference_count: int
    generated_social_count: int
    approved_generated_social_count: int
    sales_quantity: int
    queue_score: int
    output_dir: str
    image_handoff: str
    video_handoff: str
    social_jobs: list[CreativeGenerationJobRecord]
    art_board_jobs: list[CreativeGenerationJobRecord]
    video_jobs: list[CreativeGenerationJobRecord]


@dataclass(frozen=True)
class ArtStudioVideoRequest:
    request_job: CreativeGenerationJobRecord
    product: ProductRecord
    reference_assets: list[AssetRecord]
    opening_job: CreativeGenerationJobRecord | None
    ending_job: CreativeGenerationJobRecord | None
    video_job: CreativeGenerationJobRecord | None
    status: str
    status_label: str
    can_approve: bool
    can_cancel: bool
    details: dict[str, object]


def art_studio_queue(session: Session, limit: int = 24) -> list[ArtStudioProduct]:
    refresh_asset_file_state(session)
    products = list(session.scalars(select(ProductRecord).order_by(ProductRecord.name)))
    assets_by_product = _assets_by_product(session)
    jobs_by_product = _jobs_by_product(session)
    sales_by_product = _sales_by_product(session)
    rows: list[ArtStudioProduct] = []
    for product in products:
        assets = assets_by_product.get(product.id, [])
        references = [asset for asset in assets if _can_be_reference(asset)]
        approved_references = [asset for asset in references if _is_approved_reference(asset)]
        default_references = [asset for asset in references if asset.default_reference]
        generated = [asset for asset in assets if asset.asset_type == SOCIAL_IMAGE_ASSET_TYPE]
        approved_generated = [asset for asset in generated if asset.review_state == "approved"]
        video_start_assets = _video_start_assets(assets)
        sales_quantity = sales_by_product.get(product.id, 0)
        queue_score = _queue_score(
            approved_reference_count=len(approved_references),
            default_reference_count=len(default_references),
            sales_quantity=sales_quantity,
            approved_generated_count=len(approved_generated),
            generated_count=len(generated),
        )
        selected_references = default_references or approved_references or references[:3]
        output_dir = f"outputs/graphics/social-worthy/{slugify(product.name)}"
        rows.append(
            ArtStudioProduct(
                product=product,
                reference_assets=selected_references[:4],
                video_start_assets=video_start_assets[:4],
                approved_reference_count=len(approved_references),
                default_reference_count=len(default_references),
                generated_social_count=len(generated),
                approved_generated_social_count=len(approved_generated),
                sales_quantity=sales_quantity,
                queue_score=queue_score,
                output_dir=output_dir,
                image_handoff=social_image_handoff(product, selected_references[:4], output_dir),
                video_handoff=video_pilot_handoff(product, (video_start_assets or selected_references)[:3]),
                social_jobs=[
                    job for job in jobs_by_product.get(product.id, []) if job.target_format == SOCIAL_JOB_FORMAT
                ],
                art_board_jobs=[
                    job for job in jobs_by_product.get(product.id, []) if job.target_format == VIDEO_ART_BOARD_JOB_FORMAT
                ],
                video_jobs=[
                    job for job in jobs_by_product.get(product.id, []) if job.target_format == VIDEO_JOB_FORMAT
                ],
            )
        )
    return sorted(rows, key=lambda row: (row.queue_score, row.product.name.lower()), reverse=True)[:limit]


def art_studio_video_requests(session: Session, limit: int = 50) -> list[ArtStudioVideoRequest]:
    refresh_asset_file_state(session)
    jobs = list(
        session.scalars(
            select(CreativeGenerationJobRecord)
            .where(CreativeGenerationJobRecord.target_format.in_([VIDEO_REQUEST_FORMAT, VIDEO_ART_BOARD_JOB_FORMAT, VIDEO_JOB_FORMAT]))
            .order_by(CreativeGenerationJobRecord.created_at.desc(), CreativeGenerationJobRecord.id.desc())
        )
    )
    card_jobs_by_request: dict[int, list[CreativeGenerationJobRecord]] = {}
    video_jobs_by_request: dict[int, list[CreativeGenerationJobRecord]] = {}
    request_jobs: list[CreativeGenerationJobRecord] = []
    for job in jobs:
        metadata = _json_dict(job.response_metadata_json)
        parent_id = _int_value(metadata.get("video_request_job_id"))
        if job.target_format == VIDEO_REQUEST_FORMAT:
            request_jobs.append(job)
        elif job.target_format == VIDEO_ART_BOARD_JOB_FORMAT and parent_id is not None:
            card_jobs_by_request.setdefault(parent_id, []).append(job)
        elif job.target_format == VIDEO_JOB_FORMAT and parent_id is not None:
            video_jobs_by_request.setdefault(parent_id, []).append(job)

    rows: list[ArtStudioVideoRequest] = []
    for request_job in request_jobs[:limit]:
        metadata = _json_dict(request_job.response_metadata_json)
        product_id = _job_product_id(request_job) or _int_value(metadata.get("product_id"))
        product = session.get(ProductRecord, product_id) if product_id is not None else None
        if product is None:
            continue
        references = _assets_for_ids(session, metadata.get("reference_asset_ids"), product.id)
        card_jobs = card_jobs_by_request.get(request_job.id, [])
        opening = _job_by_board_role(card_jobs, "opening_card")
        ending = _job_by_board_role(card_jobs, "ending_card")
        video_job = (video_jobs_by_request.get(request_job.id) or [None])[0]
        status, status_label = _video_request_status(request_job, opening, ending, video_job)
        rows.append(
            ArtStudioVideoRequest(
                request_job=request_job,
                product=product,
                reference_assets=references,
                opening_job=opening,
                ending_job=ending,
                video_job=video_job,
                status=status,
                status_label=status_label,
                can_approve=status == "ready_for_approval",
                can_cancel=status not in {"canceled", "complete"},
                details=metadata,
            )
        )
    return rows



def normalize_social_image_platform(platform: str | None) -> str:
    key = (platform or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "instagram_feed": "ig_feed",
        "instagram": "ig_feed",
        "facebook_feed": "fb_feed",
        "facebook": "fb_feed",
        "instagram_portrait": "ig_portrait",
        "facebook_portrait": "fb_portrait",
        "story": "stories",
        "reel": "reels",
        "tik_tok": "tiktok",
        "tiktok_style": "tiktok",
        "twitter": "x",
        "twitter_x": "x",
        "landscape": "landscape_link",
        "link_preview": "landscape_link",
        "pin": "pinterest",
    }
    return aliases.get(key, key)


def social_image_platform_label(platform: str | None) -> str:
    key = normalize_social_image_platform(platform)
    if key in SOCIAL_IMAGE_PLATFORM_LABELS:
        return SOCIAL_IMAGE_PLATFORM_LABELS[key]
    return (platform or "").strip() or "Social"


def social_image_platform_options() -> list[dict[str, str]]:
    return [
        {
            "key": key,
            "label": f"{SOCIAL_IMAGE_PLATFORM_LABELS[key]} ({ratio})",
            "aspect_ratio": ratio,
            "name": SOCIAL_IMAGE_PLATFORM_LABELS[key],
        }
        for key, ratio in SOCIAL_IMAGE_PLATFORM_ASPECT_RATIOS.items()
    ]


def resolve_social_image_frame(
    platform: str | None = None,
    aspect_ratio: str | None = None,
) -> tuple[str, str]:
    """Return (platform_key, aspect_ratio). Defaults to ig_feed / 1:1 when unspecified."""
    platform_key = normalize_social_image_platform(platform)
    ratio = (aspect_ratio or "").strip()
    if platform_key in SOCIAL_IMAGE_PLATFORM_ASPECT_RATIOS:
        return platform_key, ratio or SOCIAL_IMAGE_PLATFORM_ASPECT_RATIOS[platform_key]
    if ratio:
        return platform_key, ratio
    return DEFAULT_SOCIAL_IMAGE_PLATFORM, DEFAULT_SOCIAL_IMAGE_ASPECT_RATIO


def social_image_format_blurb(aspect_ratio: str, platform: str = "") -> str:
    ratio = (aspect_ratio or DEFAULT_SOCIAL_IMAGE_ASPECT_RATIO).strip() or DEFAULT_SOCIAL_IMAGE_ASPECT_RATIO
    blurb = SOCIAL_IMAGE_ASPECT_FORMAT_BLURBS.get(ratio, f"{ratio} social image")
    label = social_image_platform_label(platform) if platform else ""
    if label and label != "Social":
        return f"{blurb} ({label})"
    return blurb


def social_image_aspect_ratio_from_job(job: CreativeGenerationJobRecord) -> str:
    metadata = _json_dict(job.response_metadata_json)
    ratio = str(metadata.get("aspect_ratio") or "").strip()
    if ratio:
        return ratio
    dims = (job.requested_dimensions or "").strip()
    if dims:
        token = dims.split()[0]
        if ":" in token:
            return token
    return DEFAULT_SOCIAL_IMAGE_ASPECT_RATIO


def social_image_handoff(
    product: ProductRecord,
    references: list[AssetRecord],
    output_dir: str | Path,
    option_number: int | None = None,
    aspect_ratio: str = DEFAULT_SOCIAL_IMAGE_ASPECT_RATIO,
    platform: str = "",
) -> str:
    roles = _reference_roles(references)
    reference_lines = "\n".join(f"- {role}: {asset.source_path}" for role, asset in roles) or "- Add approved product references before generation."
    scene_direction = social_image_scene_direction(product)
    scene_variation = social_image_scene_variation(option_number or 1)
    context_note = _product_context_note(product)
    format_blurb = social_image_format_blurb(aspect_ratio, platform)
    return (
        "Create a Social Worthy product image for MattMadeMe.\n\n"
        f"Product: {product.name}\n"
        f"Format: {format_blurb}, realistic photographic scene, no text overlay.\n"
        "Product theme context:\n"
        f"{context_note}\n\n"
        "Scene direction:\n"
        f"{scene_direction}\n\n"
        "Scene variation:\n"
        f"{scene_variation}\n\n"
        "Reference roles:\n"
        f"{reference_lines}\n\n"
        "Prompt:\n"
        "Create a realistic, social-worthy photographic scene for the exact duck shown in @img1. "
        "The setting must match the product theme and scene direction above; do not put the duck in a generic office, desk, shelf, or unrelated room unless that is the product's explicit theme. "
        "Use secondary references only as identity locks. The duck is a 2.5 inch 3D printed collectible; "
        "keep the object miniature inside a full-scale environment. Preserve silhouette, color, accessories, "
        "print layer texture, facial details, proportions, and material exactly. Generate only the surrounding "
        "environment, lighting, depth of field, reflections, and contact shadows. No added text, watermark, "
        "duplicate product, invented logo, changed accessory, or distorted product detail. Keep the image "
        "family-friendly and brand-safe: no weapons, ammunition, shell casings, gun ranges, violent props, "
        "adult themes, sexualized details, drugs, alcohol focus, gore, political symbols, hate symbols, "
        "offensive gestures, or unsafe activity."
    )


def social_image_scene_variation(option_number: int) -> str:
    variations = [
        "Option 1: product-forward hero scene with the duck large in the foreground, clean depth of field, and a clear theme-relevant environment behind it.",
        "Option 2: lifestyle discovery scene with the duck placed naturally in a believable themed moment, surrounded by a few contextual props without clutter.",
        "Option 3: close detail scene with a lower camera angle, tactile surfaces, and theme-specific background cues that make the setting feel different from options 1 and 2.",
        "Option 4: outdoor or travel-style scene with natural light, environmental scale contrast, and a sense of place tied to the product theme.",
        "Option 5: display or collector scene with the duck staged as a giftable collectible, using theme-relevant textures and props without becoming a generic shelf photo.",
        "Option 6: action-adjacent scene that implies the hobby, job, holiday, or location without making the duck animate or perform an unsafe activity.",
        "Option 7: seasonal or occasion scene with atmospheric lighting and theme-relevant celebration details, while keeping the product as the only subject.",
        "Option 8: macro product-detail scene focused on material, silhouette, and accessories, with a distinct themed environment in soft background focus.",
    ]
    index = max(1, min(option_number, len(variations))) - 1
    return variations[index]


def social_image_scene_direction(product: ProductRecord) -> str:
    text = _product_theme_text(product)
    rules = [
        (("construction", "builder", "contractor", "hard hat", "tool belt"), "Place the duck on a safe, realistic construction site scene with lumber, tools, plans, concrete, cones, or worksite textures around it."),
        (("bowling", "bowling alley", "bowler", "pins", "lane"), "Place the duck in a bowling alley scene with polished lanes, bowling balls, pins, score-console glow, or retro league-night details."),
        (("chipmunk", "animal costume", "woodland", "critter"), "Place the duck in a playful woodland or nature scene with acorns, leaves, tree bark, picnic textures, or forest-floor details that fit the chipmunk costume."),
        (("firefighter", "fireman", "fire helmet", "fire hose", "turnout"), "Place the duck in a respectful firehouse or fire-station bay scene with hose, turnout gear, polished concrete, or emergency-service details."),
        (("delivery", "package", "courier", "mail", "postal", "route"), "Place the duck in a package-delivery setting such as a doorstep, mailroom, delivery route, parcel shelf, or sorting counter."),
        (("tattoo", "ink", "artist", "tattoo station"), "Place the duck in a tattoo studio scene with sanitized workstation details, flash art, ink caps, gloves, and studio lighting."),
        (("biker", "motorcycle", "rider", "two wheels", "open road"), "Place the duck in a biker or motorcycle scene with a parked motorcycle, garage, leather textures, road-trip stop, or open-road atmosphere."),
        (("room steward", "towel animal", "cabin", "cruise hallway"), "Place the duck in a cruise-cabin or ship hallway scene with folded towels, fresh linens, cabin-door details, or housekeeping cart cues."),
        (("hula", "tropical", "luau", "island", "grass skirt"), "Place the duck in a tropical luau or beachside scene with flowers, tiki textures, sand, palm leaves, and vacation light."),
        (("florida", "sunshine state", "palm", "beach"), "Place the duck in a sunny Florida vacation scene with palm trees, beach boardwalk, citrus colors, cruise-port cues, or warm coastal light."),
        (("texas", "cowboy", "lone star", "western", "rodeo"), "Place the duck in a Texas western scene with rustic wood, boots, rope, ranch, rodeo, or Lone Star visual cues."),
        (("georgia", "peach", "southern belle", "cherokee rose"), "Place the duck in a Georgia-inspired Southern scene with peaches, porch light, garden textures, magnolia or rose cues, and warm hospitality."),
        (("new york", "empire state", "statue of liberty", "big apple"), "Place the duck in a New York city scene with skyline, sidewalk, subway-tile, deli-counter, apple, or Statue of Liberty-inspired cues."),
        (("pennsylvania", "keystone", "steel city", "state flag"), "Place the duck in a Pennsylvania scene with Keystone State, steel-city, bridge, workshop, or state-pride cues."),
        (("patriotic", "4th of july", "declaration", "independence", "1776", "america"), "Place the duck in a tasteful patriotic July 4th scene with bunting, picnic table, historical-paper textures, fireworks colors, or Americana decor."),
        (("elks", "lodge", "antler"), "Place the duck in a lodge or fraternal hall scene with warm wood, meeting-room details, antler/lodge cues, and personalized-base visibility."),
        (("cruise", "ship", "vacation", "port"), "Place the duck in a cruise-vacation scene with cabin, deck, port, railing, towel, or travel-souvenir cues."),
    ]
    for keywords, direction in rules:
        if any(_theme_matches(text, keyword) for keyword in keywords):
            return direction
    return (
        "Use the product name and description to choose a specific, theme-relevant environment. "
        "The scene should make the duck's costume, accessory, job, location, state, holiday, or hobby feel obvious without adding text."
    )


def _product_theme_text(product: ProductRecord) -> str:
    parts = [
        product.name,
        product.sales_momentum_note,
        " ".join(json_list(product.use_cases_json)),
        " ".join(json_list(product.seasonality_json)),
    ]
    return " ".join(part for part in parts if part).lower()


def _theme_matches(text: str, keyword: str) -> bool:
    keyword = keyword.lower()
    if " " in keyword:
        return keyword in text
    return re.search(rf"\b{re.escape(keyword)}\b", text) is not None


def _product_context_note(product: ProductRecord) -> str:
    description = re.sub(r"\s+", " ", product.sales_momentum_note).strip()
    tags = json_list(product.use_cases_json)
    tag_text = f" Product tags: {', '.join(tags)}." if tags else ""
    if description:
        return f"{description[:520]}{tag_text}"
    return f"Use the product name as the primary theme source.{tag_text}"


def video_pilot_handoff(
    product: ProductRecord,
    references: list[AssetRecord],
    end_frame: AssetRecord | None = None,
    effect: dict[str, object] | None = None,
    duration_seconds: int = 8,
    aspect_ratio: str = "9:16",
    resolution: str = "1080p",
    audio_direction: str = "",
    style_direction: str = "",
    tail_rule: str = "",
) -> str:
    roles = _reference_roles(references)
    reference_lines = "\n".join(f"- {role}: {asset.source_path}" for role, asset in roles) or "- Add approved product references before generation."
    effect = effect or {}
    effect_slug = str(effect.get("slug") or "").strip()
    effect_name = str(effect.get("name") or "Product-safe camera and environment motion")
    effect_motion = str(effect.get("video_motion_prompt") or "Motion should come from camera, focus, light, and environment only.")
    cinematic_motion = str(effect.get("cinematic_motion") or effect_motion)
    prompt_defaults = video_prompt_defaults(aspect_ratio)
    audio_text = audio_direction.strip() or prompt_defaults["audio_direction"]
    style_text = style_direction.strip() or prompt_defaults["style_direction"]
    tail_text = tail_rule.strip() or prompt_defaults["tail_rule"]
    end_frame_text = (
        f"End frame: use {end_frame.source_path} as the controlled last-frame reference.\n"
        if end_frame is not None
        else "End frame: omit by default; let the selected motion resolve from the start frame without inventing a new product pose.\n"
    )
    motion_beats = _video_motion_beats(
        effect_slug,
        effect_name,
        effect_motion,
        cinematic_motion,
        end_frame is not None,
        duration_seconds,
    )
    return (
        f"Product video for {product.name}. {duration_seconds} seconds. {aspect_ratio}. {resolution}.\n"
        f"Suggested model: {effect.get('suggested_model') or default_video_models(duration_seconds)['final']}.\n\n"
        "SCENE:\n"
        "Continue the approved start frame exactly as a realistic product-in-scene shot. Keep the same environment, light, surface, depth, and atmosphere.\n\n"
        "SUBJECT:\n"
        f"The exact {product.name} duck from the start frame, presented as an inanimate 2.5 inch 3D printed collectible.\n\n"
        "REFERENCE / PRODUCT LOCK:\n"
        "Use the approved opening card as the first frame.\n"
        f"{end_frame_text}"
        "Reference roles:\n"
        f"{reference_lines}\n"
        "Keep the duck identical: same silhouette, colors, accessories, layer lines, facial details, proportions, material, and contact shadows.\n\n"
        "MOTION:\n"
        f"{motion_beats}\n\n"
        "AUDIO:\n"
        f"{audio_text}\n\n"
        "STYLE:\n"
        f"{style_text}\n\n"
        "NEGATIVE PROMPT:\n"
        f"{DEFAULT_VIDEO_NEGATIVE_PROMPT}\n\n"
        "TAIL (Ending Rule):\n"
        f"{tail_text}"
    )


def _video_motion_beats(
    effect_slug: str,
    effect_name: str,
    effect_motion: str,
    cinematic_motion: str,
    has_end_frame: bool,
    duration_seconds: int,
) -> str:
    if effect_slug == "dolly_in":
        return (
            "0-2s - Hold the opening frame long enough to read the duck and start a smooth on-axis push-in.\n"
            f"2-{max(3, duration_seconds - 2)}s - {effect_motion}\n"
            f"{max(3, duration_seconds - 2)}-{duration_seconds}s - Ease into the closer hero framing without changing the duck."
        )
    if effect_slug == "dolly_out":
        return (
            "0-2s - Start from the hero frame and begin a smooth pullback while the duck stays centered and stable.\n"
            f"2-{max(3, duration_seconds - 2)}s - {effect_motion}\n"
            f"{max(3, duration_seconds - 2)}-{duration_seconds}s - Settle into the wider reveal without changing the duck."
        )
    if effect_slug == "vertigo_effect":
        return (
            "0-2s - Hold the wide opening frame and keep the duck centered, stable, and unchanged.\n"
            f"2-{max(3, duration_seconds - 2)}s - {effect_motion}\n"
            f"{max(3, duration_seconds - 2)}-{duration_seconds}s - Snap back into the original wide framing with the duck still locked in size and position."
        )
    if effect_slug == "social_media_ad":
        return (
            "0-2s - Open on a scroll-stopping hero frame that reads instantly in 9:16.\n"
            f"2-{max(3, duration_seconds - 2)}s - {effect_motion}\n"
            f"{max(3, duration_seconds - 2)}-{duration_seconds}s - Finish on the clearest hero product view with the duck still exact and unchanged."
        )
    middle_end = max(3, min(duration_seconds - 1, 5))
    final_start = max(2, middle_end)
    final_instruction = (
        "Use the provided end frame as the controlled landing composition while preserving product identity."
        if has_end_frame
        else "Resolve the move from the start frame with no new product pose or invented ending-card composition."
    )
    return (
        f"0-2s - Establish the start frame and begin the {effect_name.lower()} gently. {cinematic_motion}\n"
        f"2-{middle_end}s - Continue the selected motion with small, believable changes only. {effect_motion}\n"
        f"{final_start}-{duration_seconds}s - Ease the motion into a stable final view. {final_instruction}"
    )


def video_art_board_handoff(
    product: ProductRecord,
    references: list[AssetRecord],
    scene: str = "festive picnic setup",
    aspect_ratio: str = "9:16",
    output_dir: str | Path = "",
    board_role: str = "opening_card",
    effect: dict[str, object] | None = None,
) -> str:
    roles = _reference_roles(references)
    reference_lines = "\n".join(f"- {role}: {asset.source_path}" for role, asset in roles) or "- Add approved product references before generation."
    output_text = f"\nOutput folder: {Path(output_dir).as_posix()}" if str(output_dir).strip() else ""
    role_label = "ending card / last frame" if board_role == "ending_card" else "opening card / first frame"
    effect = effect or {}
    effect_name = str(effect.get("name") or "product-safe first/last-frame motion")
    effect_value = str(effect.get("value") or "Create visible scene progression while keeping the product unchanged.")
    effect_motion = str(effect.get("video_motion_prompt") or "Motion should come from camera, focus, light, and environment only.")
    effect_card_brief = str(
        effect.get("ending_card_brief" if board_role == "ending_card" else "opening_card_brief")
        or ""
    )
    composition = (
        "Create this only after the opening card exists. Use the generated opening card as the composition and scene "
        "reference when available. Keep the same scene layout, staging surface or plane, prop positions, background "
        "element placement, lighting direction, color temperature, and product placement except where the selected video effect explicitly requires "
        "a camera-position, focus-plane, time-of-day, or perspective change. Do not change the duck."
        if board_role == "ending_card"
        else "Make this a scroll-stopping first frame: the product is already in the scene with enough context and "
        "foreground interest to avoid a plain product-card opening."
    )
    return (
        "Use $video-content-planner to choose one scene direction for the user-queued product, then "
        "$social-media-art-director to create this controlled video card still.\n\n"
        f"Product: {product.name}\n"
        f"Scene strategy: {scene}\n"
        f"Selected video effect: {effect_name}\n"
        f"Effect value: {effect_value}\n"
        f"Effect-specific card brief: {effect_card_brief}\n"
        f"Expected video motion: {effect_motion}\n"
        f"Card role: {role_label}\n"
        f"Format: {aspect_ratio} vertical video frame; realistic photographic product-in-scene still; no text overlay.{output_text}\n\n"
        "Reference roles:\n"
        f"{reference_lines}\n\n"
        "Art board prompt:\n"
        f"Create a realistic social video {role_label} for the exact duck shown in @img1. Place the duck in a {scene}. "
        f"{composition} "
        "The duck is locked reference content: preserve its exact silhouette, colors, accessories, print layer texture, facial details, proportions, and material. "
        "Do not add yellow pieces, extra parts, new accessories, duplicate ducks, text, logos, watermarks, or misleading product details. "
        "Generate only the scene, surface, lighting, shadows, depth of field, and background atmosphere around the unchanged product."
    )


def select_video_effect(
    product: ProductRecord,
    scene_guidance: str = "",
    duration_seconds: int = 8,
    aspect_ratio: str = "9:16",
    requested_template: str = "",
) -> dict[str, object]:
    requested_slug = requested_template.strip()
    if requested_slug in VIDEO_EFFECT_STYLES:
        selected = dict(VIDEO_EFFECT_STYLES[requested_slug])
        selected["slug"] = requested_slug
        selected["selection_score"] = int(selected.get("base_score") or 0)
        selected["requested_template"] = True
        return selected
    text = f"{product.name} {scene_guidance}".lower()
    product_key = product.id or sum(ord(char) for char in product.name)
    best_slug = "focus_pull"
    best_score = -1
    for index, (slug, effect) in enumerate(VIDEO_EFFECT_STYLES.items()):
        score = int(effect["base_score"])
        score += sum(18 for keyword in effect["keywords"] if keyword in text)
        score += ((product_key + index * 7) % 17) - 8
        if duration_seconds <= 5 and effect["risk"] in {"medium-high"}:
            score -= 14
        if aspect_ratio == "1:1" and slug in {"hyperlapse_sweep", "bullet_time"}:
            score -= 8
        if score > best_score:
            best_slug = slug
            best_score = score
    selected = dict(VIDEO_EFFECT_STYLES[best_slug])
    selected["slug"] = best_slug
    selected["selection_score"] = best_score
    return selected


def video_request_strategy_direction(
    product: ProductRecord,
    scene_guidance: str,
    duration_seconds: int,
    aspect_ratio: str,
    resolution: str,
    effect: dict[str, object] | None = None,
    voice_script: str = "",
    voice_tone: str = "",
) -> str:
    scene = scene_guidance.strip() or "strategist-selected product-safe social scene"
    effect = effect or select_video_effect(product, scene_guidance, duration_seconds, aspect_ratio)
    voice_direction = requested_voice_direction(voice_script, voice_tone)
    voice_text = f" Requested voice direction: {voice_direction}" if voice_direction else ""
    return (
        f"Create a {duration_seconds} second {aspect_ratio} product-safe social video for {product.name}. "
        f"Scene direction: {scene}. Selected template: {effect['name']} ({effect['risk']} risk). "
        f"Suggested model: {effect.get('suggested_model') or default_video_models(duration_seconds)['final']}. "
        f"Why this template: {effect['value']} "
        "The opening card should start directly in the finished scene with the duck already placed as an inanimate collectible. "
        f"Opening card direction: {effect['opening_card_brief']} "
        "Generate one opening scene card first and use it as the video start frame. Do not generate a matching ending card by default; "
        "test the selected video effect from the single scene image before spending credits on first/last-frame control. "
        f"Optional ending card direction if later needed: {effect['ending_card_brief']} "
        f"Video motion direction: {effect['video_motion_prompt']} "
        "Motion must come from camera movement, light, focus, perspective, time, or environmental atmosphere only. "
        "The duck must remain physically still and unchanged: exact silhouette, colors, accessories, layer lines, facial details, proportions, and material."
        f"{voice_text}"
    )


def create_video_request(
    session: Session,
    product_id: int,
    reference_asset_ids: list[int],
    duration_seconds: int = 8,
    aspect_ratio: str = "9:16",
    resolution: str = "1080p",
    scene_guidance: str = "",
    template_slug: str = "focus_pull",
    voice_script: str = "",
    voice_tone: str = "",
) -> CreativeGenerationJobRecord:
    refresh_asset_file_state(session)
    product = _product_or_raise(session, product_id)
    references = _references_or_raise(session, reference_asset_ids, product.id)
    if not references:
        raise ValueError("Select at least one reference image for the video request.")
    selected_template = select_video_effect(
        product,
        scene_guidance,
        duration_seconds,
        aspect_ratio,
        requested_template=template_slug,
    )
    request_job = CreativeGenerationJobRecord(
        source_asset_id=references[0].id,
        target_format=VIDEO_REQUEST_FORMAT,
        provider="art_studio",
        model_name="queued_video_workflow",
        prompt="Handoff queued for agent-run video planning. Waiting on video-content-planner, social-media-art-director, and video-editor registration (not a marketing-os-worker job).",
        requested_dimensions=f"{aspect_ratio} {duration_seconds}s {resolution}",
        provider_status="queued",
        response_metadata_json=json.dumps(
            {
                "art_studio": True,
                "product_id": product.id,
                "product_name": product.name,
                "reference_asset_ids": [asset.id for asset in references],
                "duration_seconds": duration_seconds,
                "aspect_ratio": aspect_ratio,
                "resolution": resolution,
                "scene_guidance": scene_guidance.strip(),
                "video_template_slug": selected_template["slug"],
                "video_template_name": selected_template["name"],
                "suggested_video_model": selected_template.get("suggested_model") or default_video_models(duration_seconds)["final"],
                "video_reference_strategy": selected_template.get("reference_strategy") or "start_frame_only",
                "requested_voice_script": voice_script.strip(),
                "requested_voice_tone": (
                    (voice_tone.strip() or DEFAULT_VIDEO_VOICE_TONE) if voice_script.strip() else ""
                ),
                "storyboard_mode": "single_start_frame",
                "ending_card_required": False,
                "asset_type": VIDEO_ASSET_TYPE,
                "asset_role": VIDEO_ASSET_ROLE,
            },
            indent=2,
        ),
        review_state="needs_review",
        review_notes="Video request handoff queued — waiting on Magnific / agent (not drained by marketing-os-worker yet). Register the planner brief before scene-card generation starts.",
    )
    session.add(request_job)
    session.flush()
    return request_job


def register_social_image_output(
    session: Session,
    product_id: int,
    source_asset_id: int,
    output_path: str | Path,
    title: str = "",
    prompt: str = "",
    provider: str = "magnific_mcp",
    model_name: str = "",
    provider_job_id: str = "",
    notes: str = "",
) -> AssetRecord:
    refresh_asset_file_state(session)
    product = _product_or_raise(session, product_id)
    source = _source_or_raise(session, source_asset_id, product_id)
    output = Path(output_path).expanduser()
    if not output.is_file():
        raise ValueError(f"Generated image file not found: {output}")
    record = _asset_for_path(session, output) or AssetRecord(
        product_id=product.id,
        name=title.strip() or f"{product.name} social image",
        asset_type=SOCIAL_IMAGE_ASSET_TYPE,
        source_path=output.as_posix(),
        preview_path=output.as_posix(),
        platform_suitability_json=json.dumps(["facebook", "instagram", "pinterest"]),
        readiness_state="needs human review",
        notes=notes.strip() or "Art Studio Social Worthy image; review before planner reuse.",
        external_source=provider,
        external_id=provider_job_id,
        sync_status="generated",
        staleness_state="fresh",
        review_state="needs review",
        asset_role=SOCIAL_IMAGE_ROLE,
        brand_safe="review",
        generated_prompt=prompt,
        source_asset_id=source.id,
    )
    if record.id is None:
        session.add(record)
    record.product_id = product.id
    record.asset_type = SOCIAL_IMAGE_ASSET_TYPE
    record.asset_role = SOCIAL_IMAGE_ROLE
    record.external_source = provider
    record.external_id = provider_job_id
    record.generated_prompt = prompt or record.generated_prompt
    record.source_asset_id = source.id
    record.readiness_state = "needs human review"
    record.review_state = "needs review"
    record.notes = notes.strip() or record.notes
    if model_name:
        record.manual_override_note = f"Model: {model_name}"
    session.flush()
    refresh_asset_file_state(session, asset_ids=[record.id])
    return record


def enqueue_social_image_generation(
    session: Session,
    product_id: int,
    source_asset_id: int,
    option_number: int = 1,
    reference_asset_ids: list[int] | None = None,
    platform: str | None = None,
    aspect_ratio: str | None = None,
) -> CreativeGenerationJobRecord:
    refresh_asset_file_state(session)
    product = _product_or_raise(session, product_id)
    source = _source_or_raise(session, source_asset_id, product_id)
    references = _references_or_raise(session, reference_asset_ids or [source_asset_id], product.id)
    platform_key, ratio = resolve_social_image_frame(platform=platform, aspect_ratio=aspect_ratio)
    platform_label = social_image_platform_label(platform_key)
    output_dir = f"outputs/graphics/social-worthy/{slugify(product.name)}"
    prompt = social_image_handoff(
        product,
        references,
        output_dir,
        option_number=option_number,
        aspect_ratio=ratio,
        platform=platform_key,
    )
    metadata_match = {
        "reference_asset_ids": [asset.id for asset in references],
        "platform": platform_key,
        "aspect_ratio": ratio,
    }
    existing = _queued_job(session, source.id, SOCIAL_JOB_FORMAT, option_number, metadata_match=metadata_match)
    api_ready = magnific_api_configured()
    if existing is not None:
        _ensure_social_image_automation_job(session, existing, api_ready=api_ready)
        return existing
    provider = "magnific_api" if api_ready else "magnific_mcp"
    model_name = "Nano Banana Pro Flash" if api_ready else "Google Nano Banana 2"
    review_notes = (
        "Queued for marketing-os-worker Magnific API drain. "
        "Attach/import remains available as a fallback."
        if api_ready
        else (
            "Handoff queued — waiting on Magnific (not drained by marketing-os-worker yet). "
            "Generate in Magnific, then attach/import the file to complete."
        )
    )
    job = CreativeGenerationJobRecord(
        source_asset_id=source.id,
        target_format=SOCIAL_JOB_FORMAT,
        provider=provider,
        model_name=model_name,
        prompt=prompt,
        requested_dimensions=f"{ratio} {platform_label}",
        provider_status="queued",
        response_metadata_json=json.dumps(
            {
                "art_studio": True,
                "product_id": product.id,
                "product_name": product.name,
                "option_number": option_number,
                "platform": platform_key,
                "platform_label": platform_label,
                "aspect_ratio": ratio,
                "reference_asset_ids": [asset.id for asset in references],
                "output_dir": output_dir,
                "asset_type": SOCIAL_IMAGE_ASSET_TYPE,
                "asset_role": SOCIAL_IMAGE_ROLE,
                "magnific_api_drain": api_ready,
            },
            indent=2,
        ),
        review_state="needs_review",
        review_notes=review_notes,
    )
    session.add(job)
    session.flush()
    _ensure_social_image_automation_job(session, job, api_ready=api_ready)
    return job


def _ensure_social_image_automation_job(
    session: Session,
    job: CreativeGenerationJobRecord,
    *,
    api_ready: bool,
) -> None:
    """Enqueue durable drain job when MAGNIFIC_API_KEY is configured; no-op otherwise."""
    if not api_ready:
        return
    if job.provider_status not in {"queued", "generating"}:
        return
    enqueue_job(
        session,
        job_type="art_studio.social_image.generate",
        payload={"creativeJobId": job.id},
        idempotency_key=f"art_studio.social_image.generate:{job.id}",
        correlation_id=f"art_studio.social_image:{job.id}",
        max_attempts=3,
        priority=80,
    )


def enqueue_video_art_board_generation(
    session: Session,
    product_id: int,
    source_asset_id: int,
    scene: str = "festive picnic setup",
    aspect_ratio: str = "9:16",
    option_number: int = 1,
    board_role: str = "opening_card",
    storyboard_id: str = "",
    reference_asset_ids: list[int] | None = None,
    video_request_job_id: int | None = None,
    effect: dict[str, object] | None = None,
    prompt_override: str = "",
    provider: str = "magnific_mcp",
    model_name: str = "Google Nano Banana 2",
) -> CreativeGenerationJobRecord:
    refresh_asset_file_state(session)
    product = _product_or_raise(session, product_id)
    source = _source_or_raise(session, source_asset_id, product_id)
    references = _references_or_raise(session, reference_asset_ids or [source_asset_id], product.id)
    if board_role not in {"opening_card", "ending_card"}:
        raise ValueError("Video art board role must be opening_card or ending_card.")
    output_dir = f"outputs/graphics/social-worthy/{slugify(product.name)}"
    prompt = prompt_override.strip() or video_art_board_handoff(
        product,
        references,
        scene=scene,
        aspect_ratio=aspect_ratio,
        output_dir=output_dir,
        board_role=board_role,
        effect=effect,
    )
    existing = _queued_job(session, source.id, VIDEO_ART_BOARD_JOB_FORMAT, option_number, metadata_match={"board_role": board_role})
    if existing is not None:
        existing.prompt = prompt
        existing.provider = provider
        existing.model_name = model_name
        metadata = _json_dict(existing.response_metadata_json)
        metadata["prompt_source"] = "agent_authored" if prompt_override.strip() else "template_generated"
        existing.response_metadata_json = json.dumps(metadata, indent=2)
        session.flush()
        return existing
    asset_role = VIDEO_ENDING_CARD_ROLE if board_role == "ending_card" else VIDEO_OPENING_CARD_ROLE
    job = CreativeGenerationJobRecord(
        source_asset_id=source.id,
        target_format=VIDEO_ART_BOARD_JOB_FORMAT,
        provider=provider,
        model_name=model_name,
        prompt=prompt,
        requested_dimensions=f"{aspect_ratio} {board_role.replace('_', ' ')}",
        provider_status="queued",
        response_metadata_json=json.dumps(
            {
                "art_studio": True,
                "product_id": product.id,
                "product_name": product.name,
                "option_number": option_number,
                "storyboard_id": storyboard_id or f"product-{product.id}-source-{source.id}-option-{option_number}",
                "video_request_job_id": video_request_job_id,
                "board_role": board_role,
                "scene": scene,
                "video_effect_slug": effect.get("slug") if effect else "",
                "video_effect_name": effect.get("name") if effect else "",
                "video_effect_risk": effect.get("risk") if effect else "",
                "video_effect_value": effect.get("value") if effect else "",
                "card_brief": effect.get("ending_card_brief" if board_role == "ending_card" else "opening_card_brief") if effect else "",
                "video_motion_prompt": effect.get("video_motion_prompt") if effect else "",
                "reference_asset_ids": [asset.id for asset in references],
                "aspect_ratio": aspect_ratio,
                "output_dir": output_dir,
                "prompt_source": "agent_authored" if prompt_override.strip() else "template_generated",
                "asset_type": VIDEO_ART_BOARD_ASSET_TYPE,
                "asset_role": asset_role,
                "next_step": "Review this scene card, then approve a single-start-frame Art Studio product video draft.",
            },
            indent=2,
        ),
        review_state="needs_review",
        review_notes="Handoff queued — waiting on Magnific for this scene card (not drained by marketing-os-worker yet). Generate externally, then import/attach to complete; use as the start frame for the video style test.",
    )
    session.add(job)
    session.flush()
    return job


def enqueue_video_storyboard_generation(
    session: Session,
    product_id: int,
    source_asset_id: int,
    scene_guidance: str = "",
    aspect_ratio: str = "9:16",
    option_number: int = 1,
) -> list[CreativeGenerationJobRecord]:
    scene = scene_guidance.strip() or "festive picnic setup"
    storyboard_id = f"product-{product_id}-source-{source_asset_id}-option-{option_number}"
    opening = enqueue_video_art_board_generation(
        session,
        product_id,
        source_asset_id,
        scene=scene,
        aspect_ratio=aspect_ratio,
        option_number=option_number,
        board_role="opening_card",
        storyboard_id=storyboard_id,
    )
    ending = enqueue_video_art_board_generation(
        session,
        product_id,
        source_asset_id,
        scene=scene,
        aspect_ratio=aspect_ratio,
        option_number=option_number,
        board_role="ending_card",
        storyboard_id=storyboard_id,
    )
    return [opening, ending]


def enqueue_video_generation(
    session: Session,
    product_id: int,
    source_asset_id: int,
    end_asset_id: int | None = None,
    duration_seconds: int = 8,
    aspect_ratio: str = "9:16",
    resolution: str = "1080p",
    video_request_job_id: int | None = None,
    effect: dict[str, object] | None = None,
    prompt_override: str = "",
    provider: str = "magnific_mcp",
    model_name: str = "",
    audio_direction: str = "",
    style_direction: str = "",
    tail_rule: str = "",
) -> CreativeGenerationJobRecord:
    refresh_asset_file_state(session)
    product = _product_or_raise(session, product_id)
    source = _video_source_or_raise(session, source_asset_id, product_id)
    end_frame = _video_source_or_raise(session, end_asset_id, product_id) if end_asset_id is not None else None
    selected_model = model_name.strip() or default_video_models(duration_seconds)["final"]
    prompt = prompt_override.strip() or video_pilot_handoff(
        product,
        [source],
        end_frame=end_frame,
        effect=effect,
        duration_seconds=duration_seconds,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        audio_direction=audio_direction,
        style_direction=style_direction,
        tail_rule=tail_rule,
    )
    existing = _queued_job(
        session,
        source.id,
        VIDEO_JOB_FORMAT,
        1,
        metadata_match={"end_frame_asset_id": end_frame.id if end_frame is not None else None},
    )
    if existing is not None:
        existing.prompt = prompt
        existing.provider = provider
        existing.model_name = selected_model
        metadata = _json_dict(existing.response_metadata_json)
        metadata["prompt_source"] = "agent_authored" if prompt_override.strip() else "template_generated"
        metadata["audio_direction"] = audio_direction.strip()
        metadata["style_direction"] = style_direction.strip()
        metadata["tail_rule"] = tail_rule.strip()
        existing.response_metadata_json = json.dumps(metadata, indent=2)
        session.flush()
        return existing
    job = CreativeGenerationJobRecord(
        source_asset_id=source.id,
        target_format=VIDEO_JOB_FORMAT,
        provider=provider,
        model_name=selected_model,
        prompt=prompt,
        requested_dimensions=f"{aspect_ratio} {duration_seconds}s {resolution}",
        provider_status="queued",
        response_metadata_json=json.dumps(
            {
                "art_studio": True,
                "product_id": product.id,
                "product_name": product.name,
                "duration_seconds": duration_seconds,
                "aspect_ratio": aspect_ratio,
                "resolution": resolution,
                "asset_type": VIDEO_ASSET_TYPE,
                "asset_role": VIDEO_ASSET_ROLE,
                "start_frame_asset_id": source.id,
                "end_frame_asset_id": end_frame.id if end_frame is not None else None,
                "video_request_job_id": video_request_job_id,
                "video_effect_slug": effect.get("slug") if effect else "",
                "video_effect_name": effect.get("name") if effect else "",
                "video_motion_prompt": effect.get("video_motion_prompt") if effect else "",
                "start_frame_strategy": "Use the generated opening card as the first frame; avoid plain product-photo opening cards.",
                "end_frame_strategy": "Use the generated ending card as the last frame when available for controlled first/last-frame video.",
                "scene_decisions_source": "video-content-planner",
                "prompt_source": "agent_authored" if prompt_override.strip() else "template_generated",
                "negative_prompt": DEFAULT_VIDEO_NEGATIVE_PROMPT,
                "audio_direction": audio_direction.strip(),
                "style_direction": style_direction.strip(),
                "tail_rule": tail_rule.strip(),
            },
            indent=2,
        ),
        review_state="needs_review",
        review_notes="Handoff queued — waiting on Magnific video generation (not drained by marketing-os-worker yet). Use opening/ending cards as first/last frames, then attach/import the file to complete.",
    )
    session.add(job)
    session.flush()
    return job


def register_video_request_workflow(
    session: Session,
    request_job_id: int,
    planner_result: dict[str, object],
    opening_card_prompt: str,
    opening_card_title: str = "",
    ending_card_required: bool = False,
    ending_card_prompt: str = "",
    ending_card_title: str = "",
    provider: str = "codex_agent",
    opening_provider: str = "magnific_mcp",
    opening_model_name: str = "Google Nano Banana 2",
    ending_provider: str = "magnific_mcp",
    ending_model_name: str = "Google Nano Banana 2",
    video_editor_request: dict[str, object] | None = None,
    notes: str = "",
) -> CreativeGenerationJobRecord:
    request_job = _job_or_raise(session, request_job_id, VIDEO_REQUEST_FORMAT)
    metadata = _json_dict(request_job.response_metadata_json)
    product_id = _job_product_id(request_job) or _int_value(metadata.get("product_id"))
    if product_id is None:
        raise ValueError("Video request is missing a product.")
    product = _product_or_raise(session, product_id)
    references = _assets_for_ids(session, metadata.get("reference_asset_ids"), product.id)
    if not references:
        raise ValueError("Video request is missing approved reference assets.")
    if not opening_card_prompt.strip():
        raise ValueError("Opening card prompt is required.")

    selected_effect = planner_result.get("selected_effect") if isinstance(planner_result.get("selected_effect"), dict) else {}
    fallback_effect = select_video_effect(
        product,
        str(metadata.get("scene_guidance") or ""),
        int(metadata.get("duration_seconds") or 8),
        str(metadata.get("aspect_ratio") or "9:16"),
        requested_template=str(metadata.get("video_template_slug") or ""),
    )
    ending_card_required = bool(ending_card_required or planner_result.get("ending_card_required"))
    effect = {
        "slug": str(selected_effect.get("slug") or fallback_effect.get("slug") or "").strip(),
        "name": str(selected_effect.get("name") or fallback_effect.get("name") or "").strip(),
        "risk": str(selected_effect.get("risk") or fallback_effect.get("risk") or "").strip(),
        "value": str(selected_effect.get("value") or fallback_effect.get("value") or "").strip(),
        "opening_card_brief": str(planner_result.get("opening_card_brief") or fallback_effect.get("opening_card_brief") or "").strip(),
        "ending_card_brief": str(planner_result.get("ending_card_brief") or fallback_effect.get("ending_card_brief") or "").strip(),
        "video_motion_prompt": str(planner_result.get("video_motion_prompt") or fallback_effect.get("video_motion_prompt") or "").strip(),
        "suggested_model": str(planner_result.get("suggested_model") or fallback_effect.get("suggested_model") or "").strip(),
        "reference_strategy": str(planner_result.get("reference_strategy") or fallback_effect.get("reference_strategy") or "").strip(),
        "ending_card_required": bool(ending_card_required),
    }
    planner_summary = str(planner_result.get("summary") or planner_result.get("scene_strategy") or "").strip()
    scene = str(planner_result.get("scene_strategy") or metadata.get("scene_guidance") or "").strip() or "planner-selected product-safe social scene"
    prompt_defaults = video_prompt_defaults(str(metadata.get("aspect_ratio") or "9:16"))
    requested_voice_script = str(metadata.get("requested_voice_script") or "").strip()
    requested_voice_tone = str(metadata.get("requested_voice_tone") or "").strip()
    fallback_audio_direction = requested_voice_direction(requested_voice_script, requested_voice_tone) or prompt_defaults["audio_direction"]
    audio_direction = str(planner_result.get("audio_direction") or fallback_audio_direction).strip()
    style_direction = str(planner_result.get("style_direction") or prompt_defaults["style_direction"]).strip()
    tail_rule = str(planner_result.get("tail_rule") or prompt_defaults["tail_rule"]).strip()
    strategist_direction = video_request_strategy_direction(
        product,
        scene,
        int(metadata.get("duration_seconds") or 8),
        str(metadata.get("aspect_ratio") or "9:16"),
        str(metadata.get("resolution") or "1080p"),
        effect=effect,
        voice_script=requested_voice_script,
        voice_tone=requested_voice_tone,
    )

    request_job.provider = provider
    request_job.model_name = "video-content-planner"
    request_job.prompt = planner_summary or request_job.prompt
    request_job.provider_status = "planned"
    request_job.review_state = "needs_review"
    request_job.review_notes = notes.strip() or "Planner brief registered. Scene-card generation is queued for review."

    metadata.update(
        {
            "planner_result": planner_result,
            "planner_summary": planner_summary,
            "strategist_direction": strategist_direction,
            "scene_strategy": scene,
            "storyboard_mode": str(planner_result.get("storyboard_mode") or "single_start_frame"),
            "ending_card_required": bool(ending_card_required),
            "video_effect_slug": effect["slug"],
            "video_effect_name": effect["name"],
            "video_effect_risk": effect["risk"],
            "video_effect_value": effect["value"],
            "opening_card_brief": effect["opening_card_brief"],
            "ending_card_brief": effect["ending_card_brief"],
            "video_motion_prompt": effect["video_motion_prompt"],
            "video_template_slug": effect["slug"],
            "video_template_name": effect["name"],
            "suggested_video_model": effect["suggested_model"] or str(metadata.get("suggested_video_model") or ""),
            "video_reference_strategy": effect["reference_strategy"] or str(metadata.get("video_reference_strategy") or ""),
            "requested_voice_script": requested_voice_script,
            "requested_voice_tone": requested_voice_tone,
            "audio_direction": audio_direction,
            "style_direction": style_direction,
            "tail_rule": tail_rule,
        }
    )
    editor_request = dict(video_editor_request) if isinstance(video_editor_request, dict) else {}
    selected_effect_payload = {
        "slug": effect["slug"],
        "name": effect["name"],
        "risk": effect["risk"],
        "value": effect["value"],
    }
    editor_request.update(
        {
            "planner_summary": planner_summary,
            "scene_strategy": scene,
            "selected_effect": selected_effect_payload,
            "opening_card_brief": effect["opening_card_brief"],
            "ending_card_brief": effect["ending_card_brief"],
            "video_motion_prompt": effect["video_motion_prompt"],
            "suggested_model": effect["suggested_model"] or str(metadata.get("suggested_video_model") or ""),
            "reference_strategy": effect["reference_strategy"] or str(metadata.get("video_reference_strategy") or ""),
            "ending_card_required": bool(ending_card_required),
            "requested_voice_script": requested_voice_script,
            "requested_voice_tone": requested_voice_tone,
            "audio_direction": audio_direction,
            "style_direction": style_direction,
            "tail_rule": tail_rule,
        }
    )
    metadata["video_editor_request"] = editor_request

    storyboard_id = f"video-request-{request_job.id}"
    opening = enqueue_video_art_board_generation(
        session,
        product.id,
        references[0].id,
        scene=scene,
        aspect_ratio=str(metadata.get("aspect_ratio") or "9:16"),
        option_number=request_job.id,
        board_role="opening_card",
        storyboard_id=storyboard_id,
        reference_asset_ids=[asset.id for asset in references],
        video_request_job_id=request_job.id,
        effect=effect,
        prompt_override=opening_card_prompt,
        provider=opening_provider,
        model_name=opening_model_name,
    )
    metadata["opening_card_job_id"] = opening.id
    metadata["opening_card_title"] = opening_card_title.strip() or f"{product.name} opening card"

    if ending_card_required:
        if not ending_card_prompt.strip():
            raise ValueError("Ending card prompt is required when ending_card_required is true.")
        ending = enqueue_video_art_board_generation(
            session,
            product.id,
            references[0].id,
            scene=scene,
            aspect_ratio=str(metadata.get("aspect_ratio") or "9:16"),
            option_number=request_job.id,
            board_role="ending_card",
            storyboard_id=storyboard_id,
            reference_asset_ids=[asset.id for asset in references],
            video_request_job_id=request_job.id,
            effect=effect,
            prompt_override=ending_card_prompt,
            provider=ending_provider,
            model_name=ending_model_name,
        )
        ending_metadata = _json_dict(ending.response_metadata_json)
        ending_metadata["depends_on_card_job_id"] = opening.id
        ending_metadata["composition_reference_required"] = True
        ending_metadata["composition_reference_note"] = (
            "Generate the opening card first, then use that opening card as an image/composition reference for this ending card."
        )
        ending.response_metadata_json = json.dumps(ending_metadata, indent=2)
        metadata["ending_card_job_id"] = ending.id
        metadata["ending_card_title"] = ending_card_title.strip() or f"{product.name} ending card"

    request_job.response_metadata_json = json.dumps(metadata, indent=2)
    session.flush()
    return request_job


def approve_video_request_for_generation(session: Session, request_job_id: int) -> CreativeGenerationJobRecord:
    request_job = _job_or_raise(session, request_job_id, VIDEO_REQUEST_FORMAT)
    metadata = _json_dict(request_job.response_metadata_json)
    product_id = _job_product_id(request_job) or _int_value(metadata.get("product_id"))
    if product_id is None:
        raise ValueError("Video request is missing a product.")
    rows = art_studio_video_requests(session, limit=500)
    request = next((row for row in rows if row.request_job.id == request_job_id), None)
    if request is None:
        raise ValueError("Video request not found.")
    ending_required = bool(metadata.get("ending_card_required"))
    if not request.can_approve or request.opening_job is None:
        raise ValueError("Video request is not ready for video generation.")
    opening_asset = request.opening_job.candidate_asset
    ending_asset = request.ending_job.candidate_asset if request.ending_job is not None else None
    if opening_asset is None:
        raise ValueError("Opening scene card must be generated before approval.")
    if ending_required and ending_asset is None:
        raise ValueError("Ending card must be generated before approval for this video effect.")
    effect = {
        "slug": metadata.get("video_effect_slug") or "",
        "name": metadata.get("video_effect_name") or "",
        "risk": metadata.get("video_effect_risk") or "",
        "value": metadata.get("video_effect_value") or "",
        "video_motion_prompt": metadata.get("video_motion_prompt") or "",
        "suggested_model": metadata.get("suggested_video_model") or "",
        "reference_strategy": metadata.get("video_reference_strategy") or "",
    }
    video_job = enqueue_video_generation(
        session,
        product_id,
        opening_asset.id,
        end_asset_id=ending_asset.id if ending_required and ending_asset is not None else None,
        duration_seconds=int(metadata.get("duration_seconds") or 8),
        aspect_ratio=str(metadata.get("aspect_ratio") or "9:16"),
        resolution=str(metadata.get("resolution") or "1080p"),
        video_request_job_id=request_job.id,
        effect=effect,
        model_name=str(metadata.get("suggested_video_model") or ""),
        audio_direction=str(metadata.get("audio_direction") or ""),
        style_direction=str(metadata.get("style_direction") or ""),
        tail_rule=str(metadata.get("tail_rule") or ""),
    )
    request_job.provider_status = "video_queued"
    request_job.review_state = "approved"
    request_job.review_notes = f"Approved for video generation. Video job #{video_job.id} queued."
    session.flush()
    return video_job


def cancel_video_request(session: Session, request_job_id: int) -> CreativeGenerationJobRecord:
    request_job = _job_or_raise(session, request_job_id, VIDEO_REQUEST_FORMAT)
    request_job.provider_status = "canceled"
    request_job.review_state = "rejected"
    request_job.review_notes = "Canceled from Art Studio before final video generation."
    for row in art_studio_video_requests(session, limit=500):
        if row.request_job.id == request_job_id:
            for job in [row.opening_job, row.ending_job, row.video_job]:
                if job is not None and job.provider_status == "queued":
                    job.provider_status = "canceled"
                    job.review_state = "rejected"
                    job.review_notes = "Canceled with parent video request."
            break
    session.flush()
    return request_job


def register_social_image_job_output(
    session: Session,
    job_id: int,
    output_path: str | Path,
    title: str = "",
    provider_job_id: str = "",
    output_url: str = "",
    notes: str = "",
) -> CreativeGenerationJobRecord:
    job = _job_or_raise(session, job_id, SOCIAL_JOB_FORMAT)
    product_id = _job_product_id(job)
    if product_id is None:
        raise ValueError("Queued social image job is missing a source product.")
    asset = register_social_image_output(
        session,
        product_id=product_id,
        source_asset_id=job.source_asset_id,
        output_path=output_path,
        title=title or f"{job.source_asset.product.name if job.source_asset.product else 'Product'} social image",
        prompt=job.prompt,
        provider=job.provider,
        model_name=job.model_name,
        provider_job_id=provider_job_id or job.provider_job_id,
        notes=notes or "Generated from Art Studio queue; review before planner reuse.",
    )
    _complete_job(job, asset, output_path, provider_job_id, output_url)
    return job


def register_video_art_board_job_output(
    session: Session,
    job_id: int,
    output_path: str | Path,
    title: str = "",
    provider_job_id: str = "",
    output_url: str = "",
    notes: str = "",
) -> CreativeGenerationJobRecord:
    job = _job_or_raise(session, job_id, VIDEO_ART_BOARD_JOB_FORMAT)
    product_id = _job_product_id(job)
    if product_id is None:
        raise ValueError("Queued video art board job is missing a source product.")
    metadata = _json_dict(job.response_metadata_json)
    asset = register_social_image_output(
        session,
        product_id=product_id,
        source_asset_id=job.source_asset_id,
        output_path=output_path,
        title=title or f"{job.source_asset.product.name if job.source_asset.product else 'Product'} video art board",
        prompt=job.prompt,
        provider=job.provider,
        model_name=job.model_name,
        provider_job_id=provider_job_id or job.provider_job_id,
        notes=notes or "Generated from Art Studio video art-board queue; review before animating.",
    )
    asset.asset_type = str(metadata.get("asset_type") or VIDEO_ART_BOARD_ASSET_TYPE)
    asset.asset_role = str(metadata.get("asset_role") or VIDEO_ART_BOARD_ROLE)
    asset.platform_suitability_json = json.dumps(["instagram_reels", "tiktok", "youtube_shorts", "facebook_reels"])
    session.flush()
    _complete_job(job, asset, output_path, provider_job_id, output_url)
    return job


def register_video_output(
    session: Session,
    product_id: int,
    source_asset_id: int,
    video_path: str | Path,
    title: str = "",
    prompt: str = "",
    poster_path: str | Path | None = None,
    provider: str = "magnific_mcp",
    model_name: str = "bytedance-seedance-pro-2.0",
    provider_job_id: str = "",
    duration_seconds: int = 8,
    aspect_ratio: str = "9:16",
    resolution: str = "1080p",
    notes: str = "",
) -> AssetRecord:
    refresh_asset_file_state(session)
    product = _product_or_raise(session, product_id)
    source = _video_source_or_raise(session, source_asset_id, product_id)
    video = Path(video_path).expanduser()
    if not video.is_file():
        raise ValueError(f"Generated video file not found: {video}")
    poster = Path(poster_path).expanduser() if poster_path else None
    if poster is not None and not poster.is_file():
        raise ValueError(f"Video poster file not found: {poster}")
    guardrail = validate_video_motion_prompt(prompt)
    metadata = {
        "model": model_name,
        "duration_seconds": duration_seconds,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "motion_guardrail": guardrail,
        "negative_prompt": DEFAULT_VIDEO_NEGATIVE_PROMPT,
    }
    record = _asset_for_path(session, video) or AssetRecord(
        product_id=product.id,
        name=title.strip() or f"{product.name} product video",
        asset_type=VIDEO_ASSET_TYPE,
        source_path=video.as_posix(),
        preview_path=poster.as_posix() if poster else "",
        platform_suitability_json=json.dumps(["instagram_reels", "tiktok", "youtube_shorts", "facebook_reels"]),
        readiness_state="needs human review",
        notes="",
        external_source=provider,
        external_id=provider_job_id,
        sync_status="generated",
        staleness_state="fresh",
        review_state="needs review",
        asset_role=VIDEO_ASSET_ROLE,
        brand_safe="review",
        generated_prompt=prompt,
        source_asset_id=source.id,
        mime_type="video/mp4",
    )
    if record.id is None:
        session.add(record)
    record.product_id = product.id
    record.asset_type = VIDEO_ASSET_TYPE
    record.asset_role = VIDEO_ASSET_ROLE
    record.external_source = provider
    record.external_id = provider_job_id
    record.generated_prompt = prompt
    record.source_asset_id = source.id
    record.mime_type = "video/mp4"
    record.preview_path = poster.as_posix() if poster else record.preview_path
    record.readiness_state = "needs human review"
    record.review_state = "needs review"
    record.notes = (notes.strip() + "\n\n" if notes.strip() else "") + json.dumps(metadata, indent=2)
    session.flush()
    refresh_asset_file_state(session, asset_ids=[record.id])
    return record


def register_video_job_output(
    session: Session,
    job_id: int,
    video_path: str | Path,
    title: str = "",
    poster_path: str | Path | None = None,
    provider_job_id: str = "",
    output_url: str = "",
    notes: str = "",
) -> CreativeGenerationJobRecord:
    job = _job_or_raise(session, job_id, VIDEO_JOB_FORMAT)
    product_id = _job_product_id(job)
    if product_id is None:
        raise ValueError("Queued video job is missing a source product.")
    metadata = _json_dict(job.response_metadata_json)
    asset = register_video_output(
        session,
        product_id=product_id,
        source_asset_id=job.source_asset_id,
        video_path=video_path,
        title=title or f"{job.source_asset.product.name if job.source_asset.product else 'Product'} product video",
        prompt=job.prompt,
        poster_path=poster_path,
        provider=job.provider,
        model_name=job.model_name or "bytedance-seedance-pro-2.0",
        provider_job_id=provider_job_id or job.provider_job_id,
        duration_seconds=int(metadata.get("duration_seconds") or 8),
        aspect_ratio=str(metadata.get("aspect_ratio") or "9:16"),
        resolution=str(metadata.get("resolution") or "1080p"),
        notes=notes or "Generated from Art Studio queue; review before use.",
    )
    _complete_job(job, asset, video_path, provider_job_id, output_url)
    return job


def validate_video_motion_prompt(prompt: str) -> dict[str, object]:
    lowered = _prompt_without_negative_section(prompt).lower()
    disallowed = sorted(term for term in FANTASTICAL_MOTION_TERMS if _requests_disallowed_motion(lowered, term))
    missing_negative_terms = [
        term
        for term in ["walking", "riding by itself", "flapping", "talking", "blinking", "transforming"]
        if term not in DEFAULT_VIDEO_NEGATIVE_PROMPT
    ]
    return {
        "passed": not disallowed and not missing_negative_terms,
        "disallowed_motion_terms": disallowed,
        "required_negative_prompt": DEFAULT_VIDEO_NEGATIVE_PROMPT,
        "missing_negative_terms": missing_negative_terms,
    }


def _prompt_without_negative_section(prompt: str) -> str:
    return re.split(r"\n\s*negative prompt\s*:", prompt, maxsplit=1, flags=re.IGNORECASE)[0]


def _requests_disallowed_motion(prompt: str, term: str) -> bool:
    for match in re.finditer(rf"\b{re.escape(term)}\b", prompt):
        prefix = prompt[max(0, match.start() - 18) : match.start()]
        if re.search(r"\b(no|not|never|without|avoid|disallow|forbid)\s+$", prefix):
            continue
        sentence_prefix = prompt[max(0, match.start() - 90) : match.start()]
        negation = re.search(r"\b(no|not|never|without|avoid|disallow|forbid)\b", sentence_prefix)
        if negation and not re.search(r"[.;:]", sentence_prefix[negation.end() :]):
            continue
        return True
    return False


def reusable_art_studio_asset_query():
    return (
        select(AssetRecord)
        .where(AssetRecord.asset_type.in_([SOCIAL_IMAGE_ASSET_TYPE, VIDEO_ASSET_TYPE]))
        .where(AssetRecord.review_state == "approved")
        .where(AssetRecord.file_exists == 1)
        .where(AssetRecord.hidden_from_generation == 0)
    )


def art_studio_provider_status_label(provider_status: str | None) -> str:
    """Operator-facing label for Art Studio provider_status values.

    Social-image jobs drain via Magnific REST when MAGNIFIC_API_KEY is set;
    otherwise they remain Magnific handoffs (attach/import). Video stays handoff-only.
    """
    status = (provider_status or "").strip()
    labels = {
        "queued": "waiting on Magnific",
        "generating": "generating via Magnific API",
        "generated": "imported",
        "canceled": "canceled",
        "planned": "planner brief ready",
        "video_queued": "video handoff queued",
    }
    if status in labels:
        return labels[status]
    return status.replace("_", " ") if status else "unknown"


def serialize_art_studio_job(job: CreativeGenerationJobRecord) -> dict[str, object]:
    return {
        "id": job.id,
        "source_asset_id": job.source_asset_id,
        "candidate_asset_id": job.candidate_asset_id,
        "target_format": job.target_format,
        "provider": job.provider,
        "model_name": job.model_name,
        "prompt": job.prompt,
        "requested_dimensions": job.requested_dimensions,
        "provider_status": job.provider_status,
        "provider_status_label": art_studio_provider_status_label(job.provider_status),
        "provider_job_id": job.provider_job_id,
        "output_url": job.output_url,
        "output_path": job.output_path,
        "response_metadata": _json_dict(job.response_metadata_json),
        "review_state": job.review_state,
        "review_notes": job.review_notes,
        "candidate_asset": _serialize_asset(job.candidate_asset),
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "product"


def _queue_score(
    approved_reference_count: int,
    default_reference_count: int,
    sales_quantity: int,
    approved_generated_count: int,
    generated_count: int,
) -> int:
    coverage_gap = max(0, 3 - approved_generated_count)
    return (
        min(approved_reference_count, 4) * 1000
        + min(default_reference_count, 4) * 350
        + min(sales_quantity, 100) * 8
        + coverage_gap * 160
        - generated_count * 60
    )


def _assets_by_product(session: Session) -> dict[int, list[AssetRecord]]:
    assets = list(session.scalars(select(AssetRecord).where(AssetRecord.product_id.is_not(None)).order_by(AssetRecord.id)))
    grouped: dict[int, list[AssetRecord]] = {}
    for asset in assets:
        if asset.product_id is not None:
            grouped.setdefault(asset.product_id, []).append(asset)
    return grouped


def _jobs_by_product(session: Session) -> dict[int, list[CreativeGenerationJobRecord]]:
    jobs = list(
        session.scalars(
            select(CreativeGenerationJobRecord)
            .where(CreativeGenerationJobRecord.target_format.in_([SOCIAL_JOB_FORMAT, VIDEO_ART_BOARD_JOB_FORMAT, VIDEO_JOB_FORMAT]))
            .order_by(CreativeGenerationJobRecord.created_at.desc(), CreativeGenerationJobRecord.id.desc())
        )
    )
    grouped: dict[int, list[CreativeGenerationJobRecord]] = {}
    for job in jobs:
        product_id = _job_product_id(job)
        if product_id is not None:
            grouped.setdefault(product_id, []).append(job)
    return grouped


def _sales_by_product(session: Session) -> dict[int, int]:
    rows = session.execute(
        select(ProductSalesRecord.product_id, func.coalesce(func.sum(ProductSalesRecord.quantity), 0))
        .where(ProductSalesRecord.product_id.is_not(None))
        .group_by(ProductSalesRecord.product_id)
    ).all()
    return {int(product_id): int(quantity or 0) for product_id, quantity in rows if product_id is not None}


def _can_be_reference(asset: AssetRecord) -> bool:
    return asset.asset_type in SOURCE_ASSET_TYPES and not asset.hidden_from_generation and (asset.file_exists or _is_remote_asset(asset))


def _can_be_video_start(asset: AssetRecord) -> bool:
    return (
        asset.asset_type in {VIDEO_ART_BOARD_ASSET_TYPE, SOCIAL_IMAGE_ASSET_TYPE, POST_IMAGE_ASSET_TYPE, *SOURCE_ASSET_TYPES}
        and not asset.hidden_from_generation
        and bool(asset.file_exists)
        and asset.review_state in {"approved", "needs review"}
    )


def _video_start_assets(assets: list[AssetRecord]) -> list[AssetRecord]:
    candidates = [asset for asset in assets if _can_be_video_start(asset)]
    return sorted(candidates, key=_video_start_rank, reverse=True)


def _video_start_rank(asset: AssetRecord) -> tuple[int, int, int, int]:
    return (
        3
        if asset.asset_type == VIDEO_ART_BOARD_ASSET_TYPE
        else 2
        if asset.asset_type == SOCIAL_IMAGE_ASSET_TYPE
        else 1
        if asset.asset_type == POST_IMAGE_ASSET_TYPE
        else 0,
        1 if asset.review_state == "approved" else 0,
        1
        if asset.asset_role in {VIDEO_ART_BOARD_ROLE, VIDEO_OPENING_CARD_ROLE, VIDEO_ENDING_CARD_ROLE, SOCIAL_IMAGE_ROLE, "post image option"}
        else 0,
        asset.id,
    )


def _is_approved_reference(asset: AssetRecord) -> bool:
    return bool(asset.file_exists and asset.review_state == "approved")


def _is_remote_asset(asset: AssetRecord) -> bool:
    value = asset.source_path or asset.preview_path or asset.canonical_url
    return bool(value.startswith(("http://", "https://", "file://")))


def _reference_roles(references: list[AssetRecord]) -> list[tuple[str, AssetRecord]]:
    labels = [
        "@img1 primary visible product angle",
        "@img2 identity lock side/profile angle",
        "@img3 identity lock detail angle",
        "@img4 identity lock back/top angle",
    ]
    return list(zip(labels, references[:4]))


def _asset_for_path(session: Session, path: Path) -> AssetRecord | None:
    return session.scalar(select(AssetRecord).where(AssetRecord.source_path == path.as_posix()))


def _queued_job(
    session: Session,
    source_asset_id: int,
    target_format: str,
    option_number: int,
    metadata_match: dict[str, object] | None = None,
) -> CreativeGenerationJobRecord | None:
    jobs = list(
        session.scalars(
            select(CreativeGenerationJobRecord)
            .where(CreativeGenerationJobRecord.source_asset_id == source_asset_id)
            .where(CreativeGenerationJobRecord.target_format == target_format)
            .where(CreativeGenerationJobRecord.provider_status == "queued")
            .order_by(CreativeGenerationJobRecord.id.desc())
        )
    )
    for job in jobs:
        metadata = _json_dict(job.response_metadata_json)
        if int(metadata.get("option_number") or 1) == option_number and _metadata_matches(metadata, metadata_match):
            return job
    return None


def _metadata_matches(metadata: dict[str, object], expected: dict[str, object] | None) -> bool:
    if not expected:
        return True
    return all(metadata.get(key) == value for key, value in expected.items())


def _job_or_raise(session: Session, job_id: int, target_format: str) -> CreativeGenerationJobRecord:
    job = session.get(CreativeGenerationJobRecord, job_id)
    if job is None or job.target_format != target_format:
        raise ValueError(f"Art Studio job not found: {job_id}")
    return job


def _complete_job(
    job: CreativeGenerationJobRecord,
    asset: AssetRecord,
    output_path: str | Path,
    provider_job_id: str = "",
    output_url: str = "",
) -> None:
    job.candidate_asset_id = asset.id
    job.provider_status = "generated"
    if provider_job_id:
        job.provider_job_id = provider_job_id
    if output_url:
        job.output_url = output_url
    job.output_path = Path(output_path).expanduser().as_posix()
    job.review_state = "needs_review"
    job.review_notes = "Generated output attached. Review the candidate asset before reuse."


def _job_product_id(job: CreativeGenerationJobRecord) -> int | None:
    return job.source_asset.product_id if job.source_asset is not None else None


def _json_dict(value: str) -> dict[str, object]:
    try:
        data = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _serialize_asset(asset: AssetRecord | None) -> dict[str, object] | None:
    if asset is None:
        return None
    return {
        "id": asset.id,
        "name": asset.name,
        "asset_type": asset.asset_type,
        "asset_role": asset.asset_role,
        "source_path": asset.source_path,
        "preview_path": asset.preview_path,
        "review_state": asset.review_state,
        "file_exists": bool(asset.file_exists),
    }


def _product_or_raise(session: Session, product_id: int) -> ProductRecord:
    product = session.get(ProductRecord, product_id)
    if product is None:
        raise ValueError(f"Product not found: {product_id}")
    return product


def _source_or_raise(session: Session, source_asset_id: int, product_id: int) -> AssetRecord:
    source = session.get(AssetRecord, source_asset_id)
    if source is None:
        raise ValueError(f"Source asset not found: {source_asset_id}")
    if source.product_id != product_id:
        raise ValueError("Source asset must belong to the selected product.")
    if not _can_be_reference(source):
        raise ValueError("Source asset is not eligible as an Art Studio reference.")
    return source


def _references_or_raise(session: Session, source_asset_ids: list[int], product_id: int) -> list[AssetRecord]:
    seen: set[int] = set()
    references: list[AssetRecord] = []
    for asset_id in source_asset_ids:
        if asset_id in seen:
            continue
        seen.add(asset_id)
        references.append(_source_or_raise(session, asset_id, product_id))
    return references[:4]


def _video_source_or_raise(session: Session, source_asset_id: int, product_id: int) -> AssetRecord:
    source = session.get(AssetRecord, source_asset_id)
    if source is None:
        raise ValueError(f"Video start asset not found: {source_asset_id}")
    if source.product_id != product_id:
        raise ValueError("Video start asset must belong to the selected product.")
    if not _can_be_video_start(source):
        raise ValueError("Video start asset must be a local reviewed scene or product reference image.")
    return source


def _assets_for_ids(session: Session, raw_ids: object, product_id: int) -> list[AssetRecord]:
    if not isinstance(raw_ids, list):
        return []
    assets: list[AssetRecord] = []
    for raw_id in raw_ids:
        asset_id = _int_value(raw_id)
        if asset_id is None:
            continue
        asset = session.get(AssetRecord, asset_id)
        if asset is not None and asset.product_id == product_id:
            assets.append(asset)
    return assets


def _job_by_board_role(jobs: list[CreativeGenerationJobRecord], board_role: str) -> CreativeGenerationJobRecord | None:
    for job in jobs:
        metadata = _json_dict(job.response_metadata_json)
        if metadata.get("board_role") == board_role:
            return job
    return None


def _video_request_status(
    request_job: CreativeGenerationJobRecord,
    opening_job: CreativeGenerationJobRecord | None,
    ending_job: CreativeGenerationJobRecord | None,
    video_job: CreativeGenerationJobRecord | None,
) -> tuple[str, str]:
    if request_job.provider_status == "canceled":
        return "canceled", "Canceled"
    if video_job is not None and video_job.candidate_asset_id is not None:
        return "complete", "Complete"
    if video_job is not None:
        return "video_queued", "Video handoff queued"
    metadata = _json_dict(request_job.response_metadata_json)
    ending_required = bool(metadata.get("ending_card_required"))
    if _job_has_candidate(opening_job) and (not ending_required or _job_has_candidate(ending_job)):
        return "ready_for_approval", "Ready for video approval"
    if opening_job is not None or ending_job is not None:
        return "cards_in_progress", "Waiting on Magnific scene card"
    return "queued", "Handoff queued"


def _job_has_candidate(job: CreativeGenerationJobRecord | None) -> bool:
    return bool(job is not None and job.candidate_asset_id is not None and job.provider_status == "generated")


def _int_value(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
