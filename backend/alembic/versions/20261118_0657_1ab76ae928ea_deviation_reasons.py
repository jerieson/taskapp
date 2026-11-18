"""deviation reasons, Planned by default, On-Site default work set-up

Corrections from the owner after checking the team's sheet:
- "Reason for Deviation" is a dropdown: new `deviation_reasons` lookup (seeded with the
  sheet's values) and `prod_logs.deviation_reason_id` replaces the free-text column.
  Existing text that matches a value (case-insensitive) is linked to it; any other
  text is kept by appending it to the row's remarks.
- New rows are Planned unless the user says otherwise (server default true).
- The default work set-up becomes On-Site (when that value exists and is active).

Hand-edited after autogenerate (data steps, server default).

Revision ID: 1ab76ae928ea
Revises: 8f4facd661a4
Create Date: 2026-11-18 06:57:21.042739+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1ab76ae928ea"
down_revision: str | Sequence[str] | None = "8f4facd661a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REASONS = [
    "Unplanned Leaves",
    "Support Issue Prioritization",
    "Unplanned Meetings",
    "Unclear Requirements",
    "Scope Creep",
    "Technical Challenges",
    "External Dependencies",
    "Poor Communication",
    "Testing/Debugging Delays",
    "Underestimation of Task Complexity",
    "Document Revision",
]


def _set_default_work_setup(label: str) -> None:
    """Move the single default to `label`, if that value exists and is active."""
    bind = op.get_bind()
    target = bind.execute(
        sa.text("SELECT id FROM work_setups WHERE lower(label) = lower(:l) AND is_active"),
        {"l": label},
    ).scalar()
    if target is None:
        return
    # Two steps: the single-default index is not deferrable.
    bind.execute(sa.text("UPDATE work_setups SET is_default = false WHERE is_default"))
    bind.execute(sa.text("UPDATE work_setups SET is_default = true WHERE id = :id"), {"id": target})


def upgrade() -> None:
    op.create_table(
        "deviation_reasons",
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deviation_reasons")),
        sa.UniqueConstraint("label", name=op.f("uq_deviation_reasons_label")),
    )
    reasons = sa.table(
        "deviation_reasons", sa.column("label", sa.String), sa.column("sort_order", sa.Integer)
    )
    op.bulk_insert(reasons, [{"label": r, "sort_order": i} for i, r in enumerate(REASONS, 1)])

    op.add_column("prod_logs", sa.Column("deviation_reason_id", sa.Integer(), nullable=True))
    op.create_index(
        op.f("ix_prod_logs_deviation_reason_id"), "prod_logs", ["deviation_reason_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_prod_logs_deviation_reason_id_deviation_reasons"),
        "prod_logs",
        "deviation_reasons",
        ["deviation_reason_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.execute(
        """
        UPDATE prod_logs p SET deviation_reason_id = d.id
        FROM deviation_reasons d
        WHERE lower(trim(p.deviation_reason)) = lower(d.label)
        """
    )
    op.execute(
        """
        UPDATE prod_logs SET description = concat_ws(
            E'\\n', nullif(description, ''), 'Reason for deviation: ' || trim(deviation_reason))
        WHERE deviation_reason_id IS NULL AND nullif(trim(deviation_reason), '') IS NOT NULL
        """
    )
    op.drop_column("prod_logs", "deviation_reason")

    op.alter_column("prod_logs", "is_planned", server_default=sa.true())
    _set_default_work_setup("On-Site")


def downgrade() -> None:
    _set_default_work_setup("Remote")
    op.alter_column("prod_logs", "is_planned", server_default=sa.false())

    op.add_column(
        "prod_logs", sa.Column("deviation_reason", sa.TEXT(), autoincrement=False, nullable=True)
    )
    op.execute(
        """
        UPDATE prod_logs p SET deviation_reason = d.label
        FROM deviation_reasons d WHERE d.id = p.deviation_reason_id
        """
    )
    op.drop_constraint(
        op.f("fk_prod_logs_deviation_reason_id_deviation_reasons"), "prod_logs", type_="foreignkey"
    )
    op.drop_index(op.f("ix_prod_logs_deviation_reason_id"), table_name="prod_logs")
    op.drop_column("prod_logs", "deviation_reason_id")
    op.drop_table("deviation_reasons")
