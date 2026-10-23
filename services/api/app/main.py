from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from html import escape
import os, re, secrets
from fastapi import FastAPI, Depends, HTTPException, Header, Response, Query, Request
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload
from .database import Base, engine, SessionLocal
from .models import Story, Edition, Source, AuditEvent

LOCALES={'en':'English','te':'తెలుగు','hi':'हिन्दी','ta':'தமிழ்','kn':'ಕನ್ನಡ','ml':'മലയാളം','mr':'मराठी','ur':'اردو'}
from .auth import router as auth_router, session_guard, secret, initialize_admin
STAGING = os.getenv('APP_ENV') == 'staging'
PRODUCTION = os.getenv('APP_ENV') == 'production'
MANAGED_AUTH = STAGING or PRODUCTION
PUBLIC_READER = PRODUCTION and os.getenv('PUBLIC_READER_ENABLED') == 'true'
if PUBLIC_READER:
    from urllib.parse import urlparse
    public_url = urlparse(os.getenv('PUBLIC_BASE_URL', ''))
    if os.getenv('PUBLIC_LAUNCH_APPROVAL') != 'approved' or public_url.scheme != 'https' or not public_url.hostname or public_url.username or public_url.password or public_url.query or public_url.fragment or public_url.path not in ('', '/'):
        raise RuntimeError('Public reader requires explicit launch approval and an HTTPS base URL')
RENDER = os.getenv('RENDER') == 'true'
if RENDER and (not MANAGED_AUTH or (STAGING and os.getenv('STAGING_PRIVATE_ACCESS') != 'required')):
    raise RuntimeError('Render deployment requires authenticated staging access')
ADMIN_TOKEN=secret('ADMIN_TOKEN')
STATIC=Path(__file__).parent/'static'

@asynccontextmanager
async def lifespan(app):
    if MANAGED_AUTH: initialize_admin()
    if PRODUCTION:
        from .accounts import cipher
        cipher()  # Fail startup if the persistent MFA encryption key is missing or invalid.
    from .migrate import migrate
    migrate(engine)
    if MANAGED_AUTH:
        from .accounts import ensure_admin
        ensure_admin()
    with SessionLocal() as session:
        if not PRODUCTION and not session.scalar(select(func.count()).select_from(Edition)):
            story=Story(category='Technology', risk='demo');session.add(story);session.flush()
            demo=Edition(story_id=story.id,locale='en',slug='welcome-to-agn-demo',headline='Welcome to AGN — your global newsroom',body='DEMONSTRATION ARTICLE — NOT REAL NEWS. This sample story demonstrates the AGN publishing experience. Open AGN Studio to create your own draft, review the source and rights information, and publish it on the website. The demo is not a report about any real-world event.',state='published',provenance_reviewed=True,published_at=datetime.now(timezone.utc))
            session.add(demo);session.flush()
            session.add(Source(edition_id=demo.id,publisher='AGN demonstration',url='https://example.com/',rights_status='demo'))
            session.add(AuditEvent(edition_id=demo.id,actor='system',action='seeded-demo'))
            session.commit()
    yield

app=FastAPI(title='AGN Global News API',version='0.3.0',lifespan=lifespan, docs_url=None if MANAGED_AUTH else '/docs', redoc_url=None if MANAGED_AUTH else '/redoc', openapi_url=None if MANAGED_AUTH else '/openapi.json')
if MANAGED_AUTH:
    app.include_router(auth_router)
    from .accounts import router as account_router
    app.include_router(account_router)

# Never echo submitted credentials or article text in validation responses.
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    errors = [{'loc': list(error['loc']), 'msg': error['msg'], 'type': error['type']}
              for error in exc.errors()]
    return JSONResponse({'detail': errors}, status_code=422)


@app.middleware('http')
async def security_headers(request, call_next):
    protect_routes = PRODUCTION or (STAGING and os.getenv('STAGING_PRIVATE_ACCESS') == 'required')
    public_paths = {'/studio','/auth/login','/auth/session','/auth/logout','/health','/ready','/assets/site.css','/assets/studio.html','/activate','/assets/account.html','/auth/activate/start','/auth/activate/confirm'}
    reader_path = request.url.path
    reader_get = request.method in ('GET', 'HEAD') and (reader_path in {'/', '/robots.txt', '/sitemap.xml', '/v1/articles'} or re.fullmatch(r'/(?:en|te|hi|ta|kn|ml|mr|ur)(?:/news/[a-z0-9]+(?:-[a-z0-9]+)*)?', reader_path) or re.fullmatch(r'/v1/articles/(?:en|te|hi|ta|kn|ml|mr|ur)/[a-z0-9]+(?:-[a-z0-9]+)*', reader_path))
    requires_session = protect_routes and reader_path not in public_paths and not (PUBLIC_READER and reader_get)
    if requires_session:
        try:
            session_guard(request)
        except HTTPException as exc:
            if request.method == 'GET' and 'text/html' in request.headers.get('accept', ''):
                response = RedirectResponse('/studio', status_code=303)
            else:
                from fastapi.responses import JSONResponse
                response = JSONResponse({'detail':exc.detail}, status_code=exc.status_code)
        else:
            response = await call_next(request)
    else:
        response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    if MANAGED_AUTH:
        if not (PUBLIC_READER and reader_get):
            response.headers['X-Robots-Tag'] = 'noindex, nofollow'
        response.headers['Cache-Control'] = 'no-store'
    return response
app.mount('/assets',StaticFiles(directory=str(STATIC)),name='assets')

def db():
    s=SessionLocal()
    try: yield s
    finally:s.close()

def editor_guard(request: Request, authorization:str|None=Header(default=None)):
    if MANAGED_AUTH:
        if PRODUCTION and not session_guard(request)['mfa_enabled']:
            raise HTTPException(403, 'Enable MFA before accessing the production newsroom')
        from .accounts import require_roles
        if request.method in ('GET','HEAD'):
            return require_roles(request,'admin','editor','reviewer','viewer')
        if request.url.path.endswith(('/publish','/retract')):
            return require_roles(request,'admin','reviewer')
        return require_roles(request,'admin','editor')
    if not ADMIN_TOKEN or ADMIN_TOKEN.startswith('replace-'):
        raise HTTPException(503,'Configure ADMIN_TOKEN in infra/.env')
    if not authorization or not secrets.compare_digest(authorization,f'Bearer {ADMIN_TOKEN}'):
        raise HTTPException(401,'Incorrect editorial token')

class DraftPayload(BaseModel):
    locale:str='en'
    category:str=Field(min_length=2,max_length=80)
    slug:str=Field(min_length=3,max_length=190,pattern=r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
    headline:str=Field(min_length=5,max_length=350)
    body:str=Field(min_length=30,max_length=100000)
    source_url:HttpUrl
    source_publisher:str=Field(min_length=2,max_length=200)

class Approval(BaseModel):
    provenance_reviewed:bool
    rights_verified:bool
    accuracy_reviewed:bool
    actor:str=Field(min_length=2,max_length=150)

class UpdateDraft(DraftPayload):pass

def serialize(e,full=False):
    d={'id':e.id,'story_id':e.story_id,'locale':e.locale,'slug':e.slug,'headline':e.headline,'state':e.state,'category':e.story.category,'published_at':e.published_at.isoformat() if e.published_at else None,'is_demo':e.story.risk=='demo'}
    if full:d.update(body=e.body,sources=[{'publisher':s.publisher,'url':s.url,'rights_status':s.rights_status} for s in e.sources])
    return d

@app.get('/ready')
def ready(session:Session=Depends(db)):
    from sqlalchemy import text
    from sqlalchemy.exc import SQLAlchemyError
    from .migrate import check_revision
    try:
        session.execute(text('SELECT 1'))
        check_revision(session.connection())
    except (SQLAlchemyError, RuntimeError):
        session.rollback()
        raise HTTPException(503, 'Database is not ready') from None
    return {'ok': True}

@app.get('/health')
def health():return {'ok':True,'service':'agn-api','version':app.version}

@app.get('/v1/articles')
def articles(locale:str='en',q:str='',category:str='',session:Session=Depends(db)):
    if locale not in LOCALES:raise HTTPException(400,'Unsupported language')
    stmt=select(Edition).options(selectinload(Edition.story)).join(Story).where(Edition.locale==locale,Edition.state=='published')
    if PRODUCTION:stmt=stmt.where(Story.risk!='demo')
    if q:stmt=stmt.where(Edition.headline.ilike(f'%{q[:100]}%'))
    if category:stmt=stmt.where(Story.category==category)
    return [serialize(e) for e in session.scalars(stmt.order_by(Edition.published_at.desc()).limit(100)).all()]

@app.get('/v1/articles/{locale}/{slug}')
def article(locale:str,slug:str,session:Session=Depends(db)):
    e=session.scalar(select(Edition).options(selectinload(Edition.sources),selectinload(Edition.story)).where(Edition.locale==locale,Edition.slug==slug,Edition.state=='published'))
    if not e or (PRODUCTION and e.story.risk=='demo'):raise HTTPException(404,'Story not found')
    return serialize(e,True)

@app.get('/v1/editor/editions/{eid}',dependencies=[Depends(editor_guard)])
def editorial_detail(eid:int,session:Session=Depends(db)):
    e=session.scalar(select(Edition).options(selectinload(Edition.story),selectinload(Edition.sources)).where(Edition.id==eid))
    if not e:raise HTTPException(404,'Not found')
    return serialize(e,True)

@app.get('/v1/editor/editions',dependencies=[Depends(editor_guard)])
def editorial_list(session:Session=Depends(db)):
    return [serialize(e) for e in session.scalars(select(Edition).options(selectinload(Edition.story)).order_by(Edition.id.desc()).limit(250)).all()]

@app.get('/v1/editor/stats',dependencies=[Depends(editor_guard)])
def stats(session:Session=Depends(db)):
    rows=session.execute(select(Edition.state,func.count()).group_by(Edition.state)).all()
    return {'counts':{k:v for k,v in rows},'languages':len(LOCALES),'total':sum(v for k,v in rows)}

@app.post('/v1/editor/drafts',status_code=201,dependencies=[Depends(editor_guard)])
def create_draft(p:DraftPayload,request:Request,session:Session=Depends(db)):
    if p.locale not in LOCALES:raise HTTPException(400,'Unsupported language')
    if session.scalar(select(Edition.id).where(Edition.locale==p.locale,Edition.slug==p.slug)):
        raise HTTPException(409,'Slug already exists for this language')
    story=Story(category=p.category,risk='unassessed');session.add(story);session.flush()
    e=Edition(story_id=story.id,locale=p.locale,slug=p.slug,headline=p.headline,body=p.body,state='draft')
    session.add(e);session.flush()
    session.add(Source(edition_id=e.id,publisher=p.source_publisher,url=str(p.source_url)))
    session.add(AuditEvent(edition_id=e.id,actor=session_guard(request)['actor'] if MANAGED_AUTH else 'editor',action='created'))
    session.commit();return {'edition_id':e.id,'state':'draft'}

@app.put('/v1/editor/editions/{eid}',dependencies=[Depends(editor_guard)])
def update_draft(eid:int,p:UpdateDraft,request:Request,session:Session=Depends(db)):
    e=session.get(Edition,eid)
    if not e:raise HTTPException(404,'Not found')
    if e.state!='draft':raise HTTPException(409,'Only drafts may be changed')
    if p.locale not in LOCALES:raise HTTPException(400,'Unsupported language')
    if session.scalar(select(Edition.id).where(Edition.locale==p.locale,Edition.slug==p.slug,Edition.id!=eid)):
        raise HTTPException(409,'Slug already used')
    e.locale=p.locale;e.slug=p.slug;e.headline=p.headline;e.body=p.body;e.story.category=p.category
    source=session.scalar(select(Source).where(Source.edition_id==eid))
    if source:source.publisher=p.source_publisher;source.url=str(p.source_url);source.rights_status='unverified'
    session.add(AuditEvent(edition_id=eid,actor=session_guard(request)['actor'] if MANAGED_AUTH else 'editor',action='edited'))
    session.commit();return {'edition_id':eid,'state':'draft'}

@app.post('/v1/editor/editions/{eid}/publish',dependencies=[Depends(editor_guard)])
def publish(eid:int,p:Approval,request:Request,session:Session=Depends(db)):
    e=session.get(Edition,eid)
    if not e:raise HTTPException(404,'Not found')
    if e.state!='draft':raise HTTPException(409,'Only drafts can be published')
    if not(p.provenance_reviewed and p.rights_verified and p.accuracy_reviewed):raise HTTPException(409,'All reviews required')
    e.state='published';e.provenance_reviewed=True;e.published_at=datetime.now(timezone.utc)
    for s in session.scalars(select(Source).where(Source.edition_id==eid)):s.rights_status='editor-verified'
    session.add(AuditEvent(edition_id=eid,actor=session_guard(request)['actor'] if MANAGED_AUTH else p.actor,action='published'))
    session.commit();return {'edition_id':eid,'state':'published'}

@app.post('/v1/editor/editions/{eid}/retract',dependencies=[Depends(editor_guard)])
def retract(eid:int,request:Request,session:Session=Depends(db)):
    e=session.get(Edition,eid)
    if not e:raise HTTPException(404,'Not found')
    if e.state!='published':raise HTTPException(409,'Only published articles can be retracted')
    e.state='retracted';session.add(AuditEvent(edition_id=eid,actor=session_guard(request)['actor'] if MANAGED_AUTH else 'editor',action='retracted'))
    session.commit();return {'edition_id':eid,'state':'retracted'}

@app.get('/v1/editor/audit',dependencies=[Depends(editor_guard)])
def audit(session:Session=Depends(db)):
    rows=session.scalars(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(50)).all()
    return [{'edition_id':x.edition_id,'actor':x.actor,'action':x.action,'at':x.created_at.isoformat() if x.created_at else ''} for x in rows]

@app.get('/activate',response_class=HTMLResponse)
def activate():return (STATIC/'account.html').read_text(encoding='utf-8')

@app.get('/studio',response_class=HTMLResponse)
def studio():return (STATIC/'studio.html').read_text(encoding='utf-8')

@app.get('/robots.txt',response_class=Response)
def robots():return Response('User-agent: *\nDisallow: /studio\nDisallow: /v1/editor\n',media_type='text/plain')

@app.get('/sitemap.xml')
def sitemap(session:Session=Depends(db)):
    base=(os.environ.get('PUBLIC_BASE_URL') or os.environ.get('RENDER_EXTERNAL_URL','http://localhost:8000')).rstrip('/')
    editions=session.scalars(select(Edition).join(Story).where(Edition.state=='published', Story.risk!='demo' if PRODUCTION else True).limit(10000)).all()
    urls=''.join(f'<url><loc>{escape(base)}/{e.locale}/news/{escape(e.slug)}</loc></url>' for e in editions)
    return Response('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+urls+'</urlset>',media_type='application/xml')

@app.get('/',response_class=HTMLResponse)
def root():return (STATIC/'news.html').read_text(encoding='utf-8')

@app.get('/{locale}',response_class=HTMLResponse)
def home(locale:str):
    if locale not in LOCALES:raise HTTPException(404)
    return (STATIC/'news.html').read_text(encoding='utf-8')

@app.get('/{locale}/news/{slug}',response_class=HTMLResponse)
def article_page(locale:str,slug:str,session:Session=Depends(db)):
    if locale not in LOCALES:raise HTTPException(404)
    e=session.scalar(select(Edition).where(Edition.locale==locale,Edition.slug==slug,Edition.state=='published'))
    if not e or (PRODUCTION and e.story.risk=='demo'):raise HTTPException(404,'Article not found')
    template=(STATIC/'article.html').read_text(encoding='utf-8')
    safe_title=escape(e.headline)
    safe_body=''.join(f'<p>{escape(line)}</p>' for line in e.body.split('\n') if line.strip())
    base=(os.environ.get('PUBLIC_BASE_URL') or os.environ.get('RENDER_EXTERNAL_URL','http://localhost:8000')).rstrip('/')
    canonical=f'{base}/{locale}/news/{slug}'
    date=e.published_at.isoformat() if e.published_at else ''
    import json
    structured=json.dumps({'@context':'https://schema.org','@type':'NewsArticle','headline':e.headline,'datePublished':date,'dateModified':date,'inLanguage':locale,'mainEntityOfPage':canonical,'publisher':{'@type':'Organization','name':'AGN Global News'}},ensure_ascii=False).replace('<','\\u003c')
    return HTMLResponse(template.replace('%%TITLE%%',safe_title).replace('%%BODY%%',safe_body).replace('%%LOCALE%%',locale).replace('%%DATE%%',escape(date[:10])).replace('%%CANONICAL%%',escape(canonical)).replace('%%JSONLD%%',structured))
