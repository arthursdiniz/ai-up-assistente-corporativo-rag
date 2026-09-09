"""Add source evidence and response feedback.

Revision ID: 20260908_0002
Revises: 20260830_0001
Create Date: 2026-09-08
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260908_0002"
down_revision: str | None = "20260830_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("feedback", sa.SmallInteger(), nullable=True))
    op.create_check_constraint(
        "feedback_value",
        "messages",
        "feedback IS NULL OR feedback IN (-1, 1)",
    )
    op.add_column("message_sources", sa.Column("sheet", sa.String(255), nullable=True))
    op.add_column("message_sources", sa.Column("excerpt", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("message_sources", "excerpt")
    op.drop_column("message_sources", "sheet")
    op.drop_constraint(op.f("ck_messages_feedback_value"), "messages", type_="check")
    op.drop_column("messages", "feedback")
