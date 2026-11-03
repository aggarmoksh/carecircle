# CareCircle

**The care log that writes itself, in the chat you already use.**

When someone we love is ill, the people who care for them are scattered: a grandson in Los Angeles, a cousin in London, an aunt at home in Kolkata. They coordinate in one noisy WhatsApp group ("80 unread messages and zero context"), and nobody is sure whether the morning pills were given.

CareCircle is a WhatsApp agent that keeps one shared care record for one patient. A family member photographs the discharge sheet; CareCircle reads it, asks for a "yes", and from then on nudges the right person when a dose is not confirmed, privately and in their language, then the next person who is awake, wherever they are. It reads a voice note ("Maine Nanaji ko subah ki metformin de di") and a photo of the weekly pill organiser, compares lab values only with the range printed on the report, and keeps a one-page summary for the doctor.

**It coordinates. It never gives medical advice.** Medical questions are saved as tasks for the doctor's visit and answered with a fixed refusal; urgent symptoms get a fixed "call emergency services" message.

> A prototype built on Meta's Muse models and the Twilio WhatsApp Sandbox. Fictional patient and fictional data. Not a medical device, not for real patient care.

## What is real and what is simulated

| Real | Simulated or fictional |
|---|---|
| WhatsApp messages in both directions through the **Twilio sandbox**, with three real phones (Arjun in Los Angeles, Meena in Kolkata, Kabir in London) | **Sunita** (neighbour) and **Sofía** (family friend, Madrid) are simulated members: their messages are logged, not sent to a phone. They are labelled everywhere |
| Calls to **Muse Spark 1.3** and **Muse Voice Transcribe** (and, in testing, SAM 3.1) | The patient "Nanaji" and every name, medicine schedule, document and lab value. The discharge sheets and lab reports are invented. Most test photos of printed sheets were taken of a screen |
| The care record (SQLite), the escalation ladder, the guard, the relay and quiet-hours rules, the board, the doctor summary, the Today card | The **demo clock**: the board can show simulated time so a morning scene can be filmed at any hour |
| Real photos of a pill organiser (8) used in the evaluation | Four AI-generated organiser images (marked as such in the evaluation) |
| | The **interactive replay** (`site/replay.html`) is a scripted, offline page built from the same fictional seed. The real system runs on WhatsApp |

Not built: the WhatsApp Business (Meta Cloud API) channel (the Meta test number was blocked; there is a stub), message templates for members outside the 24-hour window (those messages are skipped and logged), deployment, accounts or login beyond the link tokens.

## How it works

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the diagram. In short:

1. **A document or a message arrives** on WhatsApp. A photo is classified and read into a *draft* schedule; nothing goes live until a member replies YES (or "sí", "हाँ"). If the sheet is handwritten, every line is marked unsure and a member must retype each name first.
2. **Code runs the care.** Once a second a scheduler looks at the record. A dose that is 15 minutes past due gets one private nudge to the person on duty. No answer after a minute: the next person who is awake, inside the WhatsApp window and has not chosen STOP (nearby members first). Each skipped member is logged with the reason. Doses due at the same time are one question, "done" confirms all of them, and a partial reply confirms only the medicines named. An unconfirmed dose becomes "missed" when nobody is left to ask or the next dose of that medicine falls due.
3. **Everyone sees the same picture, in their own words.** Updates go to the others according to each person's choice (everything, only their duties and alerts, one summary a day at 8 PM, or stop). System messages are fixed templates in English, Hindi and Spanish: the model does not rephrase them.
4. **A board and a doctor summary.** `/board` shows The Circle (who is where, who is awake, who was asked), the Now card, Today, lab values, the organiser grid, tasks and an activity feed in plain sentences. It updates live, works on a phone, and has a dark mode behind a toggle. `/doctor` is a one-page printable summary: adherence, missed doses with reasons, lab values against their printed ranges, and questions for the doctor.
5. **Optional extras.** A personal read-only board link per member (hashed, revocable), a Today card image sent on request ("board", "बोर्ड", "tablero") and with the daily summary, and an offline interactive replay page.

## The Meta models and how they are used

| Model | Used for | Not used for |
|---|---|---|
| **Muse Spark 1.3** (chat completions, strict JSON schema, temperature 0, low reasoning effort) | Classifying a photo; extracting medicines, doses and times from a sheet, prescription or lab report; judging which organiser compartments are full; classifying a message's intent; parsing who gave which dose against the live schedule; applying a correction to a draft; phrasing an answer to a *record question* from facts that code assembled | Deciding who is messaged, changing the record, any medical judgement, writing system messages |
| **Muse Voice Transcribe** | Voice notes in English, Hindi, Punjabi or a mix (audio converted to 16 kHz mono WAV first); the transcript then goes through the same router as text | |
| **SAM 3.1** | Tried as a way to find organiser compartments | **Dropped.** On real photos it mapped all 14 compartments on 2 of 8; Spark alone read 14/14 on all 8 |

## What was tested, and what was dropped

Pre-registered where it matters; every table and its caveat is in [docs/EVALS.md](docs/EVALS.md). Highlights (all small samples, one run per input unless stated):

- **Reading sheets:** 78/78 fields exact on 3 fictional discharge sheets (photos of a screen). On 4 real documents the printed ones had 0 confidently wrong lines once clerical label errors were corrected (2 before; the cause was a unit bug, fixed), and the handwritten ones were mostly dropped, hence the handwriting rule.
- **Voice:** 12/12 notes routed to the right dose update, including Hindi and Punjabi (one speaker, one phone).
- **Lab reports:** 54/54 fields on 2 fictional reports, 0 wrong statuses, 0 invented ranges.
- **Organiser photos:** Spark alone 14/14 on 8/8 real photos. **SAM 3.1 dropped:** 3 of 4 AI photos and 2 of 8 real ones.
- **Router:** 19/19 on the pre-registered set in three fresh runs (it had missed once on two earlier runs, which led to one code rule), medical questions 10/10 get the fixed reply, record questions 8/8 on the final prompt (after an unstable first prompt: 6/8, 4/8, 7/8).
- **Escalation on real phones:** next member reached at 60.0 s +/- 0.05 s in every trial.
- **Outbound safety scan:** 0 medicine names, doses or lab values outside the record in every scanned set of outgoing texts (the latest: 65 texts).
- **Medicine-name check against public listings (P9): dropped.** Muse Spark web search found 10 of 17 real names with a valid source (the bar was 15), 0 of 5 invented names and 0 of 2 wrong strengths. It never accepted anything false, but too many cited pages did not exist.
- **Not measured:** whether the Hindi and Spanish read naturally to fluent readers beyond one review, whether families would use it, and anything with a real patient.

## Safety design

- **Coordination only.** Medical questions get a fixed reply and become a task for the doctor's visit. Urgent symptoms get a fixed message and an alert to members who are awake.
- **Code decides, the model reads.** State changes, escalation, relays and sending are plain code. The model's output is a draft, a classification, or the wording of an answer built from the record.
- **Nothing goes live unconfirmed.** Every extraction is a draft until a member says yes; uncertain or handwritten lines need a retyped name.
- **An outbound guard.** Before any message leaves, a medicine name, dose or lab value that is not in the record (or in the sender's own message) is blocked and replaced by a fixed sentence, and an advice blocklist (committed before the code) is applied.
- **Lab values are compared only with the range printed on the report,** with a word and a shape, never colour alone. No "normal", "abnormal", "risk" or "danger". Statuses are computed at display time, never stored.
- **Units stay as printed.** "2 tsp" is never converted to millilitres.
- **People stay in control.** Nobody is woken at night (waking hours are respected and messages are queued); STOP silences everything until the member writes again; the 24-hour WhatsApp window is respected.
- **Access.** The board needs a token; each member's link is personal, read-only and revocable (only its hash is stored); the clock and revoke endpoints need an admin token. The code has no real patient data and the repository history was scanned for secrets.

## Setup

Requirements: Python 3.11, ffmpeg (voice notes), a Chrome or Chromium install (only to render the Today card), a Meta model API key, and a Twilio account with the WhatsApp Sandbox for real sends.

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt        # on macOS/Linux: .venv/bin/pip
cp .env.example .env                                   # fill in the values; never commit .env
```

`.env` holds: `MODEL_API_KEY`, the Twilio values (`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`), `WA_RECIPIENTS` (the three real members' numbers, comma-separated, in order), `PUBLIC_BASE_URL` (a public address that reaches the server, for example a quick tunnel), `BOARD_TOKEN` and `ADMIN_TOKEN` (long random strings). The `WA_*` variables are for the unused Meta Cloud API channel.

```bash
# tests (no network, no keys needed)
.venv/Scripts/python -m pytest tests

# run the server (set CARECIRCLE_DRY_RUN=1 to capture messages instead of sending them)
.venv/Scripts/python -m uvicorn app.server:app --port 8000
# in the Twilio console set the sandbox webhook to <PUBLIC_BASE_URL>/twilio/inbound and the status callback to <PUBLIC_BASE_URL>/twilio/status

# demo scenes (fictional data; prints the board path and the steps for each scene)
.venv/Scripts/python tools/demo_reset.py --scene monday      # fresh circle, no schedule yet
.venv/Scripts/python tools/demo_reset.py --scene thursday    # a week of history, doses overdue
# board: http://127.0.0.1:8000/board?token=<BOARD_TOKEN>      doctor summary: /doctor?token=<BOARD_TOKEN>

# the interactive replay works offline: open site/replay.html in a browser
```

The Twilio sandbox accepts one message every 3 seconds; the app spaces its sends accordingly and counts outbound messages against a cap (`CC_MESSAGE_CAP`, default 80).

## Limits

- Twilio sandbox only: three real phones, each must have joined it, free-form messages only inside the 24-hour window. No template sends and no production WhatsApp Business account.
- One patient and one circle, a single SQLite file, no login. Not designed for multiple families or real health data, and not audited for privacy law compliance.
- Extraction is as good as the photo: handwriting, glare and unusual layouts are handled by asking a person, not by guessing. The tests are small and mostly fictional documents.
- The medicine-name guard uses a built-in list of about 90 common drugs plus the record, so a rare drug name that is not in the record could slip past the name check (the dose and lab-value checks still apply).
- Hindi and Spanish messages are fixed templates. One reader reviewed the Hindi; nobody fluent has reviewed the Spanish. Nothing here replaces review by fluent speakers.
- The model is the weakest link on free text. Record questions are phrased by Spark and were unstable on the first prompt; the final one scored 8/8, which is not proof of stability.
- Escalation timing assumes the server is running; there is no push when it is down.

## License

MIT. See [LICENSE](LICENSE).
