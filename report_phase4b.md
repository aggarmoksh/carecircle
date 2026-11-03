# Phase 4b report

Scope: board started for the user, lighter messages, deduplicated activity feed, P9 medicine-name check (time-boxed), Sofía in Madrid with Spanish replies. Synthetic data only. No remote, no push.

## Acceptance
| Check | Result |
|---|---|
| Tests for items 1, 2 and 4 | pass: tests/test_phase4b.py (7 tests): one nudge and one escalation step per dose time; one missed alert for doses that went missed together; "done" confirms all and relays once; a partial reply confirms only the named medicines; single medicine keeps the short wording; activity feed (each step logged once, "x3", newest 15 with "Show all"); Sofía's seed, her relay in Spanish, the Activity line with the text behind "details", and the English fallback when a Spanish text changes a number |
| All earlier tests pass | 70 passed (63 earlier + 7 new) |
| P9 | FAILED the pass bar: 10 of 17 real names found with a valid source (need 15); 0 of 5 fakes found; 0 of 2 wrong strengths found. Step 3e (draft-summary line) was NOT built, as the brief says |
| New screenshots 1440x900 and full page | outputs/board_p4b_1440x900.png, outputs/board_p4b_full.png (also board_p4b_390x844.png and summary_p4b.pdf) |
| Outbound scan | 60 saved texts: 0 medicine names, doses or lab values outside the record; 3 guard blocks logged (earlier phases) |
| Spanish, 10 real replies | 10 localised, 0 guard failures, 0 names or numbers changed (outputs/p4b_es.json) |

## 0. Board
Started in the Thursday scene on its own database (data/thursday.db), port 8000, in dry-run (nothing goes to WhatsApp). Board: http://127.0.0.1:8000/board?token=<BOARD_TOKEN>. Doctor summary: http://127.0.0.1:8000/doctor?token=<BOARD_TOKEN>&from=2026-11-02&to=2026-11-05. Stop: end the process listening on port 8000 (taskkill /PID <pid> /F, the pid is shown by netstat -ano | findstr :8000).

## 1. Lighter messages
Open doses are grouped by due date and time. The ladder sends one message per person per dose time: "Hi Meena, has Nanaji had his 8 AM medicines: amlodipine, aspirin, metformin? Reply done, or tell me which ones." The later steps ask the next member the same way. "done" confirms every medicine of that time; a reply that names medicines confirms only those (code matches the names in the text; the model still picks the member and the action). The confirmation reply, the relay to the circle and the missed alert are one message each. One medicine keeps the old short wording. When two dose times are waiting and the reply names none, it asks which time.

## 2. Activity feed
Each ladder step is logged once (skips were already once per member; nudges are now once per group). Repeats of the same sentence in the same minute show as "x3". The page shows the newest 15 with "Show all N".

## 3. P9 medicine-name check
a. dev.meta.ai docs: web search exists (web_search tool, Responses API only, $2.50 per 1,000 searches). Used with strict json_schema output, which the docs do not describe but which worked.
b. tests/p9_labels.json committed (cedae34) before any search.
c. Spark returns {found, product, strength_found, source_url}; code fetches the URL and counts it only if the domain is on the list, the page loads and it contains the name (and the strength when one was asked). Only names and strengths were sent. One run, no prompt changes. Reasoning effort low, at most 2 searches per name.
d. Result: FAIL, 10 of 17. Spend for the run $0.41 (limit $1.00).

| Name | Expected | Result | Source domain | Note |
|---|---|---|---|---|
| metformin 500 mg | found | found | www.drugs.com | ok |
| amlodipine 5 mg | found | found | www.drugs.com | ok |
| atorvastatin 20 mg | found | found | www.drugs.com | ok |
| levothyroxine 50 mcg | found | found | www.drugs.com | ok |
| insulin glargine 100 units/mL | found | found | www.drugs.com | ok |
| Lipitor 20 mg | found | found | dailymed.nlm.nih.gov | ok |
| Glucophage 500 mg | found | not found | - | page does not contain the name |
| Tylenol 500 mg | found | not found | - | model: not found |
| Nurofen 200 mg | found | found | www.medicines.org.uk | ok |
| Pantop 40 mg | found | found | www.1mg.com | ok |
| Dolo 650 mg | found | not found | - | page did not load (HTTP 404) |
| Azee 250 mg | found | not found | - | page did not load (HTTP 404) |
| Econorm 250 mg | found | found | www.1mg.com | ok |
| Swich 200 mg | found | not found | - | page did not load (HTTP 404) |
| Pan-D | found | found | www.1mg.com | ok |
| Sporolac DS | found | not found | - | model: not found |
| Emeset 4 mg | found | not found | - | page did not load (HTTP 404) |
| Surich 200 mg | not found | not found | - | model: not found |
| Zeprovan 250 mg | not found | not found | - | model: not found |
| Lomaxitrine 40 mg | not found | not found | - | model: not found |
| Cardivexol 10 mg | not found | not found | - | model: not found |
| Astro Vista 20 mg | not found | not found | - | model: not found |
| Dolo 6500 mg | strength not found | not found | - | model: not found |
| Pantop 400 mg | strength not found | not found | - | model: not found |
What went wrong: 4 of the 7 misses were pages the model cited that returned HTTP 404 (Dolo, Azee, Swich, Emeset; the real listings may exist under other addresses), 1 page did not contain the name (Glucophage), 2 names were not found (Tylenol, Sporolac DS). The errors went the safe way: no fake and no wrong strength was accepted. Not built: the per-line "found in public medicine listings" text in the draft summary. Not retried, per the one-run rule.

## 4. Sofía
Ravi (Dubai) is now Sofía, family friend (simulated), Madrid, remote, language es, default "alerts and a daily summary" (seed, demo reset, tests, screenshots). Her messages are written in English by code and rewritten in Spanish by Spark under the same check as Hindi: every number and medicine name unchanged, guard again, English if anything fails. The Activity feed reads "CareCircle messaged Sofía in Spanish" with the Spanish text and the English original behind "details".
Hindi feedback applied (your note on the Hindi file): times now come with the Hindi time word ("सुबह 8 बजे") and a medicine name may be followed by "दवा". Re-run of the 10 Hindi replies: 10 of 10 localised, 0 guard failures. Remaining oddities I saw: "शाम 20:00 बजे" mixes the 24-hour clock with a time word (the nudge uses "8 PM" so the nudge reads right); Spanish drops accents on "Sofia" in one reply and "tomo" in another. Neither is covered by the check. Nobody has read the Spanish.

## Spend
Logged total $6.29 (was $5.73 at the Phase 4 report): P9 about $0.41, the two 10-reply language runs and a smoke call the rest. Cap is $8.00.

## Skipped or not done
- P9 step 3e (not built because P9 failed).
- No live WhatsApp run; the Thursday server is dry-run.
- Phase 2 live evals and the router eval were not re-run (no change to the router or parser prompts; the dose handler changed in code only).
- Spanish not read by a person; Safari and a real phone not checked.

## Commits
See git log: 5c7d2aa (grouping, feed), cedae34 (P9 labels, cap), and the Phase 4b commit that adds the rest and this report.
