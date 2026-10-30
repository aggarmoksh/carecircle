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

## Pitfalls
- AI-generated organiser images are for wiring only; never present them as real photos in the demo or submission.
