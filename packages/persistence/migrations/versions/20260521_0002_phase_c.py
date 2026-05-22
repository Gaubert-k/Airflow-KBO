"""Phase C — lifecycle history, pipeline events, analytics tables.

Revision ID: 20260521_0002
Revises: 20260520_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260521_0002"
down_revision: str | None = "20260520_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "enterprise_lifecycle_history",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("enterprise_number", sa.String(length=10), nullable=False),
        sa.Column("business_status", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["enterprise_number"],
            ["enterprises.enterprise_number"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_lifecycle_enterprise_at",
        "enterprise_lifecycle_history",
        ["enterprise_number", "recorded_at"],
    )
    op.create_table(
        "pipeline_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pipeline_events_type_at", "pipeline_events", ["event_type", "created_at"])
    op.create_table(
        "analytics_postal_summary",
        sa.Column("postal_code", sa.String(length=8), nullable=False),
        sa.Column("enterprise_count", sa.Integer(), nullable=False),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("postal_code"),
    )
    op.create_table(
        "analytics_state_summary",
        sa.Column("business_status", sa.String(length=32), nullable=False),
        sa.Column("enterprise_count", sa.Integer(), nullable=False),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("business_status"),
    )
    op.create_table(
        "analytics_activity_rank",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("nace_code", sa.String(length=16), nullable=False),
        sa.Column("activity_label", sa.String(length=512), nullable=True),
        sa.Column("enterprise_count", sa.Integer(), nullable=False),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("analytics_activity_rank")
    op.drop_table("analytics_state_summary")
    op.drop_table("analytics_postal_summary")
    op.drop_index("ix_pipeline_events_type_at", table_name="pipeline_events")
    op.drop_table("pipeline_events")
    op.drop_index("ix_lifecycle_enterprise_at", table_name="enterprise_lifecycle_history")
    op.drop_table("enterprise_lifecycle_history")
