"""Load the cached raw snapshot written by ingest.py (no API calls)."""
import json

from airtable_client import ROOT

RAW_DIR = ROOT / "data" / "raw"


def load_manifest():
    path = RAW_DIR / "_manifest.json"
    if not path.exists():
        raise SystemExit("No snapshot found. Run `python3 scripts/ingest.py` first.")
    return json.loads(path.read_text())


def load_raw(table):
    """The stored file for one table: {"table", "fetched_at", "request", "pages"}."""
    manifest = load_manifest()
    return json.loads((RAW_DIR / manifest["tables"][table]["file"]).read_text())


def load_records(table):
    """All records for a table, in API order, exactly as returned."""
    return [rec for page in load_raw(table)["pages"] for rec in page["records"]]


def load_all():
    """{table name: [records]} for every table in the snapshot."""
    return {table: load_records(table) for table in load_manifest()["tables"]}
