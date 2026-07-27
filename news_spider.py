#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import hashlib
import html
import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.robotparser
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable

from source_profiles import (
    COMMON_NEWS_TAIL_CUT_MARKERS,
    DEFAULT_FORUM_DOMAINS,
    source_access_policy,
    source_tail_cut_markers,
)


GDELT_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
OPENALEX_WORKS_ENDPOINT = "https://api.openalex.org/works"
GOOGLE_NEWS_RSS_ENDPOINT = "https://news.google.com/rss/search"
CROSSREF_WORKS_ENDPOINT = "https://api.crossref.org/works"
REDALYC_BASE_URL = "https://www.redalyc.org"
REDDIT_SEARCH_RSS_ENDPOINT = "https://www.reddit.com/search.rss"
USER_AGENT = "Mozilla/5.0 (compatible; SIANNarrativeResearch/1.0; +https://github.com/RomanUAM/sian-smart-data-narrativo)"
ALLOW_SSL_FALLBACK = True
ROBOTS_CACHE: dict[str, urllib.robotparser.RobotFileParser | None] = {}


def unique_sequence(items: Iterable[str]) -> list[str]:
    """Return non-empty strings preserving first occurrence order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        value = str(item or "").strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def default_ssl_context() -> ssl.SSLContext:
    """Return the best available SSL context for local macOS/Python installs."""
    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def open_url(req: urllib.request.Request, timeout: int = 30):
    """Open an URL with normal certificate validation, then fallback if local certs are broken."""
    try:
        return urllib.request.urlopen(req, timeout=timeout, context=default_ssl_context())
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        is_cert_error = isinstance(reason, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(exc)
        if not (ALLOW_SSL_FALLBACK and is_cert_error):
            raise
        fallback_context = ssl._create_unverified_context()
        return urllib.request.urlopen(req, timeout=timeout, context=fallback_context)


@dataclass
class NewsRecord:
    query: str
    query_variants: list[str]
    geographic_scope: str
    geographic_terms: list[str]
    year: int
    source_type: str
    source_type_confidence: str
    source_type_evidence: str
    evidence_level: str
    evidence_weight: int
    medium: str
    url: str
    title: str
    published_date: str
    language: str
    country: str
    text_raw_visible: str
    text_clean: str
    text_normalized: str
    text_length: int
    word_count: int
    paragraph_count: int
    cleaning_notes: list[str]
    source_api: str
    fetched_at: str
    status: str
    error: str = ""
    pdf_url: str = ""
    pdf_file: str = ""
    pdf_status: str = ""
    source_weight_factor: float = 1.0
    pdf_text_clean: str = ""
    pdf_text_length: int = 0
    pdf_page_count: int = 0
    analysis_tokens: list[str] | None = None
    analysis_token_count: int = 0
    top_unigrams: list[dict] | None = None
    top_bigrams: list[dict] | None = None
    top_trigrams: list[dict] | None = None
    processing_status: str = ""


MIN_PARTIAL_ANALYSIS_TEXT_CHARS = 100


def record_is_usable_for_analysis(record: NewsRecord) -> bool:
    """True when a record has enough local text for narrative analysis.

    `ok_partial` can be legitimate (abstracts, RSS summaries, public excerpts),
    but metadata-only snippets of a few words must not advance balance targets.
    """
    if record.status == "ok":
        return bool(record.text_clean or record.text_normalized)
    if record.status == "ok_partial":
        text = record.text_normalized or record.text_clean or ""
        return len(text) >= MIN_PARTIAL_ANALYSIS_TEXT_CHARS or int(record.text_length or 0) >= MIN_PARTIAL_ANALYSIS_TEXT_CHARS
    return False


def row_is_usable_for_analysis(row: dict) -> bool:
    status = str(row.get("status") or "")
    text = str(row.get("text_normalized") or row.get("text_clean") or "")
    if status == "ok":
        return bool(text)
    if status == "ok_partial":
        try:
            text_length = int(row.get("text_length") or 0)
        except (TypeError, ValueError):
            text_length = len(text)
        return len(text) >= MIN_PARTIAL_ANALYSIS_TEXT_CHARS or text_length >= MIN_PARTIAL_ANALYSIS_TEXT_CHARS
    return False


class VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg", "canvas", "nav", "footer", "header"}:
            self.skip_depth += 1
        if tag.lower() in {"p", "br", "div", "article", "section", "h1", "h2", "h3", "li"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg", "canvas", "nav", "footer", "header"}:
            self.skip_depth = max(0, self.skip_depth - 1)
        if tag.lower() in {"p", "div", "article", "section", "li"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip_depth == 0:
            self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts)
        lines = [clean_text(line) for line in re.split(r"\n+", raw)]
        return "\n\n".join(line for line in lines if line)


def clean_text(raw: str) -> str:
    text = html.unescape(raw or "")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"(?i)(aceptar cookies|cookie policy|suscr[ií]bete|newsletter|iniciar sesi[oó]n)", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def text_blocks(raw: str) -> list[str]:
    text = html.unescape(raw or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [clean_text(line) for line in re.split(r"\n+", text)]
    return [line for line in lines if line]


def split_embedded_cut_markers(block: str) -> str:
    cut_patterns = [
        r"\bOverall Score\b",
        r"\bRelated Posts?\b",
        r"\bRelated Articles?\b",
        r"\bMore Stories\b",
        r"\bMore From\b",
        r"\bRecommended Articles?\b",
        r"\bAbout the Author\b",
        r"\bAuthor Bio\b",
        r"\b[ÚU]ltimas Noticias\b",
        r"\b[Mm][áa]s de (Cultura|Sociedad|Estados|Capital|Ciencia|Opin[ií]on)\b",
        r"\bPublicidad Comercial\b",
        r"\bLo m[áa]s visto\b",
        r"\bM[áa]s le[ií]das\b",
    ]
    earliest = None
    for pattern in cut_patterns:
        match = re.search(pattern, block, flags=re.I)
        if match and (earliest is None or match.start() < earliest):
            earliest = match.start()
    return block[:earliest].strip() if earliest is not None else block


def remove_inline_boilerplate(block: str) -> str:
    patterns = [
        r"View this post on Instagram\s+A post shared by\s+.*?\)\s*",
        r"A post shared by\s+.*?\)\s*",
        r"Share this article\s*",
        r"Sign up for (our|the) newsletter\s*",
    ]
    cleaned = block
    for pattern in patterns:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.I)
    return clean_text(cleaned)


BOILERPLATE_PATTERNS = [
    r"^view this post on instagram\b",
    r"^a post shared by\b",
    r"^related posts?\b",
    r"^recommended\b",
    r"^read more\b",
    r"^more from\b",
    r"^subscribe\b",
    r"^newsletter\b",
    r"^advertisement\b",
    r"^publicidad\b",
    r"^cookies?\b",
    r"^privacy policy\b",
    r"^terms of use\b",
    r"^copyright\b",
    r"^all rights reserved\b",
    r"^share this\b",
    r"^follow us\b",
    r"^comments?\b",
    r"^tags?\b",
    r"^overall score\b",
]


def is_boilerplate_block(block: str) -> bool:
    plain = strip_for_compare(block)
    if len(plain) <= 2:
        return True
    if any(re.search(pattern, plain) for pattern in BOILERPLATE_PATTERNS):
        return True
    if re.match(r"^[a-z]+ \d{1,2}, \d{4}$", plain):
        return True
    if len(block.split()) <= 4 and any(marker in plain for marker in ("facebook", "twitter", "instagram", "linkedin")):
        return True
    return False


def strip_for_compare(value: str) -> str:
    value = value.lower()
    table = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")
    value = value.translate(table)
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def remove_title_repetition(blocks: list[str], title: str) -> tuple[list[str], int]:
    if not title:
        return blocks, 0
    title_plain = strip_for_compare(title)
    title_core = re.split(r"\s+[–—-]\s+|\s+\|\s+", title, maxsplit=1)[0].strip()
    title_core_plain = strip_for_compare(title_core)
    kept = []
    removed = 0
    for index, block in enumerate(blocks):
        block_plain = strip_for_compare(block)
        if index < 5 and (block_plain == title_plain or block_plain in title_plain):
            removed += 1
            continue
        if index < 5 and len(block.split()) > 12:
            if title_plain in block_plain:
                updated = re.sub(re.escape(title), " ", block, count=1, flags=re.I)
                if updated == block and title_core:
                    original_occurrences = list(re.finditer(re.escape(title_core), block, flags=re.I))
                    if len(original_occurrences) >= 2:
                        updated = block[original_occurrences[1].end():]
                    elif original_occurrences:
                        updated = block[original_occurrences[0].end():]
                block = updated
                removed += 1
            elif title_core_plain and block_plain.startswith(title_core_plain):
                original_occurrences = list(re.finditer(re.escape(title_core), block, flags=re.I))
                if len(original_occurrences) >= 2:
                    block = block[original_occurrences[1].end():]
                elif original_occurrences:
                    block = block[original_occurrences[0].end():]
                else:
                    block = block[len(title_core):]
                block = re.sub(
                    r"^\s*(\|\s*)?[A-Za-z0-9 ._-]{0,50}\s*(News|Noticias)?\s*"
                    r"([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)\s+\d{1,2},\s+\d{4}\s+"
                    r"([A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ._-]+\s*){0,5}(News|Noticias)?\s*",
                    " ",
                    block,
                    count=1,
                )
                removed += 1
            block = clean_text(block)
        kept.append(block)
    return kept, removed


def cut_after_related_content(blocks: list[str], source_url: str = "") -> tuple[list[str], bool]:
    cut_markers = [*COMMON_NEWS_TAIL_CUT_MARKERS, *source_tail_cut_markers(source_url)]
    for index, block in enumerate(blocks):
        plain = strip_for_compare(block)
        if any(marker in plain for marker in cut_markers):
            return blocks[:index], True
    return blocks, False


def detect_author_bio_tail(blocks: list[str]) -> tuple[list[str], bool]:
    bio_markers = [
        "i strive to",
        "in addition to my work",
        "i was previously",
        "prior to joining",
        "author",
    ]
    for index, block in enumerate(blocks):
        plain = strip_for_compare(block)
        if index > 1 and any(marker in plain for marker in bio_markers):
            return blocks[:index], True
        if any(marker in plain for marker in bio_markers):
            for marker in bio_markers:
                marker_index = plain.find(marker)
                if marker_index > 250:
                    approx = max(0, marker_index - 20)
                    return [*blocks[:index], block[:approx].strip()], True
    return blocks, False


def normalize_for_analysis(text: str) -> str:
    text = html.unescape(text or "").lower()
    table = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")
    text = text.translate(table)
    text = re.sub(r"https?://\S+|www\.\S+", " ", text)
    text = re.sub(r"[^a-z0-9áéíóúüñ\s-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def clean_article_text(raw_visible: str, title: str = "", source_url: str = "") -> dict:
    blocks = [split_embedded_cut_markers(block) for block in text_blocks(raw_visible)]
    blocks = [remove_inline_boilerplate(block) for block in blocks]
    blocks = [block for block in blocks if block]
    notes: list[str] = []

    before = len(blocks)
    blocks = [block for block in blocks if not is_boilerplate_block(block)]
    removed_boilerplate = before - len(blocks)
    if removed_boilerplate:
        notes.append(f"removed_boilerplate_blocks:{removed_boilerplate}")

    blocks, removed_titles = remove_title_repetition(blocks, title)
    if removed_titles:
        notes.append(f"removed_repeated_title_blocks:{removed_titles}")

    blocks, cut_related = cut_after_related_content(blocks, source_url=source_url)
    if cut_related:
        notes.append("cut_after_related_content")

    blocks, cut_bio = detect_author_bio_tail(blocks)
    if cut_bio:
        notes.append("cut_author_bio_tail")

    deduped: list[str] = []
    seen = set()
    for block in blocks:
        key = strip_for_compare(block)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(block)
    if len(deduped) != len(blocks):
        notes.append(f"removed_duplicate_blocks:{len(blocks) - len(deduped)}")

    text_clean = "\n\n".join(deduped).strip()
    text_clean = re.sub(r"[ \t]+", " ", text_clean)
    text_clean = re.sub(r"\n{3,}", "\n\n", text_clean).strip()
    text_normalized = normalize_for_analysis(text_clean)
    return {
        "text_clean": text_clean,
        "text_normalized": text_normalized,
        "word_count": len(re.findall(r"\b\w+\b", text_normalized)),
        "paragraph_count": len([block for block in text_clean.split("\n\n") if block.strip()]),
        "cleaning_notes": notes,
    }


def clean_partial_metadata_text(value: str) -> dict:
    """Clean title/snippet metadata without dropping it as a repeated title."""
    text_clean = clean_text(value)
    text_clean = remove_inline_boilerplate(text_clean)
    text_clean = re.sub(r"[ \t]+", " ", text_clean).strip()
    text_normalized = normalize_for_analysis(text_clean)
    return {
        "text_clean": text_clean,
        "text_normalized": text_normalized,
        "word_count": len(re.findall(r"\b\w+\b", text_normalized)),
        "paragraph_count": 1 if text_clean else 0,
        "cleaning_notes": ["partial_metadata_text"],
    }


PDF_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were", "has", "have", "not",
    "los", "las", "del", "que", "por", "con", "para", "una", "uno", "como", "mas", "sus", "sin", "sobre",
    "entre", "tambien", "esta", "este", "estos", "estas", "desde", "donde", "cuando", "porque", "pero",
    "dos", "tres", "ser", "son", "fue", "han", "hay", "the", "doi", "http", "https", "www",
    "que", "com", "uma", "das", "dos", "por", "para", "com", "como", "mais", "sao", "foi", "entre",
    "citar", "articulo", "articulos", "artigo", "numero", "completo", "informacion", "informa", "pagina",
    "site", "revista", "redalyc", "sistema", "org", "issn", "correo", "email", "vol", "num", "pp",
    "universidad", "universidade", "autonoma", "autónoma", "journal", "abstract", "resumen", "palabras",
    "clave", "keywords", "copyright", "creative", "commons", "licencia", "licence",
    "nos", "nas", "pelos", "pela", "elas", "eles", "seus", "suas",
}


def tokenize_for_json(text: str) -> list[str]:
    normalized = strip_for_compare(text)
    tokens = re.findall(r"\b[a-z][a-z0-9_-]{2,}\b", normalized)
    return [token for token in tokens if token not in PDF_STOPWORDS and not token.isnumeric()]


def top_ngrams_from_tokens(tokens: list[str], n: int, top_n: int = 50) -> list[dict]:
    if n <= 1:
        counts = Counter(tokens)
    else:
        counts = Counter(" ".join(tokens[i:i + n]) for i in range(0, max(0, len(tokens) - n + 1)))
    return [{"term": term, "count": count} for term, count in counts.most_common(top_n)]


def extract_pdf_text(pdf_path: str | Path, max_pages: int = 80) -> tuple[str, int, str]:
    """Extract local PDF text using pypdf when available.

    This is intentionally local and conservative: if the PDF is scanned or encrypted,
    the record keeps metadata and reports the extraction status instead of pretending
    that full text exists.
    """
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return "", 0, f"pdf_text_error:pypdf_unavailable:{type(exc).__name__}"
    try:
        reader = PdfReader(str(pdf_path))
        page_count = len(reader.pages)
        parts: list[str] = []
        for page in reader.pages[:max_pages]:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                parts.append("")
        text = clean_text("\n".join(parts))
        if not text:
            return "", page_count, "pdf_text_empty_or_scanned"
        return text, page_count, "pdf_text_extracted"
    except Exception as exc:  # noqa: BLE001
        return "", 0, f"pdf_text_error:{type(exc).__name__}"


def enrich_record_with_pdf_text(record: NewsRecord, max_tokens: int = 12000) -> NewsRecord:
    if not record.pdf_file:
        if not record.processing_status:
            record.processing_status = "no_pdf_file_for_text_extraction"
        return record
    pdf_path = Path(record.pdf_file)
    if not pdf_path.exists():
        record.processing_status = "pdf_file_missing_for_text_extraction"
        return record
    pdf_text, page_count, extraction_status = extract_pdf_text(pdf_path)
    record.pdf_text_clean = pdf_text
    record.pdf_text_length = len(pdf_text)
    record.pdf_page_count = page_count
    if pdf_text and len(pdf_text) > len(record.text_clean or ""):
        record.text_raw_visible = pdf_text
        record.text_clean = pdf_text
        record.text_normalized = normalize_for_analysis(pdf_text)
        record.text_length = len(record.text_clean)
        record.word_count = len(re.findall(r"\b\w+\b", record.text_normalized))
        record.paragraph_count = len([block for block in re.split(r"\n{2,}", record.text_clean) if block.strip()]) or 1
        record.cleaning_notes = unique_sequence([*record.cleaning_notes, "pdf_full_text_used_for_analysis"])
        if record.status in {"ok_partial", "too_short", "fetch_error", "error"}:
            record.status = "ok"
            record.error = ""
    tokens = tokenize_for_json(record.text_normalized or record.text_clean or pdf_text)
    record.analysis_tokens = tokens[:max_tokens]
    record.analysis_token_count = len(tokens)
    record.top_unigrams = top_ngrams_from_tokens(tokens, 1)
    record.top_bigrams = top_ngrams_from_tokens(tokens, 2)
    record.top_trigrams = top_ngrams_from_tokens(tokens, 3)
    record.processing_status = extraction_status
    return record


def request_json(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with open_url(req, timeout=timeout) as response:
        raw_text = response.read().decode("utf-8", errors="replace")
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        snippet = clean_text(raw_text[:240])
        raise ValueError(f"non_json_response:{snippet}") from exc


def request_html(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with open_url(req, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        raw = response.read()
    if "pdf" in content_type.lower():
        raise ValueError("PDF document, not HTML news page")
    return raw.decode("utf-8", errors="replace")


def robots_allowed(url: str) -> tuple[bool, str]:
    """Respect robots.txt for local full-text extraction."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False, "invalid_url"
    base = f"{parsed.scheme}://{parsed.netloc}"
    if base not in ROBOTS_CACHE:
        rp = urllib.robotparser.RobotFileParser()
        robots_url = urllib.parse.urljoin(base, "/robots.txt")
        rp.set_url(robots_url)
        try:
            req = urllib.request.Request(robots_url, headers={"User-Agent": USER_AGENT})
            with open_url(req, timeout=6) as response:
                robots_text = response.read(300_000).decode("utf-8", errors="replace")
            rp.parse(robots_text.splitlines())
            ROBOTS_CACHE[base] = rp
        except Exception as exc:  # noqa: BLE001
            ROBOTS_CACHE[base] = None
            return False, f"robots_unavailable_metadata_only:{type(exc).__name__}"
    rp = ROBOTS_CACHE.get(base)
    if rp is None:
        return False, "robots_unavailable_metadata_only"
    try:
        allowed = rp.can_fetch(USER_AGENT, url) and rp.can_fetch("*", url)
    except Exception:
        return False, "robots_check_failed_metadata_only"
    return allowed, "robots_allowed" if allowed else "robots_disallow"


def safe_write_text_atomic(path: Path, text: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(text, encoding=encoding)
    tmp_path.replace(path)


def download_pdf_file(pdf_url: str, output_dir: Path, year: int, record_id: str, timeout: int = 25) -> tuple[str, str]:
    if not pdf_url:
        return "", "no_pdf_url"
    allowed, robots_note = robots_allowed(pdf_url)
    if not allowed:
        return "", f"pdf_metadata_only:{robots_note}"
    pdf_dir = output_dir / "pdfs" / str(year)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / f"{record_id}.pdf"
    if pdf_path.exists() and pdf_path.stat().st_size > 0:
        return str(pdf_path), "already_downloaded"
    try:
        req = urllib.request.Request(pdf_url, headers={"User-Agent": USER_AGENT, "Accept": "application/pdf,*/*;q=0.8"})
        with open_url(req, timeout=timeout) as response:
            content_type = (response.headers.get("Content-Type") or "").lower()
            data = response.read()
        if not data or (b"%PDF" not in data[:1024] and "pdf" not in content_type):
            return "", "not_pdf_response"
        tmp_path = pdf_path.with_suffix(".pdf.tmp")
        tmp_path.write_bytes(data)
        tmp_path.replace(pdf_path)
        return str(pdf_path), "downloaded"
    except Exception as exc:  # noqa: BLE001
        return "", f"pdf_error:{type(exc).__name__}"


def month_periods(
    start_year: int,
    end_year: int,
    start_month: int | None = None,
    end_month: int | None = None,
) -> Iterable[tuple[dt.datetime, dt.datetime]]:
    for year in range(start_year, end_year + 1):
        first_month = int(start_month or 1) if year == start_year else 1
        last_month = int(end_month or 12) if year == end_year else 12
        first_month = max(1, min(12, first_month))
        last_month = max(1, min(12, last_month))
        for month in range(1, 13):
            if month < first_month or month > last_month:
                continue
            start = dt.datetime(year, month, 1, 0, 0, 0)
            if month == 12:
                end = dt.datetime(year, 12, 31, 23, 59, 59)
            else:
                end = dt.datetime(year, month + 1, 1, 0, 0, 0) - dt.timedelta(seconds=1)
            yield start, end


def gdelt_datetime(value: dt.datetime) -> str:
    return value.strftime("%Y%m%d%H%M%S")


def clean_query_variants(query: str, variants: list[str] | None = None) -> list[str]:
    seen = set()
    cleaned: list[str] = []
    for item in [query, *(variants or [])]:
        value = clean_text(item).strip()
        key = strip_for_compare(value)
        if not value or key in seen:
            continue
        seen.add(key)
        cleaned.append(value)
    return cleaned


def quote_query_term(term: str) -> str:
    term = term.strip()
    if not term:
        return term
    if term.startswith('"') and term.endswith('"'):
        return term
    if re.search(r"\s", term) and not re.search(r"\bOR\b|\(|\)|domain:", term, flags=re.I):
        escaped = term.replace('"', '\\"')
        return f'"{escaped}"'
    return term


def canonical_domain(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    parsed = urllib.parse.urlparse(value if re.match(r"^https?://", value, re.I) else "https://" + value)
    domain = (parsed.netloc or parsed.path).lower().replace("www.", "").strip("/")
    return domain


def build_term_query(query: str, variants: list[str] | None = None) -> str:
    terms = clean_query_variants(query, variants)
    if not terms:
        return query.strip()
    if len(terms) == 1:
        return quote_query_term(terms[0])
    return "(" + " OR ".join(quote_query_term(term) for term in terms) + ")"


def build_query(
    query: str,
    domains: list[str],
    variants: list[str] | None = None,
    geographic_terms: list[str] | None = None,
    exclude_terms: list[str] | None = None,
    exclude_domains: list[str] | None = None,
) -> str:
    query = build_term_query(query, variants)
    geo_terms = clean_query_variants("", geographic_terms)
    if geo_terms:
        geo_clause = " OR ".join(quote_query_term(term) for term in geo_terms)
        query = f"({query}) ({geo_clause})"
    clean_domains = [canonical_domain(d) for d in domains if d.strip()]
    clean_domains = [domain for domain in clean_domains if domain]
    if clean_domains:
        domain_clause = " OR ".join(f"domain:{domain}" for domain in clean_domains)
        query = f"({query}) ({domain_clause})"
    negatives = []
    for term in clean_query_variants("", exclude_terms):
        negatives.append("-" + quote_query_term(term))
    for domain in [canonical_domain(d) for d in (exclude_domains or []) if d.strip()]:
        negatives.append(f"-domain:{domain}")
    if negatives:
        query = f"{query} " + " ".join(negatives)
    return query


def build_google_news_query(
    query: str,
    domains: list[str],
    variants: list[str] | None = None,
    geographic_terms: list[str] | None = None,
    exclude_terms: list[str] | None = None,
    exclude_domains: list[str] | None = None,
) -> str:
    google_query = build_term_query(query, variants)
    geo_terms = clean_query_variants("", geographic_terms)
    if geo_terms:
        google_query = f"({google_query}) ({' OR '.join(quote_query_term(term) for term in geo_terms)})"
    clean_domains = [canonical_domain(d) for d in domains if d.strip()]
    clean_domains = [domain for domain in clean_domains if domain]
    if clean_domains:
        google_query = f"({google_query}) ({' OR '.join(f'site:{domain}' for domain in clean_domains)})"
    negatives = []
    for term in clean_query_variants("", exclude_terms):
        negatives.append("-" + quote_query_term(term))
    for domain in [canonical_domain(d) for d in (exclude_domains or []) if d.strip()]:
        negatives.append(f"-site:{domain}")
    if negatives:
        google_query = f"{google_query} " + " ".join(negatives)
    return google_query


def chunked(items: list[str], size: int) -> Iterable[list[str]]:
    size = max(1, int(size))
    for index in range(0, len(items), size):
        yield items[index:index + size]


def compact_query_variants(query: str, variants: list[str], limit: int = 8) -> list[str]:
    """Keep forum/index queries short enough for public search endpoints."""
    cleaned = clean_query_variants(query, variants)
    selected: list[str] = []
    for term in cleaned:
        if term.lower() in {item.lower() for item in selected}:
            continue
        selected.append(term)
        if len(selected) >= limit:
            break
    return selected


def gdelt_forum_single_query(
    term: str,
    domain: str,
    geographic_terms: list[str],
    exclude_terms: list[str],
) -> str:
    """Build a GDELT-valid forum query without invalid single-term parentheses."""
    parts = [quote_query_term(term)]
    if geographic_terms:
        parts.append(quote_query_term(geographic_terms[0]))
    if domain:
        parts.append(f"domain:{canonical_domain(domain)}")
    for excluded in exclude_terms:
        parts.append("-" + quote_query_term(excluded))
    return " ".join(part for part in parts if part)


def gdelt_or_clause(prefix: str, values: list[str]) -> str:
    values = [value for value in values if value]
    if not values:
        return ""
    clauses = [f"{prefix}{value}" for value in values]
    if len(clauses) == 1:
        return clauses[0]
    return "(" + " OR ".join(clauses) + ")"


def gdelt_news_single_query(
    term: str,
    domains: list[str],
    geographic_terms: list[str],
    exclude_terms: list[str],
    exclude_domains: list[str],
) -> str:
    """Build GDELT-valid news query with parentheses only around OR clauses."""
    parts = [quote_query_term(term)]
    geo_terms = [quote_query_term(term) for term in geographic_terms if term]
    if geo_terms:
        parts.append(geo_terms[0] if len(geo_terms) == 1 else "(" + " OR ".join(geo_terms) + ")")
    domain_clause = gdelt_or_clause("domain:", [canonical_domain(domain) for domain in domains if canonical_domain(domain)])
    if domain_clause:
        parts.append(domain_clause)
    for excluded in exclude_terms:
        parts.append("-" + quote_query_term(excluded))
    for domain in [canonical_domain(domain) for domain in exclude_domains if canonical_domain(domain)]:
        parts.append(f"-domain:{domain}")
    return " ".join(part for part in parts if part)


def build_gdelt_news_query_plan(
    query: str,
    domains: list[str],
    variants: list[str],
    geographic_terms: list[str],
    exclude_terms: list[str],
    exclude_domains: list[str],
    *,
    term_limit: int = 3,
    domain_batch_size: int = 5,
    max_domain_batches: int = 2,
) -> list[dict]:
    """Build short, auditable GDELT news queries instead of one saturated query."""
    terms = compact_query_variants(query, variants, limit=term_limit) or [query]
    clean_domains = [canonical_domain(domain) for domain in domains if canonical_domain(domain)]
    domain_batches = list(chunked(clean_domains, domain_batch_size)) if clean_domains else [[]]
    domain_batches = domain_batches[: max(1, int(max_domain_batches))]
    compact_geo = clean_query_variants("", geographic_terms)[:2]
    critical_exclusions = [
        term for term in exclude_terms
        if term.lower() in {
            "cigar",
            "cigars",
            "cigarro",
            "cigarros",
            "tobacco",
            "tabaco",
            "colonoscopic tattooing",
            "colonoscopic",
            "endoscopic tattooing",
            "endoscopic",
        }
    ][:4]
    # Domain exclusions are enforced after retrieval. Keeping them inside GDELT
    # easily makes the query too long and causes non-json rejection.
    clean_exclude_domains: list[str] = []
    plan: list[dict] = []
    for domain_index, domain_batch in enumerate(domain_batches, start=1):
        for term_index, term in enumerate(terms, start=1):
            plan.append(
                {
                    "term": term,
                    "term_index": term_index,
                    "domain_batch_index": domain_index,
                    "domains": domain_batch,
                    "query": gdelt_news_single_query(
                        term,
                        domain_batch,
                        compact_geo,
                        critical_exclusions,
                        clean_exclude_domains,
                    ),
                }
            )
    return [item for item in plan if item["query"]]


def build_forum_gdelt_query_plan(
    query: str,
    forum_domains: list[str],
    variants: list[str],
    geographic_terms: list[str],
    exclude_terms: list[str],
    exclude_domains: list[str],
) -> list[dict]:
    """Build adaptive forum queries: base term first, then synonyms only if needed."""
    compact_terms = compact_query_variants(query, variants, limit=3)
    if not compact_terms:
        compact_terms = [query]
    compact_geo = clean_query_variants("", geographic_terms)[:1]
    critical_exclusions = [
        term for term in exclude_terms
        if term.lower() in {"cigar", "cigars", "cigarro", "cigarros", "tobacco", "tabaco"}
    ][:4]
    def forum_domain_priority(domain: str) -> tuple[int, str]:
        domain = canonical_domain(domain)
        if "reddit" in domain:
            return (4, domain)
        if domain in {"medium.com", "substack.com", "wordpress.com", "blogspot.com", "tumblr.com"}:
            return (0, domain)
        if any(marker in domain for marker in ("tattoo", "inkppl")):
            return (1, domain)
        if domain in {"quora.com", "stackexchange.com", "dev.to"}:
            return (2, domain)
        return (3, domain)

    ordered_domains = sorted(
        {canonical_domain(domain) for domain in forum_domains if canonical_domain(domain)},
        key=forum_domain_priority,
    )[:6]
    plan: list[dict] = []
    for domain in ordered_domains:
        for stage, term in enumerate(compact_terms, start=1):
            geo_variants: list[tuple[str, list[str]]] = [("geo", compact_geo)]
            if compact_geo:
                geo_variants.append(("no_geo", []))
            for geo_mode, geo_terms in geo_variants:
                plan.append(
                    {
                        "domain": domain,
                        "term": term,
                        "stage": stage,
                        "geo_mode": geo_mode,
                        "query": gdelt_forum_single_query(
                            term,
                            domain,
                            geo_terms,
                            critical_exclusions,
                        ),
                    }
                )
    return [item for item in plan if item["query"]]


def search_gdelt(query: str, start: dt.datetime, end: dt.datetime, max_records: int) -> list[dict]:
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": str(max_records),
        "sort": "datedesc",
        "startdatetime": gdelt_datetime(start),
        "enddatetime": gdelt_datetime(end),
    }
    url = GDELT_ENDPOINT + "?" + urllib.parse.urlencode(params)
    data = request_json(url, timeout=15)
    return data.get("articles", []) or []


def search_gdelt_with_retries(
    query: str,
    start: dt.datetime,
    end: dt.datetime,
    max_records: int,
    *,
    attempts: int = 3,
    base_wait_seconds: float = 15.0,
    stop_requested=None,
    progress=None,
    label: str = "GDELT",
) -> list[dict]:
    """Search GDELT without silently skipping the same month on rate limits."""
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return search_gdelt(query, start, end, max_records)
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code != 429:
                raise
            wait_seconds = base_wait_seconds * attempt
            if progress:
                progress(
                    f"{label} rate limit {start:%Y-%m}: retry {attempt}/{attempts} "
                    f"after {wait_seconds:.0f}s"
                )
            if interruptible_sleep(wait_seconds, stop_requested):
                if progress:
                    progress(f"Stopped by user during {label} rate-limit retry.")
                return []
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if "non_json_response:Your query was too short or too long" in str(exc):
                if progress:
                    progress(f"{label} rejected {start:%Y-%m}: query too short/long; trying next compact batch.")
                return []
            raise
    if progress:
        progress(
            f"{label} skipped {start:%Y-%m}: rate limit persisted after {attempts} retries; "
            "lower depth, raise delay, or run fewer source layers."
        )
    if last_error:
        return []
    return []


def search_gdelt_with_status(
    query: str,
    start: dt.datetime,
    end: dt.datetime,
    max_records: int,
    *,
    attempts: int = 1,
    base_wait_seconds: float = 15.0,
    stop_requested=None,
    progress=None,
    label: str = "GDELT",
) -> tuple[list[dict], str]:
    """Search GDELT and return an explicit status for adaptive/circuit-breaker flows."""
    for attempt in range(1, attempts + 1):
        try:
            return search_gdelt(query, start, end, max_records), "ok"
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                wait_seconds = base_wait_seconds * attempt
                if progress:
                    progress(f"{label} rate limit {start:%Y-%m}: attempt {attempt}/{attempts}; wait {wait_seconds:.0f}s")
                if interruptible_sleep(wait_seconds, stop_requested):
                    return [], "stopped"
                continue
            raise
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            if "non_json_response:Parentheses may only be used around OR'd statements" in message:
                if progress:
                    progress(f"{label} rejected {start:%Y-%m}: invalid parentheses syntax.")
                return [], "bad_query"
            if "non_json_response:Your query was too short or too long" in message:
                if progress:
                    progress(f"{label} rejected {start:%Y-%m}: query too short/long.")
                return [], "bad_query"
            raise
    if progress:
        progress(f"{label} skipped {start:%Y-%m}: rate limit persisted; skipping rest of this source/month.")
    return [], "rate_limited"


def search_google_news_rss(query: str, start: dt.datetime, end: dt.datetime, max_records: int) -> tuple[list[dict], dict]:
    """Search public Google News RSS for one period.

    This does not scrape Google Scholar or Google web pages. It uses the public
    RSS endpoint as an additional news index and keeps extraction local.
    """
    q = f"{query} after:{start:%Y-%m-%d} before:{(end + dt.timedelta(days=1)):%Y-%m-%d}"
    params = {
        "q": q,
        "hl": "es-419",
        "gl": "MX",
        "ceid": "MX:es-419",
    }
    url = GOOGLE_NEWS_RSS_ENDPOINT + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with open_url(req, timeout=20) as response:
        xml_text = response.read().decode("utf-8", errors="replace")
    root = ET.fromstring(xml_text)
    rows: list[dict] = []
    total_items = 0
    undated_items = 0
    outside_period_items = 0
    for item in root.findall(".//item"):
        total_items += 1
        title = clean_text(item.findtext("title") or "")
        link = clean_text(item.findtext("link") or "")
        published = clean_text(item.findtext("pubDate") or "")
        parsed = parse_rss_datetime(published)
        if not parsed:
            undated_items += 1
            continue
        if not (start <= parsed <= end + dt.timedelta(days=1)):
            outside_period_items += 1
            continue
        description = clean_text(html.unescape(item.findtext("description") or ""))
        source_node = item.find("source")
        medium = clean_text(source_node.text if source_node is not None and source_node.text else "")
        rows.append(
            {
                "url": link,
                "title": title,
                "seendate": published,
                "sourceCommonName": medium or "Google News RSS",
                "domain": urllib.parse.urlparse(link).netloc.replace("www.", ""),
                "language": "",
                "sourceCountry": "",
                "source_api": "google_news_rss",
                "rss_description": description,
            }
        )
        if len(rows) >= max_records:
            break
    return rows, {
        "total_items": total_items,
        "dated_in_period": len(rows),
        "undated_items": undated_items,
        "outside_period_items": outside_period_items,
    }


def parse_rss_datetime(value: str) -> dt.datetime | None:
    value = clean_text(value)
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            return parsed
        return parsed.astimezone(dt.UTC).replace(tzinfo=None)
    except Exception:
        try:
            parsed = dt.datetime.strptime(value, "%a, %d %b %Y %H:%M:%S %z")
            return parsed.astimezone(dt.UTC).replace(tzinfo=None)
        except Exception:
            return None


def article_year(article: dict, fallback_year: int) -> int:
    published = str(article.get("seendate", "") or article.get("publishedDate", "") or "")
    if published[:4].isdigit():
        return int(published[:4])
    parsed_rss = parse_rss_datetime(published)
    if parsed_rss:
        return int(parsed_rss.year)
    return int(fallback_year)


def parse_seed_date(value: str) -> dt.datetime | None:
    value = clean_text(value)
    if not value:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return dt.datetime.strptime(value, fmt)
        except Exception:
            continue
    parsed = parse_rss_datetime(value)
    return parsed


def title_from_url(url: str) -> str:
    path = urllib.parse.urlparse(url).path.strip("/")
    if not path:
        return url
    slug = path.split("/")[-1]
    slug = re.sub(r"[-_]+", " ", slug)
    slug = re.sub(r"\s+", " ", slug).strip()
    return slug[:180] or url


def seed_file_paths(seed_url_file: str | Path | None) -> list[Path]:
    if not seed_url_file:
        return []
    if isinstance(seed_url_file, Path):
        return [seed_url_file]
    return [
        Path(part.strip())
        for part in str(seed_url_file).split(",")
        if part.strip()
    ]


def load_seed_url_articles(seed_url_file: str | Path | None) -> list[dict]:
    rows = []
    for path in seed_file_paths(seed_url_file):
        rows.extend(load_seed_url_articles_from_path(path))
    return rows


def load_seed_url_articles_from_path(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    rows = []
    for item in data:
        if not isinstance(item, dict):
            continue
        url = clean_text(str(item.get("url") or ""))
        if not url:
            continue
        parsed_date = parse_seed_date(str(item.get("date") or item.get("fecha") or ""))
        if not parsed_date:
            try:
                seed_year = int(str(item.get("year") or item.get("anio") or "").strip()[:4])
                parsed_date = dt.datetime(seed_year, 1, 1)
            except (TypeError, ValueError):
                parsed_date = None
        if not parsed_date:
            continue
        source_type = str(item.get("source_type") or "news")
        medium = clean_text(str(item.get("medium") or item.get("medio") or infer_medium({}, url)))
        pdf_url = clean_text(str(item.get("pdf_url") or item.get("pdf") or ""))
        doi = clean_text(str(item.get("doi") or ""))
        rows.append(
            {
                "url": url,
                "title": clean_text(str(item.get("title") or item.get("titulo") or title_from_url(url))),
                "seendate": parsed_date.strftime("%Y-%m-%d"),
                "sourceCommonName": medium,
                "domain": urllib.parse.urlparse(url).netloc.replace("www.", ""),
                "language": "Spanish",
                "sourceCountry": "MX",
                "source_api": str(item.get("source_api") or "seed_url_list"),
                "source_type_override": source_type,
                "source_type_evidence_override": str(item.get("source_type_evidence") or "curated_seed_url"),
                "pdf_url": pdf_url,
                "doi": doi,
                "abstract": clean_text(str(item.get("abstract") or item.get("resumen") or "")),
                "authors": clean_text(str(item.get("authors") or item.get("autores") or "")),
                "keywords": clean_text(str(item.get("keywords") or item.get("palabras") or "")),
                "source_weight_factor": item.get("source_weight_factor", item.get("factor", "")),
            }
        )
    return rows


def source_types_in_seed_file(seed_url_file: str | Path | None) -> set[str]:
    return {
        str(row.get("source_type_override") or "").strip()
        for row in load_seed_url_articles(seed_url_file)
        if str(row.get("source_type_override") or "").strip()
    }


def search_reddit_rss(query: str, start: dt.datetime, end: dt.datetime, max_records: int) -> list[dict]:
    """Search public Reddit RSS posts for one period.

    This retrieves public post-level RSS entries, not private data and not a
    complete comment archive. It is suitable as a lightweight forum signal.
    """
    params = {
        "q": query,
        "sort": "new",
        "t": "all",
        "limit": str(max(10, min(max_records, 100))),
    }
    url = REDDIT_SEARCH_RSS_ENDPOINT + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
        },
    )
    with open_url(req, timeout=20) as response:
        xml_text = response.read().decode("utf-8", errors="replace")
    root = ET.fromstring(xml_text)
    rows: list[dict] = []
    for item in root.findall(".//item"):
        title = clean_text(item.findtext("title") or "")
        link = clean_text(item.findtext("link") or "")
        published = clean_text(item.findtext("pubDate") or "")
        parsed = parse_rss_datetime(published)
        if parsed and not (start <= parsed <= end + dt.timedelta(days=1)):
            continue
        description = clean_text(html.unescape(item.findtext("description") or ""))
        rows.append(
            {
                "url": link,
                "title": title,
                "seendate": published,
                "sourceCommonName": "reddit.com",
                "domain": "reddit.com",
                "language": "",
                "sourceCountry": "",
                "source_api": "reddit_rss",
                "source_type_override": "forum",
                "rss_description": description,
            }
        )
        if len(rows) >= max_records:
            break
    return rows


def contains_excluded_content(
    url: str,
    medium: str,
    title: str,
    text: str,
    exclude_terms: list[str] | None = None,
    exclude_domains: list[str] | None = None,
) -> tuple[bool, str]:
    haystack = strip_for_compare(" ".join([url, medium, title, text[:6000]]))
    parsed_domain = urllib.parse.urlparse(url).netloc.lower().replace("www.", "")
    for domain in exclude_domains or []:
        domain = canonical_domain(domain)
        if domain and (parsed_domain == domain or parsed_domain.endswith("." + domain) or domain in medium.lower()):
            return True, f"excluded_domain:{domain}"
    for term in exclude_terms or []:
        normalized = strip_for_compare(term)
        if normalized and normalized in haystack:
            return True, f"excluded_term:{term}"
    return False, ""


def passes_geographic_filter(
    geographic_scope: str,
    geographic_terms: list[str],
    url: str,
    medium: str,
    title: str,
    text: str,
    country: str = "",
) -> tuple[bool, str]:
    scope = strip_for_compare(geographic_scope)
    if not scope or scope in {"global", "global sin limite regional", "sin limite regional"}:
        return True, "global_scope"
    terms = clean_query_variants("", geographic_terms)
    if not terms:
        return True, "no_geographic_terms"
    policy = source_access_policy(url)
    policy_country = str(policy.get("country") or "").upper()
    record_country = str(country or "").upper()
    domain = urllib.parse.urlparse(url).netloc.lower()
    if "mex" in scope:
        if record_country == "MX" or policy_country == "MX" or domain.endswith(".mx") or ".com.mx" in domain or ".gob.mx" in domain:
            return True, "mexico_source_or_domain"
    latin_countries = {"MX", "AR", "BR", "CL", "CO", "PE", "UY", "PY", "BO", "EC", "VE", "CR", "PA", "GT", "HN", "SV", "NI", "DO", "CU", "PR"}
    if "latin" in scope or "america latina" in scope or "latinoamerica" in scope:
        if record_country in latin_countries or policy_country in latin_countries:
            return True, "latin_america_source_country"
    haystack = strip_for_compare(" ".join([url, medium, title, text[:4000]]))
    normalized_terms = [strip_for_compare(term) for term in terms if strip_for_compare(term)]
    for term in normalized_terms:
        if term and term in haystack:
            return True, f"geo_term:{term}"
    return False, "missing_geographic_signal"


def expanded_topic_terms(query: str, variants: list[str] | None = None) -> list[str]:
    terms = clean_query_variants(query, variants)
    normalized = " ".join(strip_for_compare(term) for term in terms)
    if "tatuaj" in normalized or "tattoo" in normalized:
        terms.extend([
            "tatuaje",
            "tatuajes",
            "tattoo",
            "tattoos",
            "tattooing",
            "tattooed",
            "body art",
            "permanent makeup",
            "permanent make-up",
        ])
    return clean_query_variants("", terms)


def topical_relevance_score_text(title: str, text: str, terms: list[str]) -> int:
    title_norm = strip_for_compare(title)
    text_norm = strip_for_compare(text)
    score = 0
    for term in terms:
        term_norm = strip_for_compare(term)
        if not term_norm:
            continue
        pattern = rf"(?<![a-z0-9]){re.escape(term_norm)}(?![a-z0-9])"
        if re.search(pattern, title_norm):
            score += 5
        hits = len(re.findall(pattern, text_norm))
        score += min(6, hits * 2)
    return score


def academic_topic_relevance(
    title: str,
    text: str,
    query: str,
    variants: list[str] | None = None,
    min_score: int = 5,
) -> tuple[bool, str]:
    terms = expanded_topic_terms(query, variants)
    score = topical_relevance_score_text(title, text, terms)
    if score >= min_score:
        return True, f"academic_topic_score:{score}"
    return False, f"low_academic_topic_score:{score}; required:{min_score}; terms:{', '.join(terms[:8])}"


def build_academic_query_plan(
    query: str,
    variants: list[str],
    geographic_terms: list[str],
    *,
    max_queries: int = 16,
) -> list[str]:
    """Build short scientific-search queries.

    Academic engines behave differently from GDELT/RSS: if we search globally
    and apply geography only as a post-filter, Mexico/LatAm papers are easily
    buried. Therefore the scientific layer combines topic and geography early.
    """
    topic_terms = compact_query_variants(query, variants, limit=8) or [query]
    geo_terms = clean_query_variants("", geographic_terms)[:4]
    queries: list[str] = []
    if geo_terms:
        for topic in topic_terms:
            for geo in geo_terms:
                queries.append(f"{topic} {geo}".strip())
        for topic in topic_terms:
            if any(marker in strip_for_compare(topic) for marker in ["mexic", "latino", "america latina"]):
                queries.append(topic)
    else:
        queries.extend(topic_terms)
    normalized_seen = set()
    output = []
    for item in queries:
        normalized = strip_for_compare(item)
        if normalized and normalized not in normalized_seen:
            output.append(item)
            normalized_seen.add(normalized)
        if len(output) >= max_queries:
            break
    return output or [query]


def academic_exclude_terms(exclude_terms: list[str]) -> list[str]:
    """Keep only exclusions that are true cross-domain contaminants for papers.

    Biomedical terms such as HIV, hepatitis, keloid or dermatology can be
    relevant to tattoo research. They should not be excluded in the scientific
    layer; they can be classified later as biomedical subtopic.
    """
    allowed = {
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
        "colonoscopic tattooing",
        "colonoscopic",
        "endoscopic tattooing",
        "endoscopic",
        "colonoscopy",
        "polypectomy",
        "indocyanine green",
    }
    return [term for term in exclude_terms if strip_for_compare(term) in {strip_for_compare(item) for item in allowed}]


def extract_visible_text(page_html: str) -> str:
    parser = VisibleTextParser()
    parser.feed(page_html)
    return parser.text()


def infer_medium(article: dict, url: str) -> str:
    for key in ("sourceCommonName", "domain"):
        value = article.get(key)
        if value:
            return str(value)
    parsed = urllib.parse.urlparse(url)
    return parsed.netloc.replace("www.", "")


def openalex_abstract(index: dict | None) -> str:
    if not index:
        return ""
    positions = []
    for word, indexes in index.items():
        for position in indexes:
            positions.append((int(position), word))
    positions.sort()
    return clean_text(" ".join(word for _, word in positions))


def strip_markup(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return clean_text(value)


def search_openalex_year(query: str, year: int, max_records: int, oa_only: bool = True) -> list[dict]:
    rows: list[dict] = []
    cursor = "*"
    per_page = min(max_records, 200)
    filters = [f"from_publication_date:{year}-01-01", f"to_publication_date:{year}-12-31"]
    if oa_only:
        filters.append("is_oa:true")
    while len(rows) < max_records:
        params = {
            "search": query,
            "filter": ",".join(filters),
            "per-page": str(per_page),
            "sort": "publication_date:desc",
            "cursor": cursor,
        }
        url = OPENALEX_WORKS_ENDPOINT + "?" + urllib.parse.urlencode(params)
        data = request_json(url, timeout=20)
        page = data.get("results", []) or []
        if not page:
            break
        rows.extend(page)
        cursor = (data.get("meta") or {}).get("next_cursor")
        if not cursor:
            break
        if len(page) < per_page:
            break
    return rows[:max_records]


def search_crossref_year(query: str, year: int, max_records: int, timeout: int = 8) -> list[dict]:
    params = {
        "query.bibliographic": query,
        "filter": f"from-pub-date:{year}-01-01,until-pub-date:{year}-12-31,type:journal-article",
        "rows": str(min(max_records, 100)),
        "sort": "published",
        "order": "desc",
        "select": "DOI,title,container-title,abstract,author,published-print,published-online,published,URL,subject,link",
    }
    url = CROSSREF_WORKS_ENDPOINT + "?" + urllib.parse.urlencode(params)
    data = request_json(url, timeout=timeout)
    return ((data.get("message") or {}).get("items") or [])[:max_records]


def redalyc_pdf_url(item: dict) -> str:
    journal_id = str(item.get("cveRevista") or "").strip()
    article_id = str(item.get("cveArticulo") or "").strip()
    if not journal_id or not article_id:
        return ""
    jatspdf = str(item.get("jatspdf") or "").strip()
    if jatspdf in {"7", "8"}:
        path = f"/journal/{journal_id}/{article_id}/{article_id}.pdf"
    else:
        path = f"/pdf/{journal_id}/{article_id}.pdf"
    return urllib.parse.urljoin(REDALYC_BASE_URL, path)


def search_redalyc_year(query: str, year: int, max_records: int, timeout: int = 8) -> list[dict]:
    """Search Redalyc public article endpoint and keep records from the requested year.

    Redalyc is especially useful for Latin American open-access journals. Its public
    search endpoint is paginated but not reliably year-filtered, so filtering is
    applied locally and the scan is capped to avoid brute-force behavior.
    """
    rows: list[dict] = []
    safe_query = (query or "").strip().replace("/", "s-s") or "0"
    page_size = min(max(max_records * 2, 10), 50)
    max_pages = 4
    for page in range(1, max_pages + 1):
        encoded_query = urllib.parse.quote(safe_query, safe="")
        url = f"{REDALYC_BASE_URL}/service/r2020/getArticles/{encoded_query}/{page}/{page_size}/1/default"
        data = request_json(url, timeout=timeout)
        items = data.get("resultados") or []
        if not items:
            break
        for item in items:
            try:
                item_year = int(str(item.get("anioArticulo") or item.get("anoEdcNum") or "0")[:4])
            except ValueError:
                continue
            if item_year == int(year):
                rows.append(item)
                if len(rows) >= max_records:
                    return rows
        total = int(data.get("totalResultados") or 0)
        if page * page_size >= total:
            break
    return rows[:max_records]


def openalex_record(
    item: dict,
    query: str,
    clean_variants: list[str],
    geographic_scope: str,
    clean_geographic_terms: list[str],
    year: int,
    min_text_chars: int,
) -> NewsRecord:
    title = clean_text(item.get("title") or item.get("display_name") or "")
    primary_location = item.get("primary_location") or {}
    best_oa_location = item.get("best_oa_location") or {}
    source = primary_location.get("source") or {}
    landing_page_url = primary_location.get("landing_page_url") or item.get("doi") or item.get("id") or ""
    pdf_url = primary_location.get("pdf_url") or best_oa_location.get("pdf_url") or ""
    medium = source.get("display_name") or urllib.parse.urlparse(landing_page_url).netloc.replace("www.", "") or "OpenAlex"
    abstract = openalex_abstract(item.get("abstract_inverted_index"))
    authorships = item.get("authorships") or []
    author_names = ", ".join(
        (authorship.get("author") or {}).get("display_name", "")
        for authorship in authorships[:8]
        if (authorship.get("author") or {}).get("display_name")
    )
    institution_names = []
    institution_countries = []
    for authorship in authorships[:12]:
        for institution in authorship.get("institutions") or []:
            if institution.get("display_name"):
                institution_names.append(str(institution.get("display_name")))
            if institution.get("country_code"):
                institution_countries.append(str(institution.get("country_code")).upper())
    country = institution_countries[0] if institution_countries else ""
    institutions = ", ".join(institution_names[:8])
    concepts = ", ".join((concept.get("display_name") or "") for concept in (item.get("concepts") or [])[:8])
    text_clean = clean_text(" ".join(part for part in [title, abstract, author_names, institutions, concepts] if part))
    text_normalized = strip_for_compare(text_clean)
    scientific_min_text_chars = min(min_text_chars, 40)
    status = "ok" if len(text_clean) >= scientific_min_text_chars and pdf_url else "ok_partial" if len(text_clean) >= scientific_min_text_chars else "too_short"
    evidence_level, evidence_weight = evidence_rank_for_source_type("scientific_article")
    return NewsRecord(
        query=query,
        query_variants=clean_variants,
        geographic_scope=geographic_scope,
        geographic_terms=clean_geographic_terms,
        year=year,
        source_type="scientific_article",
        source_type_confidence="high",
        source_type_evidence="openalex_oa_work",
        evidence_level=evidence_level,
        evidence_weight=evidence_weight,
        medium=medium,
        url=landing_page_url,
        title=title,
        published_date=str(item.get("publication_date") or year),
        language=str(item.get("language") or ""),
        country=country,
        text_raw_visible=text_clean,
        text_clean=text_clean,
        text_normalized=text_normalized,
        text_length=len(text_clean),
        word_count=len(text_normalized.split()),
        paragraph_count=1 if text_clean else 0,
        cleaning_notes=["openalex_metadata_abstract"] + ([] if pdf_url else ["metadata_only_no_pdf"]),
        source_api="openalex_oa_works",
        fetched_at=dt.datetime.now(dt.UTC).isoformat(),
        status=status,
        error="",
        pdf_url=pdf_url,
    )


def crossref_record(
    item: dict,
    query: str,
    clean_variants: list[str],
    geographic_scope: str,
    clean_geographic_terms: list[str],
    year: int,
    min_text_chars: int,
) -> NewsRecord:
    title_values = item.get("title") or []
    title = clean_text(str(title_values[0] if title_values else ""))
    container_values = item.get("container-title") or []
    medium = clean_text(str(container_values[0] if container_values else "Crossref"))
    doi = str(item.get("DOI") or "").strip()
    url = str(item.get("URL") or (f"https://doi.org/{doi}" if doi else item.get("resource", {}).get("primary", {}).get("URL", ""))).strip()
    pdf_url = ""
    for link in item.get("link") or []:
        content_type = str(link.get("content-type") or "").lower()
        candidate_url = str(link.get("URL") or "")
        if "pdf" in content_type or candidate_url.lower().endswith(".pdf"):
            pdf_url = candidate_url
            break
    abstract = strip_markup(str(item.get("abstract") or ""))
    subjects = ", ".join(str(subject) for subject in (item.get("subject") or [])[:8])
    authors = ", ".join(
        clean_text(" ".join([str(author.get("given", "")), str(author.get("family", ""))]))
        for author in (item.get("author") or [])[:8]
    )
    text_clean = clean_text(" ".join(part for part in [title, abstract, authors, subjects] if part))
    text_normalized = strip_for_compare(text_clean)
    published = item.get("published-print") or item.get("published-online") or item.get("published")
    date_parts = (published or {}).get("date-parts") or [[year]]
    published_date = "-".join(str(part) for part in date_parts[0]) if date_parts and date_parts[0] else str(year)
    scientific_min_text_chars = min(min_text_chars, 40)
    status = "ok" if len(text_clean) >= scientific_min_text_chars and pdf_url else "ok_partial" if len(text_clean) >= scientific_min_text_chars else "too_short"
    evidence_level, evidence_weight = evidence_rank_for_source_type("scientific_article")
    return NewsRecord(
        query=query,
        query_variants=clean_variants,
        geographic_scope=geographic_scope,
        geographic_terms=clean_geographic_terms,
        year=year,
        source_type="scientific_article",
        source_type_confidence="medium",
        source_type_evidence="crossref_full_text_metadata",
        evidence_level=evidence_level,
        evidence_weight=evidence_weight,
        medium=medium or "Crossref",
        url=url,
        title=title,
        published_date=published_date,
        language=str(item.get("language") or ""),
        country="",
        text_raw_visible=text_clean,
        text_clean=text_clean,
        text_normalized=text_normalized,
        text_length=len(text_clean),
        word_count=len(text_normalized.split()),
        paragraph_count=1 if text_clean else 0,
        cleaning_notes=["crossref_metadata_abstract"] + ([] if pdf_url else ["metadata_only_no_pdf"]),
        source_api="crossref_works",
        fetched_at=dt.datetime.now(dt.UTC).isoformat(),
        status=status,
        error="",
        pdf_url=pdf_url,
    )


def redalyc_record(
    item: dict,
    query: str,
    clean_variants: list[str],
    geographic_scope: str,
    clean_geographic_terms: list[str],
    year: int,
    min_text_chars: int,
) -> NewsRecord:
    title = strip_markup(str(item.get("titulo") or ""))
    medium = clean_text(str(item.get("nomRevista") or "Redalyc"))
    article_id = str(item.get("cveArticulo") or "").strip()
    journal_id = str(item.get("cveRevista") or "").strip()
    url = urllib.parse.urljoin(REDALYC_BASE_URL, f"/articulo.oa?id={article_id}") if article_id else REDALYC_BASE_URL
    pdf_url = redalyc_pdf_url(item)
    authors = strip_markup(str(item.get("autores") or item.get("apellidoNombre") or ""))
    keywords = strip_markup(str(item.get("palabras") or "").replace(">>>", ". "))
    abstract = strip_markup(str(item.get("resumen") or "").replace(">>>", ". "))
    content = strip_markup(str(item.get("contenido") or ""))
    journal_institution = strip_markup(str(item.get("nomInstitucionRev") or ""))
    text_clean = clean_text(" ".join(part for part in [title, abstract, keywords, authors, journal_institution, content] if part))
    text_normalized = strip_for_compare(text_clean)
    scientific_min_text_chars = min(min_text_chars, 40)
    status = "ok" if len(text_clean) >= scientific_min_text_chars and pdf_url else "ok_partial" if len(text_clean) >= scientific_min_text_chars else "too_short"
    evidence_level, evidence_weight = evidence_rank_for_source_type("scientific_article")
    return NewsRecord(
        query=query,
        query_variants=clean_variants,
        geographic_scope=geographic_scope,
        geographic_terms=clean_geographic_terms,
        year=year,
        source_type="scientific_article",
        source_type_confidence="high",
        source_type_evidence="redalyc_open_access_article",
        evidence_level=evidence_level,
        evidence_weight=evidence_weight,
        medium=medium or "Redalyc",
        url=url,
        title=title,
        published_date=str(item.get("anioArticulo") or item.get("anoEdcNum") or year),
        language=str(item.get("idiomaArticulo") or ""),
        country=str(item.get("paisRevista") or item.get("paisInstitucion") or ""),
        text_raw_visible=text_clean,
        text_clean=text_clean,
        text_normalized=text_normalized,
        text_length=len(text_clean),
        word_count=len(text_normalized.split()),
        paragraph_count=1 if text_clean else 0,
        cleaning_notes=["redalyc_metadata_abstract", f"redalyc_journal:{journal_id}"] + ([] if pdf_url else ["metadata_only_no_pdf"]),
        source_api="redalyc_r2020_articles",
        fetched_at=dt.datetime.now(dt.UTC).isoformat(),
        status=status,
        error="",
        pdf_url=pdf_url,
    )


def classify_source_type(article: dict, url: str, medium: str, title: str = "") -> tuple[str, str, str]:
    """Classify the discursive source genre for narrative-structure analysis.

    Categories used in the project:
    1. scientific_article: indexed papers, journals, preprints, DOI-like pages.
    2. institutional_report: government, public agencies, NGOs, international organisms.
    3. industry_report: professional surveys, institutional reports, vendor/industry studies.
    3. news: journalistic or magazine/news pages.
    4. forum: user/community discussion spaces.
    5. other: evidence is insufficient.

    Scientific markers are checked before generic news markers because many
    research sites contain words such as "science" or "article" in paths.
    """
    haystack = " ".join(
        [
            url,
            medium,
            title,
            str(article.get("sourceCommonName", "")),
            str(article.get("domain", "")),
        ]
    ).lower()
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.lower()
    domain = medium.lower().replace("www.", "")

    scientific_markers = [
        "doi.org",
        "pubmed.ncbi.nlm.nih.gov",
        "ncbi.nlm.nih.gov/pmc",
        "sciencedirect.com",
        "springer.com",
        "link.springer.com",
        "tandfonline.com",
        "wiley.com",
        "sagepub.com",
        "jstor.org",
        "mdpi.com",
        "frontiersin.org",
        "plos.org",
        "nature.com",
        "science.org",
        "arxiv.org",
        "biorxiv.org",
        "medrxiv.org",
        "scielo.",
        "redalyc.org",
        "dialnet.unirioja.es",
        "researchgate.net/publication",
    ]
    forum_markers = [
        "reddit.com",
        "quora.com",
        "stackexchange.com",
        "stackoverflow.com",
        "forum",
        "forums.",
        "/forum/",
        "/forums/",
        "community.",
        "/community/",
        "groups.google.com",
        "discourse.",
        "tapatalk.com",
        "medium.com",
        "substack.com",
        "wordpress.com",
        "blogspot.com",
        "tumblr.com",
        "dev.to",
        "news.ycombinator.com",
        "tattoo.com",
        "tattooing101.com",
        "tattoodo.com",
        "inkppl.com",
        "tattooers.net",
    ]
    industry_markers = [
        "survey.stackoverflow.co",
        "stackoverflow.blog",
        "developer survey",
        "github.blog",
        "octoverse.github.com",
        "mckinsey.com",
        "gartner.com",
        "forrester.com",
        "idc.com",
        "statista.com",
        "state of software",
        "state of dev",
        "state of ai",
    ]
    institutional_markers = [
        ".gob.mx",
        "gob.mx",
        "salud.gob.mx",
        "cofepris.gob.mx",
        "dof.gob.mx",
        "diputados.gob.mx",
        "senado.gob.mx",
        "inegi.org.mx",
        "who.int",
        "paho.org",
        "unesco.org",
        "un.org",
        "oecd.org",
        "worldbank.org",
        "government",
        "secretaria de salud",
        "secretaría de salud",
        "cofepris",
        "diario oficial",
        "norma oficial",
        "lineamiento",
        "regulacion sanitaria",
        "regulación sanitaria",
    ]
    news_markers = [
        "/news/",
        "/noticias/",
        "/world/",
        "/politics/",
        "/society/",
        "/science/",
        "/salud/",
        "/opinion/",
        "news",
        "times",
        "post",
        "journal",
        "diario",
        "jornada",
        "elpais",
        "bbc.",
        "cnn.",
        "reuters",
        "apnews",
        "nytimes",
        "washingtonpost",
        "theguardian",
    ]

    if any(marker in haystack for marker in scientific_markers):
        return "scientific_article", "high", "scientific domain/index marker"
    if re.search(r"\bdoi\b|/article/|/abstract|/fulltext|/journal|/paper|/publication/", path):
        return "scientific_article", "medium", "scientific URL path marker"
    if any(marker in haystack for marker in industry_markers):
        return "industry_report", "high", "industry survey/report marker"
    if any(marker in haystack for marker in institutional_markers):
        return "institutional_report", "high", "government/institutional marker"
    if any(marker in haystack for marker in forum_markers):
        return "forum", "high", "forum/community domain or path marker"
    if any(marker in haystack for marker in news_markers):
        return "news", "medium", "news domain or section marker"
    if article.get("sourceCommonName") or article.get("domain"):
        return "news", "low", "GDELT indexed source, no stronger genre marker"
    if domain:
        return "other", "low", "domain present but genre unclear"
    return "other", "low", "insufficient source evidence"


def evidence_rank_for_source_type(source_type: str) -> tuple[str, int]:
    mapping = {
        "scientific_article": ("peer_reviewed_or_academic_highest", 4),
        "institutional_report": ("government_or_institutional_public_record", 3),
        "industry_report": ("industry_survey_or_report", 3),
        "news": ("specialized_or_journalistic_context", 2),
        "forum": ("professional_practice_discussion", 1),
        "other": ("unclear_low", 0),
    }
    return mapping.get(source_type, mapping["other"])


def stable_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def normalize_dedup_text(value: str) -> str:
    table = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")
    value = (value or "").lower().translate(table)
    value = re.sub(r"^https?://", "", value)
    value = re.sub(r"^www\.", "", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def canonical_url_key(url: str) -> str:
    url = (url or "").strip().lower()
    url = re.sub(r"^https?://", "", url)
    url = re.sub(r"^www\.", "", url)
    url = url.split("#", 1)[0].split("?", 1)[0]
    return url.rstrip("/")


def canonical_doi_key(*values: str) -> str:
    haystack = " ".join(value or "" for value in values)
    match = re.search(r"10\.\d{4,9}/[^\s\"<>]+", haystack, flags=re.I)
    if not match:
        return ""
    return match.group(0).lower().rstrip(".,;)")


def document_dedup_key_from_values(
    *,
    url: str = "",
    title: str = "",
    year: int | str = "",
    medium: str = "",
    pdf_url: str = "",
) -> str:
    doi = canonical_doi_key(url, pdf_url)
    if doi:
        return f"doi:{doi}"
    normalized_url = canonical_url_key(url)
    normalized_title = normalize_dedup_text(title)
    normalized_medium = normalize_dedup_text(medium)
    if normalized_title and year and normalized_medium:
        return f"title_year_medium:{year}:{normalized_medium}:{normalized_title[:180]}"
    if normalized_url:
        return f"url:{normalized_url}"
    if normalized_title and year:
        return f"title_year:{year}:{normalized_title[:180]}"
    return ""


def document_dedup_key(record: NewsRecord) -> str:
    return document_dedup_key_from_values(
        url=record.url,
        title=record.title,
        year=record.year,
        medium=record.medium,
        pdf_url=record.pdf_url,
    )


def article_dedup_key(article: dict, fallback_year: int | str = "") -> str:
    url = str(article.get("url") or article.get("link") or article.get("id") or "")
    title = str(article.get("title") or article.get("name") or article.get("display_name") or "")
    medium = str(article.get("sourceCommonName") or article.get("domain") or article.get("medium") or "")
    year = article_year(article, int(fallback_year or 0)) if str(fallback_year).isdigit() else fallback_year
    return document_dedup_key_from_values(url=url, title=title, year=year, medium=medium)


def should_stop(stop_requested) -> bool:
    return bool(stop_requested and stop_requested())


def interruptible_sleep(seconds: float, stop_requested=None) -> bool:
    """Sleep in small chunks. Return True when a stop was requested."""
    deadline = time.monotonic() + max(0, seconds)
    while time.monotonic() < deadline:
        if should_stop(stop_requested):
            return True
        time.sleep(min(0.25, max(0, deadline - time.monotonic())))
    return should_stop(stop_requested)


def crawl_news(
    query: str,
    start_year: int,
    end_year: int,
    start_month: int | None = None,
    end_month: int | None = None,
    domains: list[str] | None = None,
    query_variants: list[str] | None = None,
    geographic_scope: str = "global",
    geographic_terms: list[str] | None = None,
    exclude_terms: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    source_modes: list[str] | None = None,
    output_dir: Path | str = "news_output",
    max_records_per_month: int = 50,
    max_records_per_source_type_year: int = 100,
    target_min_per_source_type_year: int = 0,
    required_source_types: list[str] | None = None,
    accept_source_types: list[str] | None = None,
    seed_url_file: str | Path | None = None,
    download_pdfs: bool = False,
    strict_open_access_articles: bool = True,
    delay_seconds: float = 1.0,
    search_delay_seconds: float = 2.0,
    min_text_chars: int = 600,
    save_every: int = 25,
    progress=None,
    stop_requested=None,
) -> list[NewsRecord]:
    if start_year > end_year:
        raise ValueError("start_year must be <= end_year")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    clean_variants = clean_query_variants(query, query_variants)[1:]
    clean_geographic_terms = clean_query_variants("", geographic_terms)
    clean_exclude_terms = clean_query_variants("", exclude_terms)
    clean_exclude_domains = [
        domain.strip().lower().replace("https://", "").replace("http://", "").strip("/")
        for domain in (exclude_domains or [])
        if domain.strip()
    ]
    active_source_modes = source_modes or ["gdelt_news"]
    required_source_type_set = {str(item).strip() for item in (required_source_types or []) if str(item).strip()}
    accept_source_type_set = {str(item).strip() for item in (accept_source_types or []) if str(item).strip()}
    effective_query = build_query(
        query,
        domains or [],
        clean_variants,
        clean_geographic_terms,
        exclude_terms=clean_exclude_terms,
        exclude_domains=clean_exclude_domains,
    )
    google_news_query = build_google_news_query(
        query,
        domains or [],
        clean_variants,
        clean_geographic_terms,
        exclude_terms=clean_exclude_terms,
        exclude_domains=clean_exclude_domains,
    )
    reddit_compact_terms = compact_query_variants(query, clean_variants, limit=8)
    reddit_rss_query_plan = [
        f"{quote_query_term(term)} {' '.join(clean_geographic_terms[:2])}".strip()
        for term in (reddit_compact_terms or [query])
    ]
    seed_url_articles = load_seed_url_articles(seed_url_file)
    if progress and seed_url_articles:
        seed_types = sorted(source_types_in_seed_file(seed_url_file))
        progress(
            f"Seed URLs loaded: {len(seed_url_articles)} from {seed_url_file}"
            f"{' · source_types=' + ','.join(seed_types) if seed_types else ''}"
        )
    seen_document_keys: set[str] = set()
    records: list[NewsRecord] = []
    accepted_by_year_type: dict[tuple[int, str], int] = {}

    def can_accept_record(year: int, source_type: str) -> bool:
        cap = int(max_records_per_source_type_year or 0)
        if cap <= 0:
            return True
        return accepted_by_year_type.get((int(year), str(source_type)), 0) < cap

    def mark_accepted_record(year: int, source_type: str) -> None:
        key = (int(year), str(source_type))
        accepted_by_year_type[key] = accepted_by_year_type.get(key, 0) + 1

    def accepted_count(year: int, source_type: str) -> int:
        return accepted_by_year_type.get((int(year), str(source_type)), 0)

    def balance_status(year: int, source_type: str) -> str:
        cap = int(max_records_per_source_type_year or 0)
        target = int(target_min_per_source_type_year or 0)
        observed = accepted_count(year, source_type)
        if target > 0:
            if cap > 0:
                return f"{observed}/min {target} · max {cap}"
            return f"{observed}/min {target}"
        if cap > 0:
            return f"{observed}/max {cap}"
        return str(observed)

    periods = list(month_periods(start_year, end_year, start_month=start_month, end_month=end_month))
    gdelt_news_cooldown_until = 0
    gdelt_forums_cooldown_until = 0
    run_indexed_news = bool(seed_url_articles) or any(mode in active_source_modes for mode in {"gdelt_news", "institutional_gdelt", "forums", "google_news_rss", "reddit_rss", "seed_urls"})
    if run_indexed_news:
        if progress:
            progress(f"Effective indexed query design: {effective_query[:500]}{'...' if len(effective_query) > 500 else ''}")
    for period_index, (start, end) in enumerate(periods, start=1):
        if not run_indexed_news:
            break
        if should_stop(stop_requested):
            if progress:
                progress("Stopped by user before next month.")
            break
        if progress:
            progress(f"Searching {start:%Y-%m} ({period_index}/{len(periods)})")
        articles: list[dict] = []
        seed_rows_for_period = [
            row for row in seed_url_articles
            if (parsed := parse_seed_date(str(row.get("seendate") or ""))) and start <= parsed <= end
        ]
        if seed_rows_for_period:
            articles.extend(seed_rows_for_period)
            if progress:
                progress(f"Seed URLs {start:%Y-%m}: {len(seed_rows_for_period)}")
        if ("gdelt_news" in active_source_modes or "institutional_gdelt" in active_source_modes) and period_index >= gdelt_news_cooldown_until:
            try:
                news_query_plan = build_gdelt_news_query_plan(
                    query,
                    domains or [],
                    clean_variants,
                    clean_geographic_terms,
                    clean_exclude_terms,
                    clean_exclude_domains,
                )
                if progress:
                    progress(
                        f"GDELT news adaptive plan: {len(news_query_plan)} short queries "
                        f"({len({tuple(item['domains']) for item in news_query_plan})} domain batches)"
                    )
                news_batches_with_hits: set[tuple[str, ...]] = set()
                gdelt_news_month_blocked = False
                for plan_index, plan_item in enumerate(news_query_plan, start=1):
                    domain_key = tuple(plan_item["domains"])
                    if domain_key in news_batches_with_hits:
                        continue
                    if gdelt_news_month_blocked or should_stop(stop_requested):
                        break
                    gdelt_query = plan_item["query"]
                    if progress:
                        domains_label = ",".join(domain_key) if domain_key else "open"
                        progress(
                            f"GDELT news batch {plan_index}/{len(news_query_plan)} · "
                            f"term '{plan_item['term']}' · domains {domains_label}: {gdelt_query}"
                        )
                    rows, status = search_gdelt_with_status(
                        gdelt_query,
                        start,
                        end,
                        max(5, min(max_records_per_month, 50)),
                        attempts=1,
                        base_wait_seconds=max(8, search_delay_seconds),
                        stop_requested=stop_requested,
                        progress=progress,
                        label="GDELT news",
                    )
                    if status in {"rate_limited", "stopped"}:
                        gdelt_news_month_blocked = True
                        if status == "rate_limited":
                            gdelt_news_cooldown_until = period_index + 4
                        if progress:
                            progress(
                                f"GDELT news {start:%Y-%m}: stopped remaining news GDELT queries because status={status}. "
                                f"Cooling down until month index {gdelt_news_cooldown_until}."
                            )
                        break
                    if rows:
                        news_batches_with_hits.add(domain_key)
                    articles.extend(rows)
                    if interruptible_sleep(max(0.5, search_delay_seconds / 3), stop_requested):
                        if progress:
                            progress("Stopped by user during GDELT news batch delay.")
                        break
                if interruptible_sleep(search_delay_seconds, stop_requested):
                    if progress:
                        progress("Stopped by user during search delay.")
                    break
            except urllib.error.HTTPError as exc:
                if progress:
                    progress(f"GDELT search error {start:%Y-%m}: HTTP {exc.code} {exc.reason}")
            except Exception as exc:  # noqa: BLE001
                if progress:
                    progress(f"GDELT search error {start:%Y-%m}: {exc}")
        elif ("gdelt_news" in active_source_modes or "institutional_gdelt" in active_source_modes) and period_index < gdelt_news_cooldown_until:
            if progress:
                progress(
                    f"GDELT news skipped {start:%Y-%m}: source cooling down after rate limit; "
                    "using seed/RSS/other layers instead."
                )
        if "forums" in active_source_modes and period_index >= gdelt_forums_cooldown_until:
            try:
                forum_domain_markers = (
                    "reddit",
                    "quora",
                    "stackexchange",
                    "stackoverflow",
                    "forum",
                    "hacker",
                    "dev.to",
                    "medium.com",
                    "substack.com",
                    "wordpress.com",
                    "blogspot.com",
                    "tumblr.com",
                    "tattoo",
                    "inkppl",
                )
                forum_domains = [
                    domain for domain in (domains or [])
                    if any(marker in domain.lower() for marker in forum_domain_markers)
                ]
                forum_domains = unique_sequence([*forum_domains, *DEFAULT_FORUM_DOMAINS])
                forum_query_plan = build_forum_gdelt_query_plan(
                    query,
                    forum_domains,
                    clean_variants,
                    clean_geographic_terms,
                    clean_exclude_terms,
                    clean_exclude_domains,
                )
                if progress:
                    progress(
                        "GDELT forums adaptive plan: "
                        f"{len({item['domain'] for item in forum_query_plan})} domains × sequential terms × geo/no_geo"
                    )
                forum_domains_with_hits: set[str] = set()
                gdelt_forums_month_blocked = False
                for batch_index, plan_item in enumerate(forum_query_plan, start=1):
                    if gdelt_forums_month_blocked:
                        break
                    domain = plan_item["domain"]
                    if domain in forum_domains_with_hits:
                        continue
                    if should_stop(stop_requested):
                        if progress:
                            progress("Stopped by user before next forum query batch.")
                        break
                    forum_query = plan_item["query"]
                    if progress:
                        progress(
                            f"GDELT forums {domain}: term {plan_item['stage']} "
                            f"'{plan_item['term']}' · {plan_item.get('geo_mode', 'geo')} → {forum_query}"
                        )
                    forum_rows, forum_status = search_gdelt_with_status(
                        forum_query,
                        start,
                        end,
                        max(5, min(25, max_records_per_month // 4)),
                        attempts=1,
                        base_wait_seconds=max(8, search_delay_seconds),
                        stop_requested=stop_requested,
                        progress=progress,
                        label=f"GDELT forums {domain}",
                    )
                    if forum_status in {"rate_limited", "stopped"}:
                        gdelt_forums_month_blocked = True
                        if forum_status == "rate_limited":
                            gdelt_forums_cooldown_until = period_index + 4
                        if progress:
                            progress(
                                f"GDELT forums {start:%Y-%m}: stopped remaining forum GDELT queries "
                                f"because status={forum_status}. Cooling down until month index {gdelt_forums_cooldown_until}. "
                                "Switching to curated public conversation seeds/RSS if configured."
                            )
                        break
                    if forum_status == "bad_query":
                        continue
                    if forum_rows:
                        forum_domains_with_hits.add(domain)
                        if progress:
                            progress(
                                f"GDELT forums {domain}: {len(forum_rows)} hits with '{plan_item['term']}', "
                                f"{plan_item.get('geo_mode', 'geo')}; skipping later synonyms for this domain."
                            )
                    articles.extend(forum_rows)
                    if interruptible_sleep(max(1.0, search_delay_seconds / 2), stop_requested):
                        if progress:
                            progress("Stopped by user during forums batch delay.")
                        break
                if interruptible_sleep(search_delay_seconds, stop_requested):
                    if progress:
                        progress("Stopped by user during forums search delay.")
                    break
            except urllib.error.HTTPError as exc:
                if progress:
                    progress(f"GDELT forums search error {start:%Y-%m}: HTTP {exc.code} {exc.reason}")
            except Exception as exc:  # noqa: BLE001
                if progress:
                    progress(f"GDELT forums search error {start:%Y-%m}: {exc}")
        elif "forums" in active_source_modes and period_index < gdelt_forums_cooldown_until:
            if progress:
                progress(
                    f"GDELT forums skipped {start:%Y-%m}: source cooling down after rate limit; "
                    "try public blogs/seed URLs or lower forum target."
                )
        if "google_news_rss" in active_source_modes:
            try:
                if progress:
                    progress(f"Google News RSS {start:%Y-%m}")
                rss_rows, rss_diag = search_google_news_rss(google_news_query, start, end, max_records_per_month)
                if progress and not rss_rows:
                    progress(
                        f"Google News RSS {start:%Y-%m}: 0 dated items in requested period "
                        f"(returned={rss_diag['total_items']}, outside_period={rss_diag['outside_period_items']}, "
                        f"undated={rss_diag['undated_items']}). RSS is weak for historical months."
                    )
                articles.extend(rss_rows)
                if interruptible_sleep(search_delay_seconds, stop_requested):
                    if progress:
                        progress("Stopped by user during Google News RSS delay.")
                    break
            except Exception as exc:  # noqa: BLE001
                if progress:
                    progress(f"Google News RSS error {start:%Y-%m}: {exc}")
        if "reddit_rss" in active_source_modes:
            try:
                reddit_rows: list[dict] = []
                for reddit_stage, reddit_query in enumerate(reddit_rss_query_plan, start=1):
                    if should_stop(stop_requested):
                        if progress:
                            progress("Stopped by user before next Reddit RSS query.")
                        break
                    if progress:
                        progress(f"Reddit RSS {start:%Y-%m}: term {reddit_stage} → {reddit_query}")
                    try:
                        reddit_rows = search_reddit_rss(reddit_query, start, end, max_records_per_month)
                    except urllib.error.HTTPError as exc:
                        if exc.code == 429:
                            if progress:
                                progress(
                                    f"Reddit RSS {start:%Y-%m}: rate limited on term {reddit_stage}; "
                                    "skipping remaining Reddit synonyms for this month."
                                )
                            reddit_rows = []
                            break
                        raise
                    if reddit_rows:
                        if progress:
                            progress(
                                f"Reddit RSS {start:%Y-%m}: {len(reddit_rows)} hits with term {reddit_stage}; "
                                "skipping later synonyms."
                            )
                        break
                articles.extend(reddit_rows)
                if interruptible_sleep(search_delay_seconds, stop_requested):
                    if progress:
                        progress("Stopped by user during Reddit RSS delay.")
                    break
            except Exception as exc:  # noqa: BLE001
                if progress:
                    progress(f"Reddit RSS error {start:%Y-%m}: {exc}")

        for article in articles:
            if should_stop(stop_requested):
                if progress:
                    progress("Stopped by user before next article.")
                break
            url = str(article.get("url", "")).strip()
            dedup_key = article_dedup_key(article, start.year)
            if not url or (dedup_key and dedup_key in seen_document_keys):
                continue
            if dedup_key:
                seen_document_keys.add(dedup_key)
            published = str(article.get("seendate", "") or article.get("publishedDate", ""))
            year = article_year(article, start.year)
            medium = infer_medium(article, url)
            title = clean_text(str(article.get("title", "")))
            excluded, reason = contains_excluded_content(
                url,
                medium,
                title,
                "",
                exclude_terms=clean_exclude_terms,
                exclude_domains=clean_exclude_domains,
            )
            if excluded:
                if progress:
                    progress(f"excluded: {year} · {medium} · {reason} · {title[:70]}")
                continue
            if article.get("source_type_override"):
                source_type = str(article.get("source_type_override"))
                source_type_confidence = "high"
                source_type_evidence = str(article.get("source_type_evidence_override") or "manual_or_index_override")
            else:
                source_type, source_type_confidence, source_type_evidence = classify_source_type(
                    article=article,
                    url=url,
                    medium=medium,
                    title=title,
                )
            if accept_source_type_set and source_type not in accept_source_type_set:
                if progress:
                    progress(f"skipped_layer: {year} · wanted {sorted(accept_source_type_set)} · got {source_type} · {medium} · {title[:70]}")
                continue
            evidence_level, evidence_weight = evidence_rank_for_source_type(source_type)
            language = str(article.get("language", ""))
            country = str(article.get("sourceCountry", ""))
            try:
                source_weight_factor = float(article.get("source_weight_factor") or 1.0)
            except (TypeError, ValueError):
                source_weight_factor = 1.0
            fetched_at = dt.datetime.now(dt.UTC).isoformat()
            rss_partial_text = clean_text(" ".join([
                title,
                str(article.get("rss_description") or ""),
                str(article.get("abstract") or ""),
                str(article.get("authors") or ""),
                str(article.get("keywords") or ""),
            ]))
            metadata_partial_text = rss_partial_text or title

            force_partial_access = False
            access_policy = {"access": "unknown"}
            try:
                if article.get("source_api") == "reddit_rss":
                    text_raw_visible = rss_partial_text
                else:
                    access_policy = source_access_policy(url)
                    force_partial_access = access_policy.get("access") in {"partial", "paywall"}
                    allowed, robots_note = robots_allowed(url)
                    if not allowed:
                        raise PermissionError(robots_note)
                    page = request_html(url, timeout=12)
                    text_raw_visible = extract_visible_text(page)
                cleaned = clean_article_text(text_raw_visible, title=title, source_url=url)
                text_clean = cleaned["text_clean"]
                text_normalized = cleaned["text_normalized"]
                word_count = cleaned["word_count"]
                paragraph_count = cleaned["paragraph_count"]
                cleaning_notes = cleaned["cleaning_notes"]
                if len(text_clean) < min_text_chars:
                    if len(metadata_partial_text) >= 30:
                        partial_cleaned = clean_partial_metadata_text(metadata_partial_text)
                        text_raw_visible = metadata_partial_text
                        text_clean = partial_cleaned["text_clean"]
                        text_normalized = partial_cleaned["text_normalized"]
                        word_count = partial_cleaned["word_count"]
                        paragraph_count = partial_cleaned["paragraph_count"]
                        cleaning_notes = partial_cleaned["cleaning_notes"] + ["partial_metadata_record", f"partial_source:{article.get('source_api') or 'indexed_news'}"]
                        status = "ok_partial"
                    else:
                        status = "too_short"
                else:
                    if article.get("source_api") == "reddit_rss":
                        status = "ok_partial"
                        cleaning_notes = cleaning_notes + ["public_rss_partial"]
                    elif force_partial_access:
                        status = "ok_partial"
                        cleaning_notes = cleaning_notes + [
                            f"access_policy:{access_policy.get('access')}",
                            "metadata_or_visible_excerpt_not_fulltext",
                        ]
                    else:
                        status = "ok"
                error = ""
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, PermissionError) as exc:
                if len(metadata_partial_text) >= 30:
                    partial_cleaned = clean_partial_metadata_text(metadata_partial_text)
                    text_raw_visible = metadata_partial_text
                    text_clean = partial_cleaned["text_clean"]
                    text_normalized = partial_cleaned["text_normalized"]
                    word_count = partial_cleaned["word_count"]
                    paragraph_count = partial_cleaned["paragraph_count"]
                    cleaning_notes = partial_cleaned["cleaning_notes"] + ["partial_metadata_record", "full_fetch_failed_or_not_allowed", f"partial_source:{article.get('source_api') or 'indexed_news'}"]
                    status = "ok_partial"
                    error = f"full_fetch_failed:{exc}"
                else:
                    text_raw_visible = ""
                    text_clean = ""
                    text_normalized = ""
                    word_count = 0
                    paragraph_count = 0
                    cleaning_notes = []
                    status = "fetch_error"
                    error = str(exc)
            except Exception as exc:  # noqa: BLE001
                text_raw_visible = ""
                text_clean = ""
                text_normalized = ""
                word_count = 0
                paragraph_count = 0
                cleaning_notes = []
                status = "error"
                error = str(exc)

            excluded, reason = contains_excluded_content(
                url,
                medium,
                title,
                text_clean,
                exclude_terms=clean_exclude_terms,
                exclude_domains=clean_exclude_domains,
            )
            if excluded:
                if progress:
                    progress(f"excluded: {year} · {medium} · {reason} · {title[:70]}")
                continue
            geo_ok, geo_reason = passes_geographic_filter(
                geographic_scope,
                clean_geographic_terms,
                url,
                medium,
                title,
                text_clean,
                country=country,
            )
            if not geo_ok:
                if progress:
                    progress(f"excluded_geo: {year} · {medium} · {geo_reason} · {title[:70]}")
                continue
            if not can_accept_record(year, source_type):
                if progress:
                    progress(f"cap_reached: {year} · {source_type} · max {max_records_per_source_type_year}/year/type")
                continue

            record = NewsRecord(
                query=query,
                query_variants=clean_variants,
                geographic_scope=geographic_scope,
                geographic_terms=clean_geographic_terms,
                year=year,
                source_type=source_type,
                source_type_confidence=source_type_confidence,
                source_type_evidence=source_type_evidence,
                evidence_level=evidence_level,
                evidence_weight=evidence_weight,
                medium=medium,
                url=url,
                title=title,
                published_date=published,
                language=language,
                country=country,
                text_raw_visible=text_raw_visible,
                text_clean=text_clean,
                text_normalized=text_normalized,
                text_length=len(text_clean),
                word_count=word_count,
                paragraph_count=paragraph_count,
                cleaning_notes=cleaning_notes,
                source_api=str(article.get("source_api") or "gdelt_doc_2_1"),
                fetched_at=fetched_at,
                status=status,
                error=error,
                pdf_url=str(article.get("pdf_url") or ""),
                source_weight_factor=source_weight_factor,
            )
            if download_pdfs and record.pdf_url:
                pdf_file, pdf_status = download_pdf_file(record.pdf_url, output_dir, record.year, stable_id(record.url or record.pdf_url), timeout=10)
                record.pdf_file = pdf_file
                record.pdf_status = pdf_status
                record = enrich_record_with_pdf_text(record)
            records.append(record)
            if record_is_usable_for_analysis(record):
                mark_accepted_record(record.year, record.source_type)
            try:
                save_incremental_record(output_dir, record)
                append_record_jsonl(output_dir, record)
                if len(records) % max(1, int(save_every)) == 0:
                    save_outputs(output_dir, records, scan_existing=False)
            except OSError as exc:
                if progress:
                    progress(f"save warning: {exc}")
            if progress:
                progress(f"{status}: {year} · {record.source_type} {balance_status(year, record.source_type)} · len={record.text_length} · {medium} · {title[:80]}")
            if interruptible_sleep(delay_seconds, stop_requested):
                if progress:
                    progress("Stopped by user during page delay.")
                break
        if progress and required_source_type_set:
            summary = ", ".join(
                f"{source_type}={balance_status(start.year, source_type)}"
                for source_type in sorted(required_source_type_set)
            )
            progress(f"balance_status: {start.year}-{start.month:02d} · {summary}")

    if any(mode in active_source_modes for mode in {"openalex_oa", "crossref", "redalyc"}):
        academic_queries = build_academic_query_plan(query, clean_variants, clean_geographic_terms)
        scientific_exclude_terms = academic_exclude_terms(clean_exclude_terms)

    if "openalex_oa" in active_source_modes:
        if progress:
            progress(
                f"OpenAlex OA queries: {', '.join(academic_queries)}"
                + (" · strict_open_access_articles=true" if strict_open_access_articles else " · includes metadata fallback")
            )
        for year in range(start_year, end_year + 1):
            if should_stop(stop_requested):
                if progress:
                    progress("Stopped by user before next OpenAlex year.")
                break
            if progress:
                progress(f"Searching OpenAlex OA {year}")
            try:
                items = []
                for academic_query in academic_queries:
                    oa_items = search_openalex_year(academic_query, year, max_records_per_month, oa_only=True)
                    items.extend(oa_items)
                    if not strict_open_access_articles and len(oa_items) < max_records_per_month:
                        items.extend(
                            search_openalex_year(
                                academic_query,
                                year,
                                max(0, max_records_per_month - len(oa_items)),
                                oa_only=False,
                            )
                        )
                    if interruptible_sleep(search_delay_seconds, stop_requested):
                        if progress:
                            progress("Stopped by user during OpenAlex search delay.")
                        break
            except urllib.error.HTTPError as exc:
                if progress:
                    progress(f"OpenAlex search error {year}: HTTP {exc.code} {exc.reason}")
                continue
            except Exception as exc:  # noqa: BLE001
                if progress:
                    progress(f"OpenAlex search error {year}: {exc}")
                continue
            for item in items:
                if should_stop(stop_requested):
                    if progress:
                        progress("Stopped by user before next OpenAlex item.")
                    break
                record = openalex_record(
                    item=item,
                    query=query,
                    clean_variants=clean_variants,
                    geographic_scope=geographic_scope,
                    clean_geographic_terms=clean_geographic_terms,
                    year=year,
                    min_text_chars=min_text_chars,
                )
                dedup_key = document_dedup_key(record)
                if not record.url or (dedup_key and dedup_key in seen_document_keys):
                    continue
                if dedup_key:
                    seen_document_keys.add(dedup_key)
                if strict_open_access_articles and not record.pdf_url:
                    if progress:
                        progress(f"excluded_closed_or_metadata_only: {year} · OpenAlex · no_pdf_url · {record.medium} · {record.title[:70]}")
                    continue
                excluded, reason = contains_excluded_content(
                    record.url,
                    record.medium,
                    record.title,
                    record.text_clean,
                    exclude_terms=scientific_exclude_terms,
                    exclude_domains=clean_exclude_domains,
                )
                if excluded:
                    if progress:
                        progress(f"excluded: {year} · {record.medium} · {reason} · {record.title[:70]}")
                    continue
                relevant, relevance_reason = academic_topic_relevance(
                    record.title,
                    record.text_clean,
                    query=query,
                    variants=clean_variants,
                )
                if not relevant:
                    if progress:
                        progress(f"excluded: {year} · OpenAlex · {relevance_reason} · {record.title[:70]}")
                    continue
                geo_ok, geo_reason = passes_geographic_filter(
                    geographic_scope,
                    clean_geographic_terms,
                    record.url,
                    record.medium,
                    record.title,
                    record.text_clean,
                    country=record.country,
                )
                if not geo_ok:
                    if progress:
                        progress(f"excluded_geo: {year} · OpenAlex · {geo_reason} · {record.title[:70]}")
                    continue
                if not can_accept_record(record.year, record.source_type):
                    if progress:
                        progress(f"cap_reached: {record.year} · {record.source_type} · max {max_records_per_source_type_year}/year/type")
                    continue
                if download_pdfs and record.pdf_url:
                    pdf_file, pdf_status = download_pdf_file(record.pdf_url, output_dir, record.year, stable_id(record.url or record.pdf_url))
                    record.pdf_file = pdf_file
                    record.pdf_status = pdf_status
                    record = enrich_record_with_pdf_text(record)
                records.append(record)
                if record_is_usable_for_analysis(record):
                    mark_accepted_record(record.year, record.source_type)
                try:
                    save_incremental_record(output_dir, record)
                    append_record_jsonl(output_dir, record)
                    if len(records) % max(1, int(save_every)) == 0:
                        save_outputs(output_dir, records, scan_existing=False)
                except OSError as exc:
                    if progress:
                        progress(f"save warning: {exc}")
                if progress:
                    progress(f"{record.status}: {year} · {record.source_type} {balance_status(year, record.source_type)} · len={record.text_length} · OpenAlex · {record.medium} · {record.title[:80]}")
                if interruptible_sleep(delay_seconds, stop_requested):
                    if progress:
                        progress("Stopped by user during OpenAlex delay.")
                    break

    if "crossref" in active_source_modes:
        if progress:
            progress(
                f"Crossref queries: {', '.join(academic_queries)}"
                + (" · only records with PDF/full-text link are accepted" if strict_open_access_articles else " · metadata-only allowed")
            )
        for year in range(start_year, end_year + 1):
            if should_stop(stop_requested):
                if progress:
                    progress("Stopped by user before next Crossref year.")
                break
            if progress:
                progress(f"Searching Crossref {year}")
            items = []
            for academic_query in academic_queries:
                try:
                    items.extend(search_crossref_year(academic_query, year, max_records_per_month))
                except urllib.error.HTTPError as exc:
                    if progress:
                        progress(f"Crossref query error {year} · {academic_query}: HTTP {exc.code} {exc.reason}")
                except Exception as exc:  # noqa: BLE001
                    if progress:
                        progress(f"Crossref query error {year} · {academic_query}: {exc}")
                if interruptible_sleep(search_delay_seconds, stop_requested):
                    if progress:
                        progress("Stopped by user during Crossref search delay.")
                    break
            for item in items:
                if should_stop(stop_requested):
                    if progress:
                        progress("Stopped by user before next Crossref item.")
                    break
                record = crossref_record(
                    item=item,
                    query=query,
                    clean_variants=clean_variants,
                    geographic_scope=geographic_scope,
                    clean_geographic_terms=clean_geographic_terms,
                    year=year,
                    min_text_chars=min_text_chars,
                )
                dedup_key = document_dedup_key(record)
                if not record.url or (dedup_key and dedup_key in seen_document_keys):
                    continue
                if dedup_key:
                    seen_document_keys.add(dedup_key)
                if strict_open_access_articles and not record.pdf_url:
                    if progress:
                        progress(f"excluded_closed_or_metadata_only: {year} · Crossref · no_pdf_url · {record.medium} · {record.title[:70]}")
                    continue
                excluded, reason = contains_excluded_content(
                    record.url,
                    record.medium,
                    record.title,
                    record.text_clean,
                    exclude_terms=scientific_exclude_terms,
                    exclude_domains=clean_exclude_domains,
                )
                if excluded:
                    if progress:
                        progress(f"excluded: {year} · {record.medium} · {reason} · {record.title[:70]}")
                    continue
                relevant, relevance_reason = academic_topic_relevance(
                    record.title,
                    record.text_clean,
                    query=query,
                    variants=clean_variants,
                )
                if not relevant:
                    if progress:
                        progress(f"excluded: {year} · Crossref · {relevance_reason} · {record.title[:70]}")
                    continue
                geo_ok, geo_reason = passes_geographic_filter(
                    geographic_scope,
                    clean_geographic_terms,
                    record.url,
                    record.medium,
                    record.title,
                    record.text_clean,
                    country=record.country,
                )
                if not geo_ok:
                    if progress:
                        progress(f"excluded_geo: {year} · Crossref · {geo_reason} · {record.title[:70]}")
                    continue
                if not can_accept_record(record.year, record.source_type):
                    if progress:
                        progress(f"cap_reached: {record.year} · {record.source_type} · max {max_records_per_source_type_year}/year/type")
                    continue
                if download_pdfs and record.pdf_url:
                    pdf_file, pdf_status = download_pdf_file(record.pdf_url, output_dir, record.year, stable_id(record.url or record.pdf_url))
                    record.pdf_file = pdf_file
                    record.pdf_status = pdf_status
                    record = enrich_record_with_pdf_text(record)
                records.append(record)
                if record_is_usable_for_analysis(record):
                    mark_accepted_record(record.year, record.source_type)
                try:
                    save_incremental_record(output_dir, record)
                    append_record_jsonl(output_dir, record)
                    if len(records) % max(1, int(save_every)) == 0:
                        save_outputs(output_dir, records, scan_existing=False)
                except OSError as exc:
                    if progress:
                        progress(f"save warning: {exc}")
                if progress:
                    progress(f"{record.status}: {year} · {record.source_type} {balance_status(year, record.source_type)} · len={record.text_length} · Crossref · {record.medium} · {record.title[:80]}")
                if interruptible_sleep(delay_seconds, stop_requested):
                    if progress:
                        progress("Stopped by user during Crossref delay.")
                    break

    if "redalyc" in active_source_modes:
        if progress:
            progress(f"Redalyc OA queries: {', '.join(academic_queries)} · Latin American open-access repository")
        for year in range(start_year, end_year + 1):
            if should_stop(stop_requested):
                if progress:
                    progress("Stopped by user before next Redalyc year.")
                break
            if progress:
                progress(f"Searching Redalyc {year}")
            items: list[dict] = []
            for academic_query in academic_queries:
                try:
                    items.extend(search_redalyc_year(academic_query, year, max_records_per_month))
                except urllib.error.HTTPError as exc:
                    if progress:
                        progress(f"Redalyc query error {year} · {academic_query}: HTTP {exc.code} {exc.reason}")
                except Exception as exc:  # noqa: BLE001
                    if progress:
                        progress(f"Redalyc query error {year} · {academic_query}: {exc}")
                if len(items) >= max_records_per_month:
                    break
                if interruptible_sleep(search_delay_seconds, stop_requested):
                    if progress:
                        progress("Stopped by user during Redalyc search delay.")
                    break
            for item in items:
                if should_stop(stop_requested):
                    if progress:
                        progress("Stopped by user before next Redalyc item.")
                    break
                record = redalyc_record(
                    item=item,
                    query=query,
                    clean_variants=clean_variants,
                    geographic_scope=geographic_scope,
                    clean_geographic_terms=clean_geographic_terms,
                    year=year,
                    min_text_chars=min_text_chars,
                )
                dedup_key = document_dedup_key(record)
                if not record.url or (dedup_key and dedup_key in seen_document_keys):
                    continue
                if dedup_key:
                    seen_document_keys.add(dedup_key)
                if strict_open_access_articles and not record.pdf_url:
                    if progress:
                        progress(f"excluded_closed_or_metadata_only: {year} · Redalyc · no_pdf_url · {record.medium} · {record.title[:70]}")
                    continue
                excluded, reason = contains_excluded_content(
                    record.url,
                    record.medium,
                    record.title,
                    record.text_clean,
                    exclude_terms=scientific_exclude_terms,
                    exclude_domains=clean_exclude_domains,
                )
                if excluded:
                    if progress:
                        progress(f"excluded: {year} · {record.medium} · {reason} · {record.title[:70]}")
                    continue
                relevant, relevance_reason = academic_topic_relevance(
                    record.title,
                    record.text_clean,
                    query=query,
                    variants=clean_variants,
                )
                if not relevant:
                    if progress:
                        progress(f"excluded: {year} · Redalyc · {relevance_reason} · {record.title[:70]}")
                    continue
                geo_ok, geo_reason = passes_geographic_filter(
                    geographic_scope,
                    clean_geographic_terms,
                    record.url,
                    record.medium,
                    record.title,
                    record.text_clean,
                    country=record.country,
                )
                if not geo_ok:
                    if progress:
                        progress(f"excluded_geo: {year} · Redalyc · {geo_reason} · {record.title[:70]}")
                    continue
                if not can_accept_record(record.year, record.source_type):
                    if progress:
                        progress(f"cap_reached: {record.year} · {record.source_type} · max {max_records_per_source_type_year}/year/type")
                    continue
                if download_pdfs and record.pdf_url:
                    pdf_file, pdf_status = download_pdf_file(record.pdf_url, output_dir, record.year, stable_id(record.url or record.pdf_url))
                    record.pdf_file = pdf_file
                    record.pdf_status = pdf_status
                    record = enrich_record_with_pdf_text(record)
                records.append(record)
                if record_is_usable_for_analysis(record):
                    mark_accepted_record(record.year, record.source_type)
                try:
                    save_incremental_record(output_dir, record)
                    append_record_jsonl(output_dir, record)
                    if len(records) % max(1, int(save_every)) == 0:
                        save_outputs(output_dir, records, scan_existing=False)
                except OSError as exc:
                    if progress:
                        progress(f"save warning: {exc}")
                if progress:
                    progress(f"{record.status}: {year} · {record.source_type} {balance_status(year, record.source_type)} · len={record.text_length} · Redalyc · {record.medium} · {record.title[:80]}")
                if interruptible_sleep(delay_seconds, stop_requested):
                    if progress:
                        progress("Stopped by user during Redalyc delay.")
                    break

    try:
        save_outputs(output_dir, records, scan_existing=False)
    except OSError as exc:
        if progress:
            progress(f"final save warning: {exc}. Incremental JSONL and yearly JSON files remain available.")
    if progress and required_source_type_set and int(target_min_per_source_type_year or 0) > 0:
        target = int(target_min_per_source_type_year)
        for year in range(start_year, end_year + 1):
            for source_type in sorted(required_source_type_set):
                observed = accepted_by_year_type.get((int(year), source_type), 0)
                if observed < target:
                    progress(f"coverage_gap: {year} · {source_type} · {observed}/{target}. La araña intentó la búsqueda, pero no alcanzó la meta mínima.")
                else:
                    progress(f"coverage_ok: {year} · {source_type} · {observed}/{target}")
    return records


def save_incremental_record(output_dir: Path, record: NewsRecord) -> None:
    year_dir = output_dir / str(record.year)
    year_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{record.year}_{safe_slug(record.medium)}_{stable_id(record.url)}.json"
    safe_write_text_atomic(
        year_dir / filename,
        json.dumps(asdict(record), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def append_record_jsonl(output_dir: Path, record: NewsRecord) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "news_records_incremental.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")


def save_outputs(output_dir: Path, records: list[NewsRecord], scan_existing: bool = True) -> None:
    data_by_url: dict[str, dict] = {}
    if scan_existing:
        for file_path in sorted(output_dir.glob("**/*.json")):
            if file_path.name in {"news_records.json", "news_records_recleaned.json"}:
                continue
            try:
                item = json.loads(file_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(item, dict):
                key = document_dedup_key_from_values(
                    url=str(item.get("url") or ""),
                    title=str(item.get("title") or ""),
                    year=item.get("year") or "",
                    medium=str(item.get("medium") or ""),
                    pdf_url=str(item.get("pdf_url") or ""),
                ) or str(file_path)
                data_by_url[key] = item
    for record in records:
        item = asdict(record)
        data_by_url[document_dedup_key(record) or stable_id(str(item))] = item
    data = list(data_by_url.values())
    data.sort(key=lambda item: (item.get("year") or 0, item.get("medium") or "", item.get("title") or ""))
    safe_write_text_atomic(output_dir / "news_records.json", json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    safe_write_text_atomic(
        output_dir / "news_records.jsonl",
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in data),
        encoding="utf-8",
    )


def stable_json_hash(value) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_cli_manifest(output_dir: Path, config: dict, records: list[NewsRecord], status: str, error: str = "") -> None:
    rows = [asdict(record) for record in records]
    manifest = {
        "system": "SIAN",
        "manifest_version": 1,
        "execution": "local_cli_news_spider",
        "analysis_policy": "heuristic_local_no_external_llm",
        "started_or_finished_at": dt.datetime.now(dt.UTC).isoformat(),
        "status": status,
        "config": config,
        "config_hash": stable_json_hash(config),
        "records_total": len(rows),
        "records_usable": sum(1 for row in rows if row_is_usable_for_analysis(row)),
        "records_by_source_type": {
            source_type: sum(1 for row in rows if str(row.get("source_type") or "unknown") == source_type)
            for source_type in sorted({str(row.get("source_type") or "unknown") for row in rows})
        },
        "records_by_status": {
            row_status: sum(1 for row in rows if str(row.get("status") or "unknown") == row_status)
            for row_status in sorted({str(row.get("status") or "unknown") for row in rows})
        },
        "records_hash": stable_json_hash(rows) if rows else "",
        "error": error,
        "notes": [
            "CLI run uses public/indexed sources only.",
            "Partial/paywall/blocked sources must be interpreted as metadata signals, not full text.",
            "No external LLM is used for local extraction.",
        ],
    }
    safe_write_text_atomic(output_dir / "run_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def safe_slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return value[:80] or "unknown"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local academic news spider using GDELT + article text extraction.")
    parser.add_argument("--query", required=True, help="Search query, e.g. 'violencia escolar' or 'nearshoring mexico'.")
    parser.add_argument("--query-variants", default="", help="Comma-separated variants/synonyms, e.g. tatuaje,tatuajes.")
    parser.add_argument("--geographic-scope", default="global", help="Analytical geographic frame, e.g. global, mexico, latin_america.")
    parser.add_argument("--geographic-terms", default="", help="Comma-separated geography terms added with OR, e.g. Mexico,México.")
    parser.add_argument("--exclude-terms", default="", help="Comma-separated terms to reject after search, e.g. cigar,cigars,tobacco.")
    parser.add_argument("--exclude-domains", default="", help="Comma-separated domains to reject, e.g. halfwheel.com,cigaraficionado.com.")
    parser.add_argument(
        "--source-modes",
        default="gdelt_news",
        help="Comma-separated engines: gdelt_news,google_news_rss,openalex_oa,crossref,redalyc,forums. Forums use domain presets through GDELT.",
    )
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    parser.add_argument("--domains", default="", help="Comma-separated domains, e.g. jornada.com.mx,elpais.com")
    parser.add_argument("--output-dir", default="news_output")
    parser.add_argument("--max-records-per-month", type=int, default=30)
    parser.add_argument("--max-records-per-source-type-year", type=int, default=100)
    parser.add_argument("--target-min-per-source-type-year", type=int, default=0)
    parser.add_argument("--required-source-types", default="", help="Comma-separated required/audited source types, e.g. news,forum.")
    parser.add_argument("--accept-source-types", default="", help="Comma-separated accepted source types. Empty accepts all.")
    parser.add_argument("--seed-url-file", default="", help="JSON list of curated seed URLs to ingest as indexed records.")
    parser.add_argument(
        "--download-pdfs",
        action="store_true",
        help=(
            "Attempt PDF download only when local policy permits it; otherwise keep metadata/pdf_url. "
            "Crossref PDFs remain metadata-only unless license verification is added."
        ),
    )
    parser.add_argument(
        "--allow-metadata-only-articles",
        action="store_true",
        help="Allow scientific metadata/abstract records without an open PDF/full-text link. Default is strict open-access article mode.",
    )
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--search-delay", type=float, default=2.0)
    parser.add_argument("--min-text-chars", type=int, default=600)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    domains = [item.strip() for item in args.domains.split(",") if item.strip()]
    query_variants = [item.strip() for item in args.query_variants.split(",") if item.strip()]
    geographic_terms = [item.strip() for item in args.geographic_terms.split(",") if item.strip()]
    exclude_terms = [item.strip() for item in args.exclude_terms.split(",") if item.strip()]
    exclude_domains = [item.strip() for item in args.exclude_domains.split(",") if item.strip()]
    source_modes = [item.strip() for item in args.source_modes.split(",") if item.strip()]
    required_source_types = [item.strip() for item in args.required_source_types.split(",") if item.strip()]
    accept_source_types = [item.strip() for item in args.accept_source_types.split(",") if item.strip()]
    config = {
        "query": args.query,
        "start_year": args.start_year,
        "end_year": args.end_year,
        "domains": domains,
        "query_variants": query_variants,
        "geographic_scope": args.geographic_scope,
        "geographic_terms": geographic_terms,
        "exclude_terms": exclude_terms,
        "exclude_domains": exclude_domains,
        "source_modes": source_modes or ["gdelt_news"],
        "output_dir": args.output_dir,
        "max_records_per_month": args.max_records_per_month,
        "max_records_per_source_type_year": args.max_records_per_source_type_year,
        "target_min_per_source_type_year": args.target_min_per_source_type_year,
        "required_source_types": required_source_types,
        "accept_source_types": accept_source_types,
        "seed_url_file": args.seed_url_file or "",
        "download_pdfs": bool(args.download_pdfs),
        "strict_open_access_articles": not bool(args.allow_metadata_only_articles),
        "delay_seconds": args.delay,
        "search_delay_seconds": args.search_delay,
        "min_text_chars": args.min_text_chars,
    }
    records: list[NewsRecord] = []
    output_path = Path(args.output_dir)
    try:
        records = crawl_news(
            query=args.query,
            start_year=args.start_year,
            end_year=args.end_year,
            domains=domains,
            query_variants=query_variants,
            geographic_scope=args.geographic_scope,
            geographic_terms=geographic_terms,
            exclude_terms=exclude_terms,
            exclude_domains=exclude_domains,
            source_modes=source_modes,
            output_dir=args.output_dir,
            max_records_per_month=args.max_records_per_month,
            max_records_per_source_type_year=args.max_records_per_source_type_year,
            target_min_per_source_type_year=args.target_min_per_source_type_year,
            required_source_types=required_source_types,
            accept_source_types=accept_source_types,
            seed_url_file=args.seed_url_file or None,
            download_pdfs=args.download_pdfs,
            strict_open_access_articles=not bool(args.allow_metadata_only_articles),
            delay_seconds=args.delay,
            search_delay_seconds=args.search_delay,
            min_text_chars=args.min_text_chars,
            progress=lambda message: print(message, flush=True),
        )
        write_cli_manifest(output_path, config, records, "finished")
    except Exception as exc:  # noqa: BLE001
        write_cli_manifest(output_path, config, records, "error", str(exc))
        raise
    usable = sum(1 for record in records if record_is_usable_for_analysis(record))
    partial = sum(1 for record in records if record.status == "ok_partial")
    print(f"Saved {len(records)} records ({usable} usable; {partial} partial RSS/metadata) in {args.output_dir}")


if __name__ == "__main__":
    main()
