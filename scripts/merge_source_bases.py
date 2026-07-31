#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.parse
from pathlib import Path


SOURCE_KEYS = ["news", "forums", "institutional", "articles", "reports_other"]
RECORD_FILE_NAMES = {
    "news_records_sequential_merged.json",
    "news_records_sequential_merged.jsonl",
    "news_records_merged.json",
    "news_records_merged.jsonl",
    "news_records.json",
    "news_records.jsonl",
    "news_records_incremental.jsonl",
}


def normalize_key_text(value: str) -> str:
    value = (value or "").lower()
    table = str.maketrans("áéíóúüñ", "aeiouun")
    value = value.translate(table)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def canonical_url_key(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    if not parsed.netloc:
        return normalize_key_text(url)
    domain = parsed.netloc.lower().removeprefix("www.")
    path = re.sub(r"/+$", "", parsed.path or "")
    return f"url:{domain}{path}"


def row_dedup_key(row: dict) -> str:
    url_key = canonical_url_key(str(row.get("url") or row.get("pdf_url") or ""))
    if url_key:
        return url_key
    title = normalize_key_text(str(row.get("title") or ""))
    year = str(row.get("year") or "")
    medium = normalize_key_text(str(row.get("medium") or ""))
    if title:
        return f"title:{year}:{medium}:{title}"
    payload = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
    return "hash:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_records(path: Path) -> list[dict]:
    if not path.exists() or not path.is_file() or path.stat().st_size <= 2:
        return []
    try:
        if path.suffix.lower() == ".jsonl":
            rows = []
            with path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    item = json.loads(line)
                    if isinstance(item, dict):
                        rows.append(item)
            return rows
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def unavailable_reason(path: Path) -> str:
    try:
        stat = path.stat()
    except OSError as exc:
        return f"stat_error:{type(exc).__name__}"
    if stat.st_size <= 2:
        return "empty_or_json_empty_array"
    if getattr(stat, "st_blocks", 1) == 0:
        return "dataless_or_cloud_offloaded"
    try:
        with path.open("rb") as fh:
            fh.read(1)
    except TimeoutError:
        return "read_timeout"
    except OSError as exc:
        return f"read_error:{type(exc).__name__}"
    return "parse_error_or_no_dict_rows"


def source_record_files(source_dir: Path) -> list[Path]:
    if not source_dir.exists():
        return []
    ignored_names = {"query_plan.json", "run_manifest.json", "merge_report.json"}
    files = [
        path
        for path in source_dir.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".json", ".jsonl"}
        and (path.name in RECORD_FILE_NAMES or path.name not in ignored_names)
    ]
    # Prefer JSONL when both JSON and JSONL siblings exist. JSONL is streamed
    # line-by-line and is safer on long local crawls where large JSON arrays can
    # trigger OS timeouts while Streamlit is also running.
    jsonl_siblings = {path.with_suffix(".jsonl") for path in files if path.suffix == ".json"}
    filtered = []
    for path in files:
        if path.suffix == ".json" and path.with_suffix(".jsonl") in jsonl_siblings:
            continue
        filtered.append(path)
    return sorted(filtered)


def merge_sources(base_output_dir: Path, source_keys: list[str]) -> tuple[list[dict], dict]:
    merged: dict[str, dict] = {}
    report = {
        "base_output_dir": str(base_output_dir),
        "sources": {},
        "total_rows_seen": 0,
        "total_rows_merged": 0,
        "duplicates": 0,
    }
    for source_key in source_keys:
        source_dir = base_output_dir / "by_source" / source_key
        files = source_record_files(source_dir)
        source_report = {
            "source_dir": str(source_dir),
            "files_found": len(files),
            "files_with_rows": 0,
            "rows_seen": 0,
            "rows_merged_or_duplicate": 0,
            "read_failures_or_empty": 0,
            "unavailable_reasons": {},
        }
        for record_file in files:
            rows = read_records(record_file)
            if not rows:
                source_report["read_failures_or_empty"] += 1
                reason = unavailable_reason(record_file)
                source_report["unavailable_reasons"][reason] = source_report["unavailable_reasons"].get(reason, 0) + 1
                continue
            source_report["files_with_rows"] += 1
            source_report["rows_seen"] += len(rows)
            report["total_rows_seen"] += len(rows)
            for row in rows:
                key = row_dedup_key(row)
                if not key:
                    continue
                source_report["rows_merged_or_duplicate"] += 1
                if key not in merged:
                    copy = dict(row)
                    existing_collection = str(copy.get("source_collection") or "").strip()
                    copy["source_collection"] = ", ".join(
                        item for item in [existing_collection, source_key] if item
                    )
                    copy["dedup_key"] = key
                    merged[key] = copy
                else:
                    report["duplicates"] += 1
                    prior = merged[key]
                    collections = {
                        item.strip()
                        for item in str(prior.get("source_collection") or "").split(",")
                        if item.strip()
                    }
                    collections.add(source_key)
                    prior["source_collection"] = ", ".join(sorted(collections))
        report["sources"][source_key] = source_report
    merged_rows = sorted(
        merged.values(),
        key=lambda item: (str(item.get("year") or ""), str(item.get("source_type") or ""), str(item.get("medium") or "")),
    )
    report["total_rows_merged"] = len(merged_rows)
    return merged_rows, report


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge SIAN source databases, including nested by_rubric runs.")
    parser.add_argument("--base-output-dir", required=True, help="Folder that contains by_source/")
    parser.add_argument("--sources", default=",".join(SOURCE_KEYS), help="Comma-separated source keys.")
    args = parser.parse_args()
    base_output_dir = Path(args.base_output_dir).expanduser()
    source_keys = [item.strip() for item in args.sources.split(",") if item.strip()]
    rows, report = merge_sources(base_output_dir, source_keys)
    base_output_dir.mkdir(parents=True, exist_ok=True)
    if not rows and report["total_rows_seen"] == 0:
        report["write_status"] = "skipped_empty_merge_to_preserve_existing_output"
        (base_output_dir / "merge_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2
    report["write_status"] = "written"
    (base_output_dir / "news_records_merged.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (base_output_dir / "news_records_merged.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + ("\n" if rows else ""),
        encoding="utf-8",
    )
    (base_output_dir / "merge_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
