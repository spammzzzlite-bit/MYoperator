# TalentFlow Q3 roadmap exercise: analysis pack

The brief, constraints and deliverables are summarised in [`PROJECT_NOTES.md`](PROJECT_NOTES.md).

## Reproduce

Requires Python 3.9+ and nothing outside the standard library.

```bash
cp .env.example .env                 # then set AIRTABLE_TOKEN
python3 scripts/ingest.py            # 1. download every table once -> data/raw/
python3 scripts/profile_data.py      # 2. profile the snapshot -> reports/data_profile.md
python3 scripts/sample_records.py    # 3. 15 full raw records -> data/sample_raw_records.md
```

`ingest.py` refuses to overwrite an existing snapshot. Pass `--refresh` to re-download.
Steps 2 and 3 read only the local snapshot and never call the API.

## Layout

| Path | What it is | In git? |
|---|---|---|
| `data/raw/<table>.json` | Every page response per table, exactly as Airtable returned it | No (personal data) |
| `data/raw/_manifest.json` | Fetch time, record/page counts, request count, retries, schema-endpoint status | No |
| `data/sample_raw_records.md` | 5 complete raw records each from Offers, Applications and Candidates, linked offer → application → candidate | No (personal data) |
| `reports/data_profile.md` | Per-table profile plus the D1/D3/D4 field map (personal data masked) | Yes |
| `scripts/airtable_client.py` | Read-only client: throttling (≤ 4 req/s), 429/5xx retry, token redaction | Yes |
| `scripts/ingest.py` | Step 1 | Yes |
| `scripts/raw_data.py` | Loads the local snapshot for all later analysis | Yes |
| `scripts/profile_data.py` | Step 2 | Yes |
| `scripts/relevance.py` | D1/D3/D4 field map. Field names are validated against the data | Yes |
| `scripts/sample_records.py` | Step 3 | Yes |
| `scripts/check_connection.py` | One-off connectivity check | Yes |

## API handling

- GET only. The base is read-only.
- Rate limit: 5 req/s per base; a 429 locks the base for 30 s. The client spaces
  requests 0.25 s apart and waits 31 s on a 429.
- Pagination: `pageSize=100`, following `offset` until none is returned.
- The token is read from `.env` and never printed or written to any output.
