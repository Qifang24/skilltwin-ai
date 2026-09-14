"""Persist curriculum source files for serverless deployments.

Revision ID: 0003_curriculum_file_content
Revises: 0002_task_curriculum_link
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_curriculum_file_content"
down_revision = "0002_task_curriculum_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    present = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("curriculum_import_batch")}
    if "file_content" not in present:
        op.add_column("curriculum_import_batch", sa.Column("file_content", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column("curriculum_import_batch", "file_content")
