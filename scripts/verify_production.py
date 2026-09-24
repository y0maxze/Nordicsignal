"""Read-only production checks. Emits assertions and metadata, never API bodies/secrets."""
import json
import re
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse
from pathlib import Path

FRONTEND = 'https://nordicsignal.8pnwk5r8f4.workers.dev'
BACKEND = 'https://nordicsignal-api.onrender.com'
checks = []


def fetch(origin, path):
    try:
        with urllib.request.urlopen(urllib.request.Request(origin+path, headers={'User-Agent':'Aksjer-production-verification'}), timeout=35) as response:
            return response.status, response.read().decode(), dict(response.headers), response.url
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode(), dict(error.headers), error.url


def require(condition, name):
    checks.append({'check':name,'passed':bool(condition)})
    print(('PASS ' if condition else 'FAIL ')+name, flush=True)


def run_content_checks():
    # Render and Cloudflare deploy independently; wait only for the newly introduced routes.
    for attempt in range(12):
        status, body, _, _ = fetch(FRONTEND, '/api/early-discovery')
        if status == 200 and '"items"' in body:break
        if attempt < 11:time.sleep(15)
    for path in ['/app','/morning','/stock?ticker=EQNR']:
        status, body, headers, _ = fetch(FRONTEND,path)
        require(status==200,path+' HTTP 200')
        require('Aksjer' in body or 'AKSJER' in body,path+' branding')
        require('portfolio_dashboard.js' not in body and 'dashboard_performance.js' not in body,path+' no portfolio injection')
        require('stock_readiness.js' not in body and 'stock_opportunity_ui.js' not in body,path+' no duplicated stock UI')
        require(headers.get('x-content-type-options',headers.get('X-Content-Type-Options'))=='nosniff',path+' security header')
        if path=='/app':require('showStock(' not in body and '/stock?ticker=' in body,'canonical Market routing')
        if path.startswith('/stock'):require('stock_analysis.js' in body,'continuous Stock analysis asset')
    for path in ['/holdings','/holdings.html','/portfolio','/frontend/holdings.html','/mobile.html']:
        status,body,_,url=fetch(FRONTEND,path)
        require(status==200 and url.endswith('/app'),path+' redirects to Market')
    for path in ['/api/stocks','/api/market-snapshot','/api/morning-brief','/api/early-discovery','/api/early-discovery/EQNR/history','/api/opportunity-timeline/EQNR','/api/ipo-radar?limit=2']:
        status,body,_,_=fetch(FRONTEND,path)
        require(status==200,path+' HTTP 200')
        try:d=json.loads(body)
        except ValueError:d=None
        require(isinstance(d,(dict,list)),path+' JSON')
        if path=='/api/market-snapshot' and isinstance(d,dict):
            require(isinstance(d.get('items'),list) and len(d['items'])>0,'Market real universe available')
            require(all(x.get('data_status') in {'LIVE','FORSINKET','LAGRET','UTILGJENGELIG'} for x in d.get('items',[])),'Market truthful data states')
        if path=='/api/early-discovery' and isinstance(d,dict):require(d.get('score_effect')==0,'Early Discovery zero score effect')
    for origin,path,expected in [(FRONTEND,'/api/dashboard-home?phase=core',403),(FRONTEND,'/api/holdings',403),(FRONTEND,'/api/refresh',403),(BACKEND,'/api/holdings',401),(BACKEND,'/api/refresh',401)]:
        status,_,_,_=fetch(origin,path)
        require(status==expected,('Worker' if origin==FRONTEND else 'Backend')+path+' unauthenticated denied')
    for path in ['/manifest.webmanifest','/sw.js','/stock_analysis.js']:
        status,body,_,_=fetch(FRONTEND,path)
        require(status==200 and len(body)>20,path+' available')
        if path=='/sw.js':require("CACHE_NAME='aksjer-shell-v7'" in body,'PWA current shell')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_boundary(origin, path):
    # Do not follow login redirects: a login page's HTTP 200 is not app availability.
    request = urllib.request.Request(origin + path, headers={'User-Agent': 'Aksjer-boundary-verification'})
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=35) as response:
            return response.status, dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers)


def is_access_login(status, headers):
    location = headers.get('Location', headers.get('location', ''))
    target = urlparse(location)
    return (status in {302, 303, 307} and target.scheme == 'https'
            and target.hostname == 'lucky-darkness-5204.cloudflareaccess.com'
            and target.path.startswith('/cdn-cgi/access/login'))


def run():
    # Access was enabled by the owner on 2026-09-24 for this Worker, all traffic.
    # This checks the anonymous boundary only; it must never certify authenticated UX.
    frontend_paths = ['/app', '/morning', '/stock?ticker=EQNR', '/holdings',
                      '/holdings.html', '/portfolio', '/frontend/holdings.html',
                      '/mobile.html', '/api/stocks', '/api/market-snapshot',
                      '/api/morning-brief', '/api/early-discovery', '/api/holdings',
                      '/api/refresh', '/manifest.webmanifest', '/sw.js', '/stock_analysis.js']
    for path in frontend_paths:
        status, headers = fetch_boundary(FRONTEND, path)
        require(is_access_login(status, headers), 'Worker ' + path + ' requires Access login')
    status, _ = fetch_boundary(BACKEND, '/api/health')
    require(status == 200, 'Backend public health available')
    for path in ['/api/stocks', '/api/market-snapshot', '/api/morning-brief',
                 '/api/early-discovery', '/api/security-status', '/api/holdings', '/api/refresh']:
        status, _ = fetch_boundary(BACKEND, path)
        require(status == 401, 'Backend ' + path + ' direct anonymous access denied')


if __name__ == '__main__':
    try:
        run()
    finally:
        Path('production-verification.json').write_text(json.dumps({
            'scope': 'anonymous_security_boundary',
            'authenticated_content_verification': 'not_run_no_access_session',
            'checks': checks,
        }, indent=2))
    if not checks or not all(x['passed'] for x in checks):
        raise SystemExit(1)
