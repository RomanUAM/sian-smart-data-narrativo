"""Bounded retry and disk cache around native SIAN public-source readers."""
from __future__ import annotations
import datetime as dt
import json
import time
import urllib.error
from pathlib import Path
from corpus_storage import atomic_json
from record_schema import digest

ENGINES={'google_news_rss':'search_google_news_rss','reddit_rss':'search_reddit_rss','openalex':'search_openalex_year','crossref':'search_crossref_year','redalyc':'search_redalyc_year'}

class SourceAdapter:
    def __init__(self,cache_dir,ttl_seconds=3600,max_attempts=2):
        self.cache_dir=Path(cache_dir);self.ttl=max(0,ttl_seconds);self.max_attempts=max(1,min(3,max_attempts))
    def query(self,engine,parameters,reader=None,raise_errors=False):
        if engine not in ENGINES:raise ValueError('Unsupported engine: '+engine)
        key=digest({'engine':engine,'parameters':parameters,'adapter_version':2})
        path=self.cache_dir/(key+'.json')
        if path.exists():
            try:
                saved=json.loads(path.read_text())
                if time.time()-saved['cached_at']<self.ttl and saved['status'] in {'completed','empty'}:
                    return {**saved,'cache_hit':True,'attempts_this_call':0}
            except (ValueError,KeyError,OSError):pass
        if reader is None:
            import news_spider
            reader=getattr(news_spider,ENGINES[engine])
            reader=getattr(reader,'__wrapped__',reader)
        from source_control import remaining, cooldown
        if remaining(engine)>0:
            from news_spider import _mark_task_deferred
            _mark_task_deferred()
            raise TimeoutError(f"{engine}: deferred_shared_cooldown")
        attempts=[]; result=None; last_error=None
        for attempt in range(1,self.max_attempts+1):
            try:
                value=reader(**parameters)
                rows,diagnostics=value if isinstance(value,tuple) else (value,{})
                if not isinstance(rows,list) or not all(isinstance(r,dict) for r in rows):raise ValueError('Reader returned an invalid record list')
                result={'status':'completed' if rows else 'empty','rows':rows,'diagnostics':diagnostics};attempts.append({'attempt':attempt,'status':'completed'});break
            except Exception as exc:
                last_error=exc
                attempts.append({'attempt':attempt,'status':'failed','error':type(exc).__name__+': '+str(exc)})
                if isinstance(exc,urllib.error.HTTPError) and exc.code==429:
                    cooldown(engine,exc.headers.get('Retry-After') if exc.headers else None)
                    from news_spider import _mark_task_deferred
                    _mark_task_deferred()
                    break
                transient=isinstance(exc,(TimeoutError,urllib.error.URLError)) and (not isinstance(exc,urllib.error.HTTPError) or exc.code in {429,500,502,503,504})
                if not transient or attempt==self.max_attempts:break
                time.sleep(min(2,attempt))
        if result is None:result={'status':'failed','rows':[],'diagnostics':{},'error':attempts[-1]['error']}
        result.update(engine=engine,query_id=key,parameters=json.loads(json.dumps(parameters,default=str)),attempts=attempts,
                      attempts_this_call=len(attempts),cache_hit=False,cached_at=time.time(),consulted_at=dt.datetime.now(dt.UTC).isoformat())
        atomic_json(path,result)
        if result["status"]=="failed" and raise_errors:raise last_error
        return result

def cached_source(engine):
    """Decorate a native reader without changing its public return type."""
    import functools
    import inspect
    import os
    def decorate(reader):
        signature=inspect.signature(reader)
        @functools.wraps(reader)
        def wrapped(*args,**kwargs):
            bound=signature.bind(*args,**kwargs);bound.apply_defaults()
            cache=SourceAdapter(os.environ.get('SIAN_CACHE_DIR','.sian_cache'),ttl_seconds=float(os.environ.get('SIAN_CACHE_TTL','3600')))
            result=cache.query(engine,dict(bound.arguments),reader=reader,raise_errors=True)
            return (result['rows'],result['diagnostics']) if engine=='google_news_rss' else result['rows']
        return wrapped
    return decorate
