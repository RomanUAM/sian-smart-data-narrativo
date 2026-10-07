"""Versioned record contract, independent of source readers and presentation."""
from __future__ import annotations
import copy
import hashlib
import json
from urllib.parse import urlsplit, parse_qsl, urlencode
import re

SCHEMA_VERSION = 2
STAGES = ('discovery','retrieval','extraction','selection','review','analysis')
SELECTION_STATES = {'candidate','pending','included','excluded'}

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()[:24]

def canonical_url_key(url):
    parsed=urlsplit(str(url or '').strip())
    if not parsed.netloc:return str(url or '').strip().rstrip('/')
    tracking={'fbclid','gclid','mc_cid','mc_eid'}
    pairs=[(k,v) for k,v in parse_qsl(parsed.query,keep_blank_values=True) if not k.lower().startswith('utm_') and k.lower() not in tracking]
    query=urlencode(sorted(pairs))
    return parsed.netloc.lower().removeprefix('www.')+parsed.path.rstrip('/')+('?' + query if query else '')

def identity_key(row):
    doi=re.search(r'10\.\d{4,9}/[^\s"<>]+',' '.join(str(row.get(k) or '') for k in ('doi','url','pdf_url')),re.I)
    if doi:return 'doi:'+doi.group().lower().rstrip('.,;)')
    url=canonical_url_key(row.get('canonical_url') or row.get('url') or row.get('pdf_url'))
    if url:return 'url:'+url
    return 'hash:'+digest({k:row.get(k) for k in ('title','medium','published_date','text_clean','pdf_text_clean')})

def validate_record(row):
    if not isinstance(row,dict):raise ValueError('Record must be an object')
    if row.get('record_schema_version') != SCHEMA_VERSION:raise ValueError('Unsupported record schema')
    for field in ('document_id','version_id','retrieval_id'):
        if not isinstance(row.get(field),str) or not row[field]:raise ValueError('Missing identifier: '+field)
    if row['selection']['state'] not in SELECTION_STATES:raise ValueError('Invalid selection state')
    if row['selection']['state'] in {'included','excluded'} and not all(row['selection'].get(k) for k in ('reason','evidence','reviewer')):
        raise ValueError('Included/excluded selection requires reason, evidence and reviewer')
    author=row['record_information']['author']
    if author.get('state')=='explicit' and (not isinstance(author.get('value'),list) or not all(isinstance(v,str) for v in author['value'])):raise ValueError('Explicit authors must be a list of names')
    for field in ('claims','versions','retrievals','record_history'):
        if not isinstance(row.get(field),list):raise ValueError(field+' must be a list')
    return row

def upgrade_record(row):
    row=copy.deepcopy(row)
    if row.get('record_schema_version') not in {None,1,2}:raise ValueError('Cannot migrate an unknown future schema')
    old_version=row.get('version_id')
    info=row['record_information']
    for field,c in info.items():
        c.setdefault('provenance',{'source_url':row.get('url'),'source_api':row.get('source_api'),
                    'observed_at':row.get('fetched_at'),'location':c.get('evidence') or None,
                    'location_precision':'legacy_reference' if c.get('method')=='legacy_import' else 'extraction_reference'})
    text=str(info['text'].get('value') or '')
    notes=' '.join(str(n) for n in row.get('cleaning_notes') or [])
    row['content_kind'] = 'title' if text.strip()==str(row.get('title') or '').strip() or 'title_only' in notes else 'abstract' if 'abstract' in notes else 'full_text' if info['text'].get('coverage')=='full' else 'fragment' if text else 'none'
    version_id=digest({'title':row.get('title'),'information':{k:{f:v for f,v in c.items() if f!='provenance'} for k,c in info.items() if k!='consultation_date'},'content_kind':row['content_kind']})
    row.setdefault('record_history',[])
    if old_version and old_version!=version_id:
        event={'event':'record_version_changed','from_version':old_version,'to_version':version_id,'observed_at':row.get('fetched_at')}
        if event not in row['record_history']:row['record_history'].append(event)
        reviewed=[c for c in row.get('claims') or [] if c.get('review_status')=='validated']
        if reviewed:row['record_history'].append({'event':'review_invalidated','version_id':old_version,'claims':copy.deepcopy(reviewed)})
        for c in row.get('claims') or []:
            if c.get('review_status')=='validated':c['review_status']='needs_review'
        for key in ('reviewed_narrative','reviewed_reception'):
            if row.get(key):row[key]['review_status']='needs_review'
        row['reviewed_concepts']=[]
        if row.get('selection',{}).get('state') in {'included','excluded'}:
            row['record_history'].append({'event':'selection_invalidated','previous_selection':copy.deepcopy(row['selection'])})
            row['selection']={**row['selection'],'state':'pending','reason':'record_changed_requires_review'}
    row['version_id']=version_id
    row['canonical_document_id']=digest(identity_key(row))
    row['retrieval_id']=digest({'document':row['canonical_document_id'],'version':version_id,'source_api':row.get('source_api'),'url':row.get('url'),'query':row.get('query'),'fetched_at':row.get('fetched_at')})
    retrieval={k:row.get(k) for k in ('retrieval_id','version_id','source_api','url','query','fetched_at','status','error')}
    row.setdefault('retrievals',[])
    if retrieval not in row['retrievals']:row['retrievals'].append(retrieval)
    version={'version_id':version_id,'content_kind':row['content_kind'],'title':row.get('title'),'record_information':copy.deepcopy(info)}
    row.setdefault('versions',[])
    if not any(v['version_id']==version_id for v in row['versions']):row['versions'].append(version)
    legacy=str(row.get('selection_state') or '')
    row.setdefault('selection',{'state':'pending' if 'pending' in legacy or 'metadata_verified' in legacy else 'candidate',
          'reason':'bibliography_verified_content_pending' if 'metadata_verified' in legacy else 'not_reviewed',
          'evidence':None,'reviewer':None,'reviewed_at':None})
    unknown={'value':None,'state':'not_evaluable','evidence':None}
    row.setdefault('geography',{role:copy.deepcopy(unknown) for role in ('subject','publisher','participants')})
    row['dates']={**(row.get('dates') or {}),**{role:copy.deepcopy(info[key]) for role,key in [('publication','publication_date'),('update','update_date'),('consultation','consultation_date')]}}
    for role in ('event','study_period'):row['dates'].setdefault(role,copy.deepcopy(unknown))
    row.setdefault('document_relations',[])
    row.setdefault('stage_states',{'discovery':'completed' if row.get('url') else 'unknown','retrieval':'partial' if text else 'failed' if row.get('status') in {'error','fetch_error'} else 'unknown','extraction':'partial' if text else 'unknown','selection':row['selection']['state'],'review':'pending','analysis':'not_run'})
    row['stage_states']['selection']=row['selection']['state']
    row['record_schema_version']=SCHEMA_VERSION
    return validate_record(row)
