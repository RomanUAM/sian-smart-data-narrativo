"""Atomic file replacement and transactional document/version/retrieval storage."""
from __future__ import annotations
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from record_schema import validate_record

def atomic_write(path, data, encoding="utf-8"):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.'+path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(data.encode(encoding) if isinstance(data,str) else data);stream.flush();os.fsync(stream.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def atomic_json(path,data):atomic_write(path,json.dumps(data,ensure_ascii=False,indent=2,default=str))

class CorpusStore:
    def __init__(self,path):
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.connection=sqlite3.connect(path)
        self.connection.execute('PRAGMA foreign_keys=ON')
        self.connection.executescript('''CREATE TABLE IF NOT EXISTS documents(document_id TEXT PRIMARY KEY, canonical_document_id TEXT, current_version_id TEXT, record_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS versions(version_id TEXT,document_id TEXT REFERENCES documents(document_id),payload_json TEXT NOT NULL,PRIMARY KEY(document_id,version_id));
        CREATE TABLE IF NOT EXISTS retrievals(retrieval_id TEXT PRIMARY KEY,document_id TEXT REFERENCES documents(document_id),version_id TEXT NOT NULL,payload_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS relations(document_id TEXT REFERENCES documents(document_id),relation_json TEXT,PRIMARY KEY(document_id,relation_json));''')
    def put(self,rows):
        with self.connection:
            for row in rows:
                import copy
                row=copy.deepcopy(row)
                previous=self.connection.execute('SELECT record_json FROM documents WHERE document_id=?',(row.get('document_id'),)).fetchone()
                if previous:
                    old=json.loads(previous[0])
                    for field in ('versions','retrievals','record_history'):
                        for item in old[field]:
                            if item not in row[field]:row[field].append(item)
                    if old['version_id']!=row['version_id']:
                        event={'event':'registry_version_changed','from_version':old['version_id'],'to_version':row['version_id']}
                        if event not in row['record_history']:row['record_history'].append(event)
                validate_record(row)
                self.connection.execute('INSERT INTO documents VALUES(?,?,?,?) ON CONFLICT(document_id) DO UPDATE SET canonical_document_id=excluded.canonical_document_id,current_version_id=excluded.current_version_id,record_json=excluded.record_json',(row['document_id'],row['canonical_document_id'],row['version_id'],json.dumps(row,ensure_ascii=False)))
                for v in row['versions']:self.connection.execute('INSERT OR IGNORE INTO versions VALUES(?,?,?)',(v['version_id'],row['document_id'],json.dumps(v,ensure_ascii=False)))
                for r in row['retrievals']:self.connection.execute('INSERT OR IGNORE INTO retrievals VALUES(?,?,?,?)',(r['retrieval_id'],row['document_id'],r['version_id'],json.dumps(r,ensure_ascii=False)))
                for r in row['document_relations']:self.connection.execute('INSERT OR IGNORE INTO relations VALUES(?,?)',(row['document_id'],json.dumps(r,ensure_ascii=False,sort_keys=True)))
    def close(self):self.connection.close()
