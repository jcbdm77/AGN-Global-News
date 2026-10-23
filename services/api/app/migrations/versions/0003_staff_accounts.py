"""Named staff accounts, invitations, encrypted MFA and recovery codes."""
from alembic import op
import sqlalchemy as sa
revision = '0003_staff_accounts'
down_revision = '0002_sessions'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('staff_accounts',
        sa.Column('username', sa.String(100), primary_key=True),
        sa.Column('password_hash', sa.String(256), nullable=True),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('version', sa.String(64), nullable=False),
        sa.Column('invite_hash', sa.String(64), nullable=True),
        sa.Column('invite_expires', sa.Float(), nullable=True),
        sa.Column('mfa_secret', sa.Text(), nullable=True),
        sa.Column('mfa_pending', sa.Text(), nullable=True),
        sa.Column('mfa_pending_expires', sa.Float(), nullable=True),
        sa.Column('mfa_counter', sa.BigInteger(), nullable=False),
        sa.Column('recovery_hashes', sa.Text(), nullable=False))
    op.create_index('ix_staff_accounts_invite_hash', 'staff_accounts', ['invite_hash'], unique=True)

def downgrade():
    raise RuntimeError('Destructive downgrades require a separately reviewed recovery plan')
