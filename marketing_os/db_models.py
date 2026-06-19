from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class SyncMetadata(Base):
    __tablename__ = "sync_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    source_path: Mapped[str] = mapped_column(String(400), nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)


class ProductRecord(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(80), nullable=False)
    primary_audience: Mapped[str] = mapped_column(String(200), nullable=False)
    secondary_audiences_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    best_channels_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    use_cases_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    seasonality_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    sales_momentum_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    launch_priority: Mapped[str] = mapped_column(String(40), default="medium", nullable=False)
    external_source: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    external_id: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sync_status: Mapped[str] = mapped_column(String(80), default="local", nullable=False)
    sync_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    staleness_state: Mapped[str] = mapped_column(String(80), default="unknown", nullable=False)
    manual_override_state: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    manual_override_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    assets: Mapped[list["AssetRecord"]] = relationship(back_populates="product")
    external_references: Mapped[list["ProductExternalReference"]] = relationship(back_populates="product", cascade="all, delete-orphan")


class ProductExternalReference(Base):
    __tablename__ = "product_external_references"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    source_name: Mapped[str] = mapped_column(String(80), nullable=False)
    external_id: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    display_name: Mapped[str] = mapped_column(String(260), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    product: Mapped[ProductRecord] = relationship(back_populates="external_references")

    __table_args__ = (UniqueConstraint("source_name", "external_id", name="uq_product_external_source_id"),)


class TemplateRecord(Base):
    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_type: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    platform: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    format: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    source_path: Mapped[str] = mapped_column(String(400), nullable=False)
    body_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    __table_args__ = (UniqueConstraint("template_type", "name", name="uq_template_type_name"),)


class AssetRecord(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(120), nullable=False)
    source_path: Mapped[str] = mapped_column(String(400), nullable=False)
    preview_path: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    platform_suitability_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    readiness_state: Mapped[str] = mapped_column(String(120), nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    date_added: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    external_source: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    external_id: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sync_status: Mapped[str] = mapped_column(String(80), default="local", nullable=False)
    sync_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    staleness_state: Mapped[str] = mapped_column(String(80), default="unknown", nullable=False)
    manual_override_state: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    manual_override_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    file_exists: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    file_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    file_modified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    file_checksum: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    relative_path: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    asset_role: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    rights: Mapped[str] = mapped_column(String(80), default="unknown", nullable=False)
    brand_safe: Mapped[str] = mapped_column(String(80), default="review", nullable=False)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_state: Mapped[str] = mapped_column(String(80), default="unreviewed", nullable=False)
    approval_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    generated_prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source_asset_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    product: Mapped[ProductRecord | None] = relationship(back_populates="assets")


class BlogPostRecord(Base):
    __tablename__ = "blog_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_source: Mapped[str] = mapped_column(String(80), nullable=False)
    external_id: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(260), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), default="", nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_external_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tags_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    raw_external_data_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sync_status: Mapped[str] = mapped_column(String(80), default="imported", nullable=False)
    sync_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    review_state: Mapped[str] = mapped_column(String(80), default="needs_review", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    __table_args__ = (UniqueConstraint("external_source", "external_id", name="uq_blog_external_source_id"),)


class PlanRecord(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mode: Mapped[str] = mapped_column(String(40), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    weekly_theme: Mapped[str] = mapped_column(Text, nullable=False)
    campaign_narrative: Mapped[str] = mapped_column(Text, nullable=False)
    validation_report_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)

    calendar_items: Mapped[list["CalendarItemRecord"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", order_by="CalendarItemRecord.date"
    )
    tasks: Mapped[list["TaskRecord"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", order_by="TaskRecord.due_date"
    )


class CalendarItemRecord(Base):
    __tablename__ = "calendar_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(String(260), nullable=False)
    platform: Mapped[str] = mapped_column(String(80), nullable=False)
    content_type: Mapped[str] = mapped_column(String(80), nullable=False)
    business_goal: Mapped[str] = mapped_column(String(160), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    target_audience: Mapped[str] = mapped_column(String(160), nullable=False)
    featured_product: Mapped[str] = mapped_column(String(200), nullable=False)
    draft_copy: Mapped[str] = mapped_column(Text, nullable=False)
    cta: Mapped[str] = mapped_column(Text, nullable=False)
    hashtags_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    asset_brief: Mapped[str] = mapped_column(Text, nullable=False)
    asset_type: Mapped[str] = mapped_column(String(120), nullable=False)
    production_notes: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(40), nullable=False)
    effort_estimate: Mapped[str] = mapped_column(String(40), nullable=False)
    expected_impact: Mapped[str] = mapped_column(String(40), nullable=False)
    success_metric: Mapped[str] = mapped_column(Text, nullable=False)

    plan: Mapped[PlanRecord] = relationship(back_populates="calendar_items")
    task: Mapped["TaskRecord | None"] = relationship(back_populates="calendar_item")


class PlannedContentRecord(Base):
    __tablename__ = "planned_content_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    calendar_date: Mapped[date] = mapped_column(Date, nullable=False)
    destinations_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    goals_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    product_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    selected_source_asset_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    audience: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    occasion: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    promotion: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(80), default="planned", nullable=False)
    brief_status: Mapped[str] = mapped_column(String(80), default="pending", nullable=False)
    last_production_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    production_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    candidates: Mapped[list["GeneratedContentCandidateRecord"]] = relationship(
        back_populates="planned_item", cascade="all, delete-orphan", order_by="GeneratedContentCandidateRecord.created_at"
    )


class GeneratedContentCandidateRecord(Base):
    __tablename__ = "generated_content_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    planned_item_id: Mapped[int] = mapped_column(ForeignKey("planned_content_items.id"), nullable=False)
    candidate_type: Mapped[str] = mapped_column(String(80), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), default="codex", nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source_facts_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    source_asset_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    review_state: Mapped[str] = mapped_column(String(80), default="needs_review", nullable=False)
    revision_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    reviewed_by: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    planned_item: Mapped[PlannedContentRecord] = relationship(back_populates="candidates")

    __table_args__ = (UniqueConstraint("planned_item_id", "candidate_type", "provider", name="uq_candidate_planned_type_provider"),)


class CreativeGenerationJobRecord(Base):
    __tablename__ = "creative_generation_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), nullable=False)
    candidate_asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    target_format: Mapped[str] = mapped_column(String(160), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), default="magnific_manual", nullable=False)
    model_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    requested_dimensions: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    provider_job_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    provider_status: Mapped[str] = mapped_column(String(80), default="manual_import", nullable=False)
    provider_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    output_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    output_path: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    response_metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    review_state: Mapped[str] = mapped_column(String(80), default="needs_review", nullable=False)
    review_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    reviewed_by: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    source_asset: Mapped[AssetRecord] = relationship(foreign_keys=[source_asset_id])
    candidate_asset: Mapped[AssetRecord | None] = relationship(foreign_keys=[candidate_asset_id])


class TaskRecord(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), nullable=False)
    calendar_item_id: Mapped[int | None] = mapped_column(ForeignKey("calendar_items.id"), nullable=True)
    planned_content_item_id: Mapped[int | None] = mapped_column(ForeignKey("planned_content_items.id"), nullable=True)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(String(260), nullable=False)
    owner_role: Mapped[str] = mapped_column(String(80), nullable=False)
    platform: Mapped[str] = mapped_column(String(80), nullable=False)
    content_type: Mapped[str] = mapped_column(String(80), nullable=False)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    generated_content_candidate_id: Mapped[int | None] = mapped_column(ForeignKey("generated_content_candidates.id"), nullable=True)
    draft_caption: Mapped[str] = mapped_column(Text, nullable=False)
    cta: Mapped[str] = mapped_column(Text, nullable=False)
    hashtags_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    posting_steps_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    preview_checklist_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    metric_instruction: Mapped[str] = mapped_column(Text, nullable=False)
    published_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    platform_post_id: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    metric_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    metric_status: Mapped[str] = mapped_column(String(80), default="not due", nullable=False)
    external_source: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    external_id: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sync_status: Mapped[str] = mapped_column(String(80), default="local", nullable=False)
    sync_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    staleness_state: Mapped[str] = mapped_column(String(80), default="unknown", nullable=False)
    manual_override_state: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    manual_override_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(80), default="ready to post", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    plan: Mapped[PlanRecord] = relationship(back_populates="tasks")
    calendar_item: Mapped[CalendarItemRecord | None] = relationship(back_populates="task")
    planned_content_item: Mapped[PlannedContentRecord | None] = relationship()
    asset: Mapped[AssetRecord | None] = relationship()
    generated_content_candidate: Mapped[GeneratedContentCandidateRecord | None] = relationship()
    metrics: Mapped[list["MetricRecord"]] = relationship(back_populates="task", cascade="all, delete-orphan")


class MetricRecord(Base):
    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    recorded_on: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    post_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    reach: Mapped[int | None] = mapped_column(Integer, nullable=True)
    likes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comments: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shares: Mapped[int | None] = mapped_column(Integer, nullable=True)
    saves: Mapped[int | None] = mapped_column(Integer, nullable=True)
    etsy_visits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    etsy_orders: Mapped[int | None] = mapped_column(Integer, nullable=True)
    email_signups: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome_tags_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    collection_status: Mapped[str] = mapped_column(String(80), default="recorded", nullable=False)
    external_source: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    external_id: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sync_status: Mapped[str] = mapped_column(String(80), default="manual", nullable=False)
    sync_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    manual_override_state: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    manual_override_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    task: Mapped[TaskRecord] = relationship(back_populates="metrics")
