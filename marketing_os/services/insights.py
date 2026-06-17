from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db_models import MetricRecord, TaskRecord
from ..phase3 import json_list


@dataclass(frozen=True)
class PatternSummary:
    name: str
    count: int
    average_score: float
    total_score: float
    notes: list[str]


@dataclass(frozen=True)
class CandidateOutcome:
    candidate_id: int
    candidate_type: str
    provider: str
    task_id: int
    task_title: str
    channel: str
    product_name: str
    asset_id: int | None
    score: float
    outcome_tags: list[str]
    notes: str
    review_state: str


@dataclass(frozen=True)
class LearningSummary:
    metrics_count: int
    linked_metric_count: int
    top_channels: list[PatternSummary]
    top_products: list[PatternSummary]
    top_ctas: list[PatternSummary]
    top_assets: list[PatternSummary]
    generated_candidate_outcomes: list[CandidateOutcome]
    what_worked: list[str]
    what_to_improve: list[str]
    needs_more_data: list[str]


POSITIVE_TAGS = {"sold item", "got comments", "good story angle", "good image", "repeat customer", "saved", "shared"}
NEGATIVE_TAGS = {"no engagement", "bad image", "wrong audience", "weak cta", "stale product", "rewrite"}


def build_learning_summary(session: Session) -> LearningSummary:
    metrics = list(session.scalars(select(MetricRecord).order_by(MetricRecord.recorded_on.desc(), MetricRecord.id.desc())))
    task_scores: list[tuple[TaskRecord, MetricRecord, float]] = []
    for metric in metrics:
        if metric.task:
            task_scores.append((metric.task, metric, metric_score(metric)))

    linked = [(task, metric, score) for task, metric, score in task_scores if task.generated_content_candidate_id]
    candidate_outcomes = [_candidate_outcome(task, metric, score) for task, metric, score in linked if task.generated_content_candidate]

    what_worked = _what_worked(task_scores, candidate_outcomes)
    what_to_improve = _what_to_improve(task_scores)
    needs_more_data = _needs_more_data(task_scores, linked)

    return LearningSummary(
        metrics_count=len(metrics),
        linked_metric_count=len(linked),
        top_channels=_summarize_patterns((task.platform, metric, score) for task, metric, score in task_scores),
        top_products=_summarize_patterns((task.product_name or "Unassigned product", metric, score) for task, metric, score in task_scores),
        top_ctas=_summarize_patterns((task.cta or "No CTA", metric, score) for task, metric, score in task_scores),
        top_assets=_summarize_patterns((f"Asset #{task.asset_id}" if task.asset_id else "No asset attached", metric, score) for task, metric, score in task_scores),
        generated_candidate_outcomes=candidate_outcomes,
        what_worked=what_worked,
        what_to_improve=what_to_improve,
        needs_more_data=needs_more_data,
    )


def serialize_learning_summary(summary: LearningSummary) -> dict[str, object]:
    return {
        "metrics_count": summary.metrics_count,
        "linked_metric_count": summary.linked_metric_count,
        "top_channels": [_pattern_dict(pattern) for pattern in summary.top_channels],
        "top_products": [_pattern_dict(pattern) for pattern in summary.top_products],
        "top_ctas": [_pattern_dict(pattern) for pattern in summary.top_ctas],
        "top_assets": [_pattern_dict(pattern) for pattern in summary.top_assets],
        "generated_candidate_outcomes": [
            {
                "candidate_id": outcome.candidate_id,
                "candidate_type": outcome.candidate_type,
                "provider": outcome.provider,
                "task_id": outcome.task_id,
                "task_title": outcome.task_title,
                "channel": outcome.channel,
                "product_name": outcome.product_name,
                "asset_id": outcome.asset_id,
                "score": outcome.score,
                "outcome_tags": outcome.outcome_tags,
                "notes": outcome.notes,
                "review_state": outcome.review_state,
            }
            for outcome in summary.generated_candidate_outcomes
        ],
        "what_worked": summary.what_worked,
        "what_to_improve": summary.what_to_improve,
        "needs_more_data": summary.needs_more_data,
    }


def brief_performance_context(session: Session) -> dict[str, object]:
    summary = build_learning_summary(session)
    return {
        "what_worked": summary.what_worked[:3],
        "what_to_improve": summary.what_to_improve[:3],
        "needs_more_data": summary.needs_more_data[:3],
        "top_channels": [_pattern_dict(pattern) for pattern in summary.top_channels[:3]],
        "top_products": [_pattern_dict(pattern) for pattern in summary.top_products[:3]],
    }


def metric_score(metric: MetricRecord) -> float:
    return float(
        (metric.reach or 0) * 0.1
        + (metric.likes or 0) * 2
        + (metric.comments or 0) * 5
        + (metric.shares or 0) * 6
        + (metric.saves or 0) * 4
        + (metric.etsy_visits or 0) * 1.5
        + (metric.etsy_orders or 0) * 30
        + (metric.email_signups or 0) * 20
    )


def outcome_tags(metric: MetricRecord) -> list[str]:
    return json_list(metric.outcome_tags_json)


def _candidate_outcome(task: TaskRecord, metric: MetricRecord, score: float) -> CandidateOutcome:
    candidate = task.generated_content_candidate
    assert candidate is not None
    return CandidateOutcome(
        candidate_id=candidate.id,
        candidate_type=candidate.candidate_type,
        provider=candidate.provider,
        task_id=task.id,
        task_title=task.title,
        channel=task.platform,
        product_name=task.product_name,
        asset_id=task.asset_id,
        score=round(score, 1),
        outcome_tags=outcome_tags(metric),
        notes=metric.notes,
        review_state=candidate.review_state,
    )


def _summarize_patterns(values: Iterable[tuple[str, MetricRecord, float]]) -> list[PatternSummary]:
    grouped: dict[str, list[tuple[MetricRecord, float]]] = {}
    for raw_name, metric, score in values:
        name = str(raw_name or "Unknown").strip() or "Unknown"
        grouped.setdefault(name, []).append((metric, score))

    summaries: list[PatternSummary] = []
    for name, records in grouped.items():
        total = sum(score for _, score in records)
        notes = [metric.notes for metric, _ in records if metric.notes][:3]
        summaries.append(PatternSummary(name=name, count=len(records), average_score=round(total / len(records), 1), total_score=round(total, 1), notes=notes))
    return sorted(summaries, key=lambda item: (item.average_score, item.count), reverse=True)[:5]


def _what_worked(task_scores: list[tuple[TaskRecord, MetricRecord, float]], candidate_outcomes: list[CandidateOutcome]) -> list[str]:
    messages: list[str] = []
    for task, metric, score in task_scores:
        tags = set(outcome_tags(metric))
        if tags & POSITIVE_TAGS or score >= 75:
            detail = _tag_phrase(tags) or f"score {score:.1f}"
            messages.append(f"{task.platform} for {task.product_name or 'unassigned product'} worked: {detail}.")
    for outcome in candidate_outcomes:
        if set(outcome.outcome_tags) & POSITIVE_TAGS:
            messages.append(f"Generated {outcome.candidate_type} #{outcome.candidate_id} has a positive outcome on {outcome.channel}.")
    return _dedupe(messages)[:6]


def _what_to_improve(task_scores: list[tuple[TaskRecord, MetricRecord, float]]) -> list[str]:
    messages: list[str] = []
    for task, metric, score in task_scores:
        tags = set(outcome_tags(metric))
        if tags & NEGATIVE_TAGS or score <= 5:
            detail = _tag_phrase(tags) or "low recorded engagement"
            messages.append(f"Review {task.platform} for {task.product_name or 'unassigned product'}: {detail}.")
    return _dedupe(messages)[:6]


def _needs_more_data(task_scores: list[tuple[TaskRecord, MetricRecord, float]], linked: list[tuple[TaskRecord, MetricRecord, float]]) -> list[str]:
    messages: list[str] = []
    if not task_scores:
        messages.append("Record at least one posted-task metric or outcome note to start the learning loop.")
    if task_scores and not linked:
        messages.append("Link posted tasks back to generated copy so Codex can learn which drafts worked.")
    if len(task_scores) < 3:
        messages.append("Collect a few more outcomes before treating top patterns as reliable.")
    return messages


def _pattern_dict(pattern: PatternSummary) -> dict[str, object]:
    return {
        "name": pattern.name,
        "count": pattern.count,
        "average_score": pattern.average_score,
        "total_score": pattern.total_score,
        "notes": pattern.notes,
    }


def _tag_phrase(tags: set[str]) -> str:
    useful = sorted(tag for tag in tags if tag in POSITIVE_TAGS or tag in NEGATIVE_TAGS)
    return ", ".join(useful)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
