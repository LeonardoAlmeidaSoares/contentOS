"""amostras do Laboratório de Vozes

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voice_samples",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("voice", sa.String(80), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("params", sa.JSON, nullable=False),
        sa.Column("storage_key", sa.String(200), nullable=False),
        sa.Column("seconds", sa.Float, nullable=False),
        sa.Column("gen_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("voice_samples")
