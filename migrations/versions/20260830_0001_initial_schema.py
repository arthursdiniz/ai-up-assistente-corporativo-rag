"""Upgrade legacy installations to the final AI-Up schema.

Revision ID: 20260830_0001
Revises: 0001_initial
Create Date: 2026-08-30
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260830_0001"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("users", "name", existing_type=sa.String(150), type_=sa.String(120))
    op.alter_column("users", "email", existing_type=sa.String(255), type_=sa.String(320))
    op.execute("ALTER TABLE users ALTER COLUMN role TYPE VARCHAR(8) USING role::text")
    op.alter_column("users", "created_at", existing_type=sa.DateTime(timezone=True), nullable=False)
    op.alter_column("users", "updated_at", existing_type=sa.DateTime(timezone=True), nullable=False)
    op.drop_constraint("users_email_key", "users", type_="unique")
    op.drop_index("ix_users_email", table_name="users")
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.alter_column("chats", "title", existing_type=sa.String(200), type_=sa.String(160))
    op.alter_column("chats", "created_at", existing_type=sa.DateTime(timezone=True), nullable=False)
    op.alter_column("chats", "updated_at", existing_type=sa.DateTime(timezone=True), nullable=False)

    op.alter_column("documents", "file_type", existing_type=sa.String(20), type_=sa.String(30))
    op.alter_column("documents", "file_path", existing_type=sa.String(500), type_=sa.String(1024))
    op.execute("ALTER TABLE documents ALTER COLUMN status TYPE VARCHAR(10) USING status::text")
    op.alter_column("documents", "created_at", existing_type=sa.DateTime(timezone=True), nullable=False)
    op.create_unique_constraint(op.f("uq_documents_filename"), "documents", ["filename"])

    op.alter_column("audit_logs", "action", existing_type=sa.String(50), type_=sa.String(80))
    op.alter_column("audit_logs", "resource_type", existing_type=sa.String(50), type_=sa.String(80))
    op.alter_column("audit_logs", "resource_id", existing_type=sa.String(100), type_=sa.String(80))
    op.execute(
        "ALTER TABLE audit_logs ALTER COLUMN details TYPE JSON USING to_json(details)"
    )
    op.alter_column("audit_logs", "created_at", existing_type=sa.DateTime(timezone=True), nullable=False)

    op.execute("ALTER TABLE messages ALTER COLUMN role TYPE VARCHAR(9) USING role::text")
    op.alter_column("messages", "created_at", existing_type=sa.DateTime(timezone=True), nullable=False)

    op.drop_constraint("message_sources_document_id_fkey", "message_sources", type_="foreignkey")
    op.alter_column("message_sources", "document_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("message_sources", "chunk_id", existing_type=sa.String(100), type_=sa.String(255))
    op.alter_column("message_sources", "relevance_score", existing_type=sa.Float(), nullable=False)
    op.create_index(
        op.f("ix_message_sources_document_id"), "message_sources", ["document_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_message_sources_document_id_documents"),
        "message_sources",
        "documents",
        ["document_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_column("message_sources", "created_at")

    op.execute("DROP TYPE IF EXISTS userrole")
    op.execute("DROP TYPE IF EXISTS documentstatus")
    op.execute("DROP TYPE IF EXISTS messagerole")


def downgrade() -> None:
    bind = op.get_bind()
    sa.Enum("USER", "MANAGER", "IT_ADMIN", name="userrole").create(bind, checkfirst=True)
    sa.Enum("UPLOADED", "PROCESSING", "READY", "ERROR", name="documentstatus").create(
        bind, checkfirst=True
    )
    sa.Enum("USER", "ASSISTANT", "SYSTEM", name="messagerole").create(bind, checkfirst=True)

    op.add_column(
        "message_sources",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )
    op.drop_constraint(
        op.f("fk_message_sources_document_id_documents"), "message_sources", type_="foreignkey"
    )
    op.drop_index(op.f("ix_message_sources_document_id"), table_name="message_sources")
    op.alter_column("message_sources", "relevance_score", existing_type=sa.Float(), nullable=True)
    op.alter_column("message_sources", "chunk_id", existing_type=sa.String(255), type_=sa.String(100))
    op.alter_column("message_sources", "document_id", existing_type=sa.Integer(), nullable=True)
    op.create_foreign_key(
        "message_sources_document_id_fkey",
        "message_sources",
        "documents",
        ["document_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.alter_column("messages", "created_at", existing_type=sa.DateTime(timezone=True), nullable=True)
    op.execute("ALTER TABLE messages ALTER COLUMN role TYPE messagerole USING role::messagerole")

    op.alter_column("audit_logs", "created_at", existing_type=sa.DateTime(timezone=True), nullable=True)
    op.execute("ALTER TABLE audit_logs ALTER COLUMN details TYPE TEXT USING details::text")
    op.alter_column("audit_logs", "resource_id", existing_type=sa.String(80), type_=sa.String(100))
    op.alter_column("audit_logs", "resource_type", existing_type=sa.String(80), type_=sa.String(50))
    op.alter_column("audit_logs", "action", existing_type=sa.String(80), type_=sa.String(50))

    op.drop_constraint(op.f("uq_documents_filename"), "documents", type_="unique")
    op.alter_column("documents", "created_at", existing_type=sa.DateTime(timezone=True), nullable=True)
    op.execute(
        "ALTER TABLE documents ALTER COLUMN status TYPE documentstatus USING status::documentstatus"
    )
    op.alter_column("documents", "file_path", existing_type=sa.String(1024), type_=sa.String(500))
    op.alter_column("documents", "file_type", existing_type=sa.String(30), type_=sa.String(20))

    op.alter_column("chats", "updated_at", existing_type=sa.DateTime(timezone=True), nullable=True)
    op.alter_column("chats", "created_at", existing_type=sa.DateTime(timezone=True), nullable=True)
    op.alter_column("chats", "title", existing_type=sa.String(160), type_=sa.String(200))

    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.create_unique_constraint("users_email_key", "users", ["email"])
    op.create_index("ix_users_email", "users", ["email"], unique=False)
    op.alter_column("users", "updated_at", existing_type=sa.DateTime(timezone=True), nullable=True)
    op.alter_column("users", "created_at", existing_type=sa.DateTime(timezone=True), nullable=True)
    op.execute("ALTER TABLE users ALTER COLUMN role TYPE userrole USING role::userrole")
    op.alter_column("users", "email", existing_type=sa.String(320), type_=sa.String(255))
    op.alter_column("users", "name", existing_type=sa.String(120), type_=sa.String(150))
