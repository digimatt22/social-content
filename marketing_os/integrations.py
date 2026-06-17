from __future__ import annotations

from typing import Protocol

from .models import CalendarEntry, ContentIdea


class Publisher(Protocol):
    """Future extension point for external publishing integrations."""

    def publish(self, idea: ContentIdea) -> str:
        ...


class AnalyticsProvider(Protocol):
    """Future extension point for Etsy, social, website, or email analytics."""

    def summarize(self) -> dict[str, str | int | float]:
        ...


class MockPublisher:
    """Local mock publisher used in Phase 1 instead of external APIs."""

    def publish(self, idea: ContentIdea) -> str:
        return f"MOCK-PUBLISH {idea.platform}: {idea.title}"


class MockAnalyticsProvider:
    """Local mock analytics provider used until real integrations are added."""

    def summarize(self) -> dict[str, str | int | float]:
        return {
            "source": "mock",
            "status": "No external analytics configured in Phase 1",
        }


class CalendarExporter(Protocol):
    def export(self, entries: list[CalendarEntry]) -> str:
        ...


class MarkdownCalendarExporter:
    def export(self, entries: list[CalendarEntry]) -> str:
        lines = [
            "| Date | Platform | Type | Objective | CTA | Featured Product |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for entry in entries:
            lines.append(
                f"| {entry.date.isoformat()} | {entry.platform} | {entry.content_type} | "
                f"{entry.objective} | {entry.cta} | {entry.featured_product} |"
            )
        return "\n".join(lines)

