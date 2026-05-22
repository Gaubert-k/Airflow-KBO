"""MS-05 MVP — enterprises, states, raw_documents, snapshots, discoveries.

Revision ID: 20260520_0001
Revises:
Create Date: 2026-05-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260520_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "enterprises",
        sa.Column("enterprise_number", sa.String(length=10), nullable=False),
        sa.Column(
            "seed_source",
            sa.Enum("CSV", "DISCOVERED", name="seed_source", native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("enterprise_number"),
    )
    op.create_table(
        "enterprise_processing_state",
        sa.Column("enterprise_number", sa.String(length=10), nullable=False),
        sa.Column(
            "state",
            sa.Enum(
                "NEW",
                "QUEUED_SCRAPE",
                "SCRAPING",
                "RAW_STORED",
                "QUEUED_PARSE",
                "PARSING",
                "STRUCTURED",
                "FAILED_SCRAPE",
                "FAILED_PARSE",
                "FAILED_VALIDATE",
                name="processing_state",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "state_since",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("lock_owner", sa.String(length=128), nullable=True),
        sa.Column("lock_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(
            ["enterprise_number"],
            ["enterprises.enterprise_number"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("enterprise_number"),
    )
    op.create_index(
        "ix_eps_state_state_since",
        "enterprise_processing_state",
        ["state", "state_since"],
    )
    op.create_table(
        "raw_documents",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("enterprise_number", sa.String(length=10), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("doc_type", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("hdfs_dir", sa.Text(), nullable=False),
        sa.Column("document_path", sa.Text(), nullable=False),
        sa.Column("metadata_path", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=False),
        sa.Column("download_status", sa.String(length=32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "status",
            sa.Enum("STORED", "FAILED", "SKIPPED", name="raw_document_status", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "created_at",
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
        sa.UniqueConstraint(
            "enterprise_number",
            "source",
            "doc_type",
            "run_id",
            name="uq_raw_documents_idempotency",
        ),
    )
    op.create_index(
        "ix_raw_documents_enterprise_scraped",
        "raw_documents",
        ["enterprise_number", "scraped_at"],
    )
    op.create_table(
        "enterprise_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("enterprise_number", sa.String(length=10), nullable=False),
        sa.Column(
            "snapshot_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["enterprise_number"],
            ["enterprises.enterprise_number"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_snapshots_enterprise_at",
        "enterprise_snapshots",
        ["enterprise_number", "snapshot_at"],
    )
    op.create_table(
        "enterprise_discoveries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source_enterprise_number", sa.String(length=10), nullable=False),
        sa.Column("discovered_enterprise_number", sa.String(length=10), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
        sa.Column(
            "discovered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["discovered_enterprise_number"],
            ["enterprises.enterprise_number"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_enterprise_number",
            "discovered_enterprise_number",
            name="uq_enterprise_discoveries_pair",
        ),
    )
    op.create_index("ix_discoveries_discovered_at", "enterprise_discoveries", ["discovered_at"])


def downgrade() -> None:
    op.drop_index("ix_discoveries_discovered_at", table_name="enterprise_discoveries")
    op.drop_table("enterprise_discoveries")
    op.drop_index("ix_snapshots_enterprise_at", table_name="enterprise_snapshots")
    op.drop_table("enterprise_snapshots")
    op.drop_index("ix_raw_documents_enterprise_scraped", table_name="raw_documents")
    op.drop_table("raw_documents")
    op.drop_index("ix_eps_state_state_since", table_name="enterprise_processing_state")
    op.drop_table("enterprise_processing_state")
    op.drop_table("enterprises")
