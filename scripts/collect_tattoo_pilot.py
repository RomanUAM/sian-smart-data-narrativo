#!/usr/bin/env python3
"""Real SIAN retrieval benchmark: annual news feeds, public forum feed and Redalyc.

These are indexed candidates, not a representative or semantically validated corpus.
Annual windows cover 2016 through the actual consultation instant in 2026.
"""
import concurrent.futures
import datetime as dt
import hashlib
import json
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from news_spider import (search_google_news_rss, search_reddit_rss, request_json,
                         redalyc_record, clean_partial_metadata_text, strip_markup)
from evidence_model import normalize_record, cell
from source_adapters import SourceAdapter

ROOT = None
CUTOFF = dt.datetime.now(dt.UTC)
QUERY = '(tatuaje OR tatuajes OR tattoo) (México OR Mexico)'


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def feed_record(item, source_type, query, search_year=None):
    # Excerpt limit keeps the export a metadata/excerpt database rather than a mirror.
    description = strip_markup(item.get("rss_description") or "")
    title = item.get("title") or ""
    excerpt = " ".join(description.split()[:20]) or title
    text = title if source_type == "news" else excerpt if title in excerpt else title + ". " + excerpt
    clean = clean_partial_metadata_text(text)
    row = {"query": query, "search_role": "anchor", "geographic_scope": "México",
           "geographic_terms": ["México", "Mexico"], "year": search_year,
           "medium": item.get("sourceCommonName"), "url": item.get("url"),
           "publisher_url": item.get("publisher_url"), "title": title,
           "published_date": item.get("publishedDate") or "", "source_type": source_type,
           "source_api": item.get("source_api"), "status": "ok_partial",
           "fetched_at": CUTOFF.isoformat(), "text_clean": clean["text_clean"],
           "text_normalized": clean["text_normalized"], "text_length": len(clean["text_clean"]),
           "cleaning_notes": ["public_feed_excerpt_not_article_fulltext"],
           "selection_state": "candidate_pending_content_and_geography_review",
           "publication_date_evidence": item.get("seendate"), "retrieval_mode": "sian_native_feed",
           "content_sha256": hashlib.sha256(description.encode()).hexdigest()}
    if item.get("authors"):
        row["authors"] = item["authors"]
    if item.get("updated_date"):
        row["updated_date"] = item["updated_date"]
    return normalize_record(row)


def annual_news(year):
    start = dt.datetime(year, 1, 1, tzinfo=dt.UTC)
    end = min(dt.datetime(year + 1, 1, 1, tzinfo=dt.UTC) - dt.timedelta(seconds=1), CUTOFF)
    audit = {"engine": "google_news_rss", "query": QUERY, "start": start.isoformat(), "end": end.isoformat(), "year": year}
    try:
        items, diagnostics = search_google_news_rss(QUERY, start, end, 100)
        # The reader may allow one extra day: enforce the exact cutoff again.
        rows = [feed_record(item, "news", QUERY, year) for item in items
                if item.get("publishedDate") and start <= dt.datetime.fromisoformat(item["publishedDate"]) <= end]
        audit.update(status="completed", diagnostics=diagnostics, records=len(rows))
        write(ROOT / "by_source/news/by_year" / str(year) / "news_records.json", rows)
    except Exception as exc:
        audit.update(status="failed", error=f"{type(exc).__name__}: {exc}", records=0)
    write(ROOT / "retrieval_logs" / f"news_{year}.json", audit)
    print(json.dumps(audit, ensure_ascii=False), flush=True)
    return audit


def forum():
    query = "tatuaje Mexico"
    audit = {"engine": "reddit_rss", "query": query, "historical_limit": "recent public feed, not an archive"}
    try:
        items = search_reddit_rss(query, dt.datetime(2016, 1, 1, tzinfo=dt.UTC), CUTOFF, 100)
        rows = [feed_record(item, "forum", query) for item in items]
        write(ROOT / "by_source/forums/news_records.json", rows)
        audit.update(status="completed", records=len(rows))
    except Exception as exc:
        audit.update(status="failed", error=f"{type(exc).__name__}: {exc}", records=0)
    write(ROOT / "retrieval_logs/forums.json", audit)
    print(json.dumps(audit, ensure_ascii=False), flush=True)
    return audit


def academic():
    # Read one bounded paginated result set, then stratify locally; avoid re-fetching the same pages for 11 years.
    audit = {"engine": "redalyc", "query": "tatuaje", "pages": [], "status": "completed", "records": 0}
    rows = []
    for page in range(1, 9):
        url = f"https://www.redalyc.org/service/r2020/getArticles/tatuaje/{page}/50/1/default"
        try:
            def read_page(url):
                data = request_json(url, timeout=20)
                return data.get("resultados") or [], {"totalResultados": data.get("totalResultados")}
            result = SourceAdapter(ROOT / ".query_cache").query("redalyc", {"url": url}, reader=read_page, raise_errors=True)
            data = result["diagnostics"]
            items = result["rows"]
            audit["pages"].append({"page": page, "items": len(items), "reported_total": data.get("totalResultados")})
            for item in items:
                try:
                    year = int(str(item.get("anioArticulo") or item.get("anoEdcNum") or "0")[:4])
                except ValueError:
                    continue
                if not 2016 <= year <= 2026:
                    continue
                record = redalyc_record(item, "tatuaje", ["tatuajes", "tattoo"], "México", ["México", "Mexico"], year, 40)
                row = normalize_record(record.__dict__)
                # Do not redistribute full abstracts/article content in this pilot.
                excerpt = " ".join((row.get("text_clean") or "").split()[:20])
                row["text_clean"] = excerpt
                row["text_normalized"] = excerpt.lower()
                row["text_length"] = len(excerpt)
                row["record_information"]["text"] = cell(excerpt, "explicit", "redalyc.metadata_excerpt", "index_extraction", coverage="partial")
                row["retrieval_mode"] = "sian_native_redalyc"
                row["query"] = "tatuaje"
                row["selection_state"] = "candidate_pending_mexico_content_review"
                row["index_affiliation"] = item.get("nomInstitucionRev")
                rows.append(row)
            total = int(data.get("totalResultados") or 0)
            if not items or page * 50 >= total:
                break
        except Exception as exc:
            audit.update(status="partial_or_failed", error=f"{type(exc).__name__}: {exc}")
            break
    audit["records"] = len(rows)
    write(ROOT / "by_source/articles/news_records.json", rows)
    write(ROOT / "retrieval_logs/articles.json", audit)
    print(json.dumps(audit, ensure_ascii=False), flush=True)
    return audit


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir")
    parser.add_argument("--news-only", action="store_true")
    args = parser.parse_args()
    ROOT = Path(args.output_dir).resolve()
    ROOT.mkdir(parents=True, exist_ok=True)
    protocol = {"topic": "tatuaje", "scope": "México", "start": "2016-01-01", "cutoff": CUTOFF.isoformat(),
                "selection": "indexed candidates plus separately labelled manually verified primary sources",
                "annual_news_cap": 100, "redalyc_page_cap": 8, "forum_feed_cap": 100,
                "not_guaranteed": ["complete corpus", "author", "date", "full text", "Mexico relevance"],
                "excluded": ["endoscopic tattooing without body-tattoo relevance", "tobacco brands", "purely foreign cases"]}
    write(ROOT / "protocol.json", protocol)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(annual_news, year) for year in range(2016, 2027)]
        if not args.news_only:
            futures += [pool.submit(forum), pool.submit(academic)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    write(ROOT / "retrieval_summary.json", results)
