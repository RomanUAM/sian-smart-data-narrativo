"""Consistent analyzed checkpoints every 20 minutes and on completion.

Only a successful external upload survives loss of a temporary server disk.
"""
import datetime as dt
import io
import json
import os
import threading
import zipfile
from corpus_storage import atomic_write
from checkpoint_analysis import analyze, markdown

INTERVAL_SECONDS = 20 * 60


def configured():
    return bool(os.environ.get('SIAN_BACKUP_BUCKET'))


def object_key(token):
    return os.environ.get('SIAN_BACKUP_PREFIX', 'sian/jobs').strip('/') + '/' + token + '.zip'


def client():
    import boto3
    from botocore.config import Config
    return boto3.client('s3', config=Config(connect_timeout=10, read_timeout=30,
                                           retries={'max_attempts': 2}))


def checkpoint(job, reason='manual'):
    try:
        # Archive uses SQLite backup; analyze the exact same snapshot, not live rows.
        original = job.archive()
        with zipfile.ZipFile(io.BytesIO(original)) as z:
            rows = json.loads(z.read('news_records_merged.json'))
            coverage = json.loads(z.read('coverage.json'))
        report = analyze(rows, coverage)
        report['checkpoint_reason'] = reason
        output = io.BytesIO(original)
        with zipfile.ZipFile(output, 'a', zipfile.ZIP_DEFLATED) as z:
            z.writestr('checkpoint_analysis.json', json.dumps(report, ensure_ascii=False, indent=2))
            z.writestr('checkpoint_analysis.md', markdown(report))
        data = output.getvalue()
        atomic_write(job.root/'checkpoint_analysis.json', json.dumps(report, ensure_ascii=False, indent=2))
        atomic_write(job.root/'checkpoint_analysis.md', markdown(report))
        atomic_write(job.root/'latest_checkpoint.zip', data)
        now = dt.datetime.now(dt.UTC).isoformat()
        job.set('checkpoint_at', now)
        job.set('checkpoint_reason', reason)
        if not configured():
            job.set('backup_status', 'local_only')
            return False
        client().put_object(Bucket=os.environ['SIAN_BACKUP_BUCKET'], Key=object_key(job.root.name),
                            Body=data, ContentType='application/zip', ServerSideEncryption='AES256')
        job.set('backup_status', 'saved')
        job.set('backup_saved_at', now)
        job.log('Respaldo externo confirmado: ' + now + ' · ' + reason)
        return True
    except Exception as exc:
        job.set('backup_status', 'failed')
        job.log('Respaldo falló: ' + type(exc).__name__)
        return False


class PeriodicBackup:
    def __init__(self, job, interval=INTERVAL_SECONDS):
        self.job, self.interval = job, interval
        self.stop = threading.Event()
        self.thread = None

    def __enter__(self):
        checkpoint(self.job, 'start')
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        return self

    def _run(self):
        while not self.stop.wait(self.interval):
            checkpoint(self.job, 'interval')

    def __exit__(self, exc_type, exc, tb):
        self.stop.set()
        self.thread.join()
        checkpoint(self.job, 'interrupted' if exc_type else 'completion_or_pause')


def recover(token):
    if not configured():
        return None
    import botocore.exceptions
    try:
        response = client().get_object(Bucket=os.environ['SIAN_BACKUP_BUCKET'], Key=object_key(token))
        if response.get('ContentLength', 0) > 500_000_000:
            raise ValueError('Respaldo excede 500 MB.')
        return response['Body'].read(500_000_001)
    except botocore.exceptions.ClientError as exc:
        if exc.response.get('Error', {}).get('Code') in {'NoSuchKey', '404'}:
            return None
        raise
