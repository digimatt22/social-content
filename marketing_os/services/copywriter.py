from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FacebookPostDraft:
    hook: str
    body: str
    cta: str
    quality_checklist: list[str]


@dataclass(frozen=True)
class CopyQualityScore:
    passed: list[str]
    warnings: list[str]


def generate_facebook_post(brief: dict[str, object]) -> FacebookPostDraft:
    """Create a reviewable Facebook draft from a structured content brief.

    This is a deterministic local copywriter for the first Phase 5 slice. The
    nightly Codex job can replace or refine this text, while the app keeps the
    same review/data model.
    """
    products = [str(item) for item in brief.get("products", []) if str(item).strip()]
    goals = [str(item) for item in brief.get("goals", []) if str(item).strip()]
    audience = str(brief.get("audience") or "collectors and gift buyers")
    occasion = _public_context_value(str(brief.get("occasion") or ""))
    promotion = _public_context_value(str(brief.get("promotion") or ""))
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
            "Keeps internal planning notes out of public-facing copy.",
            "Includes a natural comment-friendly CTA.",
            "Needs human review before posting.",
        ],
    )


def score_copy_against_voice(copy: str, context: dict[str, object]) -> CopyQualityScore:
    """Run deterministic review checks before a human reads generated copy."""
    normalized_copy = copy.lower()
    passed: list[str] = []
    warnings: list[str] = []

    products = [str(item).strip() for item in context.get("products", []) if str(item).strip()]
    if products and any(product.lower() in normalized_copy for product in products):
        passed.append("Names at least one planned product.")
    else:
        warnings.append("Does not name a planned product.")

    if "?" in copy or "tell me" in normalized_copy or "reply" in normalized_copy:
        passed.append("Includes a comment-friendly CTA.")
    else:
        warnings.append("CTA may not invite an easy Facebook response.")

    if len(copy) <= 900:
        passed.append("Fits a concise Facebook post length.")
    else:
        warnings.append("May be too long for a first Facebook draft.")

    if copy.count("#") <= 3:
        passed.append("Avoids hashtag stuffing.")
    else:
        warnings.append("Uses more than three hashtags.")

    notes = str(context.get("notes") or "").strip()
    if notes and notes.lower() in normalized_copy:
        warnings.append("Includes internal planning notes in public-facing copy.")
    else:
        passed.append("Keeps internal planning notes out of public-facing copy.")

    internal_terms = ["phase 5", "proof draft", "review-ready", "readiness", "internal", "planning note"]
    leaked_terms = [term for term in internal_terms if term in normalized_copy]
    if leaked_terms:
        warnings.append("Includes internal workflow wording: " + ", ".join(leaked_terms) + ".")
    else:
        passed.append("Keeps internal workflow labels out of public-facing copy.")

    avoid_terms = [str(item).strip() for item in context.get("avoid", []) if str(item).strip()]
    unsupported_terms = ["rubber duck", "licensed", "official disney", "guaranteed bestseller"]
    flagged = [term for term in [*avoid_terms, *unsupported_terms] if term.lower() in normalized_copy]
    if flagged:
        warnings.append("May include avoided or unsupported wording: " + ", ".join(flagged[:5]) + ".")
    else:
        passed.append("Avoids known unsupported or off-brand wording.")

    if _sounds_specific(copy, products):
        passed.append("Uses product-specific wording instead of a generic promo shell.")
    else:
        warnings.append("Could use more product-specific detail.")

    return CopyQualityScore(passed=passed, warnings=warnings)


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


def _public_context_value(value: str) -> str:
    text = value.strip()
    normalized = text.lower()
    internal_markers = ["phase ", "proof", "review-ready", "readiness", "internal", "test fixture"]
    if any(marker in normalized for marker in internal_markers):
        return ""
    return text


def _sounds_specific(copy: str, products: list[str]) -> bool:
    normalized_copy = copy.lower()
    if products and any(product.lower() in normalized_copy for product in products):
        return True
    specific_markers = ["duck", "3d", "printed", "gift", "collector", "shop", "flock"]
    return sum(1 for marker in specific_markers if marker in normalized_copy) >= 2
