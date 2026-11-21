"""revisão humana de vídeos, conexão YouTube e publicações

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)
LIVE = "status in ('preparing','uploading','succeeded','uncertain')"


def upgrade() -> None:
    op.create_table(
        "video_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("note", sa.Text, nullable=False, server_default=""),
        sa.Column("decided_at", TS, nullable=False),
    )
    op.create_table(
        "youtube_connection",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel_id", sa.String(64)), sa.Column("channel_title", sa.String(200)),
        sa.Column("refresh_token_enc", sa.Text), sa.Column("access_token_enc", sa.Text), sa.Column("expires_at", TS),
        sa.Column("scopes", sa.Text, nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("status_message", sa.Text),
        sa.Column("pending_state", sa.String(64)), sa.Column("pending_verifier_enc", sa.Text), sa.Column("pending_at", TS),
        sa.Column("connected_at", TS),
    )
    op.create_table(
        "youtube_publications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("privacy", sa.String(10), nullable=False, server_default="private"),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("tags", sa.JSON), sa.Column("made_for_kids", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("channel_id", sa.String(64)), sa.Column("channel_title", sa.String(200)),
        sa.Column("session_url_enc", sa.Text),
        sa.Column("bytes_sent", sa.Integer, nullable=False, server_default="0"),
        sa.Column("video_id", sa.String(32)), sa.Column("url", sa.String(200)), sa.Column("error", sa.Text),
        sa.Column("created_at", TS, nullable=False), sa.Column("finished_at", TS),
    )
    op.create_index("uq_ytpub_one_live_per_run", "youtube_publications", ["run_id"], unique=True,
                    postgresql_where=sa.text(LIVE))


def downgrade() -> None:
    op.drop_table("youtube_publications")
    op.drop_table("youtube_connection")
    op.drop_table("video_reviews")
