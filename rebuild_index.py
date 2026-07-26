#!/usr/bin/env python3
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def read_record(file_path: Path) -> dict | None:
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def rebuild_index(output_dir: str | Path = "news_output") -> list[dict]:
    output_dir = Path(output_dir)
    records_by_url: dict[str, dict] = {}
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
            key = data.get("url") or str(futures[future])
            records_by_url[key] = data

    records = list(records_by_url.values())
    records.sort(key=lambda item: (item.get("year") or 0, item.get("medium") or "", item.get("title") or ""))

    (output_dir / "news_records.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with (output_dir / "news_records.jsonl").open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Rebuilt {len(records)} records in {output_dir}")
    if skipped:
        print(f"Skipped {skipped} unreadable files")
    return records


if __name__ == "__main__":
    rebuild_index()
