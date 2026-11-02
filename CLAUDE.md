# CareCircle

Family care coordination agent on WhatsApp 1:1. Coordination only: it never gives medical advice.

## Stack (locked)
Python 3.11+, OpenAI SDK pointed at the Meta base_url, ffmpeg, FastAPI later, Next.js later.

## Rules
- Standard mode only.
- Never print or log keys, tokens or phone numbers.
- Synthetic data only; no real prescriptions or health records.
- Never commit media or .env.
- Coordination, not medical advice.

## Anti-features
- No dose suggestions
- No interaction checks
- No diagnosis
- No inferred dose times
- No pharmacy or EHR integration
- No accounts
- No real patient data
- No pill counting (the claim is "compartment empty" only)
- No sends outside the WhatsApp 24-hour window except approved templates
- No interpretation of test results: no high/low/normal judgement beyond the flag printed on the report, no trends, no explanation of what a value means; a question about a result becomes a follow-up task for whoever will talk to the doctor.
- Say 'circle member', never 'sibling', in code, prompts and UI.
- Simulated members are always labelled 'simulated' on screen.

## Phase gates
Stop at every phase boundary and print the gate line.

## Phase 0 rule changes
- The labels gate exempts "notes" (may be "") and "times" (may be []); every other value outside "_" keys must be non-empty and not "?".
- P2 parses {actor, slot, action}; actor is m1..m5 or patient. The sender member id comes from the labels "sender" field, not from the phone the note arrived on (all notes arrive from r1).
- Probe order is now P1, P3, then P4 (on the channel the advisor approves), P2, P5, P6. GO/NO-GO is otherwise unchanged.
- Do not use the WhatsApp MCP in Phase 0.

## Design notes for Phase 1 (not built in Phase 0)
Members have relationship, timezone and role hands_on or remote; a member is real (a WhatsApp number) or simulated (shown on the web board only). Escalation nudges hands_on members first; remote members are messaged only in their local waking hours (08:00 to 22:00) unless the ladder reaches 'no hands_on member answered'. Test-report capture is a Phase 2 feature and needs its own probe on 2 fictional lab reports first. WhatsApp goes through a channel adapter so the provider can change.

## Decisions
2026-10-29 (updated 18:30 PT): Building CareCircle (Indie track): care coordination for everyone who cares for one person (family, friends and close relatives, nearby or in other countries and time zones) over real WhatsApp 1:1 on three real phones (r1..r3) plus simulated circle members m4 and m5 shown on a live web care board, on Muse Spark 1.3, Muse Voice Transcribe and SAM 3.1; test reports are stored, copied exactly as printed and turned into follow-up tasks, never interpreted; no more idea rounds; the Phase 0 GO/NO-GO rule decides, and any pivot waits for an advisor review of the Phase 0 report.


2026-10-30: Spark alone judges organiser compartments; SAM 3.1 runs on every organiser photo and its overlay is stored as evidence only when it returns exactly 14 masks. SAM's role is re-decided after real ice-tray photos. CareCircle is 1:1 with each member and relays updates so the circle shares one stream (no group chats on this channel). Problem statement: Build for Your World.

## Pitfalls
- AI-generated organiser images are for wiring only; never present them as real photos in the demo or submission.

## Phase 3 decisions (pre-registered rules, applied mechanically to the P3-real results)
- Organiser judge: Spark alone must read >= 13/14 labelled compartments on >= 7/8 real photos (tests/organiser_real_labels_v2.json). Result: 8/8 photos at 14/14, so Spark stays the judge. AUDIT-RED is not flagged. If this ever fails, the organiser feature makes no claims and replies "I couldn't read this photo reliably".
- SAM overlays: kept only if all 14 labelled compartments are mapped on >= 7/8 photos. Result: 2/8, so SAM overlays are dropped from the board and intake; the submission says Spark judges alone. SAM-HELPS: not flagged (SAM pipeline never beat Spark alone by 2 compartments).
- The tray has 16 compartments; the unlabelled spare row or column is never scored.
- Lab values are compared only with the range printed on the same report, by code. No words like normal, abnormal, danger, risk, good or bad anywhere in the board or the summary.
- A member who writes STOP receives nothing (relays, nudges, alerts) until they write again; the escalation ladder skips them and logs why.
- SAM (for the submission): with the text prompt "pill organizer compartment", SAM 3.1 mapped all 14 compartments on 3 of 4 AI-generated photos but on only 2 of 8 real ice-tray photos (one mask on 6 of them). The product does not call SAM; the submission says Spark judges alone.
- Missed dose: after due + grace a dose shows "overdue, escalating"; it becomes "missed" when its escalation ladder is exhausted or when the next dose of the same medicine falls due, whichever comes first.
- Units are kept as printed and never converted (tsf, tbsp, sachet; anything else is "other" with the printed unit). Found on P8 doc 1: "2 TSF" was read as "2.0 mL".
- Handwriting rule: the classifier sets has_handwriting; on a handwritten document every medicine line is marked unsure whatever the per-line legibility, so a member confirms each name before YES.
