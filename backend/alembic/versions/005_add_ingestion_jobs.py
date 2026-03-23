"""Add ingestion_jobs table for tracking batch ingestion progress

Revision ID: 005_add_ingestion_jobs
Revises: 004_money_trail_view
Create Date: 2026-03-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "005_add_ingestion_jobs"
down_revision: Union[str, None] = "004_money_trail_view"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ingestion_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("job_type", sa.String(100), nullable=False),
        sa.Column(
            "status",
            sa.String(50),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "progress",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "total",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "started_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "completed_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "errors",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ingestion_jobs_status", "ingestion_jobs", ["status"])
    op.create_index(
        "ix_ingestion_jobs_job_type_status",
        "ingestion_jobs",
        ["job_type", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_ingestion_jobs_job_type_status", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_status", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
