"""Added ModeSchedule model

Revision ID: ba16e4887492
Revises: 493669d0b033
Create Date: 2025-04-02 11:58:27.432716

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ba16e4887492'
down_revision = '493669d0b033'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('mode_schedule',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('mode_type', sa.String(length=256), nullable=False),
    sa.Column('people_cnt', sa.Integer(), nullable=False),
    sa.Column('rep_name', sa.String(length=256), nullable=False),
    sa.Column('start_time', sa.DateTime(), nullable=False),
    sa.Column('end_time', sa.DateTime(), nullable=False),
    sa.Column('memo', sa.String(length=256), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('mode_schedule')
    # ### end Alembic commands ###
