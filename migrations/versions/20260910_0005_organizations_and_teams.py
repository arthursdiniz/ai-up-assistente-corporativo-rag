"""Organizations, teams and shared document visibility."""

from alembic import op
import sqlalchemy as sa


revision = "20260910_0005"
down_revision = "20260910_0004"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    organizations = sa.table(
        "organizations", sa.column("id", sa.Integer()), sa.column("name", sa.String())
    )
    bind = op.get_bind()
    bind.execute(organizations.insert().values(name="AI-Up Local"))
    organization_id = bind.scalar(sa.select(organizations.c.id).order_by(organizations.c.id).limit(1))

    op.add_column("users", sa.Column("organization_id", sa.Integer(), nullable=True))
    bind.execute(
        sa.text("UPDATE users SET organization_id = :organization_id"),
        {"organization_id": organization_id},
    )
    op.alter_column("users", "organization_id", nullable=False)
    op.create_foreign_key(
        "fk_users_organization_id_organizations",
        "users",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_users_organization_id", "users", ["organization_id"])

    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "name", name="uq_teams_organization_id"),
    )
    op.create_index("ix_teams_organization_id", "teams", ["organization_id"])
    op.create_table(
        "team_members",
        sa.Column(
            "team_id",
            sa.Integer(),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.add_column("documents", sa.Column("organization_id", sa.Integer(), nullable=True))
    op.add_column("documents", sa.Column("team_id", sa.Integer(), nullable=True))
    op.add_column(
        "documents",
        sa.Column(
            "visibility",
            sa.Enum(
                "PRIVATE", "ORGANIZATION", "TEAM", name="document_visibility", native_enum=False
            ),
            nullable=False,
            server_default="PRIVATE",
        ),
    )
    bind.execute(
        sa.text(
            "UPDATE documents SET organization_id = "
            "(SELECT users.organization_id FROM users WHERE users.id = documents.user_id)"
        )
    )
    op.alter_column("documents", "organization_id", nullable=False)
    op.create_foreign_key(
        "fk_documents_organization_id_organizations",
        "documents",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_documents_team_id_teams",
        "documents",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_documents_organization_id", "documents", ["organization_id"])
    op.create_index("ix_documents_team_id", "documents", ["team_id"])

    op.add_column("audit_logs", sa.Column("organization_id", sa.Integer(), nullable=True))
    bind.execute(
        sa.text(
            "UPDATE audit_logs SET organization_id = "
            "(SELECT users.organization_id FROM users WHERE users.id = audit_logs.user_id) "
            "WHERE user_id IS NOT NULL"
        )
    )
    op.create_foreign_key(
        "fk_audit_logs_organization_id_organizations",
        "audit_logs",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_audit_logs_organization_id", "audit_logs", ["organization_id"])


def downgrade():
    op.drop_index("ix_audit_logs_organization_id", table_name="audit_logs")
    op.drop_constraint(
        "fk_audit_logs_organization_id_organizations", "audit_logs", type_="foreignkey"
    )
    op.drop_column("audit_logs", "organization_id")
    op.drop_index("ix_documents_team_id", table_name="documents")
    op.drop_index("ix_documents_organization_id", table_name="documents")
    op.drop_constraint("fk_documents_team_id_teams", "documents", type_="foreignkey")
    op.drop_constraint(
        "fk_documents_organization_id_organizations", "documents", type_="foreignkey"
    )
    op.drop_column("documents", "visibility")
    op.drop_column("documents", "team_id")
    op.drop_column("documents", "organization_id")
    op.drop_table("team_members")
    op.drop_index("ix_teams_organization_id", table_name="teams")
    op.drop_table("teams")
    op.drop_index("ix_users_organization_id", table_name="users")
    op.drop_constraint(
        "fk_users_organization_id_organizations", "users", type_="foreignkey"
    )
    op.drop_column("users", "organization_id")
    op.drop_table("organizations")
