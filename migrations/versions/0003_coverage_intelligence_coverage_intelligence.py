"""coverage intelligence and catalog monitor

Revision ID: 0003_coverage_intelligence
Revises: 0002_growth_contracts
Create Date: 2026-07-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0003_coverage_intelligence"
down_revision: Union[str, None] = "0002_growth_contracts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "product_identities",
        sa.Column(
            "mapping_revision",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_table(
        "search_intents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("intent_key", sa.String(length=240), nullable=False),
        sa.Column("normalized_query", sa.String(length=260), nullable=False),
        sa.Column("audience", sa.String(length=200), nullable=False),
        sa.Column("occasion", sa.String(length=200), nullable=False),
        sa.Column("locale", sa.String(length=40), nullable=False),
        sa.Column("season_key", sa.String(length=120), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column("evidence_state", sa.String(length=40), nullable=False),
        sa.Column("confidence_bps", sa.Integer(), nullable=False),
        sa.Column("evidence_ids_json", sa.Text(), nullable=False),
        sa.Column("product_ids_json", sa.Text(), nullable=False),
        sa.Column("revision_hash", sa.String(length=64), nullable=False),
        sa.Column("lifecycle_state", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("intent_key"),
    )
    op.create_index(
        "ix_search_intents_state_season",
        "search_intents",
        ["lifecycle_state", "season_key"],
        unique=False,
    )
    op.create_index(
        "ix_search_intents_query_locale",
        "search_intents",
        ["normalized_query", "locale"],
        unique=False,
    )

    op.create_table(
        "landing_pages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("website_id", sa.String(length=180), nullable=False),
        sa.Column("page_type", sa.String(length=40), nullable=False),
        sa.Column("canonical_path", sa.String(length=400), nullable=False),
        sa.Column("canonical_url", sa.String(length=500), nullable=False),
        sa.Column("website_revision", sa.String(length=160), nullable=False),
        sa.Column("website_product_ids_json", sa.Text(), nullable=False),
        sa.Column("product_ids_json", sa.Text(), nullable=False),
        sa.Column("intent_keys_json", sa.Text(), nullable=False),
        sa.Column("lifecycle_state", sa.String(length=40), nullable=False),
        sa.Column("readiness_state", sa.String(length=40), nullable=False),
        sa.Column("readiness_reason", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("checked_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_path"),
        sa.UniqueConstraint("website_id"),
    )
    op.create_index(
        "ix_landing_pages_type_readiness",
        "landing_pages",
        ["page_type", "readiness_state"],
        unique=False,
    )

    op.create_table(
        "catalog_changes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_name", sa.String(length=120), nullable=False),
        sa.Column("source_revision", sa.String(length=160), nullable=False),
        sa.Column("source_product_id", sa.String(length=180), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("change_type", sa.String(length=40), nullable=False),
        sa.Column("before_hash", sa.String(length=64), nullable=False),
        sa.Column("after_hash", sa.String(length=64), nullable=False),
        sa.Column("deduplication_key", sa.String(length=240), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("detected_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("deduplication_key"),
    )
    op.create_index(
        "ix_catalog_changes_source_revision",
        "catalog_changes",
        ["source_name", "source_revision"],
        unique=False,
    )
    op.create_index(
        "ix_catalog_changes_product_time",
        "catalog_changes",
        ["product_id", "detected_at"],
        unique=False,
    )

    op.create_table(
        "catalog_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_name", sa.String(length=120), nullable=False),
        sa.Column("source_revision", sa.String(length=160), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("product_count", sa.Integer(), nullable=False),
        sa.Column("completeness_state", sa.String(length=40), nullable=False),
        sa.Column("product_hashes_json", sa.Text(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_name"),
    )

    op.create_table(
        "coverage_cells",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dimensional_key", sa.String(length=240), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("search_intent_id", sa.Integer(), nullable=False),
        sa.Column("season_key", sa.String(length=120), nullable=False),
        sa.Column("content_format", sa.String(length=80), nullable=False),
        sa.Column("landing_page_id", sa.Integer(), nullable=True),
        sa.Column("channel", sa.String(length=80), nullable=False),
        sa.Column("coverage_state", sa.String(length=40), nullable=False),
        sa.Column("freshness_state", sa.String(length=40), nullable=False),
        sa.Column("suppression_state", sa.String(length=40), nullable=False),
        sa.Column("suppression_reason", sa.Text(), nullable=False),
        sa.Column("source_revision", sa.String(length=160), nullable=False),
        sa.Column("explanation_json", sa.Text(), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["landing_page_id"], ["landing_pages.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["search_intent_id"], ["search_intents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dimensional_key"),
    )
    op.create_index(
        "ix_coverage_cells_product_state",
        "coverage_cells",
        ["product_id", "coverage_state"],
        unique=False,
    )
    op.create_index(
        "ix_coverage_cells_intent_channel",
        "coverage_cells",
        ["search_intent_id", "channel"],
        unique=False,
    )
    op.create_index(
        "ix_coverage_cells_exception",
        "coverage_cells",
        ["suppression_state", "freshness_state"],
        unique=False,
    )

    op.create_table(
        "decision_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_key", sa.String(length=240), nullable=False),
        sa.Column("run_type", sa.String(length=80), nullable=False),
        sa.Column("input_revision", sa.String(length=160), nullable=False),
        sa.Column("score_version", sa.String(length=40), nullable=False),
        sa.Column("considered_count", sa.Integer(), nullable=False),
        sa.Column("selected_count", sa.Integer(), nullable=False),
        sa.Column("suppressed_count", sa.Integer(), nullable=False),
        sa.Column("explanation_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_key"),
    )
    op.create_index(
        "ix_decision_runs_type_time",
        "decision_runs",
        ["run_type", "created_at"],
        unique=False,
    )

    op.create_table(
        "page_opportunities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("coverage_cell_id", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(length=80), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("score_version", sa.String(length=40), nullable=False),
        sa.Column("score_components_json", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("target_ready_date", sa.Date(), nullable=True),
        sa.Column("lifecycle_state", sa.String(length=40), nullable=False),
        sa.Column("scored_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["coverage_cell_id"], ["coverage_cells.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("coverage_cell_id"),
    )
    op.create_index(
        "ix_page_opportunities_rank",
        "page_opportunities",
        ["lifecycle_state", "score"],
        unique=False,
    )

    op.create_table(
        "publication_opportunities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("coverage_cell_id", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(length=80), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("score_version", sa.String(length=40), nullable=False),
        sa.Column("score_components_json", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("eligible", sa.Boolean(), nullable=False),
        sa.Column("eligibility_reason", sa.Text(), nullable=False),
        sa.Column("publish_start_date", sa.Date(), nullable=True),
        sa.Column("lifecycle_state", sa.String(length=40), nullable=False),
        sa.Column("scored_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["coverage_cell_id"], ["coverage_cells.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("coverage_cell_id"),
    )
    op.create_index(
        "ix_publication_opportunities_rank",
        "publication_opportunities",
        ["eligible", "lifecycle_state", "score"],
        unique=False,
    )

    op.create_table(
        "measurement_cursors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_name", sa.String(length=120), nullable=False),
        sa.Column("opaque_cursor", sa.Text(), nullable=False),
        sa.Column("last_event_key", sa.String(length=240), nullable=False),
        sa.Column("last_source_at", sa.DateTime(), nullable=True),
        sa.Column("ingested_count", sa.Integer(), nullable=False),
        sa.Column("checkpointed_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_name"),
    )

    op.create_table(
        "coverage_outcomes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("outcome_key", sa.String(length=240), nullable=False),
        sa.Column("coverage_cell_id", sa.Integer(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("landing_page_id", sa.Integer(), nullable=True),
        sa.Column("metric_name", sa.String(length=80), nullable=False),
        sa.Column("maturity_window", sa.String(length=40), nullable=False),
        sa.Column("observed_value", sa.Integer(), nullable=False),
        sa.Column("attribution_quality", sa.String(length=40), nullable=False),
        sa.Column("inference_kind", sa.String(length=40), nullable=False),
        sa.Column("period_start", sa.DateTime(), nullable=False),
        sa.Column("period_end", sa.DateTime(), nullable=False),
        sa.Column("source_revision", sa.String(length=160), nullable=False),
        sa.Column("explanation_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["coverage_cell_id"], ["coverage_cells.id"]),
        sa.ForeignKeyConstraint(["landing_page_id"], ["landing_pages.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("outcome_key"),
    )
    op.create_index(
        "ix_coverage_outcomes_product_metric",
        "coverage_outcomes",
        ["product_id", "metric_name", "period_end"],
        unique=False,
    )
    op.create_index(
        "ix_coverage_outcomes_cell_metric",
        "coverage_outcomes",
        ["coverage_cell_id", "metric_name", "period_end"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_coverage_outcomes_cell_metric", table_name="coverage_outcomes")
    op.drop_index("ix_coverage_outcomes_product_metric", table_name="coverage_outcomes")
    op.drop_table("coverage_outcomes")
    op.drop_table("measurement_cursors")
    op.drop_index("ix_publication_opportunities_rank", table_name="publication_opportunities")
    op.drop_table("publication_opportunities")
    op.drop_index("ix_page_opportunities_rank", table_name="page_opportunities")
    op.drop_table("page_opportunities")
    op.drop_index("ix_decision_runs_type_time", table_name="decision_runs")
    op.drop_table("decision_runs")
    op.drop_index("ix_coverage_cells_exception", table_name="coverage_cells")
    op.drop_index("ix_coverage_cells_intent_channel", table_name="coverage_cells")
    op.drop_index("ix_coverage_cells_product_state", table_name="coverage_cells")
    op.drop_table("coverage_cells")
    op.drop_index("ix_catalog_changes_product_time", table_name="catalog_changes")
    op.drop_index("ix_catalog_changes_source_revision", table_name="catalog_changes")
    op.drop_table("catalog_changes")
    op.drop_table("catalog_snapshots")
    op.drop_index("ix_landing_pages_type_readiness", table_name="landing_pages")
    op.drop_table("landing_pages")
    op.drop_index("ix_search_intents_query_locale", table_name="search_intents")
    op.drop_index("ix_search_intents_state_season", table_name="search_intents")
    op.drop_table("search_intents")
    op.drop_column("product_identities", "mapping_revision")
