from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict
from typing import Iterable


CAUSAL_MARKERS = [
    "because", "due to", "as a result", "therefore", "caused", "causes", "causing",
    "leads to", "led to", "results in", "provokes", "prevents", "blocks",
    "porque", "debido a", "por lo tanto", "como resultado", "causa", "causó",
    "causo", "provoca", "provocó", "provoco", "genera", "generó", "genero",
    "produce", "impide", "evita", "deriva", "derivó", "derivo", "lleva a",
]

SPEECH_ACT_MARKERS = {
    "assertive": [
        "afirma", "afirmó", "dice", "dijo", "señala", "señaló", "reporta", "reportó",
        "sostiene", "asegura", "confirma", "indica", "claims", "said", "says",
        "states", "reports", "argues", "confirms",
    ],
    "directive": [
        "debe", "deben", "exige", "pide", "llama a", "ordena", "recomienda",
        "prohíbe", "prohibe", "solicita", "should", "must", "requires", "urges",
        "calls for", "demands", "orders", "recommends", "forbids",
    ],
    "commissive": [
        "promete", "prometió", "se compromete", "garantiza", "ofrece", "promises",
        "pledges", "commits", "guarantees", "offers",
    ],
    "expressive": [
        "lamenta", "celebra", "critica", "rechaza", "teme", "denuncia", "acusa",
        "regrets", "celebrates", "criticizes", "rejects", "fears", "denounces",
        "accuses",
    ],
    "declarative": [
        "declara", "anuncia", "certifica", "autoriza", "sanciona", "aprueba",
        "declares", "announces", "certifies", "authorizes", "sanctions", "approves",
    ],
}

FALLACY_PATTERNS = {
    "ad_hominem": [
        "corrupto", "ignorante", "estúpido", "idiota", "criminal", "vendido",
        "stupid", "idiot", "corrupt", "criminal", "liar",
    ],
    "false_cause": [
        "por eso", "por lo tanto", "therefore", "así que", "so,", "caused by",
        "la causa es", "the cause is",
    ],
    "slippery_slope": [
        "terminará en", "terminara en", "llevará a", "llevara a", "inevitablemente",
        "will inevitably", "will lead to", "slippery slope",
    ],
    "false_dichotomy": [
        "o estás con", "o estas con", "o contra", "either you", "either/or",
        "no hay alternativa", "there is no alternative",
    ],
    "appeal_to_fear": [
        "amenaza", "peligro", "miedo", "terror", "caos", "crisis total",
        "threat", "danger", "fear", "panic", "chaos",
    ],
    "hasty_generalization": [
        "todos", "todas", "siempre", "nunca", "nadie", "all of them", "always",
        "never", "nobody", "everyone",
    ],
    "appeal_to_authority": [
        "según expertos", "los expertos dicen", "la ciencia dice", "estudio demuestra",
        "experts say", "science says", "study proves", "authority says",
    ],
}

DISINFORMATION_VECTOR_PATTERNS = {
    "emotional_overflow": [
        "escándalo", "escandalo", "indignante", "terrible", "horror", "pánico",
        "panic", "outrage", "shocking", "terrible", "horrific",
    ],
    "urgency_pressure": [
        "urgente", "comparte", "antes de que", "no quieren que sepas",
        "urgent", "share before", "they do not want you to know",
    ],
    "conspiracy_frame": [
        "conspiración", "conspiracion", "agenda oculta", "élite", "elite",
        "deep state", "hidden agenda", "conspiracy",
    ],
    "scapegoating": [
        "culpa de", "responsables de todo", "enemigos", "invasión", "invasion",
        "to blame", "enemies", "responsible for everything",
    ],
    "absolute_claim": [
        "siempre", "nunca", "todos", "nadie", "sin duda", "definitivamente",
        "always", "never", "everyone", "nobody", "undoubtedly", "definitely",
    ],
}

VERB_MARKERS = [
    "es", "son", "fue", "será", "sera", "tiene", "tienen", "hace", "hacen",
    "causa", "provoca", "genera", "impide", "permite", "rechaza", "apoya",
    "acusa", "afirma", "dice", "anuncia", "recomienda", "exige", "promete",
    "is", "are", "was", "were", "will", "has", "have", "causes", "generates",
    "prevents", "allows", "rejects", "supports", "accuses", "claims", "says",
    "announces", "recommends", "demands", "promises",
]

FRAME_MARKERS = {
    "problem": [
        "problema", "riesgo", "crisis", "conflicto", "daño", "peligro", "prejuicio",
        "estigma", "ilegal", "infección", "infeccion", "alergia", "problem", "risk",
        "crisis", "conflict", "harm", "danger", "stigma", "illegal", "infection",
    ],
    "culprit": [
        "culpa", "culpable", "responsable", "causa", "provoca", "por", "debido a",
        "blame", "responsible", "causes", "caused by", "due to",
    ],
    "solution": [
        "solución", "solucion", "resolver", "medida", "regulación", "regulacion",
        "propuesta", "recomienda", "debe", "prevención", "prevencion", "solution",
        "measure", "regulation", "proposal", "recommends", "should", "must",
        "prevention",
    ],
    "urgency": [
        "urgente", "ahora", "inmediato", "antes de", "pronto", "alerta", "hoy",
        "urgent", "now", "immediate", "before", "soon", "alert", "today",
    ],
}

ONTOLOGICAL_RELATIONS = [
    "APOYA_A",
    "ATACA_A",
    "CONTRADICE_A",
    "AMPLIFICA_A",
    "DESINFORMA_SOBRE",
    "VERIFICA_A",
    "DEPENDE_DE",
    "ANTECEDE_A",
    "CAUSA_A",
    "PREVIENE_A",
    "JUSTIFICA_A",
    "CUESTIONA_A",
    "IGNORA_A",
    "ECO_DE",
    "NARRATIVA_ALTERNATIVA_DE",
]


def clean_space(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def tokenize_light(text: str) -> list[str]:
    return [
        token.lower()
        for token in re.findall(r"[\wáéíóúÁÉÍÓÚñÑüÜ-]+", str(text or ""))
        if len(token) > 2
    ]


def jaccard_similarity(a: Iterable[str], b: Iterable[str]) -> float:
    set_a = {item for item in a if item}
    set_b = {item for item in b if item}
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def split_sentences(text: str, max_sentences: int = 80) -> list[str]:
    text = clean_space(text)
    if not text:
        return []
    parts = re.split(r"(?<=[.!?¿¡])\s+", text)
    return [part.strip() for part in parts if len(part.strip()) >= 25][:max_sentences]


def detect_speech_act(sentence: str) -> tuple[str, str]:
    lowered = sentence.lower()
    for act, markers in SPEECH_ACT_MARKERS.items():
        for marker in markers:
            if marker in lowered:
                return act, marker
    return "assertive", "default_statement"


def detect_markers(sentence: str, marker_map: dict[str, list[str]]) -> list[dict]:
    lowered = sentence.lower()
    hits = []
    for label, markers in marker_map.items():
        found = [marker for marker in markers if marker in lowered]
        if found:
            hits.append({"label": label, "markers": ", ".join(found[:6])})
    return hits


def extract_svo(sentence: str) -> dict:
    words = re.findall(r"[\wáéíóúÁÉÍÓÚñÑüÜ-]+", sentence)
    lowered = [word.lower() for word in words]
    verb_index = -1
    verb = ""
    for index, word in enumerate(lowered):
        if word in VERB_MARKERS or re.search(r"(ó|o|a|an|en|ed|ing)$", word):
            verb_index = index
            verb = words[index]
            break
    if verb_index <= 0:
        return {"subject": "", "verb": "", "object": "", "svo_confidence": "low"}
    subject = " ".join(words[max(0, verb_index - 5):verb_index])
    obj = " ".join(words[verb_index + 1:verb_index + 9])
    confidence = "medium" if subject and obj else "low"
    return {"subject": subject, "verb": verb, "object": obj, "svo_confidence": confidence}


def hidden_premise_hint(sentence: str, speech_act: str, fallacies: list[str]) -> str:
    lowered = sentence.lower()
    if "false_cause" in fallacies or any(marker in lowered for marker in CAUSAL_MARKERS):
        return "Supone una relación causal que debe verificarse con evidencia externa."
    if speech_act == "directive":
        return "Supone una norma implícita sobre lo que debe hacerse o evitarse."
    if speech_act == "expressive":
        return "Supone una valoración compartida que puede no ser universal."
    if any(term in lowered for term in ["normal", "natural", "obvio", "obvious", "inevitable"]):
        return "Naturaliza una premisa que debe hacerse explícita."
    return ""


def proposition_confidence(svo: dict, fallacy_labels: list[str], vector_labels: list[str]) -> float:
    score = 0.35
    if svo.get("subject") and svo.get("verb"):
        score += 0.25
    if svo.get("object"):
        score += 0.15
    if fallacy_labels:
        score -= 0.08
    if vector_labels:
        score -= 0.05
    return round(max(0.0, min(1.0, score)), 3)


def record_custody_hash(record: dict) -> str:
    material = "|".join(
        clean_space(str(record.get(key, "")))
        for key in ["url", "title", "published_date", "fetched_at", "status", "text_clean"]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def extract_structural_propositions(records: list[dict], max_sentences_per_doc: int = 40) -> list[dict]:
    rows: list[dict] = []
    for record in records:
        text = clean_space(" ".join([str(record.get("title") or ""), str(record.get("text_clean") or record.get("text_normalized") or "")]))
        custody_hash = record_custody_hash(record)
        for idx, sentence in enumerate(split_sentences(text, max_sentences=max_sentences_per_doc), start=1):
            speech_act, speech_marker = detect_speech_act(sentence)
            svo = extract_svo(sentence)
            causal_hits = [marker for marker in CAUSAL_MARKERS if marker in sentence.lower()]
            fallacy_hits = detect_markers(sentence, FALLACY_PATTERNS)
            vector_hits = detect_markers(sentence, DISINFORMATION_VECTOR_PATTERNS)
            fallacy_labels = [hit["label"] for hit in fallacy_hits]
            vector_labels = [hit["label"] for hit in vector_hits]
            proposition_id = hashlib.sha1(f"{custody_hash}:{idx}:{sentence}".encode("utf-8")).hexdigest()[:16]
            rows.append(
                {
                    "proposition_id": proposition_id,
                    "record_hash": custody_hash,
                    "sentence_index": idx,
                    "year": record.get("year"),
                    "source_type": record.get("source_type") or "other",
                    "medium": record.get("medium") or "unknown",
                    "title": record.get("title", ""),
                    "url": record.get("url", ""),
                    "sentence": sentence,
                    **svo,
                    "speech_act": speech_act,
                    "speech_marker": speech_marker,
                    "causal_markers": ", ".join(causal_hits[:6]),
                    "has_causal_relation": bool(causal_hits),
                    "fallacies": ", ".join(fallacy_labels),
                    "fallacy_markers": " | ".join(f"{hit['label']}:{hit['markers']}" for hit in fallacy_hits),
                    "disinformation_vectors": ", ".join(vector_labels),
                    "disinformation_markers": " | ".join(f"{hit['label']}:{hit['markers']}" for hit in vector_hits),
                    "hidden_premise_hint": hidden_premise_hint(sentence, speech_act, fallacy_labels),
                    "structural_confidence": proposition_confidence(svo, fallacy_labels, vector_labels),
                }
            )
    return rows


def shannon_entropy(values: Iterable[str]) -> float:
    counts = Counter(value for value in values if value)
    total = sum(counts.values())
    if total <= 0:
        return 0.0
    return round(-sum((count / total) * math.log2(count / total) for count in counts.values()), 5)


def structural_summary(propositions: list[dict]) -> list[dict]:
    grouped: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for row in propositions:
        year = int(row.get("year") or 0)
        source_type = str(row.get("source_type") or "other")
        grouped[(year, source_type)].append(row)
    output = []
    for (year, source_type), rows in sorted(grouped.items()):
        fallacy_count = sum(1 for row in rows if row.get("fallacies"))
        vector_count = sum(1 for row in rows if row.get("disinformation_vectors"))
        causal_count = sum(1 for row in rows if row.get("has_causal_relation"))
        output.append(
            {
                "year": year,
                "source_type": source_type,
                "propositions": len(rows),
                "causal_relations": causal_count,
                "fallacy_signals": fallacy_count,
                "disinformation_vector_signals": vector_count,
                "speech_act_entropy": shannon_entropy(row.get("speech_act", "") for row in rows),
                "predicate_entropy": shannon_entropy(row.get("verb", "").lower() for row in rows),
                "mean_structural_confidence": round(sum(float(row.get("structural_confidence") or 0) for row in rows) / max(1, len(rows)), 5),
            }
        )
    return output


def build_structural_influence_graph(propositions: list[dict], min_weight: int = 2) -> dict:
    nodes: dict[str, dict] = {}
    edges: Counter[tuple[str, str, str]] = Counter()

    def add_node(node_id: str, label: str, node_type: str) -> None:
        if not label:
            return
        if node_id not in nodes:
            nodes[node_id] = {"id": node_id, "label": label, "node_type": node_type, "count": 0}
        nodes[node_id]["count"] += 1

    for row in propositions:
        source_id = f"source::{row.get('medium') or 'unknown'}"
        act_id = f"speech_act::{row.get('speech_act') or 'assertive'}"
        add_node(source_id, str(row.get("medium") or "unknown"), "source")
        add_node(act_id, str(row.get("speech_act") or "assertive"), "speech_act")
        edges[(source_id, act_id, "uses_speech_act")] += 1
        if row.get("subject"):
            subject_id = f"actor::{str(row['subject']).lower()}"
            add_node(subject_id, str(row["subject"]), "actor")
            edges[(source_id, subject_id, "mentions_actor")] += 1
            edges[(subject_id, act_id, "actor_in_speech_act")] += 1
        if row.get("has_causal_relation"):
            causal_id = "logic::causal_claim"
            add_node(causal_id, "causal claim", "logic")
            edges[(source_id, causal_id, "makes_logic_move")] += 1
        for fallacy in [item.strip() for item in str(row.get("fallacies") or "").split(",") if item.strip()]:
            fallacy_id = f"fallacy::{fallacy}"
            add_node(fallacy_id, fallacy, "fallacy_signal")
            edges[(source_id, fallacy_id, "contains_fallacy_signal")] += 1
        for vector in [item.strip() for item in str(row.get("disinformation_vectors") or "").split(",") if item.strip()]:
            vector_id = f"vector::{vector}"
            add_node(vector_id, vector, "disinformation_vector")
            edges[(source_id, vector_id, "contains_vector_signal")] += 1

    edge_rows = [
        {"source": source, "target": target, "edge_type": edge_type, "weight": weight}
        for (source, target, edge_type), weight in edges.items()
        if weight >= min_weight
    ]
    return {"nodes": list(nodes.values()), "edges": edge_rows}


def technical_traceability_rows(records: list[dict]) -> list[dict]:
    rows = []
    for record in records:
        rows.append(
            {
                "record_hash": record_custody_hash(record),
                "url": record.get("url", ""),
                "title": record.get("title", ""),
                "medium": record.get("medium", ""),
                "year": record.get("year", ""),
                "status": record.get("status", ""),
                "source_type": record.get("source_type", "other"),
                "fetched_at": record.get("fetched_at", ""),
                "source_api": record.get("source_api", ""),
            }
        )
    return rows




def smart_source_cartography(records: list[dict], pareto_share: float = 0.80) -> dict:
    """Capa 1: rank sources by influence proxy and retain Pareto core."""
    by_source: dict[str, dict] = {}
    for record in records:
        medium = clean_space(record.get("medium") or "unknown")
        row = by_source.setdefault(
            medium,
            {
                "source": medium,
                "records": 0,
                "years": set(),
                "source_types": Counter(),
                "statuses": Counter(),
                "total_text_length": 0,
                "structural_weight": 0.0,
                "urls": set(),
            },
        )
        text = clean_space(record.get("text_clean") or record.get("title") or "")
        row["records"] += 1
        if record.get("year"):
            row["years"].add(int(record.get("year")))
        row["source_types"][record.get("source_type") or "other"] += 1
        row["statuses"][record.get("status") or "unknown"] += 1
        row["total_text_length"] += len(text)
        row["structural_weight"] += 1.0 + min(2.0, len(text) / 2500)
        if record.get("url"):
            row["urls"].add(record.get("url"))

    rows = []
    for row in by_source.values():
        years = sorted(row.pop("years"))
        urls = row.pop("urls")
        source_types = row.pop("source_types")
        statuses = row.pop("statuses")
        row["first_year"] = years[0] if years else ""
        row["last_year"] = years[-1] if years else ""
        row["active_years"] = len(years)
        row["source_type_main"] = source_types.most_common(1)[0][0] if source_types else "other"
        row["ok_records"] = statuses.get("ok", 0)
        row["partial_records"] = statuses.get("ok_partial", 0)
        row["unique_urls"] = len(urls)
        rows.append(row)
    rows.sort(key=lambda item: (float(item["structural_weight"]), int(item["records"])), reverse=True)
    total_weight = sum(float(row["structural_weight"]) for row in rows) or 1.0
    cumulative = 0.0
    pareto_rows = []
    for rank, row in enumerate(rows, start=1):
        cumulative += float(row["structural_weight"])
        row["rank"] = rank
        row["weight_share"] = round(float(row["structural_weight"]) / total_weight, 5)
        row["cumulative_weight_share"] = round(cumulative / total_weight, 5)
        row["pareto_core"] = cumulative / total_weight <= pareto_share or not pareto_rows
        if row["pareto_core"]:
            pareto_rows.append(row)
    return {"sources": rows, "pareto_sources": pareto_rows, "pareto_share": pareto_share}


def sentence_for_frame(sentences: list[str], markers: list[str]) -> str:
    for sentence in sentences:
        lowered = sentence.lower()
        if any(marker in lowered for marker in markers):
            return sentence[:500]
    return ""


def extract_argument_frames(records: list[dict], max_sentences_per_doc: int = 60) -> list[dict]:
    """Capa 2: extract problem/culprit/solution/urgency frames without storing full text."""
    frames = []
    for record in records:
        text = clean_space(" ".join([str(record.get("title") or ""), str(record.get("text_clean") or record.get("text_normalized") or "")]))
        sentences = split_sentences(text, max_sentences=max_sentences_per_doc)
        frame = {
            "frame_id": hashlib.sha1(f"{record_custody_hash(record)}:frame".encode("utf-8")).hexdigest()[:16],
            "record_hash": record_custody_hash(record),
            "year": record.get("year"),
            "source_type": record.get("source_type") or "other",
            "medium": record.get("medium") or "unknown",
            "title": record.get("title", ""),
            "url": record.get("url", ""),
            "problem": sentence_for_frame(sentences, FRAME_MARKERS["problem"]),
            "culprit": sentence_for_frame(sentences, FRAME_MARKERS["culprit"]),
            "solution": sentence_for_frame(sentences, FRAME_MARKERS["solution"]),
            "urgency": sentence_for_frame(sentences, FRAME_MARKERS["urgency"]),
        }
        frame_tokens = tokenize_light(" ".join([frame["problem"], frame["culprit"], frame["solution"], frame["urgency"]]))
        frame["frame_terms"] = " ".join(frame_tokens[:80])
        frame["frame_density"] = round(sum(1 for key in ["problem", "culprit", "solution", "urgency"] if frame[key]) / 4, 3)
        frame["raw_text_retention"] = "structure_only"
        frames.append(frame)
    return frames


def detect_echo_frames(frames: list[dict], similarity_threshold: float = 0.90) -> list[dict]:
    """Label repeated frames as ECO_DE using Jaccard over structural terms."""
    canonical: list[dict] = []
    output = []
    for frame in frames:
        tokens = tokenize_light(frame.get("frame_terms", ""))
        best = None
        best_similarity = 0.0
        for candidate in canonical:
            sim = jaccard_similarity(tokens, tokenize_light(candidate.get("frame_terms", "")))
            if sim > best_similarity:
                best_similarity = sim
                best = candidate
        row = dict(frame)
        if best and best_similarity >= similarity_threshold:
            row["echo_status"] = "echo"
            row["echo_of_frame_id"] = best["frame_id"]
            row["echo_similarity"] = round(best_similarity, 5)
            row["relation_type"] = "ECO_DE"
            row["storage_decision"] = "store_hash_relation_only"
        else:
            row["echo_status"] = "original_or_variant"
            row["echo_of_frame_id"] = ""
            row["echo_similarity"] = round(best_similarity, 5)
            row["relation_type"] = "NARRATIVA_ALTERNATIVA_DE" if canonical else "ORIGEN_DE_MARCO"
            row["storage_decision"] = "store_structural_frame"
            canonical.append(row)
        output.append(row)
    return output


def temporal_frame_deltas(frames: list[dict], similarity_threshold: float = 0.82) -> list[dict]:
    """Capa 3: store only changes in frame structure across time per source."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for frame in frames:
        grouped[str(frame.get("medium") or "unknown")].append(frame)
    deltas = []
    for medium, rows in grouped.items():
        rows = sorted(rows, key=lambda item: (int(item.get("year") or 0), str(item.get("frame_id"))))
        previous = None
        for row in rows:
            if previous is None:
                deltas.append({
                    "medium": medium,
                    "year": row.get("year"),
                    "frame_id": row.get("frame_id"),
                    "delta_type": "baseline",
                    "similarity_to_previous": "",
                    "changed_fields": "problem, culprit, solution, urgency",
                    "storage_decision": "store_structural_frame",
                })
                previous = row
                continue
            sim = jaccard_similarity(tokenize_light(row.get("frame_terms", "")), tokenize_light(previous.get("frame_terms", "")))
            changed_fields = [
                field for field in ["problem", "culprit", "solution", "urgency"]
                if jaccard_similarity(tokenize_light(row.get(field, "")), tokenize_light(previous.get(field, ""))) < similarity_threshold
            ]
            deltas.append({
                "medium": medium,
                "year": row.get("year"),
                "frame_id": row.get("frame_id"),
                "previous_frame_id": previous.get("frame_id"),
                "delta_type": "change" if changed_fields else "stable_repetition",
                "similarity_to_previous": round(sim, 5),
                "changed_fields": ", ".join(changed_fields),
                "storage_decision": "store_delta" if changed_fields else "timestamp_counter_only",
            })
            if changed_fields:
                previous = row
    return deltas


def silence_alerts(frames: list[dict], expected_topics: list[str], silence_threshold: float = 0.70) -> list[dict]:
    """Capa 4: flag expected topics absent from most sources."""
    sources = {str(frame.get("medium") or "unknown") for frame in frames}
    total_sources = max(1, len(sources))
    alerts = []
    for topic in [clean_space(topic).lower() for topic in expected_topics if clean_space(topic)]:
        mentioning_sources = {
            str(frame.get("medium") or "unknown")
            for frame in frames
            if topic in " ".join([
                str(frame.get("problem", "")),
                str(frame.get("culprit", "")),
                str(frame.get("solution", "")),
                str(frame.get("urgency", "")),
                str(frame.get("frame_terms", "")),
            ]).lower()
        }
        missing_share = 1.0 - (len(mentioning_sources) / total_sources)
        alerts.append({
            "expected_topic": topic,
            "sources_total": total_sources,
            "sources_mentioning": len(mentioning_sources),
            "missing_share": round(missing_share, 5),
            "alert": missing_share >= silence_threshold,
            "relation_type": "IGNORA_A" if missing_share >= silence_threshold else "CUBRE_A",
            "storage_decision": "high_value_silence_alert" if missing_share >= silence_threshold else "no_alert",
        })
    return alerts


def smart_data_nucleus(records: list[dict], expected_topics: list[str] | None = None) -> dict:
    cartography = smart_source_cartography(records)
    pareto_mediums = {row["source"] for row in cartography["pareto_sources"]}
    pareto_records = [record for record in records if (record.get("medium") or "unknown") in pareto_mediums]
    frames = extract_argument_frames(pareto_records)
    echo_frames = detect_echo_frames(frames)
    deltas = temporal_frame_deltas(echo_frames)
    silences = silence_alerts(echo_frames, expected_topics or [])
    return {
        "ontology_relations": [{"relation": relation} for relation in ONTOLOGICAL_RELATIONS],
        "cartography": cartography,
        "frames": echo_frames,
        "temporal_deltas": deltas,
        "silence_alerts": silences,
        "retention_policy": {
            "raw_text": "process_locally_then_minimize",
            "persistent": "hashes, frames, relations, metadata",
            "note": "Local prototype: raw records remain only if user keeps corpus files; SDN export stores structure.",
        },
    }
