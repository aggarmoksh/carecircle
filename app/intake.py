"""Intake router for every inbound message. The model classifies and parses; this code decides and writes the record.
image -> classify -> (discharge/prescription | organiser | lab report | ask) ; voice -> ffmpeg + transcribe -> text path ;
text -> intent {dose_update, record_question, correction, volunteer, medical_question, urgent_symptom, other}."""
import json, pathlib, re
from . import config, record, vision, voice, llm
from .clock import clock
from .db import audit
from .outbox import FIXED_MEDICAL, FIXED_URGENT, FIXED_LAB

ROOT = pathlib.Path(__file__).resolve().parent.parent
INTENTS = ["dose_update", "record_question", "correction", "volunteer", "medical_question", "urgent_symptom", "other"]
YES = {"yes", "y", "yes please", "yeah", "yep", "yes start", "yes thanks"}
TYPE_WORDS = [("discharge_sheet", r"discharge"), ("prescription", r"prescri"), ("pill_organiser", r"organi[sz]er|pill ?box|pill ?organi"), ("lab_report", r"\blab\b|report|blood test|results?")]
HELP = "I can log doses, answer questions from the care record, or save a photo of a discharge sheet, pill organiser or lab report."

INTENT_SCHEMA = {"name": "intent", "schema": {"type": "object", "additionalProperties": False, "required": ["intent"],
                 "properties": {"intent": {"type": "string", "enum": INTENTS}}}}
INTENT_PROMPT = (
    "Classify one message from a member of a family care circle looking after an elderly relative. Choose exactly one intent:\n"
    "- dose_update: reports that a dose was given, skipped, or the sender is unsure (including short replies like 'done').\n"
    "- record_question: asks what the care record says (what is due, who gave a dose, who is on duty, how many medicines, a time).\n"
    "- correction: says something in a drafted schedule is wrong or gives a fix for it.\n"
    "- volunteer: offers to take a task (e.g. 'I will', 'I can take that').\n"
    "- medical_question: asks for medical advice or information (doses, interactions, what a medicine is for, whether something is safe, what a value means).\n"
    "- urgent_symptom: describes a person currently having a worrying or emergency symptom (chest pain, confusion, collapse, difficulty breathing).\n"
    "- other: anything else.\n"
    "A draft schedule is {draft} awaiting confirmation. Message: \"{text}\"")

PARSE_SCHEMA = lambda slots: {"name": "confirmation", "schema": {"type": "object", "additionalProperties": False, "required": ["actor", "slot", "action"], "properties": {
    "actor": {"type": "string", "enum": ["m1", "m2", "m3", "m4", "m5", "patient"]},
    "slot": {"type": "string", "enum": slots + ["none"]},
    "action": {"type": "string", "enum": ["given", "skipped", "unsure"]}}}}
PARSE_PROMPT = (
    "You log dose confirmations for a family care circle. Coordination only: give no medical advice. Circle members: {members}; 'patient' is the "
    "person being cared for, called Nanaji. Medication schedule slots (medicine_time): {slots}. Currently open (due, unconfirmed) slots: {open}. "
    "The message was typed or transcribed from a voice note (English, Hindi, Punjabi or a mix). The sender is {sender}. "
    "Return who gave the dose (actor), which slot it is about, and the action. actor = m1..m5 for the circle member who gave the dose, or 'patient' if he took it himself. "
    "For skipped or unsure, actor is the member the note names, otherwise the sender. If the message names no specific dose and exactly the open slots are meant, use slot 'none'. "
    "action = given, skipped or unsure. Message: \"{text}\"")

CORR_SCHEMA = {"name": "corrections", "schema": {"type": "object", "additionalProperties": False, "required": ["ops"], "properties": {"ops": {"type": "array", "items": {
    "type": "object", "additionalProperties": False, "required": ["line", "field", "value"], "properties": {
        "line": {"type": "integer"}, "field": {"type": "string", "enum": ["name", "dose_amount", "dose_unit", "frequency", "times", "with_food", "remove"]},
        "value": {"type": "string"}}}}}}}
CORR_PROMPT = ("A member is correcting a drafted medicine schedule. The draft is:\n{draft}\nTurn the member's message into edit operations. "
               "line = the line number; field = what to change; value = the new value as plain text (times as comma-separated HH:MM 24h; "
               "dose_unit one of mg, mcg, g, mL, units, tablet, puff, drop; frequency one of once_daily, twice_daily, three_times_daily, four_times_daily, "
               "every_n_hours, at_bedtime, as_needed, weekly; with_food one of yes, no, unspecified; use field 'remove' with empty value to delete a line). "
               "Only include changes the member actually stated. Message: \"{text}\"")

QA_PROMPT = ("You answer questions about a family's care record. Use ONLY the JSON record below. Answer in one or two short plain sentences, "
             "naming people by first name. If the record does not contain the answer say \"The record doesn't say.\" Give no medical advice and "
             "add nothing that is not in the record. Begin yes/no questions with Yes or No. Always say who did it (use 'himself' when the record says "
             "Nanaji himself) and include any recorded reason or note, such as why a dose was skipped. When asked what is due, list each medicine "
             "with its time as HH:MM. 'on_duty_tonight' is who is on duty tonight.\nRecord: {rec}\nQuestion: \"{text}\"")


def nm(conn, mid):
    if mid == "patient":
        return config.PATIENT_NAME
    m = record.member(conn, mid)
    return m["name"] if m else mid


def _send(ob, mid, text, reason, sender_text=""):
    return ob.send(mid, text, reason, sender_text)


def handle(conn, ob, mid, text=None, media=None):
    """media: {'path': str, 'mime': str}. Returns {'route','type','intent','replies'} for reporting and tests."""
    now = clock.now()
    record.touch_inbound(conn, mid, now)
    n0 = len(ob.sent)
    kind = "text" if not media else media["mime"].split("/")[0]
    audit(conn, "inbound", mid, {"kind": kind, "text": text if not media else None})
    res = {"route": kind, "type": None, "intent": None}
    if media and kind == "image":
        res["type"] = _image(conn, ob, mid, media["path"], now)
    elif media and kind == "audio":
        transcript = voice.transcribe(media["path"], f"{mid}-{now.strftime('%H%M%S')}")
        audit(conn, "transcript", mid, transcript, "voice note transcribed")
        res["intent"] = _text(conn, ob, mid, transcript, via="voice")
    elif media:
        _send(ob, mid, "I can read photos and voice notes; I can't open this kind of file.", "unsupported media")
    else:
        res["intent"] = _text(conn, ob, mid, text or "")
    res["replies"] = ob.sent[n0:]
    return res


# ---------------- images ----------------
def _image(conn, ob, mid, path, now):
    cur = conn.execute("INSERT INTO documents(path,sender,status,created_at) VALUES(?,?,?,?)", (str(path), mid, "new", record.iso(now)))
    doc = cur.lastrowid
    p, _ = vision.prep(path, f"doc{doc}")
    typ, conf = vision.classify(p, doc)
    conn.execute("UPDATE documents SET type=?, confidence=? WHERE id=?", (typ, conf, doc))
    conn.commit()
    audit(conn, "image_classified", mid, {"doc": doc, "type": typ, "confidence": round(conf, 2)}, "intake router")
    if conf < config.IMAGE_CONF_THRESHOLD or typ == "other":
        conn.execute("UPDATE documents SET status='awaiting_type' WHERE id=?", (doc,))
        conn.commit()
        _send(ob, mid, "I'm not sure what this photo is. Is it a discharge sheet, a prescription, a pill organiser or a lab report?", f"low confidence ({conf:.2f}) on doc {doc}")
        return "ask"
    _process_doc(conn, ob, mid, doc, typ, p, now)
    return typ


def _process_doc(conn, ob, mid, doc, typ, prepped, now):
    if typ in ("discharge_sheet", "prescription"):
        meds = vision.extract(prepped, doc)
        conn.execute("UPDATE documents SET extraction_json=?, status='extracted', type=? WHERE id=?", (json.dumps(meds), typ, doc))
        record.add_draft(conn, doc, meds, record.iso(now))
        summ = record.draft_summary(conn)
        extra = ""
        if any(not l["times"] for l in record.lines(conn, "draft")):
            extra = "\nSome lines have no clock time printed; tell me the time for each (for example 'line 2 at 08:00') before they can start."
        audit(conn, "draft_created", mid, {"doc": doc, "lines": len(summ)}, "extraction saved as draft; nothing live until a member says YES")
        _send(ob, mid, "Here's what I read:\n" + "\n".join(summ) + extra + "\nReply YES to start this schedule, or tell me what's wrong.", "draft summary sent for confirmation")
    elif typ == "pill_organiser":
        states = vision.organiser_states(prepped, doc)
        n, overlay = 0, None
        try:
            n, overlay = vision.sam_overlay(prepped, doc, ROOT / "data" / "overlays" / f"doc{doc}.jpg")
        except Exception as e:  # SAM is evidence only; never block the audit
            audit(conn, "sam_error", mid, type(e).__name__, "SAM evidence overlay failed")
        conn.execute("UPDATE documents SET extraction_json=?, overlay_path=?, status='audited' WHERE id=?", (json.dumps(states), overlay, doc))
        conn.commit()
        audit(conn, "organiser_sam", mid, {"doc": doc, "masks": n, "overlay_stored": bool(overlay)}, "SAM overlay stored only when exactly 14 masks")
        if not record.slots(conn):
            _send(ob, mid, "I need a confirmed schedule before I can compare the organiser with the record.", "organiser without schedule")
            return
        diffs = record.week_compare(conn, states, now)
        for comp, sentence in diffs:
            audit(conn, "organiser_disagreement", mid, f"{comp} {states[comp]}, {sentence.split('; ')[-1] if '; ' in sentence else sentence}", "organiser vs record")
        if diffs:
            _send(ob, mid, "Compared with the record this week:\n" + "\n".join("- " + s for _, s in diffs), "organiser disagreements with the record")
        else:
            audit(conn, "organiser_ok", mid, f"doc {doc}", "organiser agrees with the record")
            _send(ob, mid, "The organiser agrees with the record for this week so far.", "organiser matches record")
    elif typ == "lab_report":
        conn.execute("UPDATE documents SET status='stored' WHERE id=?", (doc,))
        record.add_task(conn, f"Discuss lab report #{doc} with the doctor", None, f"document {doc}", record.iso(now))
        audit(conn, "lab_report_stored", mid, {"doc": doc}, "lab report stored, not interpreted")
        _send(ob, mid, FIXED_LAB, "lab report stored; fixed reply")
    else:
        conn.execute("UPDATE documents SET status='stored' WHERE id=?", (doc,))
        conn.commit()
        _send(ob, mid, "Saved. " + HELP, "other image")


# ---------------- text ----------------
def _text(conn, ob, mid, text, via="text"):
    now = clock.now()
    low = re.sub(r"[^a-z ]", "", text.lower()).strip()
    # pending image-type question
    pend = conn.execute("SELECT * FROM documents WHERE sender=? AND status='awaiting_type' ORDER BY id DESC LIMIT 1", (mid,)).fetchone()
    if pend:
        for typ, rx in TYPE_WORDS:
            if re.search(rx, text.lower()):
                p, _ = vision.prep(pend["path"], f"doc{pend['id']}")
                conn.execute("UPDATE documents SET type=?, status='typed' WHERE id=?", (typ, pend["id"]))
                _process_doc(conn, ob, mid, pend["id"], typ, p, now)
                return "image_type_answer"
    has_draft = bool(record.lines(conn, "draft"))
    if has_draft and low in YES:
        n = record.confirm_drafts(conn, mid, record.iso(now))
        audit(conn, "schedule_confirmed", mid, {"lines": n}, "member said YES")
        left = len(record.lines(conn, "draft"))
        _send(ob, mid, f"Schedule started: {n} medicine(s) are now live." + (f" {left} line(s) still need a time." if left else "") + " I'll check in on each dose.", "YES received")
        ob.relay(f"{nm(conn, mid)} confirmed the schedule for {config.PATIENT_NAME}: {n} medicine(s) are now live.", [mid], "state change: schedule confirmed")
        return "yes"
    intent, _, _ = llm.spark_json("phase1", "intent", [{"role": "user", "content": INTENT_PROMPT.format(draft="pending" if has_draft else "not pending", text=text)}], INTENT_SCHEMA)
    intent = intent["intent"]
    audit(conn, "intent", mid, {"intent": intent, "via": via}, "classified by model; routing is code")
    {"dose_update": _dose, "record_question": _qa, "correction": _correction, "volunteer": _volunteer,
     "medical_question": _medical, "urgent_symptom": _urgent}.get(intent, _other)(conn, ob, mid, text, now)
    return intent


def _dose(conn, ob, mid, text, now):
    sl = record.slots(conn)
    if not sl:
        _send(ob, mid, "There's no confirmed schedule yet. Send a photo of the discharge sheet first.", "dose update without schedule", text)
        return
    opens = record.open_occurrences(conn, now)
    mem = "; ".join(f"{m['id']} = {m['name']} ({m['relationship']})" for m in record.members(conn))
    r, _, _ = llm.spark_json("phase1", "parse", [{"role": "user", "content": PARSE_PROMPT.format(members=mem, slots=", ".join(sl), open=", ".join(s for s, _ in opens) or "none", sender=mid, text=text)}], PARSE_SCHEMA(sl))
    slot, d = r["slot"], None
    if slot == "none":
        if len(opens) == 1:
            slot, d = opens[0]
        elif len(opens) == 0:
            _send(ob, mid, "Nothing is waiting for confirmation right now. Which dose do you mean?", "dose update with no open dose", text)
            return
        else:
            _send(ob, mid, "Which dose do you mean? Waiting: " + ", ".join(s.replace("_", " ") for s, _ in opens), "ambiguous dose update", text)
            return
    typ, d = record.log_confirmation(conn, slot, r["action"], r["actor"], mid, f"msg from {mid}", None, now, d)
    who = nm(conn, r["actor"])
    label = slot.replace("_", " ")
    verb = {"given": "gave", "skipped": "skipped", "unsure": "wasn't sure about"}[r["action"]]
    pre = "late: " if typ == "late_confirmed" else ""
    audit(conn, "dose_event", mid, {"slot": slot, "type": typ, "actor": r["actor"], "date": str(d)}, "dose update parsed against the live schedule")
    _send(ob, mid, f"Logged: {pre}{label} {r['action']} ({who}). Thanks.", "dose update logged", text)
    verb_line = f"{who} {verb} {label}." if r["actor"] != "patient" else f"{config.PATIENT_NAME} took {label} himself." if r["action"] == "given" else f"{label}: {r['action']}."
    ob.relay("CareCircle: " + verb_line, [mid], "state change: dose event")


def _qa(conn, ob, mid, text, now):
    rec = json.dumps(record.snapshot(conn, now))
    ans, dt, usd, raw = llm.spark("phase1", "record-answer", [{"role": "user", "content": QA_PROMPT.format(rec=rec, text=text)}])
    audit(conn, "record_answer", mid, {"q": text, "a": ans}, "read-only answer from the record")
    _send(ob, mid, ans.strip(), "record question answered from the record", text)


def _correction(conn, ob, mid, text, now):
    drafts = record.lines(conn, "draft")
    if not drafts:
        record.add_task(conn, f"Correction requested by {nm(conn, mid)}: {text}", None, "correction", record.iso(now))
        _send(ob, mid, "I can only change a draft schedule myself. I've noted this as a task for the circle.", "correction without draft", text)
        return
    r, _, _ = llm.spark_json("phase1", "correction", [{"role": "user", "content": CORR_PROMPT.format(draft="\n".join(record.draft_summary(conn)), text=text)}], CORR_SCHEMA)
    ops = []
    for o in r["ops"]:
        f, v = o["field"], o["value"].strip()
        if f == "times" and not all(re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t.strip()) for t in v.split(",") if t.strip()):
            continue
        if f == "dose_unit" and v not in vision.DOSE_UNITS or f == "frequency" and v not in vision.FREQS or f == "with_food" and v not in vision.FOOD:
            continue
        if f == "dose_amount":
            try:
                float(v)
            except ValueError:
                continue
        ops.append({"line": o["line"], "field": f, "value": v})
    applied = record.apply_ops(conn, ops)
    audit(conn, "draft_corrected", mid, {"applied": [list(map(str, a)) for a in applied]}, "correction applied to the draft")
    if not applied:
        _send(ob, mid, "I couldn't tell what to change. You can say, for example, 'line 2 should be 08:00'.", "correction not understood", text)
        return
    _send(ob, mid, "Updated:\n" + "\n".join(record.draft_summary(conn)) + "\nReply YES to start this schedule, or tell me what's wrong.", "draft re-summarised after correction", text)


def _volunteer(conn, ob, mid, text, now):
    t = record.assign_oldest_unowned(conn, mid)
    if t:
        audit(conn, "task_assigned", mid, t, "member volunteered")
        _send(ob, mid, f"Thanks, this task is yours: {t['text']}", "volunteer assigned an open task", text)
        ob.relay(f"{nm(conn, mid)} took a task: {t['text']}", [mid], "state change: task owner set")
    else:
        _send(ob, mid, "Thanks. There's no open task waiting for an owner right now.", "volunteer with no open task", text)


def _medical(conn, ob, mid, text, now):
    record.add_task(conn, f"Ask the doctor: {text}", None, "medical question", record.iso(now))
    audit(conn, "medical_question", mid, "fixed reply; question saved as a task for the doctor visit", "no advice given")
    _send(ob, mid, FIXED_MEDICAL, "medical question: fixed reply")


def _urgent(conn, ob, mid, text, now):
    audit(conn, "urgent_symptom", mid, "fixed urgent reply and immediate alert to awake real members", "urgent symptom reported")
    _send(ob, mid, FIXED_URGENT, "urgent symptom: fixed reply")
    for m in record.members(conn):
        if m["id"] == mid:
            continue
        alert = f"URGENT: {nm(conn, mid)} reported a worrying symptom for {config.PATIENT_NAME} and was told to call emergency services or the doctor now. Please check in."
        if m["kind"] == "sim" or (record.awake(m, now)):
            ob.send(m["id"], alert, "urgent symptom alert to awake member")
        else:
            audit(conn, "urgent_alert_skipped", m["id"], f"asleep (local {record.local_time(m, now).strftime('%H:%M')})", "urgent alert: member asleep")


def _other(conn, ob, mid, text, now):
    _send(ob, mid, HELP, "other message: help text", text)
