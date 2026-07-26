#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from news_spider import classify_source_type, clean_article_text, evidence_rank_for_source_type


def reclean_record(record: dict) -> dict:
    source_text = record.get("text_raw_visible") or record.get("text_clean") or ""
    cleaned = clean_article_text(source_text, title=record.get("title", ""), source_url=record.get("url", ""))
    source_type, source_type_confidence, source_type_evidence = classify_source_type(
        article={},
        url=record.get("url", ""),
        medium=record.get("medium", ""),
        title=record.get("title", ""),
    )
    evidence_level, evidence_weight = evidence_rank_for_source_type(source_type)
    updated = dict(record)
    updated.setdefault("query_variants", [])
    updated.setdefault("geographic_scope", "not_recorded")
    updated.setdefault("geographic_terms", [])
    updated.setdefault("text_raw_visible", source_text)
    updated["source_type"] = source_type
    updated["source_type_confidence"] = source_type_confidence
    updated["source_type_evidence"] = source_type_evidence
    updated["evidence_level"] = evidence_level
    updated["evidence_weight"] = evidence_weight
    updated["text_clean"] = cleaned["text_clean"]
    updated["text_normalized"] = cleaned["text_normalized"]
    updated["text_length"] = len(cleaned["text_clean"])
    updated["word_count"] = cleaned["word_count"]
    updated["paragraph_count"] = cleaned["paragraph_count"]
    updated["cleaning_notes"] = cleaned["cleaning_notes"]
    if updated.get("status") == "ok" and updated["text_length"] == 0:
        updated["status"] = "too_short"
    return updated


def load_records(input_path: Path) -> list[dict]:
    if input_path.suffix.lower() == ".jsonl":
        return [
            json.loads(line)
            for line in input_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    data = json.loads(input_path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    return [data]


def save_records(records: list[dict], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "news_records_recleaned.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with (output_dir / "news_records_recleaned.jsonl").open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Re-clean already downloaded spider JSON/JSONL records offline.")
    parser.add_argument("input_path", help="Existing news_records.json, news_records.jsonl, or one record JSON file.")
    parser.add_argument("--output-dir", default="news_output_recleaned")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input_path)
    output_dir = Path(args.output_dir)
    records = [reclean_record(record) for record in load_records(input_path)]
    save_records(records, output_dir)
    ok = sum(1 for record in records if record.get("status") == "ok")
    print(f"Saved {len(records)} re-cleaned records ({ok} ok) in {output_dir}")


if __name__ == "__main__":
    main()
