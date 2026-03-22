"""Add performance indexes: composite relationship indexes + GIN full-text search

Revision ID: 003_add_performance_indexes
Revises: 002_add_config_table
Create Date: 2026-03-22
"""

from typing import Sequence, Union

from alembic import op

revision: str = "003_add_performance_indexes"
down_revision: Union[str, None] = "002_add_config_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Composite indexes for relationship queries filtered by type
    op.create_index(
        "ix_rel_from_type",
        "relationships",
        ["from_entity_id", "relationship_type"],
    )
    op.create_index(
        "ix_rel_to_type",
        "relationships",
        ["to_entity_id", "relationship_type"],
    )

    # GIN full-text search index on entities
    op.execute(
        "CREATE INDEX ix_entities_fts ON entities "
        "USING gin(to_tsvector('english', name || ' ' || coalesce(summary, '')))"
    )


def downgrade() -> None:
    op.drop_index("ix_entities_fts", table_name="entities")
    op.drop_index("ix_rel_to_type", table_name="relationships")
    op.drop_index("ix_rel_from_type", table_name="relationships")
