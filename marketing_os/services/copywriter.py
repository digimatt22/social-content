from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FacebookPostDraft:
    hook: str
    body: str
    cta: str
    quality_checklist: list[str]


def generate_facebook_post(brief: dict[str, object]) -> FacebookPostDraft:
    """Create a reviewable Facebook draft from a structured content brief.

    This is a deterministic local copywriter for the first Phase 5 slice. The
    nightly Codex job can replace or refine this text, while the app keeps the
    same review/data model.
    """
    products = [str(item) for item in brief.get("products", []) if str(item).strip()]
    goals = [str(item) for item in brief.get("goals", []) if str(item).strip()]
    audience = str(brief.get("audience") or "collectors and gift buyers")
    occasion = str(brief.get("occasion") or "").strip()
    promotion = str(brief.get("promotion") or "").strip()
    notes = str(brief.get("notes") or "").strip()
    voice = [str(item) for item in brief.get("voice_pillars", []) if str(item).strip()]
    useful_phrases = [str(item) for item in brief.get("useful_phrases", []) if str(item).strip()]

    product_text = _join_human(products) or "a new MattMadeMe duck"
    goal_text = _join_human(goals).lower() if goals else "share what makes it fun"
    voice_hint = voice[0].lower() if voice else "playful and handmade"
    phrase = useful_phrases[0] if useful_phrases else "little details make it feel personal"

    hook = f"{product_text} is ready for a little spotlight."
    lines = [
        f"I made this with the kind of {voice_hint} detail that makes a desk, gift box, or collection shelf feel less ordinary.",
        f"It is a good fit for {audience.lower()}, especially when the goal is to {goal_text}.",
    ]
    if occasion:
        lines.append(f"It also has a nice tie-in for {occasion.lower()}.")
    if promotion:
        lines.append(f"Current note: {promotion}.")
    lines.append(f"{phrase}.")
    if notes:
        lines.append(f"Planning note: {notes}")

    cta = "Take a look, and tell me who this one reminds you of."
    body = "\n\n".join([hook, *lines, cta])
    return FacebookPostDraft(
        hook=hook,
        body=body,
        cta=cta,
        quality_checklist=[
            "Uses real product focus from the planned item.",
            "Keeps a conversational Facebook tone.",
            "Avoids unsupported scarcity or sales claims.",
            "Includes a natural comment-friendly CTA.",
            "Needs human review before posting.",
        ],
    )


def _join_human(values: list[str]) -> str:
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return ", ".join(values[:-1]) + f", and {values[-1]}"

