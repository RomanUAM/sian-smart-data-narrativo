from __future__ import annotations

import csv
import copy
import json
import math
import random
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from itertools import combinations
from pathlib import Path
from typing import Iterable


STOPWORDS = {
    # Spanish
    "a", "al", "algo", "ante", "asi", "así", "aunque", "cada", "como", "con", "contra",
    "cual", "cuando", "de", "del", "desde", "donde", "dos", "durante", "e", "el", "ella",
    "ellas", "ellos", "en", "entre", "era", "eran", "es", "esa", "esas", "ese", "eso",
    "esos", "esta", "estaba", "estado", "estan", "están", "estar", "este", "esto",
    "estos", "fue", "ha", "han", "hasta", "hay", "la", "las", "le", "les", "lo", "los",
    "mas", "más", "me", "mi", "mientras", "muy", "no", "nos", "o", "otra", "otras",
    "otro", "otros", "para", "pero", "por", "porque", "que", "qué", "se", "segun",
    "según", "ser", "si", "sí", "sin", "sobre", "son", "su", "sus", "tambien",
    "también", "tan", "tanto", "te", "tiene", "tienen", "todo", "todos", "tras", "tu",
    "un", "una", "unas", "uno", "unos", "y", "ya",
    # English
    "about", "above", "after", "again", "against", "all", "am", "an", "and", "any",
    "are", "as", "at", "be", "because", "been", "before", "being", "below", "between",
    "both", "but", "by", "can", "did", "do", "does", "doing", "down", "during", "each",
    "few", "for", "from", "further", "had", "has", "have", "having", "he", "her", "here",
    "hers", "herself", "him", "himself", "his", "how", "i", "if", "in", "into", "is",
    "it", "its", "itself", "just", "me", "more", "most", "my", "myself", "no", "nor",
    "not", "now", "of", "off", "on", "once", "only", "or", "other", "our", "ours",
    "out", "over", "own", "same", "she", "should", "so", "some", "such", "than", "that",
    "the", "their", "theirs", "them", "themselves", "then", "there", "these", "they",
    "this", "those", "through", "to", "too", "under", "until", "up", "very", "was",
    "we", "were", "what", "when", "where", "which", "while", "who", "whom", "why",
    "with", "would", "will", "shall", "might", "must", "could", "you", "your", "yours",
    # Corpus noise
    "http", "https", "www", "com", "org", "doi", "journal", "news", "article", "said",
    "says", "also", "could", "would", "may", "one", "two", "new", "use", "used", "using",
    "via", "get", "got", "see", "read", "share", "follow", "subscribe", "newsletter",
    "cookie", "cookies", "privacy", "policy", "advertisement", "ads", "login", "sign",
    "copyright", "rights", "reserved", "image", "photo", "video", "posted", "post",
    "related", "posts", "source", "sources", "page", "pages", "click", "menu",
    "home", "contact", "email", "print", "open", "close", "search", "results",
    "english", "spanish", "language", "global", "unclear",
    # Generic temporal/descriptive noise frequent in crawled corpora
    "first", "second", "third", "last", "next", "previous", "current", "recent",
    "today", "yesterday", "tomorrow", "week", "month", "months", "year", "years",
    "time", "times", "day", "days", "back", "later", "early", "late",
    "make", "made", "makes", "making", "take", "takes", "took", "given", "give",
    "like", "much", "many", "several", "three", "four", "five", "part", "bit",
    "people", "person", "public", "group", "groups", "including", "according",
    "reported", "known", "available", "information", "general", "online",
    # Ruido común en español de medios y páginas web
    "noticia", "noticias", "articulo", "artículo", "leer", "ver", "compartir",
    "suscribete", "suscríbete", "boletin", "boletín", "publicidad", "anuncio",
    "inicio", "pagina", "página", "buscar", "resultados", "fuente", "fuentes",
    "derechos", "reservados", "imagen", "foto", "publicado", "publicada",
    "relacionado", "relacionados", "correo", "contacto", "imprimir",
    "primer", "primera", "segundo", "segunda", "tercer", "tercera", "ultimo",
    "último", "ultima", "última", "actual", "reciente", "hoy", "ayer", "mañana",
    "semana", "semanas", "mes", "meses", "ano", "años", "tiempo", "dia", "día",
    "dias", "días", "luego", "despues", "después", "hace", "hacer", "hecho",
    "dado", "dar", "parte", "poco", "mucho", "muchos", "varios", "personas",
    "publico", "público", "grupo", "incluye", "incluyendo", "acuerdo",
}

MEXICO_TERMS = {
    "mexico", "méxico", "mexican", "mexicana", "mexicano", "mexicanas", "mexicanos",
    "cdmx", "ciudad de mexico", "ciudad de méxico", "edomex", "estado de mexico",
    "estado de méxico", "guadalajara", "monterrey", "puebla", "queretaro", "querétaro",
    "uanl", "unam", "ipn", "uam", "tec de monterrey", "conacyt", "conahcyt",
}

LATAM_TERMS = {
    "latin america", "america latina", "américa latina", "latinoamerica", "latinoamérica",
    "latam", "argentina", "chile", "colombia", "peru", "perú", "brasil", "brazil",
    "uruguay", "paraguay", "bolivia", "ecuador", "venezuela", "costa rica",
    "guatemala", "honduras", "panama", "panamá", "el salvador",
}


AI_SOFTWARE_NARRATIVE_FRAMES = {
    "productivity": [
        "productivity", "productive", "efficiency", "faster", "speed", "time saving",
        "ahorro", "tiempo", "productividad", "eficiencia", "rapidez", "acelera",
    ],
    "supervision": [
        "supervision", "supervisory", "oversight", "review", "validate", "verification",
        "supervisión", "supervisar", "validación", "verificación", "revisar", "revisión",
    ],
    "errors_and_correction": [
        "error", "errors", "bug", "bugs", "incorrect", "hallucination", "debug", "fix",
        "errores", "fallas", "corregir", "corrección", "depurar", "alucinación",
    ],
    "security": [
        "security", "vulnerability", "vulnerabilities", "privacy", "risk", "risks",
        "seguridad", "vulnerabilidad", "privacidad", "riesgo", "riesgos",
    ],
    "architecture": [
        "architecture", "design", "system design", "maintainability", "technical debt",
        "arquitectura", "diseño", "mantenibilidad", "deuda técnica",
    ],
    "requirements": [
        "requirements", "specification", "user needs", "problem definition",
        "requisitos", "requerimientos", "especificación", "necesidades", "problema",
    ],
    "ux": [
        "user experience", "ux", "interface", "usability", "users",
        "experiencia de usuario", "interfaz", "usabilidad", "usuarios",
    ],
    "trust": [
        "trust", "confidence", "reliability", "accuracy", "precise", "precision",
        "confianza", "confiabilidad", "precisión", "exactitud",
    ],
    "labor_role": [
        "replace", "replacement", "job", "role", "developer", "engineer", "skills",
        "reemplazar", "sustituir", "trabajo", "rol", "programador", "ingeniero", "habilidades",
    ],
}

TATTOO_NARRATIVE_FRAMES = {
    "bodily_archive_memory": [
        "memoria", "memory", "recuerdo", "remember", "duelo", "grief", "homenaje",
        "tributo", "familia", "madre", "padre", "hijo", "hija", "vida", "historia",
        "archivo corporal", "marca", "cicatriz", "cuerpo", "body",
    ],
    "aesthetic_design_art": [
        "arte", "art", "artistico", "artístico", "estetica", "estética", "diseño",
        "design", "estilo", "style", "ilustracion", "ilustración", "lienzo",
        "visual", "barberia", "barbería", "estudio", "studio",
    ],
    "craft_work_profession": [
        "oficio", "trabajo", "profesion", "profesión", "tatuador", "tatuadora",
        "tattoo artist", "artista del tatuaje", "cliente", "client", "negocio",
        "business", "estudio de tatuajes", "tattoo studio",
    ],
    "identity_belonging_youth": [
        "identidad", "identity", "pertenencia", "belonging", "juventud", "joven",
        "jovenes", "jóvenes", "genero", "género", "feminista", "religioso",
        "ritual", "prehispanico", "prehispánico", "mexicano", "mexicana",
    ],
    "health_risk_sanitary_regulation": [
        "salud", "health", "riesgo", "risk", "infeccion", "infección", "infection",
        "alergia", "allergy", "tinta", "tintas", "ink", "cofepris", "sanitario",
        "sanitaria", "regulacion", "regulación", "maquillaje permanente",
    ],
    "stigma_discrimination_workplace": [
        "estigma", "stigma", "prejuicio", "prejudice", "discriminacion",
        "discriminación", "empleo", "trabajo", "laboral", "rechazo", "aceptacion",
        "aceptación", "clandestinidad", "clandestino", "clandestina",
    ],
    "media_visibility_pop_culture": [
        "redes", "sociales", "celebridad", "celebrity", "famoso", "famosa",
        "nodal", "messi", "viral", "instagram", "tiktok", "fans", "musica",
        "música", "deporte", "television", "televisión",
    ],
}

NARRATIVE_FRAMES = AI_SOFTWARE_NARRATIVE_FRAMES


def infer_domain_profile(records: list[dict]) -> str:
    haystack = " ".join(
        str(part or "")
        for record in records[:200]
        for part in [
            record.get("query"),
            " ".join(str(item) for item in record.get("query_variants", []) if item),
            record.get("title"),
        ]
    )
    normalized = normalize_token_text(haystack)
    if any(term in normalized for term in ["tatuaje", "tatuajes", "tattoo", "tattoos", "arte corporal", "body art"]):
        return "tattoo"
    if any(term in normalized for term in ["software", "programador", "coding", "copilot", "developer", "inteligencia artificial"]):
        return "ai_software"
    return "generic"


def narrative_frames_for_records(records: list[dict]) -> dict[str, list[str]]:
    profile = infer_domain_profile(records)
    if profile == "tattoo":
        return TATTOO_NARRATIVE_FRAMES
    if profile == "ai_software":
        return AI_SOFTWARE_NARRATIVE_FRAMES
    return {
        "problem_conflict": ["problema", "conflict", "conflicto", "riesgo", "risk", "tension", "tensión"],
        "actor_authority": ["autoridad", "authority", "gobierno", "government", "expert", "experto"],
        "solution_response": ["solucion", "solución", "solution", "respuesta", "response", "medida", "policy"],
        "identity_meaning": ["identidad", "identity", "sentido", "meaning", "memoria", "memory", "cultura", "culture"],
        "change_consequence": ["cambio", "change", "consecuencia", "consequence", "impacto", "impact"],
    }

NARRATIVE_EVENT_PATTERNS = {
    "initial_event": [
        "began", "started", "announced", "reported", "launched", "introduced", "emerged",
        "inició", "inicio", "comenzó", "comenzo", "anunció", "anuncio", "reportó",
        "reporto", "lanzó", "lanzo", "surgió", "surgio", "apareció", "aparecio",
    ],
    "conflict": [
        "conflict", "problem", "issue", "concern", "controversy", "tension", "risk",
        "error", "failure", "dispute", "crisis", "criticism", "challenge",
        "conflicto", "problema", "crítica", "critica", "controversia", "tensión",
        "tension", "riesgo", "error", "fallo", "falla", "disputa", "crisis", "reto",
    ],
    "turning_point": [
        "however", "but", "nevertheless", "nonetheless", "shift", "changed", "after",
        "later", "then", "instead", "despite",
        "sin embargo", "pero", "no obstante", "cambió", "cambio", "después",
        "despues", "luego", "a partir", "en cambio", "pese a",
    ],
    "resolution": [
        "solution", "resolved", "response", "strategy", "measure", "proposal",
        "recommendation", "mitigate", "address", "implemented", "adopted",
        "solución", "solucion", "resolvió", "resolvio", "respuesta", "estrategia",
        "medida", "propuesta", "recomendación", "recomendacion", "mitigar",
        "atender", "implementó", "implemento", "adoptó", "adopto",
    ],
    "consequences": [
        "therefore", "as a result", "consequence", "impact", "effect", "led to",
        "resulted", "outcome", "caused", "increased", "decreased",
        "por lo tanto", "como resultado", "consecuencia", "impacto", "efecto",
        "derivó", "derivo", "provocó", "provoco", "generó", "genero", "resultado",
        "aumentó", "aumento", "disminuyó", "disminuyo",
    ],
}

GENERIC_ACTOR_TERMS = {
    "The", "A", "An", "This", "That", "These", "Those", "In", "On", "For", "With",
    "From", "By", "As", "At", "And", "But", "News", "Article", "Related", "Posts",
    "El", "La", "Los", "Las", "Un", "Una", "En", "Por", "Para", "Con", "Sin",
    "Como", "Este", "Esta", "Estos", "Estas", "Noticias", "Artículo", "Articulo",
    "Relacionados", "También", "Tambien",
    "TV", "DE", "DEL", "LA", "LAS", "LOS", "EL", "UN", "UNA", "EN", "POR", "PARA",
}

ACTOR_NOISE_TERMS = {
    "abstract", "article", "articles", "body", "case", "city", "conclusion", "conclusions",
    "discussion", "english", "figure", "figures", "global", "introduction", "journal",
    "kota", "method", "methods", "objective", "objectives", "results", "source",
    "study", "table", "tattoo", "tattoos", "tatuaje", "tatuajes", "title", "unknown",
    "articulo", "artículos", "articulos", "conclusion", "conclusiones", "discusion",
    "introduccion", "metodo", "metodos", "objetivo", "resultados", "revista",
}

ACTOR_NOISE_PHRASES = {
    "conclusion the", "source journal", "source piel", "source international",
    "global unclear", "area metropolitana", "metropolitan area",
}

ALLOWED_SHORT_ACTORS = {"ai", "ia", "ux", "uam", "unam", "ipn", "hcv", "hiv", "who", "oms"}

AI_SOFTWARE_IDEA_GROUPS = {
    "productivity_promise": [
        "productivity", "productive", "efficiency", "faster", "speed", "time saving",
        "productividad", "eficiencia", "rapidez", "ahorro", "tiempo", "acelera",
    ],
    "human_supervision": [
        "supervision", "supervisory", "oversight", "review", "validate", "verification",
        "supervisión", "supervisar", "validación", "verificación", "revisión", "revisar",
    ],
    "errors_correction_maintenance": [
        "error", "errors", "bug", "bugs", "debug", "fix", "maintenance", "correction",
        "errores", "fallas", "corrección", "corregir", "mantenimiento", "depurar",
    ],
    "security_risk": [
        "security", "vulnerability", "privacy", "risk", "safety", "secure",
        "seguridad", "vulnerabilidad", "privacidad", "riesgo", "riesgos",
    ],
    "architecture_design": [
        "architecture", "design", "system design", "technical debt", "maintainability",
        "arquitectura", "diseño", "deuda técnica", "mantenibilidad",
    ],
    "requirements_problem_framing": [
        "requirements", "specification", "problem definition", "user needs",
        "requisitos", "requerimientos", "especificación", "necesidades", "problema",
    ],
    "ux_users": [
        "user experience", "ux", "interface", "usability", "users",
        "experiencia de usuario", "interfaz", "usabilidad", "usuarios",
    ],
    "trust_accuracy": [
        "trust", "confidence", "reliability", "accuracy", "precision",
        "confianza", "confiabilidad", "precisión", "exactitud",
    ],
    "labor_role_skills": [
        "replace", "replacement", "job", "role", "developer", "engineer", "skills",
        "reemplazar", "sustituir", "trabajo", "rol", "programador", "ingeniero", "habilidades",
    ],
}

TATTOO_IDEA_GROUPS = {
    "bodily_memory_archive": [
        "memoria", "recuerdo", "duelo", "homenaje", "tributo", "cicatriz",
        "archivo corporal", "historia personal", "marca corporal", "memory", "grief",
    ],
    "aesthetic_design_art": [
        "arte", "artistico", "artístico", "estetica", "estética", "diseño",
        "ilustracion", "ilustración", "lienzo", "visual", "body art", "design",
    ],
    "craft_profession_studio": [
        "tatuador", "tatuadora", "oficio", "estudio", "cliente", "negocio",
        "profesion", "profesión", "barberia", "barbería", "tattoo artist", "studio",
    ],
    "identity_belonging_culture": [
        "identidad", "pertenencia", "cultura", "juventud", "genero", "género",
        "ritual", "prehispanico", "prehispánico", "mexicano", "mexicana", "identity",
    ],
    "health_risk_regulation": [
        "salud", "riesgo", "infeccion", "infección", "alergia", "tinta", "tintas",
        "cofepris", "sanitario", "sanitaria", "regulacion", "regulación", "maquillaje permanente",
    ],
    "stigma_discrimination_work": [
        "estigma", "prejuicio", "discriminacion", "discriminación", "empleo",
        "laboral", "rechazo", "aceptacion", "aceptación", "clandestinidad",
    ],
    "media_pop_visibility": [
        "redes", "viral", "celebridad", "famoso", "famosa", "nodal", "messi",
        "instagram", "tiktok", "fans", "musica", "música", "deporte",
    ],
}

IDEA_GROUPS = AI_SOFTWARE_IDEA_GROUPS


def idea_groups_for_records(records: list[dict]) -> dict[str, list[str]]:
    profile = infer_domain_profile(records)
    if profile == "tattoo":
        return TATTOO_IDEA_GROUPS
    if profile == "ai_software":
        return AI_SOFTWARE_IDEA_GROUPS
    return {
        "problem_conflict": ["problema", "conflicto", "riesgo", "tension", "tensión"],
        "actor_authority": ["actor", "autoridad", "gobierno", "experto", "fuente"],
        "solution_response": ["solucion", "solución", "respuesta", "medida", "politica", "política"],
        "identity_meaning": ["identidad", "sentido", "memoria", "cultura", "experiencia"],
        "change_consequence": ["cambio", "consecuencia", "impacto", "efecto", "deriva"],
    }

LP_REFERENCE_CACHE: dict[tuple, dict] = {}
LP_SEED_CACHE: dict[tuple, dict] = {}


def read_record_file(file_path: Path) -> dict | None:
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def load_records_from_path(path: str | Path) -> list[dict]:
    path = Path(path)
    if path.is_dir():
        candidates = [
            path / "news_records.jsonl",
            path / "news_records.json",
            path / "news_records_recleaned.json",
        ]
        for candidate in candidates:
            if candidate.exists():
                records = load_records_from_path(candidate)
                if records:
                    return records
        files = [
            file_path for file_path in sorted(path.glob("**/*.json"))
            if file_path.name not in {"news_records.json", "news_records_recleaned.json"}
        ]
        records = []
        with ThreadPoolExecutor(max_workers=16) as executor:
            futures = [executor.submit(read_record_file, file_path) for file_path in files]
            for future in as_completed(futures):
                try:
                    data = future.result()
                except OSError:
                    continue
                if data:
                    records.append(data)
        records.sort(key=lambda item: (item.get("year") or 0, item.get("medium") or "", item.get("title") or ""))
        return records

    if not path.exists():
        return []
    if path.suffix.lower() == ".jsonl":
        try:
            records = []
            with path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    item = json.loads(line)
                    if isinstance(item, dict):
                        records.append(item)
            return records
        except (OSError, json.JSONDecodeError):
            return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return []


def save_records_json(records: list[dict], output_dir: str | Path) -> None:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "news_records.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with (output_dir / "news_records.jsonl").open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def normalize_token_text(text: str) -> str:
    return (text or "").lower().translate(str.maketrans("áéíóúüñ", "aeiouun"))


def tokenize(text: str, extra_stopwords: Iterable[str] | None = None) -> list[str]:
    text = normalize_token_text(text)
    tokens = re.findall(r"\b[a-z][a-z0-9_-]{2,}\b", text)
    stops = {normalize_token_text(stop).strip() for stop in STOPWORDS}
    stops.update(normalize_token_text(s).strip() for s in (extra_stopwords or []) if s.strip())
    return [token for token in tokens if token not in stops and not token.isnumeric()]


def record_ngrams(
    record: dict,
    n_values: Iterable[int] = (1, 2, 3),
    extra_stopwords: Iterable[str] | None = None,
) -> list[str]:
    tokens = tokenize(record_text(record), extra_stopwords)
    grams: list[str] = []
    for n in n_values:
        if n == 1:
            grams.extend(tokens)
            continue
        grams.extend(" ".join(tokens[i:i + n]) for i in range(0, max(0, len(tokens) - n + 1)))
    return grams


def canonicalize_record_terms(
    record: dict,
    canonical_terms: set[str],
    extra_stopwords: Iterable[str] | None = None,
    max_n: int = 3,
) -> list[str]:
    """Represent a document with repeated canonical phrases before single words.

    This prevents a repeated phrase such as "violencia social" or
    "ai pair programming" from being split into noisy monograms when the graph
    is built. Edges are then created between canonical concepts, not raw tokens.
    """
    tokens = tokenize(record_text(record), extra_stopwords)
    terms: list[str] = []
    i = 0
    while i < len(tokens):
        matched = ""
        remaining = len(tokens) - i
        for n in range(min(max_n, remaining), 1, -1):
            gram = " ".join(tokens[i:i + n])
            if gram in canonical_terms:
                matched = gram
                i += n
                break
        if matched:
            terms.append(matched)
            continue
        token = tokens[i]
        if token in canonical_terms:
            terms.append(token)
        i += 1
    return terms


def phrase_contains(short: str, long: str) -> bool:
    short_tokens = short.split()
    long_tokens = long.split()
    if len(short_tokens) >= len(long_tokens):
        return False
    return any(long_tokens[i:i + len(short_tokens)] == short_tokens for i in range(0, len(long_tokens) - len(short_tokens) + 1))


def normalize_numeric_values(values: Iterable[float]) -> dict[float, float]:
    values_list = [float(value or 0) for value in values]
    if not values_list:
        return {}
    max_value = max(values_list)
    if max_value <= 0:
        return {value: 0.0 for value in values_list}
    return {value: round(value / max_value, 6) for value in values_list}


def add_normalized_graph_weights(nodes: list[dict], edges: list[dict], node_count_field: str = "count") -> None:
    """Attach [0,1] weights without destroying raw count weights.

    Raw weights remain as counts because they are the reproducible evidence.
    Normalized weights are added for comparisons, diagnostics and optimization.
    """
    max_edge_weight = max([float(edge.get("weight", 0) or 0) for edge in edges] or [0.0])
    for edge in edges:
        raw = float(edge.get("weight", 0) or 0)
        edge["raw_weight"] = raw
        edge["weight_norm"] = round(raw / max_edge_weight, 6) if max_edge_weight > 0 else 0.0
        edge["weight"] = edge["weight_norm"]

    max_count = max([float(node.get(node_count_field, 0) or 0) for node in nodes] or [0.0])
    max_wdegree = max([float(node.get("weighted_degree_raw", node.get("weighted_degree", 0)) or 0) for node in nodes] or [0.0])
    for node in nodes:
        count_raw = float(node.get(node_count_field, 0) or 0)
        wdegree_raw = float(node.get("weighted_degree_raw", node.get("weighted_degree", 0)) or 0)
        node["raw_count"] = count_raw
        node["count_norm"] = round(count_raw / max_count, 6) if max_count > 0 else 0.0
        node["weighted_degree_norm"] = round(wdegree_raw / max_wdegree, 6) if max_wdegree > 0 else 0.0
        node["weight_norm"] = round((node["count_norm"] + node["weighted_degree_norm"]) / 2, 6)
        node["score"] = node["weight_norm"]


def graph_weight_distribution_stats(nodes: list[dict], edges: list[dict]) -> dict:
    edge_weights = sorted(float(edge.get("weight_norm", edge.get("weight", 0)) or 0) for edge in edges)
    node_weights = sorted(float(node.get("weight_norm", 0) or 0) for node in nodes)
    degrees = sorted(float(node.get("degree", 0) or 0) for node in nodes)

    def mean(values: list[float]) -> float:
        return sum(values) / max(1, len(values))

    def variance(values: list[float]) -> float:
        mu = mean(values)
        return sum((value - mu) ** 2 for value in values) / max(1, len(values))

    def quantile(values: list[float], q: float) -> float:
        if not values:
            return 0.0
        idx = min(len(values) - 1, max(0, round((len(values) - 1) * q)))
        return values[idx]

    def concentration(values: list[float]) -> float:
        total = sum(values)
        if total <= 0:
            return 0.0
        top = sorted(values, reverse=True)[: max(1, math.ceil(len(values) * 0.1))]
        return sum(top) / total

    degree_var = variance(degrees)
    degree_mean = mean(degrees)
    edge_concentration = concentration(edge_weights)
    if len(nodes) < 3 or not edges:
        network_type = "insufficient_data"
    elif degree_mean > 0 and degree_var / max(degree_mean, 1e-9) > 2.5:
        network_type = "heterogeneous_or_hub_dominated"
    elif edge_concentration > 0.55:
        network_type = "weight_concentrated"
    else:
        network_type = "relatively_homogeneous"
    return {
        "edge_weight_min": round(edge_weights[0], 6) if edge_weights else 0.0,
        "edge_weight_max": round(edge_weights[-1], 6) if edge_weights else 0.0,
        "edge_weight_mean": round(mean(edge_weights), 6),
        "edge_weight_variance": round(variance(edge_weights), 6),
        "edge_weight_q25": round(quantile(edge_weights, 0.25), 6),
        "edge_weight_q50": round(quantile(edge_weights, 0.50), 6),
        "edge_weight_q75": round(quantile(edge_weights, 0.75), 6),
        "node_weight_mean": round(mean(node_weights), 6),
        "node_weight_variance": round(variance(node_weights), 6),
        "degree_mean": round(degree_mean, 6),
        "degree_variance": round(degree_var, 6),
        "top_10pct_edge_weight_share": round(edge_concentration, 6),
        "network_type_diagnostic": network_type,
    }


def compose_repeated_phrases(
    records: list[dict],
    top_n_each: int = 30,
    min_count: int = 2,
    extra_stopwords: Iterable[str] | None = None,
    absorption_ratio: float = 0.8,
) -> list[dict]:
    """Build canonical phrase nodes and mark smaller n-grams absorbed by phrases.

    A monogram/bigram is not discarded blindly. It is absorbed only when most of
    its appearances are explained by a repeated longer phrase.
    """
    unigram_counts = Counter()
    bigram_counts = Counter()
    trigram_counts = Counter()
    for record in records:
        tokens = tokenize(record_text(record), extra_stopwords)
        unigram_counts.update(tokens)
        bigram_counts.update(" ".join(tokens[i:i + 2]) for i in range(0, max(0, len(tokens) - 1)))
        trigram_counts.update(" ".join(tokens[i:i + 3]) for i in range(0, max(0, len(tokens) - 2)))

    rows: list[dict] = []
    phrase_rows = []
    for phrase, count in trigram_counts.most_common(top_n_each):
        if count >= min_count:
            phrase_rows.append({"node": phrase, "node_type": "trigram", "count": count, "absorbed_by": ""})
    for phrase, count in bigram_counts.most_common(top_n_each):
        if count >= min_count:
            phrase_rows.append({"node": phrase, "node_type": "bigram", "count": count, "absorbed_by": ""})

    canonical_phrases = sorted(phrase_rows, key=lambda row: (len(row["node"].split()), row["count"]), reverse=True)
    rows.extend(canonical_phrases)

    absorbed: dict[str, str] = {}
    for small_counts in [bigram_counts, unigram_counts]:
        for small, small_count in small_counts.items():
            if small_count < min_count:
                continue
            for phrase_row in canonical_phrases:
                phrase = phrase_row["node"]
                if phrase_contains(small, phrase) and phrase_row["count"] / max(1, small_count) >= absorption_ratio:
                    absorbed[small] = phrase
                    break

    for term, count in unigram_counts.most_common(top_n_each):
        if count >= min_count and term not in absorbed:
            rows.append({"node": term, "node_type": "monogram", "count": count, "absorbed_by": ""})
    for gram, count in bigram_counts.most_common(top_n_each):
        if count >= min_count and gram not in absorbed and not any(row["node"] == gram for row in rows):
            rows.append({"node": gram, "node_type": "bigram", "count": count, "absorbed_by": ""})
    for gram, phrase in absorbed.items():
        if gram in unigram_counts or gram in bigram_counts:
            rows.append({
                "node": gram,
                "node_type": "absorbed_ngram",
                "count": unigram_counts.get(gram, bigram_counts.get(gram, 0)),
                "absorbed_by": phrase,
            })
    return sorted(rows, key=lambda row: (row["node_type"] == "absorbed_ngram", -row["count"], row["node"]))


MIN_PARTIAL_ANALYSIS_TEXT_CHARS = 100


def record_has_usable_text(record: dict) -> bool:
    status = str(record.get("status") or "")
    text = str(record.get("text_normalized") or record.get("text_clean") or "")
    if status == "ok":
        return bool(text)
    if status == "ok_partial":
        try:
            text_length = int(record.get("text_length") or 0)
        except (TypeError, ValueError):
            text_length = len(text)
        return len(text) >= MIN_PARTIAL_ANALYSIS_TEXT_CHARS or text_length >= MIN_PARTIAL_ANALYSIS_TEXT_CHARS
    return False


def usable_records(records: list[dict]) -> list[dict]:
    return [record for record in records if record_has_usable_text(record)]


def record_text(record: dict) -> str:
    return record.get("text_normalized") or record.get("text_clean") or record.get("title") or ""


def normalize_label(value: str) -> str:
    return (value or "").strip() or "unknown"


def row_language(record: dict) -> str:
    value = normalize_label(record.get("language", "unknown"))
    lower = value.lower()
    if lower.startswith("spanish") or lower in {"es", "spa"}:
        return "Spanish"
    if lower.startswith("english") or lower in {"en", "eng"}:
        return "English"
    return value


def localization_signal(record: dict) -> dict:
    medium = (record.get("medium") or "").lower()
    country = (record.get("country") or "").lower()
    scope = (record.get("geographic_scope") or "").lower()
    geo_terms = " ".join(record.get("geographic_terms") or []).lower()
    text = f"{record.get('title','')} {record_text(record)[:5000]}".lower()
    normalized = text.translate(str.maketrans("áéíóúüñ", "aeiouun"))

    evidence = []
    score = 0
    if country in {"mx", "mexico", "méxico"}:
        score += 4
        evidence.append("source_country_mx")
    if medium.endswith(".mx") or ".com.mx" in medium or ".gob.mx" in medium or ".edu.mx" in medium:
        score += 4
        evidence.append("mexican_domain")
    if "mexico" in scope or "méxico" in scope or "mexico" in geo_terms or "méxico" in geo_terms:
        score += 2
        evidence.append("declared_mexico_scope")
    mexico_hits = sum(1 for term in MEXICO_TERMS if term in text or term in normalized)
    if mexico_hits:
        score += min(3, mexico_hits)
        evidence.append(f"mexico_text_mentions:{mexico_hits}")
    latam_hits = sum(1 for term in LATAM_TERMS if term in text or term in normalized)
    if latam_hits and not mexico_hits:
        score += 1
        evidence.append(f"latam_text_mentions:{latam_hits}")

    if score >= 5:
        label = "Mexico-focused"
    elif score >= 2:
        label = "Mexico-mentioned"
    elif latam_hits:
        label = "Latin-America-mentioned"
    else:
        label = "Global/unclear"
    return {"localization": label, "mexico_score": score, "localization_evidence": ", ".join(evidence)}


def narrative_flow_stage(source_type: str) -> dict:
    """Analytical flow: individual dialogue tends to precede news, then research.

    This is not a weight. It is a layer for stratified analysis because the
    direction can feed back: research and news also reshape later dialogue.
    """
    source_type = (source_type or "other").strip().lower()
    mapping = {
        "forum": (1, "individual_dialogue"),
        "news": (2, "news_media"),
        "institutional_report": (3, "institutional_authority"),
        "industry_report": (4, "technical_or_industry_derivation"),
        "scientific_article": (5, "research"),
        "other": (6, "other_or_unclear_derivation"),
    }
    order, label = mapping.get(source_type, mapping["other"])
    return {"narrative_flow_order": order, "narrative_flow_stage": label}


def enrich_records_for_analysis(records: list[dict]) -> list[dict]:
    enriched = []
    for record in records:
        row = dict(record)
        if not row.get("source_type"):
            row["source_type"] = "other"
        row["analysis_language"] = row_language(row)
        row.update(narrative_flow_stage(row.get("source_type") or "other"))
        row.update(localization_signal(row))
        enriched.append(row)
    return enriched


def filter_records(
    records: list[dict],
    source_types: list[str] | None = None,
    years: list[int] | None = None,
    media: list[str] | None = None,
    languages: list[str] | None = None,
    localizations: list[str] | None = None,
) -> list[dict]:
    rows = enrich_records_for_analysis(usable_records(records))
    if source_types:
        rows = [row for row in rows if (row.get("source_type") or "other") in source_types]
    if years:
        year_set = {int(year) for year in years}
        rows = [row for row in rows if int(row.get("year", 0) or 0) in year_set]
    if media:
        media_set = set(media)
        rows = [row for row in rows if (row.get("medium") or "unknown") in media_set]
    if languages:
        language_set = set(languages)
        rows = [row for row in rows if row.get("analysis_language", "unknown") in language_set]
    if localizations:
        localization_set = set(localizations)
        rows = [row for row in rows if row.get("localization", "Global/unclear") in localization_set]
    return rows


def count_rows(records: list[dict], fields: list[str]) -> list[dict]:
    counts = Counter(tuple(record.get(field, "unknown") for field in fields) for record in records)
    rows = []
    for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        row = {field: value for field, value in zip(fields, key)}
        row["records"] = count
        rows.append(row)
    return rows


def stopword_candidates(records: list[dict], top_n: int = 50) -> list[dict]:
    raw_counts: Counter[str] = Counter()
    filtered_counts: Counter[str] = Counter()
    for record in records:
        text = record_text(record).lower()
        text = text.translate(str.maketrans("áéíóúüñ", "aeiouun"))
        raw_tokens = re.findall(r"\b[a-z][a-z0-9_-]{2,}\b", text)
        raw_counts.update(raw_tokens)
        filtered_counts.update(tokenize(text))
    candidates = []
    for token, count in raw_counts.most_common(top_n * 3):
        if token in STOPWORDS:
            continue
        filtered = filtered_counts.get(token, 0)
        if count >= 3:
            candidates.append(
                {
                    "term": token,
                    "raw_count": count,
                    "after_stopwords_count": filtered,
                    "suggestion": "consider_as_stopword" if filtered >= 3 else "already_removed_or_rare",
                }
            )
        if len(candidates) >= top_n:
            break
    return candidates


def corpus_tokens(records: list[dict], extra_stopwords: Iterable[str] | None = None) -> list[str]:
    tokens: list[str] = []
    for record in records:
        tokens.extend(tokenize(record_text(record), extra_stopwords))
    return tokens


def top_terms(records: list[dict], top_n: int = 30, extra_stopwords: Iterable[str] | None = None) -> list[dict]:
    counts = Counter(corpus_tokens(records, extra_stopwords))
    return [{"term": term, "count": count} for term, count in counts.most_common(top_n)]


def top_ngrams(
    records: list[dict],
    n: int = 2,
    top_n: int = 30,
    min_count: int = 2,
    extra_stopwords: Iterable[str] | None = None,
) -> list[dict]:
    counts: Counter[str] = Counter()
    for record in records:
        tokens = tokenize(record_text(record), extra_stopwords)
        for i in range(0, max(0, len(tokens) - n + 1)):
            counts[" ".join(tokens[i:i + n])] += 1
    return [
        {"ngram": gram, "count": count}
        for gram, count in counts.most_common(top_n)
        if count >= min_count
    ]


def top_mixed_ngrams(
    records: list[dict],
    top_n_each: int = 30,
    min_count: int = 2,
    extra_stopwords: Iterable[str] | None = None,
) -> list[dict]:
    return compose_repeated_phrases(records, top_n_each, min_count, extra_stopwords)


def frame_counts(records: list[dict]) -> list[dict]:
    total_docs = max(1, len(records))
    rows = []
    for frame, keywords in narrative_frames_for_records(records).items():
        keyword_hits = 0
        doc_hits = 0
        matched_terms = Counter()
        for record in records:
            text = record_text(record).lower()
            local_hit = False
            for keyword in keywords:
                pattern = re.escape(keyword.lower())
                count = len(re.findall(rf"\b{pattern}\b", text))
                if count:
                    keyword_hits += count
                    matched_terms[keyword] += count
                    local_hit = True
            if local_hit:
                doc_hits += 1
        rows.append(
            {
                "frame": frame,
                "keyword_hits": keyword_hits,
                "documents_with_frame": doc_hits,
                "document_share": round(doc_hits / total_docs, 4),
                "top_terms": ", ".join(term for term, _ in matched_terms.most_common(5)),
            }
        )
    return sorted(rows, key=lambda row: row["keyword_hits"], reverse=True)


def split_sentences(text: str, max_sentences: int = 80) -> list[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?¿¡])\s+(?=[A-ZÁÉÍÓÚÑ0-9¿¡])", text)
    clean = []
    for sentence in sentences:
        sentence = sentence.strip(" \t\r\n")
        if 45 <= len(sentence) <= 500:
            clean.append(sentence)
        if len(clean) >= max_sentences:
            break
    return clean


def match_event_sentence(sentences: list[str], patterns: list[str]) -> tuple[str, str]:
    scored: list[tuple[int, int, str, list[str]]] = []
    for index, sentence in enumerate(sentences):
        lower = sentence.lower()
        markers = [pattern for pattern in patterns if re.search(rf"\b{re.escape(pattern.lower())}\b", lower)]
        if markers:
            scored.append((len(markers), -index, sentence, markers[:6]))
    if not scored:
        return "", ""
    scored.sort(reverse=True)
    _, _, sentence, markers = scored[0]
    return sentence, ", ".join(markers)


def actor_candidate_is_noise(value: str, extra_stopwords: Iterable[str] | None = None) -> bool:
    stripped = re.sub(r"\s+", " ", value or "").strip()
    if not stripped:
        return True
    normalized = normalize_token_text(stripped)
    normalized = re.sub(r"[^a-z0-9\s:_-]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if normalized.startswith("source:") or normalized.startswith("source "):
        return True
    if normalized in ACTOR_NOISE_TERMS or normalized in ACTOR_NOISE_PHRASES:
        return True
    if any(phrase in normalized for phrase in ACTOR_NOISE_PHRASES):
        return True
    if stripped in GENERIC_ACTOR_TERMS:
        return True
    meaningful = tokenize(stripped, extra_stopwords)
    if not meaningful and normalized not in ALLOWED_SHORT_ACTORS:
        return True
    if any(token in ACTOR_NOISE_TERMS for token in meaningful):
        return True
    if len(meaningful) == 1 and meaningful[0] not in ALLOWED_SHORT_ACTORS:
        return True
    if len(meaningful) == 1 and meaningful[0] in {"source", "unknown", "global", "unclear"}:
        return True
    if stripped.isupper() and normalized not in ALLOWED_SHORT_ACTORS and len(stripped) <= 8:
        return True
    return False


def extract_actors(record: dict, max_actors: int = 10, extra_stopwords: Iterable[str] | None = None) -> str:
    text = f"{record.get('title', '')}. {record.get('text_clean') or ''}"
    candidates = Counter()

    acronym_pattern = r"\b[A-ZÁÉÍÓÚÑ]{2,}(?:-[A-ZÁÉÍÓÚÑ0-9]+)?\b"
    name_pattern = (
        r"\b[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ0-9&\-]+"
        r"(?:\s+(?:de|del|la|las|los|y|e|and|of|the|for|to|in)?\s*"
        r"[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ0-9&\-]+){1,5}\b"
    )
    for match in re.findall(acronym_pattern, text):
        if not actor_candidate_is_noise(match, extra_stopwords):
            candidates[match] += 2
    for match in re.findall(name_pattern, text):
        value = re.sub(r"\s+", " ", match).strip()
        parts = [part.strip() for part in re.split(r"\s+(?:and|y|e)\s+", value) if part.strip()]
        for part in parts:
            first = part.split()[0]
            if first in GENERIC_ACTOR_TERMS:
                continue
            if len(part) < 4 or len(part) > 90:
                continue
            if actor_candidate_is_noise(part, extra_stopwords):
                continue
            candidates[part] += 1

    return ", ".join(actor for actor, _ in candidates.most_common(max_actors))


def extract_situation_context(record: dict) -> str:
    parts = [
        f"year={record.get('year') or 'unknown'}",
        f"source={record.get('medium') or 'unknown'}",
        f"type={record.get('source_type') or 'other'}",
        f"flow={record.get('narrative_flow_stage') or narrative_flow_stage(record.get('source_type') or 'other')['narrative_flow_stage']}",
        f"language={record.get('analysis_language') or row_language(record)}",
        f"localization={record.get('localization') or localization_signal(record).get('localization')}",
    ]
    scope = record.get("geographic_scope")
    if scope:
        parts.append(f"scope={scope}")
    return "; ".join(parts)


def extract_narrative_events(records: list[dict], extra_stopwords: Iterable[str] | None = None) -> list[dict]:
    rows = []
    for index, record in enumerate(records, start=1):
        text = f"{record.get('title', '')}. {record_text(record)}"
        sentences = split_sentences(text)
        event_values = {}
        present = 0
        for stage, patterns in NARRATIVE_EVENT_PATTERNS.items():
            sentence, markers = match_event_sentence(sentences, patterns)
            event_values[stage] = sentence
            event_values[f"{stage}_markers"] = markers
            if sentence:
                present += 1

        rows.append(
            {
                "doc_id": index,
                "doc_key": record.get("url") or f"{record.get('year')}|{record.get('medium')}|{record.get('title')}",
                "year": record.get("year"),
                "medium": record.get("medium"),
                "source_type": record.get("source_type") or "other",
                "narrative_flow_order": record.get("narrative_flow_order") or narrative_flow_stage(record.get("source_type") or "other")["narrative_flow_order"],
                "narrative_flow_stage": record.get("narrative_flow_stage") or narrative_flow_stage(record.get("source_type") or "other")["narrative_flow_stage"],
                "language": record.get("analysis_language") or row_language(record),
                "localization": record.get("localization") or localization_signal(record).get("localization"),
                "title": record.get("title", ""),
                "actors": extract_actors(record, extra_stopwords=extra_stopwords),
                "situation_context": extract_situation_context(record),
                **event_values,
                "narrative_completeness": round(present / len(NARRATIVE_EVENT_PATTERNS), 3),
                "stages_detected": present,
                "url": record.get("url", ""),
            }
        )
    return rows


def narrative_event_summary(event_rows: list[dict]) -> list[dict]:
    total = max(1, len(event_rows))
    rows = []
    labels = {
        "initial_event": "evento inicial",
        "conflict": "conflicto",
        "turning_point": "punto de cambio",
        "resolution": "resolución",
        "consequences": "consecuencias",
    }
    for stage, label in labels.items():
        docs = sum(1 for row in event_rows if row.get(stage))
        rows.append(
            {
                "narrative_stage": label,
                "documents_with_stage": docs,
                "document_share": round(docs / total, 4),
            }
        )
    return rows


def actor_counts(event_rows: list[dict], top_n: int = 50) -> list[dict]:
    counts = Counter()
    for row in event_rows:
        for actor in (row.get("actors") or "").split(","):
            actor = actor.strip()
            if actor:
                counts[actor] += 1
    return [{"actor": actor, "documents": count} for actor, count in counts.most_common(top_n)]


def build_narrative_event_graph(
    event_rows: list[dict],
    min_edge_weight: int = 1,
    max_actors_per_doc: int = 8,
    weighting_mode: str = "neutral",
) -> dict:
    """Build a weighted narrative graph from extracted event structure.

    weighting_mode="neutral" is the methodological default: narrative elements
    start with equal contribution and centrality emerges from observed
    frequency/connectivity, not from an imposed hierarchy among stages, actors,
    documents, sources or metadata.
    """
    stage_labels = {
        "initial_event": "evento inicial",
        "conflict": "conflicto",
        "turning_point": "punto de cambio",
        "resolution": "resolución",
        "consequences": "consecuencias",
    }
    nodes: dict[str, dict] = {}
    edge_counts: Counter[tuple[str, str, str]] = Counter()
    weighting_mode = weighting_mode if weighting_mode in {"neutral", "completeness_stage_emphasis"} else "neutral"

    def document_weight(row: dict) -> float:
        if weighting_mode == "completeness_stage_emphasis":
            return 1.0 + float(row.get("narrative_completeness", 0) or 0)
        return 1.0

    def stage_weight() -> float:
        return 2.0 if weighting_mode == "completeness_stage_emphasis" else 1.0

    def stage_edge_weight() -> float:
        return 2.0 if weighting_mode == "completeness_stage_emphasis" else 1.0

    def add_node(node_id: str, label: str, node_type: str, weight: float = 1.0) -> None:
        if node_id not in nodes:
            nodes[node_id] = {"id": node_id, "term": node_id, "label": label, "node_type": node_type, "weight": 0.0}
        nodes[node_id]["weight"] += weight

    def add_edge(source: str, target: str, edge_type: str, weight: float = 1.0) -> None:
        if source == target:
            return
        a, b = sorted((source, target))
        edge_counts[(a, b, edge_type)] += weight

    for row in event_rows:
        doc_id = f"doc::{row.get('doc_id')}"
        title = row.get("title") or f"Documento {row.get('doc_id')}"
        add_node(doc_id, title[:120], "document", document_weight(row))

        source_id = f"source::{row.get('medium') or 'unknown'}"
        year_id = f"year::{row.get('year') or 'unknown'}"
        geo_id = f"geo::{row.get('localization') or 'unknown'}"
        type_id = f"type::{row.get('source_type') or 'other'}"
        flow_stage = row.get("narrative_flow_stage") or narrative_flow_stage(row.get("source_type") or "other")["narrative_flow_stage"]
        flow_id = f"flow::{flow_stage}"
        add_node(source_id, str(row.get("medium") or "unknown"), "source")
        add_node(year_id, str(row.get("year") or "unknown"), "year")
        add_node(geo_id, str(row.get("localization") or "unknown"), "localization")
        add_node(type_id, str(row.get("source_type") or "other"), "source_type")
        add_node(flow_id, str(flow_stage), "narrative_flow")
        add_edge(doc_id, source_id, "document_source")
        add_edge(doc_id, year_id, "document_year")
        add_edge(doc_id, geo_id, "document_localization")
        add_edge(doc_id, type_id, "document_source_type")
        add_edge(doc_id, flow_id, "document_flow")

        present_stages = []
        for stage, label in stage_labels.items():
            if row.get(stage):
                stage_id = f"stage::{stage}"
                add_node(stage_id, label, "narrative_stage", stage_weight())
                add_edge(doc_id, stage_id, "document_stage", stage_edge_weight())
                add_edge(source_id, stage_id, "source_stage")
                add_edge(year_id, stage_id, "year_stage")
                add_edge(geo_id, stage_id, "geo_stage")
                add_edge(type_id, stage_id, "type_stage")
                add_edge(flow_id, stage_id, "flow_stage")
                present_stages.append(stage_id)

        actor_ids = []
        for actor in [item.strip() for item in (row.get("actors") or "").split(",") if item.strip()][:max_actors_per_doc]:
            actor_id = f"actor::{actor}"
            actor_ids.append(actor_id)
            add_node(actor_id, actor.replace("source:", ""), "actor")
            add_edge(doc_id, actor_id, "document_actor")
            for stage_id in present_stages:
                add_edge(actor_id, stage_id, "actor_stage")

        for a, b in combinations(actor_ids, 2):
            add_edge(a, b, "actor_co_document")
        for a, b in combinations(present_stages, 2):
            add_edge(a, b, "stage_co_document")

    edges = [
        {"source": source, "target": target, "edge_type": edge_type, "weight": round(weight, 3)}
        for (source, target, edge_type), weight in edge_counts.items()
        if weight >= min_edge_weight
    ]
    weighted_degree = Counter()
    degree = Counter()
    for edge in edges:
        weighted_degree[edge["source"]] += edge["weight"]
        weighted_degree[edge["target"]] += edge["weight"]
        degree[edge["source"]] += 1
        degree[edge["target"]] += 1

    node_rows = []
    for node in nodes.values():
        node["degree"] = degree[node["id"]]
        node["weighted_degree_raw"] = round(weighted_degree[node["id"]], 3)
        node["weighted_degree"] = node["weighted_degree_raw"]
        node["raw_count"] = round(float(node.get("weight", 0) or 0), 3)
        node["score"] = round(node["raw_count"] + node["weighted_degree_raw"], 3)
        if node["degree"] > 0:
            node_rows.append(node)
    add_normalized_graph_weights(node_rows, edges, node_count_field="raw_count")
    node_rows.sort(key=lambda item: (item["score"], item["weighted_degree"]), reverse=True)
    communities = connected_components(
        [{"term": node["id"]} for node in node_rows],
        [{"source": edge["source"], "target": edge["target"], "weight": edge["weight"]} for edge in edges],
    )
    node_count = len(node_rows)
    edge_count = len(edges)
    density = 0 if node_count < 2 else round((2 * edge_count) / (node_count * (node_count - 1)), 5)
    return {
        "nodes": node_rows,
        "edges": sorted(edges, key=lambda row: row["weight"], reverse=True),
        "communities": communities,
        "stats": {
            "nodes": node_count,
            "edges": edge_count,
            "density": density,
            "communities": len(communities),
            "total_edge_weight": round(sum(edge["weight"] for edge in edges), 3),
            "total_raw_edge_weight": round(sum(edge.get("raw_weight", 0) for edge in edges), 3),
            "weighting_mode": weighting_mode,
            **graph_weight_distribution_stats(node_rows, edges),
        },
    }


def greedy_weighted_node_cover(
    graph: dict,
    max_nodes: int = 20,
    allowed_node_types: Iterable[str] | None = None,
    edge_types: Iterable[str] | None = None,
    objective: str = "maximize_edge_weight",
    coverage_mode: str = "removal_impact",
    node_weight: float = 1.0,
    edge_cost_weight: float = 1.0,
    coverage_weight: float = 0.2,
) -> dict:
    """Greedy constructive heuristic for the same weighted node-cover problem.

    coverage_mode="removal_impact" evaluates the weight of edges that would be
    deleted if the selected covering nodes were removed from the graph.
    """
    problem = _cover_problem_data(graph, allowed_node_types, edge_types, coverage_mode=coverage_mode)
    nodes = problem["nodes"]
    allowed_ids = set(problem["candidates"])
    edges = problem["edges"]
    total_weight = problem["total_edge_weight"]
    selected_ids: list[str] = []
    selected = []
    current_eval = _evaluate_cover_solution(
        selected_ids,
        problem,
        max_nodes=max_nodes,
        node_weight=node_weight,
        edge_cost_weight=edge_cost_weight,
        coverage_weight=coverage_weight,
    )
    while len(selected_ids) < max_nodes:
        best_id = ""
        best_value = -math.inf
        best_eval = None
        for node_id in allowed_ids:
            if node_id in selected_ids:
                continue
            candidate_eval = _evaluate_cover_solution(
                [*selected_ids, node_id],
                problem,
                max_nodes=max_nodes,
                node_weight=node_weight,
                edge_cost_weight=edge_cost_weight,
                coverage_weight=coverage_weight,
            )
            value = candidate_eval["objective_value"]
            if value > best_value:
                best_id = node_id
                best_value = value
                best_eval = candidate_eval
        if not best_id:
            break
        if selected_ids and best_eval and best_eval["objective_value"] <= current_eval["objective_value"]:
            break
        previous_eval = current_eval
        selected_ids.append(best_id)
        current_eval = best_eval or _evaluate_cover_solution(
            selected_ids,
            problem,
            max_nodes=max_nodes,
            node_weight=node_weight,
            edge_cost_weight=edge_cost_weight,
            coverage_weight=coverage_weight,
        )
        node = nodes[best_id]
        selected.append(
            {
                "rank": len(selected) + 1,
                "node_id": best_id,
                "label": node.get("label", best_id),
                "node_type": node.get("node_type"),
                "node_score": node.get("score", 0),
                "marginal_edges_removed": current_eval["removed_edges"] - previous_eval["removed_edges"],
                "marginal_weight_removed": round(current_eval["removed_edge_weight"] - previous_eval["removed_edge_weight"], 3),
                "marginal_edges_covered": current_eval["covered_edges"] - previous_eval["covered_edges"],
                "marginal_weight_covered": round(current_eval["covered_edge_weight"] - previous_eval["covered_edge_weight"], 3),
                "selection_objective_value": round(best_value, 5),
                "cumulative_weight_covered": round(current_eval["covered_edge_weight"], 3),
                "cumulative_weight_share": round(current_eval["covered_weight_share"], 4),
                "cumulative_node_score": round(current_eval["selected_node_score"], 3),
                "node_score_to_edge_weight": round(current_eval["selected_node_score"] / max(1.0, current_eval["covered_edge_weight"]), 5),
            }
        )
    prefix_evaluations = [
        _evaluate_cover_solution(
            [row["node_id"] for row in selected[:index]],
            problem,
            max_nodes=max_nodes,
            node_weight=node_weight,
            edge_cost_weight=edge_cost_weight,
            coverage_weight=coverage_weight,
        )
        for index in range(1, len(selected) + 1)
    ]
    pareto_front = pareto_front_from_evaluations(prefix_evaluations)
    hypervolume = approximate_hypervolume(prefix_evaluations, problem, max_nodes) if prefix_evaluations else 0.0
    return {
        "selected_nodes": selected,
        "stats": {
            "method": "greedy",
            "objective": "node_selector_multiobjective_scp_inspired",
            "coverage_mode": coverage_mode,
            "node_weight": node_weight,
            "edge_cost_weight": edge_cost_weight,
            "coverage_weight": coverage_weight,
            "selected_nodes": len(selected),
            "total_candidate_nodes": len(problem["candidates"]),
            "candidate_edges": len(edges),
            "covered_edges": current_eval["covered_edges"],
            "uncovered_edges": current_eval["removed_edges"],
            "preserved_edges": current_eval["preserved_edges"],
            "total_edge_weight": round(total_weight, 3),
            "covered_edge_weight": round(current_eval["covered_edge_weight"], 3),
            "preserved_edge_weight": round(current_eval["preserved_edge_weight"], 3),
            "covered_weight_share": round(current_eval["covered_weight_share"], 4),
            "preserved_weight_share": round(current_eval["preserved_edge_weight_share"], 4),
            "selected_node_score": round(current_eval["selected_node_score"], 3),
            "nodes_ratio": round(current_eval["selected_node_share"], 5),
            "node_weight_ratio": round(current_eval["selected_node_weight_share"], 5),
            "removed_edge_weight_ratio": round(current_eval["removed_edge_weight_share"], 5),
            "node_score_to_edge_weight": round(current_eval["selected_node_score"] / max(1.0, current_eval["covered_edge_weight"]), 5),
            "hypervolume": round(hypervolume, 5),
            "pareto_solutions": len(pareto_front),
        },
        "pareto_front": pareto_front,
    }


def _cover_problem_data(
    graph: dict,
    allowed_node_types: Iterable[str] | None = None,
    edge_types: Iterable[str] | None = None,
    coverage_mode: str = "removal_impact",
) -> dict:
    nodes = {node["id"]: node for node in graph.get("nodes", [])}
    allowed = set(allowed_node_types or [])
    wanted_edge_types = set(edge_types or [])
    candidates = [
        node_id for node_id, node in nodes.items()
        if not allowed or node.get("node_type") in allowed
    ]
    edges = [
        {**edge, "edge_id": index}
        for index, edge in enumerate(graph.get("edges", []))
        if (not wanted_edge_types or edge.get("edge_type") in wanted_edge_types)
    ]
    edge_by_id = {edge["edge_id"]: edge for edge in edges}
    incident: dict[str, set[int]] = defaultdict(set)
    for edge in edges:
        if edge["source"] in candidates:
            incident[edge["source"]].add(edge["edge_id"])
        if edge["target"] in candidates:
            incident[edge["target"]].add(edge["edge_id"])
    return {
        "nodes": nodes,
        "candidates": candidates,
        "edges": edges,
        "edge_by_id": edge_by_id,
        "incident": incident,
        "coverage_mode": coverage_mode,
        "total_nodes": len(candidates) or 1,
        "total_node_weight": sum(float(nodes[node_id].get("score", 0) or 0) for node_id in candidates) or 1.0,
        "total_edge_weight": sum(float(edge.get("weight", 1) or 1) for edge in edges) or 1.0,
    }


def _evaluate_cover_solution(
    selected_ids: Iterable[str],
    problem: dict,
    max_nodes: int | None = None,
    min_nodes: int = 1,
    min_node_weight_share: float = 0.0,
    max_removed_edge_weight_share: float = 1.0,
    node_weight: float = 1.0,
    edge_cost_weight: float = 1.0,
    coverage_weight: float = 0.2,
    size_penalty: float = 0.05,
) -> dict:
    raw_selected = [str(node_id) for node_id in selected_ids if str(node_id)]
    selected = list(dict.fromkeys(raw_selected))
    selected_set = set(selected)
    candidates = set(problem.get("candidates", []))
    invalid_count = sum(1 for node_id in selected if node_id not in candidates)
    duplicate_count = max(0, len(raw_selected) - len(selected))
    max_nodes_value = max_nodes if max_nodes is not None else problem.get("max_nodes")
    max_nodes_value = int(max_nodes_value or max(1, len(candidates)))
    min_nodes_value = int(min_nodes or 0)
    size = len([node_id for node_id in selected if node_id in candidates])
    selected = [node_id for node_id in selected if node_id in candidates]
    selected_set = set(selected)
    all_edge_ids = set(problem["edge_by_id"])
    mode = problem.get("coverage_mode")
    if mode == "removal_impact":
        removed_edge_ids = set()
        for node_id in selected:
            removed_edge_ids.update(problem["incident"].get(node_id, set()))
        covered_edges = all_edge_ids - removed_edge_ids
    elif mode == "incident":
        covered_edges = set()
        for node_id in selected:
            covered_edges.update(problem["incident"].get(node_id, set()))
        removed_edge_ids = all_edge_ids - covered_edges
    else:
        covered_edges = {
            edge["edge_id"]
            for edge in problem["edges"]
            if edge.get("source") in selected_set and edge.get("target") in selected_set
        }
        removed_edge_ids = all_edge_ids - covered_edges
    covered_edge_weight = sum(
        float(problem["edge_by_id"][edge_id].get("weight", 1) or 1)
        for edge_id in covered_edges
    )
    selected_node_score = sum(
        float(problem["nodes"].get(node_id, {}).get("score", 0) or 0)
        for node_id in selected
    )
    total_edges = max(1, len(problem["edges"]))
    total_edge_weight = problem["total_edge_weight"] or 1.0
    total_nodes = problem.get("total_nodes") or max(1, len(problem.get("candidates", [])))
    total_node_weight = problem.get("total_node_weight") or 1.0
    removed_edges = len(removed_edge_ids)
    removed_edge_weight = sum(
        float(problem["edge_by_id"][edge_id].get("weight", 1) or 1)
        for edge_id in removed_edge_ids
    )
    selected_node_share = len(selected) / total_nodes
    selected_node_weight_share = selected_node_score / total_node_weight
    removed_edges_share = removed_edges / total_edges
    removed_edge_weight_share = removed_edge_weight / total_edge_weight
    preserved_edges = len(covered_edges)
    preserved_edge_weight = covered_edge_weight
    preserved_edges_share = preserved_edges / total_edges
    preserved_edge_weight_share = preserved_edge_weight / total_edge_weight
    min_node_weight_share = max(0.0, float(min_node_weight_share or 0.0))
    max_removed_edge_weight_share = min(1.0, max(0.0, float(max_removed_edge_weight_share if max_removed_edge_weight_share is not None else 1.0)))
    constraint_violation = (
        invalid_count
        + duplicate_count
        + max(0, min_nodes_value - size)
        + max(0, size - max_nodes_value)
        + max(0.0, min_node_weight_share - selected_node_weight_share)
        + max(0.0, removed_edge_weight_share - max_removed_edge_weight_share)
    )
    objective_value = (
        node_weight * selected_node_weight_share
        + coverage_weight * (1.0 - removed_edges_share)
        - edge_cost_weight * removed_edge_weight_share
        - size_penalty * len(selected)
    )
    return {
        "selected_ids": selected,
        "objective_value": objective_value,
        "selected_node_score": selected_node_score,
        "covered_edges": len(covered_edges),
        "covered_edge_weight": covered_edge_weight,
        "covered_weight_share": covered_edge_weight / problem["total_edge_weight"],
        "preserved_edges": preserved_edges,
        "preserved_edge_weight": preserved_edge_weight,
        "preserved_edges_share": preserved_edges_share,
        "preserved_edge_weight_share": preserved_edge_weight_share,
        "removed_edges": removed_edges,
        "removed_edge_weight": removed_edge_weight,
        "selected_node_share": selected_node_share,
        "selected_node_weight_share": selected_node_weight_share,
        "removed_edges_share": removed_edges_share,
        "removed_edge_weight_share": removed_edge_weight_share,
        "solution_size": len(selected),
        "feasible": constraint_violation == 0,
        "constraint_violation": round(float(constraint_violation), 6),
        "constraint_details": {
            "invalid_nodes": invalid_count,
            "duplicates": duplicate_count,
            "min_nodes_required": min_nodes_value,
            "max_nodes_allowed": max_nodes_value,
            "min_node_weight_share_required": round(min_node_weight_share, 6),
            "max_removed_edge_weight_share_allowed": round(max_removed_edge_weight_share, 6),
            "node_weight_shortfall": round(max(0.0, min_node_weight_share - selected_node_weight_share), 6),
            "removed_edge_excess": round(max(0.0, removed_edge_weight_share - max_removed_edge_weight_share), 6),
        },
        "objectives": {
            "minimize_selected_node_share": selected_node_share,
            "maximize_selected_node_weight_share": selected_node_weight_share,
            "minimize_removed_edge_weight_share": removed_edge_weight_share,
        },
    }


def _cover_result_from_ids(
    selected_ids: list[str],
    problem: dict,
    method: str,
    objective_value: float,
    pareto_front: list[dict] | None = None,
    hypervolume: float | None = None,
) -> dict:
    covered_edges = set()
    removed_edge_ids = set()
    selected_node_score = 0.0
    selected_rows = []
    total_edge_weight = problem["total_edge_weight"]
    total_edges = max(1, len(problem["edges"]))
    total_nodes = problem.get("total_nodes") or max(1, len(problem.get("candidates", [])))
    total_node_weight = problem.get("total_node_weight") or 1.0
    all_edge_ids = set(problem["edge_by_id"])
    for rank, node_id in enumerate(selected_ids, start=1):
        node = problem["nodes"][node_id]
        previous_edges = set(covered_edges)
        previous_removed = set(removed_edge_ids)
        mode = problem.get("coverage_mode")
        if mode == "removal_impact":
            selected_prefix = set(selected_ids[:rank])
            removed_edge_ids = set()
            for selected_node_id in selected_prefix:
                removed_edge_ids.update(problem["incident"].get(selected_node_id, set()))
            covered_edges = all_edge_ids - removed_edge_ids
        elif mode == "incident":
            new_edges = problem["incident"].get(node_id, set()) - covered_edges
            covered_edges.update(new_edges)
            removed_edge_ids = all_edge_ids - covered_edges
        else:
            selected_prefix = set(selected_ids[:rank])
            covered_edges = {
                edge["edge_id"]
                for edge in problem["edges"]
                if edge.get("source") in selected_prefix and edge.get("target") in selected_prefix
            }
            removed_edge_ids = all_edge_ids - covered_edges
        new_edges = covered_edges - previous_edges
        new_removed_edges = removed_edge_ids - previous_removed
        new_removed_weight = sum(
            float(problem["edge_by_id"][edge_id].get("weight", 1) or 1)
            for edge_id in new_removed_edges
        )
        covered_weight = sum(
            float(problem["edge_by_id"][edge_id].get("weight", 1) or 1)
            for edge_id in covered_edges
        )
        removed_edge_weight = sum(
            float(problem["edge_by_id"][edge_id].get("weight", 1) or 1)
            for edge_id in removed_edge_ids
        )
        selected_node_score += float(node.get("score", 0) or 0)
        selected_rows.append(
            {
                "rank": rank,
                "node_id": node_id,
                "label": node.get("label", node_id),
                "node_type": node.get("node_type"),
                "node_score": node.get("score", 0),
                "marginal_edges_covered": len(new_edges),
                "marginal_weight_covered": round(
                    sum(float(problem["edge_by_id"][edge_id].get("weight", 1) or 1) for edge_id in new_edges),
                    3,
                ),
                "marginal_edges_removed": len(new_removed_edges),
                "marginal_weight_removed": round(new_removed_weight, 3),
                "cumulative_weight_covered": round(covered_weight, 3),
                "cumulative_weight_share": round(covered_weight / total_edge_weight, 4),
                "cumulative_node_score": round(selected_node_score, 3),
                "node_score_to_edge_weight": round(selected_node_score / max(1.0, covered_weight), 5),
                "nodes_ratio": round(rank / total_nodes, 5),
                "node_weight_ratio": round(selected_node_score / total_node_weight, 5),
                "removed_edge_weight_ratio": round(removed_edge_weight / total_edge_weight, 5),
            }
        )
    removed_edges = len(removed_edge_ids)
    removed_edge_weight = sum(
        float(problem["edge_by_id"][edge_id].get("weight", 1) or 1)
        for edge_id in removed_edge_ids
    )
    covered_weight = sum(
        float(problem["edge_by_id"][edge_id].get("weight", 1) or 1)
        for edge_id in covered_edges
    )
    return {
        "selected_nodes": selected_rows,
        "stats": {
            "method": method,
            "objective": "node_selector_multiobjective_scp_inspired",
            "coverage_mode": problem.get("coverage_mode", "removal_impact"),
            "objective_value": round(objective_value, 5),
            "selected_nodes": len(selected_rows),
            "total_candidate_nodes": total_nodes,
            "nodes_ratio": round(len(selected_rows) / total_nodes, 5),
            "candidate_edges": len(problem["edges"]),
            "covered_edges": len(covered_edges),
            "uncovered_edges": removed_edges,
            "preserved_edges": len(covered_edges),
            "removed_edges": removed_edges,
            "total_edge_weight": round(total_edge_weight, 3),
            "covered_edge_weight": round(covered_weight, 3),
            "preserved_edge_weight": round(covered_weight, 3),
            "removed_edge_weight": round(removed_edge_weight, 3),
            "covered_weight_share": round(covered_weight / total_edge_weight, 4),
            "preserved_weight_share": round(covered_weight / total_edge_weight, 4),
            "removed_edge_weight_ratio": round(removed_edge_weight / total_edge_weight, 5),
            "selected_node_score": round(selected_node_score, 3),
            "total_node_weight": round(total_node_weight, 3),
            "node_weight_ratio": round(selected_node_score / total_node_weight, 5),
            "node_score_to_edge_weight": round(selected_node_score / max(1.0, covered_weight), 5),
            "hypervolume": round(hypervolume, 5) if hypervolume is not None else "",
            "pareto_solutions": len(pareto_front or []),
        },
        "pareto_front": pareto_front or [],
    }


def _dominates(a: dict, b: dict) -> bool:
    a_feasible = bool(a.get("feasible", True))
    b_feasible = bool(b.get("feasible", True))
    if a_feasible and not b_feasible:
        return True
    if b_feasible and not a_feasible:
        return False
    if not a_feasible and not b_feasible:
        return float(a.get("constraint_violation", math.inf)) < float(b.get("constraint_violation", math.inf))
    ao = a["objectives"]
    bo = b["objectives"]
    better_or_equal = (
        ao["minimize_selected_node_share"] <= bo["minimize_selected_node_share"]
        and ao["maximize_selected_node_weight_share"] >= bo["maximize_selected_node_weight_share"]
        and ao["minimize_removed_edge_weight_share"] <= bo["minimize_removed_edge_weight_share"]
    )
    strictly_better = (
        ao["minimize_selected_node_share"] < bo["minimize_selected_node_share"]
        or ao["maximize_selected_node_weight_share"] > bo["maximize_selected_node_weight_share"]
        or ao["minimize_removed_edge_weight_share"] < bo["minimize_removed_edge_weight_share"]
    )
    return better_or_equal and strictly_better


def pareto_front_from_evaluations(evaluations: list[dict], max_rows: int = 100) -> list[dict]:
    unique: dict[tuple[str, ...], dict] = {}
    for evaluation in evaluations:
        key = tuple(sorted(evaluation.get("selected_ids", [])))
        if key and (key not in unique or evaluation["objective_value"] > unique[key]["objective_value"]):
            unique[key] = evaluation
    values = list(unique.values())
    front = [
        evaluation for evaluation in values
        if not any(_dominates(other, evaluation) for other in values if other is not evaluation)
    ]
    front.sort(
        key=lambda row: (
            row["objectives"]["maximize_selected_node_weight_share"],
            -row["objectives"]["minimize_removed_edge_weight_share"],
            -row["objectives"]["minimize_selected_node_share"],
        ),
        reverse=True,
    )
    rows = []
    for rank, row in enumerate(front[:max_rows], start=1):
        rows.append(
            {
                "pareto_rank": rank,
                "node_ids": " | ".join(row["selected_ids"]),
                "minimize_nodes_ratio": round(row["objectives"]["minimize_selected_node_share"], 5),
                "maximize_node_weight_ratio": round(row["objectives"]["maximize_selected_node_weight_share"], 5),
                "minimize_removed_edge_weight_ratio": round(row["objectives"]["minimize_removed_edge_weight_share"], 5),
                "removed_edges": row.get("removed_edges", 0),
                "removed_edge_weight": round(row.get("removed_edge_weight", 0), 3),
                "solution_size": row.get("solution_size", 0),
                "feasible": row.get("feasible", True),
                "constraint_violation": row.get("constraint_violation", 0),
                "scalar_reference": round(row["objective_value"], 5),
            }
        )
    return rows


def normalized_objective_vector(evaluation: dict, problem: dict, max_nodes: int) -> tuple[float, float, float]:
    objectives = evaluation["objectives"]
    return (
        max(0.0, min(1.0, 1.0 - objectives["minimize_selected_node_share"])),
        max(0.0, min(1.0, objectives["maximize_selected_node_weight_share"])),
        max(0.0, min(1.0, 1.0 - objectives["minimize_removed_edge_weight_share"])),
    )


def exact_hypervolume_3d_max(vectors: list[tuple[float, float, float]]) -> float:
    """Exact dominated hypervolume for maximization in [0,1]^3, reference=(0,0,0).

    The narrative cover model reports three normalized utilities:
    compactness, selected-node relevance, and edge preservation. A point dominates
    the rectangular volume from the origin up to its coordinates. The metric must
    therefore be computed over the feasible nondominated set, not from a 2D
    projection and not from a scalarized objective.
    """
    clean = [
        (
            max(0.0, min(1.0, float(vector[0]))),
            max(0.0, min(1.0, float(vector[1]))),
            max(0.0, min(1.0, float(vector[2]))),
        )
        for vector in vectors
        if len(vector) == 3
    ]
    clean = [vector for vector in clean if vector[0] > 0 and vector[1] > 0 and vector[2] > 0]
    if not clean:
        return 0.0

    xs = sorted({0.0, *[vector[0] for vector in clean]})
    ys = sorted({0.0, *[vector[1] for vector in clean]})
    zs = sorted({0.0, *[vector[2] for vector in clean]})
    volume = 0.0
    for xi in range(len(xs) - 1):
        x_low, x_high = xs[xi], xs[xi + 1]
        if x_high <= x_low:
            continue
        for yi in range(len(ys) - 1):
            y_low, y_high = ys[yi], ys[yi + 1]
            if y_high <= y_low:
                continue
            for zi in range(len(zs) - 1):
                z_low, z_high = zs[zi], zs[zi + 1]
                if z_high <= z_low:
                    continue
                if any(vector[0] >= x_high and vector[1] >= y_high and vector[2] >= z_high for vector in clean):
                    volume += (x_high - x_low) * (y_high - y_low) * (z_high - z_low)
    return round(volume, 6)


def approximate_hypervolume(
    evaluations: list[dict],
    problem: dict,
    max_nodes: int,
    samples: int = 4000,
    seed: int = 17,
) -> float:
    """Exact hypervolume in normalized three-objective SCP space.

    ``samples`` and ``seed`` remain in the signature for backward compatibility
    with older calls, but the computation is now exact in 3D.
    """
    front_evaluations = []
    values = list(
        {
            tuple(sorted(row["selected_ids"])): row
            for row in evaluations
            if row.get("selected_ids") and row.get("feasible", True)
        }.values()
    )
    for evaluation in values:
        if not any(_dominates(other, evaluation) for other in values if other is not evaluation):
            front_evaluations.append(evaluation)
    if not front_evaluations:
        return 0.0
    vectors = [normalized_objective_vector(row, problem, max_nodes) for row in front_evaluations]
    return exact_hypervolume_3d_max(vectors)


def cover_problem_signature(problem: dict, max_nodes: int, purpose: str = "") -> tuple:
    """Stable in-memory cache key for LP guides of the same local SCP instance."""
    candidates = tuple(sorted(str(node_id) for node_id in problem.get("candidates", [])))
    node_scores = tuple(
        (node_id, round(float(problem.get("nodes", {}).get(node_id, {}).get("score", 0) or 0), 6))
        for node_id in candidates
    )
    edge_signature = tuple(
        sorted(
            (
                str(edge.get("source", "")),
                str(edge.get("target", "")),
                str(edge.get("edge_type", "")),
                round(float(edge.get("weight", 1) or 1), 6),
            )
            for edge in problem.get("edges", [])
        )
    )
    return (
        purpose,
        int(max_nodes),
        str(problem.get("coverage_mode", "")),
        candidates,
        node_scores,
        edge_signature,
    )


def relaxed_lp_reference_points(problem: dict, max_nodes: int) -> dict:
    """Compute ideal/nadir utility anchors from a mono-objective LP relaxation.

    Variables are x_v in [0,1] and r_e in [0,1]. For each edge e=(i,j):
    r_e >= x_i, r_e >= x_j, r_e <= x_i + x_j. This is the linear relaxation
    of the binary OR meaning that an edge is removed when at least one endpoint
    is selected.
    """
    candidates = list(problem.get("candidates", []))
    edges = list(problem.get("edges", []))
    n = len(candidates)
    m = len(edges)
    cache_key = cover_problem_signature(problem, max_nodes, purpose="lp_reference")
    if cache_key in LP_REFERENCE_CACHE:
        cached = copy.deepcopy(LP_REFERENCE_CACHE[cache_key])
        cached["cache"] = "memory_hit"
        cached["status"] = f"{cached.get('status', 'unknown')}_cached"
        return cached
    if not candidates:
        return {
            "status": "empty_problem",
            "ideal": {"u1": 0.0, "u2": 0.0, "u3": 0.0},
            "nadir": {"u1": 0.0, "u2": 0.0, "u3": 0.0},
        }
    max_nodes = max(1, min(int(max_nodes), n))
    min_nodes = 1
    node_index = {node_id: index for index, node_id in enumerate(candidates)}
    node_weights = [float(problem["nodes"][node_id].get("score", 0) or 0) for node_id in candidates]
    edge_weights = [float(edge.get("weight", 1) or 1) for edge in edges]
    total_node_weight = problem.get("total_node_weight") or sum(node_weights) or 1.0
    total_edge_weight = problem.get("total_edge_weight") or sum(edge_weights) or 1.0

    try:
        from scipy.optimize import linprog  # type: ignore

        variable_count = n + m
        bounds = [(0.0, 1.0)] * variable_count
        a_ub = []
        b_ub = []
        row = [0.0] * variable_count
        for index in range(n):
            row[index] = 1.0
        a_ub.append(row)
        b_ub.append(float(max_nodes))
        row = [0.0] * variable_count
        for index in range(n):
            row[index] = -1.0
        a_ub.append(row)
        b_ub.append(float(-min_nodes))

        for edge_index, edge in enumerate(edges):
            source = edge.get("source")
            target = edge.get("target")
            if source not in node_index or target not in node_index:
                continue
            r_index = n + edge_index
            source_index = node_index[source]
            target_index = node_index[target]
            row = [0.0] * variable_count
            row[source_index] = 1.0
            row[r_index] = -1.0
            a_ub.append(row)
            b_ub.append(0.0)
            row = [0.0] * variable_count
            row[target_index] = 1.0
            row[r_index] = -1.0
            a_ub.append(row)
            b_ub.append(0.0)
            row = [0.0] * variable_count
            row[r_index] = 1.0
            row[source_index] = -1.0
            row[target_index] = -1.0
            a_ub.append(row)
            b_ub.append(0.0)

        def solve(c: list[float]):
            return linprog(c, A_ub=a_ub, b_ub=b_ub, bounds=bounds, method="highs")

        def utility(result) -> tuple[float, float, float] | None:
            if not getattr(result, "success", False):
                return None
            x = result.x[:n]
            r = result.x[n:]
            selected_share = sum(x) / max(1, n)
            node_share = sum(node_weights[index] * x[index] for index in range(n)) / total_node_weight
            removed_share = sum(edge_weights[index] * r[index] for index in range(m)) / total_edge_weight
            return (
                max(0.0, min(1.0, 1.0 - selected_share)),
                max(0.0, min(1.0, node_share)),
                max(0.0, min(1.0, 1.0 - removed_share)),
            )

        c_u1_best = [1.0] * n + [0.0] * m
        c_u1_worst = [-1.0] * n + [0.0] * m
        c_u2_best = [-weight for weight in node_weights] + [0.0] * m
        c_u2_worst = node_weights + [0.0] * m
        c_u3_best = [0.0] * n + edge_weights
        c_u3_worst = [0.0] * n + [-weight for weight in edge_weights]
        solved = {
            "u1_best": utility(solve(c_u1_best)),
            "u1_worst": utility(solve(c_u1_worst)),
            "u2_best": utility(solve(c_u2_best)),
            "u2_worst": utility(solve(c_u2_worst)),
            "u3_best": utility(solve(c_u3_best)),
            "u3_worst": utility(solve(c_u3_worst)),
        }
        if any(value is None for value in solved.values()):
            raise RuntimeError("LP relaxation did not solve all anchor problems")
        ideal = {
            "u1": round(solved["u1_best"][0], 6),
            "u2": round(solved["u2_best"][1], 6),
            "u3": round(solved["u3_best"][2], 6),
        }
        nadir = {
            "u1": round(solved["u1_worst"][0], 6),
            "u2": round(solved["u2_worst"][1], 6),
            "u3": round(solved["u3_worst"][2], 6),
        }
        result_payload = {"status": "lp_relaxation_scipy_highs", "ideal": ideal, "nadir": nadir, "cache": "computed"}
        LP_REFERENCE_CACHE[cache_key] = copy.deepcopy(result_payload)
        return result_payload
    except Exception as exc:  # noqa: BLE001
        sorted_weights = sorted(node_weights, reverse=True)
        ideal_u2 = sum(sorted_weights[:max_nodes]) / total_node_weight
        result_payload = {
            "status": f"fallback_no_lp_solver:{type(exc).__name__}",
            "ideal": {"u1": round(1 - min_nodes / n, 6), "u2": round(ideal_u2, 6), "u3": 1.0},
            "nadir": {"u1": round(1 - max_nodes / n, 6), "u2": 0.0, "u3": 0.0},
            "cache": "computed",
        }
        LP_REFERENCE_CACHE[cache_key] = copy.deepcopy(result_payload)
        return result_payload


def relaxed_lp_seed_solutions(problem: dict, max_nodes: int) -> dict:
    """Return initial feasible seed sets obtained from LP objective relaxations.

    When scipy is available, each mono-objective LP relaxation is solved and
    rounded by largest fractional x values. Without scipy, deterministic
    constructive proxies are used so the algorithm remains fully local.
    """
    candidates = list(problem.get("candidates", []))
    cache_key = cover_problem_signature(problem, max_nodes, purpose="lp_seed")
    if cache_key in LP_SEED_CACHE:
        cached = copy.deepcopy(LP_SEED_CACHE[cache_key])
        cached["cache"] = "memory_hit"
        cached["status"] = f"{cached.get('status', 'unknown')}_cached"
        return cached
    if not candidates:
        return {"status": "empty_problem", "seeds": []}
    max_nodes = max(1, min(int(max_nodes), len(candidates)))
    node_weights = {
        node_id: float(problem["nodes"].get(node_id, {}).get("score", 0) or 0)
        for node_id in candidates
    }
    incident_weight = {
        node_id: sum(
            float(problem["edge_by_id"][edge_id].get("weight", 1) or 1)
            for edge_id in problem["incident"].get(node_id, set())
        )
        for node_id in candidates
    }

    def clean_seed(seed: list[str]) -> list[str]:
        unique = [node_id for node_id in dict.fromkeys(seed) if node_id in candidates]
        return unique[:max_nodes] or [max(candidates, key=lambda node_id: node_weights[node_id])]

    seeds: list[dict] = []
    try:
        from scipy.optimize import linprog  # type: ignore

        edges = list(problem.get("edges", []))
        n = len(candidates)
        m = len(edges)
        node_index = {node_id: index for index, node_id in enumerate(candidates)}
        edge_weights = [float(edge.get("weight", 1) or 1) for edge in edges]
        variable_count = n + m
        bounds = [(0.0, 1.0)] * variable_count
        a_ub = []
        b_ub = []
        row = [0.0] * variable_count
        for index in range(n):
            row[index] = 1.0
        a_ub.append(row)
        b_ub.append(float(max_nodes))
        row = [0.0] * variable_count
        for index in range(n):
            row[index] = -1.0
        a_ub.append(row)
        b_ub.append(-1.0)
        for edge_index, edge in enumerate(edges):
            source = edge.get("source")
            target = edge.get("target")
            if source not in node_index or target not in node_index:
                continue
            r_index = n + edge_index
            source_index = node_index[source]
            target_index = node_index[target]
            row = [0.0] * variable_count
            row[source_index] = 1.0
            row[r_index] = -1.0
            a_ub.append(row)
            b_ub.append(0.0)
            row = [0.0] * variable_count
            row[target_index] = 1.0
            row[r_index] = -1.0
            a_ub.append(row)
            b_ub.append(0.0)
            row = [0.0] * variable_count
            row[r_index] = 1.0
            row[source_index] = -1.0
            row[target_index] = -1.0
            a_ub.append(row)
            b_ub.append(0.0)

        objectives = {
            "lp_u1_compact": [1.0] * n + [0.0] * m,
            "lp_u2_relevance": [-node_weights[node_id] for node_id in candidates] + [0.0] * m,
            "lp_u3_preserve_edges": [0.0] * n + edge_weights,
            "lp_balanced": [
                1.0 - (node_weights[node_id] / max(1.0, max(node_weights.values()))) + incident_weight[node_id] / max(1.0, max(incident_weight.values() or [1.0]))
                for node_id in candidates
            ] + [weight / max(1.0, max(edge_weights or [1.0])) for weight in edge_weights],
        }
        for label, c in objectives.items():
            result = linprog(c, A_ub=a_ub, b_ub=b_ub, bounds=bounds, method="highs")
            if not getattr(result, "success", False):
                continue
            x_values = list(result.x[:n])
            ranked = sorted(
                candidates,
                key=lambda node_id: (x_values[node_index[node_id]], node_weights[node_id]),
                reverse=True,
            )
            positive = [node_id for node_id in ranked if x_values[node_index[node_id]] > 1e-6]
            seed = clean_seed(positive or ranked[:1])
            seeds.append({"source": label, "nodes": seed})
        status = "lp_relaxation_seed_solutions_scipy_highs"
    except Exception as exc:  # noqa: BLE001
        ranked_by_weight = sorted(candidates, key=lambda node_id: node_weights[node_id], reverse=True)
        ranked_by_low_impact = sorted(candidates, key=lambda node_id: (incident_weight[node_id], -node_weights[node_id]))
        ranked_by_ratio = sorted(
            candidates,
            key=lambda node_id: node_weights[node_id] / (1.0 + incident_weight[node_id]),
            reverse=True,
        )
        seeds = [
            {"source": "fallback_u1_compact_best_single", "nodes": clean_seed(ranked_by_ratio[:1])},
            {"source": "fallback_u2_relevance_top_k", "nodes": clean_seed(ranked_by_weight[:max_nodes])},
            {"source": "fallback_u3_preserve_low_impact", "nodes": clean_seed(ranked_by_low_impact[:1])},
            {"source": "fallback_balanced_ratio", "nodes": clean_seed(ranked_by_ratio[:max(1, min(max_nodes, 3))])},
        ]
        status = f"fallback_seed_solutions_no_lp_solver:{type(exc).__name__}"

    attempted_sources = [str(seed.get("source", "")) for seed in seeds if seed.get("source")]
    unique: dict[tuple[str, ...], dict] = {}
    for seed in seeds:
        key = solution_key(seed["nodes"])
        if key:
            if key in unique:
                previous = str(unique[key].get("source", ""))
                current = str(seed.get("source", ""))
                merged_sources = [source for source in [previous, current] if source]
                unique[key]["source"] = " + ".join(dict.fromkeys(" + ".join(merged_sources).split(" + ")))
            else:
                unique[key] = seed
    result_payload = {
        "status": status,
        "attempted_sources": attempted_sources,
        "seeds": list(unique.values()),
        "cache": "computed",
    }
    LP_SEED_CACHE[cache_key] = copy.deepcopy(result_payload)
    return result_payload


def solution_key(selected_ids: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({str(node_id) for node_id in selected_ids if str(node_id)}))


def normalized_sum_score(evaluation: dict, problem: dict, max_nodes: int) -> float:
    return sum(normalized_objective_vector(evaluation, problem, max_nodes))


def coello_selection_key(evaluation: dict, problem: dict, max_nodes: int) -> tuple[int, float, float]:
    """Rank solutions with Coello-style feasibility before scalar utility.

    Feasible solutions are always preferred to infeasible ones. Among feasible
    solutions, the normalized three-objective utility is used only to pick one
    representative from the Pareto archive. Among infeasible solutions, the
    smaller absolute distance to the feasible region is preferred.
    """
    feasible = bool(evaluation.get("feasible", False))
    violation = float(evaluation.get("constraint_violation", math.inf) or 0.0)
    utility = normalized_sum_score(evaluation, problem, max_nodes)
    return (1 if feasible else 0, -violation, utility)


def weighted_utility_score(evaluation: dict, problem: dict, max_nodes: int, weights: tuple[float, float, float]) -> float:
    values = normalized_objective_vector(evaluation, problem, max_nodes)
    return sum(weights[index] * values[index] for index in range(3))


def update_pareto_archive(archive: dict[tuple[str, ...], dict], evaluation: dict) -> None:
    key = solution_key(evaluation.get("selected_ids", []))
    if not key:
        return
    if key in archive and archive[key].get("objective_value", -math.inf) >= evaluation.get("objective_value", -math.inf):
        return
    if any(_dominates(other, evaluation) for other in archive.values()):
        return
    archive[key] = evaluation
    dominated_keys = [
        other_key for other_key, other in archive.items()
        if other_key != key and _dominates(evaluation, other)
    ]
    for other_key in dominated_keys:
        archive.pop(other_key, None)


def make_cover_helpers(problem: dict, max_nodes: int, rng: random.Random):
    candidates = problem["candidates"]
    max_nodes = max(1, min(max_nodes, len(candidates) or 1))

    def repair(solution: list[str]) -> list[str]:
        unique = [node_id for node_id in dict.fromkeys(solution) if node_id in candidates]
        if not unique and candidates:
            unique = [rng.choice(candidates)]
        if len(unique) > max_nodes:
            unique = sorted(
                unique,
                key=lambda node_id: problem["nodes"][node_id].get("score", 0),
                reverse=True,
            )[:max_nodes]
        return unique

    def random_solution() -> list[str]:
        if not candidates:
            return []
        size = rng.randint(1, max_nodes)
        return rng.sample(candidates, min(size, len(candidates)))

    def mutate(solution: list[str]) -> list[str]:
        if not candidates:
            return []
        child = list(solution)
        action = rng.random()
        if action < 0.35 and len(child) < max_nodes:
            child.append(rng.choice(candidates))
        elif action < 0.70 and len(child) > 1:
            child.pop(rng.randrange(len(child)))
        elif child:
            child[rng.randrange(len(child))] = rng.choice(candidates)
        else:
            child = random_solution()
        return repair(child)

    def crossover(parent_a: list[str], parent_b: list[str]) -> list[str]:
        if not parent_a:
            return repair(parent_b)
        if not parent_b:
            return repair(parent_a)
        cut_a = rng.randint(0, len(parent_a))
        cut_b = rng.randint(0, len(parent_b))
        return repair(parent_a[:cut_a] + parent_b[cut_b:])

    return repair, random_solution, mutate, crossover


def make_cover_evaluator(
    problem: dict,
    max_nodes: int,
    min_nodes: int = 1,
    min_node_weight_share: float = 0.0,
    max_removed_edge_weight_share: float = 1.0,
):
    calls = {"count": 0}

    def evaluate(solution: Iterable[str]) -> dict:
        calls["count"] += 1
        evaluation = _evaluate_cover_solution(
            solution,
            problem,
            max_nodes=max_nodes,
            min_nodes=min_nodes,
            min_node_weight_share=min_node_weight_share,
            max_removed_edge_weight_share=max_removed_edge_weight_share,
        )
        evaluation["evaluation_number"] = calls["count"]
        return evaluation

    return evaluate, calls


def solution_signature(solution: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(str(node_id) for node_id in solution if str(node_id)))


def result_from_multiobjective_evaluations(
    evaluations: list[dict],
    problem: dict,
    method: str,
    max_nodes: int,
    seed: int,
    evaluation_budget: int,
) -> dict:
    valid = [row for row in evaluations if row.get("selected_ids")]
    if not valid:
        result = _cover_result_from_ids([], problem, method, 0.0, pareto_front=[], hypervolume=0.0)
        result["stats"]["objective"] = "true_multiobjective_archive"
        result["stats"]["evaluation_budget"] = int(evaluation_budget)
        result["stats"]["evaluations_used"] = 0
        result["stats"]["selection_rule"] = "no_valid_solution_generated"
        result["stats"]["representative_feasible"] = False
        result["stats"]["representative_constraint_violation"] = 1.0
        result["stats"]["feasible_evaluations"] = 0
        result["stats"]["infeasible_evaluations"] = 0
        anchors = relaxed_lp_reference_points(problem, max_nodes)
        result["stats"]["lp_anchor_status"] = anchors.get("status")
        result["stats"]["lp_anchor_cache"] = anchors.get("cache")
        result["stats"]["ideal_u1"] = anchors.get("ideal", {}).get("u1")
        result["stats"]["ideal_u2"] = anchors.get("ideal", {}).get("u2")
        result["stats"]["ideal_u3"] = anchors.get("ideal", {}).get("u3")
        result["stats"]["nadir_u1"] = anchors.get("nadir", {}).get("u1")
        result["stats"]["nadir_u2"] = anchors.get("nadir", {}).get("u2")
        result["stats"]["nadir_u3"] = anchors.get("nadir", {}).get("u3")
        return result
    pareto_front = pareto_front_from_evaluations(valid)
    hypervolume = approximate_hypervolume(valid, problem, max_nodes, seed=seed)
    best = max(valid, key=lambda row: coello_selection_key(row, problem, max_nodes))
    result = _cover_result_from_ids(
        best["selected_ids"],
        problem,
        method,
        normalized_sum_score(best, problem, max_nodes),
        pareto_front=pareto_front,
        hypervolume=hypervolume,
    )
    result["stats"]["objective"] = "true_multiobjective_archive"
    result["stats"]["evaluation_budget"] = int(evaluation_budget)
    result["stats"]["evaluations_used"] = len(valid)
    result["stats"]["selection_rule"] = "coello_feasibility_then_best_normalized_sum_from_archive"
    result["stats"]["representative_feasible"] = bool(best.get("feasible", False))
    result["stats"]["representative_constraint_violation"] = float(best.get("constraint_violation", 0) or 0)
    result["stats"]["feasible_evaluations"] = sum(1 for row in valid if row.get("feasible"))
    result["stats"]["infeasible_evaluations"] = sum(1 for row in valid if not row.get("feasible"))
    anchors = relaxed_lp_reference_points(problem, max_nodes)
    result["stats"]["lp_anchor_status"] = anchors.get("status")
    result["stats"]["lp_anchor_cache"] = anchors.get("cache")
    result["stats"]["ideal_u1"] = anchors.get("ideal", {}).get("u1")
    result["stats"]["ideal_u2"] = anchors.get("ideal", {}).get("u2")
    result["stats"]["ideal_u3"] = anchors.get("ideal", {}).get("u3")
    result["stats"]["nadir_u1"] = anchors.get("nadir", {}).get("u1")
    result["stats"]["nadir_u2"] = anchors.get("nadir", {}).get("u2")
    result["stats"]["nadir_u3"] = anchors.get("nadir", {}).get("u3")
    return result


def weight_grid_for_three_objectives(levels: int = 5) -> list[tuple[float, float, float]]:
    values = [index / max(1, levels - 1) for index in range(levels)]
    weights = []
    for w1 in values:
        for w2 in values:
            for w3 in values:
                total = w1 + w2 + w3
                if total > 0:
                    weights.append((w1 / total, w2 / total, w3 / total))
    weights.sort()
    return weights


def weighted_sum_greedy_sweep_node_cover(
    graph: dict,
    max_nodes: int = 20,
    allowed_node_types: Iterable[str] | None = None,
    edge_types: Iterable[str] | None = None,
    evaluation_budget: int = 1000,
    seed: int = 42,
    coverage_mode: str = "removal_impact",
    min_nodes: int = 1,
    min_node_weight_share: float = 0.0,
    max_removed_edge_weight_share: float = 1.0,
) -> dict:
    problem = _cover_problem_data(graph, allowed_node_types, edge_types, coverage_mode=coverage_mode)
    candidates = problem["candidates"]
    if not candidates:
        return _cover_result_from_ids([], problem, "weighted_greedy_sweep", 0.0)
    max_nodes = max(1, min(max_nodes, len(candidates)))
    evaluations: list[dict] = []
    evaluate, calls = make_cover_evaluator(
        problem,
        max_nodes,
        min_nodes=min_nodes,
        min_node_weight_share=min_node_weight_share,
        max_removed_edge_weight_share=max_removed_edge_weight_share,
    )
    weights = weight_grid_for_three_objectives(levels=5)
    weight_index = 0
    while len(evaluations) < evaluation_budget and weights:
        weights_tuple = weights[weight_index % len(weights)]
        weight_index += 1
        selected_ids: list[str] = []
        current_score = -math.inf
        while len(selected_ids) < max_nodes and len(evaluations) < evaluation_budget:
            best_id = ""
            best_eval = None
            best_score = -math.inf
            for node_id in candidates:
                if len(evaluations) >= evaluation_budget:
                    break
                if node_id in selected_ids:
                    continue
                candidate_eval = evaluate([*selected_ids, node_id])
                candidate_eval["weight_vector"] = weights_tuple
                evaluations.append(candidate_eval)
                score = weighted_utility_score(candidate_eval, problem, max_nodes, weights_tuple)
                if score > best_score:
                    best_score = score
                    best_id = node_id
                    best_eval = candidate_eval
            if not best_id or best_eval is None:
                break
            selected_ids.append(best_id)
            best_weighted_score = weighted_utility_score(best_eval, problem, max_nodes, weights_tuple)
            if best_weighted_score <= current_score:
                break
            current_score = best_weighted_score
    result = result_from_multiobjective_evaluations(
        evaluations,
        problem,
        "weighted_greedy_sweep",
        max_nodes,
        seed=seed + 11,
        evaluation_budget=evaluation_budget,
    )
    result["stats"]["objective_function_calls"] = calls["count"]
    return result


def moea_weighted_node_cover(
    graph: dict,
    max_nodes: int = 20,
    allowed_node_types: Iterable[str] | None = None,
    edge_types: Iterable[str] | None = None,
    evaluation_budget: int = 1000,
    population_size: int = 60,
    mutation_rate: float = 0.18,
    seed: int = 42,
    coverage_mode: str = "removal_impact",
    min_nodes: int = 1,
    min_node_weight_share: float = 0.0,
    max_removed_edge_weight_share: float = 1.0,
) -> dict:
    problem = _cover_problem_data(graph, allowed_node_types, edge_types, coverage_mode=coverage_mode)
    rng = random.Random(seed)
    candidates = problem["candidates"]
    if not candidates:
        return _cover_result_from_ids([], problem, "moea", 0.0)
    max_nodes = max(1, min(max_nodes, len(candidates)))
    population_size = max(6, min(population_size, max(6, evaluation_budget)))
    repair, random_solution, mutate, crossover = make_cover_helpers(problem, max_nodes, rng)
    evaluate, calls = make_cover_evaluator(
        problem,
        max_nodes,
        min_nodes=min_nodes,
        min_node_weight_share=min_node_weight_share,
        max_removed_edge_weight_share=max_removed_edge_weight_share,
    )
    population = [random_solution() for _ in range(population_size)]
    evaluations: list[dict] = []
    archive: dict[tuple[str, ...], dict] = {}

    while len(evaluations) < evaluation_budget:
        evaluated = []
        for solution in population:
            if len(evaluations) >= evaluation_budget:
                break
            evaluation = evaluate(solution)
            evaluated.append(evaluation)
            evaluations.append(evaluation)
            update_pareto_archive(archive, evaluation)
        pool_evaluations = list(archive.values()) or evaluated
        pool_evaluations = sorted(
            pool_evaluations,
            key=lambda row: normalized_sum_score(row, problem, max_nodes),
            reverse=True,
        )
        parent_pool = [row["selected_ids"] for row in pool_evaluations[: max(2, min(len(pool_evaluations), population_size))]]
        new_population = [repair(parent) for parent in parent_pool[: max(2, population_size // 5)]]
        while len(new_population) < population_size:
            parent_a = rng.choice(parent_pool)
            parent_b = rng.choice(parent_pool)
            child = crossover(parent_a, parent_b)
            if rng.random() < mutation_rate:
                child = mutate(child)
            new_population.append(repair(child))
        population = new_population

    result = result_from_multiobjective_evaluations(
        evaluations,
        problem,
        "moea",
        max_nodes,
        seed=seed + 101,
        evaluation_budget=evaluation_budget,
    )
    result["stats"]["objective_function_calls"] = calls["count"]
    return result


def mosa_weighted_node_cover(
    graph: dict,
    max_nodes: int = 20,
    allowed_node_types: Iterable[str] | None = None,
    edge_types: Iterable[str] | None = None,
    evaluation_budget: int = 1000,
    initial_temperature: float = 1.0,
    cooling_rate: float = 0.995,
    seed: int = 42,
    coverage_mode: str = "removal_impact",
    min_nodes: int = 1,
    min_node_weight_share: float = 0.0,
    max_removed_edge_weight_share: float = 1.0,
) -> dict:
    problem = _cover_problem_data(graph, allowed_node_types, edge_types, coverage_mode=coverage_mode)
    rng = random.Random(seed)
    candidates = problem["candidates"]
    if not candidates:
        return _cover_result_from_ids([], problem, "mosa", 0.0)
    max_nodes = max(1, min(max_nodes, len(candidates)))
    _, random_solution, mutate, _ = make_cover_helpers(problem, max_nodes, rng)
    evaluate, calls = make_cover_evaluator(
        problem,
        max_nodes,
        min_nodes=min_nodes,
        min_node_weight_share=min_node_weight_share,
        max_removed_edge_weight_share=max_removed_edge_weight_share,
    )
    current = random_solution()
    current_eval = evaluate(current)
    evaluations = [current_eval]
    archive: dict[tuple[str, ...], dict] = {}
    update_pareto_archive(archive, current_eval)
    temperature = max(0.0001, initial_temperature)

    while len(evaluations) < evaluation_budget:
        candidate = mutate(current)
        candidate_eval = evaluate(candidate)
        evaluations.append(candidate_eval)
        update_pareto_archive(archive, candidate_eval)
        if _dominates(candidate_eval, current_eval):
            accept = True
        elif _dominates(current_eval, candidate_eval):
            delta = normalized_sum_score(candidate_eval, problem, max_nodes) - normalized_sum_score(current_eval, problem, max_nodes)
            accept = rng.random() < math.exp(delta / max(temperature, 0.0001))
        else:
            accept = rng.random() < 0.55
        if accept:
            current = candidate
            current_eval = candidate_eval
        temperature *= cooling_rate

    result = result_from_multiobjective_evaluations(
        evaluations,
        problem,
        "mosa",
        max_nodes,
        seed=seed + 202,
        evaluation_budget=evaluation_budget,
    )
    result["stats"]["objective_function_calls"] = calls["count"]
    return result


def mmc_multiobjective_weighted_node_cover(
    graph: dict,
    max_nodes: int = 20,
    allowed_node_types: Iterable[str] | None = None,
    edge_types: Iterable[str] | None = None,
    evaluation_budget: int = 1000,
    composers: int = 12,
    seed: int = 42,
    coverage_mode: str = "removal_impact",
    min_nodes: int = 1,
    min_node_weight_share: float = 0.0,
    max_removed_edge_weight_share: float = 1.0,
) -> dict:
    problem = _cover_problem_data(graph, allowed_node_types, edge_types, coverage_mode=coverage_mode)
    rng = random.Random(seed)
    candidates = problem["candidates"]
    if not candidates:
        return _cover_result_from_ids([], problem, "mmc_mo", 0.0)
    max_nodes = max(1, min(max_nodes, len(candidates)))
    composers = max(4, composers)
    repair, random_solution, mutate, crossover = make_cover_helpers(problem, max_nodes, rng)
    evaluate, calls = make_cover_evaluator(
        problem,
        max_nodes,
        min_nodes=min_nodes,
        min_node_weight_share=min_node_weight_share,
        max_removed_edge_weight_share=max_removed_edge_weight_share,
    )
    seed_info = relaxed_lp_seed_solutions(problem, max_nodes)
    lp_seed_solutions = [repair(seed.get("nodes", [])) for seed in seed_info.get("seeds", [])]
    evaluations: list[dict] = []
    guide_memory: dict[tuple[str, ...], dict] = {}
    for seed_solution in lp_seed_solutions:
        if len(evaluations) >= evaluation_budget:
            break
        evaluation = evaluate(seed_solution)
        evaluations.append(evaluation)
        update_pareto_archive(guide_memory, evaluation)
    society = []
    for seed_solution in lp_seed_solutions:
        if seed_solution and solution_key(seed_solution) not in {solution_key(item) for item in society}:
            society.append(seed_solution)
        if len(society) >= composers:
            break
    while len(society) < composers:
        society.append(random_solution())
    archive: dict[tuple[str, ...], dict] = {}
    guide_updates = 0

    while len(evaluations) < evaluation_budget:
        evaluated_society = []
        for arrangement in society:
            if len(evaluations) >= evaluation_budget:
                break
            evaluation = evaluate(arrangement)
            evaluated_society.append(evaluation)
            evaluations.append(evaluation)
            update_pareto_archive(archive, evaluation)
            before_guide_size = len(guide_memory)
            update_pareto_archive(guide_memory, evaluation)
            if len(guide_memory) != before_guide_size:
                guide_updates += 1
        guide_evaluations = list(guide_memory.values()) or list(archive.values()) or evaluated_society
        guide_evaluations = sorted(
            guide_evaluations,
            key=lambda row: normalized_sum_score(row, problem, max_nodes),
            reverse=True,
        )
        guide_solutions = [row["selected_ids"] for row in guide_evaluations]
        new_society = []
        for arrangement in society:
            if len(evaluations) >= evaluation_budget:
                break
            if not guide_solutions:
                new_society.append(mutate(arrangement))
                continue
            if rng.random() < 0.75:
                guide = rng.choice(guide_solutions[: max(1, min(len(guide_solutions), composers))])
            else:
                guide = rng.choice(guide_solutions)
            candidate = crossover(arrangement, guide)
            if rng.random() < 0.65:
                candidate = mutate(candidate)
            if len(evaluations) + 2 > evaluation_budget:
                new_society.append(repair(arrangement))
                continue
            current_eval = evaluate(arrangement)
            candidate_eval = evaluate(candidate)
            evaluations.extend([current_eval, candidate_eval])
            if _dominates(candidate_eval, current_eval) or (
                not _dominates(current_eval, candidate_eval)
                and normalized_sum_score(candidate_eval, problem, max_nodes) >= normalized_sum_score(current_eval, problem, max_nodes)
            ):
                new_society.append(repair(candidate))
            else:
                new_society.append(repair(arrangement))
        if new_society:
            society = new_society[:composers]

    result = result_from_multiobjective_evaluations(
        evaluations,
        problem,
        "mmc_mo",
        max_nodes,
        seed=seed + 303,
        evaluation_budget=evaluation_budget,
    )
    result["stats"]["initialization"] = "lp_relaxation_extreme_solutions_plus_random_fill"
    result["stats"]["lp_seed_status"] = seed_info.get("status")
    result["stats"]["lp_seed_cache"] = seed_info.get("cache")
    result["stats"]["lp_seed_count"] = len(lp_seed_solutions)
    result["stats"]["lp_seed_attempted_sources"] = ", ".join(seed_info.get("attempted_sources", []))
    result["stats"]["lp_seed_sources"] = ", ".join(seed.get("source", "") for seed in seed_info.get("seeds", []))
    result["stats"]["guide_policy"] = "lp_seeded_adaptive_pareto_memory"
    result["stats"]["guide_initial_solutions"] = len(lp_seed_solutions)
    result["stats"]["guide_final_solutions"] = len(guide_memory)
    result["stats"]["guide_updates"] = guide_updates
    result["stats"]["objective_function_calls"] = calls["count"]
    return result


def genetic_weighted_node_cover(
    graph: dict,
    max_nodes: int = 20,
    allowed_node_types: Iterable[str] | None = None,
    edge_types: Iterable[str] | None = None,
    population_size: int = 60,
    generations: int = 120,
    mutation_rate: float = 0.12,
    seed: int = 42,
    node_weight: float = 1.0,
    edge_cost_weight: float = 1.0,
    coverage_weight: float = 0.2,
    coverage_mode: str = "removal_impact",
) -> dict:
    problem = _cover_problem_data(graph, allowed_node_types, edge_types, coverage_mode=coverage_mode)
    rng = random.Random(seed)
    candidates = problem["candidates"]
    if not candidates:
        return _cover_result_from_ids([], problem, "genetic", 0.0)
    max_nodes = max(1, min(max_nodes, len(candidates)))

    def random_solution() -> list[str]:
        size = rng.randint(1, max_nodes)
        return rng.sample(candidates, size)

    def repair(solution: list[str]) -> list[str]:
        unique = [node_id for node_id in dict.fromkeys(solution) if node_id in candidates]
        if not unique:
            unique = random_solution()
        if len(unique) > max_nodes:
            scored = sorted(
                unique,
                key=lambda node_id: problem["nodes"][node_id].get("score", 0),
                reverse=True,
            )
            unique = scored[:max_nodes]
        return unique

    population = [random_solution() for _ in range(max(4, population_size))]
    best = None
    all_evaluations = []
    for _ in range(max(1, generations)):
        evaluated = [
            _evaluate_cover_solution(
                sol,
                problem,
                max_nodes=max_nodes,
                node_weight=node_weight,
                edge_cost_weight=edge_cost_weight,
                coverage_weight=coverage_weight,
            )
            for sol in population
        ]
        all_evaluations.extend(evaluated)
        evaluated.sort(key=lambda row: row["objective_value"], reverse=True)
        if best is None or evaluated[0]["objective_value"] > best["objective_value"]:
            best = evaluated[0]
        elites = [row["selected_ids"] for row in evaluated[: max(2, population_size // 5)]]
        new_population = elites[:]
        while len(new_population) < population_size:
            parent_a = rng.choice(elites)
            parent_b = rng.choice(elites)
            cut_a = rng.randint(0, len(parent_a))
            cut_b = rng.randint(0, len(parent_b))
            child = parent_a[:cut_a] + parent_b[cut_b:]
            if rng.random() < mutation_rate:
                if child and rng.random() < 0.5:
                    child.pop(rng.randrange(len(child)))
                child.append(rng.choice(candidates))
            new_population.append(repair(child))
        population = new_population
    assert best is not None
    pareto_front = pareto_front_from_evaluations(all_evaluations)
    hypervolume = approximate_hypervolume(all_evaluations, problem, max_nodes, seed=seed + 101)
    return _cover_result_from_ids(
        best["selected_ids"],
        problem,
        "genetic",
        best["objective_value"],
        pareto_front=pareto_front,
        hypervolume=hypervolume,
    )


def annealing_weighted_node_cover(
    graph: dict,
    max_nodes: int = 20,
    allowed_node_types: Iterable[str] | None = None,
    edge_types: Iterable[str] | None = None,
    iterations: int = 2000,
    initial_temperature: float = 1.0,
    cooling_rate: float = 0.995,
    seed: int = 42,
    node_weight: float = 1.0,
    edge_cost_weight: float = 1.0,
    coverage_weight: float = 0.2,
    coverage_mode: str = "removal_impact",
) -> dict:
    problem = _cover_problem_data(graph, allowed_node_types, edge_types, coverage_mode=coverage_mode)
    rng = random.Random(seed)
    candidates = problem["candidates"]
    if not candidates:
        return _cover_result_from_ids([], problem, "annealing", 0.0)
    max_nodes = max(1, min(max_nodes, len(candidates)))

    current = rng.sample(candidates, rng.randint(1, max_nodes))
    current_eval = _evaluate_cover_solution(
        current,
        problem,
        max_nodes=max_nodes,
        node_weight=node_weight,
        edge_cost_weight=edge_cost_weight,
        coverage_weight=coverage_weight,
    )
    best = dict(current_eval)
    all_evaluations = [current_eval]
    temperature = max(0.0001, initial_temperature)
    for _ in range(max(1, iterations)):
        candidate = list(current)
        action = rng.random()
        if action < 0.4 and len(candidate) < max_nodes:
            candidate.append(rng.choice(candidates))
        elif action < 0.75 and len(candidate) > 1:
            candidate.pop(rng.randrange(len(candidate)))
        else:
            if candidate:
                candidate[rng.randrange(len(candidate))] = rng.choice(candidates)
        candidate = [node_id for node_id in dict.fromkeys(candidate) if node_id in candidates][:max_nodes]
        candidate_eval = _evaluate_cover_solution(
            candidate,
            problem,
            max_nodes=max_nodes,
            node_weight=node_weight,
            edge_cost_weight=edge_cost_weight,
            coverage_weight=coverage_weight,
        )
        all_evaluations.append(candidate_eval)
        delta = candidate_eval["objective_value"] - current_eval["objective_value"]
        if delta >= 0 or rng.random() < math.exp(delta / max(temperature, 0.0001)):
            current = candidate
            current_eval = candidate_eval
            if current_eval["objective_value"] > best["objective_value"]:
                best = dict(current_eval)
        temperature *= cooling_rate
    pareto_front = pareto_front_from_evaluations(all_evaluations)
    hypervolume = approximate_hypervolume(all_evaluations, problem, max_nodes, seed=seed + 202)
    return _cover_result_from_ids(
        best["selected_ids"],
        problem,
        "annealing",
        best["objective_value"],
        pareto_front=pareto_front,
        hypervolume=hypervolume,
    )


def musical_composition_weighted_node_cover(
    graph: dict,
    max_nodes: int = 20,
    allowed_node_types: Iterable[str] | None = None,
    edge_types: Iterable[str] | None = None,
    composers: int = 12,
    max_arrangements: int = 120,
    genius_innovation_factor: float = 0.65,
    genius_change_factor: float = 0.35,
    exchange_factor: float = 0.35,
    seed: int = 42,
    node_weight: float = 1.0,
    edge_cost_weight: float = 1.0,
    coverage_weight: float = 0.2,
    coverage_mode: str = "removal_impact",
) -> dict:
    """Discrete adaptation of Mora-Gutierrez et al.'s Musical Composition Method.

    In this adaptation, each composer holds an arrangement: a subset of narrative
    nodes. The best arrangement is the genius theme. New arrangements combine
    genius-guided innovation, local change and exchange among composers.
    """
    problem = _cover_problem_data(graph, allowed_node_types, edge_types, coverage_mode=coverage_mode)
    rng = random.Random(seed)
    candidates = problem["candidates"]
    if not candidates:
        return _cover_result_from_ids([], problem, "mmc", 0.0)
    max_nodes = max(1, min(max_nodes, len(candidates)))
    composers = max(2, composers)
    max_arrangements = max(1, max_arrangements)

    ranked_candidates = sorted(
        candidates,
        key=lambda node_id: problem["nodes"][node_id].get("score", 0),
        reverse=True,
    )
    elite_pool = ranked_candidates[: max(max_nodes, min(len(ranked_candidates), max_nodes * 4))]

    def repair(arrangement: list[str]) -> list[str]:
        unique = [node_id for node_id in dict.fromkeys(arrangement) if node_id in candidates]
        if not unique:
            unique = [rng.choice(candidates)]
        if len(unique) > max_nodes:
            unique = sorted(
                unique,
                key=lambda node_id: problem["nodes"][node_id].get("score", 0),
                reverse=True,
            )[:max_nodes]
        return unique

    def random_arrangement() -> list[str]:
        size = rng.randint(1, max_nodes)
        pool = elite_pool if rng.random() < 0.5 else candidates
        return repair(rng.sample(pool, min(size, len(pool))))

    society = [random_arrangement() for _ in range(composers)]
    evaluated = [
        _evaluate_cover_solution(
            arr,
            problem,
            max_nodes=max_nodes,
            node_weight=node_weight,
            edge_cost_weight=edge_cost_weight,
            coverage_weight=coverage_weight,
        )
        for arr in society
    ]
    all_evaluations = list(evaluated)
    genius = max(evaluated, key=lambda row: row["objective_value"])

    for _ in range(max_arrangements):
        new_society = []
        for arrangement in society:
            new_arrangement = list(arrangement)

            # Genius over innovation: borrow part of the best theme.
            if rng.random() < genius_innovation_factor and genius["selected_ids"]:
                borrowed = rng.sample(
                    genius["selected_ids"],
                    rng.randint(1, min(len(genius["selected_ids"]), max_nodes)),
                )
                new_arrangement.extend(borrowed)

            # Change: modify the current arrangement.
            if rng.random() < genius_change_factor:
                action = rng.random()
                if action < 0.34 and len(new_arrangement) < max_nodes:
                    new_arrangement.append(rng.choice(elite_pool if rng.random() < 0.7 else candidates))
                elif action < 0.67 and len(new_arrangement) > 1:
                    new_arrangement.pop(rng.randrange(len(new_arrangement)))
                elif new_arrangement:
                    new_arrangement[rng.randrange(len(new_arrangement))] = rng.choice(candidates)

            # Exchange among composers: social recombination.
            if rng.random() < exchange_factor:
                partner = rng.choice(society)
                if partner:
                    new_arrangement.extend(
                        rng.sample(partner, rng.randint(1, min(len(partner), max_nodes)))
                    )

            new_arrangement = repair(new_arrangement)
            current_eval = _evaluate_cover_solution(
                arrangement,
                problem,
                max_nodes=max_nodes,
                node_weight=node_weight,
                edge_cost_weight=edge_cost_weight,
                coverage_weight=coverage_weight,
            )
            new_eval = _evaluate_cover_solution(
                new_arrangement,
                problem,
                max_nodes=max_nodes,
                node_weight=node_weight,
                edge_cost_weight=edge_cost_weight,
                coverage_weight=coverage_weight,
            )
            all_evaluations.extend([current_eval, new_eval])
            if new_eval["objective_value"] >= current_eval["objective_value"]:
                new_society.append(new_arrangement)
                if new_eval["objective_value"] > genius["objective_value"]:
                    genius = new_eval
            else:
                new_society.append(arrangement)
        society = new_society

    pareto_front = pareto_front_from_evaluations(all_evaluations)
    hypervolume = approximate_hypervolume(all_evaluations, problem, max_nodes, seed=seed + 303)
    return _cover_result_from_ids(
        genius["selected_ids"],
        problem,
        "mmc",
        genius["objective_value"],
        pareto_front=pareto_front,
        hypervolume=hypervolume,
    )


def parse_idea_groups(text: str, base_groups: dict[str, list[str]] | None = None) -> dict[str, list[str]]:
    groups = {key: list(values) for key, values in (base_groups or IDEA_GROUPS).items()}
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        name, terms = line.split(":", 1)
        name = re.sub(r"[^a-zA-Z0-9_-]+", "_", name.strip()).strip("_")
        keywords = [term.strip() for term in terms.split(",") if term.strip()]
        if name and keywords:
            groups[name] = keywords
    return groups


def idea_group_counts(records: list[dict], groups: dict[str, list[str]] | None = None) -> list[dict]:
    groups = groups or idea_groups_for_records(records)
    total_docs = max(1, len(records))
    rows = []
    for group, keywords in groups.items():
        keyword_hits = 0
        doc_hits = 0
        matched_terms = Counter()
        for record in records:
            text = record_text(record).lower()
            local_hit = False
            for keyword in keywords:
                count = len(re.findall(rf"\b{re.escape(keyword.lower())}\b", text))
                if count:
                    keyword_hits += count
                    matched_terms[keyword] += count
                    local_hit = True
            if local_hit:
                doc_hits += 1
        rows.append(
            {
                "idea_group": group,
                "keyword_hits": keyword_hits,
                "documents_with_group": doc_hits,
                "document_share": round(doc_hits / total_docs, 4),
                "top_terms": ", ".join(term for term, _ in matched_terms.most_common(8)),
            }
        )
    return sorted(rows, key=lambda row: row["keyword_hits"], reverse=True)


def idea_group_counts_by_year(records: list[dict], groups: dict[str, list[str]] | None = None) -> list[dict]:
    by_year: dict[int, list[dict]] = defaultdict(list)
    for record in records:
        year = int(record.get("year", 0) or 0)
        if year:
            by_year[year].append(record)
    rows = []
    for year, group_records in sorted(by_year.items()):
        for row in idea_group_counts(group_records, groups):
            rows.append({"year": year, **row})
    return rows


def idea_group_document_matrix(records: list[dict], groups: dict[str, list[str]] | None = None) -> list[dict]:
    groups = groups or idea_groups_for_records(records)
    rows = []
    for index, record in enumerate(records, start=1):
        text = record_text(record).lower()
        base = {
            "doc_id": index,
            "year": record.get("year"),
            "medium": record.get("medium"),
            "language": record.get("analysis_language", record.get("language")),
            "localization": record.get("localization", "Global/unclear"),
            "title": record.get("title", ""),
        }
        for group, keywords in groups.items():
            base[group] = sum(len(re.findall(rf"\b{re.escape(keyword.lower())}\b", text)) for keyword in keywords)
        rows.append(base)
    return rows


def ngram_dimension_matrix(
    records: list[dict],
    *,
    dimension: str = "medium",
    n_values: Iterable[int] = (1, 2),
    top_terms: int = 80,
    extra_stopwords: Iterable[str] | None = None,
) -> list[dict]:
    """Build a local term-dimension matrix in long format.

    This is a lightweight local equivalent of the term-source and term-month
    matrices used in older scripts: counts are computed after the same tokenizer
    and stopword cleaning used by the narrative graphs. Values are normalized in
    [0,1] by the largest count observed for the selected matrix.
    """
    global_counts: Counter[str] = Counter()
    by_dimension: dict[str, Counter[str]] = defaultdict(Counter)
    for record in records:
        if record.get("status") not in {"ok", "ok_partial", "too_short"}:
            continue
        if dimension == "year":
            dimension_value = str(record.get("year") or "unknown")
        elif dimension == "source_type":
            dimension_value = str(record.get("source_type") or "other")
        else:
            dimension_value = str(record.get(dimension) or record.get("medium") or "unknown")
        grams = record_ngrams(record, n_values=n_values, extra_stopwords=extra_stopwords)
        counts = Counter(grams)
        global_counts.update(counts)
        by_dimension[dimension_value].update(counts)
    top = {term for term, _ in global_counts.most_common(max(1, int(top_terms)))}
    max_count = max(
        [count for counts in by_dimension.values() for term, count in counts.items() if term in top] or [1]
    )
    rows = []
    for dimension_value, counts in sorted(by_dimension.items()):
        dimension_total = sum(counts.get(term, 0) for term in top)
        for term in sorted(top, key=lambda item: (-global_counts[item], item)):
            count = counts.get(term, 0)
            if count <= 0:
                continue
            rows.append(
                {
                    "dimension": dimension,
                    "dimension_value": dimension_value,
                    "term": term,
                    "count": count,
                    "count_norm": round(count / max_count, 6),
                    "within_dimension_share": round(count / max(1, dimension_total), 6),
                    "global_count": global_counts[term],
                }
            )
    return rows


def frame_counts_by_year(records: list[dict]) -> list[dict]:
    by_year: dict[int, list[dict]] = defaultdict(list)
    for record in records:
        year = int(record.get("year", 0) or 0)
        if year:
            by_year[year].append(record)
    rows = []
    for year, group in sorted(by_year.items()):
        for row in frame_counts(group):
            rows.append({"year": year, **row})
    return rows


def build_cooccurrence_network(
    records: list[dict],
    top_n_terms: int = 50,
    window_size: int = 4,
    min_cooccurrence: int = 2,
    extra_stopwords: Iterable[str] | None = None,
    community_algorithm: str = "louvain",
) -> dict:
    phrase_rows = top_mixed_ngrams(
        records,
        top_n_each=top_n_terms,
        min_count=max(2, min_cooccurrence),
        extra_stopwords=extra_stopwords,
    )
    canonical_terms = {
        row["node"] for row in phrase_rows
        if row.get("node_type") != "absorbed_ngram" and row.get("count", 0) >= max(2, min_cooccurrence)
    }
    tokens_by_doc = [canonicalize_record_terms(record, canonical_terms, extra_stopwords) for record in records]
    term_counts = Counter(token for tokens in tokens_by_doc for token in tokens)
    vocabulary = {term for term, _ in term_counts.most_common(top_n_terms)}
    node_type_by_term = {
        row["node"]: row.get("node_type", "term")
        for row in phrase_rows
        if row["node"] in vocabulary
    }
    absorbed_rows = [row for row in phrase_rows if row.get("node_type") == "absorbed_ngram"]
    edge_counts: Counter[tuple[str, str]] = Counter()

    for tokens in tokens_by_doc:
        tokens = [token for token in tokens if token in vocabulary]
        for i, token in enumerate(tokens):
            window = tokens[i + 1:i + 1 + window_size]
            for other in window:
                if token != other:
                    edge_counts[tuple(sorted((token, other)))] += 1

    edges = [
        {"source": source, "target": target, "edge_type": "cooccurrence", "weight": weight}
        for (source, target), weight in edge_counts.items()
        if weight >= min_cooccurrence
    ]
    weighted_degree = Counter()
    degree = Counter()
    for edge in edges:
        weighted_degree[edge["source"]] += edge["weight"]
        weighted_degree[edge["target"]] += edge["weight"]
        degree[edge["source"]] += 1
        degree[edge["target"]] += 1

    nodes = [
        {
            "id": term,
            "label": term,
            "node_type": node_type_by_term.get(term, "term"),
            "term": term,
            "frequency": term_counts[term],
            "count": term_counts[term],
            "degree": degree[term],
            "weighted_degree_raw": weighted_degree[term],
            "weighted_degree": weighted_degree[term],
            "score": round(term_counts[term] + weighted_degree[term], 3),
        }
        for term in vocabulary
        if degree[term] > 0 or term_counts[term] > 0
    ]
    add_normalized_graph_weights(nodes, edges, node_count_field="frequency")
    nodes = sorted(nodes, key=lambda row: (row["weighted_degree"], row["frequency"]), reverse=True)

    community_result = detect_weighted_communities(
        nodes,
        edges,
        node_key="id",
        requested_algorithm=community_algorithm,
    )
    community_by_node = {}
    for community in community_result["communities"]:
        for term in [item.strip() for item in community.get("terms", "").split(",") if item.strip()]:
            community_by_node[term] = community["community"]
    for node in nodes:
        node["community"] = community_by_node.get(node["id"], "")
    node_count = len(nodes)
    edge_count = len(edges)
    density = 0 if node_count < 2 else round((2 * edge_count) / (node_count * (node_count - 1)), 5)
    return {
        "nodes": nodes,
        "edges": sorted(edges, key=lambda row: row["weight"], reverse=True),
        "communities": community_result["communities"],
        "stats": {
            "nodes": node_count,
            "edges": edge_count,
            "density": density,
            "communities": len(community_result["communities"]),
            "average_degree": round(sum(row["degree"] for row in nodes) / max(1, node_count), 3),
            "community_algorithm": community_result["algorithm"],
            "modularity": community_result.get("modularity"),
            "total_raw_edge_weight": round(sum(edge.get("raw_weight", 0) for edge in edges), 3),
            "absorbed_ngrams": len(absorbed_rows),
            **graph_weight_distribution_stats(nodes, edges),
        },
        "phrase_composition": absorbed_rows,
    }


def build_knowledge_graph(
    records: list[dict],
    top_n_each: int = 30,
    min_node_count: int = 2,
    min_edge_weight: int = 2,
    extra_stopwords: Iterable[str] | None = None,
) -> dict:
    """Build a local knowledge graph with monograms, bigrams, trigrams, sources and metadata."""
    candidate_rows = top_mixed_ngrams(records, top_n_each=top_n_each, min_count=max(2, min_node_count), extra_stopwords=extra_stopwords)
    absorbed_rows = [row for row in candidate_rows if row.get("node_type") == "absorbed_ngram"]
    candidate_nodes = {
        row["node"] for row in candidate_rows
        if row["count"] >= max(2, min_node_count) and row.get("node_type") != "absorbed_ngram"
    }
    node_meta = {
        row["node"]: {
            "id": row["node"],
            "label": row["node"],
            "node_type": row["node_type"],
            "count": row["count"],
            "absorbed_by": row.get("absorbed_by", ""),
        }
        for row in candidate_rows
        if row["node"] in candidate_nodes
    }

    edge_counts: Counter[tuple[str, str, str]] = Counter()
    source_counts = Counter()
    year_counts = Counter()
    localization_counts = Counter()

    for record in records:
        source = f"source::{record.get('medium') or 'unknown'}"
        year = f"year::{record.get('year') or 'unknown'}"
        localization = f"geo::{record.get('localization') or 'Global/unclear'}"
        flow_info = narrative_flow_stage(record.get("source_type") or "other")
        flow = f"flow::{record.get('narrative_flow_stage') or flow_info['narrative_flow_stage']}"

        doc_grams = set(canonicalize_record_terms(record, candidate_nodes, extra_stopwords))
        doc_nodes = sorted(doc_grams & candidate_nodes)
        for node in doc_nodes:
            source_counts[(source, node)] += 1
            year_counts[(year, node)] += 1
            localization_counts[(localization, node)] += 1
            edge_counts[tuple(sorted((source, node))) + ("source_term",)] += 1
            edge_counts[tuple(sorted((year, node))) + ("year_term",)] += 1
            edge_counts[tuple(sorted((localization, node))) + ("geo_term",)] += 1
            edge_counts[tuple(sorted((flow, node))) + ("flow_term",)] += 1
        for a, b in combinations(doc_nodes[:80], 2):
            edge_counts[tuple(sorted((a, b))) + ("co_document",)] += 1

    metadata_nodes = set()
    for (a, b, _kind), weight in edge_counts.items():
        if weight >= min_edge_weight:
            for node in (a, b):
                if node.startswith(("source::", "year::", "geo::", "flow::")):
                    metadata_nodes.add(node)

    nodes = list(node_meta.values())
    for node in sorted(metadata_nodes):
        if node.startswith("source::"):
            node_type = "source"
            label = node.replace("source::", "")
        elif node.startswith("year::"):
            node_type = "year"
            label = node.replace("year::", "")
        elif node.startswith("geo::"):
            node_type = "localization"
            label = node.replace("geo::", "")
        elif node.startswith("flow::"):
            node_type = "narrative_flow"
            label = node.replace("flow::", "")
        else:
            node_type = "metadata"
            label = node
        nodes.append({"id": node, "label": label, "node_type": node_type, "count": 0})

    edges = [
        {"source": a, "target": b, "edge_type": kind, "weight": weight}
        for (a, b, kind), weight in edge_counts.items()
        if weight >= min_edge_weight and (a in node_meta or a in metadata_nodes) and (b in node_meta or b in metadata_nodes)
    ]
    weighted_degree = Counter()
    degree = Counter()
    for edge in edges:
        weighted_degree[edge["source"]] += edge["weight"]
        weighted_degree[edge["target"]] += edge["weight"]
        degree[edge["source"]] += 1
        degree[edge["target"]] += 1
    for node in nodes:
        node["degree"] = degree[node["id"]]
        node["weighted_degree_raw"] = weighted_degree[node["id"]]
        node["weighted_degree"] = weighted_degree[node["id"]]
        node["knowledge_degree_raw"] = round(weighted_degree[node["id"]] + float(node.get("count", 0) or 0), 3)

    add_normalized_graph_weights(nodes, edges, node_count_field="count")
    for node in nodes:
        node["knowledge_degree"] = node["score"]

    nodes = sorted(nodes, key=lambda row: (row.get("knowledge_degree", 0), row["weighted_degree"], row["count"]), reverse=True)
    communities = connected_components(
        [{"term": node["id"]} for node in nodes],
        [{"source": edge["source"], "target": edge["target"], "weight": edge["weight"]} for edge in edges],
    )
    return {
        "nodes": nodes,
        "edges": sorted(edges, key=lambda row: row["weight"], reverse=True),
        "communities": communities,
        "stats": {
            "nodes": len(nodes),
            "edges": len(edges),
            "communities": len(communities),
            "monograms": sum(1 for node in nodes if node["node_type"] == "monogram"),
            "bigrams": sum(1 for node in nodes if node["node_type"] == "bigram"),
            "trigrams": sum(1 for node in nodes if node["node_type"] == "trigram"),
            "absorbed_ngrams": len(absorbed_rows),
            "sources": sum(1 for node in nodes if node["node_type"] == "source"),
            "narrative_flow_nodes": sum(1 for node in nodes if node["node_type"] == "narrative_flow"),
            "total_raw_edge_weight": round(sum(edge.get("raw_weight", 0) for edge in edges), 3),
            **graph_weight_distribution_stats(nodes, edges),
        },
        "phrase_composition": absorbed_rows,
    }


def adaptive_topic_groups_from_graph(graph: dict, max_groups: int = 12, terms_per_group: int = 12) -> list[dict]:
    node_by_id = {node["id"]: node for node in graph.get("nodes", [])}
    rows = []
    for community in graph.get("communities", [])[:max_groups]:
        ids = [item.strip() for item in community.get("terms", "").split(",") if item.strip()]
        terms = [
            node_by_id[node_id] for node_id in ids
            if node_id in node_by_id and node_by_id[node_id].get("node_type") in {"monogram", "bigram", "trigram"}
        ]
        terms.sort(key=lambda node: (node.get("weighted_degree", 0), node.get("count", 0)), reverse=True)
        central = terms[0]["label"] if terms else f"grupo_{community.get('community')}"
        rows.append(
            {
                "topic_group": f"topic_{community.get('community')}_{central.replace(' ', '_')[:40]}",
                "central_ngram": central,
                "size": community.get("size", 0),
                "terms": ", ".join(node["label"] for node in terms[:terms_per_group]),
            }
        )
    return rows


def connected_components(nodes: list[dict], edges: list[dict]) -> list[dict]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for node in nodes:
        adjacency[node["term"]]
    for edge in edges:
        adjacency[edge["source"]].add(edge["target"])
        adjacency[edge["target"]].add(edge["source"])

    seen = set()
    communities = []
    for node in adjacency:
        if node in seen:
            continue
        stack = [node]
        component = []
        seen.add(node)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in adjacency[current]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        communities.append(sorted(component))
    communities = sorted(communities, key=len, reverse=True)
    return [
        {"community": index + 1, "size": len(items), "terms": ", ".join(items[:20])}
        for index, items in enumerate(communities)
    ]


def community_rows_from_sets(communities: Iterable[Iterable[str]]) -> list[dict]:
    ordered = [sorted({str(item) for item in community if str(item)}) for community in communities]
    ordered = sorted([items for items in ordered if items], key=len, reverse=True)
    return [
        {
            "community": index + 1,
            "size": len(items),
            "terms": ", ".join(items[:40]),
        }
        for index, items in enumerate(ordered)
    ]


def weighted_modularity_for_partition(
    node_ids: list[str],
    edge_weights: dict[tuple[str, str], float],
    partition: dict[str, int],
) -> float:
    adjacency_weight = Counter()
    total_weight = 0.0
    for (a, b), weight in edge_weights.items():
        adjacency_weight[a] += weight
        adjacency_weight[b] += weight
        total_weight += weight
    if total_weight <= 0:
        return 0.0
    two_m = 2.0 * total_weight
    modularity = 0.0
    for a in node_ids:
        for b in node_ids:
            if partition.get(a) != partition.get(b):
                continue
            weight = edge_weights.get(tuple(sorted((a, b))), 0.0)
            modularity += weight - (adjacency_weight[a] * adjacency_weight[b] / two_m)
    return modularity / two_m


def local_louvain_communities(nodes: list[dict], edges: list[dict], node_key: str = "term") -> dict:
    """Small local Louvain-like modularity optimizer.

    It performs the first Louvain phase: repeatedly move each node to the
    neighboring community that gives the largest modularity gain. This avoids
    external dependencies and is enough for exploratory local analysis.
    """
    node_ids = [str(node.get(node_key) or node.get("id") or node.get("term")) for node in nodes]
    edge_weights: dict[tuple[str, str], float] = defaultdict(float)
    neighbors: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        a = str(edge.get("source"))
        b = str(edge.get("target"))
        if not a or not b or a == b:
            continue
        key = tuple(sorted((a, b)))
        edge_weights[key] += float(edge.get("weight", 1) or 1)
        neighbors[a].add(b)
        neighbors[b].add(a)

    partition = {node_id: index for index, node_id in enumerate(node_ids)}
    current_modularity = weighted_modularity_for_partition(node_ids, edge_weights, partition)
    max_passes = 20
    for _ in range(max_passes):
        improved = False
        for node_id in node_ids:
            original_community = partition[node_id]
            candidate_communities = {partition[neighbor] for neighbor in neighbors.get(node_id, set())}
            best_community = original_community
            best_modularity = current_modularity
            for community in candidate_communities:
                if community == original_community:
                    continue
                trial = dict(partition)
                trial[node_id] = community
                trial_modularity = weighted_modularity_for_partition(node_ids, edge_weights, trial)
                if trial_modularity > best_modularity + 1e-10:
                    best_modularity = trial_modularity
                    best_community = community
            if best_community != original_community:
                partition[node_id] = best_community
                current_modularity = best_modularity
                improved = True
        if not improved:
            break

    grouped: dict[int, set[str]] = defaultdict(set)
    for node_id, community in partition.items():
        grouped[community].add(node_id)
    return {
        "algorithm": "louvain_local",
        "modularity": round(float(current_modularity), 5),
        "communities": community_rows_from_sets(grouped.values()),
    }


def detect_weighted_communities(
    nodes: list[dict],
    edges: list[dict],
    node_key: str = "term",
    requested_algorithm: str = "louvain",
) -> dict:
    """Detect weighted communities locally.

    Preferred method is Louvain through networkx when available. If the local
    environment does not include it, the function falls back to greedy
    modularity and then to connected components. No network/API call is used.
    """
    node_ids = [str(node.get(node_key) or node.get("id") or node.get("term")) for node in nodes]
    try:
        import networkx as nx  # type: ignore

        graph = nx.Graph()
        graph.add_nodes_from(node_ids)
        for edge in edges:
            graph.add_edge(
                str(edge.get("source")),
                str(edge.get("target")),
                weight=float(edge.get("weight", 1) or 1),
            )
        if graph.number_of_edges() == 0:
            return {"algorithm": "none", "modularity": 0.0, "communities": community_rows_from_sets([{node} for node in node_ids])}

        algorithm = (requested_algorithm or "louvain").lower()
        if algorithm == "connected_components":
            communities = list(nx.connected_components(graph))
            return {
                "algorithm": "connected_components",
                "modularity": "",
                "communities": community_rows_from_sets(communities),
            }
        if algorithm == "louvain" and hasattr(nx.algorithms.community, "louvain_communities"):
            communities = nx.algorithms.community.louvain_communities(graph, weight="weight", seed=42)
            modularity = nx.algorithms.community.modularity(graph, communities, weight="weight")
            return {
                "algorithm": "louvain",
                "modularity": round(float(modularity), 5),
                "communities": community_rows_from_sets(communities),
            }

        communities = nx.algorithms.community.greedy_modularity_communities(graph, weight="weight")
        modularity = nx.algorithms.community.modularity(graph, communities, weight="weight")
        return {
            "algorithm": "greedy_modularity",
            "modularity": round(float(modularity), 5),
            "communities": community_rows_from_sets(communities),
        }
    except Exception:
        if (requested_algorithm or "louvain").lower() == "louvain":
            return local_louvain_communities(nodes, edges, node_key=node_key)
        fallback_rows = connected_components(
            [{"term": node_id} for node_id in node_ids],
            [{"source": edge.get("source"), "target": edge.get("target"), "weight": edge.get("weight", 1)} for edge in edges],
        )
        return {"algorithm": "connected_components_fallback", "modularity": "", "communities": fallback_rows}


def pareto_terms(term_rows: list[dict]) -> list[dict]:
    total = sum(row["count"] for row in term_rows) or 1
    cumulative = 0
    output = []
    for row in term_rows:
        cumulative += row["count"]
        output.append(
            {
                **row,
                "share": round(row["count"] / total, 4),
                "cumulative_share": round(cumulative / total, 4),
            }
        )
    return output


def rows_to_csv(rows: list[dict]) -> bytes:
    if not rows:
        return b""
    import io

    fieldnames: list[str] = []
    seen_fields: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key not in seen_fields:
                seen_fields.add(key)
                fieldnames.append(key)

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")
