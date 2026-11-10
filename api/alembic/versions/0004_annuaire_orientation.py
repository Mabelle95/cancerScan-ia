"""annuaire d'orientation : coordonnées et services des établissements, structure proposée

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None

_json = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column('facilities', sa.Column('latitude', sa.Float(), nullable=True))
    op.add_column('facilities', sa.Column('longitude', sa.Float(), nullable=True))
    op.add_column('facilities', sa.Column('address', sa.String(length=255), nullable=True))
    op.add_column('facilities', sa.Column('phone', sa.String(length=50), nullable=True))
    op.add_column('facilities', sa.Column('services', _json, server_default='[]', nullable=False))
    with op.batch_alter_table('referrals') as batch:
        batch.add_column(sa.Column('proposed_facility_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('suggested_facilities', _json, server_default='[]', nullable=False))
        batch.create_foreign_key('fk_referrals_proposed_facility', 'facilities', ['proposed_facility_id'], ['id'])
        batch.create_index('ix_referrals_proposed_facility_id', ['proposed_facility_id'])


def downgrade() -> None:
    with op.batch_alter_table('referrals') as batch:
        batch.drop_index('ix_referrals_proposed_facility_id')
        batch.drop_constraint('fk_referrals_proposed_facility', type_='foreignkey')
        batch.drop_column('suggested_facilities')
        batch.drop_column('proposed_facility_id')
    for col in ('services', 'phone', 'address', 'longitude', 'latitude'):
        op.drop_column('facilities', col)
