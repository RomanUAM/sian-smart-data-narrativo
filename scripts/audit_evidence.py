#!/usr/bin/env python3
"""Migrate a corpus and export coverage/models without editing the input."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evidence_model import apply_reviews, coverage_report, descriptive_models, metadata_audit_rows
from narrative_analysis import load_records_from_path, rows_to_csv, save_records_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reviews", type=Path)
    parser.add_argument("--precision", choices=["year", "month", "day"], default="year")
    args = parser.parse_args()
    if args.output.resolve() == args.input.resolve() or args.input.resolve() in args.output.resolve().parents and args.input.is_dir():
        parser.error("Choose a separate output directory outside the input corpus")
    rows = load_records_from_path(args.input)
    if not rows:
        parser.error("No corpus records found")
    if args.reviews:
        rows = apply_reviews(rows, json.loads(args.reviews.read_text(encoding="utf-8")))
    args.output.mkdir(parents=True, exist_ok=True)
    save_records_json(rows, args.output)
    outputs = {"information_coverage.json": coverage_report(rows, args.precision),
               "descriptive_models.json": descriptive_models(rows, args.precision),
               "review_template.json": [{"document_id": r["document_id"], "claims": [], "reviewed_concepts": []} for r in rows]}
    for filename, data in outputs.items():
        (args.output / filename).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output / "metadata_audit.csv").write_bytes(rows_to_csv(metadata_audit_rows(rows)))
    for name in ("document_concept_matrix", "actor_concept_stance", "source_concept_summary", "temporal_reviewed_concepts", "asserted_relations"):
        (args.output / f"{name}.csv").write_bytes(rows_to_csv(outputs["descriptive_models.json"][name]))
    print(json.dumps({"records": len(rows), "output": str(args.output), "coverage": outputs["information_coverage.json"]["analyses"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
