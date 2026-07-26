from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from news_spider import build_query, classify_source_type, month_periods  # noqa: E402
from narrative_analysis import _cover_problem_data, _evaluate_cover_solution  # noqa: E402
from source_profiles import source_access_policy  # noqa: E402


class CoreBehaviorTests(unittest.TestCase):
    def test_month_periods_respects_bounds(self) -> None:
        periods = list(month_periods(2021, 2021, start_month=2, end_month=4))
        self.assertEqual([period[0].month for period in periods], [2, 3, 4])

    def test_source_type_classification_examples(self) -> None:
        self.assertEqual(
            classify_source_type({}, "https://www.jornada.com.mx/noticia/2020/01/12/cultura/x", "La Jornada")[0],
            "news",
        )
        self.assertEqual(
            classify_source_type({}, "https://www.gob.mx/salud/documentos/x", "Gobierno de México")[0],
            "institutional_report",
        )
        self.assertEqual(
            classify_source_type({}, "https://www.reddit.com/r/mexico/comments/x", "Reddit")[0],
            "forum",
        )
        self.assertEqual(
            classify_source_type({}, "https://doi.org/10.1000/example", "doi.org")[0],
            "scientific_article",
        )

    def test_build_query_keeps_exclusions_and_domains(self) -> None:
        query = build_query(
            "tatuaje",
            ["jornada.com.mx"],
            variants=["tatuajes", "arte corporal"],
            geographic_terms=["Mexico", "Mexican"],
            exclude_terms=["cigar", "colonoscopic tattooing"],
            exclude_domains=["halfwheel.com"],
        )
        self.assertIn("tatuaje", query)
        self.assertIn("domain:jornada.com.mx", query)
        self.assertIn("-cigar", query)
        self.assertIn('-"colonoscopic tattooing"', query)
        self.assertIn("-domain:halfwheel.com", query)

    def test_removal_impact_reports_preserved_and_removed_edges(self) -> None:
        graph = {
            "nodes": [
                {"id": "a", "node_type": "concept", "score": 3},
                {"id": "b", "node_type": "concept", "score": 2},
                {"id": "c", "node_type": "concept", "score": 1},
            ],
            "edges": [
                {"source": "a", "target": "b", "weight": 0.7},
                {"source": "b", "target": "c", "weight": 0.3},
            ],
        }
        problem = _cover_problem_data(graph, coverage_mode="removal_impact")
        result = _evaluate_cover_solution(["a"], problem)
        self.assertEqual(result["removed_edges"], 1)
        self.assertEqual(result["preserved_edges"], 1)
        self.assertAlmostEqual(result["removed_edge_weight_share"], 0.7)
        self.assertAlmostEqual(result["preserved_edge_weight_share"], 0.3)

    def test_source_access_policy_marks_partial_and_paywall(self) -> None:
        self.assertEqual(source_access_policy("https://www.proceso.com.mx/x")["access"], "partial")
        self.assertEqual(source_access_policy("https://www.nytimes.com/2020/01/01/x.html")["access"], "paywall")


if __name__ == "__main__":
    unittest.main()
