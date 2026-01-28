"""Create decision_snapshots table.

Revision ID: 001_decision_snapshots
Revises:
Create Date: 2026-01-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_decision_snapshots"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "decision_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("plugin", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("inputs_hash", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
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
        "uq_decision_snapshots_user_asof_plugin",
        "decision_snapshots",
        ["user_id", "as_of", "plugin"],
    )
    op.execute(
        "CREATE INDEX ix_decision_snapshots_user_asof "
        "ON decision_snapshots (user_id, as_of DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_decision_snapshots_user_asof")
    op.drop_constraint(
        "uq_decision_snapshots_user_asof_plugin",
        table_name="decision_snapshots",
        type_="unique",
    )
    op.drop_table("decision_snapshots")
