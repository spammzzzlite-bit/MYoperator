"""Raw Airtable connectivity check.

Pulls at most 3 records from one table and reports only metadata (HTTP status,
record count, whether more pages exist). It deliberately prints no record
contents and never prints the token. Read-only: issues GET requests only.

Usage:  python3 scripts/check_connection.py
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TABLE = "Applications"


def load_env(path=ROOT / ".env"):
    if not path.exists():
        sys.exit("Missing .env — copy .env.example to .env and fill in AIRTABLE_TOKEN.")
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def get(url, token):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace").replace(token, "[REDACTED]")
        return e.code, body


def main():
    load_env()
    token = os.environ.get("AIRTABLE_TOKEN")
    base = os.environ.get("AIRTABLE_BASE_ID")
    if not token or not base:
        sys.exit("AIRTABLE_TOKEN and AIRTABLE_BASE_ID must be set.")

    status, body = get(f"https://api.airtable.com/v0/{base}/{TABLE}?maxRecords=3", token)
    print(f"GET /v0/<base>/{TABLE}?maxRecords=3 -> HTTP {status}")
    if status != 200:
        print(f"  error: {body}")
        sys.exit(1)
    print(f"  records returned: {len(body.get('records', []))}")
    print(f"  pagination offset present: {'offset' in body}")

    status, body = get("https://api.airtable.com/v0/meta/whoami", token)
    print(f"GET /v0/meta/whoami -> HTTP {status}")
    if status == 200:
        print(f"  token scopes: {body.get('scopes', '(not reported)')}")


if __name__ == "__main__":
    main()
