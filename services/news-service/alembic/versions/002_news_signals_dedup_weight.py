"""Add published_date + weight + unique index for news_signals.

Revision ID: 002_news_signals_dedup
Revises: 001_news_signals
Create Date: 2026-01-28 00:10:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "002_news_signals_dedup"
down_revision = "001_news_signals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("news_signals", sa.Column("published_date", sa.Date(), server_default=sa.text("CURRENT_DATE"), nullable=False))
    op.add_column("news_signals", sa.Column("weight", sa.Integer(), server_default="0", nullable=False))
    op.create_index("ix_news_signals_source_date", "news_signals", ["source", "published_date"])
    op.create_unique_constraint(
        "uq_news_signals_source_title_date",
        "news_signals",
        ["source", "title", "published_date"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_news_signals_source_title_date", "news_signals", type_="unique")
    op.drop_index("ix_news_signals_source_date", table_name="news_signals")
    op.drop_column("news_signals", "weight")
    op.drop_column("news_signals", "published_date")
