"""Frozen initial AGN schema. Never edit after deployment."""
from alembic import op
import sqlalchemy as sa
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None

def baseline_metadata():
    metadata = sa.MetaData()
    sa.Table('stories', metadata,
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('category', sa.String(length=80), nullable=False, primary_key=False),
        sa.Column('risk', sa.String(length=20), nullable=False, primary_key=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
    )
    sa.Index('ix_stories_category', metadata.tables['stories'].c['category'], unique=False)
    sa.Table('editions', metadata,
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('story_id', sa.Integer(), sa.ForeignKey('stories.id'), nullable=False, primary_key=False),
        sa.Column('locale', sa.String(length=5), nullable=False, primary_key=False),
        sa.Column('slug', sa.String(length=200), nullable=False, primary_key=False),
        sa.Column('headline', sa.String(length=350), nullable=False, primary_key=False),
        sa.Column('body', sa.Text(), nullable=False, primary_key=False),
        sa.Column('state', sa.String(length=30), nullable=False, primary_key=False),
        sa.Column('provenance_reviewed', sa.Boolean(), nullable=False, primary_key=False),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True, primary_key=False),
        sa.UniqueConstraint('locale', 'slug', name='uq_locale_slug'),
        sa.UniqueConstraint('story_id', 'locale', name='uq_story_locale'),
    )
    sa.Index('ix_editions_locale', metadata.tables['editions'].c['locale'], unique=False)
    sa.Index('ix_editions_state', metadata.tables['editions'].c['state'], unique=False)
    sa.Index('ix_editions_story_id', metadata.tables['editions'].c['story_id'], unique=False)
    sa.Table('audit_events', metadata,
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('edition_id', sa.Integer(), sa.ForeignKey('editions.id'), nullable=False, primary_key=False),
        sa.Column('actor', sa.String(length=150), nullable=False, primary_key=False),
        sa.Column('action', sa.String(length=100), nullable=False, primary_key=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
    )
    sa.Table('sources', metadata,
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('edition_id', sa.Integer(), sa.ForeignKey('editions.id'), nullable=False, primary_key=False),
        sa.Column('publisher', sa.String(length=200), nullable=False, primary_key=False),
        sa.Column('url', sa.String(length=2000), nullable=False, primary_key=False),
        sa.Column('rights_status', sa.String(length=30), nullable=False, primary_key=False),
    )
    return metadata

def upgrade():
    baseline_metadata().create_all(op.get_bind(), checkfirst=False)

def downgrade():
    raise RuntimeError('Destructive downgrades require a separately reviewed recovery plan')
