# Phase 0 report (P1-screen and P3-synthetic only; P4, P2, P5, P6 not run)

## Pre-registration
- labels.json commit: 21f01a417ef22b48d2e958aa3d939371245b3c83 (committed alone, before any probe runner existed)
- labels.json sha256 at start: f99dca3478e22b50124e083fb6bd0aa71ccb45aabc026018493d8b499f3d6e8c
- labels.json sha256 at end of this phase: f99dca3478e22b50124e083fb6bd0aa71ccb45aabc026018493d8b499f3d6e8c (unchanged)
- Labels gate: passed (written_by_user true, ISO timestamp, no "?" or empty values outside "_" keys; notes and times exempt).

## Results
| probe | metric | threshold | result | PASS/FAIL | cost | latency |
|---|---|---|---|---|---|---|
| P1-screen | scored fields exact (6/med, 13 meds, 3 sheets) | >= 95% | 78/78 = 100% | PASS | $0.0224 | 5.3 / 5.8 / 7.5 s per sheet (median 5.8 s) |
| P1-screen | invented meds / dropped meds / invented times | 0 / 0 / 0 | 0 / 0 / 0 | PASS | | |
| P3-synthetic pipeline | photos with >= 13/14 compartments correct | >= 3/4 photos | 3/4 (o1, o2, o3 = 14/14; o4 = 0/14) | PASS | $0.0453 total | 7.1 / 7.3 / 10.8 / 7.6 s (median 7.5 s) |
| P3-synthetic pipeline | photos with all 14 slots mapped correctly | >= 3/4 photos | 3/4 (o1, o2, o3; o4 failed: 1 SAM mask) | PASS | | |
| P3-synthetic Spark alone | compartments correct | same table | o1 14, o2 14, o3 14, o4 14 of 14 (4/4 photos) | PASS | $0.0187 total | 3.9 / 2.5 / 2.7 / 5.2 s |
| P3-synthetic | SAM masks per photo (expected 14) | 14 | o1 14, o2 14, o3 14, o4 **1** | | | |

Mapping correctness for the pipeline was checked two ways: an automatic grid-monotone check, and the user-facing overlays in outputs/overlays/ (labels drawn over each mask), which I inspected for o1, o2 and o3. The overlays are the evidence and the user should look at them too, particularly o4.

P6 (partial, only for the probes run): median P1 per sheet 5.8 s (< 10 s). Median P3 pipeline per photo 7.5 s (< 15 s). P2 not run. Total spend so far: see below.

## Caveats the advisor should weigh
- **P1-screen** inputs are CMF photos of a Word document on a laptop screen, not paper. A pass is evidence about reading clean typed text, not about photographed paper sheets. d3 has no crossed-out drug and no handwriting.
- **P3-synthetic** inputs are AI-generated images. A pass is weak evidence. The organiser audit should not be presented as working on real photos until real photos pass. CLAUDE.md Pitfalls records this.
- **o4 (angled, dim)**: SAM 3.1 returned a single large mask covering most of the photo instead of 14 compartments, so the pipeline fails there. Spark alone got 14/14 on the same photo.
- n = 4 photos; o1-o3 are near-identical camera angles of the same synthetic scene.

## GO/NO-GO (applied mechanically)
- P1: PASS. Not NO-GO.
- P3: pipeline PASS and Spark-alone PASS. SAM-NOT-LOAD-BEARING requires Spark-alone within 1 compartment of the pipeline on every photo. On o1-o3 they are identical (14 vs 14), but on o4 Spark-alone is 14 and the pipeline is 0, so the condition is not met and **no flag is raised**. Flagging this for the advisor: on this data SAM added no accuracy on the three photos where it worked, and it broke on the hardest one.
- P4, P2, P5: not run in this phase. Flags SAM-DEMOTED, AUDIT-CUT, VOICE-*, ESCALATION-RED: none raised.

## P1-screen: labelled vs extracted notes (not scored)
| sheet | medicine | labelled notes | extracted notes |
|---|---|---|---|
| d1 | metformin, amlodipine, aspirin, atorvastatin | (empty) | (empty) |
| d2 | telmisartan | printed as 1-0-0 | 1-0-0, after food |
| d2 | glimepiride | BD before food | BD, before food |
| d2 | pantoprazole | OD before breakfast | OD, before breakfast |
| d2 | clopidogrel | (empty) | OD |
| d2 | calcium carbonate | BD after food | BD, after food |
| d3 | levothyroxine | empty stomach | (empty) |
| d3 | metoprolol, insulin glargine | (empty) | (empty) |
| d3 | ibuprofen | printed as TDS; not crossed out in the Word version | (empty) |

## Platform facts (from dev.meta.ai docs, 2026-10-30)
- SAM 3.1 model id: `sam-3.1`. Request: `POST https://api.meta.ai/v1/responses`, Bearer auth, body `{"model":"sam-3.1","stream":false,"metadata":{"mask_encoding":"one_bit","include_confidence":"true"},"input":[{"type":"message","role":"user","content":[{"type":"input_text","text":"pill organizer compartment"},{"type":"input_image","image_url":"data:image/jpeg;base64,..."}]}]}`. Response: special-token text in output_text (one box + one mask per object). The docs do not specify the one_bit mask byte format; masks were decoded with the PyPI package meta_sam_parser, which the docs name.
- Voice Transcribe id: `muse-voice-transcribe-1.0`, `POST /v1/asr/transcribe` multipart, WAV mono 16-bit 16 or 24 kHz only per docs (so native WhatsApp .ogg/.opus will need ffmpeg conversion; P2 not run yet). Audio format accepted: not yet tested.
- Spark: `muse-spark-1.3` via /v1/chat/completions, `response_format` json_schema (strict true), `temperature` 0 accepted without error although the docs do not mention it.
- Reasoning setting used: `reasoning_effort: "low"` for every Spark call in P1 and P3 ("none" is unsupported per docs).
- Prices on the pricing page match the brief: Spark $1.25 / $4.25 per 1M, Voice $0.18 per hour, SAM 3.1 $2.50 per 1,000 images. Contributor model ids were never called.
- Template status and category: not applicable yet (P4 not run).

## Spend
Total tracked spend: see outputs/spend.json (per call). Cap $5.00.
Total: $0.0913 across 21 calls (includes 1 SAM smoke test and 1 SAM re-run of o1 after my parser code crashed; see inconsistencies.md).

## Redaction grep (repo and outputs/, counts only)
- WA_RECIPIENTS values found in .env: 0 (nothing to search for); hits: 0.
- First 12 chars of MODEL_API_KEY: 0 hits. WA_TOKEN, WA_APP_SECRET, WA_VERIFY_TOKEN are empty in .env, so not checked.
- labels.json sha256 re-hashed: unchanged.
