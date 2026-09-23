"""Which tables, fields and relationships each deliverable depends on.

Rendered into section 3 of reports/data_profile.md. Every `Table.Field`
reference in backticks is checked against the snapshot by profile_data.py,
so a typo or a renamed field fails the build instead of going unnoticed.

This file maps the data; it deliberately contains no computed numbers,
verdicts or interpretation.
"""

RELEVANCE = [
    {
        "title": "D1 — Job boards as a channel (\"26.9% of hires\", \"biggest channel by a wide margin\")",
        "parts": [
            ("Tables", [
                "Candidates, Applications, Offers (core). Job Openings (what was being hired for, headcount, "
                "req status). People (referrers).",
            ]),
            ("Fields", [
                "`Candidates.Source`: the only explicit channel field. It is stored on the **candidate**, "
                "not the application, so a candidate with two applications has a single source.",
                "`Applications.Referred By`: a second, independent record of referrals (link to People), "
                "alongside `Candidates.Source` = `Referral`.",
                "What counts as a hire (to be decided, candidates for the definition): "
                "`Applications.Stage` = `Hired`, `Offers.Status` = `Accepted`, `Job Openings.Status` = "
                "`Filled` with `Job Openings.Headcount`.",
                "Time window (the VP did not state one): `Applications.Applied On`, `Applications.Closed On`, "
                "`Offers.Offered On`, `Offers.Decision On`, `Offers.Proposed Start Date`.",
                "Top-of-funnel volume per channel (for \"biggest channel\"): `Candidates.id` / "
                "`Applications.id` grouped by `Candidates.Source`.",
            ]),
            ("Join path", [
                "`Offers.Application` → Applications → `Applications.Candidate` → Candidates → "
                "`Candidates.Source`",
                "`Applications.Opening` → Job Openings → `Job Openings.Department` → Departments",
            ]),
            ("Open definitional questions", [
                "\"Biggest channel\" by what: candidates, applications or hires? These can rank differently.",
                "Is the unit of a hire the application, the candidate or the filled seat?",
                "Which source wins when `Candidates.Source` and `Applications.Referred By` disagree?",
                "Which period does \"26.9%\" refer to?",
            ]),
        ],
    },
    {
        "title": "D3 — Offer acceptance rate (\"around 72%\")",
        "parts": [
            ("Tables", [
                "Offers (core). Applications (stage and offer-date context). Candidates (the person, "
                "for anyone with more than one offer). Job Openings (cancelled reqs).",
            ]),
            ("Fields", [
                "`Offers.Status`: outcome values are `Accepted`, `Declined` and `Pending`.",
                "`Offers.Offered On`, `Offers.Decision On`: event dates for the time window and decision lag. "
                "`Offers.Decision On` is not always filled.",
                "`Offers.Decline Reason`: filled only on some records.",
                "`Offers.Proposed Start Date`: planned start. There is **no actual-joining field**, so an "
                "offer that was accepted and then reneged on cannot be seen directly.",
                "`Offers.Application` ↔ `Applications.Offers`: one-to-many allowed by the schema.",
                "`Applications.Offered On`: a second copy of the offer date, alongside `Offers.Offered On`.",
                "`Applications.Stage` (`Offer`, `Hired`, `Withdrawn`, `Rejected`) and "
                "`Applications.Status` (`Active` / `Closed`): cross-check against `Offers.Status`.",
                "`Applications.Rejection Reason` (`Position Cancelled`, `Withdrew`) and `Job Openings.Status` "
                "(`Cancelled`, `On Hold`): offers that may have been rescinded rather than declined.",
            ]),
            ("Join path", [
                "`Offers.Application` → Applications → `Applications.Candidate` → Candidates",
                "`Applications.Opening` → Job Openings",
            ]),
            ("Open definitional questions (feed the D3 spec)", [
                "Are `Pending` offers in the denominator, excluded, or shown separately?",
                "Is the time window by offer date or by decision date?",
                "Is the unit per offer, per application or per candidate? Revised or re-issued offers matter here.",
                "Where does a rescinded offer or a cancelled req go? Is it excluded or counted as not accepted?",
                "Which is the source of truth when `Offers.Status` and `Applications.Stage` disagree?",
            ]),
        ],
    },
    {
        "title": "D4 — Data-quality investigation (systematic checklist, not yet run)",
        "parts": [
            ("Scope", [
                "All tables. Most checks centre on Applications, Candidates and Offers because D1 and D3 "
                "depend on them.",
            ]),
            ("1. Completeness", [
                "Missing rates per field (section 4). Next, check stage-conditional completeness: "
                "`Applications.Stage` = `Rejected` needs `Applications.Rejection Reason`; "
                "`Applications.Status` = `Closed` needs `Applications.Closed On`; decided offers need "
                "`Offers.Decision On`.",
            ]),
            ("2. Uniqueness and duplicates", [
                "`Applications.Application ID`: business IDs should be unique.",
                "People who may be duplicated: `Candidates.Full Name`, `Candidates.Phone`, `Candidates.Email`.",
                "Repeat applications: the same candidate on the same `Applications.Opening`.",
                "`Candidates.Notes` contains templated remarks about referrals, re-applications and "
                "consolidated applications. These could be cross-checked against the structured fields.",
            ]),
            ("3. Cross-field consistency", [
                "`Applications.Stage` vs `Applications.Status` (for example a terminal stage still `Active`).",
                "`Applications.Stage` = `Hired` vs `Offers.Status` = `Accepted`, in both directions.",
                "`Applications.Offered On` vs `Offers.Offered On`.",
                "`Candidates.Source` = `Referral` vs `Applications.Referred By`.",
                "`Applications.Stage` = `Withdrawn` vs `Applications.Rejection Reason` = `Withdrew`.",
                "`Interviews.Outcome` vs `Interviews.Completed On`, `Interviews.Score` and "
                "`Interviews.Recommendation`.",
                "`Applications.First Interview On` / `Applications.Final Interview On` vs "
                "`Interviews.Scheduled On`.",
                "`Applications.Interviews` present vs `Applications.Stage` reached.",
            ]),
            ("4. Temporal validity", [
                "Pipeline order: `Applications.Applied On` ≤ `Applications.Screened On` ≤ "
                "`Applications.First Interview On` ≤ `Applications.Final Interview On` ≤ "
                "`Applications.Offered On` ≤ `Applications.Closed On`.",
                "Offer order: `Offers.Offered On` ≤ `Offers.Decision On` ≤ `Offers.Proposed Start Date`.",
                "`Candidates.Created On` vs the candidate's first `Applications.Applied On`.",
                "`Applications.Applied On` inside the opening's `Job Openings.Opened On` … `Job Openings.Target Close`.",
                "`Interviews.Completed On` vs `Interviews.Scheduled On`. Dates after the snapshot date.",
                "`Candidates.createdTime` is the same day for every table (a bulk load), so there is no "
                "audit trail of when events were actually recorded.",
            ]),
            ("5. Validity and ranges", [
                "`Interviews.Score`: the scale and whether decimals are expected.",
                "`Candidates.Current CTC` vs `Candidates.Expected CTC`. `Offers.Base CTC` vs "
                "`Job Openings.Salary Band Min` / `Job Openings.Salary Band Max`.",
                "`Candidates.Years Experience`, `Candidates.Notice Period Days`, `Offers.Joining Bonus`: "
                "plausible ranges and units.",
            ]),
            ("6. Referential integrity", [
                "Section 2 shows every link resolves, with no reciprocal mismatches in this snapshot. "
                "Any integrity problems will therefore be semantic (wrong link), not structural "
                "(broken link).",
            ]),
            ("7. Coverage and sample size", [
                "Small tables limit confidence: `Offers.id`, `Job Openings.id` and the People who act as "
                "recruiters or interviewers. Report uncertainty, not just point values.",
                "The Findings table returned zero records.",
            ]),
        ],
    },
]
