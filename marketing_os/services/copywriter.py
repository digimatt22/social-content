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
    product_facts = [item for item in brief.get("product_facts", []) if isinstance(item, dict)]

    product_text = _join_human(products) or "a new MattMadeMe duck"
    goal_text = _goal_phrase(goals)
    use_case = _first_fact_value(product_facts, "use_cases") or "desk mascot, small gift, or collection-shelf surprise"
    momentum = _first_fact_value(product_facts, "sales_momentum_note")
    phrase = _clean_sentence(useful_phrases[0]) if useful_phrases else "Made to make someone smile"

    hook = f"{product_text} is having a moment."
    lines = [
        f"This one works nicely as a {use_case}, especially for {audience.lower()}.",
    ]
    if momentum:
        lines.append(_sentence(momentum))
    if occasion:
        lines.append(f"I pulled it forward for {_occasion_phrase(occasion)} because it has that easy little giftable spark.")
    if promotion:
        lines.append(f"Current note: {promotion}.")
    lines.append(_sentence(phrase))
    if notes:
        lines.append(f"Planning note: {notes}")

    cta = _cta_for_goal(goal_text)
    body = "\n\n".join([*lines, cta])
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


def _first_fact_value(product_facts: list[dict[object, object]], key: str) -> str:
    for fact in product_facts:
        value = fact.get(key)
        if isinstance(value, list) and value:
            return str(value[0]).strip()
        if isinstance(value, str) and value.strip():
            return _clean_sentence(value)
    return ""


def _goal_phrase(goals: list[str]) -> str:
    normalized = {goal.lower() for goal in goals}
    if "sales growth" in normalized:
        return "sales growth"
    if "followers" in normalized:
        return "followers"
    if "repeat customers" in normalized:
        return "repeat customers"
    return _join_human(goals).lower() if goals else "engagement"


def _cta_for_goal(goal_text: str) -> str:
    if goal_text == "sales growth":
        return "Take a look in the shop, and tell me who this one reminds you of."
    if goal_text == "followers":
        return "Follow along if you want to see the next duck off the printer."
    return "Tell me where this duck should show up next."


def _clean_sentence(value: str) -> str:
    text = value.strip()
    return text[:-1] if text.endswith(".") else text


def _sentence(value: str) -> str:
    text = value.strip()
    return text if text.endswith((".", "!", "?")) else f"{text}."


def _occasion_phrase(value: str) -> str:
    text = value.strip().lower()
    if text.startswith(("a ", "an ", "the ", "this ", "that ")):
        return text
    return f"this {text}"
