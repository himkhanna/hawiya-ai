"""Document extractions table with RLS.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    document_type = sa.Enum(
        "passport",
        "emirates_id",
        "gcc_id",
        "residence_permit",
        "other",
        name="document_type",
    )
    checksum_status = sa.Enum("all_pass", "partial", "all_fail", "n/a", name="checksum_status")
    processing_path = sa.Enum(
        "mrz_only",
        "mrz_plus_visual",
        "visual_only",
        "vision_fallback",
        name="processing_path",
    )

    op.create_table(
        "document_extractions",
        sa.Column(
            "extraction_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.tenant_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("consumer_request_id", sa.String(length=128), nullable=True),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("document_type", document_type, nullable=False),
        sa.Column("extracted_data", postgresql.JSONB, nullable=False),
        sa.Column("confidence_per_field", postgresql.JSONB, nullable=False),
        sa.Column("checksum_status", checksum_status, nullable=False),
        sa.Column("processing_path", processing_path, nullable=False),
        sa.Column("processing_time_ms", sa.Integer, nullable=False),
        sa.Column("person_uuid", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("match_action", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_doc_extr_tenant_created",
        "document_extractions",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_doc_extr_tenant_input_hash",
        "document_extractions",
        ["tenant_id", "input_hash"],
    )
    op.create_index(
        "ix_doc_extr_tenant_consumer_req",
        "document_extractions",
        ["tenant_id", "consumer_request_id"],
    )

    op.execute("ALTER TABLE document_extractions ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE document_extractions FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY document_extractions_tenant_isolation
          ON document_extractions
          USING (tenant_id::text = current_setting('app.current_tenant', true))
          WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true));
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS document_extractions_tenant_isolation ON document_extractions;"
    )
    op.execute("ALTER TABLE document_extractions DISABLE ROW LEVEL SECURITY;")
    op.drop_index("ix_doc_extr_tenant_consumer_req", table_name="document_extractions")
    op.drop_index("ix_doc_extr_tenant_input_hash", table_name="document_extractions")
    op.drop_index("ix_doc_extr_tenant_created", table_name="document_extractions")
    op.drop_table("document_extractions")
    op.execute("DROP TYPE IF EXISTS processing_path;")
    op.execute("DROP TYPE IF EXISTS checksum_status;")
    op.execute("DROP TYPE IF EXISTS document_type;")
