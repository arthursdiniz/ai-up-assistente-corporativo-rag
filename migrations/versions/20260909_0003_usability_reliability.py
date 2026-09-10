"""Document processing, scoped chats, durable generation and source snapshots."""
from alembic import op
import sqlalchemy as sa

revision = "20260909_0003"
down_revision = "20260908_0002"
branch_labels = depends_on = None


def upgrade():
    for column in (
        sa.Column("content_hash", sa.String(64)),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("category", sa.String(80), nullable=False, server_default="Geral"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("processing_stage", sa.String(80), nullable=False, server_default="Aguardando"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("index_version", sa.String(255)),
        sa.Column("index_generation", sa.String(64)),
        sa.Column("sections", sa.JSON()), sa.Column("warnings", sa.JSON()),
    ):
        op.add_column("documents", column)
    op.create_index("ix_documents_content_hash", "documents", ["content_hash"])
    op.execute("UPDATE documents SET file_type = CASE WHEN lower(file_type) IN ('png','jpg','jpeg','image') THEN 'IMAGE' ELSE upper(file_type) END")
    op.execute("UPDATE documents SET progress = 100, processing_stage = 'Pronto (índice anterior)' WHERE status = 'READY'")
    op.add_column("chats", sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("chats", sa.Column("document_ids", sa.JSON()))
    op.add_column("messages", sa.Column("feedback_reason", sa.String(500)))
    op.add_column("messages", sa.Column("metrics", sa.JSON()))
    op.add_column("users", sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("message_sources", sa.Column("document_name", sa.String(255)))
    op.add_column("message_sources", sa.Column("location", sa.String(255)))
    op.add_column("message_sources", sa.Column("citation", sa.Integer()))
    op.execute("UPDATE message_sources SET document_name = documents.original_filename FROM documents WHERE documents.id = message_sources.document_id")
    op.drop_constraint("fk_message_sources_document_id_documents", "message_sources", type_="foreignkey")
    op.alter_column("message_sources", "document_id", existing_type=sa.Integer(), nullable=True)
    op.create_foreign_key("fk_message_sources_document_id_documents", "message_sources", "documents", ["document_id"], ["id"], ondelete="SET NULL")
    op.create_table("generations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("chat_id", sa.Integer(), sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("retry_message_id", sa.Integer(), sa.ForeignKey("messages.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("stage", sa.String(100), nullable=False),
        sa.Column("result", sa.JSON()), sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_generations_chat_id", "generations", ["chat_id"])
    op.create_index("ix_generations_user_id", "generations", ["user_id"])


def downgrade():
    raise RuntimeError("Restaure o backup em um destino novo para preservar versões e evidências.")
