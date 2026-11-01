"""Sync the private local database to one Supabase account after first sign-in.

Requires SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, JOB_BOAT_OWNER_ID.
The service role key belongs only in this server-side environment, never Vercel's VITE_* variables.
"""
import json
import os
import urllib.request
from app import connection

base=os.environ['SUPABASE_URL'].rstrip('/')
key=os.environ['SUPABASE_SERVICE_ROLE_KEY']
owner=os.environ['JOB_BOAT_OWNER_ID']

def upsert(table, rows, conflict):
    if not rows:return
    endpoint=f'{base}/rest/v1/{table}?on_conflict={conflict}'
    for start in range(0,len(rows),100):
        batch=rows[start:start+100]
        request=urllib.request.Request(endpoint,data=json.dumps(batch).encode(),method='POST',headers={
            'apikey':key,'Authorization':'Bearer '+key,'Content-Type':'application/json',
            'Prefer':'resolution=merge-duplicates,return=minimal'
        })
        with urllib.request.urlopen(request,timeout=30) as response:
            if response.status not in (200,201,204):raise RuntimeError(f'{table} sync failed: HTTP {response.status}')
    print(f'Synced {len(rows)} {table} records')

with connection() as db:
    jobs=[dict(r) for r in db.execute('SELECT source,source_id,title,company,location,url,description,track,status,note,verified_at,created_at FROM jobs')]
    cvs=[dict(r) for r in db.execute('SELECT filename,text,created_at FROM cvs')]
    settings={r['key']:r['value'] for r in db.execute('SELECT key,value FROM settings')}
for row in jobs:row['owner_id']=owner
for row in cvs:
    row['owner_id']=owner
    row['content']=row.pop('text')
    row['category']='general'
upsert('jobs',jobs,'owner_id,source,source_id')
upsert('cvs',cvs,'owner_id,filename')
upsert('profile',[{'owner_id':owner,'location':settings.get('location','Bristol; willing to relocate for career roles'),'temp_roles':settings.get('tempRoles',''),'career_roles':settings.get('careerRoles',''),'temp_pay':settings.get('tempPay',''),'career_pay':settings.get('careerPay','')}],'owner_id')
