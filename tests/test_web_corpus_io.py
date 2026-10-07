import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from web_corpus_io import parse_corpus_upload, corpus_archive, saved_files, save_collected_rows

class WebCorpusTests(unittest.TestCase):
    def row(self):
        return {'url':'https://example.org/a', 'title':'Tatuaje', 'text_clean':'Una expresión de identidad.', 'status':'ok_partial'}
    def test_import_json_and_jsonl_preserves_identity(self):
        data=json.dumps([self.row()]).encode()
        rows=parse_corpus_upload(data,'corpus.json')
        restored=parse_corpus_upload(json.dumps(rows[0]).encode()+b'\n','corpus.jsonl')
        self.assertEqual(restored, rows)
        self.assertEqual(len(parse_corpus_upload(json.dumps([self.row(),self.row()]).encode(),'a.json')),1)
    def test_rejects_manifest_and_malformed_upload(self):
        for data in (b'{"system":"SIAN"}',b'[1]',b'invalid'):
            with self.assertRaises(ValueError):parse_corpus_upload(data,'a.json')
    def test_snapshot_contains_partial_files_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'by_source/news/2020').mkdir(parents=True)
            partial=root/'by_source/news/2020/a.json';partial.write_text(json.dumps(self.row()))
            (root/'run_manifest.json').write_text('{"status":"running"}')
            (root/'ignored.tmp').write_text('unfinished')
            with zipfile.ZipFile(io.BytesIO(corpus_archive(root))) as archive:
                self.assertEqual(set(archive.namelist()), {'by_source/news/2020/a.json','run_manifest.json'})
                self.assertEqual(json.loads(archive.read('by_source/news/2020/a.json')),self.row())
            self.assertEqual(len(saved_files(root)),2)
    def test_final_and_sequential_checkpoint_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows=parse_corpus_upload(json.dumps([self.row()]).encode(),'a.json')
            save_collected_rows(tmp,rows,True)
            path=Path(tmp)/'news_records_sequential_merged.json'
            self.assertEqual(parse_corpus_upload(path.read_bytes(),path.name),rows)
            save_collected_rows(tmp,[],False)
            self.assertEqual(json.loads((Path(tmp)/'news_records.json').read_text()),[])
