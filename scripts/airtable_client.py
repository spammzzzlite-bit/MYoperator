"""Minimal read-only Airtable REST client shared by the pipeline scripts.

- Loads AIRTABLE_TOKEN / AIRTABLE_BASE_ID from the environment or `.env`.
- Issues GET requests only.
- Throttles to at most 4 requests/second (API limit is 5/sec per base; a 429
  locks the base for 30 seconds, so we keep a safety margin).
- Retries on 429 (waits out the 30 s lockout) and transient 5xx errors.
- Never prints the token; any error text echoing it is redacted.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.airtable.com/v0"

MIN_INTERVAL_S = 0.25  # 4 req/s, under the 5 req/s limit
LOCKOUT_S = 31  # 429 lockout is 30 s
MAX_RETRIES = 5


def load_env(path=ROOT / ".env"):
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())
    token = os.environ.get("AIRTABLE_TOKEN")
    base = os.environ.get("AIRTABLE_BASE_ID")
    if not token or not base:
        sys.exit("AIRTABLE_TOKEN and AIRTABLE_BASE_ID must be set (see .env.example).")
    return token, base


class AirtableClient:
    def __init__(self):
        self.token, self.base_id = load_env()
        self._last_request = 0.0
        self.request_count = 0
        self.retry_log = []  # (url_without_token, status, action)

    def _throttle(self):
        wait = self._last_request + MIN_INTERVAL_S - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def _redact(self, text):
        return text.replace(self.token, "[REDACTED]")

    def get(self, path, params=None):
        """GET {API}/{path}?params. Returns (status, parsed JSON or error text)."""
        url = f"{API}/{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params, doseq=True)
        for attempt in range(1, MAX_RETRIES + 1):
            self._throttle()
            self.request_count += 1
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.token}"})
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    return resp.status, json.loads(resp.read())
            except urllib.error.HTTPError as e:
                body = self._redact(e.read().decode(errors="replace"))
                if e.code == 429 or e.code >= 500:
                    delay = LOCKOUT_S if e.code == 429 else 2 ** attempt
                    self.retry_log.append((url, e.code, f"retry {attempt} after {delay}s"))
                    print(f"  HTTP {e.code} on {url} - waiting {delay}s (attempt {attempt})", file=sys.stderr)
                    time.sleep(delay)
                    continue
                return e.code, body
            except urllib.error.URLError as e:
                delay = 2 ** attempt
                self.retry_log.append((url, "network", f"retry {attempt} after {delay}s"))
                print(f"  network error on {url}: {self._redact(str(e))} - waiting {delay}s", file=sys.stderr)
                time.sleep(delay)
        raise RuntimeError(f"Giving up on {url} after {MAX_RETRIES} attempts")

    def list_pages(self, table, page_size=100):
        """Yield every raw page response for a table, following `offset`."""
        params = {"pageSize": page_size}
        path = f"{self.base_id}/{urllib.parse.quote(table, safe='')}"
        while True:
            status, body = self.get(path, params)
            if status != 200:
                raise RuntimeError(f"GET {table} failed: HTTP {status}: {body}")
            yield body
            offset = body.get("offset")
            if not offset:
                return
            params = {"pageSize": page_size, "offset": offset}
