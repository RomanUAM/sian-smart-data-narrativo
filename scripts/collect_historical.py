#!/usr/bin/env python3
"""Create, resume or export a historical SIAN collection job."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from collection_jobs import Job,job_base,open_job
from collection_runner import execute
from historical_sources import plan
from corpus_storage import atomic_write

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    action=parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--config',type=Path)
    action.add_argument('--resume')
    action.add_argument('--restore',type=Path)
    parser.add_argument('--plan-only',action='store_true')
    parser.add_argument('--export',type=Path)
    args=parser.parse_args()
    if args.config:
        config=json.loads(args.config.read_text())
        tasks=plan(config)
        job=Job.create(job_base(),config,tasks)
    elif args.restore:job=Job.restore(job_base(),args.restore.read_bytes())
    else:job=open_job(args.resume)
    print('Código de ejecución:',job.root.name,flush=True)
    if not args.plan_only:
        job.set('pause',False)
        try:execute(job)
        except KeyboardInterrupt:job.pause();job.set('status','paused');job.export()
    if args.export:atomic_write(args.export,job.archive())
    _,report=job.export()
    print(json.dumps({'status':job.status(),'annual':report['annual']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
