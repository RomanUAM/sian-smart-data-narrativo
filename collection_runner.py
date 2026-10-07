"""Run a recoverable collection without a browser session: python -m collection_runner PATH."""
import dataclasses
import inspect
import json
import os
import sys
import traceback
from pathlib import Path
from collection_jobs import Job
from process_lock import worker_lock
from corpus_storage import atomic_json
from historical_sources import sitemap_page

def execute(job, crawler=None):
    from news_spider import crawl_news, request_html, robots_allowed
    crawler=crawler or crawl_news
    with worker_lock(job.root/'worker.lock'):
        os.environ['SIAN_CACHE_DIR']=str(job.root/'cache')
        os.environ['SIAN_SOURCE_STATE']=str(job.db)
        job.set('task_deferred',False)
        job.set('status','running');job.log('Coordinador iniciado; estado y registros transaccionales.')
        with job.connect() as c:c.execute('UPDATE tasks SET status="pending" WHERE status="running"')
        try:
            with job.connect() as c:tasks=c.execute('SELECT id,config FROM tasks WHERE status IN ("pending","deferred","failed") ORDER BY id').fetchall()
            for task_id,raw in tasks:
                if job.get('pause',False):break
                _,coverage=job.export()
                if coverage['target_met']:break
                config=json.loads(raw);year=config['start_year']
                annual={r['year']:r for r in coverage['annual']}
                if config['start_year']==config['end_year'] and annual.get(year,{}).get('gap')==0:
                    with job.connect() as c:c.execute('UPDATE tasks SET status="quota_met" WHERE id=?',(task_id,))
                    continue
                with job.connect() as c:c.execute('UPDATE tasks SET status="running",error=NULL WHERE id=?',(task_id,))
                job.log(f'Tarea {task_id}: {year} · {config.get("source_collection",config.get("kind"))} · {config["query"]}')
                try:
                    job.set('task_deferred',False)
                    if config.get('kind')=='seeds':
                        seeds=[]
                        payload=job.get('seed_payload',{})
                        for path in config['seed_files']:seeds.extend(payload.get(path,[]))
                        atomic_json(job.root/'task_seeds.json',seeds);config['seed_url_file']=str(job.root/'task_seeds.json')
                    if config.get('kind')=='sitemap':
                        def fetch(url):
                            allowed,_=robots_allowed(url)
                            if not allowed:raise ValueError('Robots no permite acceso.')
                            return request_html(url)
                        key=f'sitemap_{task_id}'
                        terms=job.get('config').get('topic_terms') or [config['query']]
                        prior=job.get(key,{})
                        state=prior if prior.get('batch_pending') else sitemap_page(config['sitemap'],prior,terms,fetch,max_maps=5,max_urls=1000)
                        state['batch_pending']=True
                        job.set(key,state)
                        seeds=[{'url':u,'source_api':'sitemap','publishedDate':'','discovery_method':'sitemap','infer_source_type':True} for u in state['batch']]
                        atomic_json(job.root/'task_seeds.json',seeds);config['seed_url_file']=str(job.root/'task_seeds.json')
                        job.log(f'Sitemap: {len(seeds)} URLs; completo={state["discovery_complete"]}; errores={len(state["errors"])}.')
                    config.update(output_dir=str(job.root/'tasks'/str(task_id)),max_records_per_source_type_year=0,target_min_per_source_type_year=0,required_source_types=[])
                    kwargs={k:v for k,v in config.items() if k in inspect.signature(crawl_news).parameters}
                    kwargs.update(progress=job.log,stop_requested=lambda:job.get('pause',False),on_record=job.ingest)
                    results=crawler(**kwargs)
                    for row in results:job.ingest(dataclasses.asdict(row) if dataclasses.is_dataclass(row) else row)
                    deferred=job.get('task_deferred',False);job.set('task_deferred',False)
                    status='pending' if job.get('pause',False) else ('deferred' if deferred else 'completed')
                    if config.get('kind')=='sitemap':
                        state['batch_pending']=bool(job.get('pause',False));job.set(key,state)
                        if state['bounded'] and status=='completed':status='deferred'
                    with job.connect() as c:c.execute('UPDATE tasks SET status=? WHERE id=?',(status,task_id))
                except Exception as exc:
                    with job.connect() as c:c.execute('UPDATE tasks SET status="failed",error=? WHERE id=?',(type(exc).__name__+': '+str(exc),task_id))
                    job.log(f'Tarea {task_id} falló: {type(exc).__name__}: {exc}')
                job.export()
                from job_backup import checkpoint
                checkpoint(job)
            _,coverage=job.export()
            with job.connect() as c:remaining=c.execute('SELECT count(*) FROM tasks WHERE status IN ("pending","deferred","failed")').fetchone()[0]
            job.set('status','paused' if job.get('pause',False) else ('target_met' if coverage['target_met'] else ('waiting_sources' if remaining else 'finished_with_gaps')))
        except BaseException as exc:
            job.set('status','interrupted');job.log(type(exc).__name__+': '+str(exc));raise
        finally:
            job.export()
            from job_backup import checkpoint
            checkpoint(job)

def main():
    if len(sys.argv)!=2:raise SystemExit('Uso: python -m collection_runner CARPETA_JOB')
    execute(Job(sys.argv[1]))
if __name__=='__main__':main()
