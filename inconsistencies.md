# Inconsistencies (logged, not fixed)

- Brief names media/discharge/d1.jpg..d3.jpg; the files are d1.jpeg..d3.jpeg. Runner globs by stem.
- Docs say SAM image responses carry no usage field; the response has usage.images_processed (1 per image) and input_tokens 0. Cost computed per image at $2.50/1,000.
- Docs do not specify the one_bit mask byte format (base85 variant, leading "!!!!"); decoded with meta_sam_parser (PyPI, named by the docs).
- Docs do not mention temperature for muse-spark-1.3; temperature=0 was accepted without error.
- Docs describe Standard vs Contributor as model ids; there is no separate "mode" request parameter. Only muse-spark-1.3, sam-3.1 used.
- Pricing page matches the brief on all three figures; no price difference to log.
- labels.DRAFT.json (advisor) listed paracetamol with handwriting as d3's fourth med; labels.json has ibuprofen, TDS, no handwriting. labels.json is the pre-registered truth.
- One-run-per-input deviation: SAM was called once as a smoke test on o1 and once more on o1 after my P3 parser code crashed (a code bug, before any scoring). Smoke test raw kept in outputs/raw/smoke_sam_o1.json. The scored run is the later one. Extra cost about $0.005.
- P3 prompts and P1 prompt were written once, before any results; no prompt changed after results were seen, so there is a single run per probe.
- P3 "all 14 slots mapped correctly" has no ground-truth box positions in labels.json, so correctness is judged from overlays plus an automatic grid-monotone check, not an exact match.

## STOP: Twilio send rejected twice with the same error (2026-10-31)
- Request (no credentials): `POST /2010-04-01/Accounts/{AccountSid}/Messages.json`, form body `From=whatsapp:<TWILIO_WHATSAPP_FROM>`, `To=whatsapp:<r1 number>`, `Body=<short free-form text>`, `StatusCallback=<PUBLIC_BASE_URL>/twilio/status`. Made via twilio-python `client.messages.create(from_=, to=, body=, status_callback=)`.
- Response (both attempts): HTTP 400, "Unable to create record: ContentSid Required".
- Expected: a free-form text inside the 24 h window to a number that has joined the sandbox and sent "hi". No 63015.
- Also: the Content API list call returns 401 code 20003 "This feature is not available on a Trial account", so templates cannot be listed via the API on this account.
- Both rejected attempts were counted by my outbound counter (shows 2); nothing was actually delivered by the app, so the true outbound count is 0. Counter increments before the call by design (stop before exceeding the cap).
- No third attempt made. Nothing else changed.
- Third attempt (2026-10-31 20:01Z), after the sender and webhook URLs were confirmed and all three recipients had just sent "hi" (fresh 24 h windows, r3 re-joined): same request, same HTTP 400 "ContentSid Required". The 24 h window is therefore not the cause. Outbound counter now reads 3; true delivered by the app: 0. Stopped; no further sends.
- Counter reset to 3 on 2026-10-31 after the account upgrade: the 3 earlier rejected attempts were never delivered, so true outbound = 3 real sends (P4b).
