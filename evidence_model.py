"""Evidence-aware metadata and descriptive analysis; no network or imputation.

Missing values are never zero. Legacy search years are not publication years.
Human interpretations must have a verbatim quote and an explicit review state.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import re
from collections import Counter, defaultdict
from html.parser import HTMLParser
from urllib.parse import urlparse

SCHEMA_VERSION = 1
STATES = {"explicit", "inferred", "not_found", "not_evaluable", "not_applicable", "conflicting"}
FIELDS = ("author", "publication_date", "update_date", "consultation_date", "publication_source", "text")
STATE_LABELS = {
    "explicit": "Encontrado explícitamente", "inferred": "Inferido",
    "not_found": "Buscado y no encontrado", "not_evaluable": "No evaluable",
    "not_applicable": "No aplica", "conflicting": "Evidencias contradictorias",
}
ANALYSIS_LABELS = {
    "thematic": "Exploración temática", "source_comparison": "Comparación por fuente",
    "temporal": "Comparación temporal (publicación)", "claims": "Afirmaciones revisadas",
    "actor_stance": "Red actor–concepto–postura", "narrative": "Estructura narrativa revisada",
    "reception": "Recepción documentada",
}


def cell(value=None, state="not_evaluable", evidence="", method="", **extra):
    if state not in STATES:
        raise ValueError(f"Unknown evidence state: {state}")
    return {"value": value, "state": state, "evidence": evidence, "method": method, **extra}


def date_precision(value):
    """ISO date precision; reject impossible dates and invented month/day."""
    text = str(value or "").strip()
    if re.fullmatch(r"\d{4}", text):
        return "year" if 1 <= int(text) <= 9999 else None
    if re.fullmatch(r"\d{4}-\d{2}", text):
        try:
            dt.date.fromisoformat(text + "-01")
            return "month"
        except ValueError:
            return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[T ].+)?", text):
        try:
            dt.date.fromisoformat(text[:10])
            if len(text) > 10:
                dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
            return "day"
        except ValueError:
            return None
    return None


def _names(value):
    if isinstance(value, dict):
        return _names(value.get("name"))
    if isinstance(value, list):
        return [name for item in value for name in _names(item)]
    return [str(value).strip()] if value else []


class MetadataParser(HTMLParser):
    """Look only at labelled publication metadata, never arbitrary years."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.candidates = defaultdict(list)
        self.ld = False
        self.buffer = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        key = (attrs.get("name") or attrs.get("property") or "").lower()
        mapping = {"author": "author", "dc.creator": "author", "citation_author": "author",
                   "article:published_time": "publication_date", "citation_publication_date": "publication_date",
                   "datepublished": "publication_date", "article:modified_time": "update_date",
                   "og:site_name": "publication_source", "citation_journal_title": "publication_source"}
        if tag == "meta" and key in mapping and attrs.get("content"):
            self.candidates[mapping[key]].append((attrs["content"], f"meta:{key}"))
        if tag == "time" and attrs.get("itemprop") in {"datePublished", "dateModified"} and attrs.get("datetime"):
            field = "publication_date" if attrs["itemprop"] == "datePublished" else "update_date"
            self.candidates[field].append((attrs["datetime"], "time:" + attrs["itemprop"]))
        if tag == "script" and attrs.get("type", "").lower() == "application/ld+json":
            self.ld, self.buffer = True, []

    def handle_data(self, data):
        if self.ld:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.ld:
            self.ld = False
            try:
                self._visit(json.loads("".join(self.buffer)))
            except (ValueError, TypeError):
                pass

    def _visit(self, obj):
        if isinstance(obj, list):
            for item in obj:
                self._visit(item)
        elif isinstance(obj, dict):
            # Only document nodes; organisation/website authors do not sign articles.
            kinds = obj.get("@type", [])
            kinds = [kinds] if isinstance(kinds, str) else kinds
            if set(kinds) & {"Article", "NewsArticle", "ScholarlyArticle", "BlogPosting", "Report", "WebPage"}:
                for key, field in [("author", "author"), ("datePublished", "publication_date"),
                                   ("dateModified", "update_date"), ("publisher", "publication_source")]:
                    for value in _names(obj.get(key)):
                        self.candidates[field].append((value, "jsonld:" + key))
            self._visit(obj.get("@graph", []))


def extract_publication_metadata(page_html):
    parser = MetadataParser()
    parser.feed(page_html or "")
    result = {}
    for field in FIELDS[:3] + ("publication_source",):
        items = list(dict.fromkeys(parser.candidates[field]))
        if not items:
            result[field] = cell(state="not_found", method="html_labelled_metadata_search")
        elif field == "author":
            result[field] = cell(list(dict.fromkeys(v for v, _ in items)), "explicit", items, "html_metadata")
        else:
            valid = [(v, m) for v, m in items if not field.endswith("date") or date_precision(v)]
            values = list(dict.fromkeys(v for v, _ in valid))
            if not valid:
                result[field] = cell(state="not_evaluable", evidence=items, method="invalid_date_format")
            elif len(values) > 1:
                result[field] = cell(state="conflicting", evidence=items, method="html_metadata", candidates=values)
            else:
                result[field] = cell(values[0], "explicit", valid, "html_metadata",
                                     **({"precision": date_precision(values[0])} if field.endswith("date") else {}))
    return result


def document_id(row):
    key = row.get("document_id") or row.get("url") or row.get("doi") or row.get("pdf_url")
    if not key:
        key = json.dumps({k: row.get(k) for k in ("title", "medium", "text_clean", "text_raw_visible")},
                         ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(str(key).encode()).hexdigest()[:24]


def normalize_record(record):
    """Preserve raw fields, reviewed metadata and conflicts; migrate legacy rows."""
    row = copy.deepcopy(record)
    info = copy.deepcopy(row.get("record_information") or {})
    # Existing evidence is authoritative, including explicit missing states.
    for field in FIELDS:
        if field in info:
            if info[field].get("state") not in STATES:
                raise ValueError(f"Invalid evidence state for {field}")
            continue
        if field == "author":
            names = _names(row.get("authors") or row.get("author"))
            searched = any(x in str(row.get("source_api") or "").lower() for x in ("openalex", "crossref", "redalyc", "rss"))
            info[field] = cell(names or None, "explicit" if names else ("not_found" if searched else "not_evaluable"),
                               "record.authors/author" if names else "", "legacy_import")
        elif field == "publication_source":
            source = row.get("medium") or row.get("publication_source")
            host = urlparse(str(row.get("url") or "")).hostname
            if source and str(source).lower() not in {"unknown", "unclear", "openalex", "crossref", "redalyc"} and str(source).removeprefix("www.") != str(host).removeprefix("www."):
                info[field] = cell(source, "explicit", "record.medium", "legacy_import")
            else:
                info[field] = cell(host, "inferred" if host else "not_evaluable", "url.hostname", "domain_only")
        elif field in {"publication_date", "update_date", "consultation_date"}:
            key = {"publication_date": "published_date", "update_date": "updated_date", "consultation_date": "fetched_at"}[field]
            value = row.get(key)
            precision = date_precision(value)
            state = "explicit" if precision else "not_evaluable"
            if field == "publication_date":
                api = str(row.get("source_api") or "").lower()
                if "gdelt" in api or row.get("published_date_kind") == "observation":
                    state = "not_evaluable"  # seendate is index observation time.
                elif not any(x in api for x in ("openalex", "crossref", "rss", "redalyc")) and not row.get("published_date_verified"):
                    state = "inferred" if precision else "not_evaluable"
            info[field] = cell(value if precision else None, state, f"record.{key}" if value else "",
                               "legacy_import", precision=precision)
        else:
            text = str(row.get("pdf_text_clean") or row.get("text_clean") or row.get("text_raw_visible") or "")
            status = row.get("status")
            usable = bool(text.strip()) and status not in {"fetch_error", "error"}
            info[field] = cell(text if usable else None, "explicit" if usable else "not_evaluable",
                               "record.text", "local_extraction",
                               coverage="partial" if status in {"ok_partial", "too_short"} or any("metadata" in str(n) for n in row.get("cleaning_notes", [])) and not row.get("pdf_text_clean") else "unverified_extent")
    row["record_information"] = info
    row["information_schema_version"] = SCHEMA_VERSION
    row["document_id"] = row.get("document_id") or document_id(record)
    row.setdefault("search_year", record.get("year"))
    pub = info["publication_date"]
    usable_date = pub.get("state") == "explicit" and date_precision(pub.get("value"))
    row["year"] = int(str(pub["value"])[:4]) if usable_date else None
    row.setdefault("claims", [])
    from record_schema import upgrade_record
    return upgrade_record(row)


def claim_is_valid(claim, row, require_actor=False):
    text = str(row["record_information"]["text"].get("value") or "")
    quote = str(claim.get("quote") or "").strip()
    if claim.get("review_status") != "validated" or not quote or quote not in text:
        return False
    if not claim.get("concept") or not claim.get("statement"):
        return False
    if require_actor:
        return bool(claim.get("speaker") and claim.get("speaker_evidence") in quote
                    and claim.get("speaker_evidence") and claim.get("stance") in {"support", "reject", "ambivalent"})
    return True


def eligibility(record, analysis, temporal_precision="year"):
    row = normalize_record(record)
    info = row["record_information"]
    if row.get("selection", {}).get("state") == "excluded":
        return False, "documento_excluido_por_revision"
    if not info["text"].get("value"):
        return False, "sin_texto_utilizable"
    if analysis == "thematic":
        return True, "fragmento" if info["text"].get("coverage") == "partial" else "texto_recuperado"
    if analysis == "source_comparison":
        return (True, "fuente_identificada") if info["publication_source"].get("value") and info["publication_source"]["state"] == "explicit" else (False, "fuente_no_identificada")
    if analysis == "temporal":
        field = info["publication_date"]
        rank = {"year": 1, "month": 2, "day": 3}
        if temporal_precision not in rank:
            raise ValueError("Precision must be year, month or day")
        precision = date_precision(field.get("value"))
        ok = field["state"] == "explicit" and rank.get(precision, 0) >= rank[temporal_precision]
        return ok, "fecha_publicacion_utilizable" if ok else "fecha_ausente_ambigua_o_precision_insuficiente"
    if analysis in {"claims", "actor_stance"}:
        ok = any(claim_is_valid(c, row, analysis == "actor_stance") for c in row["claims"])
        return ok, "afirmacion_validada" if ok else "sin_afirmaciones_validadas_con_evidencia"
    if analysis in {"narrative", "reception"}:
        item = row.get("reviewed_narrative" if analysis == "narrative" else "reviewed_reception") or {}
        quote = str(item.get("quote") or "").strip()
        ok = item.get("review_status") == "validated" and bool(item.get("description")) and bool(quote) and quote in info["text"]["value"]
        return ok, "interpretacion_revisada" if ok else "sin_evidencia_revisada"
    raise ValueError(f"Unknown analysis: {analysis}")


def coverage_report(records, temporal_precision="year"):
    rows = [normalize_record(r) for r in records]
    result = {"schema_version": SCHEMA_VERSION, "total": len(rows), "analyses": {}, "fields": {}, "by_source_type": {}}
    for field in FIELDS:
        result["fields"][field] = dict(Counter(r["record_information"][field]["state"] for r in rows))
    for analysis in ANALYSIS_LABELS:
        ids, reasons, by_type = [], Counter(), defaultdict(lambda: {"total": 0, "eligible": 0})
        for row in rows:
            ok, reason = eligibility(row, analysis, temporal_precision)
            group = str(row.get("source_type") or "unknown")
            by_type[group]["total"] += 1
            if ok:
                ids.append(row["document_id"])
                by_type[group]["eligible"] += 1
            else:
                reasons[reason] += 1
        result["analyses"][analysis] = {"eligible": len(ids), "total": len(rows),
            "coverage": len(ids) / len(rows) if rows else None, "document_ids": ids,
            "excluded_reasons": dict(reasons), "by_source_type": dict(by_type),
            "status": "available_descriptive" if ids else "unavailable"}
    return result


def descriptive_models(records, temporal_precision="year"):
    """Document denominators and separate support/rejection; no causal/population inference."""
    rows = [normalize_record(r) for r in records]
    reviewed = [r for r in rows if eligibility(r, "claims")[0]]
    concepts = sorted({c["concept"] for r in reviewed for c in r["claims"] if claim_is_valid(c, r)})
    matrix, positions, temporal, relations = [], Counter(), Counter(), []
    for row in reviewed:
        valid = [c for c in row["claims"] if claim_is_valid(c, row)]
        detected = {c["concept"] for c in valid}
        # 0 requires explicit complete review of the concept inventory.
        complete = set(row.get("reviewed_concepts") or [])
        for concept in concepts:
            matrix.append({"document_id": row["document_id"], "concept": concept,
                           "value": 1 if concept in detected else (0 if concept in complete else None)})
        for c in valid:
            if claim_is_valid(c, row, True):
                positions[(c["speaker"], c["concept"], c["stance"])] += 1
            for relation in c.get("relations", []):
                if relation.get("source") and relation.get("target") and relation.get("type"):
                    relations.append({**relation, "document_id": row["document_id"], "quote": c["quote"],
                                      "interpretation": "relation_asserted_in_text"})
        if eligibility(row, "temporal", temporal_precision)[0]:
            date = str(row["record_information"]["publication_date"]["value"])
            period = date[:{"year": 4, "month": 7, "day": 10}[temporal_precision]]
            for concept in detected:
                temporal[(period, concept)] += 1
    denominators = Counter()
    positives = Counter()
    for item in matrix:
        if item["value"] is not None:
            row = next(r for r in reviewed if r["document_id"] == item["document_id"])
            source = row["record_information"]["publication_source"]
            # Unknown/domain-only sources remain outside named-source comparisons.
            if source["state"] == "explicit" and source.get("value"):
                key = (str(source["value"]), item["concept"])
                denominators[key] += 1
                positives[key] += item["value"]
    source_summary = [{"source": s, "concept": k, "documents_with_concept": positives[(s, k)],
                       "documents_reviewed_for_concept": n, "proportion": positives[(s, k)] / n}
                      for (s, k), n in sorted(denominators.items())]
    reviewed_temporal = [r for r in reviewed if eligibility(r, "temporal", temporal_precision)[0]]
    return {"coverage": coverage_report(rows, temporal_precision), "document_concept_matrix": matrix,
            "source_concept_summary": source_summary,
            "temporal_model_coverage": {"eligible": len(reviewed_temporal), "total": len(rows),
                                       "document_ids": [r["document_id"] for r in reviewed_temporal]},
            "actor_concept_stance": [{"actor": a, "concept": k, "stance": s, "claims": n} for (a, k, s), n in sorted(positions.items())],
            "temporal_reviewed_concepts": [{"period": t, "concept": k, "documents": n} for (t, k), n in sorted(temporal.items())],
            "asserted_relations": relations,
            "limitations": ["Descriptive corpus results, not population opinion or causal effects.",
                            "Unreviewed concepts are null, never zero.",
                            "Multiple documents/claims may depend on the same institution or event.",
                            "Temporal concept counts cover reviewed AND explicitly dated documents only."]}


def metadata_audit_rows(records):
    result = []
    for record in records:
        row = normalize_record(record)
        for field, item in row["record_information"].items():
            value = item.get("value")
            result.append({"document_id": row["document_id"], "title": row.get("title"), "field": field,
                           "value": (f"{len(value)} caracteres" if field == "text" and isinstance(value, str) else value),
                           "state": item.get("state"), "method": item.get("method"),
                           "precision": item.get("precision"), "evidence": item.get("evidence")})
    return result


def apply_reviews(records, reviews):
    """Apply explicit reviewer input by stable ID; reject unsupported quotations."""
    rows = [normalize_record(r) for r in records]
    lookup = {r["document_id"]: r for r in rows}
    seen = set()
    for review in reviews:
        key = review.get("document_id")
        if key not in lookup or key in seen:
            raise ValueError("Unknown or duplicate document_id in review")
        seen.add(key)
        row = lookup[key]
        for field, item in (review.get("record_information") or {}).items():
            if field not in FIELDS or field == "text":
                raise ValueError("Reviews cannot replace text or introduce unknown metadata fields")
            if item.get("state") not in STATES:
                raise ValueError("Invalid evidence state")
            if item["state"] in {"explicit", "inferred"} and (not item.get("value") or not item.get("evidence")):
                raise ValueError("A metadata value requires evidence")
            if field.endswith("date") and item.get("value") and not date_precision(item["value"]):
                raise ValueError("Invalid ISO date or precision")
            row["record_information"][field] = {**item, "method": "human_review"}
        row = normalize_record(row)
        for claim in review.get("claims", []):
            if not claim_is_valid(claim, row):
                raise ValueError("Validated claims require concept, statement and verbatim quote in recovered text")
            if claim.get("stance") not in {None, "support", "reject", "ambivalent", "indeterminate"}:
                raise ValueError("Invalid stance")
        for kind in ("reviewed_narrative", "reviewed_reception"):
            if kind in review:
                row[kind] = copy.deepcopy(review[kind])
                if not eligibility(row, "narrative" if kind == "reviewed_narrative" else "reception")[0]:
                    raise ValueError("Interpretation requires description and verbatim evidence")
        if "claims" in review:
            row["claims"] = copy.deepcopy(review["claims"])
        if "reviewed_concepts" in review:
            row["reviewed_concepts"] = list(review["reviewed_concepts"])
        lookup[key] = row
    return [lookup[r["document_id"]] for r in rows]
