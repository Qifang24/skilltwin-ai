"""Link generated training tasks to curriculum plans and courses."""

from alembic import op
import sqlalchemy as sa


revision = "0002_task_curriculum_link"
down_revision = "0001_professional_closed_loop"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add nullable columns without rewriting or deleting existing task rows.

    Fresh databases receive the model-level foreign keys through ``create_all``.
    Existing SQLite databases cannot add foreign-key constraints in place, so
    this additive migration relies on service validation while preserving every
    historical row. PostgreSQL deployments may add constraints separately once
    they have verified historical values.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "training_task" not in inspector.get_table_names():
        return

    present = {column["name"] for column in inspector.get_columns("training_task")}
    if "plan_id" not in present:
        op.add_column("training_task", sa.Column("plan_id", sa.String(96), nullable=True))
    if "course_id" not in present:
        op.add_column("training_task", sa.Column("course_id", sa.String(128), nullable=True))

    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("training_task")}
    if "ix_task_plan" not in indexes:
        op.create_index("ix_task_plan", "training_task", ["plan_id"], unique=False)
    if "ix_task_course" not in indexes:
        op.create_index("ix_task_course", "training_task", ["course_id"], unique=False)


def downgrade() -> None:
    # Link columns carry audit history; never remove them implicitly.
    pass
