# Project notes — TalentFlow Q3 roadmap exercise

Source of truth: `CANDIDATE_PACK_PM.md` (supplied as a .docx). Everything below is
taken from that document; anything that is our own note rather than the brief
is marked **[our note]**.

Status: data ingested and profiled. No claims calculated and no roadmap decisions yet.

---

## 1. Objective of the exercise

- Role: product manager for **TalentFlow**, a recruiting-operations product.
- Customer: **Acme**, TalentFlow's largest design partner. Acme has given read
  access to its production data: job openings, candidates, applications,
  interviews and offers.
- Budget: **6 engineer-weeks** next quarter. The task is to decide what goes into them.
- What is being assessed: *"how you turn a customer's real data into a defensible
  roadmap, using Claude Code and the Airtable REST API."* We are not expected to
  write code ourselves, but to *"direct the tool well enough that you would stake
  a decision on the numbers it gives you."*
- The trigger: Acme's VP People emailed TalentFlow's CEO on a Friday with two
  claims or requests. The CEO has said yes in principle. The brief: *"You have the
  data. Decide what is actually true."*
- Time: **2 hours, in one sitting**. *"Two hours is a cap, not a target."* They
  prefer three deliverables we stand behind over five rushed ones, and **they will
  ask how long it took.**
  - **[our note]** This session started at about 2026-09-23 08:03 UTC. Keep a
    record of the time spent.

## 2. The two claims to investigate

Quoted from the VP People's email:

> "Two things for next quarter.
> First — job boards are our biggest channel by a wide margin and they bring in
> 26.9% of our hires. I want the job-board integration work brought forward.
> Second — our offer acceptance rate is sitting at around 72% and the board is
> asking about it. I need that number moving."

| # | Claim (factual part) | Ask (roadmap part) |
|---|---|---|
| C1 | Job boards are Acme's **biggest channel by a wide margin** and bring in **26.9% of hires** | Bring the **job-board integration** work forward |
| C2 | Offer acceptance rate is **about 72%** and the board is asking about it | Get that number moving |

For each claim, the verdict must be one of: **build it, don't build it, or build
something different.** Each verdict needs **the one number that decides it.**

## 3. Deliverables D1–D5

Suggested timings are a guide; the weights show where the marks are (total 100
marks, about 100 minutes).

| ID | Deliverable | Time | Marks | Requirements |
|---|---|---|---|---|
| **D1** | Verdict on the VP's two claims | 15 min | **16** | For each claim: build it / don't build it / build something different. Each verdict carries the one number that decides it. *"Disagreeing with the VP is fine. Agreeing is fine. Doing either without a number is not."* |
| **D2** | The 6 engineer-weeks | 20 min | **20** | **Three things we will build**, in order, each with a rough size and the number that justifies it. **Three things we will not build**, each with why not. *"The not-doing list is scored as heavily as the doing list."* |
| **D3** | Metrics spec for offer acceptance rate | 15 min | **15** | Precise enough that *two engineers would implement it identically*: **numerator, denominator, edge cases, time window, and what the dashboard shows when the answer is ambiguous.** |
| **D4** | What in this data would you not trust? | 35 min | **30** (most) | Look at the data itself, not only the questions asked. **What is wrong, how much of it is wrong, and how that changes the answers above.** Be systematic: *"more interested in how you went looking than in any single problem."* If short on time, spend it here rather than polishing D2. |
| **D5** | One-page memo | 15 min | **19** | What we found, what we are doing about it, what we would look at next. **One page.** |

## 4. Airtable access

| Item | Value |
|---|---|
| Base name | **TalentFlow - Acme Corp** |
| Base ID | `appYePRAI75PMbQNQ` |
| API key | Personal access token supplied in the pack. Stored only in `.env` as `AIRTABLE_TOKEN` (git-ignored). **Not reproduced here.** |
| Access level | **Read-only.** *"Writes will return 403 — that is expected, not a bug."* |
| API docs | https://airtable.com/developers/web/api/introduction |
| API | Airtable REST API, `https://api.airtable.com/v0/{baseId}/{tableName}`, with the header `Authorization: Bearer $AIRTABLE_TOKEN` |
| Tooling | Our choice: raw REST, a client library, an MCP server, and so on |

**Tables (8):** Departments, People, Job Openings, Candidates, Applications,
Interviews, Offers, Findings.

- **Findings** is read-only for us. The findings table must be sent back **as a
  file**, not written as rows.

Sample connectivity check given in the pack:

```bash
curl -H "Authorization: Bearer $AIRTABLE_TOKEN" \
  "https://api.airtable.com/v0/appYePRAI75PMbQNQ/Applications?maxRecords=3"
```

Rule: *"Put the key in an environment variable or a .env file. Do not paste it
into your code."*

## 5. API constraints ("real constraints, not hints")

- **Rate limit: 5 requests per second, per base.** Going over returns **HTTP 429
  and locks us out for 30 seconds.**
- **Pagination: list endpoints return at most 100 records per request.** Larger
  tables are paginated. Keep requesting with the returned `offset` until no
  `offset` comes back.
- **Recommended approach:** *pull the data down once, cache it to disk, and
  analyse locally.* The pack calls this the approach they would expect in
  production.
- **[our note]** Implementation plan: throttle to 5 requests per second or less
  (for example, at least 0.25 s between calls), back off on 429, page with
  `pageSize=100` and `offset`, and write raw JSON per table to `data/raw/`
  (git-ignored). Analysis then runs only against the cache.
- **[our note]** `maxRecords` caps the total returned, so a `maxRecords=3` call
  returns no `offset`. Full pulls must not set `maxRecords`.

## 6. Numbers stated in the exercise

| Figure | Context |
|---|---|
| **2 hours** | Time cap, one sitting |
| **6 engineer-weeks** | Next quarter's capacity to allocate |
| **26.9%** | VP's claim: share of hires from job boards (claimed "biggest channel by a wide margin") |
| **~72%** | VP's claim: current offer acceptance rate |
| **5 requests/sec per base** | API rate limit |
| **429 + 30 seconds** | Penalty for exceeding the rate limit |
| **100 records** | Maximum per list request (pagination) |
| **8** | Number of tables in the base |
| **3** | `maxRecords=3` in the sample connectivity call |
| **3 build + 3 not-build** | Required D2 structure |
| **1 page** | D5 memo length |
| D1 15 min / 16 marks | |
| D2 20 min / 20 marks | |
| D3 15 min / 15 marks | |
| D4 35 min / 30 marks | Highest-weighted deliverable |
| D5 15 min / 19 marks | |
| **100 marks / 100 min** | Totals (our arithmetic from the D1–D5 figures) |

**[our note]** The pack mostly says "2 hours" but the API section says the
caching approach "will make your hour go much further". This is a small
inconsistency in the brief. We treat 2 hours as the cap.

## 7. What to send back

1. **The memo, the roadmap and the metrics spec.** One document is fine (covers
   D1, D2, D3, D5, and D4 as part of it or alongside it).
2. **A findings table** with the columns **claim, metric, value, method,
   confidence**, as Markdown or CSV. Sent as a file, because the Findings table in
   the base is read-only.
3. **Our code or queries**, in a repo or a zip. *"We will re-run them and expect
   your numbers back"*, so the pipeline must be reproducible from a clean checkout
   plus a `.env`.
4. **The Claude Code session transcript.**

## 8. How we will be assessed

| Criterion | What they are looking for |
|---|---|
| Decision quality | Verdicts follow from the data, *not from the loudest voice* |
| Sizing | Knowing how big each problem is, and how certain, *before* ranking it |
| Metric discipline | Definitions survive contact with an edge case |
| Judgement about the data | Checked whether the data could carry the decision |
| Communication | The memo says what to do, not only what is true |
| Use of Claude Code | How the tool was directed, judged from the transcript |

Also explicitly rewarded:
- Stating uncertainty plainly when we can't fully stand behind a number,
  *"including telling us a difference is too small to act on."*
- Saying what we would have checked with more time.
- Honesty about time taken. Fewer, solid deliverables beat more, weaker ones.

## 9. Security and credential handling

From the brief:
- Put the key in an **environment variable or `.env` file**. **Never paste it
  into code.**
- Access is **read-only**. A 403 on a write is expected. Do not try to write to
  any table, including Findings.

Our practice:
- The token lives only in `.env` (file mode 600). `.env` is in `.gitignore`.
  `.env.example` holds a placeholder only.
- The token is never printed in notes, code, README, logs, transcript summaries
  or other output. Scripts load it from `.env` and replace it with `[REDACTED]`
  in any error text.
- All code issues **GET requests only**.

## 10. Environment and access status

Checked 2026-09-23 with `scripts/check_connection.py`:

- `GET /v0/appYePRAI75PMbQNQ/Applications?maxRecords=3` returned **HTTP 200**
  with **3 records**. Access is live. Record contents were not inspected.
- `GET /v0/meta/whoami` returned HTTP 200.
- **[our note] Important caveat about this environment:** this cloud session
  sends traffic through an egress proxy that **injects its own Airtable
  credential** for `api.airtable.com`. A test with a deliberately invalid token,
  and one with no auth header, both returned HTTP 200, and `whoami` returned the
  same identity as with the real token. In this session, requests are therefore
  authenticated by the **proxy-injected account, not by the candidate token in
  `.env`**. As a result:
  - The candidate token itself has **not** been independently verified from this
    environment. It should work as-is when the assessors re-run the code, since
    their environment has no proxy.
  - The **read-only guarantee is not confirmed**. The injected credential may
    have broader permissions than the candidate token. We therefore **did not
    attempt a write to test for 403**, and all code stays GET-only.
  - Data access matches what the pack describes (same base ID, tables
    reachable), so the analysis is unaffected. Only the credential path differs.

### Ingestion findings (2026-09-23)

- **Schema metadata endpoint returns HTTP 403**
  (`/v0/meta/bases/{id}/tables`, which needs `schema.bases:read`). Field types,
  select-option lists and the Airtable primary field are therefore **inferred
  from values**. Consequence: a field that is empty in every record, or a
  select option that is never used, is invisible to us.
- **The Findings table returns 0 records** (HTTP 200). It exists but is empty
  for the credential in use.
- Full pull: 8 tables, 932 records, 15 requests, no 429s or retries.
  Pagination was verified: page sizes of 100/100/100/50 for Applications, and
  all record IDs unique across pages.
- **The GitHub repo is public.** The raw data and the raw-record sample contain
  candidate names, emails and phone numbers, so `data/` is git-ignored. Only
  code and the PII-masked profile are committed. The container is ephemeral,
  so `data/` is regenerated with `scripts/ingest.py`.

## Repo layout

See the table in [`README.md`](README.md).
