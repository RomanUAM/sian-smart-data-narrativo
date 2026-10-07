"""Process-independent source cooldowns shared across every job task."""
import datetime as dt
import email.utils
import json
import os
import sqlite3
import time
from pathlib import Path

def connection():
    path=Path(os.environ.get('SIAN_SOURCE_STATE', '.sian_cache/source_state.sqlite3'))
    path.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(path,timeout=30)
    c.execute('CREATE TABLE IF NOT EXISTS engines(name TEXT PRIMARY KEY, until REAL, reason TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS queries(id TEXT PRIMARY KEY, payload TEXT, expires REAL)')
    return c

def remaining(engine):
    with connection() as c:r=c.execute('SELECT until FROM engines WHERE name=?',(engine,)).fetchone()
    return max(0,r[0]-time.time()) if r else 0

def cooldown(engine, retry_after=None, minimum=60):
    seconds=minimum
    try:seconds=max(minimum,float(retry_after))
    except (ValueError,TypeError):
        try:seconds=max(minimum,email.utils.parsedate_to_datetime(retry_after).timestamp()-time.time())
        except (ValueError,TypeError,AttributeError):pass
    seconds=min(seconds,86400)
    with connection() as c:c.execute('INSERT INTO engines VALUES (?,?,?) ON CONFLICT(name) DO UPDATE SET until=MAX(until,excluded.until),reason=excluded.reason',(engine,time.time()+seconds,'rate_limited'))
    return seconds

def cached_query(key):
    with connection() as c:r=c.execute('SELECT payload,expires FROM queries WHERE id=?',(key,)).fetchone()
    return json.loads(r[0]) if r and r[1]>time.time() else None

def save_query(key,payload,ttl=3600):
    with connection() as c:c.execute('INSERT OR REPLACE INTO queries VALUES (?,?,?)',(key,json.dumps(payload,default=str),time.time()+ttl))
