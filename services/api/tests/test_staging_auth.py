import hashlib
import os
import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from app.auth import router, session_guard, _sessions, _attempts

@pytest.fixture
def client(monkeypatch):
    salt = b'a' * 16
    password = 'a-long-staging-test-password'
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32).hex()
    monkeypatch.setenv('STAGING_ADMIN_HASH', f'scrypt${salt.hex()}${digest}')
    monkeypatch.setenv('STAGING_ADMIN_USER', 'admin')
    _sessions.clear(); _attempts.clear()
    app = FastAPI(); app.include_router(router)
    @app.post('/protected', dependencies=[Depends(session_guard)])
    def protected(): return {'ok':True}
    with TestClient(app, base_url='https://localhost') as c: yield c

def test_session_csrf_logout(client):
    assert client.post('/protected').status_code == 401
    r = client.post('/auth/login', json={'username':'admin','password':'a-long-staging-test-password'})
    assert r.status_code == 200
    cookie = r.headers['set-cookie'].lower()
    assert all(s in cookie for s in ['httponly','secure','samesite=strict'])
    token = r.json()['csrf_token']
    assert client.get('/auth/session').json()['csrf_token'] == token
    assert client.post('/protected').status_code == 403
    h = {'X-CSRF-Token':token}
    assert client.post('/protected', headers=h).status_code == 200
    assert client.post('/auth/logout', headers=h).status_code == 200
    assert client.post('/protected', headers=h).status_code == 401

def test_failed_login_throttled(client):
    for _ in range(5):
        assert client.post('/auth/login',json={'username':'admin','password':'wrong'}).status_code == 401
    assert client.post('/auth/login',json={'username':'admin','password':'wrong'}).status_code == 429

def test_expired_session(client):
    client.post('/auth/login',json={'username':'admin','password':'a-long-staging-test-password'})
    for entry in _sessions.values(): entry['expires'] = 0
    assert client.get('/auth/session').status_code == 401

def test_staging_app_disables_development_token(tmp_path):
    # Fresh interpreter avoids import-time configuration leaking from local tests.
    import subprocess, sys
    program = '''
import hashlib, os
os.environ['APP_ENV']='staging'
os.environ['DATABASE_URL']='postgresql+psycopg://unused:unused@localhost/unused'
os.environ['ADMIN_TOKEN']='development-token-must-not-work'
salt=b'a'*16
os.environ['STAGING_ADMIN_HASH']='scrypt$'+salt.hex()+'$'+hashlib.scrypt(b'a-long-staging-test-password',salt=salt,n=16384,r=8,p=1,dklen=32).hex()
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app import main
main.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
main.SessionLocal.configure(bind=main.engine)
with TestClient(main.app,base_url='https://localhost') as c:
    assert c.get('/docs').status_code==404
    assert c.get('/ready').status_code==200
    assert c.get('/v1/editor/stats',headers={'Authorization':'Bearer development-token-must-not-work'}).status_code==401
    r=c.post('/auth/login',json={'username':'admin','password':'a-long-staging-test-password'})
    assert r.status_code==200,r.text
    assert c.get('/v1/editor/stats').status_code==200
    assert c.post('/v1/editor/drafts',json={}).status_code==403
    assert c.get('/en').headers['x-robots-tag']=='noindex, nofollow'
'''
    subprocess.run([sys.executable, '-c', program], check=True)
