#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from narrative_analysis import (  # noqa: E402
    annealing_weighted_node_cover,
    build_narrative_event_graph,
    extract_narrative_events,
    filter_records,
    genetic_weighted_node_cover,
    greedy_weighted_node_cover,
    load_records_from_path,
    musical_composition_weighted_node_cover,
    rows_to_csv,
)


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Solve local weighted narrative node cover.")
    parser.add_argument("--input", default=str(ROOT / "news_output"), help="JSON/JSONL file or output folder.")
    parser.add_argument("--output-dir", default=str(ROOT / "solver_output"))
    parser.add_argument("--method", choices=["greedy", "genetic", "annealing", "mmc"], default="greedy")
    parser.add_argument("--max-nodes", type=int, default=12)
    parser.add_argument("--min-edge-weight", type=int, default=1)
    parser.add_argument("--node-types", default="actor,narrative_stage,source,source_type")
    parser.add_argument("--edge-types", default="", help="Comma separated edge types; empty means all.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--generations", type=int, default=120)
    parser.add_argument("--iterations", type=int, default=2000)
    parser.add_argument("--composers", type=int, default=12)
    parser.add_argument("--arrangements", type=int, default=120)
    parser.add_argument("--edge-cost-weight", type=float, default=1.0)
    args = parser.parse_args()

    records = load_records_from_path(args.input)
    selected = filter_records(records)
    events = extract_narrative_events(selected)
    graph = build_narrative_event_graph(events, min_edge_weight=args.min_edge_weight)

    allowed_types = parse_csv(args.node_types)
    edge_types = parse_csv(args.edge_types)
    if args.method == "genetic":
        cover = genetic_weighted_node_cover(
            graph,
            max_nodes=args.max_nodes,
            allowed_node_types=allowed_types,
            edge_types=edge_types,
            generations=args.generations,
            seed=args.seed,
            edge_cost_weight=args.edge_cost_weight,
        )
    elif args.method == "annealing":
        cover = annealing_weighted_node_cover(
            graph,
            max_nodes=args.max_nodes,
            allowed_node_types=allowed_types,
            edge_types=edge_types,
            iterations=args.iterations,
            seed=args.seed,
            edge_cost_weight=args.edge_cost_weight,
        )
    elif args.method == "mmc":
        cover = musical_composition_weighted_node_cover(
            graph,
            max_nodes=args.max_nodes,
            allowed_node_types=allowed_types,
            edge_types=edge_types,
            composers=args.composers,
            max_arrangements=args.arrangements,
            seed=args.seed,
            edge_cost_weight=args.edge_cost_weight,
        )
    else:
        cover = greedy_weighted_node_cover(
            graph,
            max_nodes=args.max_nodes,
            allowed_node_types=allowed_types,
            edge_types=edge_types,
            objective="maximize_node_minimize_edge",
        )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "narrative_events.csv").write_bytes(rows_to_csv(events))
    (output_dir / "narrative_graph_nodes.csv").write_bytes(rows_to_csv(graph["nodes"]))
    (output_dir / "narrative_graph_edges.csv").write_bytes(rows_to_csv(graph["edges"]))
    (output_dir / f"weighted_node_cover_{args.method}.csv").write_bytes(rows_to_csv(cover["selected_nodes"]))
    (output_dir / f"weighted_node_cover_pareto_{args.method}.csv").write_bytes(rows_to_csv(cover.get("pareto_front", [])))
    print({"records": len(records), "events": len(events), "graph": graph["stats"], "cover": cover["stats"]})


if __name__ == "__main__":
    main()
