"""RSS candidate collector. Candidates are not independently verified news facts."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import feedparser

ROOT = Path(__file__).resolve().parents[1]
SOURCES = json.loads((ROOT / "collector" / "sources.json").read_text(encoding="utf-8"))["sources"]
OUT = Path(os.environ.get("OUTPUT_FILE", ROOT / "collector" / "latest_run.json"))


def fetch(source: dict) -> tuple[list[dict], str | None]:
    request = urllib.request.Request(source["url"], headers={"User-Agent": "GlobalNewsMonitor/1.0 (+RSS reader)"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = response.read(3_000_000)
        parsed = feedparser.parse(payload)
        if parsed.bozo and not parsed.entries:
            return [], str(parsed.bozo_exception)
        items = []
        for entry in parsed.entries[:30]:
            link = entry.get("link", "").strip()
            title = entry.get("title", "").strip()
            if not link or not title:
                continue
            raw_date = entry.get("published") or entry.get("updated") or ""
            published_at = None
            try:
                published_at = parsedate_to_datetime(raw_date).astimezone(timezone.utc).isoformat()
            except Exception:
                pass
            fingerprint = hashlib.sha256((link or title).encode("utf-8")).hexdigest()
            items.append({
                "source_name": source["name"], "category": source["category"],
                "title": title, "url": link, "summary": entry.get("summary", "")[:4000],
                "published_at": published_at, "fingerprint": fingerprint,
                "verification_status": "待核实", "collected_at": datetime.now(timezone.utc).isoformat()
            })
        return items, None
    except Exception as exc:
        return [], f"{type(exc).__name__}: {exc}"


def main() -> int:
    all_items, errors = [], []
    for source in SOURCES:
        if not source.get("enabled"):
            continue
        items, error = fetch(source)
        all_items.extend(items)
        if error:
            errors.append({"source": source["name"], "error": error})
        time.sleep(0.25)

    # Deterministic de-duplication within this run. Cross-run de-duplication is done by D1.
    unique = {item["fingerprint"]: item for item in all_items}
    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "candidate_count": len(all_items),
        "unique_candidate_count": len(unique),
        "source_error_count": len(errors),
        "source_errors": errors,
        "items": sorted(unique.values(), key=lambda x: x.get("published_at") or "", reverse=True),
        "note": "RSS候选信息，尚未完成多源交叉核验；不得直接视为已确认重大新闻。"
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("run_at", "candidate_count", "unique_candidate_count", "source_error_count")}, ensure_ascii=False))
    return 0 if not errors else 0  # Partial source failures are recorded, not hidden.
    
if __name__ == "__main__":
    sys.exit(main())
