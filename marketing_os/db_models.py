from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
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
