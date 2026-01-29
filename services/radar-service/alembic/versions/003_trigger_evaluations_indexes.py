"""Add indexes for trigger_evaluations history queries.

Revision ID: 003_trigger_eval_indexes
Revises: 002_trigger_evaluations
Create Date: 2026-01-29 00:00:00.000000

"""
from alembic import op

revision = "003_trigger_eval_indexes"
down_revision = "002_trigger_evaluations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_trigger_eval_user_plugin_triggered "
        "ON trigger_evaluations (user_id, plugin, is_triggered, as_of DESC)"
    )
    op.execute(
        "CREATE INDEX ix_trigger_eval_user_plugin_type "
        "ON trigger_evaluations (user_id, plugin, trigger_type, as_of DESC)"
    )
    op.execute(
        "CREATE INDEX ix_trigger_eval_user_evaltime "
        "ON trigger_evaluations (user_id, plugin, evaluated_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_trigger_eval_user_evaltime")
    op.execute("DROP INDEX IF EXISTS ix_trigger_eval_user_plugin_type")
    op.execute("DROP INDEX IF EXISTS ix_trigger_eval_user_plugin_triggered")
