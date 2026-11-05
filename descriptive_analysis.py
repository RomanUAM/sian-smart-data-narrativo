"""Descriptive analyses shared by the interactive and batch modes."""
from collections import defaultdict
import math
import re

from narrative_analysis import top_terms, normalize_token_text
from news_spider import classify_source_type

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


POSITIVE_SENTIMENT_TERMS = {
    "aceptacion", "aceptación", "aceptado", "admiracion", "admiración", "alegria", "alegría",
    "apoyo", "atractivo", "autonomia", "autonomía", "belleza", "beneficio", "bienestar",
    "celebracion", "celebración", "confianza", "creatividad", "cuidado", "deseable",
    "digno", "empoderamiento", "expresion", "expresión", "favorable", "feliz", "identidad",
    "inclusion", "inclusión", "libertad", "mejora", "orgullo", "positivo", "reconocimiento",
    "respeto", "seguro", "solidaridad", "valor", "valioso",
    "acceptance", "accepted", "admiration", "autonomy", "beautiful", "beauty", "benefit",
    "care", "celebration", "confidence", "creative", "creativity", "desirable", "empowerment",
    "expression", "freedom", "happy", "improvement", "positive",
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
    "criticism", "damage", "danger", "disease", "discrimination", "failure", "fear", "harm", "illegal", "infection", "negative", "pain", "prejudice",
    "problem", "rejection", "regret", "risk", "stigma", "threat", "violence", "vulnerability",
}


NEGATION_TERMS = {"no", "not", "never", "nunca", "sin", "without", "ni"}


INTENSIFIER_TERMS = {"muy", "very", "bastante", "really", "extremely", "sumamente", "altamente"}


def sentiment_for_text(text: str, extra_positive: list[str] | None = None, extra_negative: list[str] | None = None) -> dict:
    tokens = re.findall(r"\b[a-z]+\b", normalize_token_text(text))
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


def narrative_timeline_rows(records: list[dict], event_rows: list[dict], extra_stopwords: list[str]) -> list[dict]:
    event_by_key = {row.get("doc_key"): row for row in event_rows}
    grouped: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for row in records:
        if not str(row.get("year", "")).isdigit():
            continue
        grouped[(int(row.get("year")), row_source_type(row))].append(row)
    timeline = []
    for (year, source_type), rows in sorted(grouped.items()):
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


def normalize_local(value: str) -> str:
    table = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")
    value = (value or "").lower().translate(table)
    return " ".join(value.split())
