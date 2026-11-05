"""Run SIAN's analysis stages outside the interactive app."""
import argparse
import csv
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import zipfile

from corpus_contract import merge_rows
from lexical_figures import lexical_figure_files, network_figure_files
import narrative_analysis as na
from structural_narrative import extract_structural_propositions, build_structural_influence_graph
from web_corpus_io import iter_corpus_upload


def csv_bytes(rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def run(corpus, output, budget, seed):
    print("1/4 Ingesta y auditoría", flush=True)
    data = corpus.read_bytes()
    fingerprint = sha256(data).hexdigest()
    input_count = 0

    def incoming():
        nonlocal input_count
        for row in iter_corpus_upload(data, corpus.name):
            input_count += 1
            yield row

    unique = merge_rows(incoming())
    del data
    records = [row for row in unique if
               (row.get("status") == "ok" and na.record_text(row).strip()) or
               (row.get("status") == "ok_partial" and len(na.record_text(row).strip()) >= 100)]
    if not records:
        raise ValueError("El corpus no contiene texto apto para análisis.")
    audit = {
        "records_input": input_count, "records_unique": len(unique), "records_analyzed": len(records),
        "source_types": dict(Counter(row.get("source_type") or "unknown" for row in records)),
        "years": dict(Counter(str(row.get("year") or "sin año") for row in records)),
    }
    print("2/4 Análisis léxico", flush=True)
    terms = na.top_terms(records, top_n=100)
    bigrams = na.top_ngrams(records, n=2, top_n=100)
    trigrams = na.top_ngrams(records, n=3, top_n=100)
    print("3/4 Redes y optimización", flush=True)
    events = na.extract_narrative_events(records)
    propositions = extract_structural_propositions(records)
    narrative = na.build_narrative_event_graph(events)
    networks = [
        ("narrativa", "Red narrativa", narrative),
        ("conocimiento", "Grafo de conocimiento", na.build_knowledge_graph(records)),
        ("semantica", "Red semántica", na.build_cooccurrence_network(records)),
        ("estructural", "Red estructural", build_structural_influence_graph(propositions)),
    ]
    solvers = (na.weighted_sum_greedy_sweep_node_cover, na.moea_weighted_node_cover,
               na.mosa_weighted_node_cover, na.mmc_multiobjective_weighted_node_cover)
    covers = [solve(narrative, evaluation_budget=budget, seed=seed, max_nodes=12, min_nodes=3,
                    min_node_weight_share=.005, max_removed_edge_weight_share=.10,
                    allowed_node_types=["actor", "narrative_stage", "narrative_flow",
                                        "source", "source_type", "document"])
              for solve in solvers] if narrative["edges"] else []
    print("4/4 Exportación", flush=True)
    manifest = {
        "format": "sian-agent-results-v1", "generated_at": datetime.now(timezone.utc).isoformat(),
        "revision": os.getenv("GITHUB_SHA"), "corpus_sha256": fingerprint,
        "evaluation_budget": budget, "seed": seed, **audit,
        "networks": {name: {"nodes": len(graph["nodes"]), "edges": len(graph["edges"])}
                     for name, _, graph in networks},
    }
    tables = {"monogramas": terms, "bigramas": bigrams, "trigramas": trigrams,
              "eventos": events, "proposiciones": propositions,
              "cubridor": [cover["stats"] for cover in covers]}
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("optimizacion.json", json.dumps(covers, ensure_ascii=False, default=str))
        for name, rows in tables.items():
            archive.writestr(f"datos/{name}.csv", csv_bytes(rows))
        for name, _, graph in networks:
            for kind in ("nodes", "edges"):
                archive.writestr(f"datos/{name}_{kind}.csv", csv_bytes(graph[kind]))
        figures = lexical_figure_files(terms, bigrams, trigrams, len(records))
        figures.update(network_figure_files(networks))
        for name, contents in figures.items():
            archive.writestr(name, contents)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--budget", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.budget < 1:
        parser.error("--budget debe ser positivo")
    if args.corpus.resolve() == args.output.resolve():
        parser.error("La entrada y la salida deben ser archivos distintos")
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    try:
        run(args.corpus, temporary, args.budget, args.seed)
        temporary.replace(args.output)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
