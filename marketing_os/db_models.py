from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
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
    secondary_audiences_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    best_channels_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    use_cases_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    seasonality_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    sales_momentum_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
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


class ProductSalesRecord(Base):
    __tablename__ = "product_sales"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    source_name: Mapped[str] = mapped_column(String(80), nullable=False)
    external_id: Mapped[str] = mapped_column(String(220), nullable=False)
    listing_id: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    listing_title: Mapped[str] = mapped_column(String(260), default="", nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    revenue_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency_code: Mapped[str] = mapped_column(String(12), default="", nullable=False)
    sold_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    raw_data_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    product: Mapped[ProductRecord | None] = relationship()

    __table_args__ = (UniqueConstraint("source_name", "external_id", name="uq_product_sales_source_id"),)


class EtsyReviewRecord(Base):
    __tablename__ = "etsy_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    external_source: Mapped[str] = mapped_column(String(80), default="etsy_api", nullable=False)
    external_id: Mapped[str] = mapped_column(String(220), nullable=False)
    shop_id: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    listing_id: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    transaction_id: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    buyer_user_id: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review: Mapped[str] = mapped_column(Text, default="", nullable=False)
    language: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    image_url_fullxfull: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    created_timestamp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_timestamp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_data_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    product: Mapped[ProductRecord | None] = relationship()

    __table_args__ = (UniqueConstraint("external_source", "external_id", name="uq_etsy_review_source_id"),)


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
    default_reference: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hidden_from_generation: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

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
    scheduled_time: Mapped[str] = mapped_column(String(5), default="09:00", nullable=False)
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
    scheduled_time: Mapped[str] = mapped_column(String(5), default="09:00", nullable=False)
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


class PrincipalRecord(Base):
    __tablename__ = "principals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    principal_type: Mapped[str] = mapped_column(String(40), nullable=False)
    username: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, default="", nullable=False)
    roles_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    sessions: Mapped[list["OperatorSessionRecord"]] = relationship(
        back_populates="principal", cascade="all, delete-orphan"
    )
    service_credentials: Mapped[list["ServiceCredentialRecord"]] = relationship(
        back_populates="principal", cascade="all, delete-orphan"
    )


class OperatorSessionRecord(Base):
    __tablename__ = "operator_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    principal_id: Mapped[int] = mapped_column(ForeignKey("principals.id"), nullable=False)
    session_token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    csrf_token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoke_reason: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    user_agent_hash: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    remote_address_hash: Mapped[str] = mapped_column(String(128), default="", nullable=False)

    principal: Mapped[PrincipalRecord] = relationship(back_populates="sessions")

    __table_args__ = (
        Index("ix_operator_sessions_principal_active", "principal_id", "revoked_at"),
        Index("ix_operator_sessions_expiry", "idle_expires_at", "absolute_expires_at"),
    )


class ServiceCredentialRecord(Base):
    __tablename__ = "service_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    principal_id: Mapped[int] = mapped_column(ForeignKey("principals.id"), nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    scopes_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    description: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoke_reason: Mapped[str] = mapped_column(String(240), default="", nullable=False)

    principal: Mapped[PrincipalRecord] = relationship(back_populates="service_credentials")


class AuditEventRecord(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    principal_id: Mapped[int | None] = mapped_column(ForeignKey("principals.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    target_type: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    target_id: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    detail_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        Index("ix_audit_events_created_type", "created_at", "event_type"),
        Index("ix_audit_events_correlation", "correlation_id"),
    )


class AutomationRunRecord(Base):
    __tablename__ = "automation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_type: Mapped[str] = mapped_column(String(120), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(80), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    state: Mapped[str] = mapped_column(String(40), default="running", nullable=False)
    input_revision: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    queued_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    succeeded_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    dead_letter_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    summary_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    jobs: Mapped[list["AutomationJobRecord"]] = relationship(back_populates="run")


class AutomationJobRecord(Base):
    __tablename__ = "automation_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("automation_runs.id"), nullable=True)
    job_type: Mapped[str] = mapped_column(String(120), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    state: Mapped[str] = mapped_column(String(40), default="queued", nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(240), unique=True, nullable=True)
    lease_owner: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    result_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    last_error_code: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    run: Mapped[AutomationRunRecord | None] = relationship(back_populates="jobs")

    __table_args__ = (
        Index("ix_automation_jobs_claim", "state", "scheduled_at", "priority", "id"),
        Index("ix_automation_jobs_lease", "state", "lease_expires_at"),
        Index("ix_automation_jobs_correlation", "correlation_id"),
    )


class ProductIdentityRecord(Base):
    __tablename__ = "product_identities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), unique=True, nullable=False)
    website_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    website_slug: Mapped[str] = mapped_column(String(220), default="", nullable=False)
    etsy_listing_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    mapping_state: Mapped[str] = mapped_column(String(40), default="unresolved", nullable=False)
    mapping_revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    exception_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    product: Mapped[ProductRecord] = relationship()

    __table_args__ = (
        Index("ix_product_identities_mapping_state", "mapping_state"),
        UniqueConstraint("website_id", name="uq_product_identity_website_id"),
        UniqueConstraint("etsy_listing_id", name="uq_product_identity_etsy_listing_id"),
    )


class DemandEvidenceRecord(Base):
    __tablename__ = "demand_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_name: Mapped[str] = mapped_column(String(120), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(80), nullable=False)
    topic: Mapped[str] = mapped_column(String(260), nullable=False)
    deduplication_key: Mapped[str] = mapped_column(String(240), unique=True, nullable=False)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[str] = mapped_column(String(40), default="unknown", nullable=False)
    evidence_state: Mapped[str] = mapped_column(String(40), default="observed", nullable=False)
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    raw_data_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    __table_args__ = (
        Index("ix_demand_evidence_source_time", "source_name", "source_timestamp"),
        Index("ix_demand_evidence_topic_state", "topic", "evidence_state"),
    )


class GrowthEventRecord(Base):
    __tablename__ = "growth_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    campaign_id: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    content_id: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    publication_id: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    session_id: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    source_timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    attribution_quality: Mapped[str] = mapped_column(String(40), default="unknown", nullable=False)
    destination_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    product: Mapped[ProductRecord | None] = relationship()

    __table_args__ = (
        Index("ix_growth_events_type_source_time", "event_type", "source_timestamp"),
        Index("ix_growth_events_campaign_content", "campaign_id", "content_id"),
    )


class SearchIntentRecord(Base):
    __tablename__ = "search_intents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    intent_key: Mapped[str] = mapped_column(String(240), unique=True, nullable=False)
    normalized_query: Mapped[str] = mapped_column(String(260), nullable=False)
    audience: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    occasion: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    locale: Mapped[str] = mapped_column(String(40), default="en-US", nullable=False)
    season_key: Mapped[str] = mapped_column(String(120), default="evergreen", nullable=False)
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    evidence_state: Mapped[str] = mapped_column(String(40), default="hypothesis", nullable=False)
    confidence_bps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    evidence_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    product_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    revision_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    __table_args__ = (
        Index("ix_search_intents_state_season", "lifecycle_state", "season_key"),
        Index("ix_search_intents_query_locale", "normalized_query", "locale"),
    )


class LandingPageRecord(Base):
    __tablename__ = "landing_pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    website_id: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    page_type: Mapped[str] = mapped_column(String(40), nullable=False)
    canonical_path: Mapped[str] = mapped_column(String(400), unique=True, nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    website_revision: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    website_product_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    product_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    intent_keys_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(String(40), default="draft", nullable=False)
    readiness_state: Mapped[str] = mapped_column(String(40), default="not_ready", nullable=False)
    readiness_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    __table_args__ = (Index("ix_landing_pages_type_readiness", "page_type", "readiness_state"),)


class CatalogChangeRecord(Base):
    __tablename__ = "catalog_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    source_product_id: Mapped[str] = mapped_column(String(180), nullable=False)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    change_type: Mapped[str] = mapped_column(String(40), nullable=False)
    before_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    after_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    deduplication_key: Mapped[str] = mapped_column(String(240), unique=True, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    product: Mapped[ProductRecord | None] = relationship()

    __table_args__ = (
        Index("ix_catalog_changes_source_revision", "source_name", "source_revision"),
        Index("ix_catalog_changes_product_time", "product_id", "detected_at"),
    )


class CatalogSnapshotRecord(Base):
    __tablename__ = "catalog_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    source_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    product_count: Mapped[int] = mapped_column(Integer, nullable=False)
    completeness_state: Mapped[str] = mapped_column(String(40), nullable=False)
    product_hashes_json: Mapped[str] = mapped_column(Text, nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)


class CoverageCellRecord(Base):
    __tablename__ = "coverage_cells"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dimensional_key: Mapped[str] = mapped_column(String(240), unique=True, nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    search_intent_id: Mapped[int] = mapped_column(ForeignKey("search_intents.id"), nullable=False)
    season_key: Mapped[str] = mapped_column(String(120), default="evergreen", nullable=False)
    content_format: Mapped[str] = mapped_column(String(80), nullable=False)
    landing_page_id: Mapped[int | None] = mapped_column(ForeignKey("landing_pages.id"), nullable=True)
    channel: Mapped[str] = mapped_column(String(80), default="pinterest", nullable=False)
    coverage_state: Mapped[str] = mapped_column(String(40), default="missing", nullable=False)
    freshness_state: Mapped[str] = mapped_column(String(40), default="unknown", nullable=False)
    suppression_state: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    suppression_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source_revision: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    explanation_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    last_observed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    product: Mapped[ProductRecord] = relationship()
    search_intent: Mapped[SearchIntentRecord] = relationship()
    landing_page: Mapped[LandingPageRecord | None] = relationship()

    __table_args__ = (
        Index("ix_coverage_cells_product_state", "product_id", "coverage_state"),
        Index("ix_coverage_cells_intent_channel", "search_intent_id", "channel"),
        Index("ix_coverage_cells_exception", "suppression_state", "freshness_state"),
    )


class PageOpportunityRecord(Base):
    __tablename__ = "page_opportunities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    coverage_cell_id: Mapped[int] = mapped_column(ForeignKey("coverage_cells.id"), unique=True, nullable=False)
    action_type: Mapped[str] = mapped_column(String(80), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    score_version: Mapped[str] = mapped_column(String(40), nullable=False)
    score_components_json: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    target_ready_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    lifecycle_state: Mapped[str] = mapped_column(String(40), default="ranked", nullable=False)
    scored_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    coverage_cell: Mapped[CoverageCellRecord] = relationship()

    __table_args__ = (Index("ix_page_opportunities_rank", "lifecycle_state", "score"),)


class PublicationOpportunityRecord(Base):
    __tablename__ = "publication_opportunities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    coverage_cell_id: Mapped[int] = mapped_column(ForeignKey("coverage_cells.id"), unique=True, nullable=False)
    action_type: Mapped[str] = mapped_column(String(80), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    score_version: Mapped[str] = mapped_column(String(40), nullable=False)
    score_components_json: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    eligible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    eligibility_reason: Mapped[str] = mapped_column(Text, nullable=False)
    publish_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    lifecycle_state: Mapped[str] = mapped_column(String(40), default="ranked", nullable=False)
    scored_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    coverage_cell: Mapped[CoverageCellRecord] = relationship()

    __table_args__ = (
        Index("ix_publication_opportunities_rank", "eligible", "lifecycle_state", "score"),
    )


class DecisionRunRecord(Base):
    __tablename__ = "decision_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_key: Mapped[str] = mapped_column(String(240), unique=True, nullable=False)
    run_type: Mapped[str] = mapped_column(String(80), nullable=False)
    input_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    score_version: Mapped[str] = mapped_column(String(40), nullable=False)
    considered_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    selected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    suppressed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    explanation_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    __table_args__ = (Index("ix_decision_runs_type_time", "run_type", "created_at"),)


class MeasurementCursorRecord(Base):
    __tablename__ = "measurement_cursors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    opaque_cursor: Mapped[str] = mapped_column(Text, default="", nullable=False)
    last_event_key: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    last_source_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ingested_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    checkpointed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)


class CoverageOutcomeRecord(Base):
    __tablename__ = "coverage_outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    outcome_key: Mapped[str] = mapped_column(String(240), unique=True, nullable=False)
    coverage_cell_id: Mapped[int | None] = mapped_column(ForeignKey("coverage_cells.id"), nullable=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    landing_page_id: Mapped[int | None] = mapped_column(ForeignKey("landing_pages.id"), nullable=True)
    metric_name: Mapped[str] = mapped_column(String(80), nullable=False)
    maturity_window: Mapped[str] = mapped_column(String(40), nullable=False)
    observed_value: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attribution_quality: Mapped[str] = mapped_column(String(40), default="unknown", nullable=False)
    inference_kind: Mapped[str] = mapped_column(String(40), default="observational", nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    source_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    explanation_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    coverage_cell: Mapped[CoverageCellRecord | None] = relationship()
    product: Mapped[ProductRecord | None] = relationship()
    landing_page: Mapped[LandingPageRecord | None] = relationship()

    __table_args__ = (
        Index("ix_coverage_outcomes_product_metric", "product_id", "metric_name", "period_end"),
        Index("ix_coverage_outcomes_cell_metric", "coverage_cell_id", "metric_name", "period_end"),
    )


class ShadowCampaignRecord(Base):
    __tablename__ = "shadow_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    coverage_cell_id: Mapped[int] = mapped_column(ForeignKey("coverage_cells.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    landing_page_id: Mapped[int | None] = mapped_column(ForeignKey("landing_pages.id"), nullable=True)
    decision_run_id: Mapped[int | None] = mapped_column(ForeignKey("decision_runs.id"), nullable=True)
    source_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    repository_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    adapter_provenance_json: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(String(40), nullable=False)
    page_artifact_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    coverage_cell: Mapped[CoverageCellRecord] = relationship()
    product: Mapped[ProductRecord] = relationship()
    landing_page: Mapped[LandingPageRecord | None] = relationship()
    decision_run: Mapped[DecisionRunRecord | None] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "coverage_cell_id",
            "input_hash",
            name="uq_shadow_campaign_input",
        ),
        CheckConstraint(
            "lifecycle_state IN ('generating','blocked','ready_for_review','reviewed','superseded')",
            name="ck_shadow_campaign_lifecycle",
        ),
        Index("ix_shadow_campaigns_state_created", "lifecycle_state", "created_at"),
    )


class ShadowPublicationRecord(Base):
    __tablename__ = "shadow_publications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("shadow_campaigns.id"), nullable=False)
    content_id: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    publication_id: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    variant_role: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    board_recommendation: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    canonical_destination_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    tracked_destination_url: Mapped[str] = mapped_column(String(800), default="", nullable=False)
    page_artifact_json: Mapped[str] = mapped_column(Text, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(String(60), nullable=False)
    superseded_by_id: Mapped[int | None] = mapped_column(ForeignKey("shadow_publications.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    campaign: Mapped[ShadowCampaignRecord] = relationship()

    __table_args__ = (
        UniqueConstraint("campaign_id", "variant_role", name="uq_shadow_publication_variant"),
        CheckConstraint(
            "variant_role IN ('search_exact','gift_context','audience_context')",
            name="ck_shadow_publication_variant",
        ),
        CheckConstraint(
            "lifecycle_state IN ('generating','blocked','ready_for_review','reviewed','superseded')",
            name="ck_shadow_publication_lifecycle",
        ),
        Index("ix_shadow_publications_state_created", "lifecycle_state", "created_at"),
        Index("ix_shadow_publications_payload_hash", "payload_hash"),
    )


class ShadowCreativeManifestRecord(Base):
    __tablename__ = "shadow_creative_manifests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    publication_id: Mapped[int] = mapped_column(ForeignKey("shadow_publications.id"), nullable=False)
    option_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    source_asset_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    source_checksums_json: Mapped[str] = mapped_column(Text, nullable=False)
    review_asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    review_asset_origin: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    provider_path: Mapped[str] = mapped_column(String(120), nullable=False)
    model_preference: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    negative_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    crop_ratio: Mapped[str] = mapped_column(String(20), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_output_path: Mapped[str] = mapped_column(String(500), nullable=False)
    generation_state: Mapped[str] = mapped_column(String(60), nullable=False)
    provenance_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    publication: Mapped[ShadowPublicationRecord] = relationship()
    review_asset: Mapped[AssetRecord | None] = relationship()

    __table_args__ = (
        UniqueConstraint("publication_id", "option_number", name="uq_shadow_manifest_option"),
        CheckConstraint("option_number > 0", name="ck_shadow_manifest_option_positive"),
        CheckConstraint(
            "crop_ratio = '2:3' AND width = 1000 AND height = 1500",
            name="ck_shadow_manifest_dimensions",
        ),
    )


class ShadowQADecisionRecord(Base):
    __tablename__ = "shadow_qa_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("shadow_campaigns.id"), nullable=True)
    publication_id: Mapped[int | None] = mapped_column(ForeignKey("shadow_publications.id"), nullable=True)
    manifest_id: Mapped[int | None] = mapped_column(ForeignKey("shadow_creative_manifests.id"), nullable=True)
    gate_name: Mapped[str] = mapped_column(String(100), nullable=False)
    gate_version: Mapped[str] = mapped_column(String(60), nullable=False)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_codes_json: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "result IN ('pass','fail','not_evaluated')",
            name="ck_shadow_qa_result",
        ),
        Index("ix_shadow_qa_campaign_gate", "campaign_id", "gate_name"),
        Index("ix_shadow_qa_publication_gate", "publication_id", "gate_name"),
        Index("ix_shadow_qa_result_created", "result", "created_at"),
    )


class ShadowReviewSessionRecord(Base):
    __tablename__ = "shadow_review_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_token: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("shadow_campaigns.id"), nullable=False)
    reviewer: Mapped[str] = mapped_column(String(160), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    elapsed_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "elapsed_seconds IS NULL OR elapsed_seconds >= 0",
            name="ck_shadow_review_elapsed",
        ),
        Index("ix_shadow_review_sessions_campaign", "campaign_id", "started_at"),
    )


class ShadowReviewDecisionRecord(Base):
    __tablename__ = "shadow_review_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("shadow_review_sessions.id"), nullable=False)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("shadow_campaigns.id"), nullable=False)
    publication_id: Mapped[int | None] = mapped_column(ForeignKey("shadow_publications.id"), nullable=True)
    manifest_id: Mapped[int | None] = mapped_column(ForeignKey("shadow_creative_manifests.id"), nullable=True)
    review_asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    decision_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    result: Mapped[str] = mapped_column(String(40), nullable=False)
    reason_codes_json: Mapped[str] = mapped_column(Text, nullable=False)
    reviewer_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    reviewed_payload_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    reviewed_manifest_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    reviewed_request_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "decision_kind IN ('copy','board','destination','creative','package')",
            name="ck_shadow_review_decision_kind",
        ),
        CheckConstraint(
            "result IN ('accepted_for_shadow','revise','rejected','exception')",
            name="ck_shadow_review_result",
        ),
        Index("ix_shadow_review_decisions_session", "session_id", "decided_at"),
        Index("ix_shadow_review_decisions_campaign", "campaign_id", "decision_kind"),
        Index("ix_shadow_review_decisions_publication", "publication_id", "decision_kind"),
    )


class ShadowPayloadLeaseRecord(Base):
    __tablename__ = "shadow_payload_leases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    publication_id: Mapped[int] = mapped_column(ForeignKey("shadow_publications.id"), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (Index("ix_shadow_payload_leases_active", "released_at", "superseded_at"),)


class ShadowDigestRecord(Base):
    __tablename__ = "shadow_digests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    utc_week: Mapped[date] = mapped_column(Date, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ready_count: Mapped[int] = mapped_column(Integer, nullable=False)
    blocked_count: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("utc_week", "input_hash", name="uq_shadow_digest_week_input"),
        Index("ix_shadow_digests_week", "utc_week"),
    )


class PinterestConnectionRecord(Base):
    __tablename__ = "pinterest_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_reference: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    credential_reference: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    access_tier: Mapped[str] = mapped_column(String(40), default="unknown", nullable=False)
    scopes_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    approved_board_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    connection_state: Mapped[str] = mapped_column(String(40), default="disabled", nullable=False)
    provider_contract_version: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "access_tier IN ('unknown','trial','standard')",
            name="ck_pinterest_connection_access_tier",
        ),
        CheckConstraint(
            "connection_state IN ('disabled','fixture_only','verified','revoked','error')",
            name="ck_pinterest_connection_state",
        ),
    )


class PinterestAuthorityGrantRecord(Base):
    __tablename__ = "pinterest_authority_grants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_class: Mapped[str] = mapped_column(String(120), nullable=False)
    principal_id: Mapped[int] = mapped_column(ForeignKey("principals.id"), nullable=False)
    scope_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    principal: Mapped[PrincipalRecord] = relationship()

    __table_args__ = (
        CheckConstraint(
            "state IN ('active','revoked','expired')",
            name="ck_pinterest_authority_grant_state",
        ),
        Index(
            "ix_pinterest_authority_grants_policy_expiry",
            "policy_class",
            "state",
            "expires_at",
        ),
    )


class PinterestMediaDeliveryRecord(Base):
    __tablename__ = "pinterest_media_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("pinterest_connections.id"), nullable=False)
    review_asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), nullable=False)
    media_url: Mapped[str] = mapped_column(String(800), nullable=False)
    content_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    content_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    delivery_state: Mapped[str] = mapped_column(String(40), nullable=False)
    verification_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    connection: Mapped[PinterestConnectionRecord] = relationship()
    review_asset: Mapped[AssetRecord] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "review_asset_id",
            "content_checksum",
            "content_revision",
            name="uq_pinterest_media_delivery_revision",
        ),
        CheckConstraint(
            "delivery_state IN ('fixture_verified','verified','revoked','error')",
            name="ck_pinterest_media_delivery_state",
        ),
        Index("ix_pinterest_media_delivery_state", "delivery_state", "verified_at"),
    )


class PinterestPublicationRecord(Base):
    __tablename__ = "pinterest_publications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shadow_publication_id: Mapped[int] = mapped_column(
        ForeignKey("shadow_publications.id"), unique=True, nullable=False
    )
    connection_id: Mapped[int] = mapped_column(ForeignKey("pinterest_connections.id"), nullable=False)
    approval_decision_id: Mapped[int] = mapped_column(
        ForeignKey("shadow_review_decisions.id"), nullable=False
    )
    media_delivery_id: Mapped[int] = mapped_column(
        ForeignKey("pinterest_media_deliveries.id"), nullable=False
    )
    external_idempotency_key: Mapped[str] = mapped_column(String(240), unique=True, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    board_id: Mapped[str] = mapped_column(String(160), nullable=False)
    external_pin_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    lifecycle_state: Mapped[str] = mapped_column(String(40), default="prepared", nullable=False)
    provider_request_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    provider_response_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    last_error_code: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    shadow_publication: Mapped[ShadowPublicationRecord] = relationship()
    connection: Mapped[PinterestConnectionRecord] = relationship()
    approval_decision: Mapped[ShadowReviewDecisionRecord] = relationship()
    media_delivery: Mapped[PinterestMediaDeliveryRecord] = relationship()

    __table_args__ = (
        CheckConstraint(
            "lifecycle_state IN "
            "('prepared','submitted','published','publish_unknown','confirmed_absent',"
            "'failed','unpublished')",
            name="ck_pinterest_publication_lifecycle",
        ),
        Index("ix_pinterest_publications_state_updated", "lifecycle_state", "updated_at"),
        Index("ix_pinterest_publications_external_pin", "external_pin_id"),
        UniqueConstraint(
            "connection_id",
            "external_pin_id",
            name="uq_pinterest_publication_connection_pin",
        ),
    )


class PinterestPublishAttemptRecord(Base):
    __tablename__ = "pinterest_publish_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pinterest_publication_id: Mapped[int] = mapped_column(
        ForeignKey("pinterest_publications.id"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_status: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    provider_response_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    error_code: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    claimed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    claim_expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    publication: Mapped[PinterestPublicationRecord] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "pinterest_publication_id",
            "attempt_number",
            name="uq_pinterest_publish_attempt",
        ),
        CheckConstraint(
            "state IN ('submitted','published','ambiguous','retryable_failure','failed')",
            name="ck_pinterest_publish_attempt_state",
        ),
        CheckConstraint("attempt_number > 0", name="ck_pinterest_publish_attempt_positive"),
    )


class PinterestReconciliationRecord(Base):
    __tablename__ = "pinterest_reconciliations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pinterest_publication_id: Mapped[int] = mapped_column(
        ForeignKey("pinterest_publications.id"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    result: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_response_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    publication: Mapped[PinterestPublicationRecord] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "pinterest_publication_id",
            "attempt_number",
            name="uq_pinterest_reconciliation_attempt",
        ),
        CheckConstraint(
            "result IN ('published','absent','still_unknown','provider_error')",
            name="ck_pinterest_reconciliation_result",
        ),
        CheckConstraint("attempt_number > 0", name="ck_pinterest_reconciliation_attempt_positive"),
    )


class PinterestPerformanceSnapshotRecord(Base):
    __tablename__ = "pinterest_performance_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pinterest_publication_id: Mapped[int] = mapped_column(
        ForeignKey("pinterest_publications.id"), nullable=False
    )
    source_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    impressions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    saves: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pin_clicks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    outbound_clicks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_metrics_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    publication: Mapped[PinterestPublicationRecord] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "pinterest_publication_id",
            "window_start",
            "window_end",
            "source_revision",
            name="uq_pinterest_snapshot_window_revision",
        ),
        CheckConstraint("window_end > window_start", name="ck_pinterest_snapshot_window"),
        CheckConstraint(
            "impressions >= 0 AND saves >= 0 AND pin_clicks >= 0 AND outbound_clicks >= 0",
            name="ck_pinterest_snapshot_nonnegative",
        ),
        Index("ix_pinterest_snapshots_publication_window", "pinterest_publication_id", "window_end"),
    )
