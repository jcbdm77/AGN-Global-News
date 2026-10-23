"""Production launch boundaries with disposable local fixtures only."""
import os
import subprocess
import sys
import pytest

@pytest.mark.parametrize('public', ['false', 'true'])
def test_production_reader_and_newsroom_boundaries(public):
    program = r'''
import os
from cryptography.fernet import Fernet
from pathlib import Path
native=os.getenv('AGN_NATIVE_PRODUCTION_CHECK')=='1'
if native:
    assert not os.getenv('RENDER_SERVICE_ID'), 'Never run disposable checks on Render'
    from sqlalchemy.engine import make_url
    base=make_url(Path(os.environ['DATABASE_URL_FILE']).read_text().strip())
    assert base.host=='postgres' and base.database=='agn', 'Disposable CI database required'
    target='agn_production_public' if os.environ['PUBLIC_READER_ENABLED']=='true' else 'agn_production_private'
    database_url=base.set(database=target).render_as_string(hide_password=False)
else:
    database_url='postgresql://unused:unused@localhost/unused'
os.environ.pop('DATABASE_URL_FILE',None)
os.environ.update(APP_ENV='production',RENDER='true',DATABASE_URL=database_url,STAGING_ADMIN_PASSWORD='disposable-production-check-password-123456789',AUTH_ENCRYPTION_KEY=Fernet.generate_key().decode(),PUBLIC_BASE_URL='https://news.example.com',PUBLIC_LAUNCH_APPROVAL='approved')
os.environ.pop('STAGING_ADMIN_HASH',None)
os.environ.pop('STAGING_ADMIN_HASH_FILE',None)
from sqlalchemy import create_engine,select,func
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app import main
from app.models import Story,Edition,AuditEvent
if not native:
    main.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    main.SessionLocal.configure(bind=main.engine)
public=os.environ['PUBLIC_READER_ENABLED']=='true'
with TestClient(main.app,base_url='https://news.example.com') as client:
    with main.SessionLocal.begin() as db:
        assert db.scalar(select(func.count()).select_from(Edition))==0
        for slug,state,risk in [('fixture-public','published','unassessed'),('fixture-draft','draft','unassessed'),('fixture-demo','published','demo')]:
            story=Story(category='Fixture',risk=risk);db.add(story);db.flush()
            db.add(Edition(story_id=story.id,locale='en',slug=slug,headline='Disposable test article',body='Disposable local fixture only.',state=state))
        for locale,label in main.LOCALES.items():
            if locale=='en':continue
            story=Story(category='Fixture',risk='unassessed');db.add(story);db.flush()
            db.add(Edition(story_id=story.id,locale=locale,slug='fixture-'+locale,headline='Test '+label,body='Disposable fixture '+label,state='published'))
    for path in ['/','/en','/v1/articles','/robots.txt','/sitemap.xml']:
        assert client.get(path).status_code==(200 if public else 401),path
    if public:
        for locale in main.LOCALES:
            page=client.get('/'+locale)
            assert page.status_code==200
            direction='rtl' if locale=='ur' else 'ltr'
            assert f'<html lang="{locale}" dir="{direction}">' in page.text
            assert client.get('/v1/articles?locale='+locale).status_code==200
            stories=client.get('/v1/articles?locale='+locale).json()
            assert len(stories)==1
            expected='fixture-public' if locale=='en' else 'fixture-'+locale
            assert stories[0]['slug']==expected
            detail=client.get('/'+locale+'/news/'+expected)
            assert detail.status_code==200
            assert f'<html lang="{locale}" dir="{direction}">' in detail.text
            if locale!='en':assert main.LOCALES[locale] in detail.text
        assert client.get('/v1/articles?locale=invalid').status_code==400
        assert client.get('/v1/articles?q=never-present').json()==[]
        assert client.get('/v1/articles?category=never-present').json()==[]
        assert [e['slug'] for e in client.get('/v1/articles').json()]==['fixture-public']
        for path in ['/v1/articles/en/fixture-demo','/en/news/fixture-draft','/en/news/fixture-demo']:
            assert client.get(path).status_code==404,path
        assert 'fixture-demo' not in client.get('/sitemap.xml').text
        assert 'X-Robots-Tag' not in client.get('/en').headers
    for path in ['/v1/editor/editions','/v1/editor/audit','/auth/accounts','/docs','/openapi.json','/assets/news.html']:
        assert client.get(path).status_code==401,path
    assert client.post('/v1/articles',json={}).status_code==401
    assert client.get('/studio').headers['X-Robots-Tag']=='noindex, nofollow'
    password=os.environ['STAGING_ADMIN_PASSWORD']
    login=client.post('/auth/login',json={'username':'admin','password':password})
    assert login.status_code==200
    headers={'X-CSRF-Token':login.json()['csrf_token']}
    assert client.get('/v1/editor/editions').status_code==403
    import pyotp
    enrolled=client.post('/auth/mfa/start',headers=headers,json={'password':password})
    assert enrolled.status_code==200
    confirmed=client.post('/auth/mfa/confirm',headers=headers,json={'password':password,'otp':pyotp.TOTP(enrolled.json()['secret']).now()})
    assert confirmed.status_code==200
    logged=client.post('/auth/login',json={'username':'admin','password':password,'otp':confirmed.json()['recovery_codes'][0]})
    assert logged.status_code==200
    assert client.get('/v1/editor/editions').status_code==200
    draft={'locale':'en','category':'Fixture','slug':'production-check','headline':'Disposable test draft','body':'Disposable local acceptance test; not real reporting.','source_url':'https://example.com/','source_publisher':'Fixture'}
    created=client.post('/v1/editor/drafts',headers={'X-CSRF-Token':logged.json()['csrf_token']},json=draft)
    assert created.status_code==201
    with main.SessionLocal() as db:
        assert db.scalar(select(AuditEvent).where(AuditEvent.edition_id==created.json()['edition_id'])).actor=='admin'
'''
    subprocess.run([sys.executable,'-c',program],env={**os.environ,'PUBLIC_READER_ENABLED':public},check=True)

@pytest.mark.parametrize('approval,url', [('', 'https://news.example.com'),('approved','http://news.example.com'),('approved','https://user:pass@news.example.com'),('approved','https://news.example.com/?token=secret')])
def test_public_launch_rejects_unsafe_configuration(approval,url):
    env={**os.environ,'APP_ENV':'production','RENDER':'true','DATABASE_URL':'postgresql://unused:unused@localhost/unused','PUBLIC_READER_ENABLED':'true','PUBLIC_LAUNCH_APPROVAL':approval,'PUBLIC_BASE_URL':url}
    result=subprocess.run([sys.executable,'-c','from app import main'],env=env,capture_output=True,text=True)
    assert result.returncode!=0
    assert 'explicit launch approval' in result.stderr
