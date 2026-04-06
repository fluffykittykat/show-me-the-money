"""add activity_events table

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP

revision: str = 'd4e5f6a7b8c9'
down_revision: str = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'activity_events',
        sa.Column('id', UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column('event_type', sa.String(30), nullable=False),
        sa.Column('headline', sa.String(500), nullable=False),
        sa.Column('detail', sa.Text),
        sa.Column('entity_slug', sa.String(200)),
        sa.Column('entity_name', sa.String(500)),
        sa.Column('metadata', JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column('created_at', TIMESTAMP(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index('ix_activity_events_created_at', 'activity_events', ['created_at'])
    op.create_index('ix_activity_events_event_type', 'activity_events', ['event_type'])


def downgrade() -> None:
    op.drop_table('activity_events')
