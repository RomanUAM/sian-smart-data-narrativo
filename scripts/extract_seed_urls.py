#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: extract_seed_urls.py INPUT_PASTED_TEXT OUTPUT_JSON")
    source = Path(sys.argv[1])
    target = Path(sys.argv[2])
    text = source.read_text(encoding="utf-8")
    pattern = re.compile(
        r"\{\s*'medio':\s*'([^']+)'\s*,\s*'url':\s*'([^']+)'\s*,\s*'fecha':\s*'([^']+)'\s*\}"
    )
    rows = []
    seen = set()
    for medium, url, date in pattern.findall(text):
        if url in seen:
            continue
        seen.add(url)
        rows.append(
            {
                "medium": medium.strip(),
                "url": url.strip(),
                "date": date.strip(),
                "source_type": "news",
                "source_api": "seed_url_list",
                "source_type_evidence": "curated_mexico_news_seed",
            }
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"extracted_seed_urls={len(rows)}")


if __name__ == "__main__":
    main()
