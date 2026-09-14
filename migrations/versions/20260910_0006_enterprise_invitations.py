"""Enterprise invitations and optional team assignment."""

from alembic import op
import sqlalchemy as sa


revision = "20260910_0006"
down_revision = "20260910_0005"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "invitations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column(
            "role",
            sa.Enum("USER", "MANAGER", "IT_ADMIN", name="user_role", native_enum=False),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_invitations_organization_id", "invitations", ["organization_id"])
    op.create_index("ix_invitations_created_by_id", "invitations", ["created_by_id"])
    op.create_index("ix_invitations_email", "invitations", ["email"])
    op.create_index(
        "ix_invitations_token_hash", "invitations", ["token_hash"], unique=True
    )
    op.create_index("ix_invitations_expires_at", "invitations", ["expires_at"])
    op.create_table(
        "invitation_teams",
        sa.Column(
            "invitation_id",
            sa.Integer(),
            sa.ForeignKey("invitations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "team_id",
            sa.Integer(),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade():
    op.drop_table("invitation_teams")
    op.drop_index("ix_invitations_expires_at", table_name="invitations")
    op.drop_index("ix_invitations_token_hash", table_name="invitations")
    op.drop_index("ix_invitations_email", table_name="invitations")
    op.drop_index("ix_invitations_created_by_id", table_name="invitations")
    op.drop_index("ix_invitations_organization_id", table_name="invitations")
    op.drop_table("invitations")
