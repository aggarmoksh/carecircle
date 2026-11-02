# Phase 3 report (final)

Status: all items done, including the live run (second round of advisor decisions applied: units, handwriting rule, missed-dose rule, P8 rescore, SAM note).

## Pre-registration (hashes, first 16 hex)
| File | Commit | sha256 |
|---|---|---|
| tests/organiser_real_labels.json (plan record, kept) | d60ea78 | c3e63f74f697e2a4 |
| tests/paper_labels.json | d60ea78 | ef64846aad4bd55a |
| tests/organiser_real_labels_v2.json (advisor reading of the 8 photos, user-approved) | e8348a1 | c2bc8e10e602a50e |
| [a local folder] (private, never opened by me) | not in repo | de42e64512cbaca6 |
| [a local folder] (private, never opened by me) | not in repo | 3cdcdd06bc97b93c |

Deviation log: the photos in media/organiser_real are or1..or8, not the r1..r5 plan. The advisor's reading (v2) replaced the plan; v1 stays as the plan record. v2 was committed alone before any P3-real run. Scoring of private documents was changed to names only before any run.

## Acceptance
| Check | Result |
|---|---|
| P3-real | Spark alone >= 13/14 on 8/8 photos: Spark stays the judge, AUDIT-RED not flagged. SAM mapped all 14 labelled compartments on 2/8 (rule needs 7/8): overlays dropped, "Spark judges alone". SAM-HELPS: no photo |
| P8-private | MISS on the printed-doc target: doc 1 has 2 confidently wrong lines (need 0). Doc 3: 0. Handwritten docs 2 and 4: 0 confidently wrong in total (need <= 1). Counts below |
| P1-paper | SKIPPED (media/paper is empty; advisor said skip) |
| Phase 1 router eval | 19/19 (types), medical 10/10, record 8/8 (outputs/phase3_router.json) |
| Phase 2 evals, one run | original 8/8, held-out 8/8, medical 12/12, 0 guard blocks (outputs/phase2_eval_runp3.json; texts in outputs/phase2_texts_runp3.jsonl) |
| P1-screen with the new schema | 78/78 fields (d1 24/24, d2 30/30, d3 24/24), same as Phase 1; no invented or dropped medicines; no unsure lines |
| Unit and escalation tests | 51 passed (27 old + 24 new; one old assertion changed, see caveats) |
| Lab graphics | screenshots below |
| Relay choice | unit tests for everything, duties, daily and stop (each through the router), stop skipped in the ladder with the reason logged, urgent alert skipped for STOP, writing again ends STOP, board shows each choice |
| Missed dose | tests plus screenshots: past doses show "missed" on the board and in the summary after a scheduler run; the board ladder shows only today's open doses |
| Live run | DONE: r2 sent "only my duties and alerts" (relay_pref duties); r3 asked a medical question (saved as a task, fixed reply), then "I will": the task-owner relay to r2 was NOT sent and is logged as relay_suppressed ("member chose only duties and alerts; relay not sent"). m1 got it queued (asleep), m4/m5 are simulated |
| Outbound count (live) | 4 of cap 40 real WhatsApp sends (data/outbound_phase3.json) |
| Unit preservation test | pass (2 TSF stays tsf; unknown unit kept via unit_as_printed) |
| Handwriting rule test | pass (every line unsure on a handwritten sheet; YES blocked until each name is retyped) |
| Missed-dose rule | pass: "overdue, escalating" after grace; missed when the ladder is exhausted or the next dose of the same medicine falls due (test_escalation unchanged) |
| P1-screen after unit/handwriting change | 78/78 |
| Router eval after classify change | run 1: 18/19 (voice v05 routed record_question instead of dose_update, no code on that path touched), run 2: 19/19; medical 10/10, record 8/8 both runs |
| Unit tests | 55 passed |

## P3-real (8 photos, tests/organiser_real_labels_v2.json, 14 labelled compartments each)
| Photo | Spark alone | SAM masks | All 14 mapped | SAM pipeline | Pipeline minus alone |
|---|---|---|---|---|---|
| or1 | 14/14 | 1 | no | 0/14 | -14 |
| or2 | 14/14 | 1 | no | 0/14 | -14 |
| or3 | 14/14 | 1 | no | 0/14 | -14 |
| or4 | 14/14 | 16 | yes | 14/14 | 0 |
| or5 | 14/14 | 16 | yes | 14/14 | 0 |
| or6 | 14/14 | 1 | no | 0/14 | -14 |
| or7 | 14/14 | 1 | no | 0/14 | -14 |
| or8 | 14/14 | 1 | no | 0/14 | -14 |

Spark alone: 8/8 photos at 14/14, 0 wrong compartments in total. SAM returned a single mask on six photos and 16 masks (the whole tray) on or4 and or5; only those two mapped. Rule results: Spark stays judge; SAM overlays dropped; SAM-HELPS not flagged. The product no longer calls SAM and the board shows the photo only. The rules are recorded in CLAUDE.md.

## P8-private (names only; counts only; file contents never printed or copied)
Scoring tool: tools/doc_score.py. Rule fixed before any run: normalised match, or a contains-match of 4+ letters; a clear unmatched line close to a label name (difflib ratio >= 0.6) is confidently wrong, otherwise invented. Extractions are in [a local folder]<n>.json and the counts in [a local folder], both outside the repo.

| Doc | Kind | Label medicines | Extracted lines | Found | Unsure-flagged | Dropped | Confidently wrong | Invented | Unsure unmatched lines |
|---|---|---|---|---|---|---|---|---|---|
| 1 | printed | 7 | 7 | 5 | 0 | 2 | 2 | 0 | 0 |
| 2 | handwritten | 1 | 3 | 0 | 0 | 1 | 0 | 1 | 2 |
| 3 | printed | 8 | 8 | 8 | 0 | 0 | 0 | 0 | 0 |
| 4 | handwritten | 3 | 2 | 0 | 0 | 3 | 0 | 0 | 2 |

Target: printed docs (1, 3) 0 confidently wrong. Doc 1 has 2, so this is a miss. Cause found: doc 1's "2 TSF" dose was extracted as 2.0 mL because the unit enum had no teaspoon (fixed, see below).

### Rescore with the advisor's post-hoc corrected labels (saved extractions, no new API calls)
The corrected file fixes clerical errors: the labels of docs 2 and 4 had been swapped, two spelling typos on doc 1, and one medicine missing from doc 4's labels. Pre-registered score is the result above; the corrected score is a post-hoc reading and is reported alongside it, not instead of it.
| Doc | Scoring | Label medicines | Found | Unsure-flagged | Dropped | Confidently wrong | Invented |
|---|---|---|---|---|---|---|---|
| 1 | pre-registered | 7 | 5 | 0 | 2 | 2 | 0 |
| 1 | corrected | 7 | 7 | 0 | 0 | 0 | 0 |
| 2 | pre-registered | 1 | 0 | 0 | 1 | 0 | 1 |
| 2 | corrected | 3 | 0 | 1 | 2 | 1 | 0 |
| 3 | pre-registered | 8 | 8 | 0 | 0 | 0 | 0 |
| 3 | corrected | 8 | 8 | 0 | 0 | 0 | 0 |
| 4 | pre-registered | 3 | 0 | 0 | 3 | 0 | 0 |
| 4 | corrected | 2 | 0 | 1 | 1 | 0 | 0 |
Corrected: printed docs 0 confidently wrong (target met); handwritten docs 1 in total (target <= 1, met). That one line was returned as clear on a handwritten sheet; under the new handwriting rule it would be shown as "?". Extraction was not re-run, so that rule is covered by a unit test, not by a new P8 run. Handwritten docs (2, 4) <= 1 in total: 0, met. No prompt change was made after seeing results. Worth knowing: on the handwritten docs the model marked 4 lines unsure (they would show with "?" and need a retyped name) but none matched a label name; doc 2 has one clear line that matches no label (counted as invented, which is outside the stated target); doc 4 dropped all 3 label medicines.

## Lab graphics
Board lab section: outputs/board_labs_p3.png (full board: outputs/board_p3_full.png). Doctor summary page: outputs/summary_p3.png. Per test: the printed range as a band; a value marker (triangle up = above, triangle down = below, circle = within); status in words and a shape; one-sided ranges open-ended with an arrow; no bar when no range is printed; out-of-range tests first under "N of M outside the lab's printed range"; a trend with the printed band when a test is in two or more reports. A test scans the board, the summary and board.html for normal, abnormal, danger, risk, good and bad (none found). The screenshots use a synthetic demo DB (tools/make_shots_db.py) with an invented earlier report so a trend shows.

## What changed (short)
- Extraction: name_as_printed, generic_if_printed, legibility (clear or unsure). Unsure lines show "?" in the draft; YES is refused until each "?" line is retyped or removed.
- Relay choice: everything / only my duties and alerts / daily summary at 8 PM / stop. STOP silences everything (relays, nudges, alerts) until the member writes again; the ladder skips them and logs why. Daily batches relays into one 8 PM summary; nudges, urgent alerts and missed-dose notices still reach "duties" and "daily" members.
- Missed dose: when the scheduler runs, any unconfirmed dose more than 12 hours past due becomes "missed" (event plus audit line; no messages for the catch-up). The live ladder still handles today and yesterday first. I read "past due plus grace" as "after the ladder had its chance", because marking missed at due plus grace would remove the nudges the Phase 1 escalation tests require. Say if you want it earlier.
- Demo reset: tools/demo_reset.py (fictional seed, schedule not confirmed, clock target 07:55 patient-local, every choice "everything", prints /board?token=<BOARD_TOKEN>). Run on a fresh database for the live DB. A running server's clock is moved through the admin endpoint if ADMIN_TOKEN is set; otherwise start the server with the printed CC_START_TIME.

## Round 2 changes (advisor, 2026-11-01 21:55 PT)
- Units kept as printed, never converted: enum adds tsf, tbsp, sachet, other (+ unit_as_printed). The guard also recognises tsf and tbsp.
- Handwriting: classifier returns has_handwriting; on a handwritten sheet every line is unsure, so a member retypes each name before YES.
- Missed dose: replaces my earlier 12-hour reading (the 12 h constant is removed). Board label for the stage between grace and missed: "overdue, escalating".
- SAM note recorded in CLAUDE.md and FRICTION_LOG.md (3 of 4 AI photos, 2 of 8 real photos).

## Caveats and skipped
- Live run note: r3's task-owner confirmation and the m4/m5 copies were replaced by the guard's fallback sentence, because the fresh demo record has no confirmed schedule and "metformin" is therefore not an allowed name. The guard worked as designed; r2's suppression was logged before that.
- P1-paper skipped (advisor).
- One Phase 2 assertion changed: test_board_state_and_charts used the old lab_charts field, which the server-built graphics replace.
- The outbound scan (own regexes) over every saved text, including this phase's eval run, found 0 medicine names, doses or lab values outside the record.
- Private extraction spend (4 calls) is not logged in the repo. Logged spend this phase is about $0.91; total across phases about $3.03.
- The product extraction prompt still says "fictional discharge sheet"; I left it unchanged for the P8 run.
- The SAM overlay code remains in app/vision.py but is no longer called.

## Commits
d60ea78 (organiser_real and paper labels), e8348a1 (organiser_real_labels_v2), 5a902f8 (backend), 83c9f7c (P3-real decision, tools), 489ba50 (report), ec1fd8f (round 2 fixes), final report commit follows.
