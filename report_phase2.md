# Phase 2 report

## Acceptance
| Check | Result |
|---|---|
| P7 lab extraction | PASS: 54/54 fields, 0 wrong statuses, 0 invented ranges, 0 invented/dropped tests |
| Held-out record questions, 3 runs | PASS: 8/8, 8/8, 8/8 (see caveat) |
| Original 8 record questions, 3 runs | PASS: 8/8, 8/8, 8/8 |
| Medical questions 1-12, 3 runs | PASS: 12/12 each, fixed reply, Q6 and Q10 urgent |
| Medicine names/doses/lab values outside record in outbound | PASS: 0 / 0 / 0 across 280 saved texts (own scan, tests/scan_outbound_p2.py, includes live DB); 0 guard blocks in the final runs |
| Phase 1 router eval | PASS: 19/19 (outputs/phase2_router_rerun.json); escalation tests pass |
| Unit tests | 27 passed |
| Board token / admin token | PASS: board 403 without BOARD_TOKEN, loads with it; /admin/clock 403 without ADMIN_TOKEN (tests) |
| Offline replay (d1, YES, v01, o3, L2, YES) | PASS: all checks; board JSON shows schedule, TUE_PM mismatch, 4 out-of-range values |
| One live run on real phones | PASS (below) |

## P7 table (extracted vs label; fields = value, unit, range)
| Report | Test | Extracted | Printed range | Status (code) | Label status | Fields ok |
|---|---|---|---|---|---|---|
| L1 | haemoglobin | 11.8 g/dL | 13.0 - 17.0 | below | below | 3/3 |
| L1 | total wbc count | 7200 /cumm | 4,000 - 11,000 | within | within | 3/3 |
| L1 | platelet count | 1.9 lakh/cumm | 1.5 - 4.5 | within | within | 3/3 |
| L1 | hba1c | 8.2 % | 4.0 - 5.6 | above | above | 3/3 |
| L1 | fasting blood sugar | 152 mg/dL | 70 - 100 | above | above | 3/3 |
| L1 | total cholesterol | 186 mg/dL | < 200 | within | within | 3/3 |
| L1 | ldl cholesterol | 112 mg/dL | < 100 | above | above | 3/3 |
| L1 | hdl cholesterol | 38 mg/dL | > 40 | below | below | 3/3 |
| L1 | triglycerides | 150 mg/dL | < 150 | above | above | 3/3 |
| L2 | serum creatinine | 1.4 mg/dL | 0.7 - 1.3 | above | above | 3/3 |
| L2 | blood urea | 38 mg/dL | 15 - 40 | within | within | 3/3 |
| L2 | egfr | 48 mL/min/1.73m2 | > 60 | below | below | 3/3 |
| L2 | sodium | 134 mmol/L | 135 - 145 | below | below | 3/3 |
| L2 | potassium | 5 mmol/L | 3.5 - 5.0 | within | within | 3/3 |
| L2 | tsh | 6.8 uIU/mL | 0.4 - 4.0 | above | above | 3/3 |
| L2 | free t4 | 1.1 ng/dL | 0.8 - 1.8 | within | within | 3/3 |
| L2 | alt | 32 U/L | 7 - 56 | within | within | 3/3 |
| L2 | vitamin d | 18 ng/mL | (none) | no_range | no_range | 3/3 |

Dates and lab name matched on both reports (L1 25 Oct, L2 29 Oct).

## Record questions, 3 runs x 2 sets
| Run | Original 8 | Held-out 8 |
|---|---|---|
| 1 | 8/8 | 8/8 |
| 2 | 8/8 | 8/8 |
| 3 | 8/8 | 8/8 |

Held-out history: pre-fix 5/8; after fix attempt 1: 6, 7, 7; after fix attempt 2: 8, 8, 8. Both allowed attempts are used. Fixes were made after seeing results (printed-range precision, query mapping for "in range" questions, who_gave attribution); labels were never changed. Keyword checks are loose.

## Live run (real phones, 1 Nov 09:08-09:10 UTC, fresh DB data/live2.db)
- r1, r2 "hi": help text each (windows open).
- r3 L2 photo: classified lab_report (0.99), 9 values, 4 outside range, draft reply sent; nothing live.
- r3 YES: lab report live, doctor task added, relay sent to r2 (delivered) and to simulated m4, m5.
- r1 (Arjun, LA): relay was **queued, not delivered**, because it was night in LA (awake window 08:00-22:00 local). This is the designed behaviour, but it means the brief's "relay on r1 and r2" was met for r2 only; r1 will get it when it wakes.
- Real outbound this phase: 5 of cap 40. 0 guard blocks.

## Numbers
- Outbound count: 5 real (cap 40); eval/replay outbounds are dry-run captures.
- Spend: Phase 2 about $0.85 logged in outputs/spend.json (total all phases $2.13). Private extraction tool spend (about $0.013) is not logged in the repo.
- Tests: 27 passing (14 new).
- Commits: lab_labels f72f48e; phase2_labels bf87592; Phase 2 code 6e0a900; report commit follows.
- Board screenshot: outputs/board_screenshot.png. Doctor summary: outputs/doctor_summary.pdf. Eval texts: outputs/phase2_texts_*.jsonl.

## Caveats and findings
- The pre-registered guard blocklist pattern `diagnos\w*` matches the lab name "Sunrise Diagnostics", so the lab name is left out of outbound texts. Blocklist unchanged.
- Values print as "5" not "5.0" (stored as float).
- Board ladder shows many unconfirmed past occurrences in the demo because the replay had no scheduler.
- The v01 voice transcript varies between runs; the replay calls ensure_due_events to keep it deterministic.
- Lab images were copied from media/discharge to media/labs. Screenshots/PDF are untracked (outputs/ is gitignored).
- Informational scan: the number 1.73 (part of the unit mL/min/1.73m2) appears in answers; not a violation.

## Skipped
Nothing from the brief. Out-of-scope items (vitals, trends, Meta Cloud API, deployment, Phase 3 reruns) not touched.
