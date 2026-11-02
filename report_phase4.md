# Phase 4 report

Scope: correctness fixes, board and doctor-summary redesign per docs/DESIGN.md, the Thursday demo scene, and replies in the member's language (item 8, done because 1-7 passed). Synthetic data only. No remote, no push.

## Acceptance
| Check | Result |
|---|---|
| Lab status test, every row | pass: tests/test_phase4.py renders every lab row in the DB (including a deliberately stale stored status) and asserts status == compute(value, printed range) |
| 09-29 source explained | yes, see below |
| Dose state test at a fixed clock | pass: inside grace "due"; past due + grace "overdue" (board shows "overdue, escalating" with its open ladder); "missed" when the ladder is exhausted or the next dose of the same medicine falls due |
| Board screenshot at a past-due time shows no "due, not confirmed" | yes: board_p4_1440x900.png / board_p4_full.png at Thu 08:31, three doses "overdue, escalating" |
| Guard task-name test | pass: the Phase 3 live-run case (medical question, then "I will") now sends the real task sentence to the creator and the relays; the fallback sentence still applies to a free-text mention and to a different dose in the same message |
| Router eval 19/19 in 3 runs | 19/19, 19/19, 19/19 (B 10/10, C 8/8 each); see history below |
| Earlier tests pass | 63 passed (51 earlier + 12 new) |
| Screenshots and summary PDF follow DESIGN.md | yes, deviations listed below |
| Demo scene offline test | pass |
| Outbound scan | 65 saved texts scanned (4 databases, eval answers, 3 router runs' record answers): 0 medicine names, doses or lab values outside the record; 3 guard blocks logged (earlier phases) |
| Item 8, Hindi | 10 of 10 replies localised, 0 guard failures, 0 names or numbers changed (outputs/p4_hindi.json) |

## 1. The 2026-09-29 report
It was my own screenshot fixture, not product data. tools/make_shots_db.py (Phase 3) loaded fixture L2 from tests/lab_labels.json as an "earlier report", then edited the stored values with SQL (creatinine to 1.2, sodium to 137, and so on) without recomputing the stored `status` column, so the screenshot showed the L2 statuses (above, below) next to the new values. Two causes: a status that was stored instead of computed, and a fixture edited behind the code's back. Fixes: `labs.report()` now recomputes the parsed range and the status from value and printed range text on every read, so nothing stored is ever shown; reports loaded from fixtures carry `origin = "demo seed (fictional)"`, shown under the report header on the board and in the summary. No real data was involved.

## 2-5 Other fixes
- Dose state: `status_of` returns "overdue" once past due + grace; the board label is "overdue, escalating"; "due, not confirmed" only appears inside the grace period. Escalation skip lines are logged once per member and dose (the time of day in "asleep (local ...)" no longer creates a new line every minute).
- Guard: a task created from a member's own message (source "medical question" or "correction") may be named in a message that carries that task's text. Nothing else changes.
- Router: a message that reports a past action ("took", "gave", "de di", "le li", and the Devanagari and Gurmukhi forms) with no question mark is routed as a dose report when the model said record_question or other (logged as intent_override). History: with the first version of the rule (record_question only) one run missed voice v11 (a Punjabi clip the model called "other"); I extended the rule to "other" and to the Gurmukhi wording, checked offline that every "given" transcript from the saved Phase 2 run matches, then ran three fresh runs: 19/19 each. Earlier same-day runs of 18/19 (v05, then v11) are in outputs/phase4_router_*.txt and phase4b_router_*.txt (run 3 of that batch was cut off by the spend cap).
- Default relay choice: remote members "alerts and a daily summary", hands_on members "everything" (seed and demo reset). Legacy tests set everyone to "everything" in the test helper and one test asserts the role defaults.

## 6. Redesign (docs/DESIGN.md)
One HTML page (app/board.html), no new server, no JS framework, Inter from Google Fonts. The Circle (SVG ring, patient at the centre, nearby members inner ring, remote members outer ring, sun or moon, simulated members dashed with a "sim" tag, greyed STOP members, an arc to the member being nudged that animates once over 600 ms, none with prefers-reduced-motion); Now card with headline and ladder timeline; Today 24-hour line with now marker; lab rows with 220 px range bars, sparklines, collapsed within-range rows and a report switcher; organiser photo with 7 x 2 grid (mismatches outlined); tasks; "who gets which updates"; Activity as plain sentences with icons and a details toggle; footer; demo controls in a collapsed section; the demo-clock badge shows only once an admin token is typed. Phone layout: Now first, the circle as chips, Today scrolls sideways. Every earlier data feature is kept.
Doctor summary: one page (verified 1 page, A4), black and white safe, adherence bars, missed doses with reasons, lab bars in greyscale, questions for the doctor, footer.

Screenshots (outputs/): board_p4_1440x900.png (top of page), board_p4_full.png (full page, 1440 wide), board_p4_390x844.png (phone), summary_p4.pdf (one page), summary_p4_preview.png (the same page as an image). They were taken from the synthetic data/shots.db (tools/make_shots_db.py, tools/shots.sh).

Deviations from DESIGN.md, and why:
- Summary shows the newest lab report only, without trend sparklines (the other reports appear on the board). One page was the stricter rule; trends need width the printed page does not have.
- Phone screenshot is taken in a 390 px iframe and cropped: headless Chrome will not make a window narrower than about 500 px.
- The Circle's label spacing is tuned for five members; a larger circle would need a different layout.
- Sun and moon icons are neutral grey, not amber, because amber is reserved for "outside the printed range" and overdue.
- The "Doctor summary" button is a link on the board, and the summary page has a Print button that is hidden when printing.
- Not visually checked: Safari, a real phone, and the summary in Letter size (the page uses A4 margins; content fits well inside Letter height).

## 7. Demo scene
`python tools/demo_reset.py --scene thursday`: d1 confirmed by Meena on Monday; Monday, Tuesday and Wednesday 08:00 doses confirmed by various members; Wednesday 20:00 doses never confirmed (recorded as "missed", so the live ticker does not start nudging on Thursday morning); lab report L2 confirmed by Kabir (marked demo seed); patient clock Thursday 07:55. Sending media/organiser_real/or1.jpeg from r2 produces "Wednesday PM is still full in the organiser: that dose wasn't given." (design-file wording; no medical advice) and an organiser_disagreement audit line. The offline test stubs the two model calls (photo type, compartment states from the advisor's reading of or1) and asserts the exact reply, the log line, the board mismatch and the guard. The real-photo read of or1 is the Phase 3 result (14/14).

## 8. Replies in the member's language
members.language (m2 = hi, others en). The reply is written in English by code; Spark rewrites it in Hindi (Devanagari); code checks that every number and every medicine name is present unchanged in Latin letters and digits, rejects Devanagari digits, and runs the guard on the result; any failure sends the English text and logs `lang_fallback`. 10 real replies (nudge, dose logged, relay, organiser, schedule started, record answer, missed, lab saved, lab relay, medical fixed reply): 10 localised, 0 fell back, 0 guard failures, 0 changed names or numbers. The check covers medicine names and numbers only; I did not have the Hindi read by a person, so the quality of the Hindi is unchecked.

## Spend and cap
The $5 cap was reached during the router runs (run 3 of the first batch was cut off); you approved raising it to $7 and CAP in app/llm.py is now 7.00. Logged total across all phases: $5.73, up from $3.03 at the Phase 3 report, so about $2.70 since then (Phase 3 round 2 and Phase 4; the router eval batches were most of it).

## Skipped or not done
- Phase 2 live evals (original, held-out, medical) were not re-run this phase; only the router eval (A, B, C) was, three times.
- No live WhatsApp run this phase (outbound cap untouched).
- Private labels and images were not used.

## Commits
Listed in git log: the DESIGN.md commit, then the Phase 4 commit and this report.
