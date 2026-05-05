"""Person Registry: persons, identifiers, name variants, match_decisions.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Extensions: pg_trgm for trigram name matching, unaccent for diacritic
    # handling (CLAUDE.md §3 tech stack). Both must be installed in the
    # cluster's contrib package; on Postgres 16 they are preloaded.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent;")

    sex = sa.Enum("M", "F", "X", name="sex")
    person_status = sa.Enum("active", "merged", "archived", name="person_status")
    identifier_type = sa.Enum(
        "passport", "emirates_id", "gcc_id", "prior_passport", name="identifier_type"
    )
    identifier_status = sa.Enum("active", "archived", name="identifier_status")
    name_script = sa.Enum("arabic", "latin", "other", name="name_script")
    name_variant_type = sa.Enum(
        "canonical", "transliteration", "alias", "mrz", name="name_variant_type"
    )
    match_type = sa.Enum("deterministic", "probabilistic", "llm_assisted", name="match_type")
    match_decision_value = sa.Enum(
        "auto_merge",
        "suggest_merge",
        "no_match",
        "manual_review",
        name="match_decision_value",
    )
    review_outcome = sa.Enum(
        "confirmed_match", "rejected_match", "escalated", name="review_outcome"
    )

    # ------------------------------------------------------------------ persons
    op.create_table(
        "persons",
        sa.Column(
            "person_uuid",
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
        sa.Column("canonical_name_ar", sa.String(length=255), nullable=True),
        sa.Column("canonical_name_en", sa.String(length=255), nullable=True),
        sa.Column("date_of_birth", sa.Date, nullable=True),
        sa.Column("nationality", sa.String(length=3), nullable=True),
        sa.Column("sex", sex, nullable=True),
        sa.Column("status", person_status, nullable=False, server_default="active"),
        sa.Column("merged_into", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_persons_tenant_status_dob",
        "persons",
        ["tenant_id", "status", "date_of_birth"],
    )
    op.create_index(
        "ix_persons_tenant_nationality",
        "persons",
        ["tenant_id", "nationality"],
    )
    # Trigram GIN index for fuzzy Arabic name search (Phase 2 will use it).
    op.execute(
        "CREATE INDEX ix_persons_tenant_name_ar_trgm ON persons "
        "USING gin (tenant_id, canonical_name_ar gin_trgm_ops);"
    )

    # -------------------------------------------------------- person_identifiers
    op.create_table(
        "person_identifiers",
        sa.Column(
            "identifier_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "person_uuid",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("persons.person_uuid", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("identifier_type", identifier_type, nullable=False),
        sa.Column("identifier_value", sa.String(length=64), nullable=False),
        sa.Column("issuing_country", sa.String(length=3), nullable=True),
        sa.Column("issue_date", sa.Date, nullable=True),
        sa.Column("expiry_date", sa.Date, nullable=True),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("status", identifier_status, nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_pid_tenant_person", "person_identifiers", ["tenant_id", "person_uuid"])
    # Partial unique: an active identifier of a given type+value is unique
    # within a tenant. Archived rows can coexist (history of merges, etc.).
    op.create_index(
        "uq_pid_active_identifier",
        "person_identifiers",
        ["tenant_id", "identifier_type", "identifier_value"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    # ------------------------------------------------------ person_name_variants
    op.create_table(
        "person_name_variants",
        sa.Column(
            "variant_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "person_uuid",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("persons.person_uuid", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name_value", sa.String(length=255), nullable=False),
        sa.Column("script", name_script, nullable=False),
        sa.Column("variant_type", name_variant_type, nullable=False),
        sa.Column("phonetic_key", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_pnv_tenant_person", "person_name_variants", ["tenant_id", "person_uuid"])
    op.create_index(
        "ix_pnv_tenant_phonetic",
        "person_name_variants",
        ["tenant_id", "phonetic_key"],
    )
    op.execute(
        "CREATE INDEX ix_pnv_tenant_name_trgm ON person_name_variants "
        "USING gin (tenant_id, name_value gin_trgm_ops);"
    )

    # ------------------------------------------------------------- match_decisions
    op.create_table(
        "match_decisions",
        sa.Column(
            "decision_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_a", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("candidate_b", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("match_type", match_type, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column(
            "features",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("decision", match_decision_value, nullable=False),
        sa.Column("reviewed_by", sa.String(length=128), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_outcome", review_outcome, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_match_decisions_tenant_created",
        "match_decisions",
        ["tenant_id", "created_at"],
    )

    # ------------------------------------------------------------------ RLS
    for table in (
        "persons",
        "person_identifiers",
        "person_name_variants",
        "match_decisions",
    ):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation "
            f"  ON {table} "
            f"  USING (tenant_id::text = current_setting('app.current_tenant', true)) "
            f"  WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true));"
        )


def downgrade() -> None:
    for table in (
        "match_decisions",
        "person_name_variants",
        "person_identifiers",
        "persons",
    ):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.drop_index("ix_match_decisions_tenant_created", table_name="match_decisions")
    op.drop_table("match_decisions")
    op.execute("DROP INDEX IF EXISTS ix_pnv_tenant_name_trgm;")
    op.drop_index("ix_pnv_tenant_phonetic", table_name="person_name_variants")
    op.drop_index("ix_pnv_tenant_person", table_name="person_name_variants")
    op.drop_table("person_name_variants")
    op.drop_index("uq_pid_active_identifier", table_name="person_identifiers")
    op.drop_index("ix_pid_tenant_person", table_name="person_identifiers")
    op.drop_table("person_identifiers")
    op.execute("DROP INDEX IF EXISTS ix_persons_tenant_name_ar_trgm;")
    op.drop_index("ix_persons_tenant_nationality", table_name="persons")
    op.drop_index("ix_persons_tenant_status_dob", table_name="persons")
    op.drop_table("persons")

    for enum in (
        "review_outcome",
        "match_decision_value",
        "match_type",
        "name_variant_type",
        "name_script",
        "identifier_status",
        "identifier_type",
        "person_status",
        "sex",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum};")
