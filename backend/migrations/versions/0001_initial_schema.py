"""Initial schema.

Revision ID: 0001
Revises:
Create Date: 2026-08-21

Three constraints in this migration carry constitutional guarantees and must not be
dropped without amending the Constitution:

  * `ck_client_synthetic_only`  — Principle VII: only synthetic client data exists.
  * `ck_source_document_size` / `ck_source_document_pages` — uploads are declined,
    never truncated.
  * The `audit_event` grant at the end — Principle VIII / FR-032: the application role
    may append and read, never rewrite.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    # ---------------------------------------------------------------- users
    op.create_table(
        "app_user",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("team_id", UUID, nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_app_user_email", "app_user", ["email"])

    # -------------------------------------------------------------- clients
    op.create_table(
        "client",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("client_reference", sa.String(64), nullable=False, unique=True),
        sa.Column("legal_name", sa.String(255), nullable=False),
        sa.Column("trade_name", sa.String(255), nullable=True),
        sa.Column("commercial_registration", sa.String(64), nullable=True),
        sa.Column("sector", sa.String(128), nullable=False),
        sa.Column("incorporation_date", sa.Date(), nullable=True),
        sa.Column("relationship_since", sa.Date(), nullable=True),
        sa.Column("owning_rm_id", UUID, sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("kyc_status", sa.String(32), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        # Principle VII, enforced by the database. A non-synthetic row cannot be
        # inserted, whatever the application layer believes it is doing.
        sa.CheckConstraint("is_synthetic = true", name="ck_client_synthetic_only"),
    )
    op.create_index("ix_client_owning_rm", "client", ["owning_rm_id"])
    op.create_index("ix_client_reference", "client", ["client_reference"])

    op.create_table(
        "client_record",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("client_id", UUID, sa.ForeignKey("client.id"), nullable=False),
        sa.Column("record_type", sa.String(32), nullable=False),
        sa.Column("source_system", sa.String(32), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("is_external", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_client_record_client", "client_record", ["client_id"])

    op.create_table(
        "source_document",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("client_id", UUID, sa.ForeignKey("client.id"), nullable=False),
        sa.Column("uploaded_by", UUID, sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("title", sa.String(512), nullable=True),
        sa.Column("media_type", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("provider_file_id", sa.String(128), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("trust_level", sa.String(32), nullable=False, server_default="UNTRUSTED"),
        sa.Column("uploaded_at", TS, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("size_bytes <= 33554432", name="ck_source_document_size"),
        sa.CheckConstraint(
            "page_count IS NULL OR page_count <= 600", name="ck_source_document_pages"
        ),
    )
    op.create_index("ix_source_document_client", "source_document", ["client_id"])

    # ------------------------------------------------------------ documents
    op.create_table(
        "document_template",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("document_type", sa.String(64), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("section_definitions", JSONB, nullable=False),
        sa.Column("required_inputs", JSONB, nullable=False, server_default="[]"),
        sa.Column("screening_profile", sa.String(64), nullable=False, server_default="standard"),
        sa.Column("prompt_template_ref", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("document_type", "version", name="uq_template_type_version"),
    )

    op.create_table(
        "document",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("client_id", UUID, sa.ForeignKey("client.id"), nullable=False),
        sa.Column("document_type", sa.String(64), nullable=False),
        sa.Column("template_id", UUID, sa.ForeignKey("document_template.id"), nullable=False),
        sa.Column("created_by", UUID, sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
        # Principle II: starts PENDING_REVIEW; the system never writes CLEARED.
        sa.Column(
            "shariah_status", sa.String(32), nullable=False, server_default="PENDING_REVIEW"
        ),
        sa.Column("current_version_id", UUID, nullable=True),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_document_client", "document", ["client_id"])

    op.create_table(
        "document_version",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("document_id", UUID, sa.ForeignKey("document.id"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(32), nullable=False),
        sa.Column("created_by", UUID, sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("model_id", sa.String(64), nullable=True),
        sa.Column("template_version", sa.String(32), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("ledger_id", UUID, nullable=True),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("document_id", "version_number", name="uq_version_document_number"),
    )
    op.create_index("ix_document_version_document", "document_version", ["document_id"])
    op.create_index("ix_document_version_hash", "document_version", ["content_hash"])

    op.create_table(
        "document_section",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("version_id", UUID, sa.ForeignKey("document_version.id"), nullable=False),
        sa.Column("section_key", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("evidence_refs", JSONB, nullable=False, server_default="[]"),
        sa.Column("gaps", JSONB, nullable=False, server_default="[]"),
        sa.Column("confidence", sa.String(16), nullable=False, server_default="MEDIUM"),
        sa.Column("is_rm_edited", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "contains_external_data", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.create_index("ix_document_section_version", "document_section", ["version_id"])

    # ------------------------------------------------------------- evidence
    op.create_table(
        "evidence_ledger",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("document_id", UUID, sa.ForeignKey("document.id"), nullable=False),
        sa.Column("built_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("model_id", sa.String(64), nullable=False),
        sa.Column("source_manifest", JSONB, nullable=False, server_default="{}"),
    )
    op.create_index("ix_evidence_ledger_document", "evidence_ledger", ["document_id"])

    op.create_table(
        "evidence_claim",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("ledger_id", UUID, sa.ForeignKey("evidence_ledger.id"), nullable=False),
        sa.Column("claim_id", sa.String(64), nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_id", UUID, nullable=True),
        sa.Column("source_label", sa.String(512), nullable=False, server_default=""),
        sa.Column("locator", JSONB, nullable=False, server_default="{}"),
        sa.Column("verbatim_excerpt", sa.Text(), nullable=False),
        sa.Column("is_external", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("ledger_id", "claim_id", name="uq_claim_ledger_key"),
    )
    op.create_index("ix_evidence_claim_ledger", "evidence_claim", ["ledger_id"])

    # ------------------------------------------------------------ screening
    op.create_table(
        "screening_result",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("version_id", UUID, sa.ForeignKey("document_version.id"), nullable=False),
        sa.Column("layer", sa.String(32), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("findings", JSONB, nullable=False, server_default="[]"),
        sa.Column("vocabulary_version", sa.String(32), nullable=False),
        sa.Column("screened_at", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_screening_result_version", "screening_result", ["version_id"])

    # ------------------------------------------------------------- approval
    op.create_table(
        "approval_record",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("document_id", UUID, sa.ForeignKey("document.id"), nullable=False, unique=True),
        sa.Column("version_id", UUID, sa.ForeignKey("document_version.id"), nullable=False),
        sa.Column("approved_by", UUID, sa.ForeignKey("app_user.id"), nullable=False),
        # Snapshots, so the record survives changes to the user row.
        sa.Column("approver_name", sa.String(255), nullable=False),
        sa.Column("approver_role", sa.String(32), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("shariah_status_at_approval", sa.String(32), nullable=False),
        sa.Column("gaps_acknowledged", JSONB, nullable=False, server_default="[]"),
        sa.Column("approved_at", TS, nullable=False, server_default=sa.func.now()),
    )

    # ---------------------------------------------------------------- audit
    op.create_table(
        "audit_event",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("sequence", sa.BigInteger(), sa.Identity(always=False), nullable=False, unique=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("occurred_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("actor_id", UUID, nullable=True),
        sa.Column("actor_name", sa.String(255), nullable=True),
        sa.Column("client_reference", sa.String(64), nullable=True),
        sa.Column("document_id", UUID, nullable=True),
        sa.Column("version_id", UUID, nullable=True),
        sa.Column("document_type", sa.String(64), nullable=True),
        sa.Column("input_source_ids", JSONB, nullable=False, server_default="[]"),
        sa.Column("model_id", sa.String(64), nullable=True),
        sa.Column("model_version", sa.String(64), nullable=True),
        sa.Column("prompt_version", sa.String(32), nullable=True),
        sa.Column("template_version", sa.String(32), nullable=True),
        sa.Column("output_hash", sa.String(64), nullable=True),
        sa.Column("detail", JSONB, nullable=False, server_default="{}"),
        sa.Column("prev_hash", sa.String(64), nullable=True),
        sa.Column("event_hash", sa.String(64), nullable=False),
    )
    op.create_index("ix_audit_event_type", "audit_event", ["event_type"])
    op.create_index("ix_audit_event_occurred", "audit_event", ["occurred_at"])
    op.create_index("ix_audit_event_document", "audit_event", ["document_id"])
    op.create_index("ix_audit_event_actor", "audit_event", ["actor_id"])
    op.create_index("ix_audit_event_client", "audit_event", ["client_reference"])
    op.create_index("ix_audit_event_hash", "audit_event", ["event_hash"])

    # FR-032 / Principle VIII. The application role may append and read; it may never
    # rewrite history. Applied here as well as in create_roles.sql so a database built
    # by migration alone still carries the guarantee.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'warba_app') THEN
                REVOKE ALL ON TABLE audit_event FROM warba_app;
                GRANT INSERT, SELECT ON TABLE audit_event TO warba_app;
                REVOKE UPDATE, DELETE, TRUNCATE ON TABLE audit_event FROM warba_app;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    for table in (
        "audit_event",
        "approval_record",
        "screening_result",
        "evidence_claim",
        "evidence_ledger",
        "document_section",
        "document_version",
        "document",
        "document_template",
        "source_document",
        "client_record",
        "client",
        "app_user",
    ):
        op.drop_table(table)
