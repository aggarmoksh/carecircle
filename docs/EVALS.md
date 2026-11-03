# Evaluations

Every probe we ran, with its table and its caveat. Fictional patient and data throughout. "Pre-registered" means the labels and thresholds were committed before any code that scores them existed; where a prompt or code changed after results were seen, that is said next to the result. **n is small everywhere (one run per input unless stated), so read these as evidence that a design works on our inputs, not as accuracy claims.**

Models: `muse-spark-1.3` (text and vision, chat completions, strict `json_schema`, temperature 0, `reasoning_effort: low`), `muse-voice-transcribe-1.0`, `sam-3.1`. Channel: Twilio WhatsApp Sandbox (the Meta test number was blocked, error 2655121).

## Pre-registration

| File | What it fixes | Commit | sha256 (first 16 hex) |
|---|---|---|---|
| `labels.json` | Phase 0 labels: 3 discharge sheets, organiser photos, 12 voice notes | `21f01a4` (committed alone, before any probe runner) | `f99dca3478e22b50` (unchanged at the end) |
| `tests/router_labels.json`, `tests/guard_blocklist.txt` | Phase 1 router, medical and record-question labels; advice blocklist | `7deed70` | router labels `50afd7b3ac73c1ff` |
| `tests/lab_labels.json` | Two fictional lab reports (L1, L2) | `f72f48e` | |
| `tests/phase2_labels.json` | Held-out record questions | `bf87592` | |
| `tests/organiser_real_labels.json` (plan), `tests/paper_labels.json` | Real organiser photos (plan) and paper documents | `d60ea78` | `c3e63f74f697e2a4`, `ef64846aad4bd55a` |
| `tests/organiser_real_labels_v2.json` | Advisor's reading of the 8 real organiser photos, committed before any P3-real run | `e8348a1` | `c2bc8e10e602a50e` |
| `tests/p9_labels.json` | Medicine-name check list, committed before any search | `cedae34` | |

## Phase 0: can the building blocks do the job?

| Probe | Metric | Threshold | Result | |
|---|---|---|---|---|
| P1-screen | scored fields exact (13 medicines, 3 sheets) | >= 95% | **78/78 = 100%** | PASS |
| P1-screen | invented / dropped medicines / invented times | 0 / 0 / 0 | 0 / 0 / 0 | PASS |
| P3-synthetic, SAM pipeline | photos with >= 13/14 compartments right | >= 3 of 4 | **3/4** (o1, o2, o3 14/14; o4 0/14) | PASS |
| P3-synthetic, Spark alone | compartments right | same | **14/14 on all 4 photos** | PASS |
| P3-synthetic, SAM masks | masks per photo (14 expected) | | o1 14, o2 14, o3 14, o4 1 | |
| P4(a) Twilio inbound | text, photo, 12 voice notes saved with MIME; forged signature rejected | all | all saved; forged signature 403, signed 200 | PASS |
| P4(b) outbound | free-form text delivered inside the 24 h window | delivered | 3/3 (4.3 to 8.4 s) | PASS |
| P2 voice | intents fully correct; of which Hindi / Punjabi / mixed | >= 11/12; >= 3/4 | **12/12; 4/4**, median 5.0 s per note | PASS |
| P5 escalation (4 trials, real phones) | nudge, no reply, next member at 60 s +/- 3 | | escalated at 60.04 s, 60.05 s; simulated member at 60.03 s, real at 120.04 s; a reply after escalation was logged as late | PASS |
| P5 | every real send delivered | <= 5 s | 3.3 to 4.5 s (the one slow send was P4(b), 8.4 s) | PASS |
| P6 | median latency per sheet / note / organiser photo | < 10 s / < 6 s / < 15 s | 5.8 s / 5.0 s / 7.5 s | PASS |
| P6 | total model spend | < $5 | $0.13 | PASS |

**Caveats.** P1-screen used photos of a Word document on a screen, not paper; d3 has no crossed-out drug and no handwriting. P3-synthetic used four AI-generated images (o1 to o3 are near-identical angles of one scene): weak evidence, never presented as real photos; slot mapping had no ground-truth boxes and was judged from overlays plus an automatic grid-order check. P2: all 12 notes are one speaker on one phone, the latency margin is thin (5.0 s against 6 s), and some transcripts were rough (atorvastatin heard as "Astro Vista") but parsing was right because slots are constrained to the live schedule. P5 replies came from a human, so reply timing varied (25.2 s and 82.8 s against targets of about 20 s and 70 s); escalation timing itself was within 0.05 s of target. One invalid first attempt is kept. On a Trial Twilio account free-form sends failed with "ContentSid Required"; they worked after upgrading to a full account (cause inferred, not confirmed by Twilio).

## Phase 1: the WhatsApp side

| Check | Threshold | Result |
|---|---|---|
| Router type on the Phase 0 inputs (3 sheets, 4 organiser images, 12 voice notes) | 19/19 | **19/19** |
| Medical questions get the fixed reply (two urgent) | 10/10 | **10/10** |
| Medicine names or doses outside the record in any outbound | 0 | **0 in 26 texts** |
| Record questions | >= 7/8 | **8/8** on the final prompt (two runs) |
| Escalation unit tests | pass | 6 pass |
| Offline replay (sheet, YES, voice note, organiser photo) | expected log | all 5 checks pass |
| Live run on real phones | relay arrives | PASS (the relay to a member asleep in London was queued, then delivered after the clock was set to a London morning) |

**Caveats.** Record questions were unstable at temperature 0: the first prompt scored 6/8, 4/8, 7/8 on identical inputs. The prompt was changed after those results (explicit snapshot fields and answer rules) and then scored 8/8 twice; all five runs are recorded. Two good runs are not proof of stability. The record-question check is a keyword check (a correct answer worded differently can fail, a wrong one containing the keywords could pass). The name scan uses a built-in list of about 90 drug names plus the record, so an unlisted drug name would not be caught. The live run used a stopped scheduler (escalation was verified by unit tests and in Phase 0 P5).

## Phase 2: lab reports and record questions

P7 (lab extraction from two fictional lab reports; fields = value, unit, printed range): **54/54 fields, 0 wrong statuses, 0 invented ranges, 0 invented or dropped tests.** The status (above, below, within the printed range) is computed by code from value and printed range, never by the model.

| Report | Test | Extracted | Printed range | Status (code) | Label | Fields ok |
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
| L2 | vitamin d | 18 ng/mL | (none) | no range | no range | 3/3 |

Record questions, three runs of two sets: original 8 **8/8, 8/8, 8/8**; held-out 8 **8/8, 8/8, 8/8**. Held-out history: 5/8 before any fix, 6/7/7 after fix attempt 1, 8/8/8 after attempt 2 (both allowed attempts used; fixes were made after seeing results, labels were never changed). Medical questions 1 to 12: **12/12 in each of 3 runs**, fixed reply, two urgent. Outbound scan: **0 medicine names, doses or lab values outside the record across 280 saved texts.** Phase 1 router eval again: 19/19.

**Caveats.** Keyword checks are loose. The two lab reports are fictional, printed in one style, so P7 says little about other labs' layouts. The advice blocklist pattern `diagnos\w*` matches the lab name "Sunrise Diagnostics", so that lab name is left out of outbound texts.

## Phase 3: real photos, real documents, SAM 3.1

### P3-real: 8 real organiser photos (14 labelled compartments each)

| Photo | Spark alone | SAM masks | All 14 mapped | SAM pipeline |
|---|---|---|---|---|
| or1 | 14/14 | 1 | no | 0/14 |
| or2 | 14/14 | 1 | no | 0/14 |
| or3 | 14/14 | 1 | no | 0/14 |
| or4 | 14/14 | 16 | yes | 14/14 |
| or5 | 14/14 | 16 | yes | 14/14 |
| or6 | 14/14 | 1 | no | 0/14 |
| or7 | 14/14 | 1 | no | 0/14 |
| or8 | 14/14 | 1 | no | 0/14 |

Spark alone read **8/8 photos at 14/14 (0 wrong compartments)**. SAM 3.1 returned one mask on six photos and 16 masks (the whole tray) on two; it mapped all 14 compartments on **2 of 8** photos (the rule needed 7 of 8). Decision: **SAM overlays dropped; Spark judges alone.** Across both organiser tests SAM 3.1 mapped 3 of 4 AI-generated photos and 2 of 8 real ones, and added nothing where it worked. The SAM code stays in `app/vision.py` but is not called.

### P8-private: 4 real documents (2 printed, 2 handwritten), scored by names only

The scoring tool printed counts only; file contents were never printed or copied. Rule fixed before any run: a normalised match, or a contains-match of 4+ letters; a clear unmatched line close to a label name (difflib ratio >= 0.6) is "confidently wrong", otherwise "invented".

| Doc | Kind | Label medicines | Extracted lines | Found | Dropped | Confidently wrong | Invented |
|---|---|---|---|---|---|---|---|
| 1 | printed | 7 | 7 | 5 | 2 | 2 | 0 |
| 2 | handwritten | 1 | 3 | 0 | 1 | 0 | 1 |
| 3 | printed | 8 | 8 | 8 | 0 | 0 | 0 |
| 4 | handwritten | 3 | 2 | 0 | 3 | 0 | 0 |

Pre-registered target: printed documents 0 confidently wrong. **Doc 1 scored 2, a miss, but both were clerical errors in our own answer key** (two spelling typos in its labels; the labels of documents 2 and 4 had also been swapped), so the reading was right and the key was wrong. The corrected score is reported next to the pre-registered one, below. Separately, the check found a real extraction bug: "2 TSF" came back as 2.0 mL because the unit list had no teaspoon (fixed: units are kept as printed, never converted). That concerned a dose, which this names-only scoring does not count.

Post-hoc rescore with the advisor's corrected labels (clerical errors: labels of documents 2 and 4 had been swapped, two typos on doc 1, one medicine missing for doc 4), from the saved extractions with no new calls. Reported next to the pre-registered score, not instead of it:

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

**On 4 real, redacted documents (2 printed, 2 handwritten), scored by medicine names: the printed ones read 15 of 15 names. The pre-registered score showed 2 misses, both clerical errors in our own answer key (two typos and two documents' labels swapped), corrected and reported side by side. On handwriting it misread 1 name and flagged 4 lines for a person to check, which is why every handwritten line now needs a person's confirmation.** The one misread name came back "clear" on a handwritten sheet. The handwriting rule added afterwards (every line on a handwritten sheet is marked unsure and YES is refused until each name is retyped) is covered by a unit test, not by a new P8 run. On the handwritten documents the model also dropped most label medicines.

### Other Phase 3 checks

| Check | Result |
|---|---|
| P1-screen again, with the new schema (units as printed, unsure lines) | 78/78 fields, no invented or dropped medicines |
| Router eval after the classifier change | run 1: 18/19 (voice v05 routed as a question), run 2: 19/19; medical 10/10, record 8/8 |
| Phase 2 evals, one run | original 8/8, held-out 8/8, medical 12/12, 0 guard blocks |
| P1-paper | skipped (no paper set was available) |

## Phase 4: correctness fixes and languages

| Check | Result |
|---|---|
| Lab status for every lab row | tested by rendering every row: status always computed from the value and the printed range at render time. The earlier screenshot that showed creatinine 1.2 as "above" 0.7-1.3 came from a demo fixture whose values were edited behind a stored status; statuses are no longer stored |
| Dose states at a fixed clock | "due" inside the 15-minute grace; "overdue, escalating" after it; "missed" when the ladder is exhausted or the next dose of the same medicine falls due |
| Router eval, three fresh runs | **19/19, 19/19, 19/19** (types; medical 10/10 and record 8/8 each). Same-day earlier runs: 18/19 (voice v05), then 18/19 (voice v11, a Punjabi clip the model called "other"). A code rule (a past-action report with no "?" is a dose report) was added after those misses |
| Outbound scan | 65 saved texts, 0 medicine names, doses or lab values outside the record |
| Hindi replies through Spark, 10 real replies | 10/10 localised, 0 guard failures, 0 names or numbers changed. This checks names and numbers only. One Hindi reader reviewed ten replies; their feedback (time words, a medicine word after each name) led to the fixed Hindi templates. The templates themselves have not had a second reader |
| Spanish replies through Spark, 10 real replies | 10/10, same checks. Nobody fluent has reviewed the Spanish |

System messages (nudges, relays, missed doses, schedule and lab notices, the daily summary) are now **fixed templates** in English, Hindi and Spanish; Spark phrases only free answers to record questions. Hindi times use the 12-hour clock with a time word ("शाम 8 बजे").

## P9: checking medicine names against public listings (dropped)

Muse Spark's `web_search` tool (Responses API only; $2.50 per 1,000 searches) returns a product name, a strength flag and a source URL; code then fetched the URL and counted a name as found only if the domain was on an allow-list (dailymed, medlineplus, drugs.com, ema.europa.eu, medicines.org.uk, nhs.uk, healthdirect.gov.au, 1mg, practo, pharmeasy, apollopharmacy), the page loaded and it contained the name. Pre-registered list, one run, no prompt changes after results. Pass rule: >= 15 of 17 real names found with a valid source, 0 of 5 fakes, 0 of 2 wrong strengths.

**Result: 10 of 17 real names found with a valid source; 0 of 5 fakes found; 0 of 2 wrong strengths found. FAIL, so the feature was not built.** Cost of the run: $0.41.

| Name | Expected | Result | Source domain | Note |
|---|---|---|---|---|
| metformin 500 mg | found | found | drugs.com | ok |
| amlodipine 5 mg | found | found | drugs.com | ok |
| atorvastatin 20 mg | found | found | drugs.com | ok |
| levothyroxine 50 mcg | found | found | drugs.com | ok |
| insulin glargine 100 units/mL | found | found | drugs.com | ok |
| Lipitor 20 mg | found | found | dailymed.nlm.nih.gov | ok |
| Glucophage 500 mg | found | not found | - | page does not contain the name |
| Tylenol 500 mg | found | not found | - | model: not found |
| Nurofen 200 mg | found | found | medicines.org.uk | ok |
| Pantop 40 mg | found | found | 1mg.com | ok |
| Dolo 650 mg | found | not found | - | cited page returned HTTP 404 |
| Azee 250 mg | found | not found | - | cited page returned HTTP 404 |
| Econorm 250 mg | found | found | 1mg.com | ok |
| Swich 200 mg | found | not found | - | cited page returned HTTP 404 |
| Pan-D | found | found | 1mg.com | ok |
| Sporolac DS | found | not found | - | model: not found |
| Emeset 4 mg | found | not found | - | cited page returned HTTP 404 |
| Surich 200 mg | not found | not found | - | model: not found |
| Zeprovan 250 mg | not found | not found | - | model: not found |
| Lomaxitrine 40 mg | not found | not found | - | model: not found |
| Cardivexol 10 mg | not found | not found | - | model: not found |
| Astro Vista 20 mg | not found | not found | - | model: not found |
| Dolo 6500 mg | strength not found | not found | - | model: not found |
| Pantop 400 mg | strength not found | not found | - | model: not found |

**Caveat.** The errors went the safe way (nothing false was accepted), but recall was 59% and most misses were cited pages that returned 404. Kept in `POSTLAUNCH.md`.

## Language and tone checks that are *not* measured

Nothing here measures whether the Hindi or Spanish reads naturally, whether a family would understand the board, or whether the escalation messages feel intrusive. Those need real users.

## Spend

Model spend across the project, cumulative as logged at the end of each phase: Phase 0 **$0.13**, Phase 1 $0.53, Phase 2 $2.13, Phase 3 $3.03, Phase 4 $5.73, P9 plus the language runs **$6.29** of an $8.00 cap (Phases 4c and 4d made no model calls). Twilio message costs are not model spend and are not tracked. The private-document extraction calls (4, about $0.013) are not logged in the repository.
