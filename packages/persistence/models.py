"""Modèles ORM MS-05 — schéma MVP gelé."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from packages.persistence.enums import ProcessingState, RawDocumentStatus, SeedSource


class Base(DeclarativeBase):
    pass


class Enterprise(Base):
    __tablename__ = "enterprises"

    enterprise_number: Mapped[str] = mapped_column(String(10), primary_key=True)
    seed_source: Mapped[SeedSource] = mapped_column(
        Enum(SeedSource, name="seed_source", native_enum=False, length=16),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    processing_state: Mapped[EnterpriseProcessingState | None] = relationship(
        back_populates="enterprise",
        uselist=False,
    )


class EnterpriseProcessingState(Base):
    __tablename__ = "enterprise_processing_state"
    __table_args__ = (
        Index("ix_eps_state_state_since", "state", "state_since"),
    )

    enterprise_number: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("enterprises.enterprise_number", ondelete="CASCADE"),
        primary_key=True,
    )
    state: Mapped[ProcessingState] = mapped_column(
        Enum(ProcessingState, name="processing_state", native_enum=False, length=32),
        nullable=False,
        default=ProcessingState.NEW,
    )
    state_since: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    lock_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lock_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    enterprise: Mapped[Enterprise] = relationship(back_populates="processing_state")


class RawDocument(Base):
    __tablename__ = "raw_documents"
    __table_args__ = (
        UniqueConstraint(
            "enterprise_number",
            "source",
            "doc_type",
            "run_id",
            name="uq_raw_documents_idempotency",
        ),
        Index("ix_raw_documents_enterprise_scraped", "enterprise_number", "scraped_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enterprise_number: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("enterprises.enterprise_number", ondelete="CASCADE"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(64), nullable=False)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    hdfs_dir: Mapped[str] = mapped_column(Text, nullable=False)
    document_path: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_path: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    download_status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[RawDocumentStatus] = mapped_column(
        Enum(RawDocumentStatus, name="raw_document_status", native_enum=False, length=16),
        nullable=False,
        default=RawDocumentStatus.STORED,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class EnterpriseSnapshot(Base):
    """Append-only — pas de DELETE métier pour entreprises radiées."""

    __tablename__ = "enterprise_snapshots"
    __table_args__ = (Index("ix_snapshots_enterprise_at", "enterprise_number", "snapshot_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enterprise_number: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("enterprises.enterprise_number", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class EnterpriseLifecycleHistory(Base):
    """Historique statuts métier — append-only (MS-07)."""

    __tablename__ = "enterprise_lifecycle_history"
    __table_args__ = (
        Index("ix_lifecycle_enterprise_at", "enterprise_number", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enterprise_number: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("enterprises.enterprise_number", ondelete="CASCADE"),
        nullable=False,
    )
    business_status: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class PipelineEvent(Base):
    """Événements supervision MS-09."""

    __tablename__ = "pipeline_events"
    __table_args__ = (Index("ix_pipeline_events_type_at", "event_type", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class AnalyticsPostalSummary(Base):
    __tablename__ = "analytics_postal_summary"

    postal_code: Mapped[str] = mapped_column(String(8), primary_key=True)
    enterprise_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AnalyticsStateSummary(Base):
    __tablename__ = "analytics_state_summary"

    business_status: Mapped[str] = mapped_column(String(32), primary_key=True)
    enterprise_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AnalyticsActivityRank(Base):
    __tablename__ = "analytics_activity_rank"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nace_code: Mapped[str] = mapped_column(String(16), nullable=False)
    activity_label: Mapped[str | None] = mapped_column(String(512), nullable=True)
    enterprise_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EnterpriseDiscovery(Base):
    __tablename__ = "enterprise_discoveries"
    __table_args__ = (
        UniqueConstraint(
            "source_enterprise_number",
            "discovered_enterprise_number",
            name="uq_enterprise_discoveries_pair",
        ),
        Index("ix_discoveries_discovered_at", "discovered_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_enterprise_number: Mapped[str] = mapped_column(String(10), nullable=False)
    discovered_enterprise_number: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("enterprises.enterprise_number", ondelete="CASCADE"),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
