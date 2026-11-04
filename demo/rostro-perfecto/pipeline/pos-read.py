"""Read-only Titivate exploration using the app's published Firebase auth/API route."""
import json,os,re,time,urllib.request,urllib.error,urllib.parse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
private=ROOT/'.secrets';private.mkdir(exist_ok=True,mode=0o700)
out=ROOT/'outputs/pos-private';out.mkdir(exist_ok=True,mode=0o700)
env={}
for line in (ROOT.parents[3]/'.env').read_text().splitlines():
    m=re.match(r'\s*(?:export\s+)?(RPP_POS_\w+)\s*=\s*(.*?)\s*$',line)
    if m:env[m[1]]=m[2].strip('\"\'')
def store(path,data):
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False));os.chmod(path,0o600)
cache=private/'pos-session.json'
if cache.exists() and time.time()-cache.stat().st_mtime<3300:
    auth=json.loads(cache.read_text())
else:
    bundle=(ROOT/'.cache/titivate-main.dart.js').read_text()
    m=re.search(r'A\.i3M\("([^"]+)","[^\"]+","([^\"]+firebaseapp.com)"',bundle)
    if not m:raise RuntimeError('Published Firebase configuration not found')
    req=urllib.request.Request('https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key='+m[1],data=json.dumps({'email':env['RPP_POS_USER'],'password':env['RPP_POS_PASS'],'returnSecureToken':True}).encode(),headers={'Content-Type':'application/json','Origin':'https://app.titivate.com'})
    try:
        with urllib.request.urlopen(req,timeout=30) as r:auth=json.load(r)
    except urllib.error.HTTPError as e:
        d=json.loads(e.read());print('Authentication rejected:',d.get('error',{}).get('message','unknown'));raise SystemExit(77)
    store(cache,auth)
print('POS authentication succeeded; token not printed')
with urllib.request.urlopen('https://app.titivate.com/assets/assets/environment_values/environment.json',timeout=20) as r:base=json.load(r)['urlAPI'].rstrip('/')+'/api'
def get(path,params=None):
    query=urllib.parse.urlencode(params or {})
    req=urllib.request.Request(base+path+('?' +query if query else ''),headers={'Authorization':'Bearer '+auth['idToken'],'Accept':'application/json','Origin':'https://app.titivate.com'})
    with urllib.request.urlopen(req,timeout=45) as r:return json.load(r)
def rows(d):
    if isinstance(d,list):return d
    if isinstance(d,dict):
        data=d.get('data',d.get('results',[]))
        if isinstance(data,dict):return rows(data)
        return data if isinstance(data,list) else []
    return []
if os.environ.get('RPP_POS_ACTION'):
    exec((ROOT/'scripts'/os.environ['RPP_POS_ACTION']).read_text())
else:
    try:
        d=get('/branches',{'search':os.environ['POS_BRANCH'],'per_page':50,'return_full_objects':1})
        store(out/'branches-plaza-central.json',d)
        print('Branch response keys:',list(d) if isinstance(d,dict) else 'list')
        for r in rows(d):print({k:r.get(k) for k in ['id','company_id','code','cod_branch','name','address','timezone']})
    except urllib.error.HTTPError as e:
        print('GET /branches HTTP',e.code,e.read(1200).decode(errors='replace'))
