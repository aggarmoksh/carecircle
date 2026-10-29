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

## Phase gates
Stop at every phase boundary and print the gate line.

## Decisions
<!-- PENDING: paste the text of [a local folder] here (not read by the agent). -->

## Pitfalls
