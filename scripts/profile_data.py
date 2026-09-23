"""Step 2: profile the cached snapshot and write reports/data_profile.md.

Descriptive only: counts, types, missing rates, distinct values, keys and
link integrity. No business metrics are computed here.

Field types are inferred from values, because the schema endpoint is not
available to this token (see data/raw/_manifest.json). Personal data (names,
emails, phones) is masked in examples so this report is safe to commit.

Usage:  python3 scripts/profile_data.py
"""
import re
import statistics
from collections import Counter

from airtable_client import ROOT
from raw_data import load_all, load_manifest
from relevance import RELEVANCE

OUT = ROOT / "reports" / "data_profile.md"

REC_ID = re.compile(r"^rec[A-Za-z0-9]{14}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
BUSINESS_ID = re.compile(r"^[A-Z]+(-\d+)+$")
PII_FIELDS = {"Full Name", "Email", "Work Email", "Phone"}
CATEGORICAL_MAX_DISTINCT = 25


# ---------------------------------------------------------------- inference

def infer_type(values):
    """Best-guess Airtable field type from the non-empty values seen."""
    if all(isinstance(v, bool) for v in values):
        return "checkbox"
    if all(isinstance(v, list) for v in values):
        items = [x for v in values for x in v]
        if items and all(isinstance(x, str) and REC_ID.match(x) for x in items):
            return "link"
        return "multi-value list"
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
        return "number (integer)" if all(isinstance(v, int) for v in values) else "number (decimal)"
    if all(isinstance(v, str) for v in values):
        n_date = sum(bool(DATE.match(v)) for v in values)
        n_dt = sum(bool(DATETIME.match(v)) for v in values)
        if n_date == len(values):
            return "date"
        if n_dt == len(values):
            return "datetime"
        if n_date + n_dt >= 0.5 * len(values):
            return "date (mixed formats)"
        distinct = set(values)
        if all(BUSINESS_ID.match(v) for v in values):
            return "identifier"
        if all("@" in v for v in values):
            return "email"
        if all(re.fullmatch(r"\+?[\d\s()-]{7,}", v) for v in values):
            return "phone"
        short = statistics.mean(len(v) for v in values) <= 30
        if len(distinct) <= CATEGORICAL_MAX_DISTINCT and len(distinct) < len(values):
            return "category" if short else "templated text"
        return "text"
    return "mixed: " + ", ".join(sorted({type(v).__name__ for v in values}))


def is_blank(v):
    return v is None or (isinstance(v, str) and not v.strip()) or (isinstance(v, list) and not v)


def hashable(v):
    return tuple(v) if isinstance(v, list) else v


def mask(field, v):
    if not isinstance(v, str):
        return "(masked)"
    if field == "Phone":
        digits = re.sub(r"\D", "", v)
        return f"{v[:4]}…{digits[-2:]} ({len(digits)} digits)"
    if "@" in v:
        local, _, domain = v.partition("@")
        return f"{local[:1]}***@{domain}"
    return " ".join(p[:1] + "***" for p in v.split())


def fmt(v, limit=60):
    s = v if isinstance(v, str) else repr(v)
    return s if len(s) <= limit else s[: limit - 1] + "…"


# ---------------------------------------------------------------- profiling

def profile_field(field, records):
    present = [r["fields"][field] for r in records if field in r["fields"]]
    nonblank = [v for v in present if not is_blank(v)]
    ftype = infer_type(nonblank) if nonblank else "unknown (never filled)"
    distinct = Counter(hashable(v) for v in nonblank)
    info = {
        "field": field,
        "type": ftype,
        "filled": len(nonblank),
        "missing_pct": 100 * (len(records) - len(nonblank)) / len(records),
        "blank_strings": len(present) - len(nonblank),
        "distinct": len(distinct),
        "values": distinct,
        "nonblank": nonblank,
    }
    if field in PII_FIELDS:
        info["examples"] = "PII: " + "; ".join(mask(field, v) for v in nonblank[:2])
    elif ftype.startswith("number"):
        info["examples"] = (f"min {min(nonblank):,} · median {statistics.median(nonblank):,} · "
                            f"max {max(nonblank):,}")
    elif ftype.startswith("date"):
        parseable = sorted(v[:10] for v in nonblank if DATE.match(v[:10]))
        other = len(nonblank) - len(parseable)
        info["examples"] = f"{parseable[0]} → {parseable[-1]}" if parseable else ""
        if other:
            info["examples"] += f" · {other} non-ISO: " + ", ".join(
                repr(v) for v in [v for v in nonblank if not DATE.match(v[:10])][:3])
    elif ftype == "link":
        per = [len(v) for v in nonblank]
        info["examples"] = f"{min(per)}–{max(per)} links/record · e.g. {nonblank[0][0]}"
    elif ftype == "category":
        info["examples"] = f"{len(distinct)} values (see below)"
    elif ftype == "templated text":
        info["examples"] = f"{len(distinct)} repeated sentences (see below)"
    else:
        seen = list(dict.fromkeys(hashable(v) for v in nonblank))[:2]
        info["examples"] = " | ".join(fmt(v, 45) for v in seen)
    return info


def link_report(tables, id_to_table):
    """For every link field: target table, dangling IDs, and reciprocal agreement."""
    links = {}  # (table, field) -> {src_id: [target ids]}
    for table, recs in tables.items():
        fields = {f for r in recs for f in r["fields"]}
        for f in fields:
            vals = [r["fields"][f] for r in recs if f in r["fields"]]
            if vals and infer_type(vals) == "link":
                links[(table, f)] = {r["id"]: r["fields"][f] for r in recs if f in r["fields"]}

    rows = []
    for (table, field), mapping in sorted(links.items()):
        targets = Counter(id_to_table.get(t, "∅ (unresolved)") for ids in mapping.values() for t in ids)
        target = targets.most_common(1)[0][0]
        dangling = sum(n for t, n in targets.items() if t != target)
        pairs = {(s, t) for s, ids in mapping.items() for t in ids}
        # Reciprocal: field in the target table whose links point back at `table`
        best, best_agree = None, -1
        for (t2, f2), m2 in links.items():
            if t2 != target or (t2 == table and f2 == field):
                continue
            back = {(s, t) for t, ids in m2.items() for s in ids}
            agree = len(pairs & back)
            if agree > best_agree and any(id_to_table.get(s) == table for ids in m2.values() for s in ids):
                best, best_agree, best_back = f2, agree, back
        per = [len(v) for v in mapping.values()]
        row = {
            "from": f"{table}.{field}", "to": target, "records_with_link": len(mapping),
            "max_per_record": max(per), "multi": sum(p > 1 for p in per),
            "dangling": dangling, "reciprocal": best,
        }
        if best:
            row["only_this_side"] = len(pairs - best_back)
            row["only_other_side"] = len(best_back - pairs)
        rows.append(row)
    return rows


NATURAL_KEYS = {"Full Name", "Email", "Work Email", "Phone", "Code", "Name"}


def key_candidates(records, profiles):
    """(business-ID fields, natural identifiers), each as (field, complete, dupes, distinct)."""
    business, natural = [], []
    for p in profiles:
        if not p["filled"]:
            continue
        row = (p["field"], p["filled"] == len(records),
               sum(n - 1 for n in p["values"].values() if n > 1), p["distinct"])
        if p["type"] == "identifier":
            business.append(row)
        elif p["field"] in NATURAL_KEYS:
            natural.append(row)
    return business, natural


# ---------------------------------------------------------------- rendering

def render(tables, manifest):
    id_to_table = {r["id"]: t for t, recs in tables.items() for r in recs}
    L = []
    w = L.append
    w("# Data profile — TalentFlow - Acme Corp")
    w("")
    w(f"Snapshot: `data/raw/` fetched {manifest['started_at']} → {manifest['finished_at']} "
      f"({manifest['http_requests']} API requests, {len(manifest['retries'])} retries). "
      "Generated by `scripts/profile_data.py` from the cached snapshot only.")
    w("")
    w("Descriptive only. No VP claims are calculated and nothing here is interpreted.")
    w("")
    w("**How to read this**")
    w("")
    w("- **Types are inferred from values.** The schema endpoint returned HTTP "
      f"{manifest['schema_endpoint']['status']}, so Airtable's declared field types, "
      "select-option lists and primary fields are not available.")
    w("- **Missing % = records where the field is absent or blank.** Airtable leaves empty "
      "fields out of the response, so absent means empty (or unchecked). A field that is "
      "empty in every record would not appear at all.")
    w("- **Personal data is masked** (names, emails, phones). Complete unmasked records are "
      "in `data/sample_raw_records.md`, which is local-only.")
    w("- Category values are shown exactly as stored, in backticks, so case and "
      "whitespace differences are visible.")
    w("")

    # Overview
    w("## 1. Tables")
    w("")
    w("| Table | Records | Pages | Fields seen | Record `createdTime` range |")
    w("|---|---:|---:|---:|---|")
    for t, recs in tables.items():
        nf = len({f for r in recs for f in r["fields"]})
        ct = sorted(r["createdTime"] for r in recs)
        rng = f"{ct[0][:10]} → {ct[-1][:10]}" if ct else "—"
        w(f"| {t} | {len(recs)} | {manifest['tables'][t]['pages']} | {nf} | {rng} |")
    w("")
    w("`createdTime` is when the Airtable row was created, not a business date.")
    w("")

    # Relationships
    rels = link_report(tables, id_to_table)
    w("## 2. Relationships (link fields)")
    w("")
    w("The target table is resolved by matching linked record IDs against every table in the snapshot. "
      "*Dangling* = linked IDs not found in the target table. *Reciprocal mismatch* = link pairs "
      "that appear on one side only.")
    w("")
    w("| From field | → Table | Records linked | Max links/rec | Recs with >1 | Dangling IDs | Reciprocal field | Mismatch (this side / other side) |")
    w("|---|---|---:|---:|---:|---:|---|---|")
    for r in rels:
        mm = f"{r['only_this_side']} / {r['only_other_side']}" if r["reciprocal"] else "—"
        w(f"| {r['from']} | {r['to']} | {r['records_with_link']} | {r['max_per_record']} | "
          f"{r['multi']} | {r['dangling']} | {r['reciprocal'] or '—'} | {mm} |")
    w("")

    # Relevance to deliverables
    w("## 3. What D1, D3 and D4 will need")
    w("")
    w("This is a map of what to look at, with open definitional questions. Nothing here is calculated.")
    w("")
    for section in RELEVANCE:
        w(f"### {section['title']}")
        w("")
        for label, items in section["parts"]:
            w(f"**{label}**")
            w("")
            for item in items:
                w(f"- {item}")
            w("")

    # Per-table detail
    w("## 4. Table detail")
    w("")
    for t, recs in tables.items():
        w(f"### {t} — {len(recs)} records")
        w("")
        if not recs:
            w("**Empty.** The API returned HTTP 200 with zero records: the table exists but has "
              "no rows visible to the credential in use.")
            w("")
            continue
        fields = list(dict.fromkeys(f for r in recs for f in r["fields"]))
        fields.sort(key=lambda f: -sum(f in r["fields"] for r in recs))
        profiles = [profile_field(f, recs) for f in fields]

        w("| Field | Inferred type | Missing | Distinct | Values / range / examples |")
        w("|---|---|---:|---:|---|")
        for p in profiles:
            miss = f"{p['missing_pct']:.1f}%"
            if p["blank_strings"]:
                miss += f" ({p['blank_strings']} blank strings)"
            ex = p["examples"].replace("|", "\\|")
            w(f"| {p['field']} | {p['type']} | {miss} | {p['distinct']} | {ex} |")
        w("")

        business, natural = key_candidates(recs, profiles)
        w("**Keys**")
        w("")
        w("- `id` (Airtable record ID): primary key, unique by construction. Link fields reference it.")
        for f, complete, dupes, distinct in business:
            w(f"- `{f}`: business ID. {'On every record' if complete else 'Not on every record'}, "
              f"{distinct} distinct, **{dupes} duplicate value(s)**.")
        for f, complete, dupes, distinct in natural:
            w(f"- `{f}`: natural identifier, useful for duplicate checks. {distinct} distinct, "
              f"**{dupes} duplicate value(s)**.")
        w("")

        cats = [p for p in profiles if p["type"] == "category"]
        if cats:
            w("**Category values** (count, most frequent first):")
            w("")
            for p in cats:
                vals = ", ".join(f"`{v}` {n}" for v, n in p["values"].most_common())
                w(f"- **{p['field']}**: {vals}")
            w("")
        texts = [p for p in profiles if p["type"] == "templated text"]
        for p in texts:
            w(f"<details><summary><b>{p['field']}</b>: {p['distinct']} distinct templated values</summary>")
            w("")
            for v, n in p["values"].most_common():
                w(f"- {n} × `{v}`")
            w("")
            w("</details>")
            w("")
    return "\n".join(L) + "\n"


def validate_relevance(tables):
    """Fail loudly if relevance.py names a table.field that is not in the data."""
    known = {(t, f) for t, recs in tables.items() for r in recs for f in r["fields"]}
    known |= {(t, "id") for t in tables} | {(t, "createdTime") for t in tables}
    missing = []
    for section in RELEVANCE:
        for _, items in section["parts"]:
            for item in items:
                for t, f in re.findall(r"`([A-Z][\w ]*?)\.([^`]+)`", item):
                    if (t, f) not in known:
                        missing.append(f"{t}.{f}")
    if missing:
        raise SystemExit(f"relevance.py references unknown fields: {missing}")


def main():
    tables = load_all()
    validate_relevance(tables)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(render(tables, load_manifest()))
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
