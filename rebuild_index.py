#!/usr/bin/env python3
from __future__ import annotations
from corpus_storage import atomic_write

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from corpus_contract import is_record, merge_rows


def read_record(file_path: Path) -> dict | None:
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if is_record(data) else None


def rebuild_index(output_dir: str | Path = "news_output") -> list[dict]:
    output_dir = Path(output_dir)
    source_rows = []
    skipped = 0

    files = [
        file_path
        for year_dir in sorted(path for path in output_dir.iterdir() if path.is_dir())
        for file_path in sorted(year_dir.glob("*.json"))
    ]
    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = {executor.submit(read_record, file_path): file_path for file_path in files}
        for future in as_completed(futures):
            data = future.result()
            if not data:
                skipped += 1
                continue
            source_rows.append(data)

    records = merge_rows(source_rows)
    records.sort(key=lambda item: (item.get("year") or 0, item.get("medium") or "", item.get("title") or ""))

    atomic_write(output_dir / 'news_records.json', json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    with (output_dir / "news_records.jsonl").open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Rebuilt {len(records)} records in {output_dir}")
    if skipped:
        print(f"Skipped {skipped} unreadable files")
    return records


if __name__ == "__main__":
    rebuild_index()
