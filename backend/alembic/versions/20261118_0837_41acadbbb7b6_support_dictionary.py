"""support dictionary (replaces personal processes)

- New `support_types` lookup, seeded with the team's types, and `support_entries`.
- Personal processes are removed: processes, process_steps, process_runs and the task
  columns pointing at them (their tasks stay as ordinary tasks).

Hand-edited after autogenerate (drop order, seed, downgrade order).

Revision ID: 41acadbbb7b6
Revises: bcfefda057f3
Create Date: 2026-11-18 08:37:41.673993+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "41acadbbb7b6"
down_revision: str | Sequence[str] | None = "bcfefda057f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUPPORT_TYPES = ["Concern", "Inquiry", "Bug", "Request", "Data Modification", "Transport"]


def upgrade() -> None:
    op.create_table(
        "support_types",
        sa.Column("color", sa.String(length=7), nullable=True),
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("label", sa.String(length=50), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.CheckConstraint("color ~ '^#[0-9A-Fa-f]{6}$'", name=op.f("ck_support_types_color_hex")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_types")),
        sa.UniqueConstraint("label", name=op.f("uq_support_types_label")),
    )
    op.create_table(
        "support_entries",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("type_id", sa.Integer(), nullable=False),
        sa.Column("project", sa.String(length=100), nullable=True),
        sa.Column("module", sa.String(length=100), nullable=True),
        sa.Column("sub_module", sa.String(length=100), nullable=True),
        sa.Column("concern", sa.Text(), nullable=False),
        sa.Column("cause", sa.Text(), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("query", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_support_entries_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["type_id"],
            ["support_types.id"],
            name=op.f("fk_support_entries_type_id_support_types"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"], name=op.f("fk_support_entries_updated_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_entries")),
    )
    op.create_index(
        op.f("ix_support_entries_created_by"), "support_entries", ["created_by"], unique=False
    )
    op.create_index(
        op.f("ix_support_entries_is_active_created_at"),
        "support_entries",
        ["is_active", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_support_entries_type_id"), "support_entries", ["type_id"], unique=False
    )
    types = sa.table(
        "support_types", sa.column("label", sa.String), sa.column("sort_order", sa.Integer)
    )
    op.bulk_insert(types, [{"label": t, "sort_order": i} for i, t in enumerate(SUPPORT_TYPES, 1)])

    # Tasks first: they reference process_runs and process_steps. Dropping the columns
    # also drops the step_requires_run CHECK.
    op.drop_index(op.f("ix_tasks_process_run_id"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_process_step_id"), table_name="tasks")
    op.drop_constraint(op.f("fk_tasks_process_run_id_process_runs"), "tasks", type_="foreignkey")
    op.drop_constraint(op.f("fk_tasks_process_step_id_process_steps"), "tasks", type_="foreignkey")
    op.drop_column("tasks", "process_step_id")
    op.drop_column("tasks", "process_run_id")
    op.drop_table("process_runs")
    op.drop_table("process_steps")
    op.drop_table("processes")


def downgrade() -> None:
    """Recreates the empty process tables; removed processes and runs are not restored.
    Support entries and types are dropped."""
    op.create_table(
        "processes",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_processes_owner_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_processes")),
    )
    op.create_index(op.f("ix_processes_owner_id"), "processes", ["owner_id"], unique=False)
    op.create_table(
        "process_steps",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("default_category_id", sa.Integer(), nullable=True),
        sa.Column("estimated_hours", sa.Numeric(precision=4, scale=2), nullable=True),
        sa.CheckConstraint(
            "estimated_hours > 0", name=op.f("ck_process_steps_estimated_hours_positive")
        ),
        sa.ForeignKeyConstraint(
            ["default_category_id"],
            ["categories.id"],
            name=op.f("fk_process_steps_default_category_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["process_id"],
            ["processes.id"],
            name=op.f("fk_process_steps_process_id_processes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_process_steps")),
    )
    op.create_index(
        op.f("ix_process_steps_process_id"), "process_steps", ["process_id"], unique=False
    )
    op.create_index(
        op.f("ix_process_steps_default_category_id"),
        "process_steps",
        ["default_category_id"],
        unique=False,
    )
    op.create_table(
        "process_runs",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "status", sa.String(length=32), server_default=sa.text("'in_progress'"), nullable=False
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('in_progress', 'completed', 'cancelled')",
            name=op.f("ck_process_runs_status"),
        ),
        sa.ForeignKeyConstraint(
            ["process_id"],
            ["processes.id"],
            name=op.f("fk_process_runs_process_id_processes"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_process_runs_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_process_runs")),
    )
    op.create_index(op.f("ix_process_runs_user_id"), "process_runs", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_process_runs_process_id"), "process_runs", ["process_id"], unique=False
    )
    op.add_column("tasks", sa.Column("process_run_id", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("process_step_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_tasks_process_step_id_process_steps"),
        "tasks",
        "process_steps",
        ["process_step_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_tasks_process_run_id_process_runs"),
        "tasks",
        "process_runs",
        ["process_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        op.f("ck_tasks_step_requires_run"),
        "tasks",
        "process_step_id IS NULL OR process_run_id IS NOT NULL",
    )
    op.create_index(op.f("ix_tasks_process_step_id"), "tasks", ["process_step_id"], unique=False)
    op.create_index(op.f("ix_tasks_process_run_id"), "tasks", ["process_run_id"], unique=False)

    op.drop_index(op.f("ix_support_entries_type_id"), table_name="support_entries")
    op.drop_index(op.f("ix_support_entries_is_active_created_at"), table_name="support_entries")
    op.drop_index(op.f("ix_support_entries_created_by"), table_name="support_entries")
    op.drop_table("support_entries")
    op.drop_table("support_types")
