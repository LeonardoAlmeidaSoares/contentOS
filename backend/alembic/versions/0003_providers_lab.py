"""providers, ai_usage ledger, lab, benchmark, run logs, line archive

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)
MONEY = sa.Numeric(14, 6)
LIVE = "status in ('reserved','succeeded','uncertain')"


def upgrade() -> None:
    op.add_column("production_lines", sa.Column("archived_at", TS))
    op.add_column("runs", sa.Column("config", sa.JSON))
    op.add_column("artifacts", sa.Column("provider", sa.String(120)))
    op.add_column("artifacts", sa.Column("model", sa.String(120)))
    op.add_column("artifacts", sa.Column("meta", sa.JSON))
    op.create_table(
        "run_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("step_name", sa.String(64)),
        sa.Column("level", sa.String(8), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_table(
        "providers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("service", sa.String(32), nullable=False),
        sa.Column("base_url", sa.String(300)),
        sa.Column("credentials_enc", sa.Text),
        sa.Column("credentials_hint", sa.String(16)),
        sa.Column("config", sa.JSON, nullable=False),
        sa.Column("models", sa.JSON, nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("status_message", sa.Text),
        sa.Column("status_checked_at", TS),
        sa.Column("limit_month_usd", MONEY),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_table(
        "ai_usage",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider_id", sa.String(36), sa.ForeignKey("providers.id"), nullable=False, index=True),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("capability", sa.String(16), nullable=False),
        sa.Column("scope", sa.String(8), nullable=False),
        sa.Column("line_id", sa.String(36), index=True),
        sa.Column("run_id", sa.String(36), index=True),
        sa.Column("step_name", sa.String(64)),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("cost_estimated", MONEY, nullable=False),
        sa.Column("cost_actual", MONEY),
        sa.Column("cost_effective", MONEY, nullable=False),
        sa.Column("cost_source", sa.String(12), nullable=False),
        sa.Column("cost_unknown", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("input_tokens", sa.Integer),
        sa.Column("output_tokens", sa.Integer),
        sa.Column("images", sa.Integer, nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("request_id", sa.String(200)),
        sa.Column("error", sa.Text),
        sa.Column("result", sa.JSON),
        sa.Column("created_at", TS, nullable=False, index=True),
        sa.Column("finished_at", TS),
    )
    op.create_index("uq_ai_usage_live_key", "ai_usage", ["idempotency_key"], unique=True,
                    postgresql_where=sa.text(LIVE))
    op.create_table(
        "lab_experiments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("label", sa.String(120)),
        sa.Column("batch_id", sa.String(36), index=True),
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column("negative_prompt", sa.Text),
        sa.Column("params", sa.JSON, nullable=False),
        sa.Column("created_at", TS, nullable=False, index=True),
    )
    op.create_table(
        "lab_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("experiment_id", sa.String(36), sa.ForeignKey("lab_experiments.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("provider_id", sa.String(36), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("run_id", sa.String(36)),
        sa.Column("rating", sa.Integer),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_table(
        "benchmark_prompts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("category", sa.String(120), nullable=False, unique=True),
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column("negative_prompt", sa.Text, nullable=False, server_default=""),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    for t in ("benchmark_prompts", "lab_results", "lab_experiments"):
        op.drop_table(t)
    op.drop_index("uq_ai_usage_live_key", "ai_usage")
    op.drop_table("ai_usage")
    op.drop_table("providers")
    op.drop_table("run_logs")
    for c in ("meta", "model", "provider"):
        op.drop_column("artifacts", c)
    op.drop_column("runs", "config")
    op.drop_column("production_lines", "archived_at")
