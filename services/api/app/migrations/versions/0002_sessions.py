"""Durable staging sessions and login throttles; article tables unchanged."""
from alembic import op
import sqlalchemy as sa
revision = '0002_sessions'
down_revision = '0001_initial'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('auth_sessions',
        sa.Column('token_hash', sa.String(64), primary_key=True),
        sa.Column('actor', sa.String(100), nullable=False),
        sa.Column('credential_version', sa.String(64), nullable=False),
        sa.Column('expires_at', sa.Float(), nullable=False))
    op.create_index('ix_auth_sessions_expires_at', 'auth_sessions', ['expires_at'])
    op.create_table('auth_attempts',
        sa.Column('bucket_hash', sa.String(64), primary_key=True),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('expires_at', sa.Float(), nullable=False))

def downgrade():
    raise RuntimeError('Destructive downgrades require a separately reviewed recovery plan')
