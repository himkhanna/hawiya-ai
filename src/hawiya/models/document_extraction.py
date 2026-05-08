"""Document extraction record (per CLAUDE.md §6)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from hawiya.extractors.types import ChecksumStatus, DocumentType, ProcessingPath
from hawiya.models.base import Base, enum_column


class DocumentExtraction(Base):
    __tablename__ = "document_extractions"

    extraction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.tenant_id", ondelete="RESTRICT"),
        nullable=False,
    )
    consumer_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    document_type: Mapped[DocumentType] = mapped_column(
        enum_column(DocumentType, name="document_type"),
        nullable=False,
    )
    extracted_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    confidence_per_field: Mapped[dict[str, float]] = mapped_column(JSONB, nullable=False)
    checksum_status: Mapped[ChecksumStatus] = mapped_column(
        enum_column(ChecksumStatus, name="checksum_status"),
        nullable=False,
    )
    processing_path: Mapped[ProcessingPath] = mapped_column(
        enum_column(ProcessingPath, name="processing_path"),
        nullable=False,
    )
    processing_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    person_uuid: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    match_action: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_doc_extr_tenant_created", "tenant_id", "created_at"),
        Index("ix_doc_extr_tenant_input_hash", "tenant_id", "input_hash"),
        Index("ix_doc_extr_tenant_consumer_req", "tenant_id", "consumer_request_id"),
    )
