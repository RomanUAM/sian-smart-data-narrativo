#!/usr/bin/env python3
"""Export a SIAN corpus as relational SQLite, spreadsheet, CSV and native JSON."""
from __future__ import annotations
import argparse
import io
import os
import tempfile
import csv
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from corpus_contract import merge_rows
from corpus_storage import atomic_json, atomic_write
from evidence_model import coverage_report, descriptive_models, metadata_audit_rows
from narrative_analysis import load_records_from_path


def export_database(rows, output):
    from openpyxl import Workbook
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    rows = merge_rows(rows)
    atomic_json(output/'export_manifest.json', {'status':'running','records':len(rows),'schema_version':2})
    document_rows = []
    information = []
    provenance = []
    for row in rows:
        info = row['record_information']
        document_rows.append(dict(document_id=row['document_id'], version_id=row['version_id'], retrieval_id=row['retrieval_id'], content_kind=row['content_kind'], selection_status=row['selection']['state'], selection_reason=row['selection']['reason'], year=row['year'], search_year=row.get('search_year'),
            source_type=row.get('source_type'), source_collection=row.get('source_collection'), medium=row.get('medium'),
            title=row.get('title'), url=row.get('url'), authors='; '.join(info['author'].get('value') or []) if info['author']['state']=='explicit' else None,
            publication_date=info['publication_date'].get('value'), date_state=info['publication_date']['state'],
            date_precision=info['publication_date'].get('precision'), text_coverage=info['text'].get('coverage'),
            selection_state=row.get('selection_state') or 'unreviewed', retrieval_mode=row.get('retrieval_mode') or row.get('source_api'),
            text_excerpt=info['text'].get('value')))
        for field, c in info.items():
            information.append(dict(document_id=row['document_id'], field=field,state=c.get('state'),
                value_json=json.dumps(c.get('value'),ensure_ascii=False),evidence_json=json.dumps(c.get('evidence'),ensure_ascii=False),
                method=c.get('method'),precision=c.get('precision'),coverage=c.get('coverage')))
        for item in row.get('retrieval_provenance') or [{k:row.get(k) for k in ('url','source_api','source_collection','fetched_at','search_year')}]:
            provenance.append(dict(document_id=row['document_id'], provenance_json=json.dumps(item,ensure_ascii=False)))
    coverage=coverage_report(rows); models=descriptive_models(rows)
    annual_counts=Counter((row['year'],row.get('source_type') or 'other') for row in rows if row['year'])
    annual=[dict(year=year,source_type=source,count=annual_counts[(year,source)]) for year in range(min((r['year'] for r in rows if r['year']),default=2016),max((r['year'] for r in rows if r['year']),default=2026)+1) for source in sorted({r.get('source_type') or 'other' for r in rows})]
    tables={'documents':document_rows,'information':information,'retrieval_provenance':provenance,'annual_coverage':annual,
            'analysis_coverage':[dict(analysis=k,eligible=v['eligible'],total=v['total'],coverage=v['coverage'],status=v['status'],excluded_reasons=v['excluded_reasons']) for k,v in coverage['analyses'].items()],'metadata_audit':metadata_audit_rows(rows)}
    tables.update({name:value for name,value in models.items() if isinstance(value,list) and name != 'limitations'})
    tables['document_versions']=[dict(document_id=r['document_id'],version_id=v['version_id'],payload_json=json.dumps(v,ensure_ascii=False)) for r in rows for v in r['versions']]
    tables['document_retrievals']=[dict(document_id=r['document_id'],retrieval_id=v['retrieval_id'],version_id=v['version_id'],payload_json=json.dumps(v,ensure_ascii=False)) for r in rows for v in r['retrievals']]
    tables['document_history']=[dict(document_id=r['document_id'],event_json=json.dumps(v,ensure_ascii=False)) for r in rows for v in r['record_history']]
    db=output/'tatuaje_2016_2026.sqlite'
    fd, temporary_db=tempfile.mkstemp(suffix='.sqlite',dir=output);os.close(fd)
    connection=sqlite3.connect(temporary_db)
    connection.execute('PRAGMA foreign_keys=ON')
    for name, records in tables.items():
        columns=list(dict.fromkeys(key for record in records for key in record))
        if not columns:
            columns={'document_concept_matrix':['document_id','concept','value'], 'source_concept_summary':['source','concept','documents_with_concept','documents_reviewed_for_concept','proportion'], 'actor_concept_stance':['actor','concept','stance','claims'], 'temporal_reviewed_concepts':['period','concept','documents'], 'asserted_relations':['document_id','source','target','type','quote']}.get(name,['state'])
        types={c:('INTEGER' if c in {'year','search_year','count','eligible','total','documents','claims','documents_with_concept','documents_reviewed_for_concept'} else 'REAL' if c in {'value','coverage','proportion'} and name not in {'information','metadata_audit'} else 'TEXT') for c in columns}
        if name=='documents': types['document_id']='TEXT PRIMARY KEY'
        schema=', '.join('"'+c+'" '+types[c] for c in columns)
        if name in {'information','retrieval_provenance','document_versions','document_retrievals'}: schema+=', FOREIGN KEY(document_id) REFERENCES documents(document_id)'
        connection.execute(f'CREATE TABLE "{name}" ({schema})')
        values=[[json.dumps(record.get(c),ensure_ascii=False) if isinstance(record.get(c),(dict,list)) else record.get(c) for c in columns] for record in records]
        connection.executemany(f'INSERT INTO "{name}" VALUES ({",".join("?" for _ in columns)})',values)
        stream=io.StringIO(newline='');writer=csv.writer(stream);writer.writerow(columns);writer.writerows(values)
        atomic_write(output/f'{name}.csv', '\ufeff'+stream.getvalue())
    for source in sorted({r.get('source_type') or 'other' for r in rows}):
        safe=''.join(ch for ch in source if ch.isalnum() or ch=='_')
        connection.execute(f'CREATE VIEW "base_{safe}" AS SELECT * FROM documents WHERE source_type=?'.replace('?',"'"+source.replace("'","''")+"'"))
    connection.commit()
    if connection.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or connection.execute('PRAGMA foreign_key_check').fetchall():
        raise RuntimeError('Database integrity check failed')
    connection.close()
    workbook=Workbook();workbook.remove(workbook.active)
    for name,records in tables.items():
        sheet=workbook.create_sheet(name[:31]);columns=list(dict.fromkeys(k for r in records for k in r))
        if not columns:
            sheet.append(['state']);sheet.append(['sin datos revisados suficientes']);continue
        sheet.append(columns)
        for record in records:
            values=[]
            for c in columns:
                value=record.get(c)
                if isinstance(value,(dict,list)):value=json.dumps(value,ensure_ascii=False)
                # Export retrieved text as literal cells, never spreadsheet formulas.
                if isinstance(value,str) and value.startswith(('=','+','-','@')):value="'"+value
                values.append(value)
            sheet.append(values)
        sheet.freeze_panes='A2';sheet.auto_filter.ref=sheet.dimensions
        for col in sheet.columns: sheet.column_dimensions[col[0].column_letter].width=24
    fd,temporary_excel=tempfile.mkstemp(suffix='.xlsx',dir=output);os.close(fd)
    try:
        workbook.save(temporary_excel)
        os.replace(temporary_excel,output/'tatuaje_2016_2026.xlsx')
    finally:
        if os.path.exists(temporary_excel):os.unlink(temporary_excel)
    for name,value in [('news_records.json',rows),('information_coverage.json',coverage),('descriptive_models.json',models)]:
        atomic_json(output/name,value)
    os.replace(temporary_db,db)
    atomic_json(output/'export_manifest.json', {'status':'completed','records':len(rows),'schema_version':2})
    counts=dict(Counter(r.get('source_type') or 'other' for r in rows))
    return dict(records=len(rows),by_source_type=counts,table_rows={k:len(v) for k,v in tables.items()},database=str(db))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('input');parser.add_argument('--output',required=True);args=parser.parse_args()
    print(json.dumps(export_database(load_records_from_path(args.input),args.output),ensure_ascii=False))

if __name__=='__main__':main()
