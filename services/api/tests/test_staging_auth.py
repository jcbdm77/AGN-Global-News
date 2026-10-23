import hashlib
import os
import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from app.auth import router, session_guard

@pytest.fixture
def client(monkeypatch):
    salt = b'a' * 16
    password = 'a-long-staging-test-password'
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32).hex()
    monkeypatch.setenv('STAGING_ADMIN_HASH', f'scrypt${salt.hex()}${digest}')
    monkeypatch.setenv('STAGING_ADMIN_USER', 'admin')
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app import database
    from app.migrate import migrate
    engine = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
    migrate(engine)
    monkeypatch.setattr(database, 'SessionLocal', sessionmaker(bind=engine, expire_on_commit=False))
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
    from app.database import SessionLocal
    from app.models import AuthSession
    from sqlalchemy import update
    with SessionLocal.begin() as db:
        db.execute(update(AuthSession).values(expires_at=0))
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

def test_render_generated_password_and_whole_site_gate():
    import subprocess, sys
    program = '''
import os
os.environ.update(APP_ENV='staging',RENDER='true',STAGING_PRIVATE_ACCESS='required',STAGING_ADMIN_PASSWORD='dummy-test-only-generated-secret-1234567890',DATABASE_URL='postgresql://unused:unused@localhost/unused')
os.environ.pop('STAGING_ADMIN_HASH',None)
os.environ.pop('STAGING_ADMIN_HASH_FILE',None)
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app import main
assert main.engine.dialect.driver == 'psycopg'
main.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
main.SessionLocal.configure(bind=main.engine)
with TestClient(main.app,base_url='https://localhost') as c:
    assert c.get('/ready').status_code==200
    for path in ['/en','/v1/articles','/sitemap.xml','/assets/article.html']:
        assert c.get(path).status_code==401,path
    assert c.get('/en',headers={'Accept':'text/html'},follow_redirects=False).status_code==303
    assert c.get('/studio').status_code==200
    assert c.get('/assets/site.css').status_code==200
    r=c.post('/auth/login',json={'username':'admin','password':os.environ['STAGING_ADMIN_PASSWORD']})
    assert r.status_code==200,r.text
    assert c.get('/en').status_code==200
    assert c.get('/v1/articles').status_code==200
    h={'X-CSRF-Token':r.json()['csrf_token']}
    payload={'locale':'te','category':'Technology','slug':'staging-workflow-test','headline':'Staging workflow test','body':'Fictional test content for isolated workflow verification only.','source_url':'https://example.com/','source_publisher':'Test fixture'}
    bad=dict(payload,slug='invalid slug')
    invalid=c.post('/v1/editor/drafts',json=bad,headers=h)
    assert invalid.status_code==422
    assert all('input' not in e and 'ctx' not in e for e in invalid.json()['detail'])
    created=c.post('/v1/editor/drafts',json=payload,headers=h)
    assert created.status_code==201,created.text
    eid=created.json()['edition_id']
    assert c.get('/v1/articles?locale=te').json()==[]
    payload['headline']='Updated staging workflow test'
    assert c.put(f'/v1/editor/editions/{eid}',json=payload,headers=h).status_code==200
    approval={'accuracy_reviewed':False,'rights_verified':True,'provenance_reviewed':True,'actor':'spoofed actor'}
    assert c.post(f'/v1/editor/editions/{eid}/publish',json=approval,headers=h).status_code==409
    approval['accuracy_reviewed']=True
    assert c.post(f'/v1/editor/editions/{eid}/publish',json=approval).status_code==403
    assert c.post(f'/v1/editor/editions/{eid}/publish',json=approval,headers=h).status_code==200
    assert len(c.get('/v1/articles?locale=te').json())==1
    events=c.get('/v1/editor/audit').json()
    assert any(e['edition_id']==eid and e['action']=='published' and e['actor']=='admin' for e in events)
    assert c.post(f'/v1/editor/editions/{eid}/retract',headers=h).status_code==200
    assert c.get('/v1/articles?locale=te').json()==[]
    assert all(e['actor']=='admin' for e in c.get('/v1/editor/audit').json() if e['edition_id']==eid)
    assert c.post('/auth/logout',headers={'X-CSRF-Token':r.json()['csrf_token']}).status_code==200
    assert c.get('/en').status_code==401
'''
    subprocess.run([sys.executable,'-c',program],check=True)

def test_session_storage_hashes_and_credential_rotation(client, monkeypatch):
    from app.database import SessionLocal
    from app.models import AuthSession
    from app.auth import COOKIE, token_hash
    from sqlalchemy import select
    r=client.post('/auth/login',json={'username':'admin','password':'a-long-staging-test-password'})
    assert r.status_code==200
    token=client.cookies.get(COOKIE)
    with SessionLocal() as db:
        row=db.scalar(select(AuthSession))
        assert row.token_hash==token_hash(token)
        assert row.token_hash != token
    monkeypatch.setenv('STAGING_ADMIN_HASH','scrypt$'+'b'*32+'$'+'c'*64)
    assert client.get('/auth/session').status_code==401


def test_sessions_survive_new_database_session_factory(client, monkeypatch):
    from app import database
    from sqlalchemy.orm import sessionmaker
    r=client.post('/auth/login',json={'username':'admin','password':'a-long-staging-test-password'})
    engine=database.SessionLocal.kw['bind']
    monkeypatch.setattr(database,'SessionLocal',sessionmaker(bind=engine,expire_on_commit=False))
    assert client.get('/auth/session').json()['csrf_token']==r.json()['csrf_token']


def test_expired_throttle_resets(client):
    from app.database import SessionLocal
    from app.models import AuthAttempt
    from sqlalchemy import update
    for _ in range(5):
        client.post('/auth/login',json={'username':'admin','password':'wrong'})
    with SessionLocal.begin() as db:
        db.execute(update(AuthAttempt).values(expires_at=0))
    assert client.post('/auth/login',json={'username':'admin','password':'a-long-staging-test-password'}).status_code==200
