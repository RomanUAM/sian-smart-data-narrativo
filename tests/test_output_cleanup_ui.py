"""Regression for the cleanup action that previously referenced a missing helper."""
import tempfile
import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / 'streamlit_app.py'

class OutputCleanupTests(unittest.TestCase):
    def click_cleanup(self, app):
        next(c for c in app.checkbox if c.label.startswith('Confirmo que quiero limpiar')).check().run(timeout=60)
        next(b for b in app.button if b.label == 'Limpiar bases de salida').click().run(timeout=60)
        self.assertFalse(app.exception, str(app.exception))

    def test_cleanup_of_disposable_session_output(self):
        with tempfile.TemporaryDirectory(prefix='sian-') as root:
            output = Path(root) / 'news_output'
            output.mkdir()
            (output / 'temporary.json').write_text('[]')
            app = AppTest.from_file(str(APP))
            app.session_state['web_output_dir'] = str(output)
            app.run(timeout=60)
            self.click_cleanup(app)
            self.assertFalse(output.exists())

    def test_collection_job_directory_is_preserved(self):
        with tempfile.TemporaryDirectory(prefix='sian-') as root:
            job = Path(root) / ('a' * 32)
            job.mkdir()
            saved = job / 'records.json'
            saved.write_text('[]')
            app = AppTest.from_file(str(APP))
            app.session_state['web_output_dir'] = str(job)
            app.run(timeout=60)
            self.click_cleanup(app)
            self.assertTrue(saved.exists())
            self.assertTrue(app.error)

if __name__ == '__main__':
    unittest.main()
