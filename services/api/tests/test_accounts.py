"""Full staged app account/MFA checks use disposable secrets and an isolated DB."""
import subprocess
import sys


def test_staff_activation_roles_mfa_and_revocation():
    program = r'''
import os, json, time
from pathlib import Path
native=os.getenv('AGN_NATIVE_ACCOUNT_CHECK')=='1'
native_url=Path(os.environ['DATABASE_URL_FILE']).read_text().strip() if native else 'postgresql://unused:unused@localhost/unused'
os.environ.pop('DATABASE_URL_FILE',None)
from cryptography.fernet import Fernet
os.environ.update(APP_ENV='staging',RENDER='true',STAGING_PRIVATE_ACCESS='required',STAGING_ADMIN_PASSWORD='dummy-test-only-generated-secret-1234567890',DATABASE_URL=native_url,AUTH_ENCRYPTION_KEY=Fernet.generate_key().decode())
os.environ.pop('STAGING_ADMIN_HASH',None)
os.environ.pop('STAGING_ADMIN_HASH_FILE',None)
import pyotp
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app import main
from app.models import StaffAccount
if not native:
    main.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    main.SessionLocal.configure(bind=main.engine)
password=os.environ['STAGING_ADMIN_PASSWORD']
with TestClient(main.app,base_url='https://localhost') as admin:
    login=admin.post('/auth/login',json={'username':'admin','password':password})
    h={'X-CSRF-Token':login.json()['csrf_token']}
    assert admin.get('/auth/accounts').status_code==200
    assert admin.post('/auth/accounts/invite',headers=h,json={'username':'blocked','role':'editor','password':password}).status_code==409
    owner=admin.post('/auth/mfa/start',headers=h,json={'password':password})
    assert owner.status_code==200,owner.text
    seed=owner.json()['secret']
    enabled=admin.post('/auth/mfa/confirm',headers=h,json={'password':password,'otp':pyotp.TOTP(seed).now()})
    assert enabled.status_code==200,enabled.text
    assert admin.get('/auth/session').status_code==401
    owner_codes=enabled.json()['recovery_codes']
    again=admin.post('/auth/login',json={'username':'admin','password':password,'otp':owner_codes.pop()})
    assert again.status_code==200
    h={'X-CSRF-Token':again.json()['csrf_token']}
    def owner_credentials():return {'password':password,'otp':owner_codes.pop()}
    assert admin.post('/auth/accounts/invite',headers=h,json={'username':'bad','role':'admin','password':password}).status_code==422
    invalid=admin.post('/auth/accounts/invite',headers=h,json={'username':'staff','role':'editor','password':'wrong'})
    assert invalid.status_code==401
    invite=admin.post('/auth/accounts/invite',headers=h,json={'username':'staff','role':'editor',**owner_credentials()})
    assert invite.status_code==201,invite.text
    token=invite.json()['activation_token']
    staff_password='a-separate-staff-test-password'
    with TestClient(main.app,base_url='https://localhost') as staff:
        assert staff.get('/auth/accounts').status_code==401
        start=staff.post('/auth/activate/start',json={'token':token,'password':staff_password})
        assert start.status_code==200,start.text
        value=start.json()['secret']
        with main.SessionLocal() as db:
            row=db.get(StaffAccount,'staff')
            assert row.invite_hash != token
            assert row.mfa_pending != value and value not in row.mfa_pending
            assert not row.active
        assert staff.post('/auth/login',json={'username':'staff','password':staff_password}).status_code==401
        code=pyotp.TOTP(value).now()
        confirmed=staff.post('/auth/activate/confirm',json={'token':token,'password':staff_password,'otp':code})
        assert confirmed.status_code==200,confirmed.text
        codes=confirmed.json()['recovery_codes']
        assert len(codes)==10
        assert staff.post('/auth/activate/confirm',json={'token':token,'password':staff_password,'otp':code}).status_code==400
        assert staff.post('/auth/login',json={'username':'staff','password':staff_password,'otp':code}).status_code==401
        logged=staff.post('/auth/login',json={'username':'staff','password':staff_password,'otp':codes[0]})
        assert logged.status_code==200,logged.text
        sh={'X-CSRF-Token':logged.json()['csrf_token']}
        assert staff.get('/auth/session').json()['role']=='editor'
        assert staff.get('/auth/accounts').status_code==403
        assert staff.post('/auth/accounts/invite',headers=sh,json={'username':'intruder','role':'editor','password':staff_password}).status_code==403
        draft={'locale':'en','category':'Test','slug':'staff-role-test','headline':'Isolated staff role test','body':'Fictional acceptance test for named accounts and permissions.','source_url':'https://example.com/','source_publisher':'Test fixture'}
        created=staff.post('/v1/editor/drafts',headers=sh,json=draft)
        assert created.status_code==201,created.text
        eid=created.json()['edition_id']
        approval={'accuracy_reviewed':True,'rights_verified':True,'provenance_reviewed':True,'actor':'spoofed'}
        assert staff.post(f'/v1/editor/editions/{eid}/publish',headers=sh,json=approval).status_code==403
        with main.SessionLocal() as db:
            row=db.get(StaffAccount,'staff')
            assert codes[0] not in row.recovery_hashes and len(json.loads(row.recovery_hashes))==9
        assert staff.post('/auth/logout',headers=sh).status_code==200
        assert staff.post('/auth/login',json={'username':'staff','password':staff_password,'otp':codes[0]}).status_code==401
        assert staff.post('/auth/login',json={'username':'staff','password':staff_password,'otp':codes[1]}).status_code==200
        disabled=admin.post('/auth/accounts/staff/status',headers=h,json={**owner_credentials(),'active':False})
        assert disabled.status_code==200,disabled.text
        assert staff.get('/auth/session').status_code==401
    assert admin.post('/auth/accounts/admin/status',headers=h,json={**owner_credentials(),'active':False}).status_code==409
    for role in ['reviewer','viewer']:
        invitation=admin.post('/auth/accounts/invite',headers=h,json={'username':role,'role':role,**owner_credentials()})
        assert invitation.status_code==201,invitation.text
        token2=invitation.json()['activation_token']
        with TestClient(main.app,base_url='https://localhost') as other:
            start2=other.post('/auth/activate/start',json={'token':token2,'password':staff_password})
            assert start2.status_code==200,start2.text
            confirm2=other.post('/auth/activate/confirm',json={'token':token2,'password':staff_password,'otp':pyotp.TOTP(start2.json()['secret']).now()})
            assert confirm2.status_code==200,confirm2.text
            login2=other.post('/auth/login',json={'username':role,'password':staff_password,'otp':confirm2.json()['recovery_codes'][0]})
            assert login2.status_code==200,login2.text
            rh={'X-CSRF-Token':login2.json()['csrf_token']}
            assert other.post('/v1/editor/drafts',headers=rh,json=draft).status_code==403
            assert other.get('/v1/editor/editions').status_code==200
            if role=='reviewer':
                assert other.post(f'/v1/editor/editions/{eid}/publish',headers=rh,json=approval).status_code==200
                assert other.post(f'/v1/editor/editions/{eid}/retract',headers=rh).status_code==200
            else:
                assert other.post(f'/v1/editor/editions/{eid}/publish',headers=rh,json=approval).status_code==403
    reset=admin.post('/auth/accounts/staff/reset',headers=h,json=owner_credentials())
    assert reset.status_code==200,reset.text
    assert admin.post('/auth/mfa/start',headers=h,json=owner_credentials()).status_code==409
'''
    subprocess.run([sys.executable, '-c', program], check=True)
