"""Capability-aware planning and bounded sitemap discovery.

Sitemap lastmod is deliberately never promoted to a publication date.
"""
import datetime as dt
import json
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from collection_policy import folded
from corpus_storage import atomic_json

CAPABILITIES = {
    'gdelt_news': {'earliest_year':2017,'historical':True,'date_kind':'observation'},
    'forums': {'earliest_year':2017,'historical':True,'date_kind':'observation'},
    'institutional_gdelt': {'earliest_year':2017,'historical':True,'date_kind':'observation'},
    'google_news_rss': {'earliest_year':None,'historical':'weak','date_kind':'publication'},
    'reddit_rss': {'earliest_year':None,'historical':'weak','date_kind':'publication'},
    'openalex_oa': {'earliest_year':None,'historical':True,'date_kind':'publication'},
    'crossref': {'earliest_year':None,'historical':True,'date_kind':'publication'},
    'redalyc': {'earliest_year':None,'historical':True,'date_kind':'publication'},
    'seed_urls': {'earliest_year':None,'historical':True,'date_kind':'page_metadata'},
    'sitemap': {'earliest_year':None,'historical':'source_dependent','date_kind':'page_metadata'},
}

def plan(config, layers=None, today=None):
    today=today or dt.date.today()
    first,last=int(config['start_year']),min(int(config['end_year']),today.year)
    if first>last:raise ValueError('Intervalo de años inválido.')
    layers=layers or config.get('sequential_source_layers') or [{'source_collection':'mixed','source_modes':config.get('source_modes') or ['gdelt_news','google_news_rss','openalex_oa','crossref']}]
    groups=list((config.get('classification_rubrics') or {}).values())
    balanced=[group[index] for index in range(max([len(g) for g in groups] or [0])) for group in groups if index<len(group)]
    terms=list(dict.fromkeys([config['query'],*balanced,*config.get('query_variants',[])]))
    terms=terms[:max(1,int(config.get('sequential_synonym_limit',8)))]
    if config.get('sequential_randomize'):
        import random
        exploratory=terms[1:];random.Random(config.get('sequential_seed') or 2026).shuffle(exploratory);terms=terms[:1]+exploratory
    tasks=[]
    seeds=list(dict.fromkeys(p for p in [config.get('seed_url_file'),*config.get('seed_url_files_by_source',{}).values()] if p))
    if seeds:tasks.append({**config,'kind':'seeds','seed_files':seeds,'source_modes':['seed_urls'],'start_year':first,'end_year':last})
    for sitemap in config.get('historical_sitemaps',[]):tasks.append({**config,'kind':'sitemap','sitemap':sitemap,'source_modes':['seed_urls'],'start_year':first,'end_year':last})
    # Sweep months across years and layers, rather than spending hours on the first year.
    for month in range(1,13):
        for year in range(first,last+1):
            if year==today.year and month>today.month:continue
            for layer in layers:
                source=layer.get('source_collection','mixed')
                modes=layer.get('source_modes',[])
                modes=[m for m in modes if not CAPABILITIES.get(m,{}).get('earliest_year') or year>=CAPABILITIES[m]['earliest_year']]
                academic=[m for m in modes if m in {'openalex_oa','crossref','redalyc'}]
                public=[m for m in modes if m not in academic]
                if month==1 and academic:
                    for term in terms:
                        tasks.append({**config,**layer,'kind':'index','query':term,'query_variants':[],'start_year':year,'end_year':year,'start_month':None,'end_month':None,'source_modes':academic,'seed_url_file':''})
                if public:
                    term=terms[(month-1)%len(terms)]
                    variants=[terms[(month-1+i)%len(terms)] for i in range(min(len(terms),max(1,int(config.get('sequential_terms_per_month',2)))))]
                    tasks.append({**config,**layer,'kind':'index','query':config['query'],'query_variants':[t for t in variants if t!=config['query']],'start_year':year,'end_year':year,'start_month':month,'end_month':month,'source_modes':public,'seed_url_file':''})
    return tasks

def sitemap_page(root_url, state, terms, fetch, max_maps=5, max_urls=1000):
    """One bounded discovery slice; caller persists queue and discovered URLs."""
    host=urllib.parse.urlsplit(root_url).hostname
    if not host or urllib.parse.urlsplit(root_url).scheme!='https':raise ValueError('El sitemap debe usar HTTPS.')
    queue=list(state.get('queue',[root_url]));seen=set(state.get('seen',[]));urls=list(state.get('urls',[]));errors=list(state.get('errors',[]))
    pending=list(state.get('pending_urls',[]));batch=[];processed=0
    def consume():
        while pending and len(batch)<max_urls:
            loc=pending.pop(0)
            if loc not in urls:urls.append(loc);batch.append(loc)
    consume()
    while queue and processed<max_maps and len(batch)<max_urls:
        url=queue.pop(0)
        if url in seen:continue
        parsed=urllib.parse.urlsplit(url)
        if parsed.hostname!=host or parsed.scheme!='https':continue
        processed+=1
        try:
            xml=fetch(url)
            if len(xml.encode())>10_000_000:raise ValueError('Sitemap supera el límite local de 10 MB.')
            tree=ET.fromstring(xml)
            index=tree.tag.rsplit('}',1)[-1]=='sitemapindex'
            for element in tree:
                loc=next((c.text for c in element if c.tag.rsplit('}',1)[-1]=='loc'),'') or ''
                if urllib.parse.urlsplit(loc).hostname!=host or urllib.parse.urlsplit(loc).scheme!='https':continue
                if index:
                    if loc not in seen and loc not in queue:queue.append(loc)
                elif any(folded(t) in folded(urllib.parse.unquote(loc)) for t in terms if len(t)>=3) and loc not in urls and loc not in pending:
                    pending.append(loc)
            seen.add(url)
            consume()
        except Exception as exc:
            errors.append({'url':url,'error':type(exc).__name__})
            # Retry the failed map on a later explicit resume, never in this slice.
            queue.append(url)
            break
    return {'queue':queue,'seen':sorted(seen),'urls':urls,'pending_urls':pending,'batch':batch,'errors':errors,'discovery_complete':not queue and not pending,'bounded':bool(queue or pending)}

