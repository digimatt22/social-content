"""pinterest disabled control plane

Revision ID: 0005_pinterest_control_plane
Revises: 0004_pinterest_shadow_production
Create Date: 2026-07-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0005_pinterest_control_plane"
down_revision: Union[str, None] = "0004_pinterest_shadow_production"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "shadow_review_decisions",
        sa.Column("reviewed_payload_hash", sa.String(64), nullable=False, server_default=""),
    )
    op.add_column(
        "shadow_review_decisions",
        sa.Column("reviewed_manifest_hash", sa.String(64), nullable=False, server_default=""),
    )
    op.add_column(
        "shadow_review_decisions",
        sa.Column("reviewed_request_hash", sa.String(64), nullable=False, server_default=""),
    )

    op.create_table(
        "pinterest_connections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_reference", sa.String(160), nullable=False),
        sa.Column("credential_reference", sa.String(240), nullable=False),
        sa.Column("access_tier", sa.String(40), nullable=False),
        sa.Column("scopes_json", sa.Text(), nullable=False),
        sa.Column("approved_board_ids_json", sa.Text(), nullable=False),
        sa.Column("connection_state", sa.String(40), nullable=False),
        sa.Column("provider_contract_version", sa.String(80), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "access_tier IN ('unknown','trial','standard')",
            name="ck_pinterest_connection_access_tier",
        ),
        sa.CheckConstraint(
            "connection_state IN ('disabled','fixture_only','verified','revoked','error')",
            name="ck_pinterest_connection_state",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_reference"),
    )

    op.create_table(
        "pinterest_authority_grants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("policy_class", sa.String(120), nullable=False),
        sa.Column("principal_id", sa.Integer(), nullable=False),
        sa.Column("scope_hash", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["principal_id"], ["principals.id"]),
        sa.CheckConstraint(
            "state IN ('active','revoked','expired')",
            name="ck_pinterest_authority_grant_state",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_pinterest_authority_grants_policy_expiry",
        "pinterest_authority_grants",
        ["policy_class", "state", "expires_at"],
    )

    op.create_table(
        "pinterest_media_deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("review_asset_id", sa.Integer(), nullable=False),
        sa.Column("media_url", sa.String(800), nullable=False),
        sa.Column("content_checksum", sa.String(128), nullable=False),
        sa.Column("content_revision", sa.String(160), nullable=False),
        sa.Column("delivery_state", sa.String(40), nullable=False),
        sa.Column("verification_json", sa.Text(), nullable=False),
        sa.Column("verified_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["pinterest_connections.id"]),
        sa.ForeignKeyConstraint(["review_asset_id"], ["assets.id"]),
        sa.CheckConstraint(
            "delivery_state IN ('fixture_verified','verified','revoked','error')",
            name="ck_pinterest_media_delivery_state",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connection_id",
            "review_asset_id",
            "content_checksum",
            "content_revision",
            name="uq_pinterest_media_delivery_revision",
        ),
    )
    op.create_index(
        "ix_pinterest_media_delivery_state",
        "pinterest_media_deliveries",
        ["delivery_state", "verified_at"],
    )

    op.create_table(
        "pinterest_publications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shadow_publication_id", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("approval_decision_id", sa.Integer(), nullable=False),
        sa.Column("media_delivery_id", sa.Integer(), nullable=False),
        sa.Column("external_idempotency_key", sa.String(240), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("board_id", sa.String(160), nullable=False),
        sa.Column("external_pin_id", sa.String(160), nullable=True),
        sa.Column("external_url", sa.String(500), nullable=True),
        sa.Column("lifecycle_state", sa.String(40), nullable=False),
        sa.Column("provider_request_json", sa.Text(), nullable=False),
        sa.Column("provider_response_json", sa.Text(), nullable=False),
        sa.Column("last_error_code", sa.String(120), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("reconciled_at", sa.DateTime(), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["pinterest_connections.id"]),
        sa.ForeignKeyConstraint(["approval_decision_id"], ["shadow_review_decisions.id"]),
        sa.ForeignKeyConstraint(["media_delivery_id"], ["pinterest_media_deliveries.id"]),
        sa.ForeignKeyConstraint(["shadow_publication_id"], ["shadow_publications.id"]),
        sa.CheckConstraint(
            "lifecycle_state IN "
            "('prepared','submitted','published','publish_unknown','confirmed_absent',"
            "'failed','unpublished')",
            name="ck_pinterest_publication_lifecycle",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_idempotency_key"),
        sa.UniqueConstraint(
            "connection_id",
            "external_pin_id",
            name="uq_pinterest_publication_connection_pin",
        ),
        sa.UniqueConstraint("shadow_publication_id"),
    )
    op.create_index(
        "ix_pinterest_publications_state_updated",
        "pinterest_publications",
        ["lifecycle_state", "updated_at"],
    )
    op.create_index(
        "ix_pinterest_publications_external_pin",
        "pinterest_publications",
        ["external_pin_id"],
    )

    op.create_table(
        "pinterest_publish_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pinterest_publication_id", sa.Integer(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("provider_status", sa.String(40), nullable=False),
        sa.Column("provider_response_json", sa.Text(), nullable=False),
        sa.Column("error_code", sa.String(120), nullable=False),
        sa.Column("claimed_at", sa.DateTime(), nullable=False),
        sa.Column("claim_expires_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["pinterest_publication_id"], ["pinterest_publications.id"]),
        sa.CheckConstraint(
            "state IN ('submitted','published','ambiguous','retryable_failure','failed')",
            name="ck_pinterest_publish_attempt_state",
        ),
        sa.CheckConstraint(
            "attempt_number > 0",
            name="ck_pinterest_publish_attempt_positive",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "pinterest_publication_id",
            "attempt_number",
            name="uq_pinterest_publish_attempt",
        ),
    )

    op.create_table(
        "pinterest_reconciliations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pinterest_publication_id", sa.Integer(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("result", sa.String(40), nullable=False),
        sa.Column("provider_response_json", sa.Text(), nullable=False),
        sa.Column("checked_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["pinterest_publication_id"], ["pinterest_publications.id"]),
        sa.CheckConstraint(
            "result IN ('published','absent','still_unknown','provider_error')",
            name="ck_pinterest_reconciliation_result",
        ),
        sa.CheckConstraint(
            "attempt_number > 0",
            name="ck_pinterest_reconciliation_attempt_positive",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "pinterest_publication_id",
            "attempt_number",
            name="uq_pinterest_reconciliation_attempt",
        ),
    )

    op.create_table(
        "pinterest_performance_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pinterest_publication_id", sa.Integer(), nullable=False),
        sa.Column("source_revision", sa.String(160), nullable=False),
        sa.Column("window_start", sa.DateTime(), nullable=False),
        sa.Column("window_end", sa.DateTime(), nullable=False),
        sa.Column("impressions", sa.Integer(), nullable=False),
        sa.Column("saves", sa.Integer(), nullable=False),
        sa.Column("pin_clicks", sa.Integer(), nullable=False),
        sa.Column("outbound_clicks", sa.Integer(), nullable=False),
        sa.Column("source_payload_hash", sa.String(64), nullable=False),
        sa.Column("raw_metrics_json", sa.Text(), nullable=False),
        sa.Column("ingested_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["pinterest_publication_id"], ["pinterest_publications.id"]),
        sa.CheckConstraint("window_end > window_start", name="ck_pinterest_snapshot_window"),
        sa.CheckConstraint(
            "impressions >= 0 AND saves >= 0 AND pin_clicks >= 0 AND outbound_clicks >= 0",
            name="ck_pinterest_snapshot_nonnegative",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "pinterest_publication_id",
            "window_start",
            "window_end",
            "source_revision",
            name="uq_pinterest_snapshot_window_revision",
        ),
    )
    op.create_index(
        "ix_pinterest_snapshots_publication_window",
        "pinterest_performance_snapshots",
        ["pinterest_publication_id", "window_end"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_pinterest_snapshots_publication_window",
        table_name="pinterest_performance_snapshots",
    )
    op.drop_table("pinterest_performance_snapshots")
    op.drop_table("pinterest_reconciliations")
    op.drop_table("pinterest_publish_attempts")
    op.drop_index("ix_pinterest_publications_external_pin", table_name="pinterest_publications")
    op.drop_index("ix_pinterest_publications_state_updated", table_name="pinterest_publications")
    op.drop_table("pinterest_publications")
    op.drop_index("ix_pinterest_media_delivery_state", table_name="pinterest_media_deliveries")
    op.drop_table("pinterest_media_deliveries")
    op.drop_index(
        "ix_pinterest_authority_grants_policy_expiry",
        table_name="pinterest_authority_grants",
    )
    op.drop_table("pinterest_authority_grants")
    op.drop_table("pinterest_connections")
    op.drop_column("shadow_review_decisions", "reviewed_manifest_hash")
    op.drop_column("shadow_review_decisions", "reviewed_request_hash")
    op.drop_column("shadow_review_decisions", "reviewed_payload_hash")
