"""Add money_trail SQL view for efficient bill-voter-donor queries

Revision ID: 004_money_trail_view
Revises: 003_add_performance_indexes
Create Date: 2026-03-22
"""

from typing import Sequence, Union

from alembic import op

revision: str = "004_money_trail_view"
down_revision: Union[str, None] = "003_add_performance_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE OR REPLACE VIEW money_trail AS
    SELECT
        b.slug as bill_slug,
        b.name as bill_name,
        p.slug as senator_slug,
        p.name as senator_name,
        r_vote.relationship_type as vote,
        d.slug as donor_slug,
        d.name as donor_name,
        r_donate.amount_usd,
        r_donate.date_start as donation_date,
        r_vote.date_start as vote_date
    FROM entities b
    JOIN relationships r_vote ON r_vote.to_entity_id = b.id
        AND r_vote.relationship_type IN ('voted_yes', 'voted_no')
    JOIN entities p ON p.id = r_vote.from_entity_id
    LEFT JOIN relationships r_donate ON r_donate.to_entity_id = p.id
        AND r_donate.relationship_type = 'donated_to'
    LEFT JOIN entities d ON d.id = r_donate.from_entity_id
    WHERE b.entity_type = 'bill'
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS money_trail")
