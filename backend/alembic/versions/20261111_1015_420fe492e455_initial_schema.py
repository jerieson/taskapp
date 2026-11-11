"""initial schema

Hand-reviewed after autogenerate:
- Role/status/feature columns are VARCHAR + explicit CHECK constraints (not native ENUMs).
- Partial unique indexes keep a single default row in statuses and priorities.
- CHECK constraints and ON DELETE rules match CLAUDE.md "Delete behaviour".

Revision ID: 420fe492e455
Revises:
Create Date: 2026-11-11 10:15:08.859901+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "420fe492e455"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("label", sa.String(length=50), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.CheckConstraint("color ~ '^#[0-9A-Fa-f]{6}$'", name=op.f("ck_categories_color_hex")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
        sa.UniqueConstraint("label", name=op.f("uq_categories_label")),
    )
    op.create_table(
        "priorities",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("label", sa.String(length=50), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.CheckConstraint("color ~ '^#[0-9A-Fa-f]{6}$'", name=op.f("ck_priorities_color_hex")),
        sa.CheckConstraint(
            "is_active OR NOT is_default", name=op.f("ck_priorities_default_is_active")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_priorities")),
        sa.UniqueConstraint("label", name=op.f("uq_priorities_label")),
    )
    op.create_index(
        "uq_priorities_single_default",
        "priorities",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
        sa.UniqueConstraint("name", name=op.f("uq_projects_name")),
    )
    op.create_table(
        "statuses",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("label", sa.String(length=50), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_done", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.CheckConstraint("color ~ '^#[0-9A-Fa-f]{6}$'", name=op.f("ck_statuses_color_hex")),
        sa.CheckConstraint(
            "is_active OR NOT is_default", name=op.f("ck_statuses_default_is_active")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_statuses")),
        sa.UniqueConstraint("label", name=op.f("uq_statuses_label")),
    )
    op.create_index(
        "uq_statuses_single_default",
        "statuses",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )
    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teams")),
        sa.UniqueConstraint("name", name=op.f("uq_teams_name")),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("google_sub", sa.String(length=255), nullable=True),
        sa.Column(
            "role",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column("team_id", sa.Integer(), nullable=True),
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
        sa.CheckConstraint(
            "(role = 'admin' AND team_id IS NULL) OR (role <> 'admin' AND team_id IS NOT NULL)",
            name=op.f("ck_users_team_matches_role"),
        ),
        sa.CheckConstraint(
            "password_hash IS NOT NULL OR google_sub IS NOT NULL",
            name=op.f("ck_users_has_login_method"),
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name=op.f("fk_users_team_id_teams"), ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "role IN ('admin', 'manager', 'dev')",
            name=op.f("ck_users_role"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.UniqueConstraint("google_sub", name=op.f("uq_users_google_sub")),
        sa.UniqueConstraint("username", name=op.f("uq_users_username")),
    )
    op.create_index(op.f("ix_users_team_id"), "users", ["team_id"], unique=False)
    op.create_table(
        "ai_requests",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "feature",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0",
            name=op.f("ck_ai_requests_tokens_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_ai_requests_user_id_users")
        ),
        sa.CheckConstraint(
            "feature IN ('nl_log_entry', 'daily_plan', 'team_summary')",
            name=op.f("ck_ai_requests_feature"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_requests")),
    )
    op.create_index(
        op.f("ix_ai_requests_user_id_created_at"),
        "ai_requests",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "ai_summaries",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("requested_by", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("period_end >= period_start", name=op.f("ck_ai_summaries_period_order")),
        sa.ForeignKeyConstraint(
            ["requested_by"], ["users.id"], name=op.f("fk_ai_summaries_requested_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            name=op.f("fk_ai_summaries_team_id_teams"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_summaries")),
    )
    op.create_index(
        op.f("ix_ai_summaries_requested_by"), "ai_summaries", ["requested_by"], unique=False
    )
    op.create_index(
        op.f("ix_ai_summaries_team_id_period_start_period_end"),
        "ai_summaries",
        ["team_id", "period_start", "period_end"],
        unique=False,
    )
    op.create_table(
        "daily_plans",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("plan_date", sa.Date(), nullable=False),
        sa.Column("ai_generated", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_daily_plans_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_daily_plans")),
        sa.UniqueConstraint("user_id", "plan_date", name=op.f("uq_daily_plans_user_id_plan_date")),
    )
    op.create_table(
        "invites",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column(
            "role",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("role <> 'admin'", name=op.f("ck_invites_role_not_admin")),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_invites_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name=op.f("fk_invites_team_id_teams"), ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "role IN ('admin', 'manager', 'dev')",
            name=op.f("ck_invites_role"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invites")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_invites_token_hash")),
    )
    op.create_index(op.f("ix_invites_created_by"), "invites", ["created_by"], unique=False)
    op.create_index(op.f("ix_invites_email"), "invites", ["email"], unique=False)
    op.create_index(op.f("ix_invites_team_id"), "invites", ["team_id"], unique=False)
    op.create_table(
        "password_resets",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_password_resets_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_password_resets_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_password_resets")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_password_resets_token_hash")),
    )
    op.create_index(
        op.f("ix_password_resets_created_by"), "password_resets", ["created_by"], unique=False
    )
    op.create_index(
        op.f("ix_password_resets_user_id"), "password_resets", ["user_id"], unique=False
    )
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
        "sessions",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("csrf_token", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_sessions_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_sessions_token_hash")),
    )
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], unique=False)
    op.create_table(
        "process_runs",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="in_progress",
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["process_id"],
            ["processes.id"],
            name=op.f("fk_process_runs_process_id_processes"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_process_runs_user_id_users")
        ),
        sa.CheckConstraint(
            "status IN ('in_progress', 'completed', 'cancelled')",
            name=op.f("ck_process_runs_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_process_runs")),
    )
    op.create_index(
        op.f("ix_process_runs_process_id"), "process_runs", ["process_id"], unique=False
    )
    op.create_index(op.f("ix_process_runs_user_id"), "process_runs", ["user_id"], unique=False)
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
        op.f("ix_process_steps_default_category_id"),
        "process_steps",
        ["default_category_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_process_steps_process_id"), "process_steps", ["process_id"], unique=False
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("status_id", sa.Integer(), nullable=False),
        sa.Column("priority_id", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("process_run_id", sa.Integer(), nullable=True),
        sa.Column("process_step_id", sa.Integer(), nullable=True),
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
        sa.CheckConstraint(
            "process_step_id IS NULL OR process_run_id IS NOT NULL",
            name=op.f("ck_tasks_step_requires_run"),
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_tasks_category_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["priority_id"],
            ["priorities.id"],
            name=op.f("fk_tasks_priority_id_priorities"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["process_run_id"],
            ["process_runs.id"],
            name=op.f("fk_tasks_process_run_id_process_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["process_step_id"],
            ["process_steps.id"],
            name=op.f("fk_tasks_process_step_id_process_steps"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_tasks_project_id_projects"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["status_id"],
            ["statuses.id"],
            name=op.f("fk_tasks_status_id_statuses"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_tasks_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
    )
    op.create_index(op.f("ix_tasks_category_id"), "tasks", ["category_id"], unique=False)
    op.create_index(op.f("ix_tasks_priority_id"), "tasks", ["priority_id"], unique=False)
    op.create_index(op.f("ix_tasks_process_run_id"), "tasks", ["process_run_id"], unique=False)
    op.create_index(op.f("ix_tasks_process_step_id"), "tasks", ["process_step_id"], unique=False)
    op.create_index(op.f("ix_tasks_project_id"), "tasks", ["project_id"], unique=False)
    op.create_index(op.f("ix_tasks_status_id"), "tasks", ["status_id"], unique=False)
    op.create_index(op.f("ix_tasks_user_id"), "tasks", ["user_id"], unique=False)
    op.create_table(
        "daily_plan_items",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("daily_plan_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("item_order", sa.Integer(), nullable=False),
        sa.Column("suggested_hours", sa.Numeric(precision=4, scale=2), nullable=True),
        sa.Column("ai_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "suggested_hours > 0 AND suggested_hours <= 24",
            name=op.f("ck_daily_plan_items_suggested_hours_range"),
        ),
        sa.ForeignKeyConstraint(
            ["daily_plan_id"],
            ["daily_plans.id"],
            name=op.f("fk_daily_plan_items_daily_plan_id_daily_plans"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_daily_plan_items_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_daily_plan_items")),
        sa.UniqueConstraint(
            "daily_plan_id", "task_id", name=op.f("uq_daily_plan_items_daily_plan_id_task_id")
        ),
    )
    op.create_index(
        op.f("ix_daily_plan_items_task_id"), "daily_plan_items", ["task_id"], unique=False
    )
    op.create_table(
        "prod_logs",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=True),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("log_date", sa.Date(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("hours_spent", sa.Numeric(precision=4, scale=2), nullable=False),
        sa.Column("updated_by", sa.Integer(), nullable=False),
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
        sa.CheckConstraint(
            "hours_spent > 0 AND hours_spent <= 24", name=op.f("ck_prod_logs_hours_spent_range")
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_prod_logs_category_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_prod_logs_project_id_projects"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.id"], name=op.f("fk_prod_logs_task_id_tasks"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name=op.f("fk_prod_logs_team_id_teams"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"], name=op.f("fk_prod_logs_updated_by_users")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_prod_logs_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prod_logs")),
    )
    op.create_index(op.f("ix_prod_logs_category_id"), "prod_logs", ["category_id"], unique=False)
    op.create_index(op.f("ix_prod_logs_project_id"), "prod_logs", ["project_id"], unique=False)
    op.create_index(op.f("ix_prod_logs_task_id"), "prod_logs", ["task_id"], unique=False)
    op.create_index(
        op.f("ix_prod_logs_team_id_log_date"), "prod_logs", ["team_id", "log_date"], unique=False
    )
    op.create_index(op.f("ix_prod_logs_updated_by"), "prod_logs", ["updated_by"], unique=False)
    op.create_index(
        op.f("ix_prod_logs_user_id_log_date"), "prod_logs", ["user_id", "log_date"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_prod_logs_user_id_log_date"), table_name="prod_logs")
    op.drop_index(op.f("ix_prod_logs_updated_by"), table_name="prod_logs")
    op.drop_index(op.f("ix_prod_logs_team_id_log_date"), table_name="prod_logs")
    op.drop_index(op.f("ix_prod_logs_task_id"), table_name="prod_logs")
    op.drop_index(op.f("ix_prod_logs_project_id"), table_name="prod_logs")
    op.drop_index(op.f("ix_prod_logs_category_id"), table_name="prod_logs")
    op.drop_table("prod_logs")
    op.drop_index(op.f("ix_daily_plan_items_task_id"), table_name="daily_plan_items")
    op.drop_table("daily_plan_items")
    op.drop_index(op.f("ix_tasks_user_id"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_status_id"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_project_id"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_process_step_id"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_process_run_id"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_priority_id"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_category_id"), table_name="tasks")
    op.drop_table("tasks")
    op.drop_index(op.f("ix_process_steps_process_id"), table_name="process_steps")
    op.drop_index(op.f("ix_process_steps_default_category_id"), table_name="process_steps")
    op.drop_table("process_steps")
    op.drop_index(op.f("ix_process_runs_user_id"), table_name="process_runs")
    op.drop_index(op.f("ix_process_runs_process_id"), table_name="process_runs")
    op.drop_table("process_runs")
    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_table("sessions")
    op.drop_index(op.f("ix_processes_owner_id"), table_name="processes")
    op.drop_table("processes")
    op.drop_index(op.f("ix_password_resets_user_id"), table_name="password_resets")
    op.drop_index(op.f("ix_password_resets_created_by"), table_name="password_resets")
    op.drop_table("password_resets")
    op.drop_index(op.f("ix_invites_team_id"), table_name="invites")
    op.drop_index(op.f("ix_invites_email"), table_name="invites")
    op.drop_index(op.f("ix_invites_created_by"), table_name="invites")
    op.drop_table("invites")
    op.drop_table("daily_plans")
    op.drop_index(
        op.f("ix_ai_summaries_team_id_period_start_period_end"), table_name="ai_summaries"
    )
    op.drop_index(op.f("ix_ai_summaries_requested_by"), table_name="ai_summaries")
    op.drop_table("ai_summaries")
    op.drop_index(op.f("ix_ai_requests_user_id_created_at"), table_name="ai_requests")
    op.drop_table("ai_requests")
    op.drop_index(op.f("ix_users_team_id"), table_name="users")
    op.drop_table("users")
    op.drop_table("teams")
    op.drop_index(
        "uq_statuses_single_default", table_name="statuses", postgresql_where=sa.text("is_default")
    )
    op.drop_table("statuses")
    op.drop_table("projects")
    op.drop_index(
        "uq_priorities_single_default",
        table_name="priorities",
        postgresql_where=sa.text("is_default"),
    )
    op.drop_table("priorities")
    op.drop_table("categories")
