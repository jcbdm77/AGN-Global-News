"""Single-admin staging authentication with durable, hashed sessions."""
import hashlib
import os
import secrets
import hmac
import time
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

router = APIRouter(prefix='/auth')
COOKIE = 'agn_session'
TTL = 3600


def secret(name):
    filename = os.getenv(name + '_FILE')
    return Path(filename).read_text().strip() if filename else os.getenv(name, '')



_generated_hash = ''

def admin_hash():
    return secret('STAGING_ADMIN_HASH') or _generated_hash

def initialize_admin():
    """Accept a platform-generated secret without storing it in source or logs."""
    global _generated_hash
    if secret('STAGING_ADMIN_HASH'):
        configured()
        return
    password = secret('STAGING_ADMIN_PASSWORD')
    if len(password) < 32:
        raise RuntimeError('Configure a generated staging administrator secret')
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32).hex()
    _generated_hash = f'scrypt${salt.hex()}${digest}'


def verify_password(password, encoded):
    try:
        kind, salt, expected = encoded.split('$')
        if kind != 'scrypt' or len(salt) != 32 or len(expected) != 64:
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32).hex()
        return secrets.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def configured():
    if len(admin_hash().split('$')) != 3:
        raise HTTPException(503, 'Staging administrator is not configured')


def credential_version():
    # Stable across restarts, revoked automatically when credentials change.
    material = secret('STAGING_ADMIN_HASH') or secret('STAGING_ADMIN_PASSWORD')
    return hashlib.sha256((os.getenv('STAGING_ADMIN_USER', 'admin') + ':' + material).encode()).hexdigest()


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_for(token):
    return hmac.new(credential_version().encode(), token.encode(), hashlib.sha256).hexdigest()


def session_guard(request: Request):
    cached = getattr(request.state, 'agn_identity', None)
    if cached is not None:
        return cached
    from .database import SessionLocal
    from .models import AuthSession, StaffAccount
    from .accounts import account_version
    token = request.cookies.get(COOKIE, '')
    if len(token) != 43:
        raise HTTPException(401, 'Sign in required')
    with SessionLocal() as db:
        item = db.get(AuthSession, token_hash(token))
        user = db.get(StaffAccount, item.actor) if item else None
        if not item or not user or not user.active or item.expires_at <= time.time() or not secrets.compare_digest(item.credential_version, account_version(user)):
            raise HTTPException(401, 'Sign in required')
        csrf = csrf_for(token)
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            if not secrets.compare_digest(request.headers.get('x-csrf-token', ''), csrf):
                raise HTTPException(403, 'Invalid CSRF token')
        identity = {'csrf': csrf, 'actor': item.actor, 'role': user.role, 'mfa_enabled':bool(user.mfa_secret)}
        request.state.agn_identity = identity
        return identity


def record_attempt(request, scope='login'):
    """Atomic shared limit survives restarts; forwarding headers are untrusted."""
    from sqlalchemy import case, delete
    from .database import SessionLocal
    from .models import AuthAttempt
    key = token_hash(scope + ':' + (request.client.host if request.client else 'unknown'))
    now = time.time()
    with SessionLocal.begin() as db:
        dialect = db.bind.dialect.name
        if dialect == 'postgresql':
            from sqlalchemy.dialects.postgresql import insert
        else:
            from sqlalchemy.dialects.sqlite import insert
        stmt = insert(AuthAttempt).values(bucket_hash=key, attempts=1, expires_at=now + 300)
        expired = AuthAttempt.expires_at <= now
        stmt = stmt.on_conflict_do_update(index_elements=['bucket_hash'], set_={
            'attempts': case((expired, 1), else_=AuthAttempt.attempts + 1),
            'expires_at': case((expired, now + 300), else_=AuthAttempt.expires_at),
        }).returning(AuthAttempt.attempts)
        count = db.execute(stmt).scalar_one()
        db.execute(delete(AuthAttempt).where(AuthAttempt.expires_at < now))
    if count > 5:
        raise HTTPException(429, 'Too many attempts; retry in five minutes')
    return key


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=100, pattern=r'^[a-zA-Z0-9_.-]+$')
    password: str = Field(max_length=256)
    otp: str = Field(default='', max_length=100)


@router.post('/login')
def login(payload: Login, request: Request, response: Response):
    configured()
    key = record_attempt(request)
    from sqlalchemy import delete, select
    from .database import SessionLocal
    from .models import AuthSession, AuthAttempt, StaffAccount
    from .accounts import ensure_admin, password_valid, use_factor, account_version
    ensure_admin()
    token = secrets.token_urlsafe(32)
    csrf = csrf_for(token)
    with SessionLocal.begin() as db:
        user = db.scalar(select(StaffAccount).where(StaffAccount.username == payload.username).with_for_update())
        valid = password_valid(user, payload.password) if user else verify_password(payload.password, admin_hash()) and False
        if not user or not user.active or not valid:
            raise HTTPException(401, 'Invalid sign-in or verification code')
        if user.username != os.getenv('STAGING_ADMIN_USER', 'admin') and not user.mfa_secret:
            raise HTTPException(401, 'Account activation is incomplete')
        if not use_factor(db, user, payload.otp):
            raise HTTPException(401, 'Invalid sign-in or verification code')
        db.execute(delete(AuthAttempt).where(AuthAttempt.bucket_hash == key))
        db.execute(delete(AuthSession).where(AuthSession.expires_at <= time.time()))
        previous = request.cookies.get(COOKIE, '')
        if previous:
            db.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash(previous)))
        active = db.scalars(select(AuthSession).where(AuthSession.actor==user.username).order_by(AuthSession.expires_at)).all()
        for old in active[:-19] if len(active) >= 20 else []:
            db.delete(old)
        db.add(AuthSession(token_hash=token_hash(token), actor=user.username,
                           credential_version=account_version(user), expires_at=time.time() + TTL))
        role=user.role
        mfa_enabled=bool(user.mfa_secret)
    response.set_cookie(COOKIE, token, max_age=TTL, secure=True, httponly=True, samesite='strict', path='/')
    response.headers['Cache-Control'] = 'no-store'
    return {'csrf_token': csrf, 'role':role, 'mfa_enabled':mfa_enabled}


@router.get('/session')
def session(request: Request, response: Response):
    item = session_guard(request)
    response.headers['Cache-Control'] = 'no-store'
    return {'csrf_token': item['csrf'], 'role':item['role'], 'username':item['actor'], 'mfa_enabled':item['mfa_enabled']}


@router.post('/logout')
def logout(request: Request, response: Response):
    session_guard(request)
    from sqlalchemy import delete
    from .database import SessionLocal
    from .models import AuthSession
    with SessionLocal.begin() as db:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash(request.cookies.get(COOKIE, ''))))
    response.delete_cookie(COOKIE, secure=True, httponly=True, samesite='strict', path='/')
    return {'ok': True}
