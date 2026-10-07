"""Annual quotas describe an observed sample, never an assumed population."""
import datetime as dt
import hashlib
import re
import unicodedata
from collections import Counter
from evidence_model import normalize_record, date_precision
from corpus_contract import merge_rows, identity_key

def folded(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value)).lower() if not unicodedata.combining(c))

def classify(row, rubrics):
    text = folded(' '.join(str(row.get(k) or '') for k in ('title', 'text_clean', 'summary')))
    labels, hits = [], []
    for name, terms in rubrics.items():
        matches = [t for t in terms if len(folded(t)) >= 3 and folded(t) in text]
        if matches and name not in {'núcleo', 'nucleo'}:
            labels.append(name); hits.extend(matches)
    old=row.get('narrative_rubrics') or []
    if isinstance(old,str):old=[s.strip() for s in old.split(',') if s.strip()]
    row['collection_rubrics']=sorted(set(old+labels))
    row['narrative_rubrics']=', '.join(row['collection_rubrics'])
    old_terms=row.get('narrative_terms') or []
    if isinstance(old_terms,str):old_terms=[s.strip() for s in old_terms.split(',') if s.strip()]
    row['narrative_terms'] = sorted(set(old_terms + hits))
    return row

def assess(rows, config, today=None):
    today = today or dt.date.today()
    start, end = int(config['start_year']), min(int(config['end_year']), today.year)
    target = max(1, int(config.get('target_total_per_year', 200)))
    counts, sources, rubrics, months, reasons = Counter(), Counter(), Counter(), Counter(), Counter()
    fingerprints = {}
    merged = merge_rows(rows)
    # Prefer the most informative copy, with deterministic tie breaking across resumes.
    merged.sort(key=lambda r: (-len(r.get('text_clean') or ''), identity_key(r)))
    for row in merged:
        row = classify(row, config.get('classification_rubrics') or config.get('variant_rubrics') or {})
        pub = row.get('record_information', {}).get('publication_date', {})
        text = row.get('text_clean') or row.get('text_normalized') or ''
        reason = ''
        year = row.get('year')
        precision = date_precision(pub.get('value')) if pub.get('state') == 'explicit' else ''
        if not precision or not year: reason = 'missing_or_conflicting_publication_date'
        elif not start <= year <= end: reason = 'outside_requested_years'
        elif str(pub['value'])[:10] > today.isoformat(): reason = 'future_publication_date'
        elif row.get('selection', {}).get('state') == 'excluded': reason = 'excluded'
        elif row.get('status') not in {'ok', 'ok_partial'} or len(text.strip()) < int(config.get('min_text_chars', 300)): reason = 'insufficient_text'
        elif not any(folded(t) in folded(' '.join((str(row.get('title') or ''), text))) for t in [config.get('query', ''), *config.get('topic_terms', [])] if len(folded(t)) >= 3): reason = 'topic_not_verified'
        fingerprint = hashlib.sha256(re.sub(r'\s+', ' ', text).strip().encode()).hexdigest() if len(text.strip()) >= 300 else None
        duplicate = fingerprints.get(fingerprint) if fingerprint else None
        if not reason and duplicate: reason = 'duplicate_content'
        if not reason and fingerprint: fingerprints[fingerprint] = identity_key(row)
        eligible = not reason
        selected = eligible and counts[year] < target
        if selected:
            counts[year] += 1
            sources[(year, row.get('source_type', 'unknown'))] += 1
            for name in row.get('collection_rubrics', []): rubrics[(year, name)] += 1
            if precision in {'month','day','datetime'}: months[(year, str(pub['value'])[5:7])] += 1
        reasons[reason or ('selected' if selected else 'beyond_target')] += 1
        row['collection_assessment'] = {'eligible': eligible, 'selected': selected, 'reason': reason or ('selected' if selected else 'beyond_target'), 'duplicate_of': duplicate, 'policy_version': 1}
    coverage = [{'year': year, 'target': target, 'selected': counts[year], 'gap': max(0,target-counts[year]), 'period_complete': year < today.year} for year in range(start,end+1)]
    report = {'annual': coverage, 'reasons': dict(reasons), 'records_retained': len(merged), 'duplicate_retrievals': len(rows)-len(merged), 'additional_provenances': sum(max(0,len(r.get('retrievals',[]))-1) for r in merged), 'by_source': [{'year':y,'source_type':s,'count':c} for (y,s),c in sorted(sources.items())], 'by_rubric': [{'year':y,'rubric':s,'count':c} for (y,s),c in sorted(rubrics.items())], 'by_month': [{'year':y,'month':s,'count':c} for (y,s),c in sorted(months.items())], 'target_met': bool(coverage) and all(r['gap']==0 for r in coverage), 'cutoff': today.isoformat(), 'sampling_note': 'Muestra de disponibilidad. Alcanzar la cuota no demuestra representatividad; las etiquetas de rubro pueden superponerse.'}
    return merged, report
