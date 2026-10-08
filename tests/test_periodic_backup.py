import io
import json
import tempfile
import threading
import unittest
import zipfile
from unittest.mock import patch, Mock
from collection_jobs import Job
from job_backup import checkpoint, PeriodicBackup, INTERVAL_SECONDS

class BackupTests(unittest.TestCase):
    def make_job(self, root):
        job = Job.create(root, {'query':'tatuaje','start_year':2020,'end_year':2020,'target_total_per_year':1}, [])
        job.ingest({'title':'Tatuaje', 'text_clean':'Un relato público sobre tatuaje.', 'url':'https://example.org/test', 'status':'ok'})
        return job

    def test_local_snapshot_analysis_restore_without_cloud_claim(self):
        with tempfile.TemporaryDirectory() as root, patch('job_backup.configured', return_value=False):
            job=self.make_job(root)
            self.assertFalse(checkpoint(job))
            self.assertEqual(job.get('backup_status'),'local_only')
            data=(job.root/'latest_checkpoint.zip').read_bytes()
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                report=json.loads(z.read('checkpoint_analysis.json'))
                rows=json.loads(z.read('news_records_merged.json'))
                self.assertEqual(report['records_retained'],len(rows))
                self.assertIn('checkpoint_analysis.md',z.namelist())
            restored=Job.restore(root,data)
            self.assertEqual(restored.rows(),job.rows())

    def test_only_successful_upload_is_confirmed(self):
        with tempfile.TemporaryDirectory() as root, patch('job_backup.configured', return_value=True), patch('job_backup.client') as client, patch.dict('os.environ',{'SIAN_BACKUP_BUCKET':'test'}):
            job=self.make_job(root)
            self.assertTrue(checkpoint(job))
            self.assertIsNotNone(job.get('backup_saved_at'))
            client.return_value.put_object.side_effect=OSError('offline')
            last=job.get('backup_saved_at')
            self.assertFalse(checkpoint(job))
            self.assertEqual(job.get('backup_status'),'failed')
            self.assertEqual(last,job.get('backup_saved_at'))

    def test_timer_fires_during_long_task_and_finishes(self):
        reached=threading.Event()
        def fake(job,reason):
            if reason=='interval':reached.set()
        with patch('job_backup.checkpoint',side_effect=fake) as call:
            with PeriodicBackup(Mock(),interval=.01):
                self.assertTrue(reached.wait(2))
            reasons=[c.args[1] for c in call.call_args_list]
            self.assertEqual(reasons[0],'start')
            self.assertIn('interval',reasons)
            self.assertEqual(reasons[-1],'completion_or_pause')
            self.assertEqual(INTERVAL_SECONDS,1200)

    def test_exception_still_checkpoints(self):
        with patch('job_backup.checkpoint') as call:
            with self.assertRaises(RuntimeError):
                with PeriodicBackup(Mock()):raise RuntimeError('interrupted')
            self.assertEqual(call.call_args_list[-1].args[1],'interrupted')
