"""Add document audit runs, extracted rule sets, alerts and human reviews."""
from alembic import op
import sqlalchemy as sa


revision = "20261111_0007"
down_revision = "20260910_0006"
branch_labels = depends_on = None


def ref(name, table, *, nullable=False):
    return sa.Column(name, sa.Integer(), sa.ForeignKey(f"{table}.id", ondelete="CASCADE"), nullable=nullable)


def timestamp(name):
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade():
    op.create_table("auditor_runs",
        sa.Column("id", sa.String(36), primary_key=True), ref("user_id", "users"),
        ref("organization_id", "organizations"), ref("document_id", "documents"),
        sa.Column("fingerprint", sa.String(64), nullable=False), sa.Column("attempt", sa.String(36), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("stage", sa.String(120), nullable=False), sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(40)), sa.Column("error", sa.Text()), timestamp("created_at"),
        sa.UniqueConstraint("user_id", "fingerprint"))
    op.create_index("ix_auditor_runs_document_id", "auditor_runs", ["document_id"])
    op.create_index("ix_auditor_runs_user_status", "auditor_runs", ["user_id", "status"])
    op.create_table("auditor_rule_sets", sa.Column("id", sa.Integer(), primary_key=True), ref("document_id", "documents"),
        sa.Column("generation", sa.String(64), nullable=False), sa.Column("extractor_version", sa.String(40), nullable=False),
        sa.Column("rules", sa.JSON(), nullable=False), sa.Column("limited", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("document_id", "generation", "extractor_version"))
    op.create_table("auditor_alerts", sa.Column("id", sa.Integer(), primary_key=True), ref("user_id", "users"),
        ref("organization_id", "organizations"),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("auditor_runs.id", ondelete="SET NULL")),
        ref("left_id", "documents"), ref("right_id", "documents"),
        sa.Column("left_generation", sa.String(64), nullable=False), sa.Column("right_generation", sa.String(64), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False), sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("valid_until", sa.Date()),
        sa.Column("state", sa.String(20), nullable=False), sa.Column("subject", sa.String(240), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False), sa.Column("evidence", sa.JSON(), nullable=False),
        timestamp("detected_at"), sa.UniqueConstraint("user_id", "fingerprint"))
    op.create_index("ix_auditor_alerts_left_id", "auditor_alerts", ["left_id"])
    op.create_index("ix_auditor_alerts_right_id", "auditor_alerts", ["right_id"])
    op.create_index("ix_auditor_alerts_user_state", "auditor_alerts", ["user_id", "state"])
    op.create_table("auditor_reviews", sa.Column("id", sa.Integer(), primary_key=True), ref("alert_id", "auditor_alerts"),
        ref("user_id", "users"), sa.Column("state", sa.String(20), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False), timestamp("created_at"))
    op.create_index("ix_auditor_reviews_alert_id", "auditor_reviews", ["alert_id"])


def downgrade():
    raise RuntimeError("O downgrade descartaria auditorias e decisões humanas. Restaure uma cópia em banco separado.")
