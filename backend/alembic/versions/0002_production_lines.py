"""production lines, step io/cost, run control columns

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)
MONEY = sa.Numeric(14, 6)
ACTIVE = "status in ('queued','running','retrying')"


def upgrade() -> None:
    op.create_table(
        "production_lines",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("pipeline", sa.String(64), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("config", sa.JSON, nullable=False),
        sa.Column("interval_minutes", sa.Integer),
        sa.Column("cost_limit_run", MONEY),
        sa.Column("cost_limit_month", MONEY),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="3"),
        sa.Column("backoff_seconds", sa.Integer, nullable=False, server_default="5"),
        sa.Column("last_run_at", TS),
        sa.Column("next_run_at", TS),
        sa.Column("created_at", TS, nullable=False),
    )
    op.add_column("runs", sa.Column("line_id", sa.String(36), sa.ForeignKey("production_lines.id")))
    op.add_column("runs", sa.Column("trigger", sa.String(16), nullable=False, server_default="manual"))
    op.add_column("runs", sa.Column("cost", MONEY, nullable=False, server_default="0"))
    op.add_column("runs", sa.Column("cancel_requested", sa.Boolean, nullable=False, server_default=sa.false()))
    op.add_column("runs", sa.Column("heartbeat_at", TS))
    op.create_index("ix_runs_line_id", "runs", ["line_id"])
    op.create_index("uq_runs_one_active_per_line", "runs", ["line_id"], unique=True, postgresql_where=sa.text(ACTIVE))
    op.add_column("run_steps", sa.Column("input", sa.JSON))
    op.add_column("run_steps", sa.Column("output", sa.JSON))
    op.add_column("run_steps", sa.Column("cost", MONEY, nullable=False, server_default="0"))
    op.add_column("run_steps", sa.Column("attempts", sa.Integer, nullable=False, server_default="0"))
    op.add_column("run_steps", sa.Column("total_attempts", sa.Integer, nullable=False, server_default="0"))
    op.add_column("artifacts", sa.Column("step_name", sa.String(64)))


def downgrade() -> None:
    op.drop_column("artifacts", "step_name")
    for c in ("total_attempts", "attempts", "cost", "output", "input"):
        op.drop_column("run_steps", c)
    op.drop_index("uq_runs_one_active_per_line", "runs")
    op.drop_index("ix_runs_line_id", "runs")
    for c in ("heartbeat_at", "cancel_requested", "cost", "trigger", "line_id"):
        op.drop_column("runs", c)
    op.drop_table("production_lines")
