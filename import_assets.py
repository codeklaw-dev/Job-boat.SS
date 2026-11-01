"""Import user-supplied files into the ignored local database. Usage: python import_assets.py /path/to/attachments"""
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from zipfile import ZipFile
import subprocess
import xml.etree.ElementTree as ET
import openpyxl
from app import connection

root = Path(sys.argv[1])
files = list(root.glob('*/*'))
with connection() as db:
    db.execute('CREATE TABLE IF NOT EXISTS documents (id INTEGER PRIMARY KEY, filename TEXT UNIQUE NOT NULL, category TEXT NOT NULL, text TEXT NOT NULL, bytes BLOB NOT NULL, created_at TEXT NOT NULL)')
    cv_added = doc_added = jobs_added = 0
    for path in files:
        suffix = path.suffix.lower()
        if suffix not in ('.pdf','.docx'): continue
        raw = path.read_bytes()
        if suffix == '.pdf':
            content = subprocess.run(['pdftotext', '-layout', str(path), '-'], capture_output=True, text=True, check=True).stdout
        else:
            with ZipFile(path) as z: xml = ET.fromstring(z.read('word/document.xml'))
            content = ' '.join(n.text or '' for n in xml.iter() if n.tag.endswith('}t'))
        category = 'cv' if 'CV' in path.name.upper() or path.name in ('Sakibur_Rahman.pdf','Sakibur_Rahman_Unite_Tech_AI_Talent_Pool.pdf') else 'supporting'
        table = 'cvs' if category == 'cv' else 'documents'
        if category == 'cv':
            if db.execute('SELECT 1 FROM cvs WHERE filename=?',(path.name,)).fetchone(): continue
            db.execute('INSERT INTO cvs (filename,text,bytes,created_at) VALUES (?,?,?,?)',(path.name,content,raw,datetime.now(timezone.utc).isoformat()))
            db.execute('DELETE FROM documents WHERE filename=?',(path.name,))
            cv_added += 1
        else:
            cur=db.execute('INSERT OR IGNORE INTO documents (filename,category,text,bytes,created_at) VALUES (?,?,?,?,?)',(path.name,category,content,raw,datetime.now(timezone.utc).isoformat()))
            doc_added += cur.rowcount
    for path in files:
        if path.suffix.lower() != '.xlsx': continue
        sheet = openpyxl.load_workbook(path,data_only=True).worksheets[0]
        for row in list(sheet)[4:]:
            title = row[1].value
            if not title: continue
            link = row[12].hyperlink.target if row[12].hyperlink else None
            if not link or urlparse(link).scheme != 'https': continue
            employer = str(row[2].value or '')
            area = str(row[3].value or '')
            notes = 'Imported from spreadsheet compiled 9 Oct 2026; verify vacancy is still open. '+ ' | '.join(f'{name}: {row[i].value}' for name,i in [('Priority',0),('Pay',5),('Hours',6),('Original status',8),('Notes',10)] if row[i].value)
            cur=db.execute('INSERT OR IGNORE INTO jobs (source,source_id,title,company,location,url,description,track,status,note,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)',('spreadsheet:'+path.name,link,str(title),employer,area,link,'','temp','new',notes,datetime.now(timezone.utc).isoformat()))
            jobs_added += cur.rowcount
    print(f'Imported {cv_added} CVs, {doc_added} supporting documents, {jobs_added} linked jobs')
