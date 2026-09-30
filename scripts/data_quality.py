"""Step 4: run every check in the D4 checklist (scripts/relevance.py) against
the cached snapshot and write reports/data_quality.md.

Each check states its rule, the population it applies to, how many records
break the rule, and example IDs. Descriptive only: no interpretation, no
severity judgement, no claim calculations.

Examples are shown as `BUSINESS-ID (recordId)`, because business IDs are not
guaranteed unique (see check 2.1). They are the first matches after sorting
by business ID, so they are stable across runs. No personal data is printed.

Usage:  python3 scripts/data_quality.py
"""
import re
from collections import Counter, defaultdict
from itertools import combinations

from airtable_client import ROOT
from raw_data import load_all, load_manifest

OUT = ROOT / "reports" / "data_quality.md"
N_EXAMPLES = 3
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

BUSINESS_KEY = {
    "Departments": "Code", "People": "Work Email", "Job Openings": "Req ID",
    "Candidates": "Candidate ID", "Applications": "Application ID",
    "Interviews": "Interview ID", "Offers": "Offer ID",
}
TERMINAL_STAGES = {"Rejected", "Hired", "Withdrawn"}
OPEN_STAGES = {"Applied", "Screening", "Interview", "Offer"}
PIPELINE = ["Applied On", "Screened On", "First Interview On", "Final Interview On",
            "Offered On", "Closed On"]
SINGLE_LINKS = [
    ("Applications", "Candidate"), ("Applications", "Opening"), ("Applications", "Recruiter"),
    ("Offers", "Application"), ("Interviews", "Application"), ("Interviews", "Interviewer"),
    ("Job Openings", "Department"), ("Job Openings", "Hiring Manager"),
    ("Job Openings", "Recruiter"), ("People", "Department"),
]
CTC_FIELDS = [("Candidates", "Current CTC"), ("Candidates", "Expected CTC"), ("Offers", "Base CTC"),
              ("Job Openings", "Salary Band Min"), ("Job Openings", "Salary Band Max")]

# ------------------------------------------------------------------ data access

T = load_all()
MANIFEST = load_manifest()
SNAPSHOT_DATE = MANIFEST["started_at"][:10]
BY_ID = {r["id"]: r for recs in T.values() for r in recs}
TABLE_OF = {r["id"]: t for t, recs in T.items() for r in recs}
APPS, CANDS, OFFERS, INTS, OPENINGS, PEOPLE = (
    T["Applications"], T["Candidates"], T["Offers"], T["Interviews"], T["Job Openings"], T["People"])


def f(r, k):
    return r["fields"].get(k)


def one(r, k):
    """The single linked record for a link field, or None."""
    v = f(r, k)
    return BY_ID.get(v[0]) if v else None


def many(r, k):
    return [BY_ID[i] for i in (f(r, k) or []) if i in BY_ID]


def label(r):
    key = BUSINESS_KEY.get(TABLE_OF[r["id"]])
    bid = f(r, key) if key and key != "Work Email" else None
    return f"{bid} ({r['id']})" if bid else r["id"]


def sort_key(r):
    return (label(r), r["id"])


CAND_APPS = {c["id"]: many(c, "Applications") for c in CANDS}
APP_OFFERS = {a["id"]: many(a, "Offers") for a in APPS}
APP_INTS = {a["id"]: many(a, "Interviews") for a in APPS}

# ------------------------------------------------------------------ check registry

CHECKS = []   # dicts: section, id, title, rule, pop_label, pop, affected, examples, detail
DETAIL = defaultdict(list)  # section -> extra markdown blocks (crosstabs, distributions)


def check(section, cid, title, rule, pop_label, population, predicate=None, affected=None,
          examples=None, detail=None):
    population = list(population)
    if affected is None:
        affected = [r for r in population if predicate(r)]
    ex = examples if examples is not None else [label(r) for r in sorted(affected, key=sort_key)[:N_EXAMPLES]]
    CHECKS.append(dict(section=section, id=cid, title=title, rule=rule, pop_label=pop_label,
                       n_pop=len(population), n_aff=len(affected), examples=ex, detail=detail))


def crosstab(section, title, rows, row_label, col_label, row_order=None, col_order=None):
    """rows: iterable of (row value, col value). Rendered as a markdown table."""
    c = Counter(rows)
    rv = row_order or sorted({r for r, _ in c}, key=str)
    cv = col_order or sorted({k for _, k in c}, key=str)
    lines = [f"**{title}**", "",
             f"| {row_label} \\ {col_label} | " + " | ".join(f"`{x}`" for x in cv) + " | Total |",
             "|---|" + "---:|" * (len(cv) + 1)]
    for r in rv:
        cells = [c.get((r, k), 0) for k in cv]
        lines.append(f"| `{r}` | " + " | ".join(str(x) if x else "·" for x in cells) + f" | {sum(cells)} |")
    DETAIL[section].append("\n".join(lines))


def dup_groups(records, keyfn):
    groups = defaultdict(list)
    for r in records:
        k = keyfn(r)
        if k is not None:
            groups[k].append(r)
    return [sorted(g, key=sort_key) for g in groups.values() if len(g) > 1]


def dup_check(section, cid, title, rule, pop_label, records, keyfn):
    groups = sorted(dup_groups(records, keyfn), key=lambda g: sort_key(g[0]))
    affected = [r for g in groups for r in g]
    ex = [label(r) for r in groups[0][:N_EXAMPLES]] if groups else []
    check(section, cid, title, rule, pop_label, records, affected=affected, examples=ex,
          detail=f"{len(groups)} duplicate group(s); examples are one group" if groups else None)


# ------------------------------------------------------------------ 1. Completeness

S = "1. Completeness"
for table, recs in T.items():
    fields = list(dict.fromkeys(k for r in recs for k in r["fields"]))
    for fld in fields:
        missing = [r for r in recs if fld not in r["fields"]]
        if missing:
            check(S, f"1.0.{table}.{fld}", f"`{table}.{fld}` is empty", "field absent from the record",
                  f"all {table}", recs, affected=missing)
MISSING_ROWS = [c for c in CHECKS if c["id"].startswith("1.0.")]
CHECKS[:] = [c for c in CHECKS if not c["id"].startswith("1.0.")]  # rendered as their own table

check(S, "1.1", "Rejected application without a rejection reason",
      "`Stage` = `Rejected` and `Rejection Reason` empty", "applications with `Stage` = `Rejected`",
      [a for a in APPS if f(a, "Stage") == "Rejected"], lambda a: not f(a, "Rejection Reason"))
check(S, "1.2", "Closed application without a closed date",
      "`Status` = `Closed` and `Closed On` empty", "applications with `Status` = `Closed`",
      [a for a in APPS if f(a, "Status") == "Closed"], lambda a: not f(a, "Closed On"))
check(S, "1.3", "Active application with a closed date",
      "`Status` = `Active` and `Closed On` filled (converse of 1.2)", "applications with `Status` = `Active`",
      [a for a in APPS if f(a, "Status") == "Active"], lambda a: bool(f(a, "Closed On")))
check(S, "1.4", "Decided offer without a decision date",
      "`Offers.Status` in {`Accepted`, `Declined`} and `Decision On` empty", "decided offers",
      [o for o in OFFERS if f(o, "Status") in ("Accepted", "Declined")], lambda o: not f(o, "Decision On"))
check(S, "1.5", "Pending offer with a decision date",
      "`Offers.Status` = `Pending` and `Decision On` filled", "pending offers",
      [o for o in OFFERS if f(o, "Status") == "Pending"], lambda o: bool(f(o, "Decision On")))
check(S, "1.6", "Declined offer without a decline reason",
      "`Offers.Status` = `Declined` and `Decline Reason` empty", "declined offers",
      [o for o in OFFERS if f(o, "Status") == "Declined"], lambda o: not f(o, "Decline Reason"))
check(S, "1.7", "Decline reason on an offer that was not declined",
      "`Offers.Status` ≠ `Declined` and `Decline Reason` filled", "offers not declined",
      [o for o in OFFERS if f(o, "Status") != "Declined"], lambda o: bool(f(o, "Decline Reason")))

# ------------------------------------------------------------------ 2. Uniqueness and duplicates

S = "2. Uniqueness and duplicates"
dup_check(S, "2.1", "Duplicate `Application ID`", "same `Application ID` on more than one record",
          "all applications", APPS, lambda a: f(a, "Application ID"))
dup_check(S, "2.2", "Candidates sharing a `Full Name`", "same `Full Name` (exact match)",
          "all candidates", CANDS, lambda c: f(c, "Full Name"))
dup_check(S, "2.3", "Candidates sharing a `Phone`", "same `Phone` (exact match)",
          "all candidates", CANDS, lambda c: f(c, "Phone"))
dup_check(S, "2.4", "Candidates sharing an `Email`", "same `Email` (case-insensitive)",
          "all candidates", CANDS, lambda c: (f(c, "Email") or "").strip().lower() or None)
dup_check(S, "2.5", "Candidates sharing both `Full Name` and `Phone`", "same name and same phone",
          "all candidates", CANDS, lambda c: (f(c, "Full Name"), f(c, "Phone")))
dup_check(S, "2.6", "Candidates sharing `Full Name` + `Phone` but with different `Email`",
          "same name and phone, email differs", "all candidates",
          [c for g in dup_groups(CANDS, lambda c: (f(c, "Full Name"), f(c, "Phone")))
           if len({f(x, "Email") for x in g}) > 1 for c in g],
          lambda c: (f(c, "Full Name"), f(c, "Phone")))
CHECKS[-1]["n_pop"] = len(CANDS)
dup_check(S, "2.7", "Same candidate applied more than once to the same opening",
          "more than one application with the same (`Candidate`, `Opening`)", "all applications",
          APPS, lambda a: (tuple(f(a, "Candidate") or []), tuple(f(a, "Opening") or [])))
dup_check(S, "2.8", "Same person (name + phone) applied more than once to the same opening",
          "more than one application whose candidates share name + phone, on the same `Opening`",
          "all applications", APPS,
          lambda a: (f(one(a, "Candidate"), "Full Name"), f(one(a, "Candidate"), "Phone"),
                     tuple(f(a, "Opening") or [])))

NOTE_REF = "Referred internally. Available for a call after 6pm."
NOTE_REAPPLY = "Reached out again after an earlier rejection."
NOTE_CONSOL = "Applied to two openings; consolidated onto the more senior one."
with_note = lambda text: [c for c in CANDS if f(c, "Notes") == text]

check(S, "2.9", "Note says referred, `Source` is not `Referral`",
      f"`Notes` = “{NOTE_REF}” and `Source` ≠ `Referral`", "candidates with that note",
      with_note(NOTE_REF), lambda c: f(c, "Source") != "Referral")
check(S, "2.10", "Note says referred, no application has `Referred By`",
      f"`Notes` = “{NOTE_REF}” and no linked application has `Referred By`", "candidates with that note",
      with_note(NOTE_REF), lambda c: not any(f(a, "Referred By") for a in CAND_APPS[c["id"]]))
check(S, "2.11", "Note says re-applied after rejection, only one application on file",
      f"`Notes` = “{NOTE_REAPPLY}” and exactly 1 linked application", "candidates with that note",
      with_note(NOTE_REAPPLY), lambda c: len(CAND_APPS[c["id"]]) == 1)
check(S, "2.12", "Note says re-applied after rejection, no application is `Rejected`",
      f"`Notes` = “{NOTE_REAPPLY}” and no linked application has `Stage` = `Rejected`",
      "candidates with that note", with_note(NOTE_REAPPLY),
      lambda c: not any(f(a, "Stage") == "Rejected" for a in CAND_APPS[c["id"]]))
check(S, "2.13", "Note says consolidated onto one opening, still more than one application",
      f"`Notes` = “{NOTE_CONSOL}” and more than 1 linked application", "candidates with that note",
      with_note(NOTE_CONSOL), lambda c: len(CAND_APPS[c["id"]]) > 1)
crosstab(S, "Applications per candidate, by `Notes` value",
         [(f(c, "Notes") or "(empty)", len(CAND_APPS[c["id"]])) for c in CANDS], "Notes", "applications")

# ------------------------------------------------------------------ 3. Cross-field consistency

S = "3. Cross-field consistency"
crosstab(S, "`Applications.Stage` × `Applications.Status`",
         [(f(a, "Stage"), f(a, "Status")) for a in APPS], "Stage", "Status")
check(S, "3.1", "Terminal stage still `Active`",
      "`Stage` in {`Rejected`, `Hired`, `Withdrawn`} and `Status` = `Active`",
      "applications in a terminal stage", [a for a in APPS if f(a, "Stage") in TERMINAL_STAGES],
      lambda a: f(a, "Status") == "Active")
check(S, "3.2", "Open stage but `Closed`",
      "`Stage` in {`Applied`, `Screening`, `Interview`, `Offer`} and `Status` = `Closed`",
      "applications in an open stage", [a for a in APPS if f(a, "Stage") in OPEN_STAGES],
      lambda a: f(a, "Status") == "Closed")

crosstab(S, "`Offers.Status` × linked `Applications.Stage`",
         [(f(o, "Status"), f(one(o, "Application"), "Stage")) for o in OFFERS], "Offer status", "Stage")
check(S, "3.3", "`Hired` application without an accepted offer",
      "`Stage` = `Hired` and no linked offer has `Status` = `Accepted`", "applications with `Stage` = `Hired`",
      [a for a in APPS if f(a, "Stage") == "Hired"],
      lambda a: not any(f(o, "Status") == "Accepted" for o in APP_OFFERS[a["id"]]))
check(S, "3.4", "Accepted offer on an application that is not `Hired`",
      "`Offers.Status` = `Accepted` and linked application `Stage` ≠ `Hired`", "accepted offers",
      [o for o in OFFERS if f(o, "Status") == "Accepted"],
      lambda o: f(one(o, "Application"), "Stage") != "Hired")
check(S, "3.5", "Application at `Offer`/`Hired` stage with no offer record",
      "`Stage` in {`Offer`, `Hired`} and `Offers` link empty", "applications at `Offer` or `Hired`",
      [a for a in APPS if f(a, "Stage") in ("Offer", "Hired")], lambda a: not APP_OFFERS[a["id"]])

check(S, "3.6", "`Applications.Offered On` ≠ `Offers.Offered On`",
      "application has an offer and the two dates differ (either one empty counts as differing)",
      "applications with a linked offer", [a for a in APPS if APP_OFFERS[a["id"]]],
      lambda a: f(a, "Offered On") != f(APP_OFFERS[a["id"]][0], "Offered On"))
check(S, "3.7", "`Applications.Offered On` filled but no offer record",
      "`Offered On` filled and `Offers` link empty", "applications with `Offered On`",
      [a for a in APPS if f(a, "Offered On")], lambda a: not APP_OFFERS[a["id"]])

check(S, "3.8", "`Source` = `Referral` but no application has `Referred By`",
      "candidate `Source` = `Referral` and no linked application has `Referred By`",
      "candidates with `Source` = `Referral`", [c for c in CANDS if f(c, "Source") == "Referral"],
      lambda c: not any(f(a, "Referred By") for a in CAND_APPS[c["id"]]))
check(S, "3.9", "`Referred By` filled but candidate `Source` is not `Referral`",
      "application `Referred By` filled and its candidate `Source` ≠ `Referral`",
      "applications with `Referred By`", [a for a in APPS if f(a, "Referred By")],
      lambda a: f(one(a, "Candidate"), "Source") != "Referral")
crosstab(S, "Candidate `Source` for applications with / without `Referred By`",
         [(f(one(a, "Candidate"), "Source"), "Referred By filled" if f(a, "Referred By") else "empty")
          for a in APPS], "Source", "Referred By")

crosstab(S, "`Applications.Rejection Reason` × `Applications.Stage`",
         [(f(a, "Rejection Reason") or "(empty)", f(a, "Stage")) for a in APPS], "Rejection Reason", "Stage")
check(S, "3.10", "`Withdrawn` stage without reason `Withdrew`",
      "`Stage` = `Withdrawn` and `Rejection Reason` ≠ `Withdrew` (including empty)",
      "applications with `Stage` = `Withdrawn`", [a for a in APPS if f(a, "Stage") == "Withdrawn"],
      lambda a: f(a, "Rejection Reason") != "Withdrew")
check(S, "3.11", "Reason `Withdrew` but stage is not `Withdrawn`",
      "`Rejection Reason` = `Withdrew` and `Stage` ≠ `Withdrawn`",
      "applications with reason `Withdrew`", [a for a in APPS if f(a, "Rejection Reason") == "Withdrew"],
      lambda a: f(a, "Stage") != "Withdrawn")
check(S, "3.12", "Rejection reason on an application that is not rejected or withdrawn",
      "`Rejection Reason` filled and `Stage` not in {`Rejected`, `Withdrawn`}",
      "applications with a `Rejection Reason`", [a for a in APPS if f(a, "Rejection Reason")],
      lambda a: f(a, "Stage") not in ("Rejected", "Withdrawn"))

RESULT_FIELDS = ("Completed On", "Score", "Recommendation", "Feedback")
crosstab(S, "`Interviews.Outcome` × which result fields are filled",
         [(f(i, "Outcome"), "+".join(k for k in RESULT_FIELDS if k in i["fields"]) or "none") for i in INTS],
         "Outcome", "filled")
check(S, "3.13", "`Completed` interview missing a result field",
      "`Outcome` = `Completed` and any of `Completed On`, `Score`, `Recommendation` empty",
      "interviews with `Outcome` = `Completed`", [i for i in INTS if f(i, "Outcome") == "Completed"],
      lambda i: any(k not in i["fields"] for k in ("Completed On", "Score", "Recommendation")))
check(S, "3.14", "Non-completed interview with result fields",
      "`Outcome` ≠ `Completed` and any of `Completed On`, `Score`, `Recommendation` filled",
      "interviews not `Completed`", [i for i in INTS if f(i, "Outcome") != "Completed"],
      lambda i: any(k in i["fields"] for k in ("Completed On", "Score", "Recommendation")))
rec_scores = defaultdict(list)
for i in INTS:
    if f(i, "Score") is not None:
        rec_scores[f(i, "Recommendation") or "(empty)"].append(f(i, "Score"))
DETAIL[S].append("**`Interviews.Score` by `Recommendation`** (descriptive)\n\n| Recommendation | n | min | max |\n"
                 "|---|---:|---:|---:|\n" + "\n".join(
                     f"| `{k}` | {len(v)} | {min(v)} | {max(v)} |" for k, v in sorted(rec_scores.items())))

with_ints = [a for a in APPS if APP_INTS[a["id"]] or f(a, "First Interview On")]
check(S, "3.15", "`First Interview On` ≠ earliest linked `Interviews.Scheduled On`",
      "dates differ, or one side missing", "applications with interviews or `First Interview On`",
      with_ints, lambda a: f(a, "First Interview On") != min(
          (f(i, "Scheduled On") for i in APP_INTS[a["id"]]), default=None))
with_final = [a for a in APPS if f(a, "Final Interview On")]
check(S, "3.16", "`Final Interview On` ≠ latest linked `Interviews.Scheduled On`",
      "dates differ, or no linked interviews", "applications with `Final Interview On`",
      with_final, lambda a: f(a, "Final Interview On") != max(
          (f(i, "Scheduled On") for i in APP_INTS[a["id"]]), default=None))
check(S, "3.17", "`Final Interview On` filled with only one linked interview",
      "`Final Interview On` filled and exactly 1 linked interview", "applications with `Final Interview On`",
      with_final, lambda a: len(APP_INTS[a["id"]]) == 1)

crosstab(S, "`Applications.Stage` × number of linked interviews / offers",
         [(f(a, "Stage"), f"{len(APP_INTS[a['id']])} int · {len(APP_OFFERS[a['id']])} offer") for a in APPS],
         "Stage", "links")
check(S, "3.18", "Early stage with interviews",
      "`Stage` in {`Applied`, `Screening`} and `Interviews` link filled",
      "applications at `Applied` or `Screening`", [a for a in APPS if f(a, "Stage") in ("Applied", "Screening")],
      lambda a: bool(APP_INTS[a["id"]]))
check(S, "3.19", "`Interview`/`Offer`/`Hired` stage without interviews",
      "`Stage` in {`Interview`, `Offer`, `Hired`} and `Interviews` link empty",
      "applications at `Interview`, `Offer` or `Hired`",
      [a for a in APPS if f(a, "Stage") in ("Interview", "Offer", "Hired")], lambda a: not APP_INTS[a["id"]])
check(S, "3.20", "Pre-offer stage with an offer",
      "`Stage` in {`Applied`, `Screening`, `Interview`} and `Offers` link filled",
      "applications at `Applied`, `Screening` or `Interview`",
      [a for a in APPS if f(a, "Stage") in ("Applied", "Screening", "Interview")],
      lambda a: bool(APP_OFFERS[a["id"]]))
check(S, "3.21", "Past-screening stage without `Screened On`",
      "`Stage` in {`Interview`, `Offer`, `Hired`} and `Screened On` empty",
      "applications at `Interview`, `Offer` or `Hired`",
      [a for a in APPS if f(a, "Stage") in ("Interview", "Offer", "Hired")], lambda a: not f(a, "Screened On"))

# ------------------------------------------------------------------ 4. Temporal validity

S = "4. Temporal validity"
for i, (a_f, b_f) in enumerate(combinations(PIPELINE, 2), 1):
    check(S, f"4.1.{i}", f"`{a_f}` after `{b_f}`", f"`{a_f}` > `{b_f}`", "applications with both dates",
          [a for a in APPS if f(a, a_f) and f(a, b_f)], lambda a, x=a_f, y=b_f: f(a, x) > f(a, y))


def pipeline_broken(a):
    present = [f(a, k) for k in PIPELINE if f(a, k)]
    return any(x > y for x, y in combinations(present, 2))


check(S, "4.1", "Any pipeline-order violation (summary of 4.1.x)",
      "any pair of pipeline dates out of order", "all applications", APPS, pipeline_broken)

for i, (a_f, b_f) in enumerate([("Offered On", "Decision On"), ("Decision On", "Proposed Start Date"),
                                ("Offered On", "Proposed Start Date")], 1):
    check(S, f"4.2.{i}", f"Offer `{a_f}` after `{b_f}`", f"`{a_f}` > `{b_f}`", "offers with both dates",
          [o for o in OFFERS if f(o, a_f) and f(o, b_f)], lambda o, x=a_f, y=b_f: f(o, x) > f(o, y))
check(S, "4.2.4", "Offer dated before its application's `Applied On`",
      "`Offers.Offered On` < linked `Applications.Applied On`", "all offers", OFFERS,
      lambda o: f(o, "Offered On") < f(one(o, "Application"), "Applied On"))

check(S, "4.3", "Candidate `Created On` after their first application",
      "`Candidates.Created On` > min(linked `Applications.Applied On`)", "all candidates", CANDS,
      lambda c: f(c, "Created On") > min(f(a, "Applied On") for a in CAND_APPS[c["id"]]))
check(S, "4.4", "Applied before the opening was opened",
      "`Applied On` < opening's `Opened On`", "all applications", APPS,
      lambda a: f(a, "Applied On") < f(one(a, "Opening"), "Opened On"))
check(S, "4.5", "Applied after the opening's target close",
      "`Applied On` > opening's `Target Close`", "all applications", APPS,
      lambda a: f(a, "Applied On") > f(one(a, "Opening"), "Target Close"))

check(S, "4.6", "Interview completed before it was scheduled",
      "`Completed On` < `Scheduled On`", "interviews with `Completed On`",
      [i for i in INTS if f(i, "Completed On")], lambda i: f(i, "Completed On") < f(i, "Scheduled On"))
check(S, "4.7", "Interview completed on a different day from scheduled",
      "`Completed On` ≠ `Scheduled On`", "interviews with `Completed On`",
      [i for i in INTS if f(i, "Completed On")], lambda i: f(i, "Completed On") != f(i, "Scheduled On"))
check(S, "4.8", "Interview scheduled before the application was made",
      "`Scheduled On` < linked `Applications.Applied On`", "all interviews", INTS,
      lambda i: f(i, "Scheduled On") < f(one(i, "Application"), "Applied On"))
check(S, "4.9", "Interview scheduled after the application closed",
      "`Scheduled On` > linked `Applications.Closed On`", "interviews whose application has `Closed On`",
      [i for i in INTS if f(one(i, "Application"), "Closed On")],
      lambda i: f(i, "Scheduled On") > f(one(i, "Application"), "Closed On"))

DATE_FIELDS = [(t, k) for t, recs in T.items() for k in dict.fromkeys(x for r in recs for x in r["fields"])
               if all(isinstance(r["fields"][k], str) and ISO_DATE.match(r["fields"][k])
                      for r in recs if k in r["fields"])]
n = 0
for t, k in DATE_FIELDS:
    recs = [r for r in T[t] if f(r, k)]
    n += 1
    check(S, f"4.10.{n}", f"`{t}.{k}` later than the row's own `createdTime`",
          f"`{k}` > date part of `createdTime`", f"{t} with `{k}`", recs,
          lambda r, k=k: f(r, k) > r["createdTime"][:10])
    check(S, f"4.11.{n}", f"`{t}.{k}` later than the snapshot date ({SNAPSHOT_DATE})",
          f"`{k}` > {SNAPSHOT_DATE}", f"{t} with `{k}`", recs, lambda r, k=k: f(r, k) > SNAPSHOT_DATE)

ct_lines = ["**Row `createdTime` per table** (descriptive)", "",
            "| Table | Rows | Distinct `createdTime` values | Distinct dates | Earliest | Latest |",
            "|---|---:|---:|---:|---|---|"]
for t, recs in T.items():
    if recs:
        ts = sorted(r["createdTime"] for r in recs)
        ct_lines.append(f"| {t} | {len(recs)} | {len(set(ts))} | {len({x[:10] for x in ts})} | {ts[0]} | {ts[-1]} |")
DETAIL[S].append("\n".join(ct_lines))

# ------------------------------------------------------------------ 5. Validity and ranges

S = "5. Validity and ranges"
scored = [i for i in INTS if f(i, "Score") is not None]
check(S, "5.1", "`Interviews.Score` is not a whole number", "`Score` has a fractional part",
      "interviews with `Score`", scored, lambda i: f(i, "Score") != int(f(i, "Score")))
check(S, "5.2", "`Interviews.Score` outside 1–5", "`Score` < 1 or > 5", "interviews with `Score`",
      scored, lambda i: not 1 <= f(i, "Score") <= 5)
check(S, "5.3", "`Interviews.Score` with more than one decimal place", "`Score` × 10 not a whole number",
      "interviews with `Score`", scored, lambda i: round(f(i, "Score") * 10, 6) % 1 != 0)
DETAIL[S].append("**`Interviews.Score` values** (count)\n\n" + ", ".join(
    f"`{v}` {c}" for v, c in sorted(Counter(f(i, "Score") for i in scored).items())))

check(S, "5.4", "Expected CTC below current CTC", "`Expected CTC` < `Current CTC`", "all candidates",
      CANDS, lambda c: f(c, "Expected CTC") < f(c, "Current CTC"))
check(S, "5.5", "Expected CTC equal to current CTC", "`Expected CTC` = `Current CTC`", "all candidates",
      CANDS, lambda c: f(c, "Expected CTC") == f(c, "Current CTC"))
opening_of_offer = lambda o: one(one(o, "Application"), "Opening")
check(S, "5.6", "Offer base CTC below the opening's salary band",
      "`Offers.Base CTC` < opening `Salary Band Min`", "all offers", OFFERS,
      lambda o: f(o, "Base CTC") < f(opening_of_offer(o), "Salary Band Min"))
check(S, "5.7", "Offer base CTC above the opening's salary band",
      "`Offers.Base CTC` > opening `Salary Band Max`", "all offers", OFFERS,
      lambda o: f(o, "Base CTC") > f(opening_of_offer(o), "Salary Band Max"))
check(S, "5.8", "Opening salary band inverted", "`Salary Band Min` > `Salary Band Max`",
      "all openings", OPENINGS, lambda j: f(j, "Salary Band Min") > f(j, "Salary Band Max"))

for i, (t, k) in enumerate(CTC_FIELDS, 1):
    recs = [r for r in T[t] if f(r, k) is not None]
    check(S, f"5.9.{i}", f"`{t}.{k}` not a multiple of 1,000", f"`{k}` mod 1,000 ≠ 0", f"{t} with `{k}`",
          recs, lambda r, k=k: f(r, k) % 1000 != 0)
    check(S, f"5.10.{i}", f"`{t}.{k}` below 100,000 or above 10,000,000",
          f"`{k}` < 100,000 or > 10,000,000 (unit check)", f"{t} with `{k}`",
          recs, lambda r, k=k: not 100_000 <= f(r, k) <= 10_000_000)

check(S, "5.11", "`Years Experience` is 0", "`Years Experience` = 0", "all candidates", CANDS,
      lambda c: f(c, "Years Experience") == 0)
check(S, "5.12", "`Years Experience` negative or above 40", "< 0 or > 40", "all candidates", CANDS,
      lambda c: not 0 <= f(c, "Years Experience") <= 40)
check(S, "5.13", "`Notice Period Days` negative or above 180", "< 0 or > 180", "all candidates", CANDS,
      lambda c: not 0 <= f(c, "Notice Period Days") <= 180)
check(S, "5.14", "`Joining Bonus` negative", "< 0", "all offers", OFFERS, lambda o: f(o, "Joining Bonus") < 0)
DETAIL[S].append("**Distributions** (descriptive)\n\n" + "\n".join([
    "- `Candidates.Notice Period Days`: " + ", ".join(
        f"`{v}` {c}" for v, c in sorted(Counter(f(c, "Notice Period Days") for c in CANDS).items())),
    "- `Offers.Joining Bonus`: " + ", ".join(
        f"`{v:,}` {c}" for v, c in sorted(Counter(f(o, "Joining Bonus") for o in OFFERS).items())),
    "- `Candidates.Years Experience`: min {} · max {} · whole numbers {} of {}".format(
        min(f(c, "Years Experience") for c in CANDS), max(f(c, "Years Experience") for c in CANDS),
        sum(f(c, "Years Experience") == int(f(c, "Years Experience")) for c in CANDS), len(CANDS)),
]))

# ------------------------------------------------------------------ 6. Referential integrity

S = "6. Referential integrity"
link_fields = [(t, k) for t, recs in T.items() for k in dict.fromkeys(x for r in recs for x in r["fields"])
               if all(isinstance(r["fields"][k], list) and all(str(v).startswith("rec") for v in r["fields"][k])
                      for r in recs if k in r["fields"])]
all_links = [(r, k, v) for t, k in link_fields for r in T[t] if f(r, k) for v in f(r, k)]
check(S, "6.1", "Link to a record ID not found in the snapshot", "linked ID resolves to no record",
      "all link values (across every link field)", all_links, affected=[x for x in all_links if x[2] not in BY_ID],
      examples=[f"{label(r)} → {k} → {v}" for r, k, v in all_links if v not in BY_ID][:N_EXAMPLES])

pairs = {(r["id"], v) for r, k, v in all_links}
one_sided = [(r, k, v) for r, k, v in all_links if (v, r["id"]) not in pairs]
check(S, "6.2", "Link present on one side only", "A links to B but B has no link back to A",
      "all link values", all_links, affected=one_sided,
      examples=[f"{label(r)} → {k} → {v}" for r, k, v in one_sided][:N_EXAMPLES])

for i, (t, k) in enumerate(SINGLE_LINKS, 1):
    check(S, f"6.3.{i}", f"`{t}.{k}` does not have exactly one link", "0 or more than 1 linked record",
          f"all {t}", T[t], lambda r, k=k: len(f(r, k) or []) != 1)

check(S, "6.4", "Application recruiter differs from the opening's recruiter",
      "`Applications.Recruiter` ≠ opening `Job Openings.Recruiter`", "all applications", APPS,
      lambda a: f(a, "Recruiter") != f(one(a, "Opening"), "Recruiter"))
role_checks = [
    ("6.5", "Applications", "Recruiter", "Recruiter"),
    ("6.6", "Job Openings", "Recruiter", "Recruiter"),
    ("6.7", "Job Openings", "Hiring Manager", "Hiring Manager"),
    ("6.8", "Interviews", "Interviewer", "Interviewer"),
]
for cid, t, k, role in role_checks:
    check(S, cid, f"`{t}.{k}` links to a person whose `Role` ≠ `{role}`",
          f"linked `People.Role` ≠ `{role}`", f"all {t}", T[t],
          lambda r, k=k, role=role: f(one(r, k), "Role") != role)
check(S, "6.9", "Referrer is the same person as the application's recruiter",
      "`Referred By` is the same person as the application's `Recruiter`", "applications with `Referred By`",
      [a for a in APPS if f(a, "Referred By")], lambda a: f(a, "Referred By") == f(a, "Recruiter"))
crosstab(S, "`People.Role` of linked people, by link field",
         [(f"{TABLE_OF[r['id']]}.{k}", f(BY_ID[v], "Role")) for r, k, v in all_links
          if TABLE_OF.get(v) == "People"], "Link field", "Role")

# ------------------------------------------------------------------ 7. Coverage and sample size

S = "7. Coverage and sample size"
cov = ["**Population sizes** (descriptive)", "", "| Population | n |", "|---|---:|"]
for t, recs in T.items():
    cov.append(f"| {t} rows | {len(recs)} |")
for role, c in sorted(Counter(f(p, "Role") for p in PEOPLE).items()):
    cov.append(f"| People with `Role` = `{role}` | {c} |")
for st, c in sorted(Counter(f(o, "Status") for o in OFFERS).items()):
    cov.append(f"| Offers with `Status` = `{st}` | {c} |")
for st, c in sorted(Counter(f(j, "Status") for j in OPENINGS).items()):
    cov.append(f"| Job Openings with `Status` = `{st}` | {c} |")
per_opening = sorted(len(f(j, "Applications") or []) for j in OPENINGS)
cov.append(f"| Applications per opening (min / median / max) | {per_opening[0]} / "
           f"{per_opening[len(per_opening) // 2]} / {per_opening[-1]} |")
DETAIL[S].append("\n".join(cov))
check(S, "7.1", "Findings table has no rows", "table returned 0 records", "tables in the base",
      list(T), affected=[t for t in T if not T[t]], examples=[t for t in T if not T[t]])


# ------------------------------------------------------------------ render

def pct(a, b):
    return f"{100 * a / b:.1f}%" if b else "—"


def render():
    L = ["# Data-quality checks (D4)", "",
         f"Snapshot: `data/raw/` fetched {MANIFEST['started_at']}. Generated by `scripts/data_quality.py` "
         "from the cached snapshot only.", "",
         "Runs every item in the D4 checklist (`reports/data_profile.md` §3). Results are counts only: "
         "**no interpretation, no severity and no fixes**. "
         "Each check gives its rule, the population it applies to, the number of records breaking the "
         "rule, and up to 3 example IDs as `BUSINESS-ID (recordId)`, sorted by business ID. "
         "Crosstabs and distributions under each section are descriptive context.", "",
         "Airtable omits empty fields, so **empty = field absent from the record**. Dates are compared as "
         "`YYYY-MM-DD` strings (all date fields are ISO in this snapshot).", ""]

    by_section = defaultdict(list)
    for c in CHECKS:
        by_section[c["section"]].append(c)

    sections = list(dict.fromkeys([c["section"] for c in CHECKS] + list(DETAIL)))
    L += ["## Summary: checks with at least one affected record", "",
          "| ID | Check | Affected | Out of | % |", "|---|---|---:|---:|---:|"]
    for c in CHECKS:
        if c["n_aff"]:
            L.append(f"| {c['id']} | {c['title']} | {c['n_aff']} | {c['n_pop']} | {pct(c['n_aff'], c['n_pop'])} |")
    zero = [c["id"] for c in CHECKS if not c["n_aff"]]
    L += ["", f"{len(CHECKS)} checks run; {len(CHECKS) - len(zero)} with ≥1 affected record; "
          f"{len(zero)} with none (listed in each section).", ""]

    for s in sections:
        L += [f"## {s}", ""]
        if s.startswith("1."):
            L += ["**1.0 Missing values per field** (every field with ≥1 empty record)", "",
                  "| Field | Empty | Out of | % | Examples |", "|---|---:|---:|---:|---|"]
            for c in MISSING_ROWS:
                L.append(f"| {c['title'].split('`')[1]} | {c['n_aff']} | {c['n_pop']} | "
                         f"{pct(c['n_aff'], c['n_pop'])} | {', '.join(c['examples'])} |")
            L.append("")
        rows = by_section.get(s, [])
        if rows:
            L += ["| ID | Check | Rule | Affected | Out of (population) | % | Example IDs |",
                  "|---|---|---|---:|---|---:|---|"]
            for c in rows:
                ex = ", ".join(c["examples"]) if c["examples"] else "—"
                if c["detail"]:
                    ex += f" — {c['detail']}"
                L.append(f"| {c['id']} | {c['title']} | {c['rule']} | **{c['n_aff']}** | "
                         f"{c['n_pop']} ({c['pop_label']}) | {pct(c['n_aff'], c['n_pop'])} | {ex} |")
            L.append("")
        for block in DETAIL.get(s, []):
            L += [block, ""]
    return "\n".join(L) + "\n"


def main():
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(render())
    hit = sum(1 for c in CHECKS if c["n_aff"])
    print(f"wrote {OUT.relative_to(ROOT)}: {len(CHECKS)} checks, {hit} with affected records")


if __name__ == "__main__":
    main()
