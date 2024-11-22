"""Add UTR settings for BED types

Revision ID: <will_be_generated>
Revises: b42377b4f699
Create Date: <will_be_generated>

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '<will_be_generated>'
down_revision = 'b42377b4f699'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('data_include_5utr', sa.Boolean(), nullable=True, default=False))
        batch_op.add_column(sa.Column('data_include_3utr', sa.Boolean(), nullable=True, default=False))
        batch_op.add_column(sa.Column('sambamba_include_5utr', sa.Boolean(), nullable=True, default=False))
        batch_op.add_column(sa.Column('sambamba_include_3utr', sa.Boolean(), nullable=True, default=False))
        batch_op.add_column(sa.Column('exomeDepth_include_5utr', sa.Boolean(), nullable=True, default=False))
        batch_op.add_column(sa.Column('exomeDepth_include_3utr', sa.Boolean(), nullable=True, default=False))
        batch_op.add_column(sa.Column('cnv_include_5utr', sa.Boolean(), nullable=True, default=False))
        batch_op.add_column(sa.Column('cnv_include_3utr', sa.Boolean(), nullable=True, default=False))


def downgrade():
    with op.batch_alter_table('settings', schema=None) as batch_op:
        batch_op.drop_column('cnv_include_3utr')
        batch_op.drop_column('cnv_include_5utr')
        batch_op.drop_column('exomeDepth_include_3utr')
        batch_op.drop_column('exomeDepth_include_5utr')
        batch_op.drop_column('sambamba_include_3utr')
        batch_op.drop_column('sambamba_include_5utr')
        batch_op.drop_column('data_include_3utr')
        batch_op.drop_column('data_include_5utr')