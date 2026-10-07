import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from evidence_model import normalize_record,claim_is_valid
from record_schema import validate_record
from corpus_contract import merge_rows
from corpus_pipeline import PipelineRunner,process_corpus,apply_selection_reviews
from corpus_storage import atomic_json,CorpusStore
from source_adapters import SourceAdapter

class RegistryPipelineTests(unittest.TestCase):
    def row(self):return dict(url='https://a.test/article',title='Tatuaje',text_clean='El tatuaje expresa identidad.',status='ok_partial',source_api='rss',published_date='2020',fetched_at='2026-10-06',medium='Diario')
    def test_migration_is_idempotent_and_preserves_old_id(self):
        raw=self.row();raw['document_id']='historical_id';first=normalize_record(raw)
        self.assertEqual(first,normalize_record(first));self.assertEqual(first['document_id'],'historical_id')
        self.assertEqual(first['record_schema_version'],2)
        self.assertEqual(len(first['retrievals']),1)
    def test_new_consultation_is_same_version_new_retrieval(self):
        a=normalize_record(self.row());b=self.row();b['fetched_at']='2026-10-07';b=normalize_record(b)
        self.assertEqual(a['version_id'],b['version_id']);self.assertNotEqual(a['retrieval_id'],b['retrieval_id'])
        row=merge_rows([a,b])[0];self.assertEqual(len(row['retrievals']),2)
    def test_changed_text_invalidates_reviews_but_keeps_history(self):
        row=normalize_record(self.row());row['claims']=[{'review_status':'validated','quote':'expresa identidad','concept':'identidad','statement':'Expresión'}]
        self.assertTrue(claim_is_valid(row['claims'][0],row))
        row['record_information']['text']['value']='Un argumento distinto.'
        updated=normalize_record(row)
        self.assertEqual(updated['claims'][0]['review_status'],'needs_review')
        self.assertTrue(any(e['event']=='review_invalidated' for e in updated['record_history']))
        self.assertEqual(len(updated['versions']),2)
    def test_geography_and_event_date_not_imputed(self):
        row=normalize_record(self.row());self.assertIsNone(row['geography']['subject']['value']);self.assertIsNone(row['dates']['event']['value'])
    def test_selection_requires_review_of_current_version(self):
        row=normalize_record(self.row());review={'document_id':row['document_id'],'version_id':row['version_id'],'state':'included'}
        with self.assertRaises(ValueError):apply_selection_reviews([row],[review])
        review.update(reason='pertinente',reviewer='Revisor',evidence='Fragmento sobre México',reviewed_at='2026-10-06')
        self.assertEqual(apply_selection_reviews([row],[review])[0]['selection']['state'],'included')
        review['version_id']='wrong'
        with self.assertRaises(ValueError):apply_selection_reviews([row],[review])
    def test_failed_stage_can_resume_without_repeating_completed(self):
        with tempfile.TemporaryDirectory() as d:
            run=PipelineRunner(d);calls=[]
            run.stage('discovery',[1],lambda x:calls.append('discovery') or x)
            with self.assertRaises(ValueError):run.stage('retrieval',[1],lambda x:(_ for _ in ()).throw(ValueError('failure')))
            next_run=PipelineRunner(d);next_run.stage('discovery',[1],lambda x:calls.append('repeated') or x)
            next_run.stage('retrieval',[1],lambda x:x)
            self.assertEqual(calls,['discovery']);self.assertTrue(next_run.manifest['stages']['discovery']['resumed'])
    def test_corrupt_checkpoint_is_recomputed(self):
        with tempfile.TemporaryDirectory() as d:
            run=PipelineRunner(d);run.stage('discovery',[1],lambda x:x)
            Path(run.manifest['stages']['discovery']['checkpoint']).write_text('[99]')
            self.assertEqual(run.stage('discovery',[1],lambda x:x),[1])
    def test_cache_distinguishes_empty_failure_and_hit(self):
        with tempfile.TemporaryDirectory() as d:
            adapter=SourceAdapter(d);calls=[]
            reader=lambda **kw:calls.append(1) or []
            self.assertEqual(adapter.query('crossref',{'query':'x'},reader)['status'],'empty')
            self.assertTrue(adapter.query('crossref',{'query':'x'},reader)['cache_hit']);self.assertEqual(len(calls),1)
            result=adapter.query('crossref',{'query':'bad'},lambda **kw:(_ for _ in ()).throw(ValueError('bad format')))
            self.assertEqual(result['status'],'failed');self.assertEqual(len(result['attempts']),1)
    def test_atomic_failure_keeps_previous_file(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'records.json';atomic_json(path,[1])
            with patch('corpus_storage.os.replace',side_effect=OSError('disk failure')):
                with self.assertRaises(OSError):atomic_json(path,[2])
            self.assertEqual(json.loads(path.read_text()),[1])
    def test_pipeline_quarantine_registry_and_resume(self):
        with tempfile.TemporaryDirectory() as d:
            rows,report=process_corpus([self.row(),{'system':'manifest'}],d)
            self.assertEqual(report['records'],1);self.assertEqual(report['quarantined'],1)
            again,_=process_corpus([self.row(),{'system':'manifest'}],d);self.assertEqual(rows,again)
            manifest=json.loads((Path(d)/'pipeline_manifest.json').read_text());self.assertTrue(all(v['resumed'] for v in manifest['stages'].values()))
            c=sqlite3.connect(Path(d)/'corpus_registry.sqlite');self.assertEqual(c.execute('select count(*) from retrievals').fetchone()[0],1);self.assertEqual(c.execute('pragma foreign_key_check').fetchall(),[]);c.close()
    def test_retries_bounded_and_failed_queries_not_cached_as_empty(self):
        with tempfile.TemporaryDirectory() as d,patch('source_adapters.time.sleep'):
            adapter=SourceAdapter(d,max_attempts=2);calls=[]
            def fail(**kw):calls.append(1);raise TimeoutError('timeout')
            result=adapter.query('crossref',{},fail)
            self.assertEqual(result['status'],'failed');self.assertEqual(len(calls),2)
            adapter.query('crossref',{},fail);self.assertEqual(len(calls),4)
    def test_registry_rollback_on_invalid_record(self):
        with tempfile.TemporaryDirectory() as d:
            store=CorpusStore(Path(d)/'registry.sqlite');invalid=normalize_record(self.row());invalid['version_id']=None
            with self.assertRaises(ValueError):store.put([normalize_record(self.row()),invalid])
            self.assertEqual(store.connection.execute('select count(*) from documents').fetchone()[0],0);store.close()
    def test_saved_real_atom_fixture(self):
        import datetime as dt
        from news_spider import parse_public_forum_feed
        path=Path(__file__).parent/'fixtures/reddit_probe.xml'
        rows=parse_public_forum_feed(path.read_text(),dt.datetime(2016,1,1),dt.datetime(2026,12,31),10)
        self.assertEqual(len(rows),2);self.assertTrue(all(r['publishedDate'] for r in rows))
    def test_excluded_record_is_not_eligible(self):
        from evidence_model import eligibility
        row=normalize_record(self.row());review=dict(document_id=row['document_id'],version_id=row['version_id'],state='excluded',reason='fuera del tema',reviewer='Revisor',evidence='documento sobre otro tema')
        self.assertFalse(eligibility(apply_selection_reviews([row],[review])[0],'thematic')[0])

    def test_future_schema_is_rejected(self):
        raw=self.row();raw['record_schema_version']=99
        with self.assertRaises(ValueError):normalize_record(raw)
    def test_published_json_schema_matches_migration(self):
        import jsonschema
        schema=json.loads((Path(__file__).parents[1]/'examples/record_schema_v2.schema.json').read_text())
        jsonschema.validate(normalize_record(self.row()),schema)

if __name__=='__main__':unittest.main()
