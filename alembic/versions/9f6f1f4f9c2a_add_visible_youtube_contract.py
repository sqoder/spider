"""add visible youtube capture contract

Revision ID: 9f6f1f4f9c2a
Revises: c03f96dbc38c
Create Date: 2026-05-04 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


revision: str = "9f6f1f4f9c2a"
down_revision: Union[str, None] = "c03f96dbc38c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.add_column("posts", sa.Column("visible_data", json_type, nullable=True))
    op.add_column("posts", sa.Column("raw_sources", json_type, nullable=True))
    op.add_column("posts", sa.Column("capture_meta", json_type, nullable=True))

    op.add_column("comments", sa.Column("visible_data", json_type, nullable=True))
    op.add_column("comments", sa.Column("raw_sources", json_type, nullable=True))
    op.add_column("comments", sa.Column("capture_meta", json_type, nullable=True))

    op.add_column("authors", sa.Column("visible_data", json_type, nullable=True))
    op.add_column("media_assets", sa.Column("visible_data", json_type, nullable=True))


def downgrade() -> None:
    op.drop_column("media_assets", "visible_data")
    op.drop_column("authors", "visible_data")

    op.drop_column("comments", "capture_meta")
    op.drop_column("comments", "raw_sources")
    op.drop_column("comments", "visible_data")

    op.drop_column("posts", "capture_meta")
    op.drop_column("posts", "raw_sources")
    op.drop_column("posts", "visible_data")
