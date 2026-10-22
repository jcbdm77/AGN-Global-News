"""CI-only acceptance test against private HTTPS; never prints credentials."""
import http.cookiejar
import json
from pathlib import Path
import ssl
import subprocess
import urllib.error
import urllib.request

ctx = ssl.create_default_context(cafile='/tmp/agn-root.crt')
jar = http.cookiejar.CookieJar()
client = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx), urllib.request.HTTPCookieProcessor(jar))

def call(path, data=None, csrf=None):
    headers = {'Content-Type': 'application/json'}
    if csrf: headers['X-CSRF-Token'] = csrf
    req = urllib.request.Request('https://localhost:8443'+path, data=json.dumps(data).encode() if data is not None else None, headers=headers)
    try:
        with client.open(req) as r: return r.status, json.load(r)
    except urllib.error.HTTPError as e: return e.code, None

assert call('/ready')[0] == 200
assert call('/v1/articles?locale=en')[0] == 401
assert call('/v1/editor/stats')[0] == 401
status, login = call('/auth/login', {'username':'admin','password':Path('/tmp/agn-ci-password').read_text()})
assert status == 200, f'Login failed: HTTP {status}'
assert call('/v1/editor/stats')[0] == 200
assert call('/v1/articles?locale=en')[0] == 200
assert call('/v1/editor/drafts', {})[0] == 403
assert call('/auth/logout', {}, login['csrf_token'])[0] == 200
assert call('/v1/editor/stats')[0] == 401
for service in ['postgres','api','https']:
    cid = subprocess.check_output(['docker','compose','-f','infra/staging/compose.yml','ps','-q',service],text=True).strip()
    container = json.loads(subprocess.check_output(['docker','inspect',cid],text=True))[0]
    bindings = container['HostConfig']['PortBindings'] or {}
    if service == 'https':
        assert bindings == {'443/tcp':[{'HostIp':'127.0.0.1','HostPort':'8443'}]}, bindings
    else:
        assert not any(bindings.values()), f'{service} exposes a host port'
print('HTTPS, PostgreSQL, session authentication, CSRF/logout and loopback-only ports passed.')
