import copy
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from corpus_contract import canonical_url_key, identity_key, merge_rows
from evidence_model import normalize_record, cell
from narrative_analysis import load_records_from_path
from news_spider import parse_public_forum_feed, parse_seed_date, load_seed_url_articles_from_path, crawl_news, save_outputs
from reclean_outputs import reclean_record
from scripts.merge_source_bases import merge_sources
from scripts.run_query_plan import merge_rows as replay_merge


class PipelineContractTests(unittest.TestCase):
    def record(self, **kw):
        return dict(url='https://site.test/article?id=1', title='Tatuajes en México', medium='Diario',
                    text_clean='Una narración sobre tatuajes en México.', status='ok_partial',
                    source_api='rss', published_date='2020-05-02', fetched_at='2026-10-06', **kw)

    def test_query_identity_preserves_distinct_redalyc_articles(self):
        a='https://www.redalyc.org/articulo.oa?id=123&utm_source=test'
        b='https://redalyc.org/articulo.oa?id=456'
        self.assertNotEqual(canonical_url_key(a),canonical_url_key(b))
        self.assertEqual(canonical_url_key(a),canonical_url_key('http://redalyc.org/articulo.oa?id=123#top'))
        self.assertNotEqual(canonical_url_key('https://a.test/Article'),canonical_url_key('https://a.test/article'))

    def test_same_title_different_urls_are_not_removed(self):
        a=self.record(); b=copy.deepcopy(a); b['url']='https://site.test/article?id=2'
        self.assertEqual(len(merge_rows([a,b])),2)

    def test_explicit_doi_unifies_index_and_publisher(self):
        a=self.record(doi='10.1234/example'); b=copy.deepcopy(a); b['url']='https://doi.org/10.1234/example'
        self.assertEqual(identity_key(a),identity_key(b))
        self.assertEqual(len(merge_rows([a,b])),1)

    def test_merge_preserves_conflict_text_and_both_provenances(self):
        a=self.record(authors=['A']); a['source_collection']='news'
        b=self.record(authors=['B']); b.update(text_clean='Un texto más completo sobre los tatuajes en México y su identidad.', source_collection='articles', fetched_at='2026-10-06T12:00:00+00:00')
        orig=copy.deepcopy(a)
        row=merge_rows([a,b])[0]
        self.assertEqual(a,orig)
        self.assertEqual(row['record_information']['author']['state'],'conflicting')
        self.assertEqual(row['record_information']['text']['value'], b['text_clean'])
        self.assertEqual(len(row['retrieval_provenance']),2)
        self.assertEqual(row['record_information']['consultation_date']['state'],'explicit')
        self.assertEqual(merge_rows([row,b]),merge_rows([row,b,b]))

    def test_more_precise_date_not_false_conflict(self):
        a=self.record(); a['published_date']='2020'
        b=self.record()
        row=merge_rows([a,b])[0]
        self.assertEqual(row['record_information']['publication_date']['value'],'2020-05-02')
        self.assertEqual(row['year'],2020)

    def test_atom_published_and_updated_distinct(self):
        xml='''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Tatuajes</title><link href="https://reddit.com/r/mexico/x"/><published>2020-04-01T12:00:00Z</published><updated>2024-04-01T12:00:00Z</updated><author><name>usuario</name></author><content>Opinión</content></entry></feed>'''
        rows=parse_public_forum_feed(xml,dt.datetime(2020,1,1),dt.datetime(2020,12,31),10)
        self.assertEqual(len(rows),1)
        self.assertTrue(rows[0]['publishedDate'].startswith('2020-04-01'))
        self.assertTrue(rows[0]['updated_date'].startswith('2024-04-01'))
        self.assertEqual(rows[0]['authors'],['usuario'])
        self.assertEqual(parse_public_forum_feed(xml.replace('<published>2020-04-01T12:00:00Z</published>',''),dt.datetime(2020,1,1),dt.datetime(2026,12,31),10),[])

    def test_iso_and_rfc_dates_share_utc(self):
        for value in ('2020-01-02','2020-01-02T02:00:00+02:00','Thu, 02 Jan 2020 00:00:00 GMT'):
            self.assertEqual(parse_seed_date(value),dt.datetime(2020,1,2,tzinfo=dt.UTC))

    def test_seed_missing_metadata_kept_without_fabrication(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'seeds.json';p.write_text(json.dumps([{'url':'https://x.test/1','year':2020},{'url':'https://x.test/2'}]))
            rows=load_seed_url_articles_from_path(p)
            self.assertEqual(len(rows),2)
            self.assertEqual(rows[0]['publishedDate'],'2020')
            self.assertEqual(rows[0]['sourceCountry'],'')
            self.assertEqual(rows[1]['publishedDate'],'')

    def test_cleaning_refreshes_evidence_and_preserves_metadata(self):
        row=normalize_record(self.record())
        row['record_information']['text']=cell('Texto obsoleto','explicit')
        cleaned=reclean_record(row)
        self.assertEqual(cleaned['record_information']['text']['value'],cleaned['text_clean'])
        self.assertEqual(cleaned['record_information']['publication_date'],row['record_information']['publication_date'])

    def test_cli_merge_loader_replay_same_records(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); rows=[self.record(),self.record(authors=['A'])]
            for source,row in zip(('news','articles'),rows):
                p=root/'by_source'/source/'news_records.json';p.parent.mkdir(parents=True);p.write_text(json.dumps([row]))
            merged, report=merge_sources(root,['news','articles'])
            p=root/'news_records_merged.json';p.write_text(json.dumps(merged))
            self.assertEqual(load_records_from_path(root),merged)
            self.assertEqual(len(replay_merge(rows)),len(merged))
            self.assertEqual(report['duplicates'],1)

    def test_save_outputs_excludes_manifests(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'run_manifest.json').write_text('{"system":"SIAN"}')
            save_outputs(root,[],scan_existing=True)
            self.assertEqual(json.loads((root/'news_records.json').read_text()),[])

    def test_future_only_crawl_makes_no_requests(self):
        with tempfile.TemporaryDirectory() as d, patch('news_spider.search_google_news_rss') as request:
            crawl_news(query='tatuaje',start_year=2090,end_year=2090,source_modes=['google_news_rss'],output_dir=Path(d),search_delay_seconds=0,delay_seconds=0)
            request.assert_not_called()

    def test_zero_weight_edges_remain_zero_and_invalid_rejected(self):
        from narrative_analysis import _cover_problem_data, _evaluate_cover_solution
        graph={'nodes':[{'id':'a','score':1},{'id':'b','score':1}], 'edges':[{'source':'a','target':'b','weight':0}]}
        problem=_cover_problem_data(graph)
        result=_evaluate_cover_solution(['a'],problem)
        self.assertEqual(problem['total_edge_weight'],0)
        self.assertEqual(result['removed_edge_weight'],0)
        from narrative_analysis import greedy_weighted_node_cover, genetic_weighted_node_cover, annealing_weighted_node_cover, musical_composition_weighted_node_cover
        for solve in (greedy_weighted_node_cover, genetic_weighted_node_cover, annealing_weighted_node_cover, musical_composition_weighted_node_cover):
            solved=solve(graph,max_nodes=1)
            self.assertEqual(solved['stats']['removed_edge_weight_ratio'],0)

        graph['edges'][0]['weight']=-1
        with self.assertRaises(ValueError): _cover_problem_data(graph)

    def test_empty_silence_is_unknown_not_total_absence(self):
        from structural_narrative import silence_alerts
        row=silence_alerts([],['identidad'])[0]
        self.assertIsNone(row['missing_share'])
        self.assertFalse(row['alert'])
        self.assertNotEqual(row['relation_type'],'IGNORA_A')

    def test_undated_frames_do_not_establish_temporal_order(self):
        from structural_narrative import temporal_frame_deltas
        frames=[{'frame_id':'u','year':None,'medium':'Diario'},{'frame_id':'a','year':2020,'medium':'Diario'},{'frame_id':'b','year':2020,'medium':'Diario'}]
        result=temporal_frame_deltas(frames)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['delta_type'],'baseline')

    def test_relational_export_roundtrip_and_empty_models(self):
        import sqlite3
        from scripts.export_corpus_database import export_database
        with tempfile.TemporaryDirectory() as d:
            summary=export_database([self.record(),self.record(authors=['A'])],d)
            self.assertEqual(summary['records'],1)
            connection=sqlite3.connect(Path(d)/'tatuaje_2016_2026.sqlite')
            self.assertEqual(connection.execute('SELECT count(*) FROM documents').fetchone()[0],1)
            self.assertEqual(connection.execute('SELECT count(*) FROM information').fetchone()[0],6)
            self.assertEqual(connection.execute('SELECT count(*) FROM actor_concept_stance').fetchone()[0],0)
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertEqual(len(load_records_from_path(Path(d)/'news_records.json')),1)
            connection.close()

if __name__=='__main__': unittest.main()
