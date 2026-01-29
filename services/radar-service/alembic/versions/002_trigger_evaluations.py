"""Create trigger_evaluations table.

Revision ID: 002_trigger_evaluations
Revises: 001_decision_snapshots
Create Date: 2026-01-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "002_trigger_evaluations"
down_revision = "001_decision_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trigger_evaluations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("plugin", sa.String(length=32), nullable=False),
        sa.Column("decision_inputs_hash", sa.String(length=64), nullable=False),
        sa.Column("trigger_key", sa.String(length=256), nullable=False),
        sa.Column("trigger_type", sa.String(length=32), nullable=False),
        sa.Column("condition", postgresql.JSONB(), nullable=False),
        sa.Column("observed_value", postgresql.JSONB(), nullable=False),
        sa.Column("is_triggered", sa.Boolean(), nullable=False),
        sa.Column(
            "evaluated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_unique_constraint(
        "uq_trigger_eval_identity",
        "trigger_evaluations",
        ["user_id", "as_of", "plugin", "decision_inputs_hash", "trigger_key"],
    )
    op.create_index(
        "ix_trigger_eval_user_asof_plugin",
        "trigger_evaluations",
        ["user_id", "as_of", "plugin"],
    )


def downgrade() -> None:
    op.drop_index("ix_trigger_eval_user_asof_plugin", table_name="trigger_evaluations")
    op.drop_constraint(
        "uq_trigger_eval_identity",
        table_name="trigger_evaluations",
        type_="unique",
    )
    op.drop_table("trigger_evaluations")
