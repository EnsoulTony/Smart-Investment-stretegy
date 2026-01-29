"""Add labeled_at and horizon to decision_outcomes.

Revision ID: 008_add_outcome_label_meta
Revises: 007_decision_outcomes
Create Date: 2026-01-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "008_add_outcome_label_meta"
down_revision = "007_decision_outcomes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "decision_outcomes",
        sa.Column(
            "labeled_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column(
        "decision_outcomes",
        sa.Column(
            "horizon",
            sa.Text(),
            server_default=sa.text("'D1'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("decision_outcomes", "horizon")
    op.drop_column("decision_outcomes", "labeled_at")
