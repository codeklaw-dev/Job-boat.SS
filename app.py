import html
import base64
import io
import json
import os
import sqlite3
import threading
import zipfile
import xml.etree.ElementTree as ET
import subprocess
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parent
DB = Path(os.getenv('JOB_BOAT_DB', ROOT / 'data' / 'jobs.sqlite3'))
PORT = int(os.getenv('PORT', '8765'))
SOURCES = {
    'remotive': 'https://remotive.com/api/remote-jobs',
    'arbeitnow': 'https://www.arbeitnow.com/api/job-board-api',
}
BOARDS = ['monzo', 'wise', 'deliveroo']
SEARCH_LINKS = {
    'GOV.UK Find a job': 'https://www.findajob.dwp.gov.uk/search',
    'Civil Service Jobs': 'https://www.civilservicejobs.service.gov.uk/csr/index.cgi',
    'LinkedIn': 'https://www.linkedin.com/jobs/',
    'Indeed': 'https://uk.indeed.com/',
    'Reed': 'https://www.reed.co.uk/jobs',
    'Totaljobs': 'https://www.totaljobs.com/',
    'CV-Library': 'https://www.cv-library.co.uk/',
    'Welcome to the Jungle': 'https://www.welcometothejungle.com/en/jobs',
}

def connection():
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY, source TEXT NOT NULL, source_id TEXT NOT NULL, title TEXT NOT NULL, company TEXT NOT NULL DEFAULT "", location TEXT NOT NULL DEFAULT "", url TEXT NOT NULL, description TEXT NOT NULL DEFAULT "", track TEXT NOT NULL DEFAULT "career", status TEXT NOT NULL DEFAULT "new", note TEXT NOT NULL DEFAULT "", created_at TEXT NOT NULL, UNIQUE(source, source_id))')
    if 'verified_at' not in [r[1] for r in db.execute('PRAGMA table_info(jobs)')]:
        db.execute('ALTER TABLE jobs ADD COLUMN verified_at TEXT')
    db.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS cvs (id INTEGER PRIMARY KEY, filename TEXT NOT NULL, text TEXT NOT NULL, bytes BLOB NOT NULL, created_at TEXT NOT NULL)')
    db.commit()
    return db

def get_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'JobBoat/0.1 (+personal job search)', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)

def classify(title, location):
    text = (title + ' ' + location).lower()
    temp = ['temporary', 'temp ', 'warehouse', 'delivery driver', 'retail assistant', 'hospitality', 'agency worker', 'seasonal']
    return 'temp' if any(x in text for x in temp) else 'career'

def base_cv(job, cvs):
    title = (job['title'] + ' ' + job['company']).lower()
    groups = [
        (('warehouse','picker','packer','stock','operative'), 'Warehouse_CV'),
        (('sales associate','fashion','reiss'), 'REISS_Seasonal'),
        (('retail','colleague','barista','customer','costa','tesco','marks and spencer'), 'Sakibur_Rahman_CV.docx'),
        (('property','letting','estate','leasing'), 'Property_CV'),
        (('finance','banking','accountant','risk analyst','consultant'), 'Finance_Professional'),
        (('technology','tech','software','product','business development','ai '), 'Tech_Commercial'),
        (('resident','student accommodation','unite'), 'Sakibur_Rahman.pdf'),
    ]
    for words, fragment in groups:
        if any(word in title for word in words):
            for cv in cvs:
                if fragment.lower() in cv['filename'].lower(): return cv
    for fragment in ('Sakibur_Rahman_CV.docx','Sakibur_Rahman.pdf'):
        for cv in cvs:
            if cv['filename'] == fragment: return cv
    return cvs[0] if cvs else None

def collect():
    jobs, errors = [], []
    for name, url in SOURCES.items():
        try:
            data = get_json(url)
            rows = data.get('jobs', []) if name == 'remotive' else data.get('data', [])
            for row in rows[:200]:
                title = row.get('title') or ''
                location = row.get('candidate_required_location') or row.get('location') or ''
                if name == 'arbeitnow' and not (row.get('remote') or 'uk' in location.lower() or 'united kingdom' in location.lower()):
                    continue
                jobs.append((name, str(row.get('id') or row.get('slug')), title, row.get('company_name') or row.get('company') or '', location, row.get('url') or '', row.get('description') or '', classify(title, location)))
        except Exception as exc:
            errors.append(f'{name}: {type(exc).__name__}: {exc}')
    for board in BOARDS:
        try:
            data = get_json(f'https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true')
            for row in data.get('jobs', []):
                title = row.get('title') or ''
                location = (row.get('location') or {}).get('name') or ''
                if not any(x in location.lower() for x in ('uk', 'united kingdom', 'london', 'remote')):
                    continue
                jobs.append(('greenhouse:' + board, str(row['id']), title, board.title(), location, row.get('absolute_url') or '', row.get('content') or '', classify(title, location)))
        except Exception as exc:
            errors.append(f'greenhouse:{board}: {type(exc).__name__}: {exc}')
    added = 0
    with connection() as db:
        for source, source_id, title, company, location, url, description, track in jobs:
            if not title or not url or not urlparse(url).scheme == 'https':
                continue
            cur = db.execute('INSERT OR IGNORE INTO jobs (source,source_id,title,company,location,url,description,track,created_at,verified_at) VALUES (?,?,?,?,?,?,?,?,?,?)', (source,source_id,title,company,location,url,description,track,datetime.now(timezone.utc).isoformat(),datetime.now(timezone.utc).isoformat()))
            db.execute('UPDATE jobs SET verified_at=? WHERE source=? AND source_id=?',(datetime.now(timezone.utc).isoformat(),source,source_id))
            added += cur.rowcount
        db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', ('last_scan', datetime.now(timezone.utc).isoformat()))
        db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', ('last_errors', json.dumps(errors)))
    return {'added': added, 'errors': errors}

PAGE = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Job Boat</title><style>
:root{font-family:system-ui,sans-serif;color:#14233b;background:#f4f6fa}body{max-width:1100px;margin:auto;padding:24px}h1{margin-bottom:4px}.sub{color:#59677a}button,input,select,textarea{font:inherit;padding:9px;border:1px solid #bbc6d3;border-radius:8px}button{background:#164db4;color:white;cursor:pointer}button.secondary{background:white;color:#164db4}.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}.card{background:white;border:1px solid #dce3ec;border-radius:12px;padding:16px;margin:12px 0}.meta{color:#59677a;font-size:.9em}.pill{background:#e9f0ff;border-radius:20px;padding:3px 9px;font-size:.8em}details{margin-top:10px}textarea{width:95%;min-height:65px}a{color:#164db4}nav a{margin-right:12px}label{display:block;margin:8px 0}.error{color:#a52222}#jobs{min-height:80px}</style></head><body>
<h1>Job Boat</h1><p class="sub">Two tracks. One morning review. Applications only after your approval.</p>
<nav><a href="#brief">Morning brief</a><a href="#profile">Profile</a><a href="#sources">Sources</a></nav>
<section id="brief"><div class="row"><h2>Job review</h2><button onclick="scan()">Scan public feeds</button><select id="track" onchange="load()"><option value="">Both tracks</option><option value="temp">Fast money</option><option value="career">Career</option></select><select id="status" onchange="load()"><option value="">All</option><option value="new">New</option><option value="approved">Approved</option><option value="applied">Applied</option><option value="skipped">Skipped</option></select></div><p id="scanState" class="meta"></p><div id="jobs"></div></section>
<section id="profile"><h2>Reusable profile</h2><p class="meta">Store only information you want used in application drafts. Keep sensitive identifiers out until needed.</p><div class="card"><h3>CV library</h3><input type="file" id="cvFile" accept=".pdf,.docx,.txt"><button onclick="uploadCV()">Add CV</button><div id="cvList"></div><label>Preferred name <input id="name"></label><label>Target roles: fast money <input id="tempRoles" style="width:90%"></label><label>Target roles: career <input id="careerRoles" style="width:90%"></label><label>UK location / radius <input id="location"></label><label>Minimum pay, fast money <input id="tempPay"></label><label>Minimum pay, career <input id="careerPay"></label><label>CV text <textarea id="cv" style="min-height:150px"></textarea></label><label>Reusable application answers <textarea id="answers" placeholder="Availability, work authorisation, notice period, etc."></textarea></label><button onclick="saveProfile()">Save profile</button></div></section>
<section id="sources"><h2>Expand the search</h2><p class="meta">Public feeds can be scanned here. Other platforms need their own permitted integration or job alerts; open them below while those connections are built.</p><div id="sourceLinks" class="card"></div><h3>Add a listing today</h3><div class="card"><label>Job URL <input id="newUrl" style="width:85%"></label><label>Title <input id="newTitle" style="width:85%"></label><label>Employer <input id="newCompany"></label><label>Location <input id="newLocation"></label><label>Track <select id="newTrack"><option value="career">Career</option><option value="temp">Fast money</option></select></label><button onclick="addJob()">Add to review</button></div></section>
<script>
const $=id=>document.getElementById(id);const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path,method='GET',body){let r=await fetch(path,{method,headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});let d=await r.json();if(!r.ok)throw Error(d.error||r.status);return d}
async function load(){let q=new URLSearchParams({track:$('track').value,status:$('status').value});let d=await api('/api/jobs?'+q);$('jobs').innerHTML=d.jobs.length?d.jobs.map(j=>`<div class="card"><div class="row"><strong>${esc(j.title)}</strong><span class="pill">${esc(j.track)}</span><span class="pill">${esc(j.status)}</span><span class="pill">${j.verified_at && Date.now()-Date.parse(j.verified_at)<86400000 ? "Seen in feed today" : "Unverified / stale"}</span></div><div class="meta">${esc(j.company)} · ${esc(j.location)} · ${esc(j.source)}</div><details><summary>Role details and actions</summary><p><a href="${esc(j.url)}" target="_blank" rel="noopener">Open original listing</a></p><div class="row"><button onclick="setStatus(${j.id},'approved')">Approve</button><button class="secondary" onclick="setStatus(${j.id},'skipped')">Skip</button><button class="secondary" onclick="setStatus(${j.id},'applied')">Mark applied</button><button class="secondary" onclick="draft(${j.id})">View CV and draft</button></div><p class="meta">Approval records your decision; submission is a separate step.</p><label>Notes <textarea id="note${j.id}">${esc(j.note)}</textarea></label><button class="secondary" onclick="saveNote(${j.id})">Save note</button><div id="draft${j.id}"></div><details><summary>Listing text</summary><div>${esc(j.description).replace(/\n/g,'<br>').slice(0,14000)}</div></details></details></div>`).join(''):'<div class="card">No jobs in this view yet. Scan public feeds or add a listing.</div>';}
async function setStatus(id,status){await api('/api/jobs/'+id,'PATCH',{status});load()}async function saveNote(id){await api('/api/jobs/'+id,'PATCH',{note:$('note'+id).value});load()}
async function draft(id){let d=await api('/api/draft/'+id);$('draft'+id).innerHTML='<div class="card"><h3>Application pack</h3><p class="meta">Suggested base: '+esc(d.base_filename||'none')+'</p><p><strong>CV:</strong></p><pre style="white-space:pre-wrap">'+esc(d.cv||'Add your CV text in Profile.')+'</pre><p><strong>Reusable answers:</strong></p><pre style="white-space:pre-wrap">'+esc(d.answers||'Add your answers in Profile.')+'</pre><p class="meta">Review and tailor this pack before using it on the employer form.</p></div>'}
async function scan(){$('scanState').textContent='Scanning…';try{let d=await api('/api/scan','POST',{});$('scanState').textContent=`${d.added} new jobs. ${d.errors.length} source errors.`;if(d.errors.length)$('scanState').textContent+=' '+d.errors.join(' | ');load()}catch(e){$('scanState').textContent=e.message}}
async function addJob(){try{await api('/api/jobs','POST',{url:$('newUrl').value,title:$('newTitle').value,company:$('newCompany').value,location:$('newLocation').value,track:$('newTrack').value});$('newUrl').value='';$('newTitle').value='';load()}catch(e){alert(e.message)}}
async function saveProfile(){let p={};for(let k of ['name','tempRoles','careerRoles','location','tempPay','careerPay','cv','answers'])p[k]=$(k).value;await api('/api/profile','PUT',p);alert('Saved')}
async function cvList(){let d=await api('/api/cvs');$('cvList').innerHTML=d.cvs.map(c=>`<p>${esc(c.filename)} · ${c.characters} extracted characters <button class="secondary" onclick="selectCV(${c.id})">Use this CV</button></p>`).join('')}
async function selectCV(id){let d=await api('/api/cv/'+id);$('cv').value=d.text;await saveProfile()}
async function uploadCV(){let f=$('cvFile').files[0];if(!f)return;if(f.size>5e6)return alert('CV must be under 5 MB');let data=await new Promise((resolve,reject)=>{let r=new FileReader();r.onload=()=>resolve(r.result.split(',')[1]);r.onerror=reject;r.readAsDataURL(f)});try{let d=await api('/api/cvs','POST',{filename:f.name,data});$('cv').value=d.text;await saveProfile();cvList()}catch(e){alert(e.message)}}
async function init(){let p=await api('/api/profile');for(let k of ['name','tempRoles','careerRoles','location','tempPay','careerPay','cv','answers'])$(k).value=p[k]||'';let s=await api('/api/sources');$('sourceLinks').innerHTML=Object.entries(s.links).map(([n,u])=>`<p><a href="${esc(u)}" target="_blank" rel="noopener">${esc(n)}</a></p>`).join('');cvList();load()}init();
</script></body></html>'''

class Handler(BaseHTTPRequestHandler):
    def send(self, code, data, content_type='application/json'):
        raw = data.encode() if isinstance(data, str) else json.dumps(data).encode()
        self.send_response(code)
        self.send_header('Content-Type', content_type + '; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
    def body(self):
        size = int(self.headers.get('Content-Length', '0'))
        if size > 7 * 1024 * 1024: raise ValueError('Request too large')
        return json.loads(self.rfile.read(size) or b'{}')
    def do_GET(self):
        from urllib.parse import parse_qs, urlsplit
        path = urlsplit(self.path).path
        if path == '/': return self.send(200, PAGE, 'text/html')
        if path == '/api/sources': return self.send(200, {'links': SEARCH_LINKS})
        if path == '/api/cvs':
            with connection() as db: rows=db.execute('SELECT id,filename,length(text) characters,created_at FROM cvs ORDER BY id DESC').fetchall()
            return self.send(200,{'cvs':[dict(r) for r in rows]})
        if path.startswith('/api/cv/'):
            with connection() as db:row=db.execute('SELECT id,filename,text FROM cvs WHERE id=?',(path.rsplit('/',1)[-1],)).fetchone()
            return self.send(200,dict(row)) if row else self.send(404,{'error':'CV missing'})
        if path == '/api/profile':
            with connection() as db: return self.send(200, {r['key']:r['value'] for r in db.execute('SELECT * FROM settings') if r['key'] in ('name','tempRoles','careerRoles','location','tempPay','careerPay','cv','answers')})
        if path == '/api/jobs':
            q = parse_qs(urlsplit(self.path).query)
            track, status = q.get('track',[''])[0], q.get('status',[''])[0]
            with connection() as db:
                rows = db.execute('SELECT * FROM jobs WHERE (?="" OR track=?) AND (?="" OR status=?) ORDER BY created_at DESC LIMIT 500',(track,track,status,status)).fetchall()
            return self.send(200, {'jobs':[dict(r) for r in rows]})
        if path.startswith('/api/draft/'):
            with connection() as db:
                job = db.execute('SELECT * FROM jobs WHERE id=?',(path.rsplit('/',1)[-1],)).fetchone()
                p = {r['key']:r['value'] for r in db.execute('SELECT * FROM settings')}
            if not job:return self.send(404,{'error':'Job missing'})
            with connection() as db: cvs=db.execute('SELECT filename,text FROM cvs ORDER BY id').fetchall()
            suggested=base_cv(job,cvs)
            return self.send(200,{'job':dict(job),'cv':suggested['text'] if suggested else p.get('cv',''),'base_filename':suggested['filename'] if suggested else None,'answers':p.get('answers','')})
        self.send(404,{'error':'Not found'})
    def do_POST(self):
        try:
            if self.path == '/api/cvs':
                d=self.body();name=Path(d.get('filename','')).name.lower();raw=base64.b64decode(d.get('data',''),validate=True)
                if not raw or len(raw)>5_000_000 or not name.endswith(('.pdf','.docx','.txt')):raise ValueError('Use a PDF, DOCX, or TXT under 5 MB')
                if name.endswith('.txt'): extracted=raw.decode('utf-8',errors='replace')
                elif name.endswith('.docx'):
                    with zipfile.ZipFile(io.BytesIO(raw)) as z:
                        root=ET.fromstring(z.read('word/document.xml'))
                    extracted=' '.join(n.text or '' for n in root.iter() if n.tag.endswith('}t'))
                else:
                    with tempfile.NamedTemporaryFile(suffix='.pdf') as f:
                        f.write(raw);f.flush();extracted=subprocess.run(['pdftotext','-layout',f.name,'-'],capture_output=True,text=True,timeout=10,check=True).stdout
                with connection() as db:cur=db.execute('INSERT INTO cvs (filename,text,bytes,created_at) VALUES (?,?,?,?)',(name,extracted[:100000],raw,datetime.now(timezone.utc).isoformat()))
                return self.send(200,{'id':cur.lastrowid,'text':extracted[:100000]})
            if self.path == '/api/scan':return self.send(200,collect())
            if self.path == '/api/jobs':
                d=self.body();url=d.get('url','').strip();title=d.get('title','').strip()
                if urlparse(url).scheme != 'https' or not title:raise ValueError('HTTPS URL and title required')
                track=d.get('track','career')
                if track not in ('temp','career'):raise ValueError('Invalid track')
                with connection() as db:
                    cur=db.execute('INSERT OR IGNORE INTO jobs (source,source_id,title,company,location,url,description,track,created_at) VALUES (?,?,?,?,?,?,?,?,?)',('manual',url,title,d.get('company',''),d.get('location',''),url,'',track,datetime.now(timezone.utc).isoformat()))
                return self.send(200,{'added':cur.rowcount})
            self.send(404,{'error':'Not found'})
        except (ValueError,sqlite3.Error) as exc:self.send(400,{'error':str(exc)})
    def do_PUT(self):
        try:
            if self.path != '/api/profile':return self.send(404,{'error':'Not found'})
            d=self.body();allowed=('name','tempRoles','careerRoles','location','tempPay','careerPay','cv','answers')
            with connection() as db:
                for key in allowed:
                    if key in d:db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(key,str(d[key])[:50000]))
            self.send(200,{'saved':True})
        except (ValueError,sqlite3.Error) as exc:self.send(400,{'error':str(exc)})
    def do_PATCH(self):
        try:
            if not self.path.startswith('/api/jobs/'):return self.send(404,{'error':'Not found'})
            d=self.body();updates=[];args=[]
            if 'status' in d:
                if d['status'] not in ('new','approved','applied','skipped'):raise ValueError('Invalid status')
                updates.append('status=?');args.append(d['status'])
            if 'note' in d:updates.append('note=?');args.append(str(d['note'])[:10000])
            if not updates:raise ValueError('No update')
            args.append(self.path.rsplit('/',1)[-1])
            with connection() as db:cur=db.execute('UPDATE jobs SET '+','.join(updates)+' WHERE id=?',args)
            self.send(200,{'updated':cur.rowcount})
        except (ValueError,sqlite3.Error) as exc:self.send(400,{'error':str(exc)})

def auto_scan():
    while True:
        try: collect()
        except Exception as exc: print('Scan error:',exc,flush=True)
        time.sleep(6*3600)

if __name__ == '__main__':
    connection().close()
    if os.getenv('JOB_BOAT_AUTO_SCAN') == '1':threading.Thread(target=auto_scan,daemon=True).start()
    print(f'Job Boat on http://127.0.0.1:{PORT}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',PORT),Handler).serve_forever()
