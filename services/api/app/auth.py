"""Single-admin staging sessions; in-memory state requires one API worker."""
import hashlib
import os
import secrets
import threading
import time
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

router = APIRouter(prefix='/auth')
_sessions = {}
_attempts = {}
_lock = threading.Lock()
COOKIE = 'agn_session'
TTL = 3600


def secret(name):
    filename = os.getenv(name + '_FILE')
    return Path(filename).read_text().strip() if filename else os.getenv(name, '')


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
    if len(secret('STAGING_ADMIN_HASH').split('$')) != 3:
        raise HTTPException(503, 'Staging administrator is not configured')


def session_guard(request: Request):
    now = time.monotonic()
    with _lock:
        item = _sessions.get(request.cookies.get(COOKIE, ''))
        if not item or item['expires'] <= now:
            raise HTTPException(401, 'Sign in required')
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            if not secrets.compare_digest(request.headers.get('x-csrf-token', ''), item['csrf']):
                raise HTTPException(403, 'Invalid CSRF token')
        return item


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=100, pattern=r'^[a-zA-Z0-9_.-]+$')
    password: str = Field(max_length=256)


@router.post('/login')
def login(payload: Login, request: Request, response: Response):
    configured()
    # Do not trust caller-supplied forwarding headers. The staging proxy is the
    # single rate-limit bucket; five failed attempts block all login attempts.
    key = request.client.host if request.client else 'unknown'
    now = time.monotonic()
    with _lock:
        for old in [k for k, v in _sessions.items() if v['expires'] <= now]:
            del _sessions[old]
        for old in [k for k, v in _attempts.items() if v[1] <= now]:
            del _attempts[old]
        count, until = _attempts.get(key, (0, now + 300))
        if count >= 5:
            raise HTTPException(429, 'Too many attempts; retry in five minutes')
        _attempts[key] = (count + 1, until)
    valid_password = verify_password(payload.password, secret('STAGING_ADMIN_HASH'))
    if not (secrets.compare_digest(payload.username, os.getenv('STAGING_ADMIN_USER', 'admin')) and valid_password):
        raise HTTPException(401, 'Invalid sign-in')
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with _lock:
        _attempts.pop(key, None)
        if len(_sessions) >= 20:
            _sessions.pop(next(iter(_sessions)))
        _sessions[token] = {'csrf': csrf, 'expires': now + TTL, 'actor': payload.username}
    response.set_cookie(COOKIE, token, max_age=TTL, secure=True, httponly=True, samesite='strict', path='/')
    response.headers['Cache-Control'] = 'no-store'
    return {'csrf_token': csrf}


@router.get('/session')
def session(request: Request, response: Response):
    item = session_guard(request)
    response.headers['Cache-Control'] = 'no-store'
    return {'csrf_token': item['csrf']}


@router.post('/logout')
def logout(request: Request, response: Response):
    session_guard(request)
    with _lock:
        _sessions.pop(request.cookies.get(COOKIE, ''), None)
    response.delete_cookie(COOKIE, secure=True, httponly=True, samesite='strict', path='/')
    return {'ok': True}
