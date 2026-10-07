#!/usr/bin/env python3
"""Migrate/reprocess saved SIAN records using resumable stages and a registry."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from corpus_pipeline import process_corpus

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--selection-reviews',type=Path);args=p.parse_args()
    if args.input.resolve()==args.output.resolve() or args.input.resolve() in args.output.resolve().parents and args.input.is_dir():p.error('Use a separate output directory')
    if args.input.suffix=='.jsonl':rows=[json.loads(line) for line in args.input.read_text().splitlines() if line.strip()]
    else:
        rows=json.loads(args.input.read_text());rows=rows if isinstance(rows,list) else [rows]
    reviews=json.loads(args.selection_reviews.read_text()) if args.selection_reviews else []
    rows,report=process_corpus(rows,args.output,reviews)
    print(json.dumps({k:v for k,v in report.items() if k!='analysis_eligibility'},ensure_ascii=False))
if __name__=='__main__':main()
