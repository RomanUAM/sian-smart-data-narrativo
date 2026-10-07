"""Transactional, restartable collection jobs. No Streamlit session ownership."""
import contextlib
import datetime as dt
import io
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import time
import tempfile
from process_lock import worker_lock
import zipfile
from pathlib import Path
from corpus_contract import identity_key, merge_record
from corpus_storage import atomic_json, atomic_write
from collection_policy import assess
from geographic_scope import scope_terms

class Job:
    def __init__(self, root):
        self.root = Path(root).resolve(); self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root/'job.sqlite3'
        with self.connect() as c:
            c.executescript('CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY,v TEXT); CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY,config TEXT,status TEXT DEFAULT "pending",error TEXT); CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY,payload TEXT); CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,created REAL,message TEXT); CREATE TABLE IF NOT EXISTS engines(name TEXT PRIMARY KEY,until REAL,reason TEXT);')
    def connect(self):
        c = sqlite3.connect(self.db, timeout=30); c.execute('PRAGMA busy_timeout=30000'); return c
    def get(self, key, default=None):
        with self.connect() as c: r=c.execute('SELECT v FROM meta WHERE k=?',(key,)).fetchone()
        return json.loads(r[0]) if r else default
    def set(self, key, value):
        with self.connect() as c:c.execute('INSERT OR REPLACE INTO meta VALUES (?,?)',(key,json.dumps(value,ensure_ascii=False)))
    @classmethod
    def create(cls, base, config, tasks):
        job=cls(Path(base)/secrets.token_hex(16))
        config={**config,'output_dir':str(job.root),'collection_version':3,'geographic_terms':scope_terms(config.get('geographic_scope',''),config.get('geographic_terms'))}
        job.set('config',config);job.set('created_at',dt.datetime.now(dt.UTC).isoformat());job.set('status','ready');job.set('pause',False)
        # Snapshot selected seed files so restoring a ZIP cannot read arbitrary server paths.
        seed_payload={}
        for task in tasks:
            for path in task.get('seed_files',[]):
                try:
                    value=json.loads(Path(path).read_text())
                    if isinstance(value,list):seed_payload[path]=[r for r in value if isinstance(r,dict)]
                except (OSError,ValueError):pass
        job.set('seed_payload',seed_payload)
        with job.connect() as c:
            c.executemany('INSERT INTO tasks(config) VALUES (?)',[(json.dumps(t,ensure_ascii=False),) for t in tasks])
        job.export(); return job
    @classmethod
    def conjugate(cls, base, config, jobs):
        job=cls.create(base,config,[])
        for source in jobs:
            for row in source.rows():
                row['collection_origins']=sorted(set(row.get('collection_origins',[])+[source.root.name]))
                job.ingest(row)
        _,report=job.export()
        job.set('status','target_met' if report['target_met'] else 'finished_with_gaps')
        job.log(f'Conjugadas {len(jobs)} ejecuciones; identidad y procedencia conservadas.')
        job.export();return job
    def ingest(self, row):
        from evidence_model import normalize_record
        row=normalize_record(row); key=identity_key(row)
        with self.connect() as c:
            old=c.execute('SELECT payload FROM records WHERE id=?',(key,)).fetchone()
            if old:row=merge_record(json.loads(old[0]),row)
            c.execute('INSERT OR REPLACE INTO records VALUES (?,?)',(key,json.dumps(row,ensure_ascii=False)))
    def rows(self):
        with self.connect() as c:return [json.loads(r[0]) for r in c.execute('SELECT payload FROM records ORDER BY id')]
    def log(self, message):
        with self.connect() as c:c.execute('INSERT INTO events(created,message) VALUES (?,?)',(time.time(),str(message)))
    def logs(self):
        with self.connect() as c:return [r[0] for r in reversed(c.execute('SELECT message FROM events ORDER BY id DESC LIMIT 40').fetchall())]
    def export(self):
        rows,report=assess(self.rows(),self.get('config'))
        atomic_json(self.root/'news_records_merged.json',rows)
        atomic_write(self.root/'news_records_merged.jsonl',''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
        with self.connect() as c:
            report['source_controls']=[{'engine':r[0],'next_allowed_at':dt.datetime.fromtimestamp(r[1],dt.UTC).isoformat(),'reason':r[2]} for r in c.execute('SELECT name,until,reason FROM engines')]
        atomic_json(self.root/'coverage.json',report)
        import csv
        csv_buffer=io.StringIO();writer=csv.DictWriter(csv_buffer,fieldnames=['year','target','selected','gap','period_complete']);writer.writeheader();writer.writerows(report['annual'])
        atomic_write(self.root/'coverage_annual.csv',csv_buffer.getvalue())
        with self.connect() as c:tasks=[dict(zip(('id','status','error'),r)) for r in c.execute('SELECT id,status,error FROM tasks')]
        from record_schema import digest
        from historical_sources import CAPABILITIES
        with self.connect() as c:query_plan=[{'task_id':r[0],'config':json.loads(r[1])} for r in c.execute('SELECT id,config FROM tasks ORDER BY id')]
        atomic_json(self.root/'query_plan.json',query_plan)
        atomic_json(self.root/'run_manifest.json',{'system':'SIAN','execution_version':3,'record_schema_version':2,'created_at':self.get('created_at'),'config':self.get('config'),'config_hash':digest(self.get('config')),'plan_hash':digest(query_plan),'source_capabilities':CAPABILITIES,'status':self.status(),'coverage':report,'tasks':tasks})
        return rows,report
    def active(self):
        try:
            with worker_lock(self.root/'worker.lock'):return False
        except BlockingIOError:return True
    def status(self):
        status=self.get('status','ready')
        return 'interrupted' if status=='running' and not self.active() else status
    def launch(self):
        if self.active():return
        self.set('pause',False)
        with open(self.root/'worker.log','ab') as out:
            subprocess.Popen([sys.executable,'-m','collection_runner',str(self.root)],cwd=Path(__file__).parent,stdout=out,stderr=out,start_new_session=True)
    def pause(self):self.set('pause',True)
    def archive(self):
        # Derive every export from the SAME SQLite snapshot, not from a live DB.
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);snapshot=sqlite3.connect(root/'job.sqlite3')
            with self.connect() as c:c.backup(snapshot)
            snapshot.close()
            archived=Job(root);archived.set('status','paused');archived.set('pause',True);archived.export()
            out=io.BytesIO()
            with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
                for name in ('job.sqlite3','news_records_merged.json','news_records_merged.jsonl','coverage.json','coverage_annual.csv','run_manifest.json','query_plan.json'):
                    z.write(root/name,name)
            return out.getvalue()
    @classmethod
    def restore(cls,base,data):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if sum(x.file_size for x in z.infolist())>500_000_000:raise ValueError('El respaldo excede 500 MB.')
            if 'job.sqlite3' not in z.namelist():
                from historical_sources import plan
                from web_corpus_io import parse_corpus_upload
                manifests=sorted((n for n in z.namelist() if Path(n).name=='run_manifest.json'),key=lambda n:(n.count('/'),n))
                if not manifests:raise ValueError('Respaldo sin manifiesto ni estado de ejecución.')
                config=json.loads(z.read(manifests[0])).get('config',{})
                if not {'start_year','end_year','query'}<=config.keys():raise ValueError('Manifiesto antiguo incompleto.')
                config['target_total_per_year']=int(config.get('target_total_per_year') or 200)
                # Ignore absolute paths from the old server; use the repository's curated seeds.
                config['seed_url_file']='';config['seed_url_files_by_source']={}
                job=cls.create(base,config,plan(config))
                record_names={'news_records.json','news_records.jsonl','news_records_merged.json','news_records_merged.jsonl','news_records_sequential_merged.json','news_records_sequential_merged.jsonl','news_records_incremental.jsonl'}
                for name in z.namelist():
                    if Path(name).name in record_names:
                        for row in parse_corpus_upload(z.read(name),name):job.ingest(row)
                job.set('status','paused');job.set('pause',True);job.log('Respaldo antiguo migrado al coordinador histórico; avance conservado y plan nuevo reanudable.')
                job.export();return job
            raw=z.read('job.sqlite3')
        root=Path(base)/secrets.token_hex(16);root.mkdir(parents=True)
        atomic_write(root/'job.sqlite3',raw)
        check=sqlite3.connect(root/'job.sqlite3')
        try:
            if check.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Base de ejecución dañada.')
        finally:check.close()
        job=cls(root)
        config=job.get('config')
        if not isinstance(config,dict) or not {'start_year','end_year','query'}<=config.keys():raise ValueError('Respaldo no válido.')
        config['output_dir']=str(root);job.set('config',config)
        job.set('status','paused');job.set('pause',True)
        with job.connect() as c:c.execute('UPDATE tasks SET status="pending" WHERE status="running"')
        job.export();return job

def job_base():return Path(os.environ.get('SIAN_DATA_DIR','.sian_jobs')).resolve()

def open_job(token):
    if len(token)!=32 or any(c not in '0123456789abcdef' for c in token):raise ValueError('Código de ejecución inválido.')
    root=job_base()/token
    if not (root/'job.sqlite3').exists():
        from job_backup import recover
        data=recover(token)
        if data is not None:
            restored=Job.restore(job_base(),data)
            restored.root.rename(root)
            restored=Job(root);config=restored.get('config');config['output_dir']=str(root);restored.set('config',config)
        else:raise ValueError('No se encuentra esta ejecución; importa su respaldo ZIP.')
    return Job(root)
