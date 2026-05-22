"""Worker extraction — claim QUEUED_PARSE → STRUCTURED."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.discovery.service import apply_discovery_from_parse
from packages.extraction.config import ExtractionConfig, get_extraction_config
from packages.extraction.consolidate import consolidate_parsed_documents
from packages.extraction.parse import parse_raw_document
from packages.monitoring.events import record_parse_failure, record_parse_success
from packages.persistence.enums import ProcessingState
from packages.persistence.models import Base, RawDocument
from packages.persistence.repositories import (
    append_snapshot,
    claim_enterprises_for_parse,
    transition_state,
)
from packages.persistence.session import get_engine, session_scope
from packages.storage.raw_store import read_raw_bundle

logger = logging.getLogger(__name__)


@dataclass
class ParseBatchReport:
    claimed: int
    succeeded: int
    failed: int
    enterprises: list[str]


def _parse_enterprise(
    session: Session,
    enterprise_number: str,
    *,
    config: ExtractionConfig,
    worker_id: str,
) -> bool:
    docs = list(
        session.scalars(
            select(RawDocument)
            .where(RawDocument.enterprise_number == enterprise_number)
            .order_by(RawDocument.scraped_at.desc())
        )
    )
    if not docs:
        transition_state(
            session,
            enterprise_number,
            ProcessingState.PARSING,
            ProcessingState.FAILED_PARSE,
            lock_owner=worker_id,
        )
        record_parse_failure("no_raw_documents")
        return False

    parsed_payloads: list[dict[str, Any]] = []
    all_candidates: list[str] = []
    any_ok = False

    has_kbo_detail = any(
        d.source == "kbo" and d.doc_type == "enterprise_detail" for d in docs
    )

    seen_keys: set[tuple[str, str]] = set()
    for doc in docs:
        key = (doc.source, doc.doc_type)
        if key in seen_keys:
            continue
        if has_kbo_detail and doc.source == "kbo" and doc.doc_type == "profile":
            continue
        seen_keys.add(key)
        try:
            content, sidecar = read_raw_bundle(doc.hdfs_dir)
            meta = dict(sidecar)
            meta["enterprise_number"] = enterprise_number
            meta.setdefault("source", doc.source)
            meta.setdefault("doc_type", doc.doc_type)
            result = parse_raw_document(content, meta, config=config)
            if not result.ok or result.document is None:
                continue
            any_ok = True
            parsed_payloads.append(
                {
                    "source": doc.source,
                    "doc_type": doc.doc_type,
                    "run_id": doc.run_id,
                    "extractor_version": result.document.extractor_version,
                    "schema_version": result.document.schema_version,
                    "partial": result.document.partial,
                    "fields": result.document.fields,
                }
            )
            all_candidates.extend(result.document.discovery_candidates)
        except Exception:
            logger.exception("parse failed for %s %s", enterprise_number, doc.doc_type)

    if not any_ok:
        transition_state(
            session,
            enterprise_number,
            ProcessingState.PARSING,
            ProcessingState.FAILED_PARSE,
            lock_owner=worker_id,
        )
        record_parse_failure("all_documents_failed")
        return False

    snapshot_payload = consolidate_parsed_documents(
        enterprise_number,
        parsed_payloads,
    )
    append_snapshot(
        session,
        enterprise_number,
        snapshot_payload,
        schema_version=config.schema_version,
    )
    if not snapshot_payload.get("enterprise_detail") and not snapshot_payload.get("documents"):
        transition_state(
            session,
            enterprise_number,
            ProcessingState.PARSING,
            ProcessingState.FAILED_PARSE,
            lock_owner=worker_id,
        )
        record_parse_failure("empty_snapshot_payload")
        return False

    apply_discovery_from_parse(
        session,
        source_enterprise_number=enterprise_number,
        candidates=all_candidates,
    )
    transition_state(
        session,
        enterprise_number,
        ProcessingState.PARSING,
        ProcessingState.STRUCTURED,
        lock_owner=worker_id,
    )
    record_parse_success()
    return True


def parse_batch(*, limit: int = 10, config: ExtractionConfig | None = None) -> ParseBatchReport:
    cfg = config or get_extraction_config()
    engine = get_engine()
    Base.metadata.create_all(engine)

    succeeded = 0
    failed = 0
    enterprises: list[str] = []

    with session_scope() as session:
        claimed = claim_enterprises_for_parse(
            session,
            limit=limit,
            worker_id=cfg.worker_id,
        )
        session.commit()

        for number in claimed:
            enterprises.append(number)
            try:
                ok = _parse_enterprise(session, number, config=cfg, worker_id=cfg.worker_id)
                session.commit()
                if ok:
                    succeeded += 1
                else:
                    failed += 1
            except Exception:
                logger.exception("batch parse error for %s", number)
                session.rollback()
                failed += 1

    return ParseBatchReport(
        claimed=len(claimed),
        succeeded=succeeded,
        failed=failed,
        enterprises=enterprises,
    )
