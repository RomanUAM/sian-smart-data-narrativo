"""Portable corpus imports and downloadable snapshots for hosted SIAN."""
from __future__ import annotations
import io
import json
import zipfile
from pathlib import Path
from corpus_contract import merge_rows
from corpus_storage import atomic_json, atomic_write


def parse_corpus_upload(data: bytes, filename: str) -> list[dict]:
    text = data.decode('utf-8-sig')
    if filename.lower().endswith('.jsonl'):
        value = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        value = json.loads(text)
        if isinstance(value, dict) and isinstance(value.get('records'), list):
            value = value['records']
        elif isinstance(value, dict):
            value = [value]
    if not isinstance(value, list) or any(not isinstance(r, dict) or not any(r.get(k) for k in ('url', 'title', 'text_clean', 'pdf_text_clean')) for r in value):
        raise ValueError('El archivo debe contener documentos, no un manifiesto o configuración.')
    return merge_rows(value)


def saved_files(root: str | Path) -> list[Path]:
    root = Path(root)
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob('*') if p.is_file() and not p.is_symlink() and p.suffix.lower() in {'.json', '.jsonl', '.csv'})


def corpus_archive(root: str | Path) -> bytes:
    root = Path(root)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in saved_files(root):
            archive.writestr(path.relative_to(root).as_posix(), path.read_bytes())
    return buffer.getvalue()


def save_collected_rows(root: str | Path, rows: list[dict], sequential: bool = False) -> None:
    name = 'news_records_sequential_merged.json' if sequential else 'news_records.json'
    atomic_json(Path(root) / name, rows)
    atomic_write(Path(root) / name.replace('.json', '.jsonl'), ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))
