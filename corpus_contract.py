"""Shared identity and evidence-preserving merge for every SIAN entry point."""
from __future__ import annotations
import copy
import hashlib
import json
import re
from urllib.parse import urlsplit, parse_qsl, urlencode
from evidence_model import normalize_record


def is_record(row):
    return isinstance(row, dict) and any(row.get(k) for k in ('url', 'title', 'text_clean', 'pdf_text_clean'))


from record_schema import canonical_url_key as canonical_url_key, identity_key as identity_key


def _union(values):
    result = []
    seen = set()
    for value in values:
        key = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
        if key not in seen:
            result.append(copy.deepcopy(value))
            seen.add(key)
    return result


def merge_record(prior, incoming):
    a, b = normalize_record(prior), normalize_record(incoming)
    result = copy.deepcopy(a)
    for field in ('source_collection', 'variant_rubric', 'variant_term', 'search_role', 'narrative_rubrics', 'narrative_rubric_terms'):
        result[field] = ', '.join(sorted({part.strip() for row in (a, b)
                                        for part in str(row.get(field) or '').split(',') if part.strip()}))
    provenance = []
    for row in (a, b):
        provenance.extend(row.get('retrieval_provenance') or [])
        provenance.append({k: row.get(k) for k in ('source_collection', 'source_api', 'url', 'fetched_at', 'search_year')})
    result['retrieval_provenance'] = _union(provenance)
    for field, incoming_cell in b['record_information'].items():
        old = result['record_information'][field]
        if field == 'text':
            # Prefer usable text, then length. Preserve both variants for later review.
            candidates = [old, incoming_cell]
            best = max(candidates, key=lambda c: (c.get('state') == 'explicit', len(str(c.get('value') or ''))))
            if old.get('value') != incoming_cell.get('value'):
                result['text_variants'] = _union((a.get('text_variants') or []) + (b.get('text_variants') or []) + candidates)
            if best is incoming_cell:
                for key in ('text_clean', 'text_raw_visible', 'text_normalized', 'text_length', 'word_count', 'paragraph_count', 'status', 'pdf_text_clean', 'pdf_text_length', 'cleaning_notes'):
                    if key in b:
                        result[key] = copy.deepcopy(b[key])
            result['record_information'][field] = copy.deepcopy(best)
        elif field == 'consultation_date':
            # Different consultation instants are expected retrieval history, not a contradiction.
            if incoming_cell.get('state') == 'explicit' and str(incoming_cell.get('value')) > str(old.get('value') or ''):
                result['record_information'][field] = copy.deepcopy(incoming_cell)
        elif old.get('state') == 'conflicting' or incoming_cell.get('state') == 'conflicting':
            evidence = []
            for c in (old, incoming_cell):
                evidence.extend(c.get('evidence', []) if c.get('state') == 'conflicting' else [c])
            result['record_information'][field] = {'value': None, 'state': 'conflicting', 'method': 'merge_conflict', 'evidence': _union(evidence)}
        elif old.get('state') != 'explicit' and incoming_cell.get('state') == 'explicit':
            result['record_information'][field] = copy.deepcopy(incoming_cell)
        elif old.get('state') == incoming_cell.get('state') == 'explicit' and old.get('value') != incoming_cell.get('value'):
            # Date precision can increase without a conflict when the shared prefix agrees.
            va, vb = str(old.get('value') or ''), str(incoming_cell.get('value') or '')
            if field in ('publication_date', 'update_date') and (va.startswith(vb) or vb.startswith(va)):
                result['record_information'][field] = copy.deepcopy(max((old, incoming_cell), key=lambda c: len(str(c.get('value')))))
            else:
                result['record_information'][field] = {'value': None, 'state': 'conflicting', 'method': 'merge_conflict', 'evidence': _union([old, incoming_cell])}
    for field in ('versions','retrievals','record_history','document_relations'):
        result[field] = _union((a.get(field) or []) + (b.get(field) or []))
    result['claims'] = _union((a.get('claims') or []) + (b.get('claims') or []))
    for field, flat in (('author', 'authors'), ('publication_date', 'published_date'), ('update_date', 'updated_date')):
        c = result['record_information'][field]
        result[flat] = copy.deepcopy(c.get('value')) if c.get('state') == 'explicit' else ([] if flat == 'authors' else '')
    result['dedup_key'] = identity_key(result)
    return normalize_record(result)


def merge_rows(rows):
    merged = {}
    for raw in rows:
        if not is_record(raw):
            continue
        row = normalize_record(raw)
        key = identity_key(row)
        row['dedup_key'] = key
        merged[key] = merge_record(merged[key], row) if key in merged else row
    return sorted(merged.values(), key=lambda row: (str(row.get('year') or ''), str(row.get('source_type') or ''), str(row.get('medium') or ''), identity_key(row)))
