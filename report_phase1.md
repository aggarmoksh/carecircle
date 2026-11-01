# Phase 1 report: the WhatsApp side of CareCircle

Pre-registration: tests/router_labels.json and tests/guard_blocklist.txt committed before any router code, in commit `7deed703c153021c804f88852ae2abef697a8c4c` (router_labels.json sha256 `50afd7b3ac73c1ffd2259c03be7ba264403fced73858773c5071a52da948eeb1`). Both files are unchanged since (git diff against that commit is empty). labels.json (Phase 0) is unchanged: sha256 `f99dca3478e22b50124e083fb6bd0aa71ccb45aabc026018493d8b499f3d6e8c`.
Phase 0 final state is tagged `phase0-final` (166e382). Phase 1 code commit: f2959e5, plus the commit holding this report.

## Acceptance
| Check | Threshold | Result | Status |
|---|---|---|---|
| Router type on Phase 0 inputs (3 sheets, 4 organiser images, 12 voice notes) | 19/19 | 19/19 (images typed correctly; 12 voice notes routed audio -> dose_update) | PASS |
| Medical questions get the fixed reply (Q6 and Q10 the urgent one) | 10/10 | 10/10 (8 fixed medical replies, Q6 and Q10 urgent reply; intent labels all matched) | PASS |
| Medicine names or doses outside the record in any outbound | 0 | 0 in 26 scanned outbound texts (live DB 8, replay DB 8, record-question answers 8, plus both fixed replies); 0 guard blocks fired | PASS (see limits) |
| Record questions | >= 7/8 | 8/8 on the final prompt (two runs: 8/8 and 8/8). Earlier runs on the first prompt: 6/8, 4/8, 7/8. | PASS (see variance) |
| Escalation unit tests: confirmed in time, missed, late reply, sleeper skipped, everyone asleep | pass | 6 tests pass (these five plus a closed-window skip) | PASS |
| Offline end-to-end replay (d1 image, YES, v01, o3; no real sends) | expected log incl. "TUE_PM full, no confirmation" | all 5 checks pass; audit shows "TUE_PM full, no confirmation was logged"; 14 SAM masks on o3 and the overlay stored | PASS |
| One live run on real phones (d1 photo from r2, YES from r2, relay on r1 and r3) | relay arrives on r1 and r3 | d1 photo -> 4-line draft summary on r2; YES -> schedule live; relay delivered to r1 immediately; r3 (London 01:40, asleep) was queued, then delivered after the clock was set to a London morning | PASS (with the queue step, see notes) |
| Outbound cap | <= 40 for the phase | 6 real messages sent | PASS |

## Numbers
- Real WhatsApp outbound messages in Phase 1: **6** (2 help replies, draft summary, YES reply, relay to r1, queued relay to r3). Simulated members' messages are logged in outputs/sim_inbox.jsonl and not counted.
- Model spend: **$0.4014** for Phase 1 (156 calls); total across the project $0.5279 of the $5.00 cap.
- Tests: **13 unit tests** pass (6 escalation, 7 guard/relay/outbox/clock), plus 3 live eval scripts (tests/eval_router.py parts A, B, C), the replay (tests/replay.py) and the outbound scan (tests/scan_outbound.py).
- Redaction grep over 146 text files plus both SQLite files: 0 hits for the Twilio SID, auth token, model key prefix, admin token, and all three phone numbers (digits and E.164). No env, media, .mcp.json or database file is tracked.

## Built (new in app/, tests/)
app/db.py (SQLite schema: circle, members, medications, schedule_lines, dose_events, documents, rota, tasks, audit_log, queue), app/clock.py (single time source; speed control), app/record.py (schedule, events, rota, tasks, snapshot, organiser-vs-record), app/intake.py (router), app/vision.py (classify, extract with the Phase 0 P1 prompt and schema, Spark-alone organiser judging, SAM overlay stored only at exactly 14 masks), app/voice.py (ffmpeg to 16 kHz mono WAV then transcribe), app/outbox.py (guard, 24 h window, audit reason, relay, queue), app/guard.py, app/escalation.py, app/channel.py (moved from probes/channel.py and generalised: twilio sandbox, dry run, simulated, Meta stub), app/llm.py (moved from probes/common.py), app/server.py (signature-checked webhook, status callbacks, admin-only clock endpoint, scheduler), app/seed.py. Tests: router_labels.json and guard_blocklist.txt (pre-registered), helpers, test_escalation.py, test_guard_relay_clock.py, eval_router.py, replay.py, scan_outbound.py.
Moved (not copied): probes/common.py -> app/llm.py and probes/channel.py -> app/channel.py. probes/common.py is now a shim; probes/channel.py raises with a pointer, so the frozen Phase 0 channel code is only runnable from the `phase0-final` tag. The extraction, organiser and SAM prompts were re-implemented in app/vision.py with the same wording, not imported, because p1.py and p3.py run on import.

## What is code and what is the model
Spark classifies intents, parses {actor, slot, action} against the live schedule, extracts and judges images, corrects drafts and phrases record answers. Everything that changes state or sends is code: YES handling, confirmation, escalation ladder, window and waking-hour checks, relay, queue, tasks, fixed replies, and the outbound guard. The nudges, relays and fixed replies are code templates; Spark phrases only the answers to record questions.

## Variance and limits the advisor should know
- **Record questions are unstable at temperature 0.** The first prompt gave 6/8, then 4/8, then 7/8 on identical inputs. Failures were missing detail (reason for a skip, the time, a literal "yes") and one "The record doesn't say" for who is on duty tonight. After adding explicit snapshot fields (on_duty_tonight, due_later_today) and answer rules, two runs scored 8/8. That prompt change happened after results were seen; all five runs are recorded (outputs/phase1_eval_c_run*.json). Two good runs are not proof of stability.
- The record-question check is a keyword check (tests/router_labels.json must_contain_any), so a correct answer worded differently can fail, and a wrong one containing the keywords could pass.
- The name and dose scan relies on a built-in list of about 90 drug names plus the record, so an unlisted drug name would not be caught. Eval part A and B outbound texts were not saved to disk (their circles were in memory); they went through the live guard, which logged no blocks, but the scan above covers the live run, the replay and the record answers, not part A.
- **Live run used a stopped scheduler.** The server ran with CC_TICKER=0 so no unplanned real nudges could go out; escalation was verified by unit tests and, with real phones, in Phase 0 P5. The queued relay to r3 was delivered by a one-off script that set its own clock to 08:30 London and called the same flush function the scheduler calls, not by the running server. The live server's own scheduler and the admin clock endpoint were each only smoke-tested (admin endpoint: 200 with the token, 403 with a wrong or missing token, and the change is written to the audit log).
- The organiser comparison flags empty compartments with no confirmation as well as full ones, so with a sparse record (replay: only v01) it lists several empty compartments besides TUE_PM. That is by design but may be noisy.
- Draft lines with no printed clock time stay draft after YES and are never given an inferred time (checked in the code path; the live run used d1 which prints times, so this was not exercised live).
- Free-form messages to a member whose 24 h window is closed are skipped and logged ("24h window closed (template required)"); no template sends are implemented.

## Skipped
Web board UI, doctor summary, lab-report extraction (lab reports are stored only), Meta Cloud API, deployment, template sends, and a persisted record of eval A and B outbound texts.
