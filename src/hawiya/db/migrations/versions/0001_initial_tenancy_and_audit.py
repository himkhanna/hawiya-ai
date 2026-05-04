"""Initial schema: tenants, audit_log, and RLS on audit_log.

Revision ID: 0001
Revises:
Create Date: 2026-05-04
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # tenants — the partition key for everything else
    op.create_table(
        "tenants",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("tenant_name", sa.String(length=255), nullable=False, unique=True),
        sa.Column(
            "status",
            sa.Enum("active", "suspended", "archived", name="tenant_status"),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "config",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # audit_log — every AI decision and tenant-scoped action
    op.create_table(
        "audit_log",
        sa.Column(
            "audit_id",
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
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=True),
        sa.Column("endpoint", sa.String(length=255), nullable=False),
        sa.Column("input_hash", sa.String(length=128), nullable=True),
        sa.Column("output_summary", postgresql.JSONB, nullable=True),
        sa.Column("model_versions", postgresql.JSONB, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("processing_path", sa.String(length=64), nullable=True),
        sa.Column("decision", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_audit_log_tenant_created", "audit_log", ["tenant_id", "created_at"])
    op.create_index("ix_audit_log_tenant_request", "audit_log", ["tenant_id", "request_id"])

    # Row-level security on audit_log keyed off the per-session GUC
    # `app.current_tenant`. Repository code sets this at session start via
    # `set_session_tenant()`. Without it, RLS denies all rows.
    op.execute("ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE audit_log FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY audit_log_tenant_isolation
          ON audit_log
          USING (tenant_id::text = current_setting('app.current_tenant', true))
          WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true));
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS audit_log_tenant_isolation ON audit_log;")
    op.execute("ALTER TABLE audit_log DISABLE ROW LEVEL SECURITY;")
    op.drop_index("ix_audit_log_tenant_request", table_name="audit_log")
    op.drop_index("ix_audit_log_tenant_created", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_table("tenants")
    op.execute("DROP TYPE IF EXISTS tenant_status;")
