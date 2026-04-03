"""add trade_alerts and alert_subscriptions tables

Revision ID: c3d4e5f6a7b8
Revises: a87ed4c3a1f4
Create Date: 2026-04-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP

revision: str = 'c3d4e5f6a7b8'
down_revision: str = 'a87ed4c3a1f4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'trade_alerts',
        sa.Column('id', UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column('relationship_id', UUID(as_uuid=True), sa.ForeignKey('relationships.id'), unique=True, nullable=False),
        sa.Column('official_id', UUID(as_uuid=True), sa.ForeignKey('entities.id'), nullable=False),
        sa.Column('ticker', sa.String(20), nullable=False),
        sa.Column('transaction_type', sa.String(50)),
        sa.Column('amount_label', sa.String(100)),
        sa.Column('trade_date', sa.Date),
        sa.Column('filed_date', sa.Date),
        sa.Column('alert_level', sa.String(30), server_default='ROUTINE'),
        sa.Column('narrative', sa.Text),
        sa.Column('signals', JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column('context', JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column('source', sa.String(30), server_default='senate_efd'),
        sa.Column('status', sa.String(20), server_default='new'),
        sa.Column('notified_at', TIMESTAMP(timezone=True)),
        sa.Column('created_at', TIMESTAMP(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index('ix_trade_alerts_official_id', 'trade_alerts', ['official_id'])
    op.create_index('ix_trade_alerts_ticker', 'trade_alerts', ['ticker'])
    op.create_index('ix_trade_alerts_status', 'trade_alerts', ['status'])
    op.create_index('ix_trade_alerts_created_at', 'trade_alerts', ['created_at'])

    op.create_table(
        'alert_subscriptions',
        sa.Column('id', UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column('sub_type', sa.String(20), nullable=False),
        sa.Column('target_value', sa.String(200), nullable=False),
        sa.Column('channel', sa.String(20), server_default='feed'),
        sa.Column('channel_target', sa.String(200)),
        sa.Column('is_active', sa.Boolean, server_default=sa.text('true')),
        sa.Column('created_at', TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.Column('updated_at', TIMESTAMP(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index('ix_alert_subs_type_target', 'alert_subscriptions', ['sub_type', 'target_value'])
    op.create_index('ix_alert_subs_channel_active', 'alert_subscriptions', ['channel', 'is_active'])


def downgrade() -> None:
    op.drop_table('alert_subscriptions')
    op.drop_table('trade_alerts')
