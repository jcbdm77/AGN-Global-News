import os, tempfile
f=tempfile.NamedTemporaryFile(suffix='.db',delete=False); f.close()
os.environ['DATABASE_URL']='sqlite:///'+f.name
os.environ['ADMIN_TOKEN']='test-editor-token'
from fastapi.testclient import TestClient
from app.main import app

def test_full_newsroom_flow():
    with TestClient(app) as c:
        assert c.get('/health').json()['ok']
        assert c.get('/en').status_code==200
        assert c.get('/studio').status_code==200
        assert c.get('/v1/editor/editions').status_code==401
        h={'Authorization':'Bearer test-editor-token'}
        demo=c.get('/v1/articles?locale=en').json()
        assert len(demo)>=1 and demo[0]['is_demo']
        payload={'locale':'te','category':'Technology','slug':'agn-local-test','headline':'AGN తెలుగు పరీక్ష వార్త','body':'This is a developer-generated test article for testing the editorial flow, not a real current news story.','source_url':'https://example.com/','source_publisher':'AGN Test'}
        r=c.post('/v1/editor/drafts',json=payload,headers=h)
        assert r.status_code==201,r.text
        eid=r.json()['edition_id']
        assert c.get('/v1/articles?locale=te').json()==[]
        payload['headline']='AGN సవరించిన పరీక్ష వార్త'
        assert c.put('/v1/editor/editions/'+str(eid),json=payload,headers=h).status_code==200
        approval={'provenance_reviewed':True,'rights_verified':True,'accuracy_reviewed':False,'actor':'Local QA'}
        assert c.post(f'/v1/editor/editions/{eid}/publish',json=approval,headers=h).status_code==409
        approval['accuracy_reviewed']=True
        assert c.post(f'/v1/editor/editions/{eid}/publish',json=approval,headers=h).status_code==200
        assert len(c.get('/v1/articles?locale=te').json())==1
        assert c.get('/te/news/agn-local-test').status_code==200
        assert 'NewsArticle' in c.get('/te/news/agn-local-test').text
        assert 'agn-local-test' in c.get('/sitemap.xml').text
        assert c.post(f'/v1/editor/editions/{eid}/retract',headers=h).status_code==200
        assert c.get('/v1/articles?locale=te').json()==[]
        assert c.get('/te/news/agn-local-test').status_code==404
        assert c.get('/v1/editor/audit',headers=h).status_code==200
