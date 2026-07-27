from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
import json
import hashlib
import queue
import random
import re
import shutil
import statistics
import threading
import time
from dataclasses import asdict
from pathlib import Path
import math
import html as html_lib

import streamlit as st
import streamlit.components.v1 as components

from narrative_analysis import (
    actor_counts,
    build_narrative_event_graph,
    build_cooccurrence_network,
    adaptive_topic_groups_from_graph,
    build_knowledge_graph,
    count_rows,
    enrich_records_for_analysis,
    extract_narrative_events,
    filter_records,
    frame_counts,
    frame_counts_by_year,
    idea_groups_for_records,
    idea_group_counts,
    idea_group_counts_by_year,
    idea_group_document_matrix,
    load_records_from_path,
    pareto_terms,
    parse_idea_groups,
    annealing_weighted_node_cover,
    genetic_weighted_node_cover,
    greedy_weighted_node_cover,
    mmc_multiobjective_weighted_node_cover,
    moea_weighted_node_cover,
    mosa_weighted_node_cover,
    musical_composition_weighted_node_cover,
    rows_to_csv,
    stopword_candidates,
    narrative_event_summary,
    ngram_dimension_matrix,
    tokenize,
    top_ngrams,
    top_terms,
    weighted_sum_greedy_sweep_node_cover,
)
from news_spider import (
    build_query,
    classify_source_type,
    crawl_news,
    document_dedup_key_from_values,
    evidence_rank_for_source_type,
)
from source_profiles import (
    domains_from_seed_file as catalog_domains_from_seed_file,
    profile_domains,
    source_profile_rows,
    source_strategy_rows_from_seed_file as catalog_source_strategy_rows_from_seed_file,
)
from structural_narrative import (
    build_structural_influence_graph,
    technical_traceability_rows,
    extract_structural_propositions,
    smart_data_nucleus,
    structural_summary,
)


st.set_page_config(page_title="SIAN · Smart Data Narrativo", layout="wide")

APP_ROOT = Path(__file__).resolve().parent


def json_default(value):
    if isinstance(value, Path):
        return str(value)
    return str(value)


def stable_json_hash(value) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=json_default)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def row_document_dedup_key(row: dict) -> str:
    return document_dedup_key_from_values(
        url=str(row.get("url") or ""),
        title=str(row.get("title") or ""),
        year=row.get("year") or "",
        medium=str(row.get("medium") or ""),
        pdf_url=str(row.get("pdf_url") or ""),
    ) or str(row.get("url") or row.get("title") or stable_json_hash(row))


def deduplicate_rows_for_analysis(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    kept: dict[str, dict] = {}
    duplicates: list[dict] = []
    for row in rows:
        key = row_document_dedup_key(row)
        if key not in kept:
            copy = dict(row)
            copy["dedup_key"] = key
            kept[key] = copy
            continue
        duplicate = dict(row)
        duplicate["dedup_key"] = key
        duplicate["duplicate_of"] = kept[key].get("url") or kept[key].get("title") or key
        duplicates.append(duplicate)
        prior = kept[key]
        prior["variant_rubric"] = ", ".join(
            merge_unique([str(prior.get("variant_rubric") or ""), str(row.get("variant_rubric") or "")])
        )
        prior["variant_term"] = ", ".join(
            merge_unique([str(prior.get("variant_term") or ""), str(row.get("variant_term") or "")])
        )
        prior["source_collection"] = ", ".join(
            merge_unique([str(prior.get("source_collection") or ""), str(row.get("source_collection") or "")])
        )
    return list(kept.values()), duplicates


def save_run_manifest(config: dict) -> None:
    """Persist reproducibility metadata before the worker starts."""
    output_dir = Path(config.get("output_dir") or "news_output")
    output_dir.mkdir(parents=True, exist_ok=True)
    query_plan = list(config.get("run_plan") or [])
    manifest_config = {key: value for key, value in config.items() if key != "run_plan"}
    manifest = {
        "system": "SIAN",
        "manifest_version": 1,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "execution": "local_streamlit",
        "analysis_policy": "heuristic_local_no_external_llm",
        "query_plan_steps": len(query_plan),
        "query_plan_hash": stable_json_hash(query_plan) if query_plan else "",
        "config_hash": stable_json_hash(manifest_config),
        "config": manifest_config,
        "notes": [
            "Los textos no se envían a modelos externos.",
            "La corrida secuencial usa muestreo reproducible por semilla.",
            "Reddit RSS es opcional y no debe ser fuente principal de conversación social.",
            "Las salidas heurísticas requieren validación humana.",
        ],
    }
    (output_dir / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=json_default),
        encoding="utf-8",
    )
    if query_plan:
        (output_dir / "query_plan.json").write_text(
            json.dumps(query_plan, ensure_ascii=False, indent=2, default=json_default),
            encoding="utf-8",
        )


def update_run_manifest(config: dict, status: str, rows: list[dict] | None = None, error: str = "") -> None:
    """Update manifest at the end of a local run for reproducibility/audit."""
    output_dir = Path(config.get("output_dir") or "news_output")
    manifest_path = output_dir / "run_manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}
    else:
        manifest = {"system": "SIAN", "manifest_version": 1}
    rows = rows or []
    manifest.update(
        {
            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "status": status,
            "records_total": len(rows),
            "records_usable": sum(1 for row in rows if has_usable_text(row)),
            "records_by_source_type": dict(Counter(str(row.get("source_type") or "unknown") for row in rows)),
            "records_by_status": dict(Counter(str(row.get("status") or "unknown") for row in rows)),
            "records_hash": stable_json_hash(rows) if rows else "",
            "error": error,
        }
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")


def is_safe_clear_target(path_value: str) -> tuple[bool, Path, str]:
    target = Path(path_value or "news_output").expanduser()
    try:
        resolved = target.resolve()
        app_resolved = APP_ROOT.resolve()
        cwd_resolved = Path.cwd().resolve()
    except Exception as exc:
        return False, target, f"Ruta inválida: {exc}"
    allowed_roots = [app_resolved, cwd_resolved]
    if not any(resolved == root or root in resolved.parents for root in allowed_roots):
        return False, resolved, "Por seguridad sólo se limpian carpetas dentro del proyecto local."
    if resolved.name not in {"news_output", "news_output_recleaned", "solver_output"} and "news_output" not in resolved.parts:
        return False, resolved, "La carpeta debe llamarse news_output, news_output_recleaned, solver_output o estar dentro de news_output."
    if resolved in {Path.home().resolve(), app_resolved, cwd_resolved, Path("/")}:
        return False, resolved, "No se permite limpiar una raíz de trabajo."
    return True, resolved, ""


def init_state() -> None:
    defaults = {
        "spider_thread": None,
        "spider_stop": None,
        "spider_queue": None,
        "spider_running": False,
        "spider_logs": [],
        "spider_rows": [],
        "spider_error": "",
        "spider_config": {},
        "loaded_path": "",
        "idea_group_text": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def drain_queue() -> None:
    q = st.session_state.get("spider_queue")
    if q is None:
        return
    while True:
        try:
            kind, payload = q.get_nowait()
        except queue.Empty:
            break
        if kind == "progress":
            st.session_state.spider_logs.append(str(payload))
        elif kind == "done":
            st.session_state.spider_rows = payload
            st.session_state.spider_running = False
            st.session_state.spider_logs.append("Finished.")
        elif kind == "error":
            st.session_state.spider_error = str(payload)
            st.session_state.spider_running = False
            st.session_state.spider_logs.append(f"ERROR: {payload}")


def start_worker(config: dict) -> None:
    save_run_manifest(config)
    stop_event = threading.Event()
    q: queue.Queue = queue.Queue()

    def progress(message: str) -> None:
        q.put(("progress", message))

    def worker() -> None:
        try:
            if config.get("run_plan"):
                all_rows: list[dict] = []
                sequential_counts: Counter = Counter()
                total_steps = len(config["run_plan"])
                for index, step_config in enumerate(config["run_plan"], start=1):
                    if stop_event.is_set():
                        progress("Stop requested before next planned run.")
                        break
                    target_type = str(step_config.get("target_source_type") or "")
                    target_year = int(step_config.get("start_year") or 0)
                    cap = int(step_config.get("max_records_per_source_type_year") or 0)
                    minimum = int(step_config.get("target_min_per_source_type_year") or 0)
                    if target_type and cap and sequential_counts[(target_year, target_type)] >= cap:
                        progress(
                            f"Sequential skip {index}/{total_steps}: quota reached "
                            f"{target_year} · {target_type} · "
                            f"{sequential_counts[(target_year, target_type)]}/min {minimum if minimum else 0} · max {cap}"
                        )
                        continue
                    progress(
                        f"Sequential run {index}/{total_steps}: "
                        f"{step_config.get('variant_rubric', 'general')} · "
                        f"{step_config.get('variant_term', step_config.get('query', ''))} · "
                        f"{step_config.get('source_collection', 'mixed')} · "
                        f"{step_config.get('period_label', step_config.get('start_year'))} · "
                        f"{sequential_counts[(target_year, target_type)]}/min {minimum if minimum else 0} · "
                        f"max {cap if cap else '∞'}"
                    )
                    records = crawl_news(
                        query=step_config["query"],
                        start_year=step_config["start_year"],
                        end_year=step_config["end_year"],
                        start_month=step_config.get("start_month"),
                        end_month=step_config.get("end_month"),
                        domains=step_config["domains"],
                        query_variants=step_config["query_variants"],
                        geographic_scope=step_config["geographic_scope"],
                        geographic_terms=step_config["geographic_terms"],
                        exclude_terms=step_config["exclude_terms"],
                        exclude_domains=step_config["exclude_domains"],
                        source_modes=step_config["source_modes"],
                        output_dir=Path(step_config["output_dir"]),
                        max_records_per_month=step_config["max_records_per_month"],
                        max_records_per_source_type_year=step_config["max_records_per_source_type_year"],
                        target_min_per_source_type_year=step_config.get("target_min_per_source_type_year", 0),
                        required_source_types=step_config.get("required_source_types", []),
                        accept_source_types=step_config.get("accept_source_types", []),
                        seed_url_file=step_config.get("seed_url_file") or None,
                        download_pdfs=step_config.get("download_pdfs", False),
                        strict_open_access_articles=step_config.get("strict_open_access_articles", True),
                        search_delay_seconds=step_config["search_delay_seconds"],
                        delay_seconds=step_config["delay_seconds"],
                        min_text_chars=step_config["min_text_chars"],
                        progress=progress,
                        stop_requested=stop_event.is_set,
                    )
                    for record in records:
                        row = asdict(record)
                        row["variant_rubric"] = step_config.get("variant_rubric", "")
                        row["variant_term"] = step_config.get("variant_term", "")
                        row["variant_term_index"] = step_config.get("variant_term_index", "")
                        row["source_collection"] = step_config.get("source_collection", "")
                        all_rows.append(row)
                        if has_usable_text(row):
                            sequential_counts[(int(row.get("year") or target_year), str(row.get("source_type") or target_type))] += 1
                    progress(
                        f"Finished sequential run {index}/{total_steps}: "
                        f"{step_config.get('variant_rubric', 'general')} · "
                        f"{step_config.get('variant_term', step_config.get('query', ''))} · "
                        f"{step_config.get('source_collection', 'mixed')} · "
                        f"{step_config.get('period_label', step_config.get('start_year'))} · {len(records)} records"
                    )
                merged: dict[str, dict] = {}
                for row in all_rows:
                    key = row_document_dedup_key(row)
                    if not key:
                        continue
                    if key not in merged:
                        merged[key] = row
                    else:
                        prior = merged[key]
                        rubrics = merge_unique(
                            [
                                str(prior.get("variant_rubric") or ""),
                                str(row.get("variant_rubric") or ""),
                            ]
                        )
                        terms = merge_unique(
                            [
                                str(prior.get("variant_term") or ""),
                                str(row.get("variant_term") or ""),
                            ]
                        )
                        collections = merge_unique(
                            [
                                str(prior.get("source_collection") or ""),
                                str(row.get("source_collection") or ""),
                            ]
                        )
                        prior["variant_rubric"] = ", ".join(rubrics)
                        prior["variant_term"] = ", ".join(terms)
                        prior["source_collection"] = ", ".join(collections)
                output_dir = Path(config["output_dir"])
                output_dir.mkdir(parents=True, exist_ok=True)
                merged_rows = sorted(
                    merged.values(),
                    key=lambda item: (item.get("year") or 0, item.get("source_type") or "", item.get("medium") or ""),
                )
                (output_dir / "news_records_sequential_merged.json").write_text(
                    json.dumps(merged_rows, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                (output_dir / "news_records_sequential_merged.jsonl").write_text(
                    "\n".join(json.dumps(row, ensure_ascii=False) for row in merged_rows) + ("\n" if merged_rows else ""),
                    encoding="utf-8",
                )
                update_run_manifest(config, "finished", merged_rows)
                q.put(("done", merged_rows))
            else:
                records = crawl_news(
                    query=config["query"],
                    start_year=config["start_year"],
                    end_year=config["end_year"],
                    domains=config["domains"],
                    query_variants=config["query_variants"],
                    geographic_scope=config["geographic_scope"],
                    geographic_terms=config["geographic_terms"],
                    exclude_terms=config["exclude_terms"],
                    exclude_domains=config["exclude_domains"],
                    source_modes=config["source_modes"],
                    output_dir=Path(config["output_dir"]),
                    max_records_per_month=config["max_records_per_month"],
                    max_records_per_source_type_year=config["max_records_per_source_type_year"],
                    target_min_per_source_type_year=config.get("target_min_per_source_type_year", 0),
                    required_source_types=config.get("required_source_types", []),
                    accept_source_types=config.get("accept_source_types", []),
                    seed_url_file=config.get("seed_url_file") or None,
                    download_pdfs=config.get("download_pdfs", False),
                    strict_open_access_articles=config.get("strict_open_access_articles", True),
                    search_delay_seconds=config["search_delay_seconds"],
                    delay_seconds=config["delay_seconds"],
                    min_text_chars=config["min_text_chars"],
                    progress=progress,
                    stop_requested=stop_event.is_set,
                )
                rows = [asdict(record) for record in records]
                update_run_manifest(config, "finished", rows)
                q.put(("done", rows))
        except Exception as exc:  # noqa: BLE001
            update_run_manifest(config, "error", [], str(exc))
            q.put(("error", str(exc)))

    thread = threading.Thread(target=worker, daemon=True)
    st.session_state.spider_thread = thread
    st.session_state.spider_stop = stop_event
    st.session_state.spider_queue = q
    st.session_state.spider_running = True
    st.session_state.spider_logs = ["Starting spider..."]
    st.session_state.spider_rows = []
    st.session_state.spider_error = ""
    st.session_state.spider_config = dict(config)
    thread.start()


def request_stop() -> None:
    stop_event = st.session_state.get("spider_stop")
    if stop_event is not None:
        stop_event.set()
        st.session_state.spider_logs.append("Stop requested. Waiting for the current network call to finish...")


def load_saved_rows(path: str) -> list[dict]:
    rows = load_records_from_path(path)
    st.session_state.spider_rows = rows
    st.session_state.loaded_path = path
    return rows


def candidate_analysis_paths(path: str) -> list[str]:
    base = Path(path or "news_output")
    if base.is_dir() or not base.suffix:
        candidates = [
            base / "news_records_sequential_merged.json",
            base / "news_records_merged.json",
            base / "news_records.json",
            base / "news_records.jsonl",
            base,
        ]
    else:
        candidates = [base]
    return [str(item) for item in candidates]


def autoload_saved_rows(path: str) -> tuple[list[dict], str]:
    for candidate in candidate_analysis_paths(path):
        try:
            rows = load_records_from_path(candidate)
        except Exception:
            continue
        if rows:
            st.session_state.spider_rows = rows
            st.session_state.loaded_path = candidate
            return rows, candidate
    return [], ""


def source_output_dir(base_output_dir: str, source_key: str) -> str:
    return str(Path(base_output_dir) / "by_source" / source_key)


def safe_key(value: str) -> str:
    normalized = normalize_local(value)
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in normalized)
    return "_".join(part for part in cleaned.split("_") if part)[:80] or "item"


def domains_from_seed_file(seed_file: str) -> list[str]:
    return catalog_domains_from_seed_file(seed_file)


def source_strategy_rows_from_seed_file(seed_file: str, query: str, variants: list[str], geographic_terms: list[str]) -> list[dict]:
    return catalog_source_strategy_rows_from_seed_file(seed_file, query, variants, geographic_terms)


def merge_source_bases(base_output_dir: str, source_keys: list[str]) -> list[dict]:
    merged: dict[str, dict] = {}
    for source_key in source_keys:
        rows = load_records_from_path(source_output_dir(base_output_dir, source_key))
        for row in rows:
            key = row_document_dedup_key(row)
            if not key:
                continue
            if key not in merged:
                copy = dict(row)
                copy["source_collection"] = source_key
                merged[key] = copy
            else:
                prior = merged[key]
                prior["source_collection"] = ", ".join(
                    merge_unique([str(prior.get("source_collection") or ""), source_key])
                )
    output_dir = Path(base_output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    merged_rows = sorted(merged.values(), key=lambda item: (item.get("year") or 0, item.get("source_type") or "", item.get("medium") or ""))
    (output_dir / "news_records_merged.json").write_text(json.dumps(merged_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "news_records_merged.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in merged_rows) + ("\n" if merged_rows else ""),
        encoding="utf-8",
    )
    return merged_rows


def actor_validation_path(analysis_path: str) -> Path:
    path = Path(analysis_path)
    base = path if path.suffix == "" else path.parent
    return base / "actor_validation.json"


def load_actor_validations(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def save_actor_validations(path: Path, validations: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(validations, ensure_ascii=False, indent=2), encoding="utf-8")


def apply_actor_validations(event_rows: list[dict], validations: dict) -> list[dict]:
    rows = []
    for row in event_rows:
        copy = dict(row)
        validation = validations.get(copy.get("doc_key", ""), {})
        validated_actors = validation.get("validated_actors", [])
        copy["actors_auto"] = copy.get("actors", "")
        copy["actors_validated"] = ", ".join(validated_actors)
        copy["actor_validation_status"] = validation.get("status", "pending")
        copy["actor_validation_notes"] = validation.get("notes", "")
        copy["actor_validator"] = validation.get("validator", "")
        copy["actor_validated_at"] = validation.get("validated_at", "")
        if validated_actors and copy["actor_validation_status"] in {"accepted", "corrected"}:
            copy["actors"] = ", ".join(validated_actors)
        if copy["actor_validation_status"] == "rejected":
            copy["actors"] = ""
        rows.append(copy)
    return rows


def row_source_type(row: dict) -> str:
    if row.get("source_type"):
        return row.get("source_type", "other")
    source_type, _, _ = classify_source_type(
        article={},
        url=row.get("url", ""),
        medium=row.get("medium", ""),
        title=row.get("title", ""),
    )
    return source_type


def row_evidence(row: dict) -> tuple[str, int]:
    if row.get("evidence_level") and row.get("evidence_weight") is not None:
        return row.get("evidence_level", "low"), int(row.get("evidence_weight", 1) or 1)
    return evidence_rank_for_source_type(row_source_type(row))


MIN_PARTIAL_ANALYSIS_TEXT_CHARS = 100


def row_text_for_usability(row: dict) -> str:
    return str(row.get("text_normalized") or row.get("text_clean") or "")


def row_text_length_for_usability(row: dict) -> int:
    try:
        return int(row.get("text_length") or 0)
    except (TypeError, ValueError):
        return len(row_text_for_usability(row))


def has_usable_text(row: dict) -> bool:
    status = str(row.get("status") or "")
    text = row_text_for_usability(row)
    if status == "ok":
        return bool(text)
    if status == "ok_partial":
        return len(text) >= MIN_PARTIAL_ANALYSIS_TEXT_CHARS or row_text_length_for_usability(row) >= MIN_PARTIAL_ANALYSIS_TEXT_CHARS
    return False


def annual_news_coverage_rows(rows: list[dict], target_per_year: int = 100) -> list[dict]:
    years = sorted({int(row.get("year")) for row in rows if str(row.get("year", "")).isdigit()})
    coverage = []
    for year in years:
        year_rows = [row for row in rows if int(row.get("year") or 0) == year]
        usable_news = [
            row for row in year_rows
            if has_usable_text(row) and row_source_type(row) == "news"
        ]
        full_news = [row for row in usable_news if row.get("status") == "ok"]
        partial_news = [row for row in usable_news if row.get("status") in {"ok_partial", "too_short"}]
        coverage.append(
            {
                "year": year,
                "target_news": int(target_per_year),
                "usable_news": len(usable_news),
                "full_text_news": len(full_news),
                "partial_news": len(partial_news),
                "gap_to_target": max(0, int(target_per_year) - len(usable_news)),
                "coverage_ratio": round(len(usable_news) / max(1, int(target_per_year)), 3),
                "status": "ok" if len(usable_news) >= int(target_per_year) else "insufficient_sample",
            }
        )
    return coverage


def annual_source_type_coverage_rows(
    rows: list[dict],
    target_min_per_type_year: int = 1,
    max_per_type_year: int = 100,
) -> list[dict]:
    usable_rows = [row for row in rows if has_usable_text(row)]
    years = sorted({int(row.get("year")) for row in usable_rows if str(row.get("year", "")).isdigit()})
    source_types = ["news", "forum", "institutional_report", "scientific_article", "industry_report", "other"]
    output = []
    for year in years:
        year_rows = [row for row in usable_rows if int(row.get("year") or 0) == year]
        counts = Counter(row_source_type(row) for row in year_rows)
        row = {
            "year": year,
            "target_min_per_type": int(target_min_per_type_year),
            "max_per_type": int(max_per_type_year),
            "usable_total": len(year_rows),
        }
        for source_type in source_types:
            row[source_type] = counts.get(source_type, 0)
            row[f"{source_type}_gap_to_min"] = max(0, int(target_min_per_type_year) - row[source_type])
            row[f"{source_type}_cap_remaining"] = max(0, int(max_per_type_year) - row[source_type])
        row["organic_conversation_status"] = "ok" if row["forum"] > 0 else "missing_forums"
        missing_types = [source_type for source_type in source_types if row[source_type] < int(target_min_per_type_year)]
        row["source_balance_status"] = "ok" if not missing_types else "missing_or_under_target:" + ",".join(missing_types)
        output.append(row)
    return output


def source_type_targets_from_config(config: dict, fallback_min: int, fallback_max: int) -> dict[str, dict]:
    configured = config.get("target_min_by_source_type") or {}
    source_types = ["news", "forum", "institutional_report", "scientific_article", "industry_report", "other"]
    targets = {}
    for source_type in source_types:
        targets[source_type] = {
            "target_min": int(configured.get(source_type, fallback_min) if isinstance(configured, dict) else fallback_min),
            "target_max": int(config.get("max_records_per_source_type_year", fallback_max) or fallback_max),
        }
    return targets


def live_balance_counts_from_logs(logs: list[str]) -> Counter:
    """Recover live year/source counters from human-readable progress logs.

    The worker currently emits text progress. Until progress events are fully
    structured, this keeps the visible balance table synchronized while a run is
    still active.
    """
    counts: Counter = Counter()
    for message in logs or []:
        text = str(message)
        accepted = re.search(r"^(ok|ok_partial|too_short):\s*(\d{4})\s*·\s*([a-z_]+)\s+(\d+)/min", text)
        if accepted:
            status_name = accepted.group(1)
            year = int(accepted.group(2))
            source_type = accepted.group(3)
            count = int(accepted.group(4))
            length_match = re.search(r"·\s*len=(\d+)\b", text)
            length = int(length_match.group(1)) if length_match else None
            if status_name == "ok" or (
                status_name == "ok_partial"
                and length is not None
                and length >= MIN_PARTIAL_ANALYSIS_TEXT_CHARS
            ):
                counts[(year, source_type)] = max(counts[(year, source_type)], count)
            continue
        status = re.search(r"balance_status:\s*(\d{4})-\d{2}\s*·\s*(.*)", text)
        if status:
            year = int(status.group(1))
            for part in status.group(2).split(","):
                match = re.search(r"([a-z_]+)=(\d+)/min", part.strip())
                if match:
                    source_type = match.group(1)
                    count = int(match.group(2))
                    counts[(year, source_type)] = max(counts[(year, source_type)], count)
    return counts


def source_status_rows(rows: list[dict], config: dict | None = None) -> list[dict]:
    config = config or {}
    fallback_max = int(config.get("max_records_per_source_type_year", config.get("target_news_per_year", 100)) or 100)
    fallback_min = int(config.get("target_min_per_source_type_year", 0) or 0)
    targets = source_type_targets_from_config(config, fallback_min, fallback_max)
    grouped: dict[tuple[int, str, str], list[dict]] = defaultdict(list)
    for row in rows:
        if not str(row.get("year", "")).isdigit():
            continue
        grouped[(int(row.get("year")), row_source_type(row), row.get("medium") or "unknown")].append(row)
    output = []
    for (year, source_type, medium), group in sorted(grouped.items()):
        statuses = Counter(str(row.get("status") or "unknown") for row in group)
        usable = sum(1 for row in group if has_usable_text(row))
        target = targets.get(source_type, {"target_min": fallback_min, "target_max": fallback_max})
        output.append(
            {
                "year": year,
                "source_type": source_type,
                "medium": medium,
                "usable": usable,
                "ok": statuses.get("ok", 0),
                "ok_partial": statuses.get("ok_partial", 0),
                "too_short": statuses.get("too_short", 0),
                "fetch_error": statuses.get("fetch_error", 0),
                "error": statuses.get("error", 0),
                "target_min": target["target_min"],
                "gap_to_min": max(0, int(target["target_min"]) - usable),
                "target_max": target["target_max"],
                "cap_remaining": max(0, int(target["target_max"]) - usable),
                "source_api": ", ".join(sorted({str(row.get("source_api") or "") for row in group if row.get("source_api")})),
                "last_error": next((str(row.get("error") or "") for row in reversed(group) if row.get("error")), ""),
            }
        )
    return output


def render_source_status_dashboard(rows: list[dict], config: dict | None = None) -> None:
    status_rows = source_status_rows(rows, config)
    if not status_rows:
        return
    st.subheader("Estado operacional por fuente, año y tipo")
    st.caption(
        "Esta tabla convierte los logs de ejecución en estado auditable. "
        "`gap_to_min` muestra qué capas no alcanzaron la muestra mínima configurada."
    )
    by_type_year: dict[tuple[int, str], dict] = {}
    for row in status_rows:
        key = (row["year"], row["source_type"])
        if key not in by_type_year:
            by_type_year[key] = {
                "year": row["year"],
                "source_type": row["source_type"],
                "usable": 0,
                "ok": 0,
                "ok_partial": 0,
                "too_short": 0,
                "fetch_error": 0,
                "error": 0,
                "target_min": row["target_min"],
                "target_max": row["target_max"],
            }
        target = by_type_year[key]
        for field in ["usable", "ok", "ok_partial", "too_short", "fetch_error", "error"]:
            target[field] += int(row.get(field, 0) or 0)
    summary_rows = []
    for row in by_type_year.values():
        row["gap_to_min"] = max(0, int(row["target_min"]) - int(row["usable"]))
        row["cap_remaining"] = max(0, int(row["target_max"]) - int(row["usable"]))
        row["status"] = "ok" if row["gap_to_min"] == 0 else "under_target"
        summary_rows.append(row)
    summary_rows = sorted(summary_rows, key=lambda item: (item["year"], item["source_type"]))
    st.dataframe(summary_rows, use_container_width=True)
    with st.expander("Detalle por medio"):
        st.dataframe(status_rows, use_container_width=True)


def corpus_social_balance_diagnostic(rows: list[dict]) -> dict:
    usable_rows = [row for row in rows if has_usable_text(row)]
    counts = Counter(row_source_type(row) for row in usable_rows)
    total = max(1, len(usable_rows))
    scientific_share = counts.get("scientific_article", 0) / total
    has_public_layer = counts.get("news", 0) > 0
    has_organic_layer = counts.get("forum", 0) > 0
    if scientific_share >= 0.8 and (not has_public_layer or not has_organic_layer):
        status = "not_valid_for_social_narrative"
    elif not has_public_layer or not has_organic_layer:
        status = "incomplete_social_layers"
    else:
        status = "social_layers_present"
    return {
        "usable_total": len(usable_rows),
        "news": counts.get("news", 0),
        "forum": counts.get("forum", 0),
        "scientific_article": counts.get("scientific_article", 0),
        "industry_report": counts.get("industry_report", 0),
        "other": counts.get("other", 0),
        "scientific_share": round(scientific_share, 4),
        "status": status,
    }


POSITIVE_SENTIMENT_TERMS = {
    "aceptacion", "aceptación", "aceptado", "admiracion", "admiración", "alegria", "alegría",
    "apoyo", "atractivo", "autonomia", "autonomía", "belleza", "beneficio", "bienestar",
    "celebracion", "celebración", "confianza", "creatividad", "cuidado", "deseable",
    "digno", "empoderamiento", "expresion", "expresión", "favorable", "feliz", "identidad",
    "inclusion", "inclusión", "libertad", "mejora", "orgullo", "positivo", "reconocimiento",
    "respeto", "seguro", "solidaridad", "valor", "valioso",
    "acceptance", "accepted", "admiration", "autonomy", "beautiful", "beauty", "benefit",
    "care", "celebration", "confidence", "creative", "creativity", "desirable", "empowerment",
    "expression", "favorable", "freedom", "happy", "improvement", "inclusion", "positive",
    "pride", "recognition", "respect", "safe", "solidarity", "trust", "valuable", "wellbeing",
}

NEGATIVE_SENTIMENT_TERMS = {
    "abuso", "alarma", "alergia", "amenaza", "arrepentimiento", "castigo", "conflicto",
    "contagio", "controversia", "crimen", "critica", "crítica", "daño", "delito",
    "desconfianza", "discriminacion", "discriminación", "dolor", "enfermedad", "error",
    "estigma", "exclusion", "exclusión", "fracaso", "ilegal", "infeccion", "infección",
    "miedo", "negativo", "peligro", "prejuicio", "problema", "rechazo", "riesgo",
    "sancion", "sanción", "violencia", "vulnerabilidad",
    "abuse", "alarm", "allergy", "attack", "concern", "conflict", "controversy", "crime",
    "criticism", "damage", "danger", "disease", "discrimination", "error", "exclusion",
    "failure", "fear", "harm", "illegal", "infection", "negative", "pain", "prejudice",
    "problem", "rejection", "regret", "risk", "stigma", "threat", "violence", "vulnerability",
}

NEGATION_TERMS = {"no", "not", "never", "nunca", "sin", "without", "ni"}
INTENSIFIER_TERMS = {"muy", "very", "bastante", "really", "extremely", "sumamente", "altamente"}


def sentiment_for_text(text: str, extra_positive: list[str] | None = None, extra_negative: list[str] | None = None) -> dict:
    tokens = tokenize(text or "", extra_stopwords=[])
    positive_terms = {normalize_local(term) for term in [*POSITIVE_SENTIMENT_TERMS, *(extra_positive or [])]}
    negative_terms = {normalize_local(term) for term in [*NEGATIVE_SENTIMENT_TERMS, *(extra_negative or [])]}
    negations = {normalize_local(term) for term in NEGATION_TERMS}
    intensifiers = {normalize_local(term) for term in INTENSIFIER_TERMS}
    positive_hits = 0.0
    negative_hits = 0.0
    hit_terms: list[str] = []
    for index, token in enumerate(tokens):
        normalized = normalize_local(token)
        if normalized not in positive_terms and normalized not in negative_terms:
            continue
        window = [normalize_local(item) for item in tokens[max(0, index - 3):index]]
        multiplier = 1.5 if any(item in intensifiers for item in window) else 1.0
        inverted = any(item in negations for item in window)
        is_positive = normalized in positive_terms
        if inverted:
            is_positive = not is_positive
        if is_positive:
            positive_hits += multiplier
        else:
            negative_hits += multiplier
        hit_terms.append(token)
    denominator = positive_hits + negative_hits
    score = 0.0 if denominator == 0 else (positive_hits - negative_hits) / denominator
    if score >= 0.15:
        label = "positive"
    elif score <= -0.15:
        label = "negative"
    else:
        label = "neutral_or_mixed"
    return {
        "sentiment_score": round(score, 5),
        "positive_hits": round(positive_hits, 3),
        "negative_hits": round(negative_hits, 3),
        "sentiment_label": label,
        "sentiment_terms": ", ".join(hit_terms[:40]),
    }


def sentiment_document_rows(rows: list[dict], extra_positive: list[str] | None = None, extra_negative: list[str] | None = None) -> list[dict]:
    output = []
    for row in rows:
        text = " ".join(
            str(part or "")
            for part in [row.get("title", ""), row.get("text_normalized") or row.get("text_clean") or ""]
        )
        sentiment = sentiment_for_text(text, extra_positive=extra_positive, extra_negative=extra_negative)
        output.append(
            {
                "year": row.get("year"),
                "source_type": row_source_type(row),
                "medium": row.get("medium") or "unknown",
                "title": row.get("title", ""),
                "url": row.get("url", ""),
                **sentiment,
            }
        )
    return output


def sentiment_by_year_source(rows: list[dict]) -> list[dict]:
    grouped: dict[tuple[int, str], list[float]] = defaultdict(list)
    for row in rows:
        year = row.get("year")
        if not str(year).isdigit():
            continue
        grouped[(int(year), str(row.get("source_type") or "other"))].append(float(row.get("sentiment_score") or 0))
    output = []
    for (year, source_type), values in sorted(grouped.items()):
        mean_value = sum(values) / max(1, len(values))
        variance = sum((value - mean_value) ** 2 for value in values) / max(1, len(values))
        output.append(
            {
                "year": year,
                "source_type": source_type,
                "documents": len(values),
                "mean_sentiment": round(mean_value, 5),
                "sentiment_variance": round(variance, 5),
                "sentiment_std": round(math.sqrt(variance), 5),
                "radial_value_0_1": round((mean_value + 1.0) / 2.0, 5),
            }
        )
    return output


def sentiment_radar_svg(rows: list[dict], year: int, source_order: list[str]) -> str:
    values = {row["source_type"]: float(row.get("radial_value_0_1") or 0.5) for row in rows if int(row.get("year") or 0) == int(year)}
    means = {row["source_type"]: float(row.get("mean_sentiment") or 0) for row in rows if int(row.get("year") or 0) == int(year)}
    if not source_order:
        return ""
    size = 420
    center = size / 2
    max_radius = 145
    axis_count = len(source_order)
    points = []
    axis_lines = []
    labels = []
    rings = []
    for ring_value in [0.25, 0.5, 0.75, 1.0]:
        ring_points = []
        for index in range(axis_count):
            angle = -math.pi / 2 + 2 * math.pi * index / axis_count
            radius = max_radius * ring_value
            ring_points.append(f"{center + radius * math.cos(angle):.1f},{center + radius * math.sin(angle):.1f}")
        rings.append(f'<polygon points="{" ".join(ring_points)}" fill="none" stroke="#d1d5db" stroke-width="1"/>')
    for index, source_type in enumerate(source_order):
        angle = -math.pi / 2 + 2 * math.pi * index / axis_count
        axis_x = center + max_radius * math.cos(angle)
        axis_y = center + max_radius * math.sin(angle)
        axis_lines.append(f'<line x1="{center:.1f}" y1="{center:.1f}" x2="{axis_x:.1f}" y2="{axis_y:.1f}" stroke="#e5e7eb" stroke-width="1"/>')
        label_x = center + (max_radius + 38) * math.cos(angle)
        label_y = center + (max_radius + 38) * math.sin(angle)
        anchor = "middle"
        if math.cos(angle) > 0.35:
            anchor = "start"
        elif math.cos(angle) < -0.35:
            anchor = "end"
        label = html_lib.escape(source_type)
        labels.append(
            f'<text x="{label_x:.1f}" y="{label_y:.1f}" text-anchor="{anchor}" dominant-baseline="middle" '
            f'font-size="12" fill="#374151">{label} ({means.get(source_type, 0):+.2f})</text>'
        )
        radius = max_radius * values.get(source_type, 0.5)
        points.append(f"{center + radius * math.cos(angle):.1f},{center + radius * math.sin(angle):.1f}")
    polygon = f'<polygon points="{" ".join(points)}" fill="#0891b244" stroke="#0891b2" stroke-width="3"/>'
    return f"""
    <svg viewBox="0 0 {size} {size}" width="100%" height="{size}" role="img" aria-label="Radar sentiment {year}">
      <rect width="100%" height="100%" fill="white"/>
      <text x="{center}" y="24" text-anchor="middle" font-size="18" font-weight="700" fill="#111827">Sentimiento promedio por fuente · {year}</text>
      <text x="{center}" y="46" text-anchor="middle" font-size="11" fill="#6b7280">radio = (sentimiento + 1) / 2; 0 negativo, 0.5 neutro, 1 positivo</text>
      {"".join(rings)}
      {"".join(axis_lines)}
      {polygon}
      <circle cx="{center}" cy="{center}" r="3" fill="#111827"/>
      {"".join(labels)}
    </svg>
    """


def count_records_by_year_medium_and_type(rows: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    usable_rows = [row for row in rows if has_usable_text(row)]
    by_year = Counter(int(row["year"]) for row in usable_rows if row.get("year"))
    by_year_type = Counter(
        (int(row["year"]), row_source_type(row))
        for row in usable_rows
        if row.get("year")
    )
    by_year_medium = Counter(
        (int(row["year"]), row_source_type(row), row.get("medium") or "unknown")
        for row in usable_rows
        if row.get("year")
    )

    year_counts = [
        {"year": year, "news_count": count}
        for year, count in sorted(by_year.items())
    ]
    year_type_counts = [
        {"year": year, "source_type": source_type, "news_count": count}
        for (year, source_type), count in sorted(by_year_type.items())
    ]
    year_medium_counts = [
        {"year": year, "source_type": source_type, "medium": medium, "news_count": count}
        for (year, source_type, medium), count in sorted(by_year_medium.items())
    ]
    return year_counts, year_type_counts, year_medium_counts


def render_corpus_distribution(rows: list[dict]) -> None:
    year_counts, year_type_counts, year_medium_counts = count_records_by_year_medium_and_type(rows)
    if not year_counts:
        st.info("Todavía no hay noticias con estado `ok` para graficar.")
        return

    st.subheader("Distribución del corpus")
    st.caption("Estas gráficas cuentan registros con texto completo (`ok`) o señal parcial analizable (`ok_partial`).")

    left, right = st.columns(2)
    with left:
        st.markdown("Noticias por año")
        st.vega_lite_chart(
            year_counts,
            {
                "mark": {"type": "bar", "tooltip": True},
                "encoding": {
                    "x": {"field": "year", "type": "ordinal", "title": "Año"},
                    "y": {"field": "news_count", "type": "quantitative", "title": "Noticias"},
                },
            },
            use_container_width=True,
        )

    with right:
        st.markdown("Fuentes por tipo discursivo y año")
        st.vega_lite_chart(
            year_type_counts,
            {
                "mark": {"type": "bar", "tooltip": True},
                "encoding": {
                    "x": {"field": "year", "type": "ordinal", "title": "Año"},
                    "y": {"field": "news_count", "type": "quantitative", "title": "Registros"},
                    "color": {
                        "field": "source_type",
                        "type": "nominal",
                        "title": "Tipo de fuente",
                        "scale": {"domain": ["news", "scientific_article", "forum", "other"]},
                    },
                    "tooltip": [
                        {"field": "year", "type": "ordinal", "title": "Año"},
                        {"field": "source_type", "type": "nominal", "title": "Tipo"},
                        {"field": "news_count", "type": "quantitative", "title": "Registros"},
                    ],
                },
            },
            use_container_width=True,
        )

    st.markdown("Noticias por año, tipo y medio")
    st.vega_lite_chart(
        year_medium_counts,
        {
            "mark": {"type": "bar", "tooltip": True},
            "encoding": {
                "x": {"field": "year", "type": "ordinal", "title": "Año"},
                "y": {"field": "news_count", "type": "quantitative", "title": "Registros"},
                "color": {"field": "medium", "type": "nominal", "title": "Medio"},
                "column": {
                    "field": "source_type",
                    "type": "nominal",
                    "title": "Tipo de fuente",
                    "sort": ["news", "scientific_article", "forum", "other"],
                },
                "tooltip": [
                    {"field": "year", "type": "ordinal", "title": "Año"},
                    {"field": "source_type", "type": "nominal", "title": "Tipo"},
                    {"field": "medium", "type": "nominal", "title": "Medio"},
                    {"field": "news_count", "type": "quantitative", "title": "Registros"},
                ],
            },
        },
        use_container_width=True,
    )

    with st.expander("Tabla año–tipo–medio"):
        st.dataframe(year_medium_counts, use_container_width=True)

    st.markdown("Conteo por medio")
    medium_counts = Counter(
        (row_source_type(row), row.get("medium") or "unknown")
        for row in rows
        if has_usable_text(row)
    )
    medium_rows = [
        {"source_type": source_type, "medium": medium, "news_count": count}
        for (source_type, medium), count in sorted(medium_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    st.dataframe(medium_rows, use_container_width=True)

    st.markdown("Conteo por nivel de evidencia")
    evidence_counts = Counter(
        row_evidence(row)
        for row in rows
        if has_usable_text(row)
    )
    evidence_rows = [
        {"evidence_level": level, "evidence_weight": weight, "records": count}
        for (level, weight), count in sorted(evidence_counts.items(), key=lambda item: -item[0][1])
    ]
    st.dataframe(evidence_rows, use_container_width=True)


def narrative_core_metrics(records: list[dict], event_rows: list[dict], extra_stopwords: list[str]) -> dict:
    source_types = Counter(row_source_type(row) for row in records)
    years = {int(row.get("year")) for row in records if str(row.get("year", "")).isdigit()}
    media = {row.get("medium") or "unknown" for row in records}
    actors = actor_counts(event_rows, top_n=500)
    stage_hits = sum(
        1
        for row in event_rows
        for stage in ["initial_event", "conflict", "turning_point", "resolution", "consequences"]
        if row.get(stage)
    )
    thematic_relations = (
        len(top_ngrams(records, n=2, top_n=500, min_count=2, extra_stopwords=extra_stopwords))
        + len(top_ngrams(records, n=3, top_n=500, min_count=2, extra_stopwords=extra_stopwords))
    )
    return {
        "documents": len(records),
        "news": source_types.get("news", 0),
        "forums": source_types.get("forum", 0),
        "scientific_articles": source_types.get("scientific_article", 0),
        "institutional_reports": source_types.get("institutional_report", 0),
        "actors": len(actors),
        "events_or_stages": stage_hits,
        "thematic_relations": thematic_relations,
        "sources": len(media),
        "temporal_markers": len(years),
    }


def narrative_timeline_rows(records: list[dict], event_rows: list[dict], extra_stopwords: list[str]) -> list[dict]:
    event_by_key = {row.get("doc_key"): row for row in event_rows}
    grouped: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for row in records:
        if not str(row.get("year", "")).isdigit():
            continue
        grouped[(int(row.get("year")), row_source_type(row))].append(row)
    timeline = []
    for (year, source_type), rows in sorted(grouped.items()):
        texts = " ".join((row.get("text_normalized") or row.get("text_clean") or row.get("title") or "") for row in rows)
        top_terms_row = top_terms(rows, top_n=5, extra_stopwords=extra_stopwords)
        related_events = [event_by_key.get(row.get("url") or f"{row.get('year')}|{row.get('medium')}|{row.get('title')}") for row in rows]
        related_events = [row for row in related_events if row]
        timeline.append(
            {
                "year": year,
                "source_type": source_type,
                "documents": len(rows),
                "sources": len({row.get("medium") or "unknown" for row in rows}),
                "top_terms": ", ".join(row["term"] for row in top_terms_row),
                "conflict_docs": sum(1 for row in related_events if row.get("conflict")),
                "change_docs": sum(1 for row in related_events if row.get("turning_point")),
                "consequence_docs": sum(1 for row in related_events if row.get("consequences")),
                "mean_text_length": round(sum(len(row.get("text_normalized") or row.get("text_clean") or "") for row in rows) / max(1, len(rows)), 1),
            }
        )
    return timeline


def local_query_rows(records: list[dict], query_text: str, extra_stopwords: list[str], limit: int = 30) -> list[dict]:
    query_tokens = tokenize(query_text, extra_stopwords)
    if not query_tokens:
        return []
    scored = []
    for row in records:
        text = " ".join(
            str(part or "")
            for part in [row.get("title", ""), row.get("medium", ""), row.get("text_normalized") or row.get("text_clean") or ""]
        )
        tokens = tokenize(text, extra_stopwords)
        if not tokens:
            continue
        counts = Counter(tokens)
        score = sum(counts.get(token, 0) for token in query_tokens)
        phrase_bonus = 3 if normalize_local(query_text) in normalize_local(text) else 0
        if score or phrase_bonus:
            scored.append(
                {
                    "score": score + phrase_bonus,
                    "year": row.get("year"),
                    "source_type": row_source_type(row),
                    "medium": row.get("medium") or "unknown",
                    "title": row.get("title", ""),
                    "status": row.get("status", ""),
                    "url": row.get("url", ""),
                    "preview": (row.get("text_normalized") or row.get("text_clean") or "")[:420],
                }
            )
    return sorted(scored, key=lambda item: (-item["score"], item.get("year") or 0, item.get("medium") or ""))[:limit]


def render_narrative_core_dashboard(records: list[dict], event_rows: list[dict], extra_stopwords: list[str]) -> None:
    st.subheader("Núcleo integrado de exploración narrativa")
    st.caption(
        "Esta vista une extracción, clasificación, eventos, fuentes, relaciones temáticas y tiempo. "
        "Si una capa aparece en cero, no es un problema de gráfica: es una limitación real del corpus."
    )
    metrics = narrative_core_metrics(records, event_rows, extra_stopwords)
    metric_cols = st.columns(5)
    metric_cols[0].metric("Documentos", metrics["documents"])
    metric_cols[1].metric("Noticias", metrics["news"])
    metric_cols[2].metric("Foros/expresión ciudadana", metrics["forums"])
    metric_cols[3].metric("Artículos científicos", metrics["scientific_articles"])
    metric_cols[4].metric("Gobierno/institucional", metrics["institutional_reports"])
    metric_cols = st.columns(5)
    metric_cols[0].metric("Entidades/actores", metrics["actors"])
    metric_cols[1].metric("Eventos/etapas", metrics["events_or_stages"])
    metric_cols[2].metric("Relaciones temáticas", metrics["thematic_relations"])
    metric_cols[3].metric("Fuentes", metrics["sources"])
    metric_cols[4].metric("Marcadores temporales", metrics["temporal_markers"])

    if metrics["forums"] == 0:
        st.error(
            "Capa ciudadana ausente: no hay foros/blogs/conversaciones públicas usables. "
            "El sistema puede analizar discurso periodístico o científico, pero no inferir narrativa social completa."
        )
    if metrics["news"] == 0:
        st.warning("Capa periodística ausente: falta el puente público entre conversación social e investigación/institución.")

    st.markdown("Línea de tiempo interactiva por tipo de fuente")
    timeline = narrative_timeline_rows(records, event_rows, extra_stopwords)
    if timeline:
        st.vega_lite_chart(
            timeline,
            {
                "mark": {"type": "line", "point": True, "tooltip": True},
                "encoding": {
                    "x": {"field": "year", "type": "ordinal", "title": "Año"},
                    "y": {"field": "documents", "type": "quantitative", "title": "Documentos"},
                    "color": {"field": "source_type", "type": "nominal", "title": "Tipo de fuente"},
                    "tooltip": [
                        {"field": "year", "type": "ordinal"},
                        {"field": "source_type", "type": "nominal"},
                        {"field": "documents", "type": "quantitative"},
                        {"field": "sources", "type": "quantitative"},
                        {"field": "top_terms", "type": "nominal"},
                        {"field": "conflict_docs", "type": "quantitative"},
                        {"field": "change_docs", "type": "quantitative"},
                        {"field": "consequence_docs", "type": "quantitative"},
                    ],
                },
            },
            use_container_width=True,
        )
        with st.expander("Tabla de línea de tiempo: fuentes, términos y etapas"):
            st.dataframe(timeline, use_container_width=True)

    st.markdown("Consulta local en lenguaje natural")
    query_text = st.text_input(
        "Pregunta o concepto a buscar dentro del corpus",
        value="",
        placeholder="Ejemplo: discriminación laboral por tatuajes, riesgo sanitario, identidad juvenil...",
        help="Búsqueda local por términos normalizados; no usa LLM ni sale de tu computadora.",
        key="local_narrative_query",
    )
    if query_text.strip():
        matches = local_query_rows(records, query_text, extra_stopwords)
        if matches:
            st.dataframe(matches, use_container_width=True)
        else:
            st.info("No hubo coincidencias locales con esa consulta. Prueba sinónimos o revisa si esa capa existe en el corpus.")


def render_source_type_method_note() -> None:
    with st.expander("Criterio de clasificación de fuentes"):
        st.markdown(
            """
La fuente se clasifica para estudiar la estructura de la narrativa, no para decir que una sea “mejor” que otra.

Orden conceptual para evidencia:

1. `scientific_article`: artículos científicos, revistas académicas, DOI, preprints o repositorios académicos.
2. `industry_report`: encuestas o reportes industriales, por ejemplo Stack Overflow Developer Survey.
3. `news`: notas periodísticas, medios informativos, revistas, periódicos o portales noticiosos.
4. `forum`: foros, comunidades, Reddit público, Quora público, StackExchange, Hacker News, blogs con comentarios o plataformas abiertas como Medium/Substack/WordPress/Blogspot cuando el texto representa discusión o experiencia situada.
5. `other`: fuente con evidencia insuficiente.

Cada registro guarda `source_type_confidence`, `source_type_evidence`, `evidence_level`, `evidence_weight`, `geographic_scope` y `geographic_terms` para revisar manualmente casos dudosos.

No se raspan comentarios privados, Instagram cerrado, TikTok cerrado ni páginas que requieran saltar sesión, paywall o controles técnicos. Si se tienen exportaciones autorizadas, deben importarse como documentos manuales.
"""
        )


def render_results(rows: list[dict]) -> None:
    ok_rows = [row for row in rows if has_usable_text(row)]
    partial_rows = [row for row in ok_rows if row.get("status") in {"ok_partial", "too_short"}]
    st.success(f"Listo: {len(rows)} registros guardados; {len(ok_rows)} con texto/señal usable.")
    if partial_rows:
        st.info(
            f"{len(partial_rows)} registros son parciales: sirven para narrativa de RSS/metadatos, "
            "pero no equivalen a cuerpo completo de noticia o artículo."
        )

    col1, col2, col3 = st.columns(3)
    col1.metric("Registros", len(rows))
    col2.metric("Texto/señal usable", len(ok_rows))
    col3.metric("Tipos de fuente", len({row_source_type(row) for row in ok_rows}))

    if not rows:
        return

    render_corpus_distribution(rows)
    render_source_status_dashboard(rows, config=st.session_state.get("spider_config", {}))
    render_source_type_method_note()
    balance = corpus_social_balance_diagnostic(rows)
    st.subheader("Diagnóstico de balance social del corpus")
    st.dataframe([balance], use_container_width=True)
    if balance["status"] == "not_valid_for_social_narrative":
        st.error(
            "Este corpus NO es válido para análisis social de narrativa: está dominado por artículos científicos "
            "y faltan noticias o conversaciones orgánicas. Debe recolectarse de nuevo balanceando fuentes."
        )
    elif balance["status"] == "incomplete_social_layers":
        st.warning("El corpus tiene capas sociales incompletas: faltan noticias o foros/conversaciones orgánicas.")
    config = st.session_state.get("spider_config", {})
    max_per_type = int(config.get("max_records_per_source_type_year", config.get("target_news_per_year", 100)) or 100)
    target_min_per_type = int(config.get("target_min_per_source_type_year", 1) or 0)
    coverage_rows = annual_news_coverage_rows(rows, max_per_type)
    if coverage_rows:
        st.subheader("Cobertura anual de noticias")
        st.caption(
            "Esta tabla audita si la muestra periodística alcanza la meta anual. "
            "No cuenta artículos científicos ni foros; sólo registros clasificados como noticia."
        )
        st.dataframe(coverage_rows, use_container_width=True)
        insufficient = [row for row in coverage_rows if row["status"] != "ok"]
        if insufficient:
            years = ", ".join(str(row["year"]) for row in insufficient)
            st.warning(
                f"No se alcanzó el máximo/objetivo de referencia de {max_per_type} noticias usables en: {years}. "
                "Para esos años hay que ampliar fuentes, variantes de búsqueda, dominios o aceptar una muestra menor reportada como limitación."
            )
    source_coverage = annual_source_type_coverage_rows(rows, target_min_per_type, max_per_type)
    if source_coverage:
        st.subheader("Cobertura por tipo discursivo")
        st.caption(
            "Esta auditoría revisa si realmente hay noticias, artículos y conversaciones orgánicas. "
            "Si `forum = 0`, el corpus no contiene foros/conversaciones para ese año."
        )
        st.dataframe(source_coverage, use_container_width=True)
        under_target = [row for row in source_coverage if str(row.get("source_balance_status", "")).startswith("missing_or_under_target")]
        if under_target:
            years = ", ".join(str(row["year"]) for row in under_target)
            st.warning(
                f"Falta representación mínima de uno o más tipos discursivos en: {years}. "
                "Hay que ampliar fuentes/API/exportaciones locales o reportarlo como limitación."
            )

    st.subheader("Vista previa")
    st.dataframe(
        [
                {
                    "year": row.get("year", "unknown"),
                    "source_type": row_source_type(row),
                    "source_type_confidence": row.get("source_type_confidence", ""),
                    "evidence_weight": row_evidence(row)[1],
                    "geographic_scope": row.get("geographic_scope", ""),
                    "medium": row.get("medium", "unknown"),
                    "title": row.get("title", ""),
                    "status": row.get("status", "unknown"),
                    "text_length": row.get("text_length", len(row.get("text_clean", "") or row.get("text_normalized", ""))),
                    "word_count": row.get("word_count", 0),
                    "paragraph_count": row.get("paragraph_count", 0),
                    "cleaning_notes": ", ".join(row.get("cleaning_notes", [])),
                    "url": row.get("url", ""),
                }
            for row in rows
        ],
        use_container_width=True,
    )

    json_bytes = json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8")
    jsonl_bytes = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows).encode("utf-8")

    st.download_button("Descargar JSON", data=json_bytes, file_name="news_records.json", mime="application/json")
    st.download_button("Descargar JSONL", data=jsonl_bytes, file_name="news_records.jsonl", mime="application/x-ndjson")


def render_analysis_tab(default_output_dir: str) -> None:
    st.subheader("Análisis local de narrativas")
    st.caption("Todo se calcula en tu computadora con los JSON guardados. No se envían textos a modelos externos.")
    st.markdown("Mapa de módulos disponibles")
    st.dataframe(
        [
            {
                "módulo": "Corpus y balance",
                "qué muestra": "calidad del corpus, tipos de fuente, años, medios, cobertura y registros excluidos",
                "condición": "requiere JSON local cargado",
            },
            {
                "módulo": "Red narrativa",
                "qué muestra": "actores, eventos, fuentes, relaciones narrativas ponderadas y validación humana de actores",
                "condición": "requiere documentos con texto analizable",
            },
            {
                "módulo": "Cubridor y métodos",
                "qué muestra": "modelo SCP multiobjetivo, MOEA, MOSA, MMC-MO, glotón ponderado, Pareto, hipervolumen y k corridas",
                "condición": "requiere red narrativa con aristas",
            },
            {
                "módulo": "Grafo de conocimiento",
                "qué muestra": "monogramas, bigramas, trigramas, fuentes, años, comunidades y nodos centrales",
                "condición": "requiere texto limpio después de stopwords",
            },
            {
                "módulo": "Red semántica / Louvain",
                "qué muestra": "red de coocurrencia limpia, comunidades Louvain/modularidad y cubridor multiobjetivo semántico",
                "condición": "requiere términos frecuentes y aristas semánticas",
            },
            {
                "módulo": "Sentimiento y exportación",
                "qué muestra": "sentimiento local por fuente/año y archivos CSV/JSON descargables",
                "condición": "requiere registros seleccionados",
            },
        ],
        use_container_width=True,
        hide_index=True,
    )

    with st.expander("Marco de lectura: ¿qué entendemos aquí por narrativa?", expanded=True):
        st.markdown(
            """
Una narrativa no es sólo una palabra frecuente ni una opinión positiva/negativa. En este sistema se trata como una
estructura situada de sentido: una voz habla desde una fuente, nombra actores, organiza un problema, marca un cambio,
propone una consecuencia y deja huellas en un tiempo y lugar.

Para el ejemplo **tatuaje**, la narrativa puede aparecer como archivo corporal, práctica estética, oficio, memoria,
identidad, riesgo sanitario, estigma laboral o regulación pública. Por eso el análisis separa capas discursivas
—noticias, foros, artículos, reportes— y después construye mapas de relaciones revisables.
"""
        )
        st.dataframe(
            [
                {
                    "componente": "Voz / fuente",
                    "pregunta guía": "¿Quién habla y desde qué capa discursiva?",
                    "ejemplo tatuaje": "foro de clientes, nota periodística, artículo médico, reporte sanitario",
                },
                {
                    "componente": "Actor",
                    "pregunta guía": "¿Quién aparece como agente, afectado o autoridad?",
                    "ejemplo tatuaje": "tatuador, cliente, autoridad sanitaria, médico, empleador, colectivo juvenil",
                },
                {
                    "componente": "Situación / contexto",
                    "pregunta guía": "¿Dónde y bajo qué condiciones aparece el tema?",
                    "ejemplo tatuaje": "estudio de tatuajes, empleo, salud pública, identidad urbana, diseño corporal",
                },
                {
                    "componente": "Conflicto o tensión",
                    "pregunta guía": "¿Qué problema, disputa o riesgo organiza el relato?",
                    "ejemplo tatuaje": "estigma, discriminación, infección, apropiación estética, regulación de tintas",
                },
                {
                    "componente": "Cambio / consecuencia",
                    "pregunta guía": "¿Qué se transforma o qué efecto se atribuye?",
                    "ejemplo tatuaje": "normalización cultural, alerta sanitaria, memoria personal, profesionalización del oficio",
                },
                {
                    "componente": "Validación humana",
                    "pregunta guía": "¿Qué debe corregir o confirmar el investigador?",
                    "ejemplo tatuaje": "homónimos como marca de cigarros, ironía, jerga, actores mal extraídos",
                },
            ],
            use_container_width=True,
            hide_index=True,
        )
        st.warning(
            "Este marco no afirma representatividad social automática. El corpus muestra huellas disponibles; "
            "toda conclusión debe revisar sesgos de fuente, idioma, plataforma, región y exclusiones."
        )

    col_path, col_button = st.columns([3, 1])
    with col_path:
        analysis_path = st.text_input(
            "Archivo o carpeta JSON para analizar",
            value=st.session_state.loaded_path or default_output_dir,
            help="Puedes poner una carpeta como news_output o un archivo news_records.json/jsonl.",
        )
    with col_button:
        st.write("")
        st.write("")
        if st.button("Cargar corpus guardado"):
            rows = load_saved_rows(analysis_path)
            if rows:
                st.success(f"Corpus cargado: {len(rows)} registros.")
            else:
                st.warning("No encontré registros en esa ruta.")

    rows = st.session_state.spider_rows
    if not rows and not st.session_state.get("spider_running"):
        rows, loaded_candidate = autoload_saved_rows(analysis_path)
        if rows:
            st.info(f"Corpus cargado automáticamente desde: {loaded_candidate}")
    if not rows:
        st.info(
            "Carga un corpus guardado o corre primero la araña. "
            "Si Streamlit se cerró, usa la carpeta de salida para recuperar los JSON. "
            "Las redes y el modelo multiobjetivo aparecen después de cargar registros analizables."
        )
        return

    raw_rows = rows
    rows, duplicate_rows = deduplicate_rows_for_analysis(raw_rows)
    if duplicate_rows:
        st.warning(
            f"Se detectaron {len(duplicate_rows)} registros duplicados por DOI/URL/título-año-medio. "
            "No se borraron del archivo original, pero se excluyen del análisis para no duplicar documentos."
        )
        with st.expander("Duplicados excluidos del análisis"):
            st.dataframe(
                [
                    {
                        "year": row.get("year"),
                        "source_type": row_source_type(row),
                        "medium": row.get("medium"),
                        "title": row.get("title"),
                        "url": row.get("url"),
                        "duplicate_of": row.get("duplicate_of"),
                        "dedup_key": row.get("dedup_key"),
                    }
                    for row in duplicate_rows
                ],
                use_container_width=True,
            )

    usable = enrich_records_for_analysis([row for row in rows if has_usable_text(row)])
    if not usable:
        st.warning(
            "Hay registros, pero ninguno tiene texto/señal usable. "
            "Revisa si faltan `text_clean`, `text_normalized` y `title`, o si todos tienen estados de error."
        )
        return

    balance = corpus_social_balance_diagnostic(rows)
    st.subheader("Diagnóstico de balance social del corpus")
    st.dataframe([balance], use_container_width=True)
    if balance["status"] == "not_valid_for_social_narrative":
        st.error(
            "Este corpus NO sirve para análisis social de narrativa. "
            "Está dominado por artículos científicos y faltan capas de noticias/foros."
        )
    render_source_status_dashboard(rows, config=st.session_state.get("spider_config", {}))

    config = st.session_state.get("spider_config", {})
    max_per_type = int(config.get("max_records_per_source_type_year", config.get("target_news_per_year", 100)) or 100)
    target_min_per_type = int(config.get("target_min_per_source_type_year", 1) or 0)
    coverage_rows = annual_news_coverage_rows(rows, max_per_type)
    if coverage_rows:
        with st.expander("Auditoría de cobertura anual de noticias", expanded=True):
            st.dataframe(coverage_rows, use_container_width=True)
            insufficient = [row for row in coverage_rows if row["status"] != "ok"]
            if insufficient:
                st.warning(
                    "Hay años con muestra periodística insuficiente. "
                    "Eso debe corregirse con más fuentes/variantes o reportarse como limitación."
                )
    source_coverage = annual_source_type_coverage_rows(rows, target_min_per_type, max_per_type)
    if source_coverage:
        with st.expander("Auditoría de fuentes discursivas", expanded=True):
            st.dataframe(source_coverage, use_container_width=True)
            if any(str(row.get("source_balance_status", "")).startswith("missing_or_under_target") for row in source_coverage):
                st.warning(
                    "Falta representación mínima de uno o más tipos discursivos. "
                    "El análisis de narrativa social queda incompleto si sólo hay noticias o sólo hay artículos."
                )

    source_type_options = sorted({row_source_type(row) for row in usable})
    year_options = sorted({int(row.get("year")) for row in usable if row.get("year")})
    medium_options = sorted({row.get("medium") or "unknown" for row in usable})
    language_options = sorted({row.get("analysis_language", "unknown") for row in usable})
    localization_options = sorted({row.get("localization", "Global/unclear") for row in usable})

    with st.expander("Filtros del análisis", expanded=True):
        c1, c2, c3 = st.columns(3)
        selected_types = c1.multiselect("Tipo de fuente", source_type_options, default=source_type_options)
        selected_years = c2.multiselect("Años", year_options, default=year_options)
        selected_media = c3.multiselect("Medios", medium_options, default=medium_options)
        c4, c5 = st.columns(2)
        selected_languages = c4.multiselect("Idioma", language_options, default=language_options)
        selected_localizations = c5.multiselect("Localización México/AL", localization_options, default=localization_options)
        extra_stopwords_text = st.text_area(
            "Stopwords extra",
            value=(
                "ai, artificial, intelligence, inteligencia, artificial, coding, code, software, "
                "first, time, year, years, made, like, back, people, english, noticia, articulo"
            ),
            help=(
                "Palabras separadas por coma. Se excluyen antes de monogramas, bigramas, trigramas, "
                "red semántica, grafo de conocimiento y extracción de actores."
            ),
        )
        extra_stopwords = [item.strip() for item in extra_stopwords_text.split(",") if item.strip()]
        st.markdown("Exclusión manual de documentos / elementos contaminantes")
        exclude_analysis_terms_text = st.text_area(
            "Excluir documentos que contengan estos términos",
            value="cigar, cigars, tobacco, wrapper, halfwheel",
            help="No borra archivos: sólo quita esos documentos del análisis actual. Sirve para depurar corpus contaminado.",
        )
        exclude_analysis_terms = [
            item.strip()
            for chunk in exclude_analysis_terms_text.splitlines()
            for item in chunk.split(",")
            if item.strip()
        ]
        excluded_analysis_media = st.multiselect(
            "Excluir medios completos del análisis",
            options=medium_options,
            default=[medium for medium in medium_options if medium.lower() in {"halfwheel.com"}],
            help="Útil cuando un medio completo pertenece a otro campo semántico.",
        )
        first_row = usable[0] if usable else {}
        default_topic_terms = merge_unique(
            [
                str(first_row.get("query", "")),
                *[str(item) for item in first_row.get("query_variants", [])],
            ]
        )
        topical_terms_text = st.text_area(
            "Términos de relevancia tópica",
            value=", ".join(default_topic_terms),
            help="Sirve para quitar documentos donde el tema sólo aparece en enlaces, notas recomendadas o ruido de página.",
        )
        topical_terms = split_terms(topical_terms_text)
        minimum_topical_score = st.slider(
            "Relevancia tópica mínima",
            min_value=0,
            max_value=20,
            value=0,
            step=1,
            help="0 deja ver todo el corpus usable. Sube a 3–5 cuando quieras depurar ruido después de observar redes y n-gramas.",
        )

    selected_records = filter_records(
        usable,
        source_types=selected_types,
        years=selected_years,
        media=selected_media,
        languages=selected_languages,
        localizations=selected_localizations,
    )
    selected_records, manually_removed_records = exclude_records_for_analysis(
        selected_records,
        excluded_terms=exclude_analysis_terms,
        excluded_media=excluded_analysis_media,
    )
    selected_records, low_relevance_records = filter_by_topical_relevance(
        selected_records,
        terms=topical_terms,
        minimum_score=int(minimum_topical_score),
    )
    manually_removed_records = [*manually_removed_records, *low_relevance_records]

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Documentos analizados", len(selected_records))
    m2.metric("Tipos de fuente", len({row_source_type(row) for row in selected_records}))
    m3.metric("Años", len({row.get("year") for row in selected_records}))
    m4.metric("Medios", len({row.get("medium") for row in selected_records}))
    m5.metric("México foco/mención", sum(1 for row in selected_records if row.get("localization") in {"Mexico-focused", "Mexico-mentioned"}))

    with st.expander("Auditoría del corpus: por qué el número puede bajar tanto", expanded=True):
        st.warning(
            "Si aquí quedan pocos documentos, no significa que existan pocos documentos en el mundo; "
            "significa que la combinación de búsqueda, descarga, limpieza, exclusiones y relevancia tópica está filtrando el corpus."
        )
        a1, a2, a3, a4, a5 = st.columns(5)
        a1.metric("Registros cargados", len(raw_rows))
        a2.metric("Duplicados excluidos", len(duplicate_rows))
        a3.metric("Registros deduplicados", len(rows))
        a4.metric("Usables antes de filtros", len(usable))
        a5.metric("Analizados después de filtros", len(selected_records))
        st.dataframe(corpus_audit_rows(raw_rows), use_container_width=True)
        if year_options and max(year_options) < 2026:
            st.error(
                f"Este corpus sólo llega hasta {max(year_options)}. Para analizar hasta 2026 debes correr una nueva recolección con año final 2026."
            )
        with st.expander("Fuentes exactas usadas en el análisis: tipo, motor, URL y texto limpio"):
            st.dataframe(
                [
                    {
                        "year": row.get("year"),
                        "source_type": row_source_type(row),
                        "source_api": row.get("source_api"),
                        "medium": row.get("medium"),
                        "title": row.get("title"),
                        "url": row.get("url"),
                        "status": row.get("status"),
                        "text_length": row.get("text_length"),
                        "word_count": row.get("word_count"),
                        "cleaning_notes": ", ".join(row.get("cleaning_notes") or []),
                        "analysis_text_preview": (row.get("text_normalized") or row.get("text_clean") or "")[:500],
                        "tokens_after_stopwords": " ".join(tokenize(row.get("text_normalized") or row.get("text_clean") or "", extra_stopwords)[:80]),
                    }
                    for row in selected_records
                ],
                use_container_width=True,
            )

    if manually_removed_records:
        with st.expander(f"Documentos excluidos manualmente del análisis ({len(manually_removed_records)})"):
            st.dataframe(
                [
                    {
                        "reason": row.get("exclusion_reason"),
                        "year": row.get("year"),
                        "medium": row.get("medium"),
                        "source_type": row_source_type(row),
                        "title": row.get("title"),
                        "url": row.get("url"),
                    }
                    for row in manually_removed_records
                ],
                use_container_width=True,
            )

    if not selected_records:
        st.warning("Los filtros dejaron el corpus vacío.")
        return

    core_event_rows = apply_actor_validations(
        extract_narrative_events(selected_records, extra_stopwords=extra_stopwords),
        load_actor_validations(actor_validation_path(analysis_path)),
    )
    render_narrative_core_dashboard(selected_records, core_event_rows, extra_stopwords)

    default_groups = idea_groups_for_records(selected_records)
    default_group_text = "\n".join(
        f"{name}: {', '.join(terms)}"
        for name, terms in default_groups.items()
    )

    analysis_tabs = st.tabs([
        "Geolocalización",
        "Eventos narrativos",
        "Cubridor y métodos",
        "Monogramas",
        "Bigramas",
        "Trigramas",
        "Grupos de ideas",
        "Grafo de conocimiento",
        "Marcos narrativos",
        "Red semántica",
        "Disección estructural",
        "Sentimiento",
        "Exportar",
    ])

    with analysis_tabs[0]:
        st.markdown("Geolocalización local e idioma")
        st.caption("La localización se infiere localmente por dominio, país de fuente y menciones textuales. No usa geocodificación externa.")
        lang_counts = count_rows(selected_records, ["analysis_language"])
        loc_counts = count_rows(selected_records, ["localization"])
        source_loc_counts = count_rows(selected_records, ["source_type", "localization"])
        year_lang_counts = count_rows(selected_records, ["year", "analysis_language"])
        year_loc_counts = count_rows(selected_records, ["year", "localization"])

        left, right = st.columns(2)
        with left:
            st.markdown("Idiomas del corpus")
            st.vega_lite_chart(
                lang_counts,
                {
                    "mark": {"type": "bar", "tooltip": True},
                    "encoding": {
                        "x": {"field": "records", "type": "quantitative", "title": "Registros"},
                        "y": {"field": "analysis_language", "type": "nominal", "sort": "-x", "title": "Idioma"},
                    },
                },
                use_container_width=True,
            )
        with right:
            st.markdown("Localización respecto a México")
            st.vega_lite_chart(
                loc_counts,
                {
                    "mark": {"type": "bar", "tooltip": True},
                    "encoding": {
                        "x": {"field": "records", "type": "quantitative", "title": "Registros"},
                        "y": {"field": "localization", "type": "nominal", "sort": "-x", "title": "Localización"},
                    },
                },
                use_container_width=True,
            )

        st.markdown("Tipo de fuente × localización")
        st.vega_lite_chart(
            source_loc_counts,
            {
                "mark": {"type": "rect", "tooltip": True},
                "encoding": {
                    "x": {"field": "source_type", "type": "nominal", "title": "Tipo de fuente"},
                    "y": {"field": "localization", "type": "nominal", "title": "Localización"},
                    "color": {"field": "records", "type": "quantitative", "title": "Registros"},
                    "tooltip": [
                        {"field": "source_type", "type": "nominal"},
                        {"field": "localization", "type": "nominal"},
                        {"field": "records", "type": "quantitative"},
                    ],
                },
            },
            use_container_width=True,
        )

        left, right = st.columns(2)
        with left:
            st.markdown("Idioma por año")
            st.vega_lite_chart(
                year_lang_counts,
                {
                    "mark": {"type": "bar", "tooltip": True},
                    "encoding": {
                        "x": {"field": "year", "type": "ordinal", "title": "Año"},
                        "y": {"field": "records", "type": "quantitative", "title": "Registros"},
                        "color": {"field": "analysis_language", "type": "nominal", "title": "Idioma"},
                    },
                },
                use_container_width=True,
            )
        with right:
            st.markdown("Localización por año")
            st.vega_lite_chart(
                year_loc_counts,
                {
                    "mark": {"type": "bar", "tooltip": True},
                    "encoding": {
                        "x": {"field": "year", "type": "ordinal", "title": "Año"},
                        "y": {"field": "records", "type": "quantitative", "title": "Registros"},
                        "color": {"field": "localization", "type": "nominal", "title": "Localización"},
                    },
                },
                use_container_width=True,
            )

        st.markdown("Auditoría de localización")
        audit_rows = [
            {
                "year": row.get("year"),
                "language": row.get("analysis_language"),
                "localization": row.get("localization"),
                "mexico_score": row.get("mexico_score"),
                "evidence": row.get("localization_evidence"),
                "medium": row.get("medium"),
                "title": row.get("title"),
                "url": row.get("url"),
            }
            for row in selected_records
        ]
        st.dataframe(audit_rows, use_container_width=True)

    with analysis_tabs[1]:
        st.markdown("Extracción local de estructura narrativa")
        st.caption(
            "Detecta evento inicial, conflicto, punto de cambio, resolución, consecuencias, actores y contexto/situación. "
            "Es heurístico y auditable: no usa LLM ni manda texto fuera de tu máquina."
        )
        event_rows_auto = extract_narrative_events(selected_records, extra_stopwords=extra_stopwords)
        validation_file = actor_validation_path(analysis_path)
        actor_validations = load_actor_validations(validation_file)
        event_rows = apply_actor_validations(event_rows_auto, actor_validations)
        event_summary = narrative_event_summary(event_rows)
        actors = actor_counts(event_rows)
        average_completeness = (
            sum(row.get("narrative_completeness", 0) for row in event_rows) / max(1, len(event_rows))
        )

        n1, n2, n3, n4 = st.columns(4)
        n1.metric("Documentos", len(event_rows))
        n2.metric("Completitud narrativa promedio", f"{average_completeness:.2f}")
        n3.metric("Con conflicto detectado", sum(1 for row in event_rows if row.get("conflict")))
        n4.metric("Con consecuencias detectadas", sum(1 for row in event_rows if row.get("consequences")))

        st.markdown("Validación humana de actores")
        validated_count = sum(1 for row in event_rows if row.get("actor_validation_status") in {"accepted", "corrected", "rejected"})
        v1, v2, v3 = st.columns(3)
        v1.metric("Documentos validados", validated_count)
        v2.metric("Pendientes", len(event_rows) - validated_count)
        v3.metric("Archivo validación", validation_file.name)

        with st.expander("Revisar / corregir actores", expanded=False):
            st.caption("La red narrativa usa `actors_validated` cuando existen. Si rechazas, el documento queda sin actores para la red.")
            doc_options = {
                f"{row['doc_id']} · {row.get('year')} · {row.get('medium')} · {row.get('title', '')[:90]}": row
                for row in event_rows
            }
            selected_doc_label = st.selectbox("Documento", options=list(doc_options), key="actor_validation_doc")
            selected_doc = doc_options[selected_doc_label]
            st.write({"title": selected_doc.get("title"), "url": selected_doc.get("url")})
            st.text_area("Actores automáticos", value=selected_doc.get("actors_auto", ""), height=90, disabled=True)
            current_validated = selected_doc.get("actors_validated") or selected_doc.get("actors_auto", "")
            corrected_actors_text = st.text_area(
                "Actores validados/corregidos",
                value=current_validated,
                height=100,
                help="Separados por coma. Puedes borrar ruido, normalizar nombres o agregar actores faltantes.",
            )
            status_options = ["accepted", "corrected", "rejected", "pending"]
            current_status = selected_doc.get("actor_validation_status", "pending")
            status_index = status_options.index(current_status) if current_status in status_options else 3
            c_status, c_validator = st.columns(2)
            actor_status = c_status.selectbox("Estado", options=status_options, index=status_index)
            validator_name = c_validator.text_input("Validador", value=selected_doc.get("actor_validator") or "human_coder_1")
            actor_notes = st.text_area("Notas de validación", value=selected_doc.get("actor_validation_notes", ""), height=80)
            if st.button("Guardar validación de actores"):
                actors_list = [item.strip() for item in corrected_actors_text.split(",") if item.strip()]
                actor_validations[selected_doc["doc_key"]] = {
                    "doc_key": selected_doc["doc_key"],
                    "url": selected_doc.get("url", ""),
                    "title": selected_doc.get("title", ""),
                    "auto_actors": [item.strip() for item in selected_doc.get("actors_auto", "").split(",") if item.strip()],
                    "validated_actors": actors_list,
                    "status": actor_status,
                    "validator": validator_name,
                    "notes": actor_notes,
                    "validated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                save_actor_validations(validation_file, actor_validations)
                st.success(f"Validación guardada en {validation_file}")
                st.rerun()

            validation_rows = [
                {
                    "doc_id": row.get("doc_id"),
                    "status": row.get("actor_validation_status"),
                    "actors_auto": row.get("actors_auto"),
                    "actors_validated": row.get("actors_validated"),
                    "validator": row.get("actor_validator"),
                    "notes": row.get("actor_validation_notes"),
                    "title": row.get("title"),
                }
                for row in event_rows
            ]
            st.dataframe(validation_rows, use_container_width=True)
            st.download_button(
                "Descargar validación actores JSON",
                data=json.dumps(actor_validations, ensure_ascii=False, indent=2).encode("utf-8"),
                file_name="actor_validation.json",
                mime="application/json",
            )

        st.markdown("Cobertura de etapas narrativas")
        st.vega_lite_chart(
            event_summary,
            {
                "mark": {"type": "bar", "tooltip": True},
                "encoding": {
                    "x": {"field": "documents_with_stage", "type": "quantitative", "title": "Documentos"},
                    "y": {"field": "narrative_stage", "type": "nominal", "sort": "-x", "title": "Etapa narrativa"},
                    "tooltip": [
                        {"field": "narrative_stage", "type": "nominal"},
                        {"field": "documents_with_stage", "type": "quantitative"},
                        {"field": "document_share", "type": "quantitative"},
                    ],
                },
            },
            use_container_width=True,
        )

        st.markdown("Actores detectados")
        st.vega_lite_chart(
            actors[:25],
            {
                "mark": {"type": "bar", "tooltip": True},
                "encoding": {
                    "x": {"field": "documents", "type": "quantitative", "title": "Documentos"},
                    "y": {"field": "actor", "type": "nominal", "sort": "-x", "title": "Actor"},
                },
            },
            use_container_width=True,
        )
        st.dataframe(actors, use_container_width=True)

        st.markdown("Tabla documento × estructura narrativa")
        st.dataframe(
            event_rows,
            column_order=[
                "doc_id",
                "year",
                "medium",
                "source_type",
                "language",
                "localization",
                "title",
                "actors",
                "actor_validation_status",
                "actors_validated",
                "situation_context",
                "initial_event",
                "conflict",
                "turning_point",
                "resolution",
                "consequences",
                "narrative_completeness",
                "url",
            ],
            use_container_width=True,
        )

        with st.expander("Auditoría: marcadores que activaron cada etapa"):
            st.dataframe(
                [
                    {
                        "doc_id": row["doc_id"],
                        "title": row["title"],
                        "initial_event_markers": row["initial_event_markers"],
                        "conflict_markers": row["conflict_markers"],
                        "turning_point_markers": row["turning_point_markers"],
                        "resolution_markers": row["resolution_markers"],
                        "consequences_markers": row["consequences_markers"],
                    }
                    for row in event_rows
                ],
                use_container_width=True,
            )

        st.markdown("Red compleja narrativa ponderada")
        st.caption(
            "Nodos: documentos, actores, etapas narrativas, fuentes, años, localización y tipo de fuente. "
            "Aristas: relaciones documento–actor, documento–etapa, actor–etapa, fuente–etapa y coocurrencias. "
            "El peso aumenta cuando la relación aparece en más documentos."
        )
        st.info(
            "Ponderación conceptual: por defecto se usa modo neutral. "
            "Los elementos narrativos no reciben jerarquía previa; su importancia emerge de frecuencia y conectividad."
        )
        g1, g2, g3, g4 = st.columns(4)
        narrative_min_edge = g1.slider("Peso mínimo de arista narrativa", 1, 10, 1)
        max_actors_per_doc = g2.slider("Actores máximos por documento", 1, 15, 8)
        cover_max_nodes = g3.slider("Máximo de nodos en el cubridor", 1, 50, 12)
        narrative_weighting_mode = g4.selectbox(
            "Ponderación narrativa",
            options=["neutral", "completeness_stage_emphasis"],
            index=0,
            format_func=lambda value: {
                "neutral": "Neutral/sin jerarquía",
                "completeness_stage_emphasis": "Sensibilidad: etapas y completitud",
            }.get(value, value),
            help="Neutral evita imponer que una etapa, fuente o documento valga más antes del análisis. El segundo modo es sólo para sensibilidad.",
        )
        narrative_graph = build_narrative_event_graph(
            event_rows,
            min_edge_weight=narrative_min_edge,
            max_actors_per_doc=max_actors_per_doc,
            weighting_mode=narrative_weighting_mode,
        )
        gs1, gs2, gs3, gs4, gs5, gs6 = st.columns(6)
        gs1.metric("Nodos", narrative_graph["stats"]["nodes"])
        gs2.metric("Aristas", narrative_graph["stats"]["edges"])
        gs3.metric("Densidad", narrative_graph["stats"]["density"])
        gs4.metric("Módulos semánticos", narrative_graph["stats"]["communities"])
        gs5.metric("Peso norm. aristas", narrative_graph["stats"]["total_edge_weight"])
        gs6.metric("Peso crudo aristas", narrative_graph["stats"].get("total_raw_edge_weight", 0))
        st.caption(f"Modo de ponderación de red narrativa: `{narrative_graph['stats'].get('weighting_mode')}`.")
        st.markdown("Diagnóstico de distribución de pesos")
        st.dataframe(graph_structural_summary(narrative_graph), use_container_width=True)

        st.markdown("Visualización de la red narrativa")
        vg1, vg2, vg3 = st.columns(3)
        graph_visible_nodes = vg1.slider(
            "Nodos visibles en la red",
            min_value=20,
            max_value=250,
            value=90,
            step=10,
            help="Se muestran los nodos con mayor score para que el grafo sea legible.",
        )
        graph_visible_min_weight = vg2.slider(
            "Peso mínimo visual normalizado",
            min_value=0.0,
            max_value=1.0,
            value=0.0,
            step=0.05,
            help="Las aristas conservan conteo crudo como raw_weight, pero la visualización usa weight normalizado [0,1].",
        )
        graph_height = vg3.slider("Altura del grafo", min_value=420, max_value=900, value=620, step=40)
        render_interactive_network(
            narrative_graph,
            title="Red narrativa ponderada",
            max_nodes=int(graph_visible_nodes),
            min_edge_weight=float(graph_visible_min_weight),
            height=int(graph_height),
        )

        node_type_rows = count_rows(narrative_graph["nodes"], ["node_type"])
        st.markdown("Composición de nodos")
        st.vega_lite_chart(
            node_type_rows,
            {
                "mark": {"type": "bar", "tooltip": True},
                "encoding": {
                    "x": {"field": "records", "type": "quantitative", "title": "Nodos"},
                    "y": {"field": "node_type", "type": "nominal", "sort": "-x", "title": "Tipo de nodo"},
                },
            },
            use_container_width=True,
        )

        st.markdown("Conjunto cubridor ponderado")
        with st.expander("Modelo matemático formal del cubridor", expanded=False):
            st.markdown(
                r"""
El cubridor se formula como un selector nodal multiobjetivo inspirado en SCP
sobre la red narrativa. No es SCP clásico estricto si no se exige cobertura
total del universo de aristas.

- Universo: aristas objetivo \(A^*\\) después de filtros, exclusiones y peso mínimo.
- Variable nodal: \(x_v \\in \\{0,1\\}\), selecciona o no el nodo candidato.
- Variable de remoción: \(r_a \\in \\{0,1\\}\), indica si la arista se perdería al retirar el conjunto seleccionado.
- Incidencia: \(b_{av}=1\) si la arista \(a\) es incidente al nodo \(v\).

Justificación de objetivos:

- Parsimonia: se minimizan nodos para obtener una explicación legible y no una copia del grafo completo.
- Relevancia: se maximiza peso nodal para conservar actores, fuentes, etapas o conceptos centrales.
- Estructura: se minimiza peso de aristas retiradas para no destruir relaciones narrativas importantes.

En el modo principal, el conjunto \(C\) se interpreta como conjunto cubridor que se retiraría para evaluar su costo estructural.
Por tanto, una arista se cuenta como retirada si toca al menos un nodo seleccionado:

\[
r_{ij} \\geq x_i,\\qquad r_{ij}\\geq x_j,\\qquad r_{ij}\\leq x_i+x_j
\]

Así, el objetivo de aristas no mide el subgrafo inducido por \(C\), sino el peso de relaciones que se perderían al quitar \(C\).

Restricciones principales:

\[
r_a \\geq b_{av}x_v,\\quad
r_a \\leq \\sum_v b_{av}x_v,\\quad
\\sum_v x_v\\leq k,\\quad
x_v\\leq e_v
\]

Objetivos:

\[
\\min \\frac{\\sum_v x_v}{|B|},\\qquad
\\max \\frac{\\sum_v \\sigma_v x_v}{\\sum_v \\sigma_v},\\qquad
\\min \\frac{\\sum_a w_a r_a}{\\sum_a w_a}
\]

El frente se compara con dominancia de Pareto y se resume con hipervolumen
normalizado aproximado por Monte Carlo determinístico.
"""
            )
        cover_method = st.selectbox(
            "Método de solución exploratorio (legado escalar)",
            options=[
                "Glotón local escalar",
                "Algoritmo genético local escalar",
                "Recocido simulado local escalar",
                "Método de composición musical MMC local escalar",
            ],
            index=0,
            help=(
                "Este bloque es exploratorio y usa una función escalar heredada. "
                "Para comparación publicable usa la pestaña 'Cubridor y métodos', que compara weighted_greedy_sweep, MOEA, MOSA y MMC-MO con el mismo presupuesto."
            ),
        )
        st.warning(
            "Bloque legado: estos métodos escalares no son una comparación multiobjetivo estricta. "
            "Úsalos sólo para inspección rápida de nodos; la comparación válida está en 'Cubridor y métodos'."
        )
        cover_objective_label = st.selectbox(
            "Objetivo del cubridor",
            options=[
                "Cubrir máximo peso de aristas",
                "Maximizar peso de nodos y minimizar peso de aristas",
            ],
            index=1,
            help=(
                "El segundo criterio interpreta el peso de arista como costo: busca nodos importantes "
                "que expliquen la red con menor costo relacional."
            ),
        )
        cover_objective = (
            "maximize_node_minimize_edge"
            if cover_objective_label.startswith("Maximizar peso de nodos")
            else "maximize_edge_weight"
        )
        coverage_mode_label = st.selectbox(
            "Criterio para medir aristas",
            options=[
                "Impacto por remoción: cuenta aristas que se eliminarían al quitar el cubridor",
                "Incidencia SCP clásica: una arista queda cubierta si al menos un extremo está seleccionado",
                "Subgrafo inducido exploratorio: conserva aristas sólo si ambos nodos están seleccionados",
            ],
            index=0,
            help=(
                "Para tu modelo usamos impacto por remoción: minimiza el daño estructural causado por quitar los nodos seleccionados."
            ),
        )
        if coverage_mode_label.startswith("Incidencia"):
            coverage_mode = "incident"
        elif coverage_mode_label.startswith("Subgrafo"):
            coverage_mode = "induced"
        else:
            coverage_mode = "removal_impact"
        allowed_cover_types = st.multiselect(
            "Tipos de nodo permitidos en el cubridor",
            options=["actor", "narrative_stage", "narrative_flow", "source", "year", "localization", "source_type", "document"],
            default=["actor", "narrative_stage", "narrative_flow", "source", "source_type", "document"],
            help="Si incluyes documentos, el cubridor puede volverse trivial porque cada documento cubre muchas aristas propias.",
        )
        edge_cover_types = st.multiselect(
            "Tipos de arista a cubrir",
            options=sorted({edge["edge_type"] for edge in narrative_graph["edges"]}),
            default=sorted({edge["edge_type"] for edge in narrative_graph["edges"]}),
        )
        s1, s2, s3 = st.columns(3)
        solver_seed = s1.number_input("Semilla solver", min_value=0, max_value=999999, value=42, step=1)
        population_or_iterations = s2.slider(
            "Población / iteraciones",
            min_value=20,
            max_value=3000,
            value=120,
            step=20,
            help="En genético es número de generaciones aproximado; en recocido son iteraciones/10 visuales.",
        )
        edge_cost_weight = s3.slider("Penalización peso de aristas", 0.1, 5.0, 1.0, step=0.1)
        if cover_method.startswith("Algoritmo genético"):
            cover = genetic_weighted_node_cover(
                narrative_graph,
                max_nodes=cover_max_nodes,
                allowed_node_types=allowed_cover_types,
                edge_types=edge_cover_types,
                generations=int(population_or_iterations),
                seed=int(solver_seed),
                edge_cost_weight=float(edge_cost_weight),
                coverage_mode=coverage_mode,
            )
        elif cover_method.startswith("Método de composición musical"):
            cover = musical_composition_weighted_node_cover(
                narrative_graph,
                max_nodes=cover_max_nodes,
                allowed_node_types=allowed_cover_types,
                edge_types=edge_cover_types,
                composers=12,
                max_arrangements=int(population_or_iterations),
                seed=int(solver_seed),
                edge_cost_weight=float(edge_cost_weight),
                coverage_mode=coverage_mode,
            )
        elif cover_method.startswith("Recocido"):
            cover = annealing_weighted_node_cover(
                narrative_graph,
                max_nodes=cover_max_nodes,
                allowed_node_types=allowed_cover_types,
                edge_types=edge_cover_types,
                iterations=int(population_or_iterations) * 10,
                seed=int(solver_seed),
                edge_cost_weight=float(edge_cost_weight),
                coverage_mode=coverage_mode,
            )
        else:
            cover = greedy_weighted_node_cover(
                narrative_graph,
                max_nodes=cover_max_nodes,
                allowed_node_types=allowed_cover_types,
                edge_types=edge_cover_types,
                objective=cover_objective,
                coverage_mode=coverage_mode,
                edge_cost_weight=float(edge_cost_weight),
            )
        if st.button("Comparar todos los métodos con estos parámetros"):
            comparison_covers = [
                greedy_weighted_node_cover(
                    narrative_graph,
                    max_nodes=cover_max_nodes,
                    allowed_node_types=allowed_cover_types,
                    edge_types=edge_cover_types,
                    objective=cover_objective,
                    coverage_mode=coverage_mode,
                    edge_cost_weight=float(edge_cost_weight),
                ),
                genetic_weighted_node_cover(
                    narrative_graph,
                    max_nodes=cover_max_nodes,
                    allowed_node_types=allowed_cover_types,
                    edge_types=edge_cover_types,
                    generations=int(population_or_iterations),
                    seed=int(solver_seed),
                    edge_cost_weight=float(edge_cost_weight),
                    coverage_mode=coverage_mode,
                ),
                annealing_weighted_node_cover(
                    narrative_graph,
                    max_nodes=cover_max_nodes,
                    allowed_node_types=allowed_cover_types,
                    edge_types=edge_cover_types,
                    iterations=int(population_or_iterations) * 10,
                    seed=int(solver_seed),
                    edge_cost_weight=float(edge_cost_weight),
                    coverage_mode=coverage_mode,
                ),
                musical_composition_weighted_node_cover(
                    narrative_graph,
                    max_nodes=cover_max_nodes,
                    allowed_node_types=allowed_cover_types,
                    edge_types=edge_cover_types,
                    composers=12,
                    max_arrangements=int(population_or_iterations),
                    seed=int(solver_seed),
                    edge_cost_weight=float(edge_cost_weight),
                    coverage_mode=coverage_mode,
                ),
            ]
            st.markdown("Comparación de métodos")
            st.dataframe(
                [
                    {
                        "method": item["stats"].get("method"),
                        "coverage_mode": item["stats"].get("coverage_mode"),
                        "selected_nodes": item["stats"].get("selected_nodes"),
                        "nodes_ratio": item["stats"].get("nodes_ratio"),
                        "node_weight_ratio": item["stats"].get("node_weight_ratio"),
                        "removed_edge_weight_ratio": item["stats"].get("removed_edge_weight_ratio"),
                        "preserved_weight_share": item["stats"].get("preserved_weight_share"),
                        "hypervolume": item["stats"].get("hypervolume"),
                        "objective_value": item["stats"].get("objective_value"),
                    }
                    for item in comparison_covers
                ],
                use_container_width=True,
            )
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Método", cover["stats"].get("method", "greedy"))
        c2.metric("Nodos/total", cover["stats"].get("nodes_ratio", "—"))
        c3.metric("Peso nodal/total", cover["stats"].get("node_weight_ratio", "—"))
        c4.metric("Aristas retiradas/total", cover["stats"].get("removed_edge_weight_ratio", "—"))
        c5.metric("Hipervolumen", cover["stats"].get("hypervolume", "—"))
        c6.metric("Pareto", cover["stats"].get("pareto_solutions", "—"))
        st.dataframe(cover["selected_nodes"], use_container_width=True)
        if cover.get("pareto_front"):
            st.markdown("Frente Pareto multiobjetivo")
            st.caption("Selector nodal inspirado en SCP: minimizar nodos/total, maximizar peso nodal/total y minimizar peso de aristas retiradas/total.")
            st.dataframe(cover["pareto_front"], use_container_width=True)

        with st.expander("Nodos, aristas y comunidades de la red narrativa"):
            st.markdown("Nodos centrales")
            st.dataframe(narrative_graph["nodes"][:120], use_container_width=True)
            st.markdown("Aristas principales")
            st.dataframe(narrative_graph["edges"][:200], use_container_width=True)
            st.markdown("Módulos semánticos")
            st.dataframe(narrative_graph["communities"], use_container_width=True)

    with analysis_tabs[2]:
        st.markdown("Cubridor multiobjetivo y métodos de solución")
        st.caption(
            "Esta pestaña compara glotón por suma ponderada con barrido de pesos, MOEA, MOSA y MMC multiobjetivo. "
            "Todos usan el mismo presupuesto de evaluaciones y la misma semántica de aristas: impacto por remoción."
        )
        event_rows_for_cover = apply_actor_validations(
            extract_narrative_events(selected_records, extra_stopwords=extra_stopwords),
            load_actor_validations(actor_validation_path(analysis_path)),
        )
        mc1, mc2, mc3, mc4 = st.columns(4)
        methods_min_edge = mc1.slider("Peso mínimo de arista para métodos", 1, 20, 1, key="methods_min_edge")
        methods_max_actors = mc2.slider("Actores máximos por documento para métodos", 1, 20, 8, key="methods_max_actors")
        methods_max_nodes = mc3.slider("Máximo de nodos del cubridor", 1, 80, 12, key="methods_max_nodes")
        methods_weighting_mode = mc4.selectbox(
            "Ponderación para métodos",
            options=["neutral", "completeness_stage_emphasis"],
            index=0,
            format_func=lambda value: {
                "neutral": "Neutral/sin jerarquía",
                "completeness_stage_emphasis": "Sensibilidad: etapas y completitud",
            }.get(value, value),
            key="methods_weighting_mode",
            help="Usa neutral para publicación base; el modo con énfasis sirve para análisis de sensibilidad.",
        )
        methods_graph = build_narrative_event_graph(
            event_rows_for_cover,
            min_edge_weight=methods_min_edge,
            max_actors_per_doc=methods_max_actors,
            weighting_mode=methods_weighting_mode,
        )
        sm1, sm2, sm3, sm4, sm5, sm6 = st.columns(6)
        sm1.metric("Nodos", methods_graph["stats"]["nodes"])
        sm2.metric("Aristas", methods_graph["stats"]["edges"])
        sm3.metric("Módulos semánticos", methods_graph["stats"]["communities"])
        sm4.metric("Peso norm. aristas", methods_graph["stats"]["total_edge_weight"])
        sm5.metric("Ponderación", methods_graph["stats"].get("weighting_mode", "neutral"))
        sm6.metric("Documentos", len(event_rows_for_cover))

        st.markdown("Modelo usado en esta pestaña")
        st.markdown(
            r"""
Seleccionamos un conjunto de nodos \(C\subseteq B\). Para cada nodo candidato \(v\in B\), la variable binaria
\(x_v=1\) indica que el nodo entra al cubridor. Para cada arista \(a=(i,j)\in A^\star\), la variable
\(r_a=1\) indica que esa arista se pierde si retiramos los nodos seleccionados.

\[
A_R(C)=\{(i,j)\in A^\star: i\in C \lor j\in C\}
\]

Restricciones de impacto por remoción:

\[
r_{ij}\ge x_i,\qquad r_{ij}\ge x_j,\qquad x_v,r_{ij}\in\{0,1\}
\]

Objetivos originales:

\[
\min |C|/|B|,\qquad
\max \sum_{v\in C}\sigma_v/\sum_{v\in B}\sigma_v,\qquad
\min \sum_{a\in A_R(C)}w_a/\sum_{a\in A^\star}w_a
\]

Para comparar hipervolumen aproximado y frentes se convierten a tres utilidades normalizadas que se maximizan:

\[
u_1=1-|C|/|B|,\qquad
u_2=\sum_{v\in C}\sigma_v/\sum_{v\in B}\sigma_v,\qquad
u_3=1-\sum_{a\in A_R(C)}w_a/\sum_{a\in A^\star}w_a
\]

Por eso el frente es tridimensional. Una gráfica 2D sólo es una proyección; no prueba dominancia por sí sola.
"""
        )
        st.warning(
            "Nota metodológica actualizada: weighted_greedy_sweep, MOEA, MOSA y MMC-MO construyen archivos Pareto directamente. "
            "La comparación justa se hace por el mismo número de evaluaciones de función objetivo."
        )

        render_interactive_network(
            methods_graph,
            title="Red narrativa usada por los métodos",
            max_nodes=100,
            min_edge_weight=float(methods_min_edge),
            height=560,
        )

        available_node_types = ["actor", "narrative_stage", "narrative_flow", "source", "year", "localization", "source_type", "document"]
        available_edge_types = sorted({edge["edge_type"] for edge in methods_graph["edges"]})
        cp1, cp2 = st.columns(2)
        methods_allowed_types = cp1.multiselect(
            "Tipos de nodo permitidos",
            options=available_node_types,
            default=["actor", "narrative_stage", "narrative_flow", "source", "source_type", "document"],
            key="methods_allowed_types",
        )
        methods_edge_types = cp2.multiselect(
            "Tipos de arista considerados",
            options=available_edge_types,
            default=available_edge_types,
            key="methods_edge_types",
        )
        cp3, cp4, cp5 = st.columns(3)
        methods_seed = cp3.number_input("Semilla", min_value=0, max_value=999999, value=42, step=1, key="methods_seed")
        methods_iterations = cp4.slider("Presupuesto de evaluaciones", 100, 10000, 1000, step=100, key="methods_iterations")
        methods_edge_cost = cp5.slider(
            "Peso escalar heredado (no usado por MO puro)",
            0.1,
            5.0,
            1.0,
            step=0.1,
            key="methods_edge_cost",
            help="Se conserva sólo para compatibilidad. En MOEA/MOSA/MMC-MO el daño de aristas es un objetivo separado, no un peso escalar.",
        )
        ac1, ac2, ac3 = st.columns(3)
        acceptable_min_nodes = ac1.slider(
            "Mínimo de nodos aceptable",
            1,
            max(1, int(methods_max_nodes)),
            min(3, max(1, int(methods_max_nodes))),
            key="acceptable_min_nodes",
            help="Evita soluciones triviales de un solo nodo que minimizan daño pero no explican una narrativa.",
        )
        acceptable_min_weight = ac2.slider(
            "Peso nodal mínimo / total",
            0.0,
            0.20,
            0.005,
            step=0.001,
            format="%.3f",
            key="acceptable_min_weight",
            help="Exige que el conjunto cubridor tenga relevancia narrativa mínima.",
        )
        acceptable_max_removed = ac3.slider(
            "Máximo de aristas removidas / total",
            0.0,
            1.0,
            0.10,
            step=0.01,
            format="%.2f",
            key="acceptable_max_removed",
            help="Controla el daño estructural tolerado al retirar el conjunto.",
        )

        if not methods_graph["edges"]:
            st.warning("No hay aristas para resolver. Baja el peso mínimo o revisa filtros del corpus.")
        elif not methods_allowed_types or not methods_edge_types:
            st.warning("Selecciona al menos un tipo de nodo y un tipo de arista.")
        else:
            method_covers = run_all_cover_methods(
                methods_graph,
                max_nodes=int(methods_max_nodes),
                min_nodes=int(acceptable_min_nodes),
                min_node_weight_share=float(acceptable_min_weight),
                max_removed_edge_weight_share=float(acceptable_max_removed),
                allowed_node_types=methods_allowed_types,
                edge_types=methods_edge_types,
                solver_seed=int(methods_seed),
                population_or_iterations=int(methods_iterations),
                edge_cost_weight=float(methods_edge_cost),
                coverage_mode="removal_impact",
            )
            st.markdown("Protocolo común de comparación")
            st.caption("Ningún método se evalúa con reglas especiales; sólo cambia la estrategia de búsqueda.")
            st.dataframe(
                [
                    {"criterio": "Instancia", "valor": "Mismo grafo, mismos nodos candidatos, mismas aristas objetivo y mismas exclusiones."},
                    {"criterio": "Restricciones", "valor": "Mismo presupuesto máximo de nodos, elegibilidad y definición de arista removida."},
                    {"criterio": "Factibilidad", "valor": "Criterio Coello: factible sobre infactible; entre infactibles menor violación; entre factibles Pareto."},
                    {"criterio": "Evaluaciones", "valor": f"Mismo presupuesto de llamadas a la función objetivo: {int(methods_iterations)} por método."},
                    {"criterio": "Métricas", "valor": "Hipervolumen, puntos no dominados globales, IGD, spacing, dispersión, u1, u2 y u3."},
                ],
                use_container_width=True,
            )
            st.markdown("Solución representativa del archivo Pareto por método")
            st.caption(
                "Esta tabla resume una solución elegida desde el archivo Pareto de cada método. "
                "La comparación fuerte está abajo: frente 3D, hipervolumen y puntos globalmente no dominados."
            )
            comparison_rows = cover_comparison_rows(method_covers)
            st.dataframe(comparison_rows, use_container_width=True)
            mmc_rows = [row for row in comparison_rows if row.get("method") == "mmc_mo"]
            if mmc_rows:
                mmc_row = mmc_rows[0]
                lp_seed_status = str(mmc_row.get("lp_seed_status") or "")
                lp_seed_sources = str(mmc_row.get("lp_seed_sources") or "")
                if lp_seed_status.startswith("lp_relaxation_seed_solutions"):
                    st.success(
                        "MMC-MO: guía inicial correcta desde PL relajado y memoria adaptativa activa. "
                        f"Semillas únicas: {mmc_row.get('lp_seed_count')} ({lp_seed_sources}). "
                        f"Caché: {mmc_row.get('lp_seed_cache')}; guía final: {mmc_row.get('guide_final_solutions')} soluciones."
                    )
                else:
                    st.warning(
                        "MMC-MO no está usando PL relajado real en este entorno; está usando semillas deterministas de respaldo. "
                        f"Estado: {lp_seed_status}. Para activar PL instala/actualiza dependencias con `pip install -r requirements.txt`."
                    )
            st.vega_lite_chart(
                comparison_rows,
                {
                    "mark": {"type": "bar", "tooltip": True},
                    "encoding": {
                        "x": {"field": "method", "type": "nominal", "title": "Método"},
                        "y": {"field": "removed_edge_weight_ratio", "type": "quantitative", "title": "Aristas removidas / total"},
                        "color": {"field": "method", "type": "nominal"},
                        "tooltip": [
                            {"field": "method", "type": "nominal"},
                            {"field": "nodes_ratio", "type": "quantitative"},
                            {"field": "node_weight_ratio", "type": "quantitative"},
                            {"field": "removed_edge_weight_ratio", "type": "quantitative"},
                            {"field": "hypervolume", "type": "quantitative"},
                        ],
                    },
                },
                use_container_width=True,
            )
            st.markdown("Frente Pareto combinado")
            st.caption(
                "Aquí sí se ve el comportamiento multiobjetivo: cada fila es un compromiso no dominado entre tamaño, peso narrativo y daño estructural."
            )
            pareto_rows = combined_pareto_rows(method_covers, methods_graph)
            acceptable_pareto_rows = filter_pareto_rows(
                pareto_rows,
                min_solution_size=int(acceptable_min_nodes),
                min_node_weight_ratio=float(acceptable_min_weight),
                max_removed_edge_ratio=float(acceptable_max_removed),
            )
            if pareto_rows:
                render_pareto_3d_diagnostics(pareto_rows, "Cubridor narrativo")
                st.markdown("Frente Pareto combinado: valores originales del modelo")
                st.dataframe(pareto_rows, use_container_width=True)
                st.vega_lite_chart(
                    pareto_rows,
                    {
                        "mark": {"type": "circle", "tooltip": True, "size": 90},
                        "encoding": {
                            "x": {
                                "field": "minimize_removed_edge_weight_ratio",
                                "type": "quantitative",
                                "title": "Daño estructural: aristas removidas / total",
                            },
                            "y": {
                                "field": "maximize_node_weight_ratio",
                                "type": "quantitative",
                                "title": "Relevancia: peso nodal / total",
                            },
                            "color": {"field": "method", "type": "nominal", "title": "Método"},
                            "size": {
                                "field": "solution_size",
                                "type": "quantitative",
                                "title": "Nodos",
                            },
                            "tooltip": [
                                {"field": "method", "type": "nominal"},
                                {"field": "solution_size", "type": "quantitative"},
                                {"field": "maximize_node_weight_ratio", "type": "quantitative"},
                                {"field": "minimize_removed_edge_weight_ratio", "type": "quantitative"},
                                {"field": "compromise_score", "type": "quantitative"},
                                {"field": "node_labels", "type": "nominal"},
                            ],
                        },
                    },
                    use_container_width=True,
                )
                st.markdown("Frente Pareto filtrado por aceptabilidad")
                if acceptable_pareto_rows:
                    st.dataframe(acceptable_pareto_rows, use_container_width=True)
                    best_compromise = acceptable_pareto_rows[0]
                    st.success(
                        "Mejor compromiso aceptable: "
                        f"{best_compromise['method']} · {best_compromise['solution_size']} nodos · "
                        f"peso={best_compromise['maximize_node_weight_ratio']:.5f} · "
                        f"aristas removidas={best_compromise['minimize_removed_edge_weight_ratio']:.5f}"
                    )
                    st.markdown("Nodos del mejor compromiso aceptable")
                    st.dataframe(
                        selected_nodes_from_ids(methods_graph, split_node_ids(best_compromise.get("node_ids", ""))),
                        use_container_width=True,
                    )
                else:
                    st.warning(
                        "No hay soluciones Pareto que cumplan esos umbrales. "
                        "Baja el peso nodal mínimo, sube el máximo de aristas removidas o reduce el mínimo de nodos."
                    )
            else:
                st.warning("Los métodos no generaron frente Pareto con los parámetros actuales.")

            st.markdown("Experimento estadístico multiobjetivo")
            st.caption(
                "Para comparar métodos con seriedad, se repiten las corridas. "
                "En cada corrida se usa la misma semilla para todos los métodos y el mismo número de llamadas a la función objetivo."
            )
            rep1, rep2, rep3 = st.columns(3)
            repeated_runs = rep1.slider(
                "Corridas por método",
                10,
                50,
                10,
                step=5,
                key="cover_repeated_runs",
                help="Mínimo 10 para estimar variabilidad. Más corridas dan mejor evidencia, pero tardan más.",
            )
            repeated_first_seed = rep2.number_input(
                "Primera semilla del experimento",
                min_value=0,
                max_value=999999,
                value=int(methods_seed),
                step=1,
                key="cover_repeated_first_seed",
            )
            rep3.metric("Evaluaciones por método y corrida", int(methods_iterations))
            if st.button("Ejecutar corridas estadísticas", key="run_cover_repeated_experiment"):
                with st.spinner("Ejecutando métodos repetidos y calculando frentes no dominados, bootstrap y Wilcoxon..."):
                    st.session_state.cover_repeated_results = repeated_cover_quality_experiment(
                        methods_graph,
                        max_nodes=int(methods_max_nodes),
                        min_nodes=int(acceptable_min_nodes),
                        min_node_weight_share=float(acceptable_min_weight),
                        max_removed_edge_weight_share=float(acceptable_max_removed),
                        allowed_node_types=methods_allowed_types,
                        edge_types=methods_edge_types,
                        first_seed=int(repeated_first_seed),
                        repetitions=int(repeated_runs),
                        evaluation_budget=int(methods_iterations),
                        edge_cost_weight=float(methods_edge_cost),
                        coverage_mode="removal_impact",
                    )
            if st.session_state.get("cover_repeated_results"):
                render_repeated_cover_quality_results(st.session_state.cover_repeated_results)

            selected_method_label = st.selectbox(
                "Ver detalle del método",
                options=[cover["stats"]["method"] for cover in method_covers],
                key="methods_detail_select",
            )
            selected_cover = next(cover for cover in method_covers if cover["stats"]["method"] == selected_method_label)
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("Nodos/total", selected_cover["stats"].get("nodes_ratio", "—"))
            d2.metric("Peso nodal/total", selected_cover["stats"].get("node_weight_ratio", "—"))
            d3.metric("Aristas removidas/total", selected_cover["stats"].get("removed_edge_weight_ratio", "—"))
            d4.metric("Hipervolumen", selected_cover["stats"].get("hypervolume", "—"))
            st.markdown("Nodos seleccionados por el método")
            st.dataframe(selected_cover["selected_nodes"], use_container_width=True)
            if selected_cover.get("pareto_front"):
                st.markdown("Frente Pareto generado por el método")
                st.dataframe(selected_cover["pareto_front"], use_container_width=True)
            st.download_button("Descargar comparación métodos CSV", rows_to_csv(comparison_rows), "cover_methods_comparison.csv", "text/csv")
            st.download_button("Descargar frente Pareto combinado CSV", rows_to_csv(pareto_rows), "combined_pareto_front.csv", "text/csv")
            st.download_button("Descargar frente Pareto aceptable CSV", rows_to_csv(acceptable_pareto_rows), "acceptable_pareto_front.csv", "text/csv")
            st.download_button("Descargar nodos seleccionados CSV", rows_to_csv(selected_cover["selected_nodes"]), "selected_cover_nodes.csv", "text/csv")

    with analysis_tabs[3]:
        top_n = st.slider("Número de monogramas", 10, 100, 30, step=5)
        terms = pareto_terms(top_terms(selected_records, top_n=top_n, extra_stopwords=extra_stopwords))
        left, right = st.columns(2)
        with left:
            st.markdown("Monogramas / unigramas más frecuentes")
            st.vega_lite_chart(
                terms,
                {
                    "mark": {"type": "bar", "tooltip": True},
                    "encoding": {
                        "y": {"field": "term", "type": "nominal", "sort": "-x", "title": "Término"},
                        "x": {"field": "count", "type": "quantitative", "title": "Frecuencia"},
                    },
                },
                use_container_width=True,
            )
            st.dataframe(terms, use_container_width=True)
        with right:
            st.markdown("Pareto acumulado de monogramas")
            st.vega_lite_chart(
                terms,
                {
                    "layer": [
                        {
                            "mark": {"type": "bar", "tooltip": True},
                            "encoding": {
                                "x": {"field": "term", "type": "nominal", "sort": "-y", "title": "Término"},
                                "y": {"field": "count", "type": "quantitative", "title": "Frecuencia"},
                            },
                        },
                        {
                            "mark": {"type": "line", "point": True, "tooltip": True, "color": "firebrick"},
                            "encoding": {
                                "x": {"field": "term", "type": "nominal", "sort": "-y"},
                                "y": {"field": "cumulative_share", "type": "quantitative", "title": "Proporción acumulada"},
                            },
                        },
                    ],
                    "resolve": {"scale": {"y": "independent"}},
                },
                use_container_width=True,
            )
        st.markdown("Candidatas a palabras vacías del corpus")
        st.caption("Si una palabra aparece demasiado y no aporta significado narrativo, cópiala a Stopwords extra y vuelve a correr el análisis.")
        st.dataframe(stopword_candidates(selected_records, top_n=50), use_container_width=True)

    with analysis_tabs[4]:
        top_n_bigrams = st.slider("Número de bigramas", 10, 100, 30, step=5)
        bigrams = top_ngrams(selected_records, n=2, top_n=top_n_bigrams, extra_stopwords=extra_stopwords)
        st.markdown("Bigramas más frecuentes")
        st.vega_lite_chart(
            bigrams,
            {
                "mark": {"type": "bar", "tooltip": True},
                "encoding": {
                    "y": {"field": "ngram", "type": "nominal", "sort": "-x", "title": "Bigrama"},
                    "x": {"field": "count", "type": "quantitative", "title": "Frecuencia"},
                },
            },
            use_container_width=True,
        )
        st.dataframe(bigrams, use_container_width=True)

    with analysis_tabs[5]:
        top_n_trigrams = st.slider("Número de trigramas", 10, 100, 30, step=5)
        trigrams = top_ngrams(selected_records, n=3, top_n=top_n_trigrams, extra_stopwords=extra_stopwords)
        st.markdown("Trigramas más frecuentes")
        st.vega_lite_chart(
            trigrams,
            {
                "mark": {"type": "bar", "tooltip": True},
                "encoding": {
                    "y": {"field": "ngram", "type": "nominal", "sort": "-x", "title": "Trigrama"},
                    "x": {"field": "count", "type": "quantitative", "title": "Frecuencia"},
                },
            },
            use_container_width=True,
        )
        st.dataframe(trigrams, use_container_width=True)

    with analysis_tabs[6]:
        st.markdown("Grupos de ideas / tópicos locales")
        st.caption("Los grupos se calculan por diccionarios editables, pero pueden inicializarse desde comunidades y nodos centrales del grafo de conocimiento.")
        suggested_group_graph = build_knowledge_graph(
            selected_records,
            top_n_each=25,
            min_node_count=1,
            min_edge_weight=1,
            extra_stopwords=extra_stopwords,
        )
        suggested_adaptive_groups = adaptive_topic_groups_from_graph(suggested_group_graph)
        suggested_group_text = adaptive_groups_to_dictionary_text(suggested_adaptive_groups)
        inherited_ai_dictionary = "productivity_promise:" in st.session_state.idea_group_text and "productivity_promise" not in default_groups
        if not st.session_state.idea_group_text or inherited_ai_dictionary:
            st.session_state.idea_group_text = suggested_group_text or default_group_text
        c_auto, c_reset = st.columns(2)
        if c_auto.button("Usar grupos centrales del grafo"):
            st.session_state.idea_group_text = suggested_group_text or default_group_text
            st.rerun()
        if c_reset.button("Usar diccionario base"):
            st.session_state.idea_group_text = default_group_text
            st.rerun()
        with st.expander("Diccionario sugerido desde el grafo"):
            st.caption("Si aparecen términos como cigar, cigars, halfwheel o tobacco, el corpus está capturando la marca de cigarros Tatuaje y no sólo tatuaje corporal.")
            st.code(suggested_group_text or "No se generaron grupos adaptativos con los filtros actuales.")
        group_text = st.text_area(
            "Diccionario editable de grupos",
            value=st.session_state.idea_group_text,
            help="Formato: nombre_grupo: palabra1, palabra2, frase corta. Puedes agregar o cambiar grupos.",
            height=220,
        )
        st.session_state.idea_group_text = group_text
        groups = parse_idea_groups(group_text, base_groups=default_groups)
        group_rows = idea_group_counts(selected_records, groups)
        group_year_rows = idea_group_counts_by_year(selected_records, groups)
        matrix_rows = idea_group_document_matrix(selected_records, groups)
        st.vega_lite_chart(
            group_rows,
            {
                "mark": {"type": "bar", "tooltip": True},
                "encoding": {
                    "y": {"field": "idea_group", "type": "nominal", "sort": "-x", "title": "Grupo de ideas"},
                    "x": {"field": "keyword_hits", "type": "quantitative", "title": "Menciones"},
                    "tooltip": [
                        {"field": "idea_group", "type": "nominal"},
                        {"field": "keyword_hits", "type": "quantitative"},
                        {"field": "documents_with_group", "type": "quantitative"},
                        {"field": "document_share", "type": "quantitative"},
                        {"field": "top_terms", "type": "nominal"},
                    ],
                },
            },
            use_container_width=True,
        )
        st.markdown("Evolución anual de grupos de ideas")
        st.vega_lite_chart(
            group_year_rows,
            {
                "mark": {"type": "line", "point": True, "tooltip": True},
                "encoding": {
                    "x": {"field": "year", "type": "ordinal", "title": "Año"},
                    "y": {"field": "keyword_hits", "type": "quantitative", "title": "Menciones"},
                    "color": {"field": "idea_group", "type": "nominal", "title": "Grupo"},
                },
            },
            use_container_width=True,
        )
        st.markdown("Tabla de grupos")
        st.dataframe(group_rows, use_container_width=True)
        st.markdown("Matriz documento × grupo de ideas")
        st.dataframe(matrix_rows, use_container_width=True)

    with analysis_tabs[7]:
        st.markdown("Grafo de conocimiento local")
        st.caption("Incluye monogramas, bigramas, trigramas, fuentes, años, idioma y localización. Los grupos adaptativos salen de comunidades del grafo.")
        c1, c2, c3 = st.columns(3)
        kg_top_n = c1.slider("Top por tipo de n-grama", 10, 80, 30, step=5)
        kg_min_node = c2.slider("Frecuencia mínima de nodo", 1, 10, 1)
        kg_min_edge = c3.slider("Peso mínimo de arista", 1, 10, 1)
        knowledge_graph = build_knowledge_graph(
            selected_records,
            top_n_each=kg_top_n,
            min_node_count=kg_min_node,
            min_edge_weight=kg_min_edge,
            extra_stopwords=extra_stopwords,
        )
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Nodos", knowledge_graph["stats"]["nodes"])
        k2.metric("Aristas", knowledge_graph["stats"]["edges"])
        k3.metric("Monogramas", knowledge_graph["stats"]["monograms"])
        k4.metric("Bigramas", knowledge_graph["stats"]["bigrams"])
        k5.metric("Trigramas", knowledge_graph["stats"]["trigrams"])

        node_type_counts = count_rows(knowledge_graph["nodes"], ["node_type"])
        st.markdown("Composición del grafo")
        st.vega_lite_chart(
            node_type_counts,
            {
                "mark": {"type": "bar", "tooltip": True},
                "encoding": {
                    "x": {"field": "records", "type": "quantitative", "title": "Nodos"},
                    "y": {"field": "node_type", "type": "nominal", "sort": "-x", "title": "Tipo de nodo"},
                },
            },
            use_container_width=True,
        )

        st.markdown("Análisis estructural de la red compleja")
        structural_rows = graph_structural_summary(knowledge_graph)
        st.dataframe(structural_rows, use_container_width=True)
        edge_type_counts = count_rows(knowledge_graph["edges"], ["edge_type"])
        st.markdown("Tipos de arista")
        st.vega_lite_chart(
            edge_type_counts,
            {
                "mark": {"type": "bar", "tooltip": True},
                "encoding": {
                    "x": {"field": "records", "type": "quantitative", "title": "Aristas"},
                    "y": {"field": "edge_type", "type": "nominal", "sort": "-x", "title": "Tipo de arista"},
                },
            },
            use_container_width=True,
        )

        st.markdown("Relaciones principales de la red")
        st.vega_lite_chart(
            knowledge_graph["edges"][:40],
            {
                "mark": {"type": "bar", "tooltip": True},
                "encoding": {
                    "x": {"field": "weight", "type": "quantitative", "title": "Peso normalizado [0,1]"},
                    "y": {"field": "source", "type": "nominal", "sort": "-x", "title": "Origen"},
                    "color": {"field": "edge_type", "type": "nominal", "title": "Tipo"},
                    "tooltip": [
                        {"field": "source", "type": "nominal"},
                        {"field": "target", "type": "nominal"},
                        {"field": "edge_type", "type": "nominal"},
                        {"field": "weight", "type": "quantitative"},
                        {"field": "raw_weight", "type": "quantitative"},
                    ],
                },
            },
            use_container_width=True,
        )

        st.markdown("Matrices locales término–fuente y término–año")
        st.caption(
            "Inspirado en el segundo script: matrices normalizadas después de limpieza local. "
            "Sirven para detectar qué medios o años cargan ciertos términos, bigramas o trigramas."
        )
        matrix_cols = st.columns(3)
        matrix_dimension = matrix_cols[0].selectbox(
            "Dimensión de matriz",
            ["medium", "year", "source_type"],
            format_func=lambda item: {"medium": "Medio/fuente", "year": "Año", "source_type": "Tipo de fuente"}[item],
            key="ngram_matrix_dimension",
        )
        matrix_n = matrix_cols[1].multiselect(
            "N-gramas en matriz",
            options=[1, 2, 3],
            default=[1, 2],
            key="ngram_matrix_n",
        )
        matrix_top_terms = matrix_cols[2].slider("Términos máximos en matriz", 20, 150, 80, step=10)
        matrix_rows = ngram_dimension_matrix(
            selected_records,
            dimension=matrix_dimension,
            n_values=matrix_n or [1, 2],
            top_terms=matrix_top_terms,
            extra_stopwords=extra_stopwords,
        )
        if matrix_rows:
            st.vega_lite_chart(
                matrix_rows,
                {
                    "mark": {"type": "rect", "tooltip": True},
                    "encoding": {
                        "x": {"field": "term", "type": "nominal", "sort": "-color", "title": "Término / frase"},
                        "y": {"field": "dimension_value", "type": "nominal", "title": "Dimensión"},
                        "color": {
                            "field": "count_norm",
                            "type": "quantitative",
                            "title": "Conteo normalizado",
                            "scale": {"scheme": "viridis", "domain": [0, 1]},
                        },
                        "tooltip": [
                            {"field": "dimension_value", "type": "nominal"},
                            {"field": "term", "type": "nominal"},
                            {"field": "count", "type": "quantitative"},
                            {"field": "count_norm", "type": "quantitative"},
                            {"field": "within_dimension_share", "type": "quantitative"},
                        ],
                    },
                },
                use_container_width=True,
            )
            st.dataframe(matrix_rows[:300], use_container_width=True)
            st.download_button("Descargar matriz término-dimensión CSV", rows_to_csv(matrix_rows), "ngram_dimension_matrix.csv", "text/csv")
        else:
            st.info("No hay suficientes textos para construir la matriz término-dimensión.")

        st.markdown("Nodos centrales del grafo de conocimiento")
        st.caption("`knowledge_degree` ahora está normalizado en [0,1]: combina frecuencia normalizada y grado ponderado normalizado.")
        st.vega_lite_chart(
            knowledge_graph["nodes"][:30],
            {
                "mark": {"type": "bar", "tooltip": True},
                "encoding": {
                    "x": {"field": "knowledge_degree", "type": "quantitative", "title": "Grado de conocimiento"},
                    "y": {"field": "label", "type": "nominal", "sort": "-x", "title": "Nodo"},
                    "color": {"field": "node_type", "type": "nominal", "title": "Tipo"},
                },
            },
            use_container_width=True,
        )
        st.markdown("Distribución de pesos y diagnóstico de tipo de red")
        st.dataframe(graph_structural_summary(knowledge_graph), use_container_width=True)
        if knowledge_graph.get("phrase_composition"):
            st.markdown("Composición canónica de frases")
            st.caption("Monogramas/bigramas absorbidos por frases repetidas cuando la frase explica la mayor parte de sus apariciones.")
            st.dataframe(knowledge_graph["phrase_composition"][:120], use_container_width=True)
        st.dataframe(knowledge_graph["nodes"][:80], use_container_width=True)
        st.markdown("Aristas principales")
        st.dataframe(knowledge_graph["edges"][:150], use_container_width=True)

        adaptive_groups = adaptive_topic_groups_from_graph(knowledge_graph)
        st.markdown("Grupos adaptativos por n-grama central")
        st.dataframe(adaptive_groups, use_container_width=True)
        st.markdown("Módulos semánticos del grafo")
        st.dataframe(knowledge_graph["communities"], use_container_width=True)
        st.caption("Estos grupos cambian con el tópico, filtros, stopwords y umbrales. Úsalos como propuesta inicial y luego edita el diccionario en 'Grupos de ideas'.")

    with analysis_tabs[8]:
        frames = frame_counts(selected_records)
        frames_year = frame_counts_by_year(selected_records)
        st.markdown("Marcos narrativos detectados por diccionario local")
        st.vega_lite_chart(
            frames,
            {
                "mark": {"type": "bar", "tooltip": True},
                "encoding": {
                    "y": {"field": "frame", "type": "nominal", "sort": "-x", "title": "Marco"},
                    "x": {"field": "keyword_hits", "type": "quantitative", "title": "Menciones"},
                    "tooltip": [
                        {"field": "frame", "type": "nominal"},
                        {"field": "keyword_hits", "type": "quantitative"},
                        {"field": "documents_with_frame", "type": "quantitative"},
                        {"field": "document_share", "type": "quantitative"},
                        {"field": "top_terms", "type": "nominal"},
                    ],
                },
            },
            use_container_width=True,
        )
        st.dataframe(frames, use_container_width=True)

        st.markdown("Evolución anual de marcos narrativos")
        st.vega_lite_chart(
            frames_year,
            {
                "mark": {"type": "line", "point": True, "tooltip": True},
                "encoding": {
                    "x": {"field": "year", "type": "ordinal", "title": "Año"},
                    "y": {"field": "keyword_hits", "type": "quantitative", "title": "Menciones"},
                    "color": {"field": "frame", "type": "nominal", "title": "Marco"},
                },
            },
            use_container_width=True,
        )
        st.dataframe(frames_year, use_container_width=True)

    with analysis_tabs[9]:
        st.markdown("Red semántica local con comunidades y cubridor")
        st.caption(
            "Construye una red de coocurrencia limpia, detecta comunidades con Louvain/modularidad y aplica el mismo modelo de cubridor multiobjetivo."
        )
        c1, c2, c3, c4 = st.columns(4)
        top_network_terms = c1.slider("Términos en red", 20, 120, 50, step=10)
        window_size = c2.slider("Ventana de coocurrencia", 2, 10, 4)
        min_cooc = c3.slider("Coocurrencia mínima", 1, 10, 1)
        semantic_community_algorithm = c4.selectbox(
            "Módulos semánticos",
            options=["louvain", "greedy_modularity", "connected_components"],
            index=0,
            help="Louvain si está disponible localmente; si no, la app cae a modularidad voraz.",
        )
        network = build_cooccurrence_network(
            selected_records,
            top_n_terms=top_network_terms,
            window_size=window_size,
            min_cooccurrence=min_cooc,
            extra_stopwords=extra_stopwords,
            community_algorithm=semantic_community_algorithm,
        )
        s1, s2, s3, s4, s5, s6, s7 = st.columns(7)
        s1.metric("Nodos", network["stats"]["nodes"])
        s2.metric("Aristas", network["stats"]["edges"])
        s3.metric("Densidad", network["stats"]["density"])
        s4.metric("Módulos semánticos", network["stats"]["communities"])
        s5.metric("Algoritmo", network["stats"].get("community_algorithm", "—"))
        s6.metric("Modularidad", network["stats"].get("modularity", "—"))
        s7.metric("Frases absorbidas", network["stats"].get("absorbed_ngrams", 0))

        st.markdown("Diagnóstico de distribución de pesos")
        st.dataframe(graph_structural_summary(network), use_container_width=True)
        if network.get("phrase_composition"):
            st.markdown("Composición canónica usada por la red semántica")
            st.caption("Estos términos pequeños no se analizan como nodos independientes cuando están explicados por una frase repetida.")
            st.dataframe(network["phrase_composition"][:120], use_container_width=True)

        semantic_visual_min_weight = st.slider(
            "Peso mínimo visual normalizado de red semántica",
            min_value=0.0,
            max_value=1.0,
            value=0.0,
            step=0.05,
            help="La coocurrencia mínima filtra conteos crudos; este control sólo filtra la visualización normalizada.",
        )

        render_interactive_network(
            network,
            title="Red semántica de coocurrencias",
            max_nodes=min(100, int(top_network_terms)),
            min_edge_weight=float(semantic_visual_min_weight),
            height=560,
        )

        st.markdown("Nodos centrales")
        st.dataframe(network["nodes"][:30], use_container_width=True)
        st.markdown("Aristas principales")
        st.dataframe(network["edges"][:100], use_container_width=True)
        st.markdown("Comunidades semánticas")
        st.caption(
            "Si Louvain funciona localmente, estas comunidades son módulos de alta coocurrencia interna; "
            "si no, se usa la alternativa indicada en la métrica de algoritmo."
        )
        st.dataframe(network["communities"], use_container_width=True)

        st.markdown("Cubridor multiobjetivo sobre red semántica")
        st.caption(
            "Aquí el conjunto cubridor son conceptos. El tercer objetivo mide las aristas semánticas que se perderían al retirar esos conceptos."
        )
        sc1, sc2, sc3, sc4 = st.columns(4)
        semantic_cover_max_nodes = sc1.slider("Máximo nodos cubridor semántico", 1, 40, 10)
        semantic_solver_seed = sc2.number_input("Semilla semántica", min_value=0, max_value=999999, value=42, step=1)
        semantic_iterations = sc3.slider("Presupuesto evaluaciones semánticas", 100, 10000, 1000, step=100)
        semantic_edge_cost = sc4.slider(
            "Peso escalar semántico heredado",
            0.1,
            5.0,
            1.0,
            step=0.1,
            help="No controla los métodos MO puros; el daño de aristas semánticas es el tercer objetivo.",
        )
        sa1, sa2, sa3 = st.columns(3)
        semantic_min_nodes = sa1.slider("Mínimo nodos aceptable semántico", 1, max(1, int(semantic_cover_max_nodes)), min(3, max(1, int(semantic_cover_max_nodes))))
        semantic_min_weight = sa2.slider("Peso nodal mínimo semántico / total", 0.0, 0.20, 0.005, step=0.001, format="%.3f")
        semantic_max_removed = sa3.slider("Máximo aristas semánticas removidas / total", 0.0, 1.0, 0.10, step=0.01, format="%.2f")

        if not network["edges"]:
            st.warning("No hay aristas semánticas suficientes. Baja coocurrencia mínima o sube términos en red.")
        else:
            semantic_covers = run_all_cover_methods(
                network,
                max_nodes=int(semantic_cover_max_nodes),
                min_nodes=int(semantic_min_nodes),
                min_node_weight_share=float(semantic_min_weight),
                max_removed_edge_weight_share=float(semantic_max_removed),
                allowed_node_types=["monogram", "bigram", "trigram", "term"],
                edge_types=["cooccurrence"],
                solver_seed=int(semantic_solver_seed),
                population_or_iterations=int(semantic_iterations),
                edge_cost_weight=float(semantic_edge_cost),
                coverage_mode="removal_impact",
            )
            st.markdown("Protocolo común de comparación semántica")
            st.caption("Mismo protocolo que en la red narrativa; sólo cambia la red de entrada.")
            st.dataframe(
                [
                    {"criterio": "Instancia", "valor": "Misma red semántica, mismos conceptos candidatos y mismas aristas de coocurrencia."},
                    {"criterio": "Restricciones", "valor": "Mismo máximo de nodos y misma definición de arista removida."},
                    {"criterio": "Factibilidad", "valor": "Criterio Coello común para todos los métodos."},
                    {"criterio": "Evaluaciones", "valor": f"Mismo presupuesto de llamadas a la función objetivo: {int(semantic_iterations)} por método."},
                    {"criterio": "Métricas", "valor": "Hipervolumen, puntos no dominados globales, IGD, spacing, dispersión, u1, u2 y u3."},
                ],
                use_container_width=True,
            )
            semantic_comparison_rows = cover_comparison_rows(semantic_covers)
            st.markdown("Solución representativa del archivo Pareto por método")
            st.dataframe(semantic_comparison_rows, use_container_width=True)

            semantic_pareto_rows = combined_pareto_rows(semantic_covers, network)
            semantic_acceptable_rows = filter_pareto_rows(
                semantic_pareto_rows,
                min_solution_size=int(semantic_min_nodes),
                min_node_weight_ratio=float(semantic_min_weight),
                max_removed_edge_ratio=float(semantic_max_removed),
            )
            st.markdown("Frente Pareto semántico combinado")
            st.dataframe(semantic_pareto_rows, use_container_width=True)
            if semantic_pareto_rows:
                render_pareto_3d_diagnostics(semantic_pareto_rows, "Cubridor semántico")
                st.vega_lite_chart(
                    semantic_pareto_rows,
                    {
                        "mark": {"type": "circle", "tooltip": True, "size": 90},
                        "encoding": {
                            "x": {
                                "field": "minimize_removed_edge_weight_ratio",
                                "type": "quantitative",
                                "title": "Aristas semánticas removidas / total",
                            },
                            "y": {
                                "field": "maximize_node_weight_ratio",
                                "type": "quantitative",
                                "title": "Peso conceptual / total",
                            },
                            "color": {"field": "method", "type": "nominal"},
                            "size": {"field": "solution_size", "type": "quantitative", "title": "Nodos"},
                            "tooltip": [
                                {"field": "method", "type": "nominal"},
                                {"field": "solution_size", "type": "quantitative"},
                                {"field": "maximize_node_weight_ratio", "type": "quantitative"},
                                {"field": "minimize_removed_edge_weight_ratio", "type": "quantitative"},
                                {"field": "node_labels", "type": "nominal"},
                            ],
                        },
                    },
                    use_container_width=True,
                )

            st.markdown("Frente Pareto semántico aceptable")
            if semantic_acceptable_rows:
                st.dataframe(semantic_acceptable_rows, use_container_width=True)
                semantic_best = semantic_acceptable_rows[0]
                st.success(
                    "Mejor compromiso semántico: "
                    f"{semantic_best['method']} · {semantic_best['solution_size']} conceptos · "
                    f"peso={semantic_best['maximize_node_weight_ratio']:.5f} · "
                    f"aristas removidas={semantic_best['minimize_removed_edge_weight_ratio']:.5f}"
                )
                st.dataframe(
                    selected_nodes_from_ids(network, split_node_ids(semantic_best.get("node_ids", ""))),
                    use_container_width=True,
                )
            else:
                st.warning("No hay soluciones semánticas aceptables con esos umbrales.")

            st.download_button("Descargar comparación cubridor semántico CSV", rows_to_csv(semantic_comparison_rows), "semantic_cover_methods.csv", "text/csv")
            st.download_button("Descargar Pareto semántico CSV", rows_to_csv(semantic_pareto_rows), "semantic_cover_pareto.csv", "text/csv")

    with analysis_tabs[10]:
        st.markdown("Disección estructural de narrativas")
        st.caption(
            "Esta capa no afirma verdad judicial ni psicológica. Produce indicadores locales: "
            "proposiciones sujeto-verbo-objeto, actos de habla, causalidad, premisas implícitas, "
            "marcadores retóricos revisables, entropía narrativa y trazabilidad técnica."
        )
        sd1, sd2 = st.columns(2)
        max_sentences_per_doc = sd1.slider("Máximo de oraciones por documento", 5, 120, 40, step=5)
        min_structural_edge_weight = sd2.slider("Peso mínimo arista estructural", 1, 20, 2)
        expected_topics_text = st.text_area(
            "Temas/hechos esperados para detectar silencios",
            value="regulación sanitaria, riesgos de infección, consentimiento informado, discriminación laboral, tintas no autorizadas",
            help=(
                "Separados por coma. La app NO inventa silencios: compara estos temas esperados contra los marcos extraídos."
            ),
        )
        expected_topics = [item.strip() for item in expected_topics_text.split(",") if item.strip()]

        structural_rows = extract_structural_propositions(selected_records, max_sentences_per_doc=int(max_sentences_per_doc))
        structural_summary_rows = structural_summary(structural_rows)
        structural_graph = build_structural_influence_graph(structural_rows, min_weight=int(min_structural_edge_weight))
        custody_rows = technical_traceability_rows(selected_records)
        sdn = smart_data_nucleus(selected_records, expected_topics=expected_topics)

        total_props = len(structural_rows)
        causal_props = sum(1 for row in structural_rows if row.get("has_causal_relation"))
        fallacy_props = sum(1 for row in structural_rows if row.get("fallacies"))
        vector_props = sum(1 for row in structural_rows if row.get("disinformation_vectors"))
        hidden_premises = sum(1 for row in structural_rows if row.get("hidden_premise_hint"))
        dm1, dm2, dm3, dm4, dm5 = st.columns(5)
        dm1.metric("Proposiciones", total_props)
        dm2.metric("Causalidad", causal_props)
        dm3.metric("Marcadores retóricos", fallacy_props)
        dm4.metric("Presión narrativa", vector_props)
        dm5.metric("Hipótesis implícitas", hidden_premises)

        st.markdown("Smart Data Nucleus: poda inteligente")
        st.caption(
            "Capa 1–4: cartografía Pareto de fuentes, extracción de marcos, detección de ecos, "
            "deltas temporales y silencios. Aquí el sistema guarda estructura y relaciones, no volumen bruto."
        )
        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("Fuentes totales", len(sdn["cartography"]["sources"]))
        sc2.metric("Fuentes Pareto", len(sdn["cartography"]["pareto_sources"]))
        sc3.metric("Marcos", len(sdn["frames"]))
        sc4.metric("Alertas de silencio", sum(1 for row in sdn["silence_alerts"] if row.get("alert")))

        st.markdown("Capa 1 · Cartografía de fuentes")
        st.dataframe(sdn["cartography"]["sources"], use_container_width=True)
        st.markdown("Núcleo Pareto 20/80")
        st.dataframe(sdn["cartography"]["pareto_sources"], use_container_width=True)

        st.markdown("Capa 2 · Marcos argumentales")
        st.caption("Problema, culpable, solución y urgencia. Los ecos se guardan como relación, no como texto redundante.")
        st.dataframe(sdn["frames"], use_container_width=True)

        st.markdown("Capa 3 · Deltas temporales")
        st.caption("Sólo los cambios estructurales deberían escalar a revisión; repeticiones quedan como contador temporal.")
        st.dataframe(sdn["temporal_deltas"], use_container_width=True)

        st.markdown("Capa 4 · Silencios estructurales")
        st.caption("Alertas sobre temas esperados ausentes en la mayoría de fuentes Pareto.")
        st.dataframe(sdn["silence_alerts"], use_container_width=True)

        st.markdown("Resumen estructural por año y tipo de fuente")
        st.dataframe(structural_summary_rows, use_container_width=True)
        if structural_summary_rows:
            st.vega_lite_chart(
                structural_summary_rows,
                {
                    "mark": {"type": "line", "point": True, "tooltip": True},
                    "encoding": {
                        "x": {"field": "year", "type": "ordinal", "title": "Año"},
                        "y": {"field": "speech_act_entropy", "type": "quantitative", "title": "Entropía actos de habla"},
                        "color": {"field": "source_type", "type": "nominal", "title": "Tipo de fuente"},
                        "tooltip": [
                            {"field": "year", "type": "ordinal"},
                            {"field": "source_type", "type": "nominal"},
                            {"field": "propositions", "type": "quantitative"},
                            {"field": "causal_relations", "type": "quantitative"},
                            {"field": "fallacy_signals", "type": "quantitative"},
                            {"field": "disinformation_vector_signals", "type": "quantitative"},
                            {"field": "speech_act_entropy", "type": "quantitative"},
                            {"field": "predicate_entropy", "type": "quantitative"},
                        ],
                    },
                },
                use_container_width=True,
            )

        st.markdown("Proposiciones estructurales")
        st.caption(
            "SVO y marcadores retóricos son heurísticas locales. Deben validarse: sirven como lupa de auditoría, "
            "no como sentencia automática."
        )
        st.dataframe(structural_rows, use_container_width=True)

        st.markdown("Grafo estructural de influencia")
        gc1, gc2 = st.columns(2)
        gc1.metric("Nodos estructurales", len(structural_graph["nodes"]))
        gc2.metric("Aristas estructurales", len(structural_graph["edges"]))
        st.dataframe(structural_graph["nodes"], use_container_width=True)
        st.dataframe(structural_graph["edges"], use_container_width=True)

        st.markdown("Trazabilidad técnica digital")
        st.caption(
            "Cada registro recibe hash SHA-256 sobre URL, título, fecha, estado, momento de captura y texto. "
            "Esto no vuelve admisible el dato por sí solo, pero sí hace auditable la integridad del corpus."
        )
        st.dataframe(custody_rows, use_container_width=True)

        structural_bundle = {
            "metadata": {
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "method": "local_structural_heuristics_v1",
                "records": len(selected_records),
                "propositions": len(structural_rows),
                "legal_note": "OSINT público; no intrusión; señales heurísticas sujetas a validación humana.",
            },
            "summary": structural_summary_rows,
            "propositions": structural_rows,
            "smart_data_nucleus": sdn,
            "structural_graph": structural_graph,
            "technical_traceability": custody_rows,
        }
        st.download_button("Descargar cartografía fuentes CSV", rows_to_csv(sdn["cartography"]["sources"]), "sdn_source_cartography.csv", "text/csv")
        st.download_button("Descargar fuentes Pareto CSV", rows_to_csv(sdn["cartography"]["pareto_sources"]), "sdn_pareto_sources.csv", "text/csv")
        st.download_button("Descargar marcos SDN CSV", rows_to_csv(sdn["frames"]), "sdn_argument_frames.csv", "text/csv")
        st.download_button("Descargar deltas SDN CSV", rows_to_csv(sdn["temporal_deltas"]), "sdn_temporal_deltas.csv", "text/csv")
        st.download_button("Descargar silencios SDN CSV", rows_to_csv(sdn["silence_alerts"]), "sdn_silence_alerts.csv", "text/csv")
        st.download_button("Descargar proposiciones CSV", rows_to_csv(structural_rows), "structural_propositions.csv", "text/csv")
        st.download_button("Descargar resumen estructural CSV", rows_to_csv(structural_summary_rows), "structural_summary.csv", "text/csv")
        st.download_button("Descargar nodos estructurales CSV", rows_to_csv(structural_graph["nodes"]), "structural_graph_nodes.csv", "text/csv")
        st.download_button("Descargar aristas estructurales CSV", rows_to_csv(structural_graph["edges"]), "structural_graph_edges.csv", "text/csv")
        st.download_button("Descargar trazabilidad técnica CSV", rows_to_csv(custody_rows), "technical_traceability.csv", "text/csv")
        st.download_button(
            "Descargar disección estructural JSON",
            json.dumps(structural_bundle, ensure_ascii=False, indent=2),
            "structural_narrative_dissection.json",
            "application/json",
        )

    with analysis_tabs[11]:
        st.markdown("Sentimiento local por fuente y año")
        st.caption(
            "Análisis léxico local bilingüe. Es exploratorio y auditable: no usa LLM ni servicios externos. "
            "Sirve para comparar capas discursivas, no para afirmar emociones individuales."
        )
        s1, s2 = st.columns(2)
        extra_positive_text = s1.text_area(
            "Términos positivos extra",
            value="",
            help="Separados por coma. Útil si el tópico tiene vocabulario propio de aceptación/valoración.",
        )
        extra_negative_text = s2.text_area(
            "Términos negativos extra",
            value="",
            help="Separados por coma. Útil si el tópico tiene vocabulario propio de rechazo/riesgo.",
        )
        extra_positive = split_terms(extra_positive_text)
        extra_negative = split_terms(extra_negative_text)
        sentiment_rows = sentiment_document_rows(selected_records, extra_positive=extra_positive, extra_negative=extra_negative)
        sentiment_summary = sentiment_by_year_source(sentiment_rows)

        avg_sentiment = sum(row["sentiment_score"] for row in sentiment_rows) / max(1, len(sentiment_rows))
        positive_docs = sum(1 for row in sentiment_rows if row["sentiment_label"] == "positive")
        negative_docs = sum(1 for row in sentiment_rows if row["sentiment_label"] == "negative")
        neutral_docs = sum(1 for row in sentiment_rows if row["sentiment_label"] == "neutral_or_mixed")
        sm1, sm2, sm3, sm4 = st.columns(4)
        sm1.metric("Sentimiento promedio", f"{avg_sentiment:+.3f}")
        sm2.metric("Positivos", positive_docs)
        sm3.metric("Negativos", negative_docs)
        sm4.metric("Neutros/mixtos", neutral_docs)

        st.markdown("Promedio por año y tipo de fuente")
        st.dataframe(sentiment_summary, use_container_width=True)
        if sentiment_summary:
            st.vega_lite_chart(
                sentiment_summary,
                {
                    "mark": {"type": "line", "point": True, "tooltip": True},
                    "encoding": {
                        "x": {"field": "year", "type": "ordinal", "title": "Año"},
                        "y": {
                            "field": "mean_sentiment",
                            "type": "quantitative",
                            "title": "Sentimiento promedio [-1,1]",
                            "scale": {"domain": [-1, 1]},
                        },
                        "color": {"field": "source_type", "type": "nominal", "title": "Fuente"},
                        "tooltip": [
                            {"field": "year", "type": "ordinal"},
                            {"field": "source_type", "type": "nominal"},
                            {"field": "documents", "type": "quantitative"},
                            {"field": "mean_sentiment", "type": "quantitative"},
                            {"field": "sentiment_std", "type": "quantitative"},
                        ],
                    },
                },
                use_container_width=True,
            )

            st.markdown("Gráficas radiales por año")
            st.caption("Cada eje es un tipo de fuente; el valor mostrado es el promedio de sentimiento normalizado al radio.")
            source_order = sorted({row["source_type"] for row in sentiment_summary})
            years_for_radar = sorted({int(row["year"]) for row in sentiment_summary})
            selected_radar_years = st.multiselect("Años para radar", years_for_radar, default=years_for_radar[: min(3, len(years_for_radar))])
            for year in selected_radar_years:
                components.html(sentiment_radar_svg(sentiment_summary, year, source_order), height=450, scrolling=False)

        st.markdown("Documento × sentimiento")
        st.dataframe(sentiment_rows, use_container_width=True)
        st.download_button("Descargar sentimiento por documento CSV", rows_to_csv(sentiment_rows), "sentiment_documents.csv", "text/csv")
        st.download_button("Descargar sentimiento por año/fuente CSV", rows_to_csv(sentiment_summary), "sentiment_by_year_source.csv", "text/csv")

    with analysis_tabs[12]:
        terms = pareto_terms(top_terms(selected_records, top_n=100, extra_stopwords=extra_stopwords))
        bigrams = top_ngrams(selected_records, n=2, top_n=100, extra_stopwords=extra_stopwords)
        trigrams = top_ngrams(selected_records, n=3, top_n=100, extra_stopwords=extra_stopwords)
        frames = frame_counts(selected_records)
        actor_validations = load_actor_validations(actor_validation_path(analysis_path))
        event_rows = apply_actor_validations(extract_narrative_events(selected_records, extra_stopwords=extra_stopwords), actor_validations)
        event_summary = narrative_event_summary(event_rows)
        actors = actor_counts(event_rows)
        narrative_graph = build_narrative_event_graph(event_rows)
        narrative_cover = greedy_weighted_node_cover(
            narrative_graph,
            objective="maximize_node_minimize_edge",
        )
        groups = parse_idea_groups(default_group_text, base_groups=default_groups)
        group_rows = idea_group_counts(selected_records, groups)
        group_matrix = idea_group_document_matrix(selected_records, groups)
        network = build_cooccurrence_network(selected_records, extra_stopwords=extra_stopwords)
        knowledge_graph = build_knowledge_graph(selected_records, extra_stopwords=extra_stopwords)
        adaptive_groups = adaptive_topic_groups_from_graph(knowledge_graph)
        coverage = count_rows(selected_records, ["year", "analysis_language", "localization", "source_type"])
        sentiment_rows = sentiment_document_rows(selected_records)
        sentiment_summary = sentiment_by_year_source(sentiment_rows)
        structural_rows = extract_structural_propositions(selected_records)
        structural_summary_rows = structural_summary(structural_rows)
        structural_graph = build_structural_influence_graph(structural_rows)
        custody_rows = technical_traceability_rows(selected_records)
        sdn = smart_data_nucleus(selected_records)
        sentiment_by_url = {row.get("url"): row for row in sentiment_rows}
        enriched_records = []
        for row in selected_records:
            copy = dict(row)
            sentiment = sentiment_by_url.get(row.get("url"), {})
            for key, value in sentiment.items():
                if key not in {"year", "source_type", "medium", "title", "url"}:
                    copy[key] = value
            enriched_records.append(copy)
        unified_analysis = {
            "metadata": {
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "records": len(selected_records),
                "source_types": sorted({row_source_type(row) for row in selected_records}),
                "years": sorted({int(row.get("year")) for row in selected_records if row.get("year")}),
                "note": "Análisis local; sentimiento léxico exploratorio; redes ponderadas por conteos normalizados.",
                "structural_note": "Disección estructural local con heurísticas; no sustituye validación humana ni evaluación legal.",
            },
            "records": enriched_records,
            "coverage": coverage,
            "sentiment_by_document": sentiment_rows,
            "sentiment_by_year_source": sentiment_summary,
            "structural_propositions": structural_rows,
            "structural_summary": structural_summary_rows,
            "smart_data_nucleus": sdn,
            "structural_graph": structural_graph,
            "technical_traceability": custody_rows,
            "narrative_events": event_rows,
            "narrative_event_summary": event_summary,
            "actors": actors,
            "idea_groups": group_rows,
            "idea_group_document_matrix": group_matrix,
            "adaptive_topic_groups": adaptive_groups,
            "knowledge_graph": knowledge_graph,
            "semantic_network": network,
            "narrative_graph": narrative_graph,
            "weighted_node_cover": narrative_cover,
        }
        st.markdown("JSON único del análisis")
        st.caption("Este archivo fusiona registros filtrados, sentimiento, eventos, redes, grupos y cubridor para análisis posterior.")
        st.download_button(
            "Descargar JSON único enriquecido",
            json.dumps(unified_analysis, ensure_ascii=False, indent=2).encode("utf-8"),
            "narrative_analysis_unified.json",
            "application/json",
        )
        if st.button("Guardar JSON único en carpeta local"):
            save_base = Path(analysis_path)
            save_dir = save_base if save_base.suffix == "" else save_base.parent
            save_dir.mkdir(parents=True, exist_ok=True)
            save_path = save_dir / "narrative_analysis_unified.json"
            save_path.write_text(json.dumps(unified_analysis, ensure_ascii=False, indent=2), encoding="utf-8")
            st.success(f"Guardado: {save_path}")
        st.download_button("Descargar monogramas CSV", rows_to_csv(terms), "narrative_monograms.csv", "text/csv")
        st.download_button("Descargar bigramas CSV", rows_to_csv(bigrams), "narrative_bigrams.csv", "text/csv")
        st.download_button("Descargar trigramas CSV", rows_to_csv(trigrams), "narrative_trigrams.csv", "text/csv")
        st.download_button("Descargar marcos CSV", rows_to_csv(frames), "narrative_frames.csv", "text/csv")
        st.download_button("Descargar sentimiento documentos CSV", rows_to_csv(sentiment_rows), "sentiment_documents.csv", "text/csv")
        st.download_button("Descargar sentimiento año-fuente CSV", rows_to_csv(sentiment_summary), "sentiment_by_year_source.csv", "text/csv")
        st.download_button("Descargar eventos narrativos CSV", rows_to_csv(event_rows), "narrative_events.csv", "text/csv")
        st.download_button("Descargar resumen eventos CSV", rows_to_csv(event_summary), "narrative_event_summary.csv", "text/csv")
        st.download_button("Descargar actores CSV", rows_to_csv(actors), "narrative_actors.csv", "text/csv")
        st.download_button("Descargar nodos red narrativa CSV", rows_to_csv(narrative_graph["nodes"]), "narrative_graph_nodes.csv", "text/csv")
        st.download_button("Descargar aristas red narrativa CSV", rows_to_csv(narrative_graph["edges"]), "narrative_graph_edges.csv", "text/csv")
        st.download_button("Descargar cubridor ponderado CSV", rows_to_csv(narrative_cover["selected_nodes"]), "weighted_node_cover.csv", "text/csv")
        st.download_button("Descargar frente Pareto CSV", rows_to_csv(narrative_cover.get("pareto_front", [])), "weighted_node_cover_pareto.csv", "text/csv")
        st.download_button("Descargar grupos de ideas CSV", rows_to_csv(group_rows), "idea_groups.csv", "text/csv")
        st.download_button("Descargar matriz documento-grupo CSV", rows_to_csv(group_matrix), "idea_group_document_matrix.csv", "text/csv")
        st.download_button("Descargar grupos adaptativos CSV", rows_to_csv(adaptive_groups), "adaptive_topic_groups.csv", "text/csv")
        st.download_button("Descargar nodos grafo conocimiento CSV", rows_to_csv(knowledge_graph["nodes"]), "knowledge_graph_nodes.csv", "text/csv")
        st.download_button("Descargar aristas grafo conocimiento CSV", rows_to_csv(knowledge_graph["edges"]), "knowledge_graph_edges.csv", "text/csv")
        st.download_button("Descargar cobertura CSV", rows_to_csv(coverage), "corpus_coverage.csv", "text/csv")
        st.download_button("Descargar nodos de red CSV", rows_to_csv(network["nodes"]), "semantic_network_nodes.csv", "text/csv")
        st.download_button("Descargar aristas de red CSV", rows_to_csv(network["edges"]), "semantic_network_edges.csv", "text/csv")


init_state()
drain_queue()

st.title("SIAN · Smart Data Narrativo")
st.caption(
    "Sistema local para recolectar fuentes públicas, balancear capas discursivas y diseccionar narrativas "
    "mediante grafos, Smart Data, proposiciones, marcos, deltas, silencios y trazabilidad técnica."
)

GEOGRAPHIC_PRESETS = {
    "Global / sin límite regional": [],
    "México": ["Mexico", "México", "Mexican", "mexicano", "mexicana"],
    "América Latina": ["Latin America", "América Latina", "Latinoamérica", "Latin American", "latinoamericano", "latinoamericana"],
    "Iberoamérica": ["Iberoamérica", "Iberoamerica", "Spain", "España", "Latin America", "América Latina"],
    "Personalizado": [],
}

SOURCE_PRESETS = {
    "Sin limitar fuentes": [],
    "Artículos abiertos / repositorios académicos": [
        "pubmed.ncbi.nlm.nih.gov",
        "pmc.ncbi.nlm.nih.gov",
        "arxiv.org",
        "scielo.org",
        "redalyc.org",
        "dialnet.unirioja.es",
        "doaj.org",
        "zenodo.org",
        "osf.io",
        "hal.science",
        "repositorio.unam.mx",
        "zaloamati.azc.uam.mx",
        "ri.ibero.mx",
        "frontiersin.org",
        "mdpi.com",
        "plos.org",
        "biomedcentral.com",
    ],
    "Editoriales académicas cerradas / sólo rastreo bibliográfico": [
        "sciencedirect.com",
        "dl.acm.org",
        "ieeexplore.ieee.org",
        "springer.com",
        "link.springer.com",
        "tandfonline.com",
        "wiley.com",
        "sagepub.com",
        "nature.com",
        "science.org",
        "doi.org",
    ],
    "Reportes industriales / encuestas": [
        "survey.stackoverflow.co",
        "stackoverflow.blog",
        "github.blog",
        "octoverse.github.com",
        "mckinsey.com",
        "gartner.com",
        "forrester.com",
        "idc.com",
    ],
    "Noticias tecnológicas globales": [
        *profile_domains(countries=["US", "GB"]),
        "theguardian.com",
        "businessinsider.com",
        "wired.com",
        "technologyreview.com",
        "theverge.com",
        "zdnet.com",
        "techcrunch.com",
        "theregister.com",
        "arstechnica.com",
    ],
    "Noticias México": [
        *profile_domains(countries=["MX"]),
        "expansion.mx",
        "forbes.com.mx",
        "eleconomista.com.mx",
        "elfinanciero.com.mx",
    ],
    "Noticias América Latina": [
        *profile_domains(regions=["Latin America"]),
        "lanacion.com.ar",
        "clarin.com",
        "elespectador.com",
        "latercera.com",
        "emol.com",
        "elcomercio.pe",
        "larepublica.pe",
        "bbc.com",
    ],
    "Noticias mundo / diarios internacionales": [
        *profile_domains(countries=["US", "GB", "ES", "FR", "DE", "QA", "BR"]),
        "nytimes.com",
        "washingtonpost.com",
        "ft.com",
        "theconversation.com",
        "economist.com",
        "time.com",
        "newyorker.com",
    ],
    "Noticias Europa / global multilingüe": [
        *profile_domains(regions=["Europe"]),
        "theguardian.com",
        "bbc.com",
        "dw.com",
        "france24.com",
        "lemonde.fr",
        "elpais.com",
    ],
    "Noticias Estados Unidos / Reino Unido": [
        *profile_domains(countries=["US", "GB"]),
    ],
    "Noticias Brasil / portugués": [
        *profile_domains(countries=["BR"]),
    ],
    "Gobierno México / instituciones públicas": [
        *profile_domains(countries=["MX"], source_types=["institutional_report"]),
    ],
    "Gobierno global / organismos internacionales": [
        *profile_domains(regions=["Global", "Latin America"], source_types=["institutional_report"]),
    ],
    "Foros / práctica profesional": [
        "github.com",
        "medium.com",
        "substack.com",
        "wordpress.com",
        "blogspot.com",
        "tumblr.com",
        "stackexchange.com",
        "stackoverflow.com",
        "news.ycombinator.com",
        "dev.to",
        "reddit.com",
        "old.reddit.com",
    ],
    "Foros sobre tatuajes": [
        "medium.com",
        "substack.com",
        "wordpress.com",
        "blogspot.com",
        "tumblr.com",
        "tattoo.com",
        "tattooing101.com",
        "tattoodo.com",
        "inkppl.com",
        "tattooers.net",
        "quora.com",
        "reddit.com",
        "old.reddit.com",
    ],
}

SOURCE_MODE_LABELS = {
    "Noticias web / GDELT": "gdelt_news",
    "Noticias web / Google News RSS": "google_news_rss",
    "Artículos abiertos / OpenAlex OA": "openalex_oa",
    "Índice DOI / Crossref (metadatos + links)": "crossref",
    "Artículos abiertos latinoamericanos / Redalyc": "redalyc",
    "Foros y Reddit públicos / GDELT por dominio": "forums",
    "Reddit público / RSS de publicaciones": "reddit_rss",
    "Gobierno e instituciones públicas / GDELT": "institutional_gdelt",
}

EXCLUSION_PRESETS = {
    "Sin exclusiones": {"terms": [], "domains": []},
    "Tatuaje corporal: excluir cigarros/marca": {
        "terms": [
            "cigar",
            "cigars",
            "cigarro",
            "cigarros",
            "tobacco",
            "tabaco",
            "wrapper",
            "habano",
            "habanos",
            "cigar lounge",
            "smoke",
            "smoking",
            "nicaragua",
            "nicaraguan",
            "series p",
            "brown label",
            "robusto",
            "tatuaje cigars",
        ],
        "domains": [
            "halfwheel.com",
            "cigaraficionado.com",
            "thecigarauthority.com",
            "cigarjournal.com",
            "cigar-coop.com",
        ],
    },
    "Tatuaje corporal/social: excluir cigarros y usos médicos": {
        "terms": [
            "cigar",
            "cigars",
            "cigarro",
            "cigarros",
            "tobacco",
            "tabaco",
            "wrapper",
            "habano",
            "robusto",
            "tatuaje cigars",
            "colonoscopic tattooing",
            "colonoscopic",
            "endoscopic tattooing",
            "endoscopic",
            "colonoscopy",
            "polypectomy",
            "indocyanine green",
            "hepatitis",
            "antiviral",
            "HIV",
            "vaccine",
            "vaccines",
            "radiology",
            "melanocytic nevi",
            "keloid",
            "fibroblast",
            "dermatology treatment",
        ],
        "domains": [
            "halfwheel.com",
            "cigaraficionado.com",
            "thecigarauthority.com",
            "cigarjournal.com",
            "cigar-coop.com",
        ],
    },
    "IA/programación: excluir ruido financiero/cripto": {
        "terms": ["crypto token", "stock price", "earnings call", "trading", "bitcoin"],
        "domains": ["cointelegraph.com", "coindesk.com", "benzinga.com"],
    },
}


VARIANT_RUBRIC_PRESETS = {
    "Tatuaje / tattoo": {
        "núcleo": [
            "tatuaje",
            "tatuajes",
            "tattoo",
            "tattoos",
            "arte corporal",
            "body art",
            "tatuaje corporal",
        ],
        "oficio_industria": [
            "tatuador",
            "tatuadora",
            "tatuadores",
            "tattoo artist",
            "artista del tatuaje",
            "estudio de tatuajes",
            "tattoo studio",
        ],
        "sentido_identidad": [
            "significado de tatuaje",
            "significado de los tatuajes",
            "tatuaje identidad",
            "tatuaje memoria",
            "tatuaje pertenencia",
            "tatuaje duelo",
            "tatuaje simbólico",
            "tatuaje religioso",
        ],
        "sociedad_trabajo": [
            "tatuaje juventud",
            "tatuaje género",
            "tatuaje discriminación",
            "tatuaje empleo",
            "tatuaje violencia",
            "tatuaje feminista",
        ],
        "salud_regulacion": [
            "tatuaje salud",
            "tatuaje alergia",
            "tatuaje infección",
            "tintas para tatuaje",
            "regulación sanitaria tatuajes",
            "maquillaje permanente",
        ],
        "estetica_diseño": [
            "diseño de tatuaje",
            "diseños de tatuajes",
            "tinta corporal",
            "body ink",
            "tatuaje artístico",
            "tatuaje tradicional",
            "tatuaje mexicano",
            "tatuajes mexicanos",
            "tatuaje prehispánico",
            "tatuaje ritual",
        ],
    },
    "IA y programación": {
        "núcleo": ["AI coding assistant", "AI programming", "programación con IA", "asistente de programación"],
        "herramientas": ["GitHub Copilot", "ChatGPT coding", "Cursor AI", "pair programming AI"],
        "productividad": ["developer productivity", "productividad desarrolladores", "ahorro de tiempo programación"],
        "supervision": ["code review AI", "human supervision AI code", "revisión de código IA"],
        "riesgo_calidad": ["AI code bugs", "software security AI", "technical debt AI code"],
    },
}

CONNECTOR_ONLY_TERMS = {
    "a",
    "al",
    "and",
    "con",
    "contra",
    "de",
    "del",
    "e",
    "el",
    "en",
    "for",
    "la",
    "las",
    "lo",
    "los",
    "of",
    "o",
    "or",
    "para",
    "por",
    "the",
    "to",
    "vs",
    "y",
}


def default_variant_rubrics_for_query(query: str) -> dict[str, list[str]]:
    lowered = normalize_local(query)
    if "tatu" in lowered or "tattoo" in lowered:
        return VARIANT_RUBRIC_PRESETS["Tatuaje / tattoo"]
    if "ia" in lowered or "ai" in lowered or "program" in lowered or "copilot" in lowered:
        return VARIANT_RUBRIC_PRESETS["IA y programación"]
    return {"núcleo": [query.strip()] if query.strip() else []}


def variant_rubrics_to_text(rubrics: dict[str, list[str]]) -> str:
    lines = []
    for name, terms in rubrics.items():
        clean_terms = [term for term in terms if term.strip()]
        if clean_terms:
            lines.append(f"{name}: {', '.join(clean_terms)}")
    return "\n".join(lines)


def clean_search_term(value: str) -> str:
    value = " ".join(str(value or "").strip().split())
    if not value:
        return ""
    if normalize_local(value) in CONNECTOR_ONLY_TERMS:
        return ""
    return value


def parse_variant_rubrics(text: str, fallback_query: str) -> dict[str, list[str]]:
    rubrics: dict[str, list[str]] = {}
    current_name = "núcleo"
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if ":" in line:
            name, raw_terms = line.split(":", 1)
            current_name = normalize_local(name).replace(" ", "_") or "núcleo"
            chunks = raw_terms.split(",")
        else:
            chunks = line.split(",")
        terms = [clean_search_term(chunk) for chunk in chunks]
        terms = [term for term in terms if term]
        if terms:
            rubrics.setdefault(current_name, [])
            rubrics[current_name] = merge_unique([*rubrics[current_name], *terms])
    if not rubrics and fallback_query.strip():
        rubrics["núcleo"] = [fallback_query.strip()]
    return rubrics


def merge_unique(items: list[str]) -> list[str]:
    seen = set()
    output = []
    for item in items:
        value = item.strip()
        key = value.lower()
        if value and key not in seen:
            seen.add(key)
            output.append(value)
    return output


def normalize_local(value: str) -> str:
    table = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")
    value = (value or "").lower().translate(table)
    return " ".join(value.split())


def exclude_records_for_analysis(
    rows: list[dict],
    excluded_terms: list[str],
    excluded_media: list[str],
) -> tuple[list[dict], list[dict]]:
    excluded_term_keys = [normalize_local(term) for term in excluded_terms if term.strip()]
    excluded_media_keys = {normalize_local(medium) for medium in excluded_media if medium.strip()}
    kept = []
    removed = []
    for row in rows:
        medium_key = normalize_local(row.get("medium", ""))
        haystack = normalize_local(
            " ".join(
                [
                    str(row.get("medium", "")),
                    str(row.get("title", "")),
                    str(row.get("url", "")),
                    str(row.get("text_clean", ""))[:8000],
                    str(row.get("text_normalized", ""))[:8000],
                ]
            )
        )
        reason = ""
        if medium_key in excluded_media_keys:
            reason = f"excluded_medium:{row.get('medium', '')}"
        else:
            for term in excluded_term_keys:
                if term and term in haystack:
                    reason = f"excluded_term:{term}"
                    break
        if reason:
            copy = dict(row)
            copy["exclusion_reason"] = reason
            removed.append(copy)
        else:
            kept.append(row)
    return kept, removed


def split_terms(text: str) -> list[str]:
    return [
        item.strip()
        for chunk in (text or "").splitlines()
        for item in chunk.split(",")
        if item.strip()
    ]


def topical_relevance_score(row: dict, terms: list[str]) -> int:
    normalized_terms = [normalize_local(term) for term in terms if term.strip()]
    if not normalized_terms:
        return 0
    title = normalize_local(row.get("title", ""))
    text = normalize_local(row.get("text_clean", "") or row.get("text_normalized", ""))
    score = 0
    for term in normalized_terms:
        if not term:
            continue
        if term in title:
            score += 3
        score += min(5, text.count(term))
    return score


def filter_by_topical_relevance(
    rows: list[dict],
    terms: list[str],
    minimum_score: int,
) -> tuple[list[dict], list[dict]]:
    if not terms or minimum_score <= 0:
        return rows, []
    kept = []
    removed = []
    for row in rows:
        score = topical_relevance_score(row, terms)
        copy = dict(row)
        copy["topical_relevance_score"] = score
        if score >= minimum_score:
            kept.append(copy)
        else:
            copy["exclusion_reason"] = f"low_topical_relevance:{score}"
            removed.append(copy)
    return kept, removed


def mixed_sort_key(value) -> tuple[int, int | str]:
    text = str(value)
    if text.isdigit():
        return (0, int(text))
    return (1, text.lower())


def corpus_audit_rows(rows: list[dict]) -> list[dict]:
    status_counts = Counter(row.get("status", "unknown") for row in rows)
    type_counts = Counter(row_source_type(row) for row in rows)
    api_counts = Counter(row.get("source_api", "unknown") for row in rows)
    year_counts = Counter(row.get("year", "unknown") for row in rows)
    dedup_counts = Counter(row_document_dedup_key(row) for row in rows)
    duplicate_groups = sum(1 for key, value in dedup_counts.items() if key and value > 1)
    duplicate_extra_records = sum(value - 1 for key, value in dedup_counts.items() if key and value > 1)
    audit = [{"dimension": "total_records", "value": "all", "records": len(rows)}]
    audit.append({"dimension": "deduplication", "value": "duplicate_groups", "records": duplicate_groups})
    audit.append({"dimension": "deduplication", "value": "duplicate_extra_records", "records": duplicate_extra_records})
    audit.extend({"dimension": "status", "value": key, "records": value} for key, value in status_counts.most_common())
    audit.extend({"dimension": "source_type", "value": key, "records": value} for key, value in type_counts.most_common())
    audit.extend({"dimension": "source_api", "value": key, "records": value} for key, value in api_counts.most_common())
    audit.extend(
        {"dimension": "year", "value": key, "records": value}
        for key, value in sorted(year_counts.items(), key=lambda item: mixed_sort_key(item[0]))
    )
    return audit


def render_interactive_network(
    graph: dict,
    title: str,
    max_nodes: int = 80,
    min_edge_weight: float = 1.0,
    height: int = 620,
) -> None:
    nodes = sorted(
        graph.get("nodes", []),
        key=lambda node: float(node.get("score", node.get("weight", 0)) or 0),
        reverse=True,
    )[:max_nodes]
    node_ids = {node["id"] for node in nodes}
    edges = [
        edge for edge in graph.get("edges", [])
        if edge.get("source") in node_ids
        and edge.get("target") in node_ids
        and float(edge.get("weight", 1) or 1) >= min_edge_weight
    ]
    if not nodes or not edges:
        st.info("No hay suficientes nodos/aristas para dibujar la red con esos filtros.")
        return

    width = 980
    center_x = width / 2
    center_y = height / 2
    radius = min(width, height) * 0.38
    type_order = sorted({node.get("node_type", "unknown") for node in nodes})
    palette = {
        "document": "#6b7280",
        "actor": "#dc2626",
        "narrative_stage": "#2563eb",
        "source": "#16a34a",
        "year": "#9333ea",
        "localization": "#ea580c",
        "source_type": "#0891b2",
        "concept": "#7c3aed",
        "term": "#7c3aed",
        "monogram": "#7c3aed",
        "bigram": "#be185d",
        "trigram": "#f59e0b",
        "unknown": "#374151",
    }
    groups: dict[str, list[dict]] = {}
    for node in nodes:
        groups.setdefault(node.get("node_type", "unknown"), []).append(node)

    positioned = {}
    group_count = max(1, len(groups))
    for group_index, node_type in enumerate(type_order):
        group_nodes = groups.get(node_type, [])
        start_angle = (2 * math.pi * group_index / group_count) - math.pi / 2
        end_angle = (2 * math.pi * (group_index + 1) / group_count) - math.pi / 2
        span = max(0.01, end_angle - start_angle)
        for index, node in enumerate(group_nodes):
            angle = start_angle + span * ((index + 0.5) / max(1, len(group_nodes)))
            local_radius = radius * (0.65 + 0.35 * ((index % 3) / 2))
            positioned[node["id"]] = {
                **node,
                "x": center_x + local_radius * math.cos(angle),
                "y": center_y + local_radius * math.sin(angle),
            }

    max_score = max(float(node.get("score", node.get("weight", 1)) or 1) for node in nodes) or 1.0
    max_weight = max(float(edge.get("weight", 1) or 1) for edge in edges) or 1.0
    edge_svg = []
    for edge in edges:
        source = positioned[edge["source"]]
        target = positioned[edge["target"]]
        weight = float(edge.get("weight", 1) or 1)
        stroke_width = 0.8 + 4.2 * (weight / max_weight)
        edge_title = html_lib.escape(
            f"{source.get('label', edge['source'])} — {target.get('label', edge['target'])} | {edge.get('edge_type', '')} | weight={weight}"
        )
        edge_svg.append(
            f"""
            <line x1="{source['x']:.1f}" y1="{source['y']:.1f}" x2="{target['x']:.1f}" y2="{target['y']:.1f}"
                  stroke="#94a3b8" stroke-width="{stroke_width:.2f}" opacity="0.38">
              <title>{edge_title}</title>
            </line>
            """
        )
    node_svg = []
    label_svg = []
    for node_id, node in positioned.items():
        score = float(node.get("score", node.get("weight", 1)) or 1)
        size = 5 + 17 * math.sqrt(score / max_score)
        node_type = node.get("node_type", "unknown")
        color = palette.get(node_type, palette["unknown"])
        label = str(node.get("label", node_id))
        title_text = html_lib.escape(
            f"{label} | type={node_type} | score={score:.3f} | degree={node.get('degree', '')} | weighted_degree={node.get('weighted_degree', '')}"
        )
        safe_label = html_lib.escape(label[:24] + ("…" if len(label) > 24 else ""))
        node_svg.append(
            f"""
            <circle cx="{node['x']:.1f}" cy="{node['y']:.1f}" r="{size:.1f}"
                    fill="{color}" stroke="#111827" stroke-width="0.8" opacity="0.88">
              <title>{title_text}</title>
            </circle>
            """
        )
        if size >= 9:
            label_svg.append(
                f"""
                <text x="{node['x'] + size + 2:.1f}" y="{node['y'] + 4:.1f}"
                      font-size="10" fill="#111827">{safe_label}</text>
                """
            )
    legend_svg = []
    for index, node_type in enumerate(type_order):
        y = 24 + index * 20
        color = palette.get(node_type, palette["unknown"])
        legend_svg.append(
            f'<circle cx="18" cy="{y}" r="6" fill="{color}"></circle>'
            f'<text x="32" y="{y + 4}" font-size="12" fill="#111827">{html_lib.escape(str(node_type))}</text>'
        )
    safe_title = html_lib.escape(title)
    html = f"""
    <div style="font-family: Arial, sans-serif; border:1px solid #e5e7eb; border-radius:12px; padding:10px;">
      <div style="font-weight:700; margin: 4px 0 8px 4px;">{safe_title}</div>
      <svg viewBox="0 0 {width} {height}" width="100%" height="{height}" role="img">
        <rect width="{width}" height="{height}" fill="#ffffff"></rect>
        <g>{''.join(edge_svg)}</g>
        <g>{''.join(node_svg)}</g>
        <g>{''.join(label_svg)}</g>
        <g transform="translate(8,8)">
          <rect x="0" y="0" width="190" height="{32 + 20 * len(type_order)}" rx="8" fill="#f8fafc" stroke="#e2e8f0"></rect>
          {''.join(legend_svg)}
        </g>
      </svg>
      <div style="font-size:12px;color:#475569;padding:4px;">
        Nodos visibles: {len(nodes)} · Aristas visibles: {len(edges)} · Tamaño = score · Grosor = peso de arista.
        Pasa el cursor sobre nodos/aristas para ver detalles.
      </div>
    </div>
    """
    components.html(html, height=height + 78, scrolling=True)


def cover_comparison_rows(covers: list[dict]) -> list[dict]:
    rows = []
    for item in covers:
        stats = item.get("stats", {})
        front = item.get("pareto_front", []) or []
        rows.append(
            {
                "method": stats.get("method"),
                "edge_semantics": stats.get("coverage_mode"),
                "objective": stats.get("objective"),
                "reported_solution": "best_normalized_sum_from_pareto_archive",
                "total_candidate_nodes": stats.get("total_candidate_nodes"),
                "candidate_edges": stats.get("candidate_edges"),
                "evaluation_budget": stats.get("evaluation_budget"),
                "evaluations_used": stats.get("evaluations_used"),
                "objective_function_calls": stats.get("objective_function_calls"),
                "feasible_evaluations": stats.get("feasible_evaluations"),
                "infeasible_evaluations": stats.get("infeasible_evaluations"),
                "representative_feasible": stats.get("representative_feasible"),
                "representative_constraint_violation": stats.get("representative_constraint_violation"),
                "selection_rule": stats.get("selection_rule"),
                "lp_anchor_status": stats.get("lp_anchor_status"),
                "lp_anchor_cache": stats.get("lp_anchor_cache"),
                "initialization": stats.get("initialization"),
                "lp_seed_status": stats.get("lp_seed_status"),
                "lp_seed_cache": stats.get("lp_seed_cache"),
                "lp_seed_count": stats.get("lp_seed_count"),
                "lp_seed_attempted_sources": stats.get("lp_seed_attempted_sources"),
                "lp_seed_sources": stats.get("lp_seed_sources"),
                "guide_policy": stats.get("guide_policy"),
                "guide_initial_solutions": stats.get("guide_initial_solutions"),
                "guide_final_solutions": stats.get("guide_final_solutions"),
                "guide_updates": stats.get("guide_updates"),
                "ideal_u1": stats.get("ideal_u1"),
                "ideal_u2": stats.get("ideal_u2"),
                "ideal_u3": stats.get("ideal_u3"),
                "nadir_u1": stats.get("nadir_u1"),
                "nadir_u2": stats.get("nadir_u2"),
                "nadir_u3": stats.get("nadir_u3"),
                "selected_nodes": stats.get("selected_nodes"),
                "nodes_ratio": stats.get("nodes_ratio"),
                "node_weight_ratio": stats.get("node_weight_ratio"),
                "removed_edge_weight_ratio": stats.get("removed_edge_weight_ratio"),
                "removed_edge_weight": stats.get("removed_edge_weight"),
                "preserved_weight_share": stats.get("preserved_weight_share"),
                "hypervolume": stats.get("hypervolume"),
                "pareto_solutions": stats.get("pareto_solutions"),
                "best_pareto_node_weight_ratio": max(
                    [float(row.get("maximize_node_weight_ratio", 0) or 0) for row in front] or [0]
                ),
                "min_pareto_removed_edge_ratio": min(
                    [float(row.get("minimize_removed_edge_weight_ratio", 1) or 1) for row in front] or [0]
                ),
                "objective_value": stats.get("objective_value"),
            }
        )
    return rows


def graph_node_lookup(graph: dict) -> dict[str, dict]:
    return {str(node.get("id")): node for node in graph.get("nodes", [])}


def split_node_ids(value: str | list[str]) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value or "").split("|") if part.strip()]


def selected_nodes_from_ids(graph: dict, node_ids: list[str]) -> list[dict]:
    lookup = graph_node_lookup(graph)
    rows = []
    for node_id in node_ids:
        node = lookup.get(node_id, {})
        rows.append(
            {
                "id": node_id,
                "label": node.get("label", node_id),
                "type": node.get("type", ""),
                "score": node.get("score", ""),
                "degree": node.get("degree", ""),
                "weighted_degree": node.get("weighted_degree", ""),
                "community": node.get("community", ""),
            }
        )
    return rows


def combined_pareto_rows(covers: list[dict], graph: dict) -> list[dict]:
    lookup = graph_node_lookup(graph)
    rows = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for cover in covers:
        stats = cover.get("stats", {})
        method = stats.get("method", "")
        method_hv = stats.get("hypervolume", 0)
        for row in cover.get("pareto_front", []) or []:
            node_ids = split_node_ids(row.get("node_ids", ""))
            key = (str(method), tuple(sorted(node_ids)))
            if not node_ids or key in seen:
                continue
            seen.add(key)
            node_labels = [str(lookup.get(node_id, {}).get("label", node_id)) for node_id in node_ids]
            node_ratio = float(row.get("minimize_nodes_ratio", 0) or 0)
            node_weight_ratio = float(row.get("maximize_node_weight_ratio", 0) or 0)
            removed_ratio = float(row.get("minimize_removed_edge_weight_ratio", 0) or 0)
            compactness = max(0.0, min(1.0, 1.0 - node_ratio))
            edge_preservation = max(0.0, min(1.0, 1.0 - removed_ratio))
            compromise_score = node_weight_ratio / (node_ratio + removed_ratio + 1e-9)
            rows.append(
                {
                    "method": method,
                    "pareto_rank": row.get("pareto_rank"),
                    "solution_size": int(row.get("solution_size", len(node_ids)) or len(node_ids)),
                    "minimize_nodes_ratio": node_ratio,
                    "maximize_node_weight_ratio": node_weight_ratio,
                    "minimize_removed_edge_weight_ratio": removed_ratio,
                    "u1_compactness_1_minus_nodes": round(compactness, 5),
                    "u2_relevance_node_weight": round(node_weight_ratio, 5),
                    "u3_edge_preservation_1_minus_removed": round(edge_preservation, 5),
                    "normalized_sum": round(compactness + node_weight_ratio + edge_preservation, 5),
                    "feasible": row.get("feasible", True),
                    "constraint_violation": row.get("constraint_violation", 0),
                    "removed_edges": row.get("removed_edges", 0),
                    "removed_edge_weight": row.get("removed_edge_weight", 0),
                    "method_hypervolume": method_hv,
                    "evaluation_budget": stats.get("evaluation_budget"),
                    "evaluations_used": stats.get("evaluations_used"),
                    "compromise_score": round(compromise_score, 6),
                    "node_labels": " | ".join(node_labels),
                    "node_ids": " | ".join(node_ids),
                }
            )
    rows.sort(
        key=lambda row: (
            -float(row.get("compromise_score", 0) or 0),
            float(row.get("minimize_removed_edge_weight_ratio", 0) or 0),
            float(row.get("minimize_nodes_ratio", 0) or 0),
        )
    )
    return rows


def pareto_row_dominates(a: dict, b: dict) -> bool:
    a_feasible = bool(a.get("feasible", True))
    b_feasible = bool(b.get("feasible", True))
    if a_feasible and not b_feasible:
        return True
    if b_feasible and not a_feasible:
        return False
    if not a_feasible and not b_feasible:
        return float(a.get("constraint_violation", 1e9) or 1e9) < float(b.get("constraint_violation", 1e9) or 1e9)
    a_values = (
        float(a.get("u1_compactness_1_minus_nodes", 0) or 0),
        float(a.get("u2_relevance_node_weight", 0) or 0),
        float(a.get("u3_edge_preservation_1_minus_removed", 0) or 0),
    )
    b_values = (
        float(b.get("u1_compactness_1_minus_nodes", 0) or 0),
        float(b.get("u2_relevance_node_weight", 0) or 0),
        float(b.get("u3_edge_preservation_1_minus_removed", 0) or 0),
    )
    return all(a_values[index] >= b_values[index] for index in range(3)) and any(
        a_values[index] > b_values[index] for index in range(3)
    )


def annotate_global_pareto(rows: list[dict]) -> list[dict]:
    annotated = []
    for index, row in enumerate(rows):
        is_global = not any(
            pareto_row_dominates(other, row)
            for other_index, other in enumerate(rows)
            if other_index != index
        )
        annotated.append({**row, "global_pareto": is_global})
    annotated.sort(
        key=lambda row: (
            not bool(row.get("global_pareto")),
            -float(row.get("method_hypervolume", 0) or 0),
            -float(row.get("normalized_sum", 0) or 0),
        )
    )
    return annotated


def nondominated_rows(rows: list[dict]) -> list[dict]:
    """Return the nondominated subset of the supplied rows using the shared feasibility rule."""
    front = []
    for index, row in enumerate(rows):
        if any(
            pareto_row_dominates(other, row)
            for other_index, other in enumerate(rows)
            if other_index != index
        ):
            continue
        front.append(row)
    return front


def pareto_front_summary_rows(rows: list[dict]) -> list[dict]:
    by_method: dict[str, list[dict]] = {}
    feasible_rows = [row for row in rows if bool(row.get("feasible", True))]
    rows_for_summary = feasible_rows or rows
    for row in rows_for_summary:
        by_method.setdefault(str(row.get("method", "")), []).append(row)
    reference_rows = nondominated_rows(rows_for_summary) or rows_for_summary
    reference_vectors = [pareto_row_vector(row) for row in reference_rows]
    summaries = []
    for method, method_rows in sorted(by_method.items()):
        if not method_rows:
            continue
        method_front_rows = nondominated_rows(method_rows) or method_rows
        global_rows = [row for row in method_front_rows if row.get("global_pareto")]
        method_vectors = [pareto_row_vector(row) for row in method_front_rows]
        quality = pareto_quality_metrics(method_vectors, reference_vectors)
        budgets = sorted({row.get("evaluation_budget") for row in method_rows if row.get("evaluation_budget") is not None})
        used = sorted({row.get("evaluations_used") for row in method_rows if row.get("evaluations_used") is not None})
        summaries.append(
            {
                "method": method,
                "evaluation_budget": budgets[0] if len(budgets) == 1 else ",".join(str(item) for item in budgets),
                "evaluations_used": used[0] if len(used) == 1 else ",".join(str(item) for item in used),
                "front_points": len(method_front_rows),
                "generated_feasible_points": len(method_rows),
                "global_nondominated_points": len(global_rows),
                "method_hypervolume": max(float(row.get("method_hypervolume", 0) or 0) for row in method_rows),
                "igd_to_global_front": quality["igd"],
                "spacing_std": quality["spacing_std"],
                "dispersion_extent": quality["dispersion_extent"],
                "max_relevance_u2": round(max(float(row.get("u2_relevance_node_weight", 0) or 0) for row in method_rows), 5),
                "max_edge_preservation_u3": round(max(float(row.get("u3_edge_preservation_1_minus_removed", 0) or 0) for row in method_rows), 5),
                "max_compactness_u1": round(max(float(row.get("u1_compactness_1_minus_nodes", 0) or 0) for row in method_rows), 5),
                "mean_normalized_sum": round(
                    sum(float(row.get("normalized_sum", 0) or 0) for row in method_rows) / max(1, len(method_rows)),
                    5,
                ),
            }
        )
    return sorted(
        summaries,
        key=lambda row: (row["method_hypervolume"], -row["igd_to_global_front"], row["global_nondominated_points"], row["mean_normalized_sum"]),
        reverse=True,
    )


def pareto_row_vector(row: dict) -> tuple[float, float, float]:
    return (
        float(row.get("u1_compactness_1_minus_nodes", 0) or 0),
        float(row.get("u2_relevance_node_weight", 0) or 0),
        float(row.get("u3_edge_preservation_1_minus_removed", 0) or 0),
    )


def euclidean_distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return sum((a[i] - b[i]) ** 2 for i in range(3)) ** 0.5


def pareto_quality_metrics(
    method_vectors: list[tuple[float, float, float]],
    reference_vectors: list[tuple[float, float, float]],
) -> dict:
    if not method_vectors:
        return {"igd": 1.73205, "spacing_std": 0.0, "dispersion_extent": 0.0}
    if not reference_vectors:
        reference_vectors = method_vectors
    igd = sum(min(euclidean_distance(ref, point) for point in method_vectors) for ref in reference_vectors) / max(1, len(reference_vectors))
    nearest_distances = []
    for idx, point in enumerate(method_vectors):
        others = [other for j, other in enumerate(method_vectors) if j != idx]
        nearest_distances.append(min([euclidean_distance(point, other) for other in others] or [0.0]))
    mean_nearest = sum(nearest_distances) / max(1, len(nearest_distances))
    spacing_std = (
        sum((distance - mean_nearest) ** 2 for distance in nearest_distances) / max(1, len(nearest_distances))
    ) ** 0.5
    ranges = [
        max(point[i] for point in method_vectors) - min(point[i] for point in method_vectors)
        for i in range(3)
    ]
    dispersion_extent = sum(ranges) / 3
    return {
        "igd": round(igd, 5),
        "spacing_std": round(spacing_std, 5),
        "dispersion_extent": round(dispersion_extent, 5),
    }


def numeric_summary(values: list[float], *, decimals: int = 6) -> dict:
    clean = [float(value) for value in values if value is not None and not math.isnan(float(value))]
    if not clean:
        return {
            "n": 0,
            "mean": 0.0,
            "median": 0.0,
            "mode": 0.0,
            "minimum": 0.0,
            "maximum": 0.0,
            "variance": 0.0,
        }
    rounded = [round(value, decimals) for value in clean]
    modes = statistics.multimode(rounded)
    mode_value = modes[0] if modes else rounded[0]
    variance = statistics.variance(clean) if len(clean) > 1 else 0.0
    return {
        "n": len(clean),
        "mean": round(statistics.mean(clean), decimals),
        "median": round(statistics.median(clean), decimals),
        "mode": round(mode_value, decimals),
        "minimum": round(min(clean), decimals),
        "maximum": round(max(clean), decimals),
        "variance": round(variance, decimals),
    }


def bootstrap_mean_ci(
    values: list[float],
    *,
    confidence: float = 0.95,
    resamples: int = 1000,
    seed: int = 20260725,
    decimals: int = 6,
) -> tuple[float, float]:
    clean = [float(value) for value in values if value is not None and not math.isnan(float(value))]
    if not clean:
        return (0.0, 0.0)
    if len(clean) == 1:
        single = round(clean[0], decimals)
        return (single, single)
    rng = random.Random(seed)
    means = []
    for _ in range(max(100, int(resamples))):
        sample = [clean[rng.randrange(len(clean))] for _ in clean]
        means.append(sum(sample) / len(sample))
    means.sort()
    alpha = max(0.0, min(1.0, 1.0 - confidence))
    low_index = int((alpha / 2) * (len(means) - 1))
    high_index = int((1 - alpha / 2) * (len(means) - 1))
    return (round(means[low_index], decimals), round(means[high_index], decimals))


def wilcoxon_signed_rank(values_a: list[float], values_b: list[float]) -> dict:
    paired = [
        (float(a), float(b))
        for a, b in zip(values_a, values_b)
        if a is not None and b is not None and not math.isnan(float(a)) and not math.isnan(float(b))
    ]
    differences = [a - b for a, b in paired]
    nonzero = [diff for diff in differences if abs(diff) > 1e-12]
    if not paired:
        return {"n_pairs": 0, "median_difference": 0.0, "wilcoxon_statistic": 0.0, "p_value": 1.0, "status": "sin pares"}
    if not nonzero:
        return {
            "n_pairs": len(paired),
            "median_difference": 0.0,
            "wilcoxon_statistic": 0.0,
            "p_value": 1.0,
            "status": "sin diferencias",
        }
    try:
        from scipy.stats import wilcoxon  # type: ignore

        result = wilcoxon(values_a[: len(paired)], values_b[: len(paired)], zero_method="wilcox", alternative="two-sided")
        p_value = float(result.pvalue)
        statistic = float(result.statistic)
        status = "scipy"
    except Exception:
        abs_diffs = [(abs(diff), 1 if diff > 0 else -1) for diff in nonzero]
        sorted_diffs = sorted(enumerate(abs_diffs), key=lambda item: item[1][0])
        ranks = [0.0] * len(sorted_diffs)
        position = 0
        while position < len(sorted_diffs):
            next_position = position + 1
            while next_position < len(sorted_diffs) and abs(sorted_diffs[next_position][1][0] - sorted_diffs[position][1][0]) <= 1e-12:
                next_position += 1
            average_rank = (position + 1 + next_position) / 2
            for rank_position in range(position, next_position):
                original_index = sorted_diffs[rank_position][0]
                ranks[original_index] = average_rank
            position = next_position
        w_plus = sum(rank for rank, (_, sign) in zip(ranks, abs_diffs) if sign > 0)
        w_minus = sum(rank for rank, (_, sign) in zip(ranks, abs_diffs) if sign < 0)
        statistic = min(w_plus, w_minus)
        n = len(nonzero)
        mean_w = n * (n + 1) / 4
        var_w = n * (n + 1) * (2 * n + 1) / 24
        z = 0.0 if var_w <= 0 else (statistic - mean_w) / math.sqrt(var_w)
        p_value = math.erfc(abs(z) / math.sqrt(2))
        status = "aprox_normal_sin_scipy"
    return {
        "n_pairs": len(paired),
        "median_difference": round(statistics.median(differences), 6),
        "wilcoxon_statistic": round(statistic, 6),
        "p_value": round(p_value, 6),
        "status": status,
    }


def repeated_cover_quality_experiment(
    graph: dict,
    *,
    max_nodes: int,
    min_nodes: int,
    min_node_weight_share: float,
    max_removed_edge_weight_share: float,
    allowed_node_types: list[str],
    edge_types: list[str],
    first_seed: int,
    repetitions: int,
    evaluation_budget: int,
    edge_cost_weight: float,
    coverage_mode: str = "removal_impact",
) -> dict:
    runs = max(10, int(repetitions))
    all_front_rows: list[dict] = []
    raw_rows: list[dict] = []
    covers_by_run: dict[tuple[int, str], dict] = {}
    for run_index in range(runs):
        seed = int(first_seed) + run_index
        covers = run_all_cover_methods(
            graph,
            max_nodes=max_nodes,
            min_nodes=min_nodes,
            min_node_weight_share=min_node_weight_share,
            max_removed_edge_weight_share=max_removed_edge_weight_share,
            allowed_node_types=allowed_node_types,
            edge_types=edge_types,
            solver_seed=seed,
            population_or_iterations=evaluation_budget,
            edge_cost_weight=edge_cost_weight,
            coverage_mode=coverage_mode,
        )
        front_rows = combined_pareto_rows(covers, graph)
        for row in front_rows:
            enriched = {**row, "run": run_index + 1, "seed": seed}
            all_front_rows.append(enriched)
        for cover in covers:
            method = str(cover.get("stats", {}).get("method", ""))
            covers_by_run[(run_index + 1, method)] = cover
            raw_rows.append(
                {
                    "run": run_index + 1,
                    "seed": seed,
                    "method": method,
                    "objective_function_calls": cover.get("stats", {}).get("objective_function_calls"),
                    "evaluation_budget": cover.get("stats", {}).get("evaluation_budget"),
                    "feasible_evaluations": cover.get("stats", {}).get("feasible_evaluations"),
                    "infeasible_evaluations": cover.get("stats", {}).get("infeasible_evaluations"),
                }
            )
    feasible_front_rows = [row for row in all_front_rows if bool(row.get("feasible", True))]
    reference_rows = nondominated_rows(feasible_front_rows) or feasible_front_rows or all_front_rows
    reference_vectors = [pareto_row_vector(row) for row in reference_rows]
    methods = sorted({str(row.get("method", "")) for row in raw_rows if row.get("method")})
    run_metric_rows: list[dict] = []
    for run_index in range(1, runs + 1):
        for method in methods:
            method_rows = [
                row for row in all_front_rows
                if int(row.get("run", 0) or 0) == run_index
                and str(row.get("method", "")) == method
                and bool(row.get("feasible", True))
            ]
            method_front_rows = nondominated_rows(method_rows) or method_rows
            method_vectors = [pareto_row_vector(row) for row in method_front_rows]
            quality = pareto_quality_metrics(method_vectors, reference_vectors)
            cover = covers_by_run.get((run_index, method), {})
            stats = cover.get("stats", {})
            run_metric_rows.append(
                {
                    "run": run_index,
                    "seed": int(first_seed) + run_index - 1,
                    "method": method,
                    "front_points_nondominated_feasible": len(method_front_rows),
                    "reference_front_points": len(reference_rows),
                    "hypervolume": round(float(stats.get("hypervolume", 0) or 0), 6),
                    "igd_to_empirical_ideal_front": quality["igd"],
                    "dispersion_extent": quality["dispersion_extent"],
                    "spacing_std": quality["spacing_std"],
                    "objective_function_calls": stats.get("objective_function_calls"),
                    "evaluation_budget": stats.get("evaluation_budget"),
                    "over_budget": (
                        float(stats.get("objective_function_calls") or 0)
                        > float(stats.get("evaluation_budget") or evaluation_budget)
                    ),
                    "feasible_evaluations": stats.get("feasible_evaluations"),
                    "infeasible_evaluations": stats.get("infeasible_evaluations"),
                }
            )
    metric_specs = {
        "hypervolume": "mayor_es_mejor",
        "igd_to_empirical_ideal_front": "menor_es_mejor",
        "dispersion_extent": "mayor_es_diversidad",
        "spacing_std": "menor_es_mas_regular",
    }
    summary_rows: list[dict] = []
    values_by_method_metric: dict[tuple[str, str], list[float]] = {}
    for method in methods:
        method_run_rows = [row for row in run_metric_rows if row["method"] == method]
        for metric, interpretation in metric_specs.items():
            values = [float(row.get(metric, 0) or 0) for row in method_run_rows]
            values_by_method_metric[(method, metric)] = values
            low, high = bootstrap_mean_ci(values, seed=20260725 + len(method) + len(metric))
            summary_rows.append(
                {
                    "method": method,
                    "metric": metric,
                    "interpretation": interpretation,
                    **numeric_summary(values),
                    "bootstrap_ci95_low_mean": low,
                    "bootstrap_ci95_high_mean": high,
                }
            )
    wilcoxon_rows: list[dict] = []
    for metric, interpretation in metric_specs.items():
        for method_a, method_b in combinations(methods, 2):
            test = wilcoxon_signed_rank(
                values_by_method_metric.get((method_a, metric), []),
                values_by_method_metric.get((method_b, metric), []),
            )
            wilcoxon_rows.append(
                {
                    "metric": metric,
                    "interpretation": interpretation,
                    "method_a": method_a,
                    "method_b": method_b,
                    **test,
                }
            )
    return {
        "run_metric_rows": run_metric_rows,
        "summary_rows": summary_rows,
        "wilcoxon_rows": wilcoxon_rows,
        "reference_rows": reference_rows,
        "all_front_rows": all_front_rows,
    }


def render_repeated_cover_quality_results(results: dict) -> None:
    run_metric_rows = results.get("run_metric_rows", [])
    summary_rows = results.get("summary_rows", [])
    wilcoxon_rows = results.get("wilcoxon_rows", [])
    reference_rows = results.get("reference_rows", [])
    st.markdown("Resultados estadísticos por método")
    st.caption(
        "Cada métrica se calcula sólo sobre el frente factible no dominado de cada método en cada corrida. "
        "IGD usa como referencia el frente empírico ideal: unión no dominada de todos los métodos y corridas. "
        "El hipervolumen se aproxima como volumen dominado por el frente no dominado factible de cada método."
    )
    st.metric("Puntos del frente empírico ideal", len(reference_rows))

    methods = sorted({str(row.get("method", "")) for row in run_metric_rows if row.get("method")})
    summary_by_method_metric = {
        (str(row.get("method", "")), str(row.get("metric", ""))): row
        for row in summary_rows
    }
    compact_rows = []
    budget_rows = []
    for method in methods:
        method_runs = [row for row in run_metric_rows if str(row.get("method", "")) == method]
        calls = [float(row.get("objective_function_calls") or 0) for row in method_runs]
        budgets = [float(row.get("evaluation_budget") or 0) for row in method_runs]
        feasible = [float(row.get("feasible_evaluations") or 0) for row in method_runs]
        infeasible = [float(row.get("infeasible_evaluations") or 0) for row in method_runs]
        compact_rows.append(
            {
                "method": method,
                "runs": len(method_runs),
                "mean_hypervolume": summary_by_method_metric.get((method, "hypervolume"), {}).get("mean", 0),
                "median_hypervolume": summary_by_method_metric.get((method, "hypervolume"), {}).get("median", 0),
                "mean_igd_lower_better": summary_by_method_metric.get((method, "igd_to_empirical_ideal_front"), {}).get("mean", 0),
                "mean_dispersion": summary_by_method_metric.get((method, "dispersion_extent"), {}).get("mean", 0),
                "mean_spacing_lower_better": summary_by_method_metric.get((method, "spacing_std"), {}).get("mean", 0),
                "hv_ci95": (
                    f"{summary_by_method_metric.get((method, 'hypervolume'), {}).get('bootstrap_ci95_low_mean', 0)}–"
                    f"{summary_by_method_metric.get((method, 'hypervolume'), {}).get('bootstrap_ci95_high_mean', 0)}"
                ),
            }
        )
        over_budget_runs = sum(
            1
            for row in method_runs
            if float(row.get("objective_function_calls") or 0) > float(row.get("evaluation_budget") or 0)
        )
        budget_rows.append(
            {
                "method": method,
                "runs": len(method_runs),
                "evaluation_budget": int(max(budgets) if budgets else 0),
                "mean_objective_calls": round(statistics.mean(calls), 3) if calls else 0,
                "max_objective_calls": int(max(calls) if calls else 0),
                "over_budget_runs": over_budget_runs,
                "mean_feasible_evaluations": round(statistics.mean(feasible), 3) if feasible else 0,
                "mean_infeasible_evaluations": round(statistics.mean(infeasible), 3) if infeasible else 0,
                "budget_status": "ERROR_exceeds_budget" if over_budget_runs else "ok_same_budget",
            }
        )

    st.markdown("Promedios principales de las corridas")
    st.caption("Una fila por método. Aquí debe verse el promedio de las 10 o n corridas.")
    st.dataframe(compact_rows, use_container_width=True)

    st.markdown("Auditoría de presupuesto de evaluaciones")
    st.caption("Si `over_budget_runs` es mayor que 0, ese método no es comparable y hay que corregirlo antes de interpretar.")
    st.dataframe(budget_rows, use_container_width=True)
    if any(int(row.get("over_budget_runs", 0) or 0) > 0 for row in budget_rows):
        st.error("Hay métodos que excedieron el presupuesto de evaluaciones. No interpretes la comparación hasta corregirlo.")

    st.markdown("Resumen estadístico completo")
    st.dataframe(summary_rows, use_container_width=True)
    st.markdown("Distribución por corrida")
    st.vega_lite_chart(
        run_metric_rows,
        {
            "transform": [
                {
                    "fold": [
                        "hypervolume",
                        "igd_to_empirical_ideal_front",
                        "dispersion_extent",
                        "spacing_std",
                    ],
                    "as": ["metric", "value"],
                }
            ],
            "mark": {"type": "boxplot", "extent": "min-max", "tooltip": True},
            "encoding": {
                "x": {"field": "method", "type": "nominal", "title": "Método"},
                "y": {"field": "value", "type": "quantitative", "title": "Valor"},
                "color": {"field": "method", "type": "nominal"},
                "facet": {"field": "metric", "type": "nominal", "columns": 2},
            },
            "resolve": {"scale": {"y": "independent"}},
        },
        use_container_width=True,
    )
    st.markdown("Pruebas pareadas de Wilcoxon")
    st.caption(
        "La prueba usa las mismas semillas por corrida para comparar métodos de forma pareada. "
        "Si todas las diferencias son cero, se reporta p=1 porque no hay evidencia estadística de diferencia."
    )
    st.dataframe(wilcoxon_rows, use_container_width=True)
    st.markdown("Métricas por corrida")
    st.dataframe(run_metric_rows, use_container_width=True)
    c1, c2, c3 = st.columns(3)
    c1.download_button(
        "Descargar resumen estadístico CSV",
        rows_to_csv(summary_rows),
        "cover_methods_repeated_summary.csv",
        "text/csv",
    )
    c2.download_button(
        "Descargar Wilcoxon CSV",
        rows_to_csv(wilcoxon_rows),
        "cover_methods_wilcoxon.csv",
        "text/csv",
    )
    c3.download_button(
        "Descargar métricas por corrida CSV",
        rows_to_csv(run_metric_rows),
        "cover_methods_run_metrics.csv",
        "text/csv",
    )


def render_pareto_3d_diagnostics(rows: list[dict], title_prefix: str) -> None:
    if not rows:
        st.warning("No hay puntos Pareto para comparar.")
        return
    annotated_rows = annotate_global_pareto(rows)
    st.markdown(f"{title_prefix}: comparación 3D normalizada de frentes")
    st.caption(
        "El modelo tiene tres utilidades normalizadas que se maximizan: "
        "u1=1−nodos/total, u2=peso nodal/total, u3=1−aristas removidas/total. "
        "Todos los métodos se comparan bajo el mismo grafo, restricciones, criterio de factibilidad y presupuesto de evaluaciones. "
        "Las métricas comunes se calculan sobre frentes factibles no dominados: hipervolumen, puntos globalmente no dominados, "
        "IGD contra el frente empírico ideal, spacing y dispersión."
    )
    st.dataframe(pareto_front_summary_rows(annotated_rows), use_container_width=True)
    st.dataframe(annotated_rows, use_container_width=True)

    surface_rows = pareto_surface_rows(annotated_rows, bin_size=0.05)
    if surface_rows:
        st.markdown("Superficie empírica del frente: u1 × u3 → u2")
        st.caption(
            "Cada celda agrupa soluciones cercanas en compacidad u1 y preservación estructural u3; "
            "el color muestra la mejor relevancia u2 encontrada. Esto evita vender como 3D real una proyección 2D plana."
        )
        st.vega_lite_chart(
            surface_rows,
            {
                "mark": {"type": "rect", "tooltip": True},
                "encoding": {
                    "x": {
                        "field": "u1_bin",
                        "type": "ordinal",
                        "title": "u1 compacidad bin",
                        "sort": "ascending",
                    },
                    "y": {
                        "field": "u3_bin",
                        "type": "ordinal",
                        "title": "u3 preservación bin",
                        "sort": "descending",
                    },
                    "color": {
                        "field": "best_u2_relevance",
                        "type": "quantitative",
                        "title": "mejor u2 relevancia",
                        "scale": {"scheme": "viridis", "domain": [0, 1]},
                    },
                    "facet": {"field": "method", "type": "nominal", "columns": 2},
                    "tooltip": [
                        {"field": "method", "type": "nominal"},
                        {"field": "u1_bin", "type": "nominal"},
                        {"field": "u3_bin", "type": "nominal"},
                        {"field": "best_u2_relevance", "type": "quantitative"},
                        {"field": "points", "type": "quantitative"},
                        {"field": "best_solution_size", "type": "quantitative"},
                        {"field": "best_node_labels", "type": "nominal"},
                    ],
                },
                "resolve": {"scale": {"x": "shared", "y": "shared", "color": "shared"}},
            },
            use_container_width=True,
        )

    projection_specs = [
        (
            "u3_edge_preservation_1_minus_removed",
            "u2_relevance_node_weight",
            "Proyección u3 preservación de aristas × u2 relevancia",
        ),
        (
            "u1_compactness_1_minus_nodes",
            "u2_relevance_node_weight",
            "Proyección u1 compacidad × u2 relevancia",
        ),
        (
            "u1_compactness_1_minus_nodes",
            "u3_edge_preservation_1_minus_removed",
            "Proyección u1 compacidad × u3 preservación",
        ),
    ]
    for x_field, y_field, chart_title in projection_specs:
        st.vega_lite_chart(
            annotated_rows,
            {
                "title": chart_title,
                "mark": {"type": "circle", "tooltip": True, "size": 95},
                "encoding": {
                    "x": {"field": x_field, "type": "quantitative", "scale": {"domain": [0, 1]}},
                    "y": {"field": y_field, "type": "quantitative", "scale": {"domain": [0, 1]}},
                    "color": {"field": "method", "type": "nominal"},
                    "shape": {"field": "global_pareto", "type": "nominal", "title": "Global Pareto"},
                    "size": {"field": "solution_size", "type": "quantitative", "title": "Nodos"},
                    "tooltip": [
                        {"field": "method", "type": "nominal"},
                        {"field": "global_pareto", "type": "nominal"},
                        {"field": "solution_size", "type": "quantitative"},
                        {"field": "u1_compactness_1_minus_nodes", "type": "quantitative"},
                        {"field": "u2_relevance_node_weight", "type": "quantitative"},
                        {"field": "u3_edge_preservation_1_minus_removed", "type": "quantitative"},
                        {"field": "node_labels", "type": "nominal"},
                    ],
                },
            },
            use_container_width=True,
        )

    st.markdown("Coordenadas paralelas de los tres objetivos")
    st.vega_lite_chart(
        annotated_rows,
        {
            "transform": [
                {
                    "fold": [
                        "u1_compactness_1_minus_nodes",
                        "u2_relevance_node_weight",
                        "u3_edge_preservation_1_minus_removed",
                    ],
                    "as": ["objective", "utility"],
                }
            ],
            "mark": {"type": "line", "point": True, "tooltip": True},
            "encoding": {
                "x": {"field": "objective", "type": "nominal", "title": "Objetivo normalizado"},
                "y": {"field": "utility", "type": "quantitative", "scale": {"domain": [0, 1]}, "title": "Utilidad"},
                "color": {"field": "method", "type": "nominal"},
                "detail": {"field": "node_ids", "type": "nominal"},
                "opacity": {"condition": {"test": "datum.global_pareto == true", "value": 0.95}, "value": 0.28},
                "tooltip": [
                    {"field": "method", "type": "nominal"},
                    {"field": "global_pareto", "type": "nominal"},
                    {"field": "solution_size", "type": "quantitative"},
                    {"field": "objective", "type": "nominal"},
                    {"field": "utility", "type": "quantitative"},
                    {"field": "node_labels", "type": "nominal"},
                ],
            },
        },
        use_container_width=True,
    )


def pareto_surface_rows(rows: list[dict], bin_size: float = 0.05) -> list[dict]:
    cells: dict[tuple[str, float, float], dict] = {}
    safe_bin = max(0.01, float(bin_size or 0.05))
    for row in rows:
        method = str(row.get("method") or "unknown")
        u1 = float(row.get("u1_compactness_1_minus_nodes", 0) or 0)
        u2 = float(row.get("u2_relevance_node_weight", 0) or 0)
        u3 = float(row.get("u3_edge_preservation_1_minus_removed", 0) or 0)
        u1_bin = round(round(u1 / safe_bin) * safe_bin, 2)
        u3_bin = round(round(u3 / safe_bin) * safe_bin, 2)
        key = (method, u1_bin, u3_bin)
        current = cells.get(key)
        if current is None or u2 > current["best_u2_relevance"]:
            cells[key] = {
                "method": method,
                "u1_bin": f"{u1_bin:.2f}",
                "u3_bin": f"{u3_bin:.2f}",
                "best_u2_relevance": round(u2, 5),
                "best_solution_size": row.get("solution_size"),
                "best_node_labels": row.get("node_labels"),
                "points": int((current or {}).get("points", 0)) + 1,
            }
        else:
            current["points"] = int(current.get("points", 0)) + 1
    return sorted(cells.values(), key=lambda item: (item["method"], item["u1_bin"], item["u3_bin"]))


def filter_pareto_rows(
    rows: list[dict],
    min_solution_size: int,
    min_node_weight_ratio: float,
    max_removed_edge_ratio: float,
) -> list[dict]:
    return [
        row for row in rows
        if int(row.get("solution_size", 0) or 0) >= int(min_solution_size)
        and float(row.get("maximize_node_weight_ratio", 0) or 0) >= float(min_node_weight_ratio)
        and float(row.get("minimize_removed_edge_weight_ratio", 1) or 1) <= float(max_removed_edge_ratio)
    ]


def run_all_cover_methods(
    narrative_graph: dict,
    max_nodes: int,
    min_nodes: int,
    min_node_weight_share: float,
    max_removed_edge_weight_share: float,
    allowed_node_types: list[str],
    edge_types: list[str],
    solver_seed: int,
    population_or_iterations: int,
    edge_cost_weight: float,
    cover_objective: str = "maximize_node_minimize_edge",
    coverage_mode: str = "removal_impact",
) -> list[dict]:
    evaluation_budget = int(population_or_iterations)
    return [
        weighted_sum_greedy_sweep_node_cover(
            narrative_graph,
            max_nodes=max_nodes,
            allowed_node_types=allowed_node_types,
            edge_types=edge_types,
            coverage_mode=coverage_mode,
            evaluation_budget=evaluation_budget,
            seed=int(solver_seed),
            min_nodes=min_nodes,
            min_node_weight_share=min_node_weight_share,
            max_removed_edge_weight_share=max_removed_edge_weight_share,
        ),
        moea_weighted_node_cover(
            narrative_graph,
            max_nodes=max_nodes,
            allowed_node_types=allowed_node_types,
            edge_types=edge_types,
            evaluation_budget=evaluation_budget,
            seed=int(solver_seed),
            coverage_mode=coverage_mode,
            min_nodes=min_nodes,
            min_node_weight_share=min_node_weight_share,
            max_removed_edge_weight_share=max_removed_edge_weight_share,
        ),
        mosa_weighted_node_cover(
            narrative_graph,
            max_nodes=max_nodes,
            allowed_node_types=allowed_node_types,
            edge_types=edge_types,
            evaluation_budget=evaluation_budget,
            seed=int(solver_seed),
            coverage_mode=coverage_mode,
            min_nodes=min_nodes,
            min_node_weight_share=min_node_weight_share,
            max_removed_edge_weight_share=max_removed_edge_weight_share,
        ),
        mmc_multiobjective_weighted_node_cover(
            narrative_graph,
            max_nodes=max_nodes,
            allowed_node_types=allowed_node_types,
            edge_types=edge_types,
            evaluation_budget=evaluation_budget,
            seed=int(solver_seed),
            coverage_mode=coverage_mode,
            min_nodes=min_nodes,
            min_node_weight_share=min_node_weight_share,
            max_removed_edge_weight_share=max_removed_edge_weight_share,
        ),
    ]


def adaptive_groups_to_dictionary_text(adaptive_groups: list[dict], max_groups: int = 10) -> str:
    lines = []
    for row in adaptive_groups[:max_groups]:
        name = str(row.get("topic_group") or row.get("central_ngram") or "topic")
        name = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name.lower()).strip("_")
        terms = [term.strip() for term in str(row.get("terms") or "").split(",") if term.strip()]
        central = str(row.get("central_ngram") or "").strip()
        if central and central not in terms:
            terms.insert(0, central)
        if name and terms:
            lines.append(f"{name}: {', '.join(terms[:14])}")
    return "\n".join(lines)


def graph_structural_summary(graph: dict) -> list[dict]:
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    node_count = len(nodes)
    edge_count = len(edges)
    density = 0 if node_count < 2 else (2 * edge_count) / (node_count * (node_count - 1))
    weighted_degree_values = [float(node.get("weighted_degree_norm", node.get("weighted_degree", 0)) or 0) for node in nodes]
    knowledge_degree_values = [float(node.get("knowledge_degree", 0) or 0) for node in nodes]
    rows = [
        {"metric": "nodes", "value": node_count},
        {"metric": "edges", "value": edge_count},
        {"metric": "density", "value": round(density, 6)},
        {"metric": "communities", "value": len(graph.get("communities", []))},
        {"metric": "avg_weighted_degree_norm", "value": round(sum(weighted_degree_values) / max(1, node_count), 4)},
        {"metric": "max_knowledge_degree", "value": round(max(knowledge_degree_values or [0]), 4)},
    ]
    for key in [
        "edge_weight_min",
        "edge_weight_max",
        "edge_weight_mean",
        "edge_weight_variance",
        "edge_weight_q25",
        "edge_weight_q50",
        "edge_weight_q75",
        "node_weight_mean",
        "node_weight_variance",
        "degree_mean",
        "degree_variance",
        "top_10pct_edge_weight_share",
        "network_type_diagnostic",
        "total_raw_edge_weight",
        "absorbed_ngrams",
    ]:
        if key in graph.get("stats", {}):
            rows.append({"metric": key, "value": graph["stats"][key]})
    return rows

with st.sidebar:
    st.header("Parámetros")
    query = st.text_input("Tema / consulta", value="tatuaje", disabled=st.session_state.spider_running)
    query_variants_text = st.text_area(
        "Variantes base opcionales",
        value="",
        help="Sólo variantes generales del tema, uno por línea o separados por coma. Evita conectores solos como y/e/o.",
        disabled=st.session_state.spider_running,
    )
    variant_rubrics_text = st.text_area(
        "Rubros de variantes / sinónimos",
        value=variant_rubrics_to_text(default_variant_rubrics_for_query(query)),
        height=230,
        help=(
            "Formato: rubro: término, término. "
            "No metas conectores como variantes. Mejor 'tatuaje empleo' que 'tatuaje y empleo'. "
            "La corrida secuencial usa cada rubro por separado y luego fusiona."
        ),
        disabled=st.session_state.spider_running,
    )
    sidebar_variant_rubrics = parse_variant_rubrics(variant_rubrics_text, query)
    selected_variant_rubric_names = st.multiselect(
        "Rubros que se van a correr",
        options=list(sidebar_variant_rubrics),
        default=list(sidebar_variant_rubrics),
        help="Para un corpus publicable conviene correr rubros separados, no todos mezclados.",
        disabled=st.session_state.spider_running,
    )
    geographic_choice = st.selectbox(
        "Región geográfica del estudio",
        options=list(GEOGRAPHIC_PRESETS),
        index=0,
        disabled=st.session_state.spider_running,
    )
    default_geo_terms = ", ".join(GEOGRAPHIC_PRESETS[geographic_choice])
    geographic_terms_text = st.text_area(
        "Términos geográficos que se agregan a la búsqueda",
        value=default_geo_terms,
        help="Se agregan con OR para limitar el marco empírico. Déjalo vacío para mundo/global.",
        disabled=st.session_state.spider_running,
    )
    start_year = st.number_input("Año inicial", min_value=1979, max_value=2100, value=2020, step=1, disabled=st.session_state.spider_running)
    end_year = st.number_input("Año final", min_value=1979, max_value=2100, value=2026, step=1, disabled=st.session_state.spider_running)
    source_preset_choices = st.multiselect(
        "Fuentes básicas automáticas",
        options=list(SOURCE_PRESETS),
        default=["Noticias México", "Noticias mundo / diarios internacionales"],
        help=(
            "Estos paquetes funcionan como semilla de dominios. No sustituyen las URLs semilla: "
            "inician la búsqueda en medios auditables por región/idioma. Usa 'Sin limitar fuentes' sólo para exploración amplia."
        ),
        disabled=st.session_state.spider_running,
    )
    default_source_mode_labels = [
        "Noticias web / GDELT",
        "Noticias web / Google News RSS",
        "Artículos abiertos / OpenAlex OA",
        "Índice DOI / Crossref (metadatos + links)",
        "Artículos abiertos latinoamericanos / Redalyc",
        "Foros y Reddit públicos / GDELT por dominio",
        "Gobierno e instituciones públicas / GDELT",
    ]
    source_mode_labels = st.multiselect(
        "Motores y tipos de búsqueda",
        options=list(SOURCE_MODE_LABELS),
        default=[label for label in default_source_mode_labels if label in SOURCE_MODE_LABELS],
        help=(
            "GDELT y Google News RSS encuentran noticias y páginas públicas; OpenAlex OA prioriza artículos abiertos; "
            "Crossref es índice DOI con metadatos y posibles links, no garantía de texto libre; Redalyc aporta revistas abiertas latinoamericanas; "
            "foros se buscan como dominios públicos; Reddit RSS queda como opción manual exploratoria porque suele bloquear con 429 en corridas largas; "
            "gobierno/instituciones se separa como capa institucional. Instagram no se raspa automáticamente: requiere API/exportación/manual por robustez metodológica."
        ),
        disabled=st.session_state.spider_running,
    )
    sequential_source_layer_labels = st.multiselect(
        "Capas para corrida secuencial rubro × año × fuente",
        options=["Noticias", "Foros/conversaciones", "Gobierno/instituciones", "Artículos + PDFs", "Reportes/Otros"],
        default=["Noticias", "Foros/conversaciones", "Gobierno/instituciones", "Artículos + PDFs"],
        help=(
            "El botón Rubros × fuentes corre de forma lineal por rubro, año y capa seleccionada. "
            "Esto permite ver qué fuente/año ya terminó y fusionar después."
        ),
        disabled=st.session_state.spider_running,
    )
    sequential_synonym_limit = st.slider(
        "Máximo de términos por rubro en corrida secuencial",
        min_value=1,
        max_value=20,
        value=8,
        step=1,
        help="Usa el término base del rubro y luego sinónimos en orden. Evita saturar motores con todos los sinónimos.",
        disabled=st.session_state.spider_running,
    )
    sequential_terms_per_month = st.slider(
        "Términos aleatorios por mes y capa",
        min_value=1,
        max_value=20,
        value=8,
        step=1,
        help=(
            "En noticias, foros, instituciones y reportes la corrida toma una muestra reproducible de N términos por mes/capa. "
            "Esto evita fuerza bruta y reduce sesgo por orden fijo. Artículos científicos se tratan por año para no duplicar OpenAlex/Crossref."
        ),
        disabled=st.session_state.spider_running,
    )
    sequential_randomize = st.checkbox(
        "Aleatorizar orden de rubros/términos de forma reproducible",
        value=True,
        help="Evita sesgar la recuperación hacia el primer rubro. La semilla hace que el orden pueda repetirse.",
        disabled=st.session_state.spider_running,
    )
    sequential_seed = st.number_input(
        "Semilla de orden secuencial",
        min_value=0,
        max_value=999999,
        value=2026,
        step=1,
        disabled=st.session_state.spider_running or not sequential_randomize,
    )
    st.info(
        "Instagram: no lo raspo automáticamente porque suele requerir sesión/API, cambia el HTML y puede violar términos. "
        "Para publicación conviene importar capturas/exportaciones autorizadas como documentos manuales."
    )
    exclusion_preset = st.selectbox(
        "Filtro de exclusión conceptual",
        options=list(EXCLUSION_PRESETS),
        index=list(EXCLUSION_PRESETS).index("Tatuaje corporal/social: excluir cigarros y usos médicos") if "tatu" in query.lower() else 0,
        help="Sirve para quitar homónimos o dominios contaminantes antes del análisis.",
        disabled=st.session_state.spider_running,
    )
    preset_exclusions = EXCLUSION_PRESETS[exclusion_preset]
    preset_domains = merge_unique(
        [
            domain
            for preset in source_preset_choices
            if preset != "Sin limitar fuentes"
            for domain in SOURCE_PRESETS[preset]
        ]
    )
    domains_text = st.text_area(
        "Medios o dominios manuales",
        value=", ".join(preset_domains),
        help="Puedes editar esta lista. Si queda vacía, la búsqueda no se limita por dominio.",
        disabled=st.session_state.spider_running,
    )
    exclude_terms_text = st.text_area(
        "Términos que NO deben aparecer",
        value=", ".join(preset_exclusions["terms"]),
        help="Si un registro contiene estos términos en título, URL, medio o texto, se excluye y queda reportado en el avance.",
        disabled=st.session_state.spider_running,
    )
    exclude_domains_text = st.text_area(
        "Dominios que NO deben aparecer",
        value=", ".join(preset_exclusions["domains"]),
        help="Útil para sacar fuentes contaminantes completas, por ejemplo medios de cigarros cuando buscas tatuaje corporal.",
        disabled=st.session_state.spider_running,
    )
    max_records = st.slider(
        "Profundidad máxima por mes y motor",
        min_value=5,
        max_value=1000,
        value=100,
        step=5,
        help="No es la meta muestral. Es la profundidad de búsqueda por mes/motor antes de filtros, duplicados y errores.",
        disabled=st.session_state.spider_running,
    )
    max_records_per_type_year = st.slider(
        "Máximo anual por tipo de fuente",
        min_value=10,
        max_value=500,
        value=100,
        step=10,
        help="Balancea el corpus: como máximo N registros por año para cada tipo discursivo: noticias, foros, artículos, reportes u otros.",
        disabled=st.session_state.spider_running,
    )
    target_min_per_type_year = st.slider(
        "Mínimo deseado por año y tipo de fuente",
        min_value=0,
        max_value=100,
        value=1,
        step=1,
        help="Audita representación mínima de cada tipo discursivo. Usa 1 para exigir al menos algo de cada tipo; usa 100 si quieres aspirar a 100 de cada tipo/año.",
        disabled=st.session_state.spider_running,
    )
    min_news_per_year = st.slider(
        "Mínimo obligatorio de noticias por año",
        min_value=0,
        max_value=200,
        value=50,
        step=5,
        help="Cuando corras la capa Noticias, sólo se aceptan registros clasificados como news y se reporta brecha si no llega a este mínimo.",
        disabled=st.session_state.spider_running,
    )
    min_forums_per_year = st.slider(
        "Mínimo obligatorio de foros/conversaciones por año",
        min_value=0,
        max_value=200,
        value=50,
        step=5,
        help="Cuando corras la capa Foros, sólo se aceptan registros clasificados como forum. Reddit RSS registra publicaciones públicas, no comentarios privados.",
        disabled=st.session_state.spider_running,
    )
    search_delay = st.slider(
        "Pausa entre búsquedas mensuales, segundos",
        min_value=0.0,
        max_value=20.0,
        value=8.0,
        step=0.5,
        help="Si GDELT responde 429 Too Many Requests, sube este valor. Para corridas largas conviene 8–15 segundos.",
        disabled=st.session_state.spider_running,
    )
    delay = st.slider("Pausa entre páginas, segundos", min_value=0.0, max_value=5.0, value=1.0, step=0.25, disabled=st.session_state.spider_running)
    min_chars = st.slider(
        "Mínimo de caracteres de texto útil",
        min_value=80,
        max_value=3000,
        value=300,
        step=20,
        help="Para publicación narrativa conviene no contar metadatos muy cortos como texto completo.",
        disabled=st.session_state.spider_running,
    )
    allow_metadata_only_articles = st.checkbox(
        "Permitir artículos sólo con metadatos/abstract sin PDF abierto",
        value=False,
        help=(
            "Apagado por defecto: la capa de artículos acepta sólo OpenAlex OA/Crossref con enlace PDF o texto abierto. "
            "Actívalo sólo para revisión bibliográfica, no para corpus de texto completo."
        ),
        disabled=st.session_state.spider_running,
    )
    output_dir = st.text_input("Carpeta de salida", value="news_output", disabled=st.session_state.spider_running)
    default_seed_path = APP_ROOT / "seed_sources" / "tatuaje_mexico_news_seed_urls.json"
    default_forum_seed_path = APP_ROOT / "seed_sources" / "tatuaje_public_conversation_seed_urls.json"
    use_seed_urls = st.checkbox(
        "Usar URLs semilla de noticias mexicanas",
        value=default_seed_path.exists() and "tatu" in query.lower(),
        help="Procesa URLs curadas como noticias directas; útil cuando GDELT/Google no encuentran medios conocidos.",
        disabled=st.session_state.spider_running,
    )
    seed_url_file = st.text_input(
        "Archivo JSON de URLs semilla",
        value=str(default_seed_path) if default_seed_path.exists() else "",
        disabled=st.session_state.spider_running or not use_seed_urls,
    )
    use_forum_seed_urls = st.checkbox(
        "Usar URLs semilla de blogs/foros públicos",
        value=default_forum_seed_path.exists() and "tatu" in query.lower(),
        help=(
            "No depende de GDELT ni Reddit. Usa una lista curada de blogs, WordPress/Blogspot y señales conversacionales públicas. "
            "Debe reportarse como muestra pública parcial, no como conversación social completa."
        ),
        disabled=st.session_state.spider_running,
    )
    forum_seed_url_file = st.text_input(
        "Archivo JSON de URLs semilla conversacionales",
        value=str(default_forum_seed_path) if default_forum_seed_path.exists() else "",
        disabled=st.session_state.spider_running or not use_forum_seed_urls,
    )
    seed_domains_preview = domains_from_seed_file(seed_url_file) if use_seed_urls and seed_url_file else []
    use_seed_domains_for_search = st.checkbox(
        "Usar medios detectados en corpus semilla para buscar más noticias",
        value=bool(seed_domains_preview),
        help="Extrae dominios del JSON semilla y los agrega como dominios de búsqueda. No usa sólo las URLs semilla: busca más notas dentro de esos medios.",
        disabled=st.session_state.spider_running or not seed_domains_preview,
    )
    if seed_domains_preview:
        st.caption(f"Medios detectados en semilla: {', '.join(seed_domains_preview[:12])}")
    confirm_clear_output = st.checkbox(
        "Confirmo que quiero limpiar sólo la carpeta de salida local",
        disabled=st.session_state.spider_running,
    )
    clear_output = st.button(
        "Limpiar bases de salida",
        disabled=st.session_state.spider_running or not confirm_clear_output,
    )

manual_domains = [
    item.strip()
    for chunk in domains_text.splitlines()
    for item in chunk.split(",")
    if item.strip()
]
if clear_output:
    safe_clear, target, clear_reason = is_safe_clear_target(output_dir)
    if not safe_clear:
        st.error(clear_reason)
    elif target.exists() and target.is_dir():
        shutil.rmtree(target)
        st.session_state.spider_rows = []
        st.session_state.loaded_path = ""
        st.success(f"Bases eliminadas: {target}")
        st.rerun()
    elif target.exists():
        target.unlink()
        st.session_state.spider_rows = []
        st.session_state.loaded_path = ""
        st.success(f"Archivo eliminado: {target}")
        st.rerun()
    else:
        st.info(f"No existe todavía: {target}")

seed_search_domains = seed_domains_preview if use_seed_domains_for_search else []
domains = (
    []
    if "Sin limitar fuentes" in source_preset_choices and not manual_domains and not seed_search_domains
    else merge_unique([*manual_domains, *seed_search_domains])
)
query_variants = [
    item.strip()
    for chunk in query_variants_text.splitlines()
    for item in chunk.split(",")
    if item.strip()
]
variant_rubrics = parse_variant_rubrics(variant_rubrics_text, query)
selected_variant_rubrics = {
    name: terms
    for name, terms in variant_rubrics.items()
    if name in selected_variant_rubric_names
}
query_variants = merge_unique(
    [
        *query_variants,
        *[
            term
            for name in selected_variant_rubric_names
            for term in variant_rubrics.get(name, [])
        ],
    ]
)
geographic_terms = [
    item.strip()
    for chunk in geographic_terms_text.splitlines()
    for item in chunk.split(",")
    if item.strip()
]
exclude_terms = [
    item.strip()
    for chunk in exclude_terms_text.splitlines()
    for item in chunk.split(",")
    if item.strip()
]
exclude_domains = [
    item.strip()
    for chunk in exclude_domains_text.splitlines()
    for item in chunk.split(",")
    if item.strip()
]
source_modes = [SOURCE_MODE_LABELS[label] for label in source_mode_labels]
SEQUENTIAL_SOURCE_LAYER_SPECS = {
    "Noticias": ("news", ["gdelt_news", "google_news_rss"], False),
    "Foros/conversaciones": ("forums", ["forums"], False),
    "Gobierno/instituciones": ("institutional", ["institutional_gdelt"], False),
    "Artículos + PDFs": ("articles", ["openalex_oa", "crossref", "redalyc"], True),
    "Reportes/Otros": ("reports_other", ["gdelt_news"], False),
}
SOURCE_COLLECTION_ACCEPT_TYPES = {
    "news": ["news"],
    "forums": ["forum"],
    "institutional": ["institutional_report"],
    "articles": ["scientific_article"],
    "reports_other": [],
}
SOURCE_COLLECTION_MIN_TARGETS = {
    "news": int(min_news_per_year),
    "forums": int(min_forums_per_year),
    "institutional": int(target_min_per_type_year),
    "articles": int(target_min_per_type_year),
    "reports_other": int(target_min_per_type_year),
}
sequential_source_layers = [
    SEQUENTIAL_SOURCE_LAYER_SPECS[label]
    for label in sequential_source_layer_labels
    if label in SEQUENTIAL_SOURCE_LAYER_SPECS
]
if domains and any(mode in source_modes for mode in {"gdelt_news", "google_news_rss"}) and any(
    "reddit" in domain.lower() or "pinterest" in domain.lower()
    for domain in domains
):
    st.warning(
        "Ojo: los dominios manuales restringen también las noticias. Si mezclas reddit/pinterest con periódicos, "
        "puedes dejar fuera muchas noticias generales. Para corpus social robusto conviene separar corridas: noticias amplias, foros y artículos."
    )

config = {
    "query": query,
    "query_variants": query_variants,
    "variant_rubrics": selected_variant_rubrics,
    "geographic_scope": geographic_choice,
    "geographic_terms": geographic_terms,
    "exclude_terms": exclude_terms,
    "exclude_domains": exclude_domains,
    "source_modes": source_modes,
    "sequential_source_layers": [
        {"source_collection": source_key, "source_modes": modes, "download_pdfs": download_pdfs}
        for source_key, modes, download_pdfs in sequential_source_layers
    ],
    "sequential_synonym_limit": int(sequential_synonym_limit),
    "sequential_terms_per_month": int(sequential_terms_per_month),
    "sequential_randomize": bool(sequential_randomize),
    "sequential_seed": int(sequential_seed) if sequential_randomize else None,
    "effective_query": build_query(
        query,
        domains,
        query_variants,
        geographic_terms,
        exclude_terms=exclude_terms,
        exclude_domains=exclude_domains,
    ),
    "start_year": int(start_year),
    "end_year": int(end_year),
    "domains": domains,
    "source_presets": source_preset_choices,
    "exclusion_preset": exclusion_preset,
    "periods_to_scan": (int(end_year) - int(start_year) + 1) * 12,
    "max_records_per_month": int(max_records),
    "target_min_per_source_type_year": int(target_min_per_type_year),
    "target_min_news_per_year": int(min_news_per_year),
    "target_min_forums_per_year": int(min_forums_per_year),
    "target_min_by_source_type": {
        "news": int(min_news_per_year),
        "forum": int(min_forums_per_year),
        "institutional_report": int(target_min_per_type_year),
        "scientific_article": int(target_min_per_type_year),
        "industry_report": int(target_min_per_type_year),
        "other": int(target_min_per_type_year),
    },
    "max_records_per_source_type_year": max(int(max_records_per_type_year), int(min_news_per_year), int(min_forums_per_year)),
    "required_source_types": [],
    "accept_source_types": [],
    "seed_url_file": seed_url_file if use_seed_urls and seed_url_file else "",
    "seed_url_files_by_source": {
        "news": seed_url_file if use_seed_urls and seed_url_file else "",
        "forums": forum_seed_url_file if use_forum_seed_urls and forum_seed_url_file else "",
    },
    "download_pdfs": False,
    "strict_open_access_articles": not bool(allow_metadata_only_articles),
    "search_delay_seconds": float(search_delay),
    "delay_seconds": float(delay),
    "min_text_chars": int(min_chars),
    "output_dir": output_dir,
}

st.subheader("Diseño de recolección")
st.write(config)
source_strategy_rows = source_strategy_rows_from_seed_file(
    config.get("seed_url_file", ""),
    query,
    query_variants,
    geographic_terms,
)
if source_strategy_rows:
    st.markdown("Estrategias aprendidas del corpus semilla por medio")
    st.caption(
        "El corpus semilla no sustituye la búsqueda: extrae dominios, secciones y patrones de URL para buscar más noticias dentro de cada medio."
    )
    st.dataframe(source_strategy_rows, use_container_width=True, hide_index=True)
forum_source_strategy_rows = source_strategy_rows_from_seed_file(
    config.get("seed_url_files_by_source", {}).get("forums", ""),
    query,
    query_variants,
    geographic_terms,
)
if forum_source_strategy_rows:
    st.markdown("Estrategias aprendidas de semillas conversacionales")
    st.caption(
        "Estas fuentes son blogs/foros públicos curados. Funcionan como capa humana parcial cuando GDELT/Reddit se bloquean."
    )
    st.dataframe(forum_source_strategy_rows, use_container_width=True, hide_index=True)

profile_rows = source_profile_rows(domains, include_forums=True) if domains else source_profile_rows(include_forums=True)
with st.expander("Catálogo auditable de fuentes base"):
    st.caption(
        "Cada fuente tiene país, región, idioma, acceso y patrón esperado. "
        "Esto evita mezclar prensa, foros y artículos como si fueran la misma evidencia narrativa."
    )
    st.dataframe(profile_rows, use_container_width=True, hide_index=True)
    st.download_button(
        "Descargar catálogo de fuentes CSV",
        rows_to_csv(profile_rows),
        "source_profiles.csv",
        "text/csv",
    )

balanced_target_types = []
if any(mode in source_modes for mode in {"gdelt_news", "google_news_rss"}):
    balanced_target_types.append(("news", int(min_news_per_year)))
if any(mode in source_modes for mode in {"forums", "reddit_rss"}):
    balanced_target_types.append(("forum", int(min_forums_per_year)))
if "institutional_gdelt" in source_modes:
    balanced_target_types.append(("institutional_report", int(target_min_per_type_year)))
if any(mode in source_modes for mode in {"openalex_oa", "crossref", "redalyc"}):
    balanced_target_types.append(("scientific_article", int(target_min_per_type_year)))
if balanced_target_types:
    st.caption(
        "Contadores visibles de balance para araña mezclada. "
        "Muestran avance real contra el mínimo por año/tipo; `other` puede aparecer, pero no se usa como meta social."
    )
    current_balance_counts = Counter(
        (int(row.get("year") or 0), row_source_type(row))
        for row in st.session_state.get("spider_rows", [])
        if has_usable_text(row) and str(row.get("year", "")).isdigit()
    )
    live_log_counts = live_balance_counts_from_logs(st.session_state.get("spider_logs", []))
    for key, value in live_log_counts.items():
        current_balance_counts[key] = max(current_balance_counts.get(key, 0), value)
    balance_counter_rows = []
    for year in range(int(start_year), int(end_year) + 1):
        for source_type, minimum in balanced_target_types:
            current_count = current_balance_counts.get((year, source_type), 0)
            maximum_cap = int(config["max_records_per_source_type_year"])
            balance_counter_rows.append(
                {
                    "year": year,
                    "source_type": source_type,
                    "counter": f"{current_count}/{minimum}",
                    "actual_usable": current_count,
                    "minimum_target": minimum,
                    "gap_to_min": max(0, int(minimum) - current_count),
                    "maximum_cap": maximum_cap,
                    "cap_remaining": max(0, maximum_cap - current_count),
                    "progress_to_min": round(current_count / max(1, int(minimum)), 3) if minimum else 1.0,
                    "status": "ok" if current_count >= int(minimum) else "under_target",
                }
            )
    st.dataframe(
        balance_counter_rows,
        use_container_width=True,
        hide_index=True,
    )
if selected_variant_rubrics:
    st.caption("Rubros activos de variantes; la corrida secuencial los ejecuta uno por uno.")
    st.dataframe(
        [
            {"rubro": name, "variantes": ", ".join(terms), "n_variantes": len(terms)}
            for name, terms in selected_variant_rubrics.items()
        ],
        use_container_width=True,
        hide_index=True,
    )
    st.caption(
        "Estrategia secuencial adaptativa: para cada año y capa se prueba un solo término a la vez. "
        "El orden de rubros/términos puede aleatorizarse con semilla; cuando se alcanza la cuota anual "
        "de un tipo de fuente, los pasos restantes para ese año/tipo se saltan."
    )

with st.expander("Diseño metodológico adaptable"):
    st.markdown(
        """
La araña está pensada para que el tópico cambie. Para cualquier tópico conviene separar narrativas por fuente:

- Mayor evidencia: artículos científicos revisados por pares, estudios experimentales o longitudinales.
- Evidencia intermedia fuerte: encuestas, reportes industriales o institucionales.
- Contexto público: noticias especializadas, prensa nacional o regional.
- Práctica social/profesional: foros, comunidades y discusiones de usuarios.

El corpus semilla no se usa como sustituto de la búsqueda. Se usa para detectar
medios relevantes: la app extrae dominios de las URLs semilla y puede buscar más
notas dentro de esos medios. Para tatuaje en México esto permite buscar en NMAS,
Aristegui, El Universal, Milenio y La Jornada sin esperar a que el índice los
encuentre por azar.

La cuota se aplica por año y por tipo discursivo. Con máximo anual = 100, el sistema
puede guardar hasta 100 noticias, 100 foros, 100 artículos científicos, 100 reportes
institucionales y 100 registros de otro tipo por cada año. El mínimo deseado audita
si falta representación de alguno; no se debe concluir narrativa social completa si
algún tipo queda en cero o por debajo de la meta.

El grafo de conocimiento local permite que los grupos cambien con el tópico:
usa monogramas, bigramas y trigramas centrales, fuentes, años, idioma y localización.

Los registros RSS o indexados pueden entrar como `ok_partial`: título/resumen/metadato usable para señal
narrativa pública, aunque no equivalen a cuerpo completo. En reportes publicables deben distinguirse de `ok`.

Para análisis social no conviene dejar que OpenAlex/Crossref llenen toda la base. Si el diagnóstico muestra
dominio de `scientific_article`, corre primero una recolección social con noticias/foros y después otra
académica separada, o usa las cuotas por tipo para balancearlas.

Foros y blogs públicos recomendables como señal conversacional: Reddit público,
Quora público, StackExchange cuando el tópico aplica, Hacker News para tecnología,
Dev.to, Medium, Substack, WordPress, Blogspot y comunidades temáticas abiertas.
No equivalen a un archivo completo de comentarios; son señales públicas
indexables y deben reportarse como tales.
"""
    )

st.subheader("Recolección por capa de fuente")
st.caption(
    "Elige una acción. Las corridas por capa crean bases separadas en `output_dir/by_source/<tipo>`; "
    "después fusiona para crear un corpus combinado auditado."
)
action_options = [
    "1. Crear base de noticias",
    "2. Crear base de foros/conversaciones",
    "3. Crear base de gobierno/instituciones",
    "4. Crear base de artículos científicos + PDFs",
    "5. Crear base de reportes/otros",
    "6. Fusionar bases por fuente",
    "7. Corrida secuencial rubros × fuentes",
    "8. Araña mezclada exploratoria",
]
selected_action = st.selectbox(
    "Acción de recolección",
    options=action_options,
    help=(
        "Para corpus publicable usa primero acciones separadas por fuente y después fusiona. "
        "La araña mezclada es exploratoria."
    ),
    disabled=st.session_state.spider_running,
)
left, right = st.columns([1, 1])
with left:
    execute_action = st.button("Ejecutar acción seleccionada", type="primary", disabled=st.session_state.spider_running)
with right:
    stop = st.button("Parar araña", type="secondary", disabled=not st.session_state.spider_running)

run_news = execute_action and selected_action == "1. Crear base de noticias"
run_forums = execute_action and selected_action == "2. Crear base de foros/conversaciones"
run_institutional = execute_action and selected_action == "3. Crear base de gobierno/instituciones"
run_articles = execute_action and selected_action == "4. Crear base de artículos científicos + PDFs"
run_reports = execute_action and selected_action == "5. Crear base de reportes/otros"
merge_bases = execute_action and selected_action == "6. Fusionar bases por fuente"
run_sequential = execute_action and selected_action == "7. Corrida secuencial rubros × fuentes"
run = execute_action and selected_action == "8. Araña mezclada exploratoria"

source_run_specs = {
    "news": (run_news, ["gdelt_news", "google_news_rss"], False),
    "forums": (run_forums, ["forums"], False),
    "institutional": (run_institutional, ["institutional_gdelt"], False),
    "articles": (run_articles, ["openalex_oa", "crossref", "redalyc"], True),
    "reports_other": (run_reports, ["gdelt_news"], False),
}

selected_source_run = None
for source_key, (pressed, modes, download_pdfs) in source_run_specs.items():
    if pressed:
        selected_source_run = (source_key, modes, download_pdfs)
        break

if selected_source_run or run or run_sequential:
    if not query.strip():
        st.error("Necesitas escribir una consulta.")
        st.stop()
    if start_year > end_year:
        st.error("El año inicial no puede ser mayor que el año final.")
        st.stop()
    if not selected_source_run and not run_sequential and not source_modes:
        st.error("Selecciona al menos un motor/tipo de búsqueda.")
        st.stop()
    run_config = dict(config)
    if run_sequential:
        if not selected_variant_rubrics:
            st.error("Necesitas al menos un rubro activo.")
            st.stop()
        if not sequential_source_layers:
            st.error("Selecciona al menos una capa de fuente para la corrida secuencial.")
            st.stop()
        plan = []
        rubric_term_steps = []
        for rubric_name, rubric_terms in selected_variant_rubrics.items():
            terms = merge_unique([query, *rubric_terms])[: int(sequential_synonym_limit)]
            for term_index, term in enumerate(terms, start=1):
                rubric_term_steps.append((rubric_name, term_index, term, terms))
        rng = random.Random(int(sequential_seed)) if sequential_randomize else None
        if rng:
            rng.shuffle(rubric_term_steps)
        monthly_term_budget = max(1, int(sequential_terms_per_month))
        for year in range(int(start_year), int(end_year) + 1):
            for source_key, modes, download_pdfs in sequential_source_layers:
                if source_key == "articles":
                    if rng:
                        sampled_year_terms = rng.sample(rubric_term_steps, min(monthly_term_budget, len(rubric_term_steps)))
                    else:
                        sampled_year_terms = rubric_term_steps[:monthly_term_budget]
                    periods_for_source = [(None, sampled_year_terms)]
                else:
                    periods_for_source = []
                    for month in range(1, 13):
                        if rng:
                            sampled_terms = rng.sample(rubric_term_steps, min(monthly_term_budget, len(rubric_term_steps)))
                        else:
                            sampled_terms = rubric_term_steps[:monthly_term_budget]
                        periods_for_source.append((month, sampled_terms))
                for month, selected_terms in periods_for_source:
                    for rubric_name, term_index, term, rubric_terms in selected_terms:
                        step = dict(config)
                        step["start_year"] = int(year)
                        step["end_year"] = int(year)
                        step["start_month"] = int(month) if month else None
                        step["end_month"] = int(month) if month else None
                        step["query"] = term
                        step["query_variants"] = []
                        step["source_modes"] = modes
                        step["download_pdfs"] = download_pdfs
                        step["accept_source_types"] = SOURCE_COLLECTION_ACCEPT_TYPES.get(source_key, [])
                        step["required_source_types"] = SOURCE_COLLECTION_ACCEPT_TYPES.get(source_key, [])
                        step["target_min_per_source_type_year"] = SOURCE_COLLECTION_MIN_TARGETS.get(source_key, int(target_min_per_type_year))
                        step["seed_url_file"] = config.get("seed_url_files_by_source", {}).get(source_key, "")
                        step["variant_rubric"] = rubric_name
                        step["variant_term"] = term
                        step["variant_term_index"] = term_index
                        step["variant_rubric_terms"] = rubric_terms
                        step["source_collection"] = source_key
                        step["target_source_type"] = (SOURCE_COLLECTION_ACCEPT_TYPES.get(source_key, ["other"]) or ["other"])[0]
                        period_label = f"{year}-{month:02d}" if month else str(year)
                        step["period_label"] = period_label
                        step["output_dir"] = str(Path(output_dir) / "by_rubric" / safe_key(rubric_name) / period_label / source_key / safe_key(term))
                        if source_key == "forums":
                            step["domains"] = merge_unique([
                                *SOURCE_PRESETS.get("Foros / práctica profesional", []),
                                *SOURCE_PRESETS.get("Foros sobre tatuajes", []),
                            ])
                        if source_key == "institutional":
                            step["domains"] = merge_unique([
                                *SOURCE_PRESETS.get("Gobierno México / instituciones públicas", []),
                                *SOURCE_PRESETS.get("Gobierno global / organismos internacionales", []),
                            ])
                        plan.append(step)
        run_config["run_plan"] = plan
        run_config["output_dir"] = output_dir
        st.info(
            f"Corriendo plan secuencial adaptativo: {len(plan)} pasos. "
            f"Para web pública usa años × meses × capas × hasta {monthly_term_budget} términos aleatorios; "
            "artículos científicos se agrupan por año para evitar duplicados. "
            "Cada paso usa un solo término y se saltan pasos cuando una cuota ya se cumplió."
        )
    elif selected_source_run:
        source_key, modes, download_pdfs = selected_source_run
        run_config["source_modes"] = modes
        run_config["download_pdfs"] = download_pdfs
        run_config["accept_source_types"] = SOURCE_COLLECTION_ACCEPT_TYPES.get(source_key, [])
        run_config["required_source_types"] = SOURCE_COLLECTION_ACCEPT_TYPES.get(source_key, [])
        run_config["target_min_per_source_type_year"] = SOURCE_COLLECTION_MIN_TARGETS.get(source_key, int(target_min_per_type_year))
        run_config["seed_url_file"] = config.get("seed_url_files_by_source", {}).get(source_key, "")
        run_config["output_dir"] = source_output_dir(output_dir, source_key)
        if source_key == "forums":
            run_config["domains"] = merge_unique([
                *SOURCE_PRESETS.get("Foros / práctica profesional", []),
                *SOURCE_PRESETS.get("Foros sobre tatuajes", []),
            ])
        if source_key == "institutional":
            run_config["domains"] = merge_unique([
                *SOURCE_PRESETS.get("Gobierno México / instituciones públicas", []),
                *SOURCE_PRESETS.get("Gobierno global / organismos internacionales", []),
            ])
        st.info(f"Corriendo capa `{source_key}` en {run_config['output_dir']}")
    elif run:
        mixed_required = []
        if any(mode in source_modes for mode in {"gdelt_news", "google_news_rss"}):
            mixed_required.append("news")
        if any(mode in source_modes for mode in {"forums", "reddit_rss"}):
            mixed_required.append("forum")
        if "institutional_gdelt" in source_modes:
            mixed_required.append("institutional_report")
        if any(mode in source_modes for mode in {"openalex_oa", "crossref", "redalyc"}):
            mixed_required.append("scientific_article")
        mixed_required = merge_unique(mixed_required)
        run_config["required_source_types"] = mixed_required
        run_config["accept_source_types"] = mixed_required
        mixed_seed_files = [
            path for path in config.get("seed_url_files_by_source", {}).values()
            if path
        ]
        run_config["seed_url_file"] = ",".join(merge_unique(mixed_seed_files))
        run_config["target_min_per_source_type_year"] = max(
            int(min_news_per_year) if "news" in mixed_required else 0,
            int(min_forums_per_year) if "forum" in mixed_required else 0,
            int(target_min_per_type_year),
        )
        academic_modes = [mode for mode in source_modes if mode in {"openalex_oa", "crossref", "redalyc"}]
        indexed_modes = [mode for mode in source_modes if mode not in {"openalex_oa", "crossref", "redalyc"}]
        if academic_modes and indexed_modes:
            academic_step = dict(run_config)
            academic_step["source_modes"] = academic_modes
            academic_step["download_pdfs"] = True
            academic_step["required_source_types"] = ["scientific_article"]
            academic_step["accept_source_types"] = ["scientific_article"]
            academic_step["target_min_per_source_type_year"] = int(target_min_per_type_year)
            academic_step["seed_url_file"] = ""
            academic_step["source_collection"] = "articles_first"
            academic_step["target_source_type"] = "scientific_article"
            academic_step["variant_rubric"] = "mixed_layered"
            academic_step["variant_term"] = query
            academic_step["period_label"] = f"{int(start_year)}-{int(end_year)}"
            academic_step["output_dir"] = str(Path(output_dir) / "mixed_layers" / "articles_first")

            public_step = dict(run_config)
            public_step["source_modes"] = indexed_modes
            public_step["download_pdfs"] = False
            public_required = [source_type for source_type in mixed_required if source_type != "scientific_article"]
            public_step["required_source_types"] = public_required
            public_step["accept_source_types"] = public_required
            public_step["target_min_per_source_type_year"] = max(
                int(min_news_per_year) if "news" in public_required else 0,
                int(min_forums_per_year) if "forum" in public_required else 0,
                int(target_min_per_type_year) if "institutional_report" in public_required else 0,
            )
            public_step["seed_url_file"] = ",".join(merge_unique(mixed_seed_files))
            public_step["source_collection"] = "public_layers"
            public_step["target_source_type"] = ""
            public_step["variant_rubric"] = "mixed_layered"
            public_step["variant_term"] = query
            public_step["period_label"] = f"{int(start_year)}-{int(end_year)}"
            public_step["output_dir"] = str(Path(output_dir) / "mixed_layers" / "public_layers")
            run_config["run_plan"] = [academic_step, public_step]
            run_config["output_dir"] = output_dir
        st.info(
            "Araña mezclada por capas: si incluye artículos científicos, ahora OpenAlex/Crossref corren primero "
            "para que la capa académica no quede escondida detrás de 84 meses de RSS/GDELT. "
            f"Tipos objetivo: {', '.join(mixed_required) or 'sin tipos objetivo explícitos'}. "
            f"Máximo por tipo/año: {run_config['max_records_per_source_type_year']}."
        )
    start_worker(run_config)
    st.rerun()

if merge_bases:
    merged = merge_source_bases(output_dir, ["news", "forums", "institutional", "articles", "reports_other"])
    st.session_state.spider_rows = merged
    st.session_state.loaded_path = str(Path(output_dir) / "news_records_merged.json")
    st.success(f"Base fusionada: {len(merged)} registros.")
    st.rerun()

if stop:
    request_stop()
    st.rerun()

if st.session_state.spider_running:
    st.warning("La araña está corriendo. Puedes detenerla con el botón Parar araña.")

if st.session_state.spider_error:
    st.error(st.session_state.spider_error)

if st.session_state.spider_logs:
    st.subheader("Avance")
    live_counts = live_balance_counts_from_logs(st.session_state.spider_logs)
    if live_counts:
        st.caption("Contadores vivos recuperados de los logs de ejecución.")
        st.dataframe(
            [
                {
                    "year": year,
                    "source_type": source_type,
                    "accepted_usable_so_far": count,
                }
                for (year, source_type), count in sorted(live_counts.items())
            ],
            use_container_width=True,
            hide_index=True,
        )
    st.code("\n".join(st.session_state.spider_logs[-40:]))

if st.session_state.spider_rows:
    render_results(st.session_state.spider_rows)

if st.session_state.spider_running:
    time.sleep(1)
    st.rerun()

st.divider()
analysis_page = st.tabs(["Análisis local de narrativas"])[0]
with analysis_page:
    render_analysis_tab(output_dir)

st.divider()
st.markdown(
    """
Notas metodológicas:

- GDELT, Google News RSS, OpenAlex y Crossref funcionan como índices; la extracción completa sólo se intenta si la fuente pública lo permite.
- Algunos medios bloquean arañas, usan paywall o entregan páginas muy cortas; esos casos se guardan como `fetch_error`, `too_short` u `ok_partial`.
- El sistema distingue texto completo de señal parcial: una URL indexada no equivale a evidencia textual plena.
- La pestaña de análisis trabaja localmente sobre JSON/JSONL ya guardados. No usa modelos externos.
- Los marcadores retóricos, señales de presión narrativa y ausencias relativas son heurísticas de auditoría; requieren validación humana.
- Neo4j/FastAPI/PostgreSQL son ruta futura de escalamiento; el prototipo actual opera con Streamlit, JSON y CSV.
- El botón **Parar araña** detiene la corrida al terminar la llamada de red o la espera actual; no borra lo ya guardado.
"""
)
