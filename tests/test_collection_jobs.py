import copy
import datetime as dt
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch
from collection_jobs import Job
from collection_policy import assess
from collection_runner import execute
from historical_sources import plan, sitemap_page
from news_spider import search_gdelt_with_status

class CollectionTests(unittest.TestCase):
    def config(self,**kw):return dict(query='tatuaje',start_year=2016,end_year=2017,min_text_chars=300,target_total_per_year=2,classification_rubrics={'identidad':['identidad'],'salud':['salud']},**kw)
    def row(self,url='https://example.org/1',date='2016-05-01',text=None,**kw):
        return dict(url=url,title='Tatuaje e identidad',text_clean=text or 'Tatuaje e identidad y salud en una comunidad. '*15,status='ok',source_api='rss',published_date=date,published_date_verified=True,**kw)
    def test_quota_uses_verified_publication_not_search_year(self):
        rows=[self.row(year=2025),self.row(url='https://example.org/missing',date='',year=2016)]
        records,report=assess(rows,self.config())
        self.assertEqual(report['annual'][0]['selected'],1)
        missing=next(r for r in records if r['url'].endswith('missing'))
        self.assertIsNone(missing['year']);self.assertFalse(missing['collection_assessment']['eligible'])
    def test_partial_short_future_offtopic_and_duplicate_not_counted(self):
        rows=[self.row(),self.row(url='https://example.org/copy'),self.row(url='https://example.org/short',text='tatuaje'),self.row(url='https://example.org/future',date='2027-01-01'),self.row(url='https://example.org/offtopic',text='Café y chocolate. '*40,title2='x')]
        rows[-1]['title']='Café'
        records,report=assess(rows,self.config())
        self.assertEqual(report['annual'][0]['selected'],1)
        self.assertEqual(report['reasons']['duplicate_content'],1)
        self.assertEqual(report['reasons']['insufficient_text'],1)
        self.assertEqual(report['reasons']['topic_not_verified'],1)
        self.assertEqual(report['by_rubric'][0]['count'],1)
    def test_quota_total_across_sources_and_preserves_overflow(self):
        rows=[self.row(url=f'https://example.org/{i}',text=f'Tatuaje {i}. '+'Identidad y salud '*30,source_type=s) for i,s in enumerate(['news','forum','scientific_article'])]
        records,report=assess(rows,self.config())
        self.assertEqual(len(records),3);self.assertEqual(report['annual'][0]['selected'],2)
        self.assertEqual(report['reasons']['beyond_target'],1)
    def test_plan_historical_capabilities_cutoff_and_academic_once(self):
        config=self.config(sequential_source_layers=[{'source_collection':'mixed','source_modes':['gdelt_news','institutional_gdelt','forums','google_news_rss','openalex_oa','crossref']}])
        tasks=plan(config,today=dt.date(2017,3,5))
        self.assertFalse(any(t['start_year']==2016 and 'gdelt_news' in t['source_modes'] for t in tasks))
        self.assertFalse(any(t['start_year']==2017 and (t.get('start_month') or 1)>3 for t in tasks))
        academic=[t for t in tasks if 'openalex_oa' in t['source_modes']]
        self.assertEqual(len(academic),2*3) # query plus two rubric terms per year
        self.assertTrue(all(t['start_month'] is None for t in academic))
    def test_sitemap_lastmod_is_not_publication(self):
        xml='<urlset><url><loc>https://example.org/tatuaje-arte</loc><lastmod>2016-01-01</lastmod></url></urlset>'
        state=sitemap_page('https://example.org/sitemap.xml',{},['tatuaje'],lambda _:xml)
        self.assertEqual(state['urls'],['https://example.org/tatuaje-arte'])
        self.assertNotIn('published_date',state);self.assertTrue(state['discovery_complete'])
    def test_sitemap_cursor_retains_unscanned_maps(self):
        def fetch(url):return '<sitemapindex><sitemap><loc>https://example.org/tatuaje.xml</loc></sitemap></sitemapindex>' if url.endswith('sitemap.xml') else '<urlset><url><loc>https://example.org/tatuaje</loc></url></urlset>'
        state=sitemap_page('https://example.org/sitemap.xml',{},['tatuaje'],fetch,max_maps=1)
        self.assertTrue(state['bounded']);self.assertFalse(state['discovery_complete'])
        state=sitemap_page('https://example.org/sitemap.xml',state,['tatuaje'],fetch,max_maps=1)
        self.assertTrue(state['discovery_complete']);self.assertEqual(len(state['urls']),1)
    def test_pause_backup_restore_and_resume_without_duplicate(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{},clear=False):
            config=self.config();tasks=[{**config,'start_year':2016,'end_year':2016},{**config,'start_year':2017,'end_year':2017}]
            job=Job.create(d,config,tasks)
            def first(**kw):
                kw['on_record'](self.row());job.pause();return []
            execute(job,first)
            self.assertEqual(job.status(),'paused');self.assertEqual(len(job.rows()),1)
            restored=Job.restore(d,job.archive());restored.set('pause',False)
            calls=[]
            def second(**kw):
                calls.append(kw['start_year']);kw['on_record'](self.row(date=str(kw['start_year'])+'-05-01',url='https://example.org/'+str(kw['start_year'])));return []
            execute(restored,second)
            self.assertEqual(calls,[2016,2017]);self.assertEqual(len(restored.rows()),3)
            self.assertEqual(restored.status(),'finished_with_gaps')
            self.assertTrue((restored.root/'coverage.json').exists())
    def test_failed_task_is_retryable_not_reported_as_success(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{},clear=False):
            config=self.config();job=Job.create(d,config,[config])
            def fail(**kw):raise TimeoutError('unavailable')
            execute(job,fail);self.assertEqual(job.status(),'waiting_sources')
            with job.connect() as c:self.assertEqual(c.execute('SELECT status FROM tasks').fetchone()[0],'failed')
            execute(job,lambda **kw:[])
            self.assertEqual(job.status(),'finished_with_gaps')
    def test_shared_gdelt_retry_after_survives_new_invocation(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'SIAN_SOURCE_STATE':str(Path(d)/'state.sqlite3')}):
            start,end=dt.datetime(2020,1,1),dt.datetime(2020,1,31)
            error=urllib.error.HTTPError('https://api.gdeltproject.org',429,'rate limit',{'Retry-After':'120'},None)
            with patch('news_spider.search_gdelt',side_effect=error) as reader:
                self.assertEqual(search_gdelt_with_status('tatuaje',start,end,10)[1],'rate_limited')
                self.assertEqual(search_gdelt_with_status('tatuaje',start+dt.timedelta(days=31),end+dt.timedelta(days=31),10)[1],'rate_limited')
                self.assertEqual(reader.call_count,1)
            from source_control import remaining
            self.assertGreater(remaining('gdelt'),100)
    def test_conjugation_preserves_provenance_without_double_counting(self):
        with tempfile.TemporaryDirectory() as d:
            a=Job.create(d,self.config(),[]);b=Job.create(d,self.config(),[])
            a.ingest(self.row(source_collection='news'))
            b.ingest(self.row(source_collection='articles'))
            merged=Job.conjugate(d,self.config(),[a,b])
            self.assertEqual(len(merged.rows()),1)
            _,coverage=merged.export()
            self.assertEqual(coverage['annual'][0]['selected'],1)
            self.assertEqual(set(merged.rows()[0]['collection_origins']),{a.root.name,b.root.name})
    def test_sitemap_url_budget_can_resume_without_dropping_urls(self):
        xml='<urlset>'+''.join(f'<url><loc>https://example.org/tatuaje/{i}</loc></url>' for i in range(3))+'</urlset>'
        state=sitemap_page('https://example.org/sitemap.xml',{},['tatuaje'],lambda _:xml,max_urls=1)
        self.assertEqual(len(state['batch']),1);self.assertTrue(state['bounded'])
        state=sitemap_page('https://example.org/sitemap.xml',state,['tatuaje'],lambda _:xml,max_urls=1)
        self.assertEqual(len(state['urls']),2);self.assertTrue(state['bounded'])
        state=sitemap_page('https://example.org/sitemap.xml',state,['tatuaje'],lambda _:xml,max_urls=1)
        self.assertEqual(len(state['urls']),3);self.assertTrue(state['discovery_complete'])
    def test_gdelt_2016_never_calls_network(self):
        with patch('news_spider.search_gdelt') as reader:
            self.assertEqual(search_gdelt_with_status('tatuaje',dt.datetime(2016,1,1),dt.datetime(2016,1,31),10)[1],'unsupported_period')
            reader.assert_not_called()

if __name__=='__main__':unittest.main()
