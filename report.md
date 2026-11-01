# Phase 0 report (final)

Channel: Twilio WhatsApp Sandbox behind a channel adapter (Meta test number blocked, error 2655121). Probes named P1-screen and P3-synthetic where the inputs are weaker than the brief's. Account was upgraded Trial -> Full on 2026-10-31 after free-form sends were rejected on Trial (see Platform facts).

## Pre-registration
- labels.json commit: 21f01a417ef22b48d2e958aa3d939371245b3c83 (committed alone, before any probe runner existed)
- labels.json sha256 at start: f99dca3478e22b50124e083fb6bd0aa71ccb45aabc026018493d8b499f3d6e8c
- labels.json sha256 at end: f99dca3478e22b50124e083fb6bd0aa71ccb45aabc026018493d8b499f3d6e8c (unchanged)
- Labels gate passed (notes and times exempt).

## Results
| Probe | Metric | Threshold | Result | PASS/FAIL | Cost | Latency |
|---|---|---|---|---|---|---|
| P1-screen | scored fields exact (13 meds, 3 sheets) | >= 95% | 78/78 = 100% | PASS | $0.0225 | 5.3 / 5.8 / 7.5 s per sheet |
| P1-screen | invented meds / dropped meds / invented times | 0 / 0 / 0 | 0 / 0 / 0 | PASS | | |
| P3-synthetic pipeline | photos with >= 13/14 compartments correct | >= 3/4 | 3/4 (o1, o2, o3 = 14/14; o4 = 0/14) | PASS | $0.0453 | 7.1 / 7.3 / 10.8 / 7.6 s |
| P3-synthetic pipeline | photos with all 14 slots mapped | >= 3/4 | 3/4 (o4 failed) | PASS | | |
| P3-synthetic Spark alone | compartments correct | same table | 14/14 on all 4 photos | PASS | $0.0187 | 2.5 to 5.2 s |
| P3 SAM masks per photo | expected 14 | | o1 14, o2 14, o3 14, o4 1 | | | |
| P4(a) Twilio inbound | text + photo + 12 voice notes saved with mime; bad signature rejected | all | all saved (audio/ogg for notes, image/jpeg); forged signature 403, signed 200 | PASS | | |
| P4(b) outbound free-form | delivered to r1, r2, r3 inside window | delivered | 3/3 delivered | PASS | | r1 4.66 s, r2 8.36 s, r3 4.32 s |
| P4(c) templates | list | report | account lists 6 Content templates: message_opt_in (quick-reply), notifications_welcome_template (call-to-action), notifications_order_update_template (media and quick-reply versions), notification_order_tracking (list-picker), notifications_appointment_confirmation_template (quick-reply). Not verified to be exactly the sandbox's pre-approved set. No template created. | reported | | |
| P4(d) status callbacks | log sent/delivered/read with timestamps | report | logged: sent, delivered, read (no queued callback observed); in outputs/status_log.jsonl | reported | | |
| P2 | intents fully correct; of which hi/pa/mixed | >= 11/12; >= 3/4 | 12/12; 4/4 | PASS | $0.0353 | median 5.0 s (transcribe + parse) |
| P5 (i) | nudge r2, no reply, escalate to r1 at 60 s +/- 3 | | escalated at 60.04 s | PASS | | nudge delivered 4.44 s, escalation 3.75 s |
| P5 (ii) | r2 replies "done" about 20 s, no escalation | | reply at 25.2 s (later than target), no escalation, nothing sent to r1 | PASS | | nudge delivered 4.10 s |
| P5 (iii) | r2 replies after escalation, late reply logged | | escalated at 60.05 s; r2's reply arrived at 82.8 s (target about 70 s), logged against metformin_08:00 as late | PASS | | nudge 4.24 s, escalation 3.27 s |
| P5 (iv) | no reply; m4 (simulated) at 60 s, r1 at 120 s | 60 +/- 3, 120 +/- 3 | m4 at 60.03 s (sim_inbox), r1 at 120.04 s | PASS | | nudge 3.40 s, escalation 4.45 s |
| P5 | every real send delivered within 5 s | <= 5 s | all 7 trial sends 3.27 to 4.45 s (the one over-5 s send was P4(b) r2 at 8.36 s) | PASS | | |
| P6 | median P1 per sheet | < 10 s | 5.8 s | PASS | | |
| P6 | median P2 per note | < 6 s | 5.0 s | PASS | | |
| P6 | median P3 per photo (pipeline) | < 15 s | 7.5 s | PASS | | |
| P6 | total model spend | < $5 | $0.1266 | PASS | | |

Delivery latency = status callback "delivered" arrival time on our server minus the time just before the API call, both on this machine's clock. It therefore includes the callback's network time and slightly overstates true delivery latency.

## Outbound messages
- 11 real WhatsApp messages sent by the app (cap 40): P4(b) 3, P5 trial (i) attempt 1 (invalid, r2 replied early) 1, P5 (i) 2, (ii) 1, (iii) 2, (iv) 2 to real members plus 1 to simulated m4 (not counted).
- 3 earlier send attempts were rejected by Twilio before any message left (HTTP 400 ContentSid Required, Trial account); they are not counted (counter reset to the true figure).
- The sandbox's own join auto-replies are not ours and not counted.

## Go / no-go (applied mechanically)
- P1 PASS and P4 (Twilio) PASS: GO.
- P2 PASS: no VOICE-EN-ONLY or VOICE-RED flag.
- P3: pipeline PASS and Spark-alone PASS. SAM-NOT-LOAD-BEARING needs Spark-alone within 1 compartment of the pipeline on every photo; on o4 Spark-alone is 14 and the pipeline 0, so the flag is not raised. Noted for the advisor: SAM added nothing where it worked and failed on the hardest photo. SAM's role is re-decided after real photos (CLAUDE.md Decisions).
- P5 PASS: no ESCALATION-RED.
- Result: GO. No flags raised.

## Caveats
- P1-screen: photos of a Word document on a screen, not paper. d3 has no crossed-out drug and no handwriting.
- P3-synthetic: AI-generated images; weak evidence; never present as real photos. o1-o3 are near-identical angles of one scene; n = 4. Slot-mapping correctness has no ground-truth boxes: judged by overlays (inspected o1, o2, o3) plus an automatic grid-order check.
- P2: all 12 notes are one speaker on one phone; thin latency margin (5.0 s vs 6 s); some transcripts are rough (e.g. atorvastatin heard as "Astro Vista") but parsing was correct because slots are constrained to the d1 schedule.
- P5: replies came from a human, so reply timing varied (ii at 25.2 s, iii at 82.8 s against targets of about 20 s and about 70 s). Escalation timing itself was within 0.05 s of target in every trial. The r2 slow delivery in P4(b) (8.36 s) shows delivery latency can exceed 5 s on this channel; it did not recur in P5. One invalid first attempt at (i) is kept in outputs/p5_i_attempt1_r2_replied_at_26s.json.
- n is small everywhere (one run per input).

## Platform facts
- SAM 3.1: id `sam-3.1`. Request: `POST https://api.meta.ai/v1/responses`, Bearer auth, body `{"model":"sam-3.1","stream":false,"metadata":{"mask_encoding":"one_bit","include_confidence":"true"},"input":[{"type":"message","role":"user","content":[{"type":"input_text","text":"pill organizer compartment"},{"type":"input_image","image_url":"data:image/jpeg;base64,..."}]}]}`. Response: special-token text, one box and one mask per object. The one_bit mask byte format is undocumented; decoded with PyPI `meta_sam_parser` (named by the docs). The docs say no image usage field; the response carries `usage.images_processed`.
- Voice Transcribe id: `muse-voice-transcribe-1.0`, `POST /v1/asr/transcribe`, multipart. Twilio delivered `audio/ogg`; **rejected natively** (HTTP 400: mono 16-bit PCM WAV at 16 or 24 kHz required); converted with ffmpeg (`-ac 1 -ar 16000 -c:a pcm_s16le`). No language parameter exists; language auto-detected.
- Spark: `muse-spark-1.3`, chat completions, strict json_schema; temperature 0 accepted (docs silent); `reasoning_effort: "low"` on every Spark call in P1, P2 and P3 (none is unsupported). No contributor model ids were called.
- Prices on the dev.meta.ai pricing page match the brief (Spark $1.25/$4.25 per 1M tokens, Voice $0.18/hour, SAM 3.1 $2.50 per 1,000 images).
- Twilio: on a **Trial** account, free-form sends from the sandbox sender were rejected 3 times with HTTP 400 "ContentSid Required", even inside a fresh 24 h window with all recipients joined and the sender and webhook URLs verified; the Content API also returned 401 (code 20003, not available on Trial). After upgrading to a Full account the same request succeeded. Cause is inferred from the before/after, not confirmed by Twilio. Webhook signature validation works through a Cloudflare quick tunnel; quick-tunnel addresses change on restart (one stale address cost a day).
- Template status and category: not applicable (no template created; Twilio sandbox).

## Spend
Total model spend: $0.1266 across 45 calls (smoke $0.0025, P1 $0.0225, P3 $0.0663 [pipeline $0.0453 incl. SAM, Spark-alone $0.0187, plus the failed first o1 SAM run], P2 $0.0353). Twilio message costs are not model spend and are not tracked here.

## Redaction grep (repo and outputs/, counts only)
86 text files scanned, 0 tracked-file hits. Hits: Twilio account SID 0, Twilio auth token 0, MODEL_API_KEY first 12 characters 0, r1 number 0 (also digits-only form 0), r2 0 (0), r3 0 (0). Meta WA_TOKEN, WA_APP_SECRET and WA_VERIFY_TOKEN are blank and unused. Saved JSON uses r1..r3, `r?` or `sim:mN` only. labels.json re-hashed at the end: unchanged.
