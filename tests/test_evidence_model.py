import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evidence_model import (normalize_record, eligibility, cell, coverage_report, descriptive_models,
                            extract_publication_metadata, apply_reviews, date_precision)
from news_spider import openalex_record, crossref_record
from narrative_analysis import load_records_from_path, count_rows


class EvidenceTests(unittest.TestCase):
    def row(self, **extra):
        return {"url": "https://example.org/one", "title": "Caso", "medium": "Revista",
                "status": "ok", "text_clean": "Ana sostiene que la formación mejora el empleo.", **extra}

    def claim(self, **extra):
        return {"concept": "empleo", "statement": "La formación mejora el empleo", "speaker": "Ana",
                "speaker_evidence": "Ana", "stance": "support", "review_status": "validated",
                "quote": "Ana sostiene que la formación mejora el empleo.", **extra}

    def test_missing_author_keeps_thematic_but_not_actor_network(self):
        row = normalize_record(self.row())
        self.assertIsNone(row["record_information"]["author"]["value"])
        self.assertTrue(eligibility(row, "thematic")[0])
        self.assertFalse(eligibility(row, "actor_stance")[0])

    def test_legacy_search_year_never_becomes_publication(self):
        row = normalize_record(self.row(year=2026))
        self.assertIsNone(row["year"])
        self.assertEqual(row["search_year"], 2026)
        self.assertFalse(eligibility(row, "temporal")[0])

    def test_observation_date_not_publication(self):
        row = normalize_record(self.row(published_date="2026-03-01", source_api="gdelt_doc_2_1"))
        self.assertFalse(eligibility(row, "temporal")[0])

    def test_consultation_update_not_publication(self):
        row = normalize_record(self.row(fetched_at="2026-10-06T10:00:00Z", updated_date="2026-10-01"))
        self.assertFalse(eligibility(row, "temporal")[0])
        self.assertEqual(row["record_information"]["consultation_date"]["state"], "explicit")

    def test_year_precision_does_not_create_month(self):
        row = normalize_record(self.row(published_date="2021", source_api="crossref_works"))
        self.assertTrue(eligibility(row, "temporal", "year")[0])
        self.assertFalse(eligibility(row, "temporal", "month")[0])

    def test_invalid_dates_rejected(self):
        for value in ["2026-13", "2026-02-30", "ayer", "0000"]:
            self.assertIsNone(date_precision(value))

    def test_html_metadata_not_body_years(self):
        meta = extract_publication_metadata('<p>Un estudio de 2020</p><meta name="author" content="Ana"><meta property="article:modified_time" content="2026-10-05">')
        self.assertEqual(meta["author"]["value"], ["Ana"])
        self.assertEqual(meta["publication_date"]["state"], "not_found")

    def test_conflicting_dates_preserved(self):
        meta = extract_publication_metadata('<meta property="article:published_time" content="2020-01-01"><meta property="article:published_time" content="2021-01-01">')
        row = normalize_record(self.row(record_information=meta))
        self.assertEqual(meta["publication_date"]["state"], "conflicting")
        self.assertFalse(eligibility(row, "temporal")[0])

    def test_jsonld_multiple_authors_and_bad_json(self):
        page = '<script type="application/ld+json">{"@type":"NewsArticle","author":[{"name":"Ana"},{"name":"Luis"}],"datePublished":"2020"}</script><script type="application/ld+json">bad</script>'
        meta = extract_publication_metadata(page)
        self.assertEqual(meta["author"]["value"], ["Ana", "Luis"])
        self.assertEqual(meta["publication_date"]["precision"], "year")

    def test_domain_is_not_author_or_named_publisher(self):
        row = normalize_record(self.row(medium="example.org"))
        self.assertEqual(row["record_information"]["publication_source"]["state"], "inferred")
        self.assertFalse(eligibility(row, "source_comparison")[0])

    def test_partial_text_is_reported(self):
        row = normalize_record(self.row(status="ok_partial"))
        self.assertEqual(eligibility(row, "thematic"), (True, "fragmento"))

    def test_blocked_record_is_not_zero_or_absence(self):
        row = normalize_record(self.row(status="fetch_error"))
        self.assertFalse(eligibility(row, "thematic")[0])
        self.assertEqual(row["record_information"]["text"]["state"], "not_evaluable")

    def test_migration_is_idempotent_and_nonmutating(self):
        row = self.row(year=2020)
        old = copy.deepcopy(row)
        migrated = normalize_record(row)
        self.assertEqual(row, old)
        self.assertEqual(normalize_record(migrated), migrated)

    def test_empty_coverage_has_null_ratio(self):
        report = coverage_report([])
        self.assertIsNone(report["analyses"]["thematic"]["coverage"])

    def test_temporal_coverage_counts_actual_subset(self):
        report = coverage_report([self.row(published_date="2020", source_api="crossref"), self.row(url="https://example.org/two")])
        self.assertEqual(report["analyses"]["temporal"]["eligible"], 1)
        self.assertEqual(report["analyses"]["temporal"]["total"], 2)

    def test_unvalidated_and_fabricated_claims_excluded(self):
        for claim in [self.claim(review_status="candidate"), self.claim(quote="Texto inventado")]:
            row = self.row(claims=[claim])
            self.assertFalse(eligibility(row, "claims")[0])
            self.assertFalse(descriptive_models([row])["actor_concept_stance"])

    def test_missing_actor_still_allows_validated_claim(self):
        row = self.row(claims=[self.claim(speaker=None)])
        self.assertTrue(eligibility(row, "claims")[0])
        self.assertFalse(eligibility(row, "actor_stance")[0])

    def test_support_rejection_do_not_cancel(self):
        row = self.row(claims=[self.claim(), self.claim(stance="reject")])
        positions = descriptive_models([row])["actor_concept_stance"]
        self.assertEqual({p["stance"] for p in positions}, {"support", "reject"})

    def test_unknown_concept_is_null_not_zero(self):
        one = self.row(claims=[self.claim()])
        two = self.row(url="https://example.org/two", claims=[self.claim(concept="formación")])
        matrix = descriptive_models([one, two])["document_concept_matrix"]
        self.assertEqual(sum(r["value"] is None for r in matrix), 2)
        self.assertFalse(any(r["value"] == 0 for r in matrix))

    def test_reviewed_absence_has_zero_and_correct_denominator(self):
        one = self.row(claims=[self.claim()])
        two = self.row(url="https://example.org/two", claims=[self.claim(concept="formación")], reviewed_concepts=["empleo"])
        summary = descriptive_models([one, two])["source_concept_summary"]
        item = next(r for r in summary if r["concept"] == "empleo")
        self.assertEqual(item["documents_reviewed_for_concept"], 2)
        self.assertEqual(item["proportion"], .5)

    def test_reviewer_input_quote_check_and_stable_identity(self):
        row = normalize_record(self.row())
        review = {"document_id": row["document_id"], "claims": [self.claim()],
                  "record_information": {"publication_date": cell("2020", "explicit", "Fecha revisada en fuente")}}
        result = apply_reviews([row], [review])[0]
        self.assertEqual(result["year"], 2020)
        self.assertEqual(result["document_id"], row["document_id"])
        review["claims"][0]["quote"] = "Inventado"
        with self.assertRaises(ValueError):
            apply_reviews([row], [review])

    def test_bibliographic_missing_dates_not_filled_from_search(self):
        params = dict(query="tatuaje", clean_variants=[], geographic_scope="Global", clean_geographic_terms=[], year=2026, min_text_chars=40)
        for builder in [openalex_record, crossref_record]:
            record = builder({}, **params)
            self.assertEqual(record.published_date, "")

    def test_crossref_month_precision_and_pdf_link(self):
        params = dict(query="x", clean_variants=[], geographic_scope="Global", clean_geographic_terms=[], year=2026, min_text_chars=40)
        item = {"title": ["Un título muy largo para contar con texto suficiente en este ejemplo"],
                "published": {"date-parts": [[2020, 3]]}, "link": [{"URL": "https://example.org/a.pdf"}]}
        record = crossref_record(item, **params)
        self.assertEqual(record.published_date, "2020-03")
        self.assertEqual(record.status, "ok_partial")

    def test_cli_migration_preserves_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "input.json"
            src.write_text(json.dumps([self.row(year=2020)]))
            original = src.read_bytes()
            proc = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "scripts/audit_evidence.py"), str(src), "--output", str(Path(tmp) / "out")], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(src.read_bytes(), original)
            rows = load_records_from_path(Path(tmp) / "out")
            self.assertEqual(len(rows), 1)
            self.assertIsNone(rows[0]["year"])

    def test_mixed_missing_years_can_be_counted_without_sort_error(self):
        rows = [normalize_record(self.row()), normalize_record(self.row(published_date="2020", source_api="crossref"))]
        self.assertEqual(len(count_rows(rows, ["year"])), 2)

    def test_directory_manifest_is_not_a_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "manifest.json").write_text(json.dumps({"system": "SIAN", "total": 7}))
            (Path(tmp) / "document.json").write_text(json.dumps(self.row()))
            self.assertEqual(len(load_records_from_path(tmp)), 1)


if __name__ == "__main__":
    unittest.main()
