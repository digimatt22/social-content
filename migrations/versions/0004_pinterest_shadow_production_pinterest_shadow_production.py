"""pinterest shadow production

Revision ID: 0004_pinterest_shadow_production
Revises: 0003_coverage_intelligence
Create Date: 2026-07-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0004_pinterest_shadow_production"
down_revision: Union[str, None] = "0003_coverage_intelligence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shadow_campaigns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.String(160), nullable=False),
        sa.Column("coverage_cell_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("landing_page_id", sa.Integer(), nullable=True),
        sa.Column("decision_run_id", sa.Integer(), nullable=True),
        sa.Column("source_revision", sa.String(160), nullable=False),
        sa.Column("repository_revision", sa.String(160), nullable=False),
        sa.Column("policy_version", sa.String(80), nullable=False),
        sa.Column("adapter_provenance_json", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.String(80), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("lifecycle_state", sa.String(40), nullable=False),
        sa.Column("page_artifact_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["coverage_cell_id"], ["coverage_cells.id"]),
        sa.ForeignKeyConstraint(["decision_run_id"], ["decision_runs.id"]),
        sa.ForeignKeyConstraint(["landing_page_id"], ["landing_pages.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.CheckConstraint(
            "lifecycle_state IN ('generating','blocked','ready_for_review','reviewed','superseded')",
            name="ck_shadow_campaign_lifecycle",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id"),
        sa.UniqueConstraint(
            "coverage_cell_id", "input_hash", name="uq_shadow_campaign_input",
        ),
    )
    op.create_index("ix_shadow_campaigns_state_created", "shadow_campaigns", ["lifecycle_state", "created_at"])

    op.create_table(
        "shadow_publications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("content_id", sa.String(160), nullable=False),
        sa.Column("publication_id", sa.String(160), nullable=False),
        sa.Column("variant_role", sa.String(60), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("board_recommendation", sa.String(200), nullable=False),
        sa.Column("canonical_destination_url", sa.String(500), nullable=False),
        sa.Column("tracked_destination_url", sa.String(800), nullable=False),
        sa.Column("page_artifact_json", sa.Text(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("lifecycle_state", sa.String(60), nullable=False),
        sa.Column("superseded_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["shadow_campaigns.id"]),
        sa.ForeignKeyConstraint(["superseded_by_id"], ["shadow_publications.id"]),
        sa.CheckConstraint(
            "variant_role IN ('search_exact','gift_context','audience_context')",
            name="ck_shadow_publication_variant",
        ),
        sa.CheckConstraint(
            "lifecycle_state IN ('generating','blocked','ready_for_review','reviewed','superseded')",
            name="ck_shadow_publication_lifecycle",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_id"),
        sa.UniqueConstraint("publication_id"),
        sa.UniqueConstraint("campaign_id", "variant_role", name="uq_shadow_publication_variant"),
    )
    op.create_index("ix_shadow_publications_state_created", "shadow_publications", ["lifecycle_state", "created_at"])
    op.create_index("ix_shadow_publications_payload_hash", "shadow_publications", ["payload_hash"])

    op.create_table(
        "shadow_creative_manifests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("publication_id", sa.Integer(), nullable=False),
        sa.Column("option_number", sa.Integer(), nullable=False),
        sa.Column("source_asset_ids_json", sa.Text(), nullable=False),
        sa.Column("source_checksums_json", sa.Text(), nullable=False),
        sa.Column("review_asset_id", sa.Integer(), nullable=True),
        sa.Column("review_asset_origin", sa.String(60), nullable=False),
        sa.Column("provider_path", sa.String(120), nullable=False),
        sa.Column("model_preference", sa.String(120), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("negative_prompt", sa.Text(), nullable=False),
        sa.Column("crop_ratio", sa.String(20), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("expected_output_path", sa.String(500), nullable=False),
        sa.Column("generation_state", sa.String(60), nullable=False),
        sa.Column("provenance_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["publication_id"], ["shadow_publications.id"]),
        sa.ForeignKeyConstraint(["review_asset_id"], ["assets.id"]),
        sa.CheckConstraint("option_number > 0", name="ck_shadow_manifest_option_positive"),
        sa.CheckConstraint(
            "crop_ratio = '2:3' AND width = 1000 AND height = 1500",
            name="ck_shadow_manifest_dimensions",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("publication_id", "option_number", name="uq_shadow_manifest_option"),
    )

    op.create_table(
        "shadow_qa_decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=True),
        sa.Column("publication_id", sa.Integer(), nullable=True),
        sa.Column("manifest_id", sa.Integer(), nullable=True),
        sa.Column("gate_name", sa.String(100), nullable=False),
        sa.Column("gate_version", sa.String(60), nullable=False),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column("reason_codes_json", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["manifest_id"], ["shadow_creative_manifests.id"]),
        sa.ForeignKeyConstraint(["campaign_id"], ["shadow_campaigns.id"]),
        sa.ForeignKeyConstraint(["publication_id"], ["shadow_publications.id"]),
        sa.CheckConstraint(
            "result IN ('pass','fail','not_evaluated')",
            name="ck_shadow_qa_result",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shadow_qa_campaign_gate", "shadow_qa_decisions", ["campaign_id", "gate_name"])
    op.create_index("ix_shadow_qa_publication_gate", "shadow_qa_decisions", ["publication_id", "gate_name"])
    op.create_index("ix_shadow_qa_result_created", "shadow_qa_decisions", ["result", "created_at"])

    op.create_table(
        "shadow_review_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_token", sa.String(160), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("reviewer", sa.String(160), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("elapsed_seconds", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["shadow_campaigns.id"]),
        sa.CheckConstraint(
            "elapsed_seconds IS NULL OR elapsed_seconds >= 0",
            name="ck_shadow_review_elapsed",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_token"),
    )
    op.create_index("ix_shadow_review_sessions_campaign", "shadow_review_sessions", ["campaign_id", "started_at"])

    op.create_table(
        "shadow_review_decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("publication_id", sa.Integer(), nullable=True),
        sa.Column("manifest_id", sa.Integer(), nullable=True),
        sa.Column("review_asset_id", sa.Integer(), nullable=True),
        sa.Column("decision_kind", sa.String(40), nullable=False),
        sa.Column("result", sa.String(40), nullable=False),
        sa.Column("reason_codes_json", sa.Text(), nullable=False),
        sa.Column("reviewer_note", sa.Text(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["manifest_id"], ["shadow_creative_manifests.id"]),
        sa.ForeignKeyConstraint(["campaign_id"], ["shadow_campaigns.id"]),
        sa.ForeignKeyConstraint(["publication_id"], ["shadow_publications.id"]),
        sa.ForeignKeyConstraint(["review_asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["shadow_review_sessions.id"]),
        sa.CheckConstraint(
            "decision_kind IN ('copy','board','destination','creative','package')",
            name="ck_shadow_review_decision_kind",
        ),
        sa.CheckConstraint(
            "result IN ('accepted_for_shadow','revise','rejected','exception')",
            name="ck_shadow_review_result",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shadow_review_decisions_session", "shadow_review_decisions", ["session_id", "decided_at"])
    op.create_index("ix_shadow_review_decisions_campaign", "shadow_review_decisions", ["campaign_id", "decision_kind"])
    op.create_index("ix_shadow_review_decisions_publication", "shadow_review_decisions", ["publication_id", "decision_kind"])

    op.create_table(
        "shadow_payload_leases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("publication_id", sa.Integer(), nullable=False),
        sa.Column("acquired_at", sa.DateTime(), nullable=False),
        sa.Column("released_at", sa.DateTime(), nullable=True),
        sa.Column("superseded_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["publication_id"], ["shadow_publications.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payload_hash"),
    )
    op.create_index("ix_shadow_payload_leases_active", "shadow_payload_leases", ["released_at", "superseded_at"])

    op.create_table(
        "shadow_digests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("utc_week", sa.Date(), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("ready_count", sa.Integer(), nullable=False),
        sa.Column("blocked_count", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("utc_week", "input_hash", name="uq_shadow_digest_week_input"),
    )
    op.create_index("ix_shadow_digests_week", "shadow_digests", ["utc_week"])


def downgrade() -> None:
    op.drop_index("ix_shadow_digests_week", table_name="shadow_digests")
    op.drop_table("shadow_digests")
    op.drop_index("ix_shadow_payload_leases_active", table_name="shadow_payload_leases")
    op.drop_table("shadow_payload_leases")
    op.drop_index("ix_shadow_review_decisions_publication", table_name="shadow_review_decisions")
    op.drop_index("ix_shadow_review_decisions_campaign", table_name="shadow_review_decisions")
    op.drop_index("ix_shadow_review_decisions_session", table_name="shadow_review_decisions")
    op.drop_table("shadow_review_decisions")
    op.drop_index("ix_shadow_review_sessions_campaign", table_name="shadow_review_sessions")
    op.drop_table("shadow_review_sessions")
    op.drop_index("ix_shadow_qa_result_created", table_name="shadow_qa_decisions")
    op.drop_index("ix_shadow_qa_publication_gate", table_name="shadow_qa_decisions")
    op.drop_index("ix_shadow_qa_campaign_gate", table_name="shadow_qa_decisions")
    op.drop_table("shadow_qa_decisions")
    op.drop_table("shadow_creative_manifests")
    op.drop_index("ix_shadow_publications_payload_hash", table_name="shadow_publications")
    op.drop_index("ix_shadow_publications_state_created", table_name="shadow_publications")
    op.drop_table("shadow_publications")
    op.drop_index("ix_shadow_campaigns_state_created", table_name="shadow_campaigns")
    op.drop_table("shadow_campaigns")
