"""Step 1: download every table in the base once and cache the raw responses.

Writes, under data/raw/:
  <table_slug>.json   every page response exactly as Airtable returned it
                      ({"table", "fetched_at", "request", "pages": [...]})
  _manifest.json      what was fetched, when, record/page counts, API notes

Later scripts read only from data/raw/, never from the API.

Usage:  python3 scripts/ingest.py            # refuses to overwrite an existing snapshot
        python3 scripts/ingest.py --refresh  # re-download and overwrite
"""
import json
import sys
from datetime import datetime, timezone

from airtable_client import ROOT, AirtableClient

RAW_DIR = ROOT / "data" / "raw"

# All tables named in the candidate pack.
TABLES = [
    "Departments",
    "People",
    "Job Openings",
    "Candidates",
    "Applications",
    "Interviews",
    "Offers",
    "Findings",
]


def slug(table):
    return table.lower().replace(" ", "_")


def main():
    refresh = "--refresh" in sys.argv
    manifest_path = RAW_DIR / "_manifest.json"
    if manifest_path.exists() and not refresh:
        sys.exit(f"Snapshot already exists ({manifest_path.relative_to(ROOT)}). "
                 "Use --refresh to re-download.")
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    client = AirtableClient()
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # Schema metadata endpoint (needs schema.bases:read). Recorded, not required.
    status, body = client.get(f"meta/bases/{client.base_id}/tables")
    schema_available = status == 200
    if schema_available:
        (RAW_DIR / "_schema.json").write_text(json.dumps(body, indent=2, ensure_ascii=False))
    print(f"schema endpoint: HTTP {status}" + ("" if schema_available else " (types will be inferred from values)"))

    tables = {}
    for table in TABLES:
        fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        pages = list(client.list_pages(table))
        n = sum(len(p.get("records", [])) for p in pages)
        out = RAW_DIR / f"{slug(table)}.json"
        out.write_text(json.dumps({
            "table": table,
            "fetched_at": fetched_at,
            "request": {"method": "GET", "path": f"/v0/<base>/{table}",
                        "params": {"pageSize": 100, "cellFormat": "json (default)"}},
            "pages": pages,
        }, indent=2, ensure_ascii=False))
        tables[table] = {"file": out.name, "records": n, "pages": len(pages)}
        print(f"{table:14s} {n:6d} records in {len(pages):3d} pages -> {out.relative_to(ROOT)}")

    manifest = {
        "base_id": client.base_id,
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "http_requests": client.request_count,
        "retries": [{"url": u, "status": s, "action": a} for u, s, a in client.retry_log],
        "schema_endpoint": {"status": status, "available": schema_available},
        "tables": tables,
        "notes": [
            "Airtable omits empty fields from each record, so a field absent from a "
            "record means empty/false/null; a field empty in every record is invisible.",
            "Records are stored exactly as returned; no transformation is applied here.",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"{client.request_count} HTTP requests, {len(client.retry_log)} retries")


if __name__ == "__main__":
    main()
