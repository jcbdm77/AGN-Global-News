from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey, UniqueConstraint, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

def utcnow(): return datetime.now(timezone.utc)

class Story(Base):
    __tablename__ = 'stories'
    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    risk: Mapped[str] = mapped_column(String(20), default='unassessed')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    editions: Mapped[list['Edition']] = relationship(back_populates='story')

class Edition(Base):
    __tablename__ = 'editions'
    __table_args__ = (UniqueConstraint('locale','slug', name='uq_locale_slug'), UniqueConstraint('story_id','locale',name='uq_story_locale'))
    id: Mapped[int] = mapped_column(primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey('stories.id'), index=True)
    locale: Mapped[str] = mapped_column(String(5), index=True)
    slug: Mapped[str] = mapped_column(String(200))
    headline: Mapped[str] = mapped_column(String(350))
    body: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(30), default='draft', index=True)
    provenance_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    story: Mapped['Story'] = relationship(back_populates='editions')
    sources: Mapped[list['Source']] = relationship(back_populates='edition')

class Source(Base):
    __tablename__ = 'sources'
    id: Mapped[int] = mapped_column(primary_key=True)
    edition_id: Mapped[int] = mapped_column(ForeignKey('editions.id'))
    publisher: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(String(2000))
    rights_status: Mapped[str] = mapped_column(String(30), default='unverified')
    edition: Mapped['Edition'] = relationship(back_populates='sources')

class AuditEvent(Base):
    __tablename__ = 'audit_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    edition_id: Mapped[int] = mapped_column(ForeignKey('editions.id'))
    actor: Mapped[str] = mapped_column(String(150))
    action: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

# Only token hashes persist; browser session tokens never enter the database.
from sqlalchemy import Float

class AuthSession(Base):
    __tablename__ = 'auth_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor: Mapped[str] = mapped_column(String(100))
    credential_version: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[float] = mapped_column(Float, index=True)

class AuthAttempt(Base):
    __tablename__ = 'auth_attempts'
    bucket_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int] = mapped_column()
    expires_at: Mapped[float] = mapped_column(Float)

from sqlalchemy import BigInteger

class StaffAccount(Base):
    __tablename__ = 'staff_accounts'
    username: Mapped[str] = mapped_column(String(100), primary_key=True)
    password_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    role: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[str] = mapped_column(String(64))
    invite_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    invite_expires: Mapped[float | None] = mapped_column(Float, nullable=True)
    mfa_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    mfa_pending: Mapped[str | None] = mapped_column(Text, nullable=True)
    mfa_pending_expires: Mapped[float | None] = mapped_column(Float, nullable=True)
    mfa_counter: Mapped[int] = mapped_column(BigInteger, default=-1)
    recovery_hashes: Mapped[str] = mapped_column(Text, default='[]')
