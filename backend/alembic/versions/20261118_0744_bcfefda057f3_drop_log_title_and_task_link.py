"""drop log title and task link

Owner feedback: prod logs are no longer linked to tasks (tasks are their own module),
and the short note ("title") is gone. An existing note is kept by moving it to the
front of the row's remarks as "note - remarks", the same text the CSV export already
wrote to the Remarks column. Task links are dropped.

Hand-edited after autogenerate (data step).

Revision ID: bcfefda057f3
Revises: 1ab76ae928ea
Create Date: 2026-11-18 07:44:41.195398+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bcfefda057f3"
down_revision: str | Sequence[str] | None = "1ab76ae928ea"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE prod_logs
        SET description = CASE
            WHEN description IS NULL OR description = '' THEN title
            ELSE title || ' - ' || description
        END
        WHERE title IS NOT NULL AND title <> ''
        """
    )
    op.drop_index(op.f("ix_prod_logs_task_id"), table_name="prod_logs")
    op.drop_constraint(op.f("fk_prod_logs_task_id_tasks"), "prod_logs", type_="foreignkey")
    op.drop_column("prod_logs", "task_id")
    op.drop_column("prod_logs", "title")


def downgrade() -> None:
    # Notes stay in the remarks and task links are not restored.
    op.add_column(
        "prod_logs", sa.Column("title", sa.VARCHAR(length=200), autoincrement=False, nullable=True)
    )
    op.add_column(
        "prod_logs", sa.Column("task_id", sa.INTEGER(), autoincrement=False, nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_prod_logs_task_id_tasks"),
        "prod_logs",
        "tasks",
        ["task_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_prod_logs_task_id"), "prod_logs", ["task_id"], unique=False)
