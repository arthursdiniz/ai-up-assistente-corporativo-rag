"""Create the legacy AI-Up schema used by early local installations.

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-30
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    user_role = sa.Enum("USER", "MANAGER", "IT_ADMIN", name="userrole")
    document_status = sa.Enum("UPLOADED", "PROCESSING", "READY", "ERROR", name="documentstatus")
    message_role = sa.Enum("USER", "ASSISTANT", "SYSTEM", name="messagerole")

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id", name="users_pkey"),
        sa.UniqueConstraint("email", name="users_email_key"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=False)
    op.create_table(
        "chats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="chats_user_id_fkey", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="chats_pkey"),
    )
    op.create_index("ix_chats_user_id", "chats", ["user_id"], unique=False)
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=20), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("status", document_status, nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="documents_user_id_fkey", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="documents_pkey"),
    )
    op.create_index("ix_documents_user_id", "documents", ["user_id"], unique=False)
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=True),
        sa.Column("resource_id", sa.String(length=100), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="audit_logs_user_id_fkey", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="audit_logs_pkey"),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"], unique=False)
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"], unique=False)
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.Integer(), nullable=False),
        sa.Column("role", message_role, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], name="messages_chat_id_fkey", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="messages_pkey"),
    )
    op.create_index("ix_messages_chat_id", "messages", ["chat_id"], unique=False)
    op.create_table(
        "message_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("chunk_id", sa.String(length=100), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("relevance_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], name="message_sources_document_id_fkey", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["message_id"], ["messages.id"], name="message_sources_message_id_fkey", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="message_sources_pkey"),
    )
    op.create_index("ix_message_sources_message_id", "message_sources", ["message_id"], unique=False)


def downgrade() -> None:
    op.drop_table("message_sources")
    op.drop_table("messages")
    op.drop_table("audit_logs")
    op.drop_table("documents")
    op.drop_table("chats")
    op.drop_table("users")

    bind = op.get_bind()
    sa.Enum("USER", "ASSISTANT", "SYSTEM", name="messagerole").drop(bind, checkfirst=True)
    sa.Enum("UPLOADED", "PROCESSING", "READY", "ERROR", name="documentstatus").drop(
        bind, checkfirst=True
    )
    sa.Enum("USER", "MANAGER", "IT_ADMIN", name="userrole").drop(bind, checkfirst=True)
