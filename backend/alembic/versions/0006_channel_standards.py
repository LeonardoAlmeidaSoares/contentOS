"""padrão do canal versionado e rastreabilidade das produções

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channel_standards",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("line_id", sa.String(36), sa.ForeignKey("production_lines.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("config", sa.JSON, nullable=False),
        sa.Column("changelog", sa.JSON, nullable=False),
        sa.Column("pending", sa.JSON, nullable=False),
        sa.Column("note", sa.Text, nullable=False, server_default=""),
        sa.Column("origin", sa.String(12), nullable=False, server_default="manual"),
        sa.Column("preview", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("line_id", "version", name="uq_standard_version"),
    )
    op.create_index("ix_channel_standards_line_id", "channel_standards", ["line_id"])
    op.create_index("uq_standard_one_approved", "channel_standards", ["line_id"], unique=True,
                    postgresql_where=sa.text("status = 'approved'"))
    op.add_column("runs", sa.Column("standard_id", sa.String(36), nullable=True))
    op.add_column("runs", sa.Column("standard_version", sa.Integer, nullable=True))
    op.add_column("runs", sa.Column("format", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "format")
    op.drop_column("runs", "standard_version")
    op.drop_column("runs", "standard_id")
    op.drop_table("channel_standards")
