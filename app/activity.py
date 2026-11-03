"""Audit log lines as plain sentences for the board's Activity feed. The raw line stays available behind a 'details' toggle."""
import json, re


def _who(ms, mid):
    return ms[mid]["name"] if mid in ms else ("Nanaji" if mid == "patient" else (mid or "CareCircle"))


def _j(detail):
    try:
        d = json.loads(detail)
        return d if isinstance(d, dict) else {}
    except (TypeError, ValueError):
        return {}


def _slot(s):
    med, t = (s or "").rsplit("_", 1) if s and "_" in s else (s or "a dose", "")
    return f"{med} {t}".strip()


LANGNAME = {"hi": "Hindi", "es": "Spanish"}
TYPES = {"pill_organiser": "the pill organiser", "discharge_sheet": "a discharge sheet", "prescription": "a prescription", "lab_report": "a lab report", "other": "a photo"}
DOSE = {"confirmed": "gave", "late_confirmed": "gave (late)", "skipped": "skipped", "unsure": "wasn't sure about"}


def sentence(row, ms, tz):
    """-> {text, icon, time} for one audit row (row: at, kind, actor, detail, reason). Time is the patient's local HH:MM."""
    from datetime import datetime
    k, a, d = row["kind"], row["actor"], row["detail"]
    j = _j(d)
    who = _who(ms, a)
    try:
        t = datetime.fromisoformat(row["at"].replace("Z", "+00:00")).astimezone(tz).strftime("%H:%M")
    except (TypeError, ValueError):
        t = ""
    icon, text, extra = "dot", (row["reason"] or k.replace("_", " ")), {}
    if k == "inbound":
        kind = j.get("kind")
        icon, text = ("camera", f"{who} sent a photo") if kind == "image" else ("mic", f"{who} sent a voice note") if kind in ("voice", "audio") else ("chat", f"{who} sent a message")
    elif k == "image_classified":
        icon, text = "camera", f"CareCircle recognised the photo as {TYPES.get(j.get('type'), 'a photo')}"
    elif k == "dose_event":
        icon, text = "pill", f"{_who(ms, j.get('actor'))} {DOSE.get(j.get('type'), 'logged')} {_slot(j.get('slot'))}"
    elif k == "dose_missed":
        icon, text = "cross", f"{_slot((d or '').split(' ')[0])} is recorded as missed"
    elif k == "escalation_skip":
        why = (d or "").split(": ", 1)[-1]
        why = re.sub(r"^asleep \(local (.*)\)$", r"asleep, \1", re.sub(r"^chose STOP.*", "stopped, no messages", why))
        icon, text = "moon", f"{who} was skipped ({why})"
    elif k == "escalation_hold":
        icon, text = "moon", "Nobody was reachable just now; CareCircle will try again"
    elif k == "outbound":
        m = re.search(r"([a-z]+)_(\d\d:\d\d)", row["reason"] or "")
        icon, text = "send", f"CareCircle messaged {who}" + (f" about {m.group(1)} {m.group(2)}" if m else "")
        if j.get("language") in LANGNAME:
            text += f" in {LANGNAME[j['language']]}"
            extra["detail"] = chr(10).join([f"Sent in {LANGNAME[j['language']]}: {j.get('text', '')}", f"English original: {j.get('english', '')}"])
    elif k == "relay_queued":
        icon, text = "clock", f"A message for {who} is waiting for their daytime"
    elif k == "relay_suppressed":
        icon, text = "mute", f"{who} was not sent this update: they chose fewer updates"
    elif k == "relay_pref":
        icon, text = "bell", f"{who} chose how many updates to get: {d}"
    elif k == "schedule_confirmed":
        icon, text = "check", f"{who} confirmed the medicine schedule"
    elif k == "draft_created":
        icon, text = "list", "CareCircle read the sheet and asked for confirmation"
    elif k == "draft_corrected":
        icon, text = "list", f"{who} corrected the draft"
    elif k == "yes_blocked":
        icon, text = "list", "A line marked ? needs the right name before the schedule starts"
    elif k in ("organiser_ok", "organiser_disagreement"):
        icon, text = "grid", ("The pill organiser matches the record" if k == "organiser_ok" else "The pill organiser does not match the record")
    elif k == "lab_draft_created":
        icon, text = "lab", "CareCircle read a lab report and asked for confirmation"
    elif k == "lab_confirmed":
        icon, text = "lab", f"{who} confirmed a lab report"
    elif k in ("medical_question",):
        icon, text = "flag", f"{who} asked a medical question; it was saved for the doctor visit"
    elif k == "task_assigned":
        icon, text = "list", f"{who} took a task: {j.get('text', '')}"
    elif k in ("urgent_symptom", "urgent_alert_skipped"):
        icon, text = "flag", f"{who} reported something urgent" if k == "urgent_symptom" else f"An urgent alert skipped {who}"
    elif k == "record_answer":
        icon, text = "chat", f"CareCircle answered {who} from the record"
    elif k == "transcript":
        icon, text = "mic", f"A voice note from {who} was transcribed"
    elif k == "clock_set":
        icon, text = "clock", "The demo clock was changed"
    elif k == "intent_override":
        icon, text = "pill", f"{who}'s message was read as a dose report"
    return dict(text=text, icon=icon, time=t, **extra)


def collapse(items):
    """Repeats of the same sentence in the same minute become one entry with a count ('x3'); the first (newest) entry keeps its details."""
    out, seen = [], {}
    for it in items:
        k = (it["text"], it["time"])
        if k in seen:
            seen[k]["n"] += 1
            continue
        it["n"] = 1
        seen[k] = it
        out.append(it)
    return out
