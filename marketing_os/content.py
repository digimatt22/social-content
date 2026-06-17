from __future__ import annotations

from itertools import cycle, islice

from .models import BusinessContext, ContentIdea


class ContentGenerator:
    def __init__(self, context: BusinessContext):
        self.context = context

    def instagram_posts(self, count: int = 30) -> list[ContentIdea]:
        angles = [
            "show the tiny detail that makes this design giftable",
            "ask followers who would need this duck in their flock",
            "tell a short maker-story about why this duck exists",
            "invite collectors to tag someone who matches the theme",
            "position the duck as a cruise hiding surprise",
        ]
        return self._ideas("Instagram", "post", count, angles, "Browse the Etsy shop")

    def instagram_reels(self, count: int = 10) -> list[ContentIdea]:
        angles = [
            "quick printer-plate reveal into finished duck closeup",
            "before-and-after from digital sculpt to printed collectible",
            "pack an order while naming who this duck is perfect for",
            "show three ducks that belong in the same themed flock",
            "launch teaser with comments voting on the next design",
        ]
        return self._ideas("Instagram", "reel", count, angles, "Follow for the next duck drop")

    def facebook_posts(self, count: int = 30) -> list[ContentIdea]:
        angles = [
            "start a conversation with cruise duck hunters",
            "spotlight a gift use case for a specific audience",
            "invite customer photos and stories",
            "explain custom or bulk event possibilities",
            "highlight a seasonal or launch opportunity",
        ]
        return self._ideas("Facebook", "post", count, angles, "Shop the flock on Etsy")

    def etsy_promotions(self, count: int = 10) -> list[ContentIdea]:
        angles = [
            "refresh listing copy around a proven customer use case",
            "bundle related ducks around a shared audience",
            "feature recent momentum to justify renewed promotion",
            "tie the duck to gift search language",
            "prepare a seasonal promotion window",
        ]
        return self._ideas("Etsy", "promotion", count, angles, "Add it to your cart")

    def blog_topics(self, count: int = 10) -> list[ContentIdea]:
        angles = [
            "explain how to choose cruise ducks for a trip",
            "share the design story behind a duck",
            "round up gift ideas by audience",
            "walk through the maker process",
            "show how collectors can plan a themed flock",
        ]
        return self._ideas("Website", "blog topic", count, angles, "Read the story and shop Etsy")

    def email_newsletters(self, count: int = 10) -> list[ContentIdea]:
        angles = [
            "announce a new duck release to collectors",
            "curate best sellers for gift buyers",
            "share a behind-the-scenes maker update",
            "promote a seasonal shopping window",
            "invite subscribers to vote on upcoming designs",
        ]
        return self._ideas("Email", "newsletter", count, angles, "Join the list and shop the latest ducks")

    def _ideas(self, platform: str, content_type: str, count: int, angles: list[str], default_cta: str) -> list[ContentIdea]:
        products = self.context.momentum_products or self.context.products
        audiences = self.context.audiences
        goals = self.context.business_goals
        if not products or not audiences or not goals:
            raise ValueError("Business context must include products, audiences, and business goals.")

        ideas: list[ContentIdea] = []
        for index, (product, audience, goal, angle) in enumerate(
            islice(zip(cycle(products), cycle(audiences), cycle(goals), cycle(angles)), count),
            start=1,
        ):
            title = f"{platform} {content_type.title()} {index}: {product} for {audience}"
            ideas.append(
                ContentIdea(
                    platform=platform,
                    content_type=content_type,
                    title=title,
                    angle=self._brand_wrap(angle, product, audience),
                    audience=audience,
                    featured_product=product,
                    business_goal=goal,
                    cta=self._cta(default_cta, platform),
                )
            )
        return ideas

    def _brand_wrap(self, angle: str, product: str, audience: str) -> str:
        phrase = (self.context.useful_phrases or ["collectible 3D printed duck"])[0]
        pillar = (self.context.voice_pillars or ["Whimsical"])[0].lower()
        return f"{angle}; keep it {pillar}, maker-led, and centered on {product} as a {phrase} for {audience}."

    def _cta(self, fallback: str, platform: str) -> str:
        if platform == "Etsy":
            return f"{fallback}: {self.context.etsy_url or 'mattmademe.etsy.com'}"
        if platform == "Website":
            return f"{fallback}: {self.context.website_url or 'mattmademe.com'}"
        return fallback

