"""Portable corpus imports and downloadable snapshots for hosted SIAN."""
from __future__ import annotations
import io
import csv
import json
import zipfile
from pathlib import Path
from corpus_contract import merge_rows
from corpus_storage import atomic_json, atomic_write


def parse_corpus_upload(data: bytes, filename: str) -> list[dict]:
    text = data.decode('utf-8-sig')
    suffix = Path(filename).suffix.lower()
    if suffix == '.csv':
        reader = csv.DictReader(io.StringIO(text), dialect=csv.Sniffer().sniff(text, delimiters=',;\t'))
        aliases = {'titulo': 'title', 'texto': 'text_clean', 'text': 'text_clean', 'autor': 'author', 'fuente': 'medium', 'fecha': 'published_date', 'tipo': 'source_type'}
        value = []
        for original in reader:
            row = {aliases.get(k.strip().lower(), k.strip()): v for k, v in original.items() if k is not None}
            if 'published_date_verified' in row:
                row['published_date_verified'] = str(row['published_date_verified']).lower() in {'true', '1', 'sí', 'si'}
            row.setdefault('status', 'ok' if row.get('text_clean', '').strip() else 'ok_partial')
            row.setdefault('source_api', 'user_csv_import')
            value.append(row)
    elif suffix == '.txt':
        if not text.strip():
            raise ValueError('El elemento está vacío.')
        value = [{'title': Path(filename).stem, 'text_clean': text.strip(), 'status': 'ok', 'source_api': 'user_text_import', 'source_type': 'other'}]
    elif suffix == '.jsonl':
        value = [json.loads(line) for line in text.splitlines() if line.strip()]
    elif suffix == '.json':
        value = json.loads(text)
        if isinstance(value, dict) and isinstance(value.get('records'), list):
            value = value['records']
        elif isinstance(value, dict):
            value = [value]
    else:
        raise ValueError('Formatos admitidos: JSON, JSONL, CSV y TXT.')
    return merge_rows(prepare_upload_rows(value))


def prepare_upload_rows(value):
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError('El archivo debe contener documentos, no un manifiesto o configuración.')
    aliases = {'titulo': 'title', 'texto': 'text_clean', 'text': 'text_clean', 'autor': 'author', 'fuente': 'medium', 'fecha': 'published_date'}
    for row in value:
        for original, field in aliases.items():
            if original in row:
                row.setdefault(field, row[original])
        if isinstance(row.get('published_date_verified'), str):
            row['published_date_verified'] = row['published_date_verified'].lower() in {'true', '1', 'sí', 'si'}
        if row.get('text_clean') and not row.get('status'):
            row['status'] = 'ok'
        row.setdefault('source_api', 'user_file_import')
    if any(not any(row.get(k) for k in ('url', 'title', 'text_clean', 'pdf_text_clean')) for row in value):
        raise ValueError('El archivo debe contener documentos, no un manifiesto o configuración.')
    return value


def iter_corpus_upload(data: bytes, filename: str):
    # Large exports are arrays. Decode each object separately so a single
    # non-BMP character cannot widen the decoded string for the entire file.
    if Path(filename).suffix.lower() != ".json":
        yield from parse_corpus_upload(data, filename)
        return
    with io.TextIOWrapper(io.BytesIO(data), encoding="utf-8-sig") as stream:
        buffer = stream.read(65536).lstrip()
        if not buffer.startswith("["):
            yield from parse_corpus_upload(data, filename)
            return
        decoder = json.JSONDecoder()
        buffer = buffer[1:]

        def next_token():
            nonlocal buffer
            buffer = buffer.lstrip()
            while not buffer:
                block = stream.read(65536)
                if not block:
                    raise ValueError("El arreglo JSON está incompleto.")
                buffer = block.lstrip()
            return buffer[0]

        if next_token() != "]":
            while True:
                while True:
                    try:
                        row, end = decoder.raw_decode(buffer)
                        break
                    except json.JSONDecodeError:
                        block = stream.read(65536)
                        if not block:
                            raise
                        buffer += block
                yield from prepare_upload_rows([row])
                buffer = buffer[end:]
                token = next_token()
                if token == "]":
                    break
                if token != ",":
                    raise ValueError("Se esperaba una coma entre registros JSON.")
                buffer = buffer[1:]
                next_token()
        if buffer[1:].strip() or stream.read().strip():
            raise ValueError("Hay contenido después del arreglo JSON.")


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
