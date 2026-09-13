"""Create or reconcile the professional-construction schema."""
from alembic import op
import sqlalchemy as sa

revision = "0001_professional_closed_loop"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The pre-existing project used SQLAlchemy create_all. Keep this first
    # migration additive and idempotent so existing SQLite data is preserved.
    from app.core.db import Base
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=op.get_bind())

    # create_all intentionally never mutates existing tables.  Reconcile the
    # three pre-existing tables column-by-column so installations created by
    # older releases are upgraded without dropping or copying user data.
    bind = op.get_bind()

    def add_missing(table: str, columns: list[sa.Column]) -> None:
        present = {column["name"] for column in sa.inspect(bind).get_columns(table)}
        for column in columns:
            if column.name not in present:
                op.add_column(table, column)

    add_missing("job_posting", [
        sa.Column("company_name", sa.String(255), nullable=True),
        # SQLite cannot add a FK constraint in-place; referential validation is
        # still enforced by the service and new databases get the model FK.
        sa.Column("import_batch_id", sa.String(96), nullable=True),
        sa.Column("source_record_id", sa.String(255), nullable=True),
        sa.Column("dedupe_hash", sa.String(64), nullable=True),
    ])
    add_missing("curriculum_course", [
        sa.Column("objectives", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("teaching_content", sa.Text(), nullable=True),
        sa.Column("knowledge_points", sa.Text(), nullable=True),
        sa.Column("practical_content", sa.Text(), nullable=True),
        sa.Column("learning_outcomes", sa.Text(), nullable=True),
        sa.Column("field_evidence", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    ])
    add_missing("course_skill_coverage", [
        sa.Column("coverage_status", sa.String(32), nullable=False, server_default="partial"),
        sa.Column("origin", sa.String(32), nullable=False, server_default="rule"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("generation_run_id", sa.String(64), nullable=True),
        sa.Column("teacher_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("edited_by", sa.String(128), nullable=True),
    ])
    posting_indexes = {item["name"] for item in sa.inspect(bind).get_indexes("job_posting")}
    if "ix_posting_dedupe_hash" not in posting_indexes:
        op.create_index("ix_posting_dedupe_hash", "job_posting", ["dedupe_hash"], unique=False)


def downgrade() -> None:
    # Never drop production data implicitly.
    pass
