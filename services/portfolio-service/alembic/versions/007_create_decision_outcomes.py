"""Create decision_outcomes table.

Revision ID: 007_decision_outcomes
Revises: 006_add_core_holdings_name_zh
Create Date: 2026-01-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "007_decision_outcomes"
down_revision = "006_add_core_holdings_name_zh"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "decision_outcomes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("plugin", sa.Text(), nullable=False),
        sa.Column("decision_inputs_hash", sa.Text(), nullable=False),
        sa.Column("outcome_label", sa.Text(), nullable=False),
        sa.Column("outcome_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_unique_constraint(
        "uq_decision_outcomes_identity",
        "decision_outcomes",
        ["user_id", "as_of", "plugin", "decision_inputs_hash"],
    )
    op.create_index(
        "ix_decision_outcomes_user_plugin_asof",
        "decision_outcomes",
        ["user_id", "plugin", "as_of"],
    )


def downgrade() -> None:
    op.drop_index("ix_decision_outcomes_user_plugin_asof", table_name="decision_outcomes")
    op.drop_constraint(
        "uq_decision_outcomes_identity",
        table_name="decision_outcomes",
        type_="unique",
    )
    op.drop_table("decision_outcomes")
