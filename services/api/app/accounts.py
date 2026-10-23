"""Staff account lifecycle. Invitations are single-use and never emailed here."""
import json
import secrets
import time
from typing import Literal
from cryptography.fernet import Fernet, InvalidToken
import pyotp
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from . import database
from .models import StaffAccount, AuthSession, AuthAttempt
from .auth import secret, token_hash, credential_version, session_guard, verify_password, admin_hash, record_attempt

router = APIRouter(prefix='/auth')


def cipher():
    try:
        return Fernet(secret('AUTH_ENCRYPTION_KEY').encode())
    except (ValueError, TypeError):
        raise HTTPException(503, 'Account security setup is not configured') from None


def ensure_admin():
    import os
    name = os.getenv('STAGING_ADMIN_USER', 'admin')
    with database.SessionLocal.begin() as db:
        if db.get(StaffAccount, name) is None:
            db.add(StaffAccount(username=name, role='admin', active=True,
                                version=secrets.token_hex(32), recovery_hashes='[]', mfa_counter=-1))


def account_version(user):
    return token_hash(credential_version() + ':' + user.version)


def password_valid(user, password):
    import os
    encoded = admin_hash() if user.username == os.getenv('STAGING_ADMIN_USER', 'admin') else user.password_hash
    return verify_password(password, encoded or '')


def hash_password(password):
    import hashlib
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32).hex()
    return f'scrypt${salt.hex()}${digest}'


def verified_counter(encrypted, code, previous=-1):
    try:
        totp = pyotp.TOTP(cipher().decrypt(encrypted.encode()).decode())
    except InvalidToken:
        raise HTTPException(503, 'Account security key requires administrator recovery') from None
    current = int(time.time()) // 30
    for counter in (current, current - 1, current + 1):
        if counter > previous and secrets.compare_digest(totp.at(counter * 30), code):
            return counter
    return None


def use_factor(db, user, code):
    if not user.mfa_secret:
        return True
    counter = verified_counter(user.mfa_secret, code, user.mfa_counter)
    if counter is not None:
        # Atomic compare-and-set rejects simultaneous replay of the same OTP.
        result = db.execute(update(StaffAccount).where(StaffAccount.username == user.username,
            StaffAccount.mfa_counter < counter).values(mfa_counter=counter))
        return result.rowcount == 1
    hashes = json.loads(user.recovery_hashes)
    value = token_hash(code)
    if value not in hashes:
        return False
    remaining = json.dumps([h for h in hashes if h != value])
    result = db.execute(update(StaffAccount).where(StaffAccount.username == user.username,
        StaffAccount.recovery_hashes == user.recovery_hashes).values(recovery_hashes=remaining))
    return result.rowcount == 1


def require_roles(request, *roles):
    item = session_guard(request)
    if item['role'] not in roles:
        raise HTTPException(403, 'Your role does not allow this action')
    return item


class Credentials(BaseModel):
    password: str = Field(max_length=256)
    otp: str = Field(default='', max_length=100)


def step_up(request, credentials, roles=None):
    identity = require_roles(request, *(roles or ('admin','editor','reviewer','viewer')))
    if roles == ('admin',) and not identity['mfa_enabled']:
        raise HTTPException(409, 'Enable owner MFA in Account security before managing staff')
    key = record_attempt(request, scope='security')
    with database.SessionLocal.begin() as db:
        user = db.get(StaffAccount, identity['actor'])
        if not password_valid(user, credentials.password) or not use_factor(db, user, credentials.otp):
            raise HTTPException(401, 'Password or verification code is incorrect')
        db.execute(delete(AuthAttempt).where(AuthAttempt.bucket_hash == key))
    return identity


class Invitation(Credentials):
    username: str = Field(min_length=3, max_length=100, pattern=r'^[a-zA-Z0-9_.-]+$')
    role: Literal['editor','reviewer','viewer'] = 'editor'


@router.get('/accounts')
def list_accounts(request: Request):
    require_roles(request, 'admin')
    with database.SessionLocal() as db:
        return [{'username':u.username,'role':u.role,'active':u.active,'mfa_enabled':bool(u.mfa_secret),
                 'invitation_pending':bool(u.invite_hash)} for u in db.scalars(select(StaffAccount).order_by(StaffAccount.username))]


@router.post('/accounts/invite', status_code=201)
def invite(payload: Invitation, request: Request):
    step_up(request, payload, roles=('admin',))
    cipher()  # Refuse to invite staff until encrypted MFA enrollment is available.
    token = secrets.token_urlsafe(32)
    with database.SessionLocal.begin() as db:
        if db.get(StaffAccount, payload.username):
            raise HTTPException(409, 'Username already exists')
        db.add(StaffAccount(username=payload.username, role=payload.role, active=False,
            version=secrets.token_hex(32), invite_hash=token_hash(token), invite_expires=time.time()+86400,
            recovery_hashes='[]', mfa_counter=-1))
    return {'username':payload.username,'activation_token':token,'expires_in_seconds':86400}


class AccountStatus(Credentials):
    active: bool


@router.post('/accounts/{username}/status')
def account_status(username: str, payload: AccountStatus, request: Request):
    import os
    step_up(request, payload, roles=('admin',))
    if username == os.getenv('STAGING_ADMIN_USER','admin'):
        raise HTTPException(409, 'The owner account cannot be disabled here')
    with database.SessionLocal.begin() as db:
        user = db.get(StaffAccount, username)
        if not user:
            raise HTTPException(404, 'Account not found')
        if payload.active and (not user.password_hash or not user.mfa_secret):
            raise HTTPException(409, 'Staff must complete activation and MFA first')
        user.active=payload.active
        user.version=secrets.token_hex(32)
        db.execute(delete(AuthSession).where(AuthSession.actor==username))
    return {'ok':True}


class Activation(BaseModel):
    token: str = Field(min_length=43, max_length=43)
    password: str = Field(min_length=16, max_length=256)
    otp: str = Field(default='', max_length=6)


@router.post('/activate/start')
def activate_start(payload: Activation, request: Request):
    record_attempt(request, scope='activation')
    totp_secret=pyotp.random_base32()
    with database.SessionLocal.begin() as db:
        user=db.scalar(select(StaffAccount).where(StaffAccount.invite_hash==token_hash(payload.token)).with_for_update())
        if not user or not user.invite_expires or user.invite_expires <= time.time() or user.active:
            raise HTTPException(400,'Activation link is invalid or expired')
        user.password_hash=hash_password(payload.password)
        user.mfa_pending=cipher().encrypt(totp_secret.encode()).decode()
        user.mfa_pending_expires=time.time()+600
        name=user.username
    return {'secret':totp_secret,'username':name,'issuer':'AGN Studio'}


def recovery_codes(user):
    codes=[secrets.token_hex(8) for _ in range(10)]
    user.recovery_hashes=json.dumps([token_hash(c) for c in codes])
    return codes


@router.post('/activate/confirm')
def activate_confirm(payload: Activation, request: Request):
    record_attempt(request, scope='activation-confirm')
    with database.SessionLocal.begin() as db:
        user=db.scalar(select(StaffAccount).where(StaffAccount.invite_hash==token_hash(payload.token)).with_for_update())
        if not user or not user.invite_expires or user.invite_expires<=time.time() or user.active or not user.mfa_pending or not user.mfa_pending_expires or user.mfa_pending_expires<=time.time():
            raise HTTPException(400,'Activation session is invalid or expired')
        if not verify_password(payload.password,user.password_hash):
            raise HTTPException(401,'Password or verification code is incorrect')
        counter=verified_counter(user.mfa_pending,payload.otp)
        if counter is None:
            raise HTTPException(401,'Password or verification code is incorrect')
        user.mfa_secret=user.mfa_pending;user.mfa_pending=None;user.mfa_pending_expires=None
        user.mfa_counter=counter;user.active=True;user.invite_hash=None;user.invite_expires=None
        codes=recovery_codes(user)
    return {'ok':True,'recovery_codes':codes}


@router.post('/mfa/start')
def mfa_start(payload: Credentials, request: Request):
    identity=step_up(request,payload)
    value=pyotp.random_base32()
    with database.SessionLocal.begin() as db:
        user=db.get(StaffAccount,identity['actor'])
        if user.mfa_secret:
            raise HTTPException(409,'MFA is already enabled')
        user.mfa_pending=cipher().encrypt(value.encode()).decode()
        user.mfa_pending_expires=time.time()+600
    return {'secret':value,'issuer':'AGN Studio','username':identity['actor']}


@router.post('/mfa/confirm')
def mfa_confirm(payload: Credentials, request: Request):
    identity=step_up(request,payload)
    record_attempt(request, scope='mfa-confirm')
    with database.SessionLocal.begin() as db:
        user=db.get(StaffAccount,identity['actor'])
        if user.mfa_secret or not user.mfa_pending or not user.mfa_pending_expires or user.mfa_pending_expires<=time.time():
            raise HTTPException(409,'Start MFA setup again')
        counter=verified_counter(user.mfa_pending,payload.otp)
        if counter is None:
            raise HTTPException(401,'Verification code is incorrect')
        user.mfa_secret=user.mfa_pending;user.mfa_pending=None;user.mfa_pending_expires=None
        user.mfa_counter=counter;user.version=secrets.token_hex(32)
        db.execute(delete(AuthSession).where(AuthSession.actor==user.username))
        codes=recovery_codes(user)
    return {'ok':True,'recovery_codes':codes,'sign_in_again':True}

@router.post('/accounts/{username}/reset')
def reset_account(username: str, payload: Credentials, request: Request):
    import os
    step_up(request,payload,roles=('admin',))
    cipher()
    if username == os.getenv('STAGING_ADMIN_USER','admin'):
        raise HTTPException(409,'Owner recovery uses the saved recovery codes and security key')
    token=secrets.token_urlsafe(32)
    with database.SessionLocal.begin() as db:
        user=db.get(StaffAccount,username)
        if not user:
            raise HTTPException(404,'Account not found')
        user.active=False;user.password_hash=None;user.version=secrets.token_hex(32)
        user.mfa_secret=None;user.mfa_pending=None;user.mfa_pending_expires=None
        user.mfa_counter=-1;user.recovery_hashes='[]'
        user.invite_hash=token_hash(token);user.invite_expires=time.time()+86400
        db.execute(delete(AuthSession).where(AuthSession.actor==username))
    return {'activation_token':token,'expires_in_seconds':86400}
