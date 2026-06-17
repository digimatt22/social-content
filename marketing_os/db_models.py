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
    review_state: Mapped[str] = mapped_column(String(80), default="unreviewed", nullable=False)
    approval_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    generated_prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source_asset_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    product: Mapped[ProductRecord | None] = relationship(back_populates="assets")


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


class TaskRecord(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), nullable=False)
    calendar_item_id: Mapped[int | None] = mapped_column(ForeignKey("calendar_items.id"), nullable=True)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(String(260), nullable=False)
    owner_role: Mapped[str] = mapped_column(String(80), nullable=False)
    platform: Mapped[str] = mapped_column(String(80), nullable=False)
    content_type: Mapped[str] = mapped_column(String(80), nullable=False)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
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
    asset: Mapped[AssetRecord | None] = relationship()
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
