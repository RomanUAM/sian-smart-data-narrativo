"""Resumable stages for existing corpora; never silently retrieves missing evidence."""
from __future__ import annotations
import copy
import json
from collections import Counter
from pathlib import Path
from corpus_storage import atomic_json, CorpusStore
from record_schema import digest, STAGES, validate_record
from corpus_contract import is_record, merge_rows
from evidence_model import normalize_record, coverage_report

class PipelineRunner:
    def __init__(self,output,config=None):
        self.output=Path(output);self.output.mkdir(parents=True,exist_ok=True)
        self.code_signature=digest({name:digest(Path(__file__).with_name(name).read_text()) for name in ("record_schema.py","evidence_model.py","corpus_contract.py","corpus_pipeline.py")})
        self.config=config or {};self.path=self.output/'pipeline_manifest.json'
        self.manifest=json.loads(self.path.read_text()) if self.path.exists() else {'pipeline_version':2,'stages':{}}
    def stage(self,name,payload,operation):
        if name not in STAGES:raise ValueError('Invalid pipeline stage')
        key=digest({'stage':name,'input':payload,'configuration':self.config,'pipeline_version':2,'code_signature':self.code_signature})
        path=self.output/'checkpoints'/f'{name}_{key}.json';previous=self.manifest['stages'].get(name,{})
        if previous.get('input_hash')==key and previous.get('status')=='completed' and path.exists():
            try:
                saved=json.loads(path.read_text())
                if digest(saved)==previous['output_hash']:
                    self.manifest['stages'][name]['resumed']=True;atomic_json(self.path,self.manifest);return saved
            except (OSError,ValueError,KeyError):pass
        self.manifest['status']='running';self.manifest['stages'][name]={'status':'running','input_hash':key,'resumed':False};atomic_json(self.path,self.manifest)
        try:
            result=operation(payload)
            atomic_json(path,result)
            self.manifest['stages'][name].update(status='completed',output_hash=digest(result),checkpoint=str(path))
            atomic_json(self.path,self.manifest)
            return result
        except Exception as exc:
            self.manifest['status']='failed';self.manifest['stages'][name].update(status='failed',error=type(exc).__name__+': '+str(exc));atomic_json(self.path,self.manifest);raise

def apply_selection_reviews(rows,reviews):
    indexed={r['document_id']:r for r in copy.deepcopy(rows)}
    for review in reviews:
        if review.get('document_id') not in indexed:raise ValueError('Unknown document for selection review')
        row=indexed[review['document_id']]
        if review.get('version_id')!=row['version_id']:raise ValueError('Selection review is for another document version')
        selection={k:review.get(k) for k in ('state','reason','evidence','reviewer','reviewed_at')}
        row['selection']=selection;row['stage_states']['selection']=selection['state'];validate_record(row)
        row['record_history'].append({'event':'selection_review','version_id':row['version_id'],'selection':selection})
    return list(indexed.values())

def process_corpus(raw_rows,output,selection_reviews=None):
    runner=PipelineRunner(output,{'selection_reviews':selection_reviews or []})
    def discover(items):
        valid=[];quarantine=[]
        for index,raw in enumerate(items):
            try:
                if not is_record(raw):raise ValueError('Not a corpus record')
                valid.append(normalize_record(raw))
            except (ValueError,TypeError,AttributeError,KeyError) as exc:quarantine.append({'index':index,'reason':str(exc),'raw_record':raw})
        return {'records':valid,'quarantine':quarantine}
    discovered=runner.stage('discovery',raw_rows,discover)
    # These two stages record existing retrieval/extraction availability; no fabricated network success.
    retrieved=runner.stage('retrieval',discovered['records'],lambda rows:rows)
    extracted=runner.stage('extraction',retrieved,merge_rows)
    selected=runner.stage('selection',extracted,lambda rows:apply_selection_reviews(rows,selection_reviews or []))
    reviewed=runner.stage('review',selected,lambda rows:rows)
    summary=runner.stage('analysis',reviewed,coverage_report)
    store=CorpusStore(runner.output/'corpus_registry.sqlite')
    try:store.put(reviewed)
    finally:store.close()
    atomic_json(runner.output/'news_records.json',reviewed)
    atomic_json(runner.output/'quarantine.json',discovered['quarantine'])
    usable=[r for r in reviewed if r['content_kind'] in {'fragment','abstract','full_text'}]
    report={'records':len(reviewed),'quarantined':len(discovered['quarantine']),
            'selection':dict(Counter(r['selection']['state'] for r in reviewed)),
            'content_kinds':dict(Counter(r['content_kind'] for r in reviewed)),
            'retrieval_states':dict(Counter(r['stage_states']['retrieval'] for r in reviewed)),
            'evidence_documents_beyond_titles':len(usable),'search_coverage':None,
            'search_coverage_note':'Requires query logs and a defined search denominator; record counts alone are insufficient',
            'analysis_eligibility':summary['analyses']}
    atomic_json(runner.output/'pipeline_report.json',report)
    runner.manifest['status']='completed';runner.manifest['records']=len(reviewed);atomic_json(runner.path,runner.manifest)
    return reviewed,report
