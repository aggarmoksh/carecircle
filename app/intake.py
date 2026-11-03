"""Intake router for every inbound message. The model classifies and parses; this code decides and writes the record.
image -> classify -> (discharge/prescription | organiser | lab report | ask) ; voice -> ffmpeg + transcribe -> text path ;
text -> intent {dose_update, record_question, correction, volunteer, medical_question, urgent_symptom, other}."""
import json, pathlib, re
from . import config, record, vision, voice, llm, labs, qa, tmpl
from .clock import clock
from .db import audit
from .outbox import FIXED_MEDICAL, FIXED_URGENT, FIXED_LAB

ROOT = pathlib.Path(__file__).resolve().parent.parent
INTENTS = ["dose_update", "record_question", "correction", "volunteer", "medical_question", "urgent_symptom", "relay_choice", "other"]
BOARD_RX = re.compile(r"(board|बोर्ड|tablero)[.!]?", re.I)
STOP_RX = re.compile(r"\s*stop\s*[.!]*\s*", re.I)
YES = {"yes", "y", "yes please", "yeah", "yep", "yes start", "yes thanks"}
TYPE_WORDS = [("discharge_sheet", r"discharge"), ("prescription", r"prescri"), ("pill_organiser", r"organi[sz]er|pill ?box|pill ?organi"), ("lab_report", r"\blab\b|report|blood test|results?")]
HELP = "I can log doses, answer questions from the care record, or save a photo of a discharge sheet, pill organiser or lab report."

INTENT_SCHEMA = {"name": "intent", "schema": {"type": "object", "additionalProperties": False, "required": ["intent"],
                 "properties": {"intent": {"type": "string", "enum": INTENTS}}}}
INTENT_PROMPT = (
    "Classify one message from a member of a family care circle looking after an elderly relative. Choose exactly one intent:\n"
    "- dose_update: reports that a dose was given, skipped, or the sender is unsure (including short replies like 'done').\n"
    "- record_question: asks what the care record says (what is due, who gave a dose, why a dose was skipped or missed, who is on duty, how many medicines, a time, what a lab value was, whether a value was inside or outside the lab's printed range, which values were outside it).\n"
    "- correction: says something in a drafted schedule is wrong or gives a fix for it.\n"
    "- volunteer: offers to take a task (e.g. 'I will', 'I can take that').\n"
    "- medical_question: asks for medical advice or information (doses, interactions, what a medicine is for, whether something is safe, whether a value is bad or dangerous, what a value or a result means, what a condition or an organ is doing).\n"
    "- urgent_symptom: describes a person currently having a worrying or emergency symptom (chest pain, confusion, collapse, difficulty breathing).\n"
    "- relay_choice: says how many updates from the app they want: every update, only their own duties and alerts, one daily summary at 8 PM, or that they want the messages to stop.\n"
    "- other: anything else.\n"
    "A draft schedule is {draft} awaiting confirmation. Message: \"{text}\"")

CHOICE_SCHEMA = {"name": "relay_choice", "schema": {"type": "object", "additionalProperties": False, "required": ["choice"],
                 "properties": {"choice": {"type": "string", "enum": ["everything", "duties", "daily", "stop"]}}}}
CHOICE_PROMPT = ("A circle member is choosing how many updates they get from the care app. Choose exactly one: everything (send me everything / every update), "
                 "duties (only my own duties and alerts), daily (one daily summary at 8 PM), stop (stop all messages). Message: \"{text}\"")
CHOICE_REPLY = {"everything": "Okay, I'll send you every update.", "duties": "Okay, you'll get only your own duties and alerts.",
                "daily": "Okay, you'll get one summary a day at 8 PM your time, plus alerts about missed doses.",
                "stop": "Okay, I've stopped all messages to you. Write to me any time to start again."}

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
               "dose_unit one of mg, mcg, g, mL, units, tablet, puff, drop, tsf, tbsp, sachet; frequency one of once_daily, twice_daily, three_times_daily, four_times_daily, "
               "every_n_hours, at_bedtime, as_needed, weekly; with_food one of yes, no, unspecified; use field 'remove' with empty value to delete a line). "
               "Only include changes the member actually stated. Message: \"{text}\"")


def nm(conn, mid):
    if mid == "patient":
        return config.PATIENT_NAME
    m = record.member(conn, mid)
    return m["name"] if m else mid


def _send(ob, mid, text, reason, sender_text="", free=False):
    return ob.send(mid, text, reason, sender_text, free=free)


def _lang(conn, mid):
    return (record.member(conn, mid) or {}).get("language") or "en"


def _fixed(conn, ob, mid, kind, reason, sender_text=""):
    """A fixed reply written by hand in the member's language."""
    code = _lang(conn, mid)
    return ob.send(mid, tmpl.fixed(kind, code), reason, sender_text, lang_used=code, english=tmpl.fixed(kind, "en"))


def handle(conn, ob, mid, text=None, media=None):
    """media: {'path': str, 'mime': str}. Returns {'route','type','intent','replies'} for reporting and tests."""
    now = clock.now()
    record.touch_inbound(conn, mid, now)
    if (record.member(conn, mid).get("relay_pref") or "everything") == "stop":  # writing again ends STOP
        record.set_relay_pref(conn, mid, "everything")
        audit(conn, "relay_pref", mid, "everything", "member wrote again, so STOP ended")
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
    typ, conf, hand = vision.classify(p, doc)
    conn.execute("UPDATE documents SET type=?, confidence=?, has_handwriting=? WHERE id=?", (typ, conf, int(hand), doc))
    conn.commit()
    audit(conn, "image_classified", mid, {"doc": doc, "type": typ, "confidence": round(conf, 2), "handwriting": hand}, "intake router")
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
        hand = bool(conn.execute("SELECT has_handwriting FROM documents WHERE id=?", (doc,)).fetchone()[0])
        record.add_draft(conn, doc, meds, record.iso(now), hand=hand)
        summ = record.draft_summary(conn)
        extra = ""
        if any(not l["times"] for l in record.lines(conn, "draft")):
            extra = "\nSome lines have no clock time printed; tell me the time for each (for example 'line 2 at 08:00') before they can start."
        if record.unsure_lines(conn):
            extra += "\nLines marked ? are hard to read" + (" (this sheet has handwriting, so every name needs your check)" if hand else "") + ". Please type the correct name for each (for example 'line 2 is metformin') before I can start."
        audit(conn, "draft_created", mid, {"doc": doc, "lines": len(summ)}, "extraction saved as draft; nothing live until a member says YES")
        _send(ob, mid, "Here's what I read:\n" + "\n".join(summ) + extra + "\nReply YES to start this schedule, or tell me what's wrong.", "draft summary sent for confirmation")
    elif typ == "pill_organiser":
        states = vision.organiser_states(prepped, doc)
        # Phase 3 decision (P3-real, 8 photos): Spark alone read 14/14 on all 8, SAM mapped all 14 compartments on 2 of 8, so SAM overlays are dropped
        # and Spark judges alone.
        conn.execute("UPDATE documents SET extraction_json=?, status='audited' WHERE id=?", (json.dumps(states), doc))
        conn.commit()
        if not record.slots(conn):
            _send(ob, mid, "I need a confirmed schedule before I can compare the organiser with the record.", "organiser without schedule")
            return
        diffs = record.week_compare(conn, states, now)
        for comp, sentence in diffs:
            audit(conn, "organiser_disagreement", mid, f"{comp} {states[comp]}, {sentence.split('; ')[-1] if '; ' in sentence else sentence}", "organiser vs record")
        if diffs:
            code = _lang(conn, mid)
            line = lambda c, s: tmpl.render("organiser_missed", code, day=c.split("_")[0], part=c.split("_")[1]) if s.endswith("that dose wasn't given") else s
            body = line(*diffs[0]) if len(diffs) == 1 else "Compared with the record this week:" + chr(10) + chr(10).join("- " + line(c, s) for c, s in diffs)
            ob.send(mid, body, "organiser disagreements with the record", lang_used=code if any(ord(ch) > 127 for ch in body) else "en", english=None)
        else:
            audit(conn, "organiser_ok", mid, f"doc {doc}", "organiser agrees with the record")
            _send(ob, mid, "The organiser agrees with the record for this week so far.", "organiser matches record")
    elif typ == "lab_report":
        try:
            rep = labs.extract(prepped, doc)
        except Exception as e:  # extraction failed: keep the report stored only, as in Phase 1
            rep = None
            audit(conn, "lab_extract_error", mid, type(e).__name__, "lab extraction failed; stored only")
        if not rep or not rep["tests"] or not re.fullmatch(r"\d{4}-\d\d-\d\d", rep["report_date"] or ""):
            conn.execute("UPDATE documents SET status='stored' WHERE id=?", (doc,))
            record.add_task(conn, f"Discuss lab report #{doc} with the doctor", None, f"document {doc}", record.iso(now))
            audit(conn, "lab_report_stored", mid, {"doc": doc}, "lab report stored, not interpreted")
            _send(ob, mid, FIXED_LAB, "lab report stored; fixed reply")
            return
        conn.execute("UPDATE documents SET extraction_json=?, status='extracted' WHERE id=?", (json.dumps(rep), doc))
        labs.save_draft(conn, doc, rep, record.iso(now))
        oor = labs.out_of_range(rep["tests"])
        within = [t["test"] for t in rep["tests"] if t["status"] == "within"]
        norange = [t["test"] for t in rep["tests"] if t["status"] == "no_range"]
        lines_ = [f"I read this lab report from {labs.pretty_date(rep['report_date'])}: {len(rep['tests'])} values, {len(oor)} outside the lab's printed range."]
        lines_ += ["- " + labs.value_line(t) for t in oor]
        if within:
            lines_.append("Within the lab's printed range: " + ", ".join(within) + ".")
        if norange:
            lines_.append("No range printed: " + ", ".join(norange) + ".")
        audit(conn, "lab_draft_created", mid, {"doc": doc, "tests": len(rep["tests"]), "outside_range": len(oor)}, "lab values saved as a draft; nothing live until a member says YES")
        _send(ob, mid, "\n".join(lines_) + "\nI can't interpret results. Reply YES if this matches the paper.", "lab draft summary sent for confirmation")
    else:
        conn.execute("UPDATE documents SET status='stored' WHERE id=?", (doc,))
        conn.commit()
        _send(ob, mid, "Saved. " + HELP, "other image")


# ---------------- text ----------------
PAST_ACTION = re.compile(r"\b(took|taken|gave|given|de di|dedi|diti|diya|le li|leli|khali|kha li|khaa li)\b|दे दी|दे दिया|दिया|दी\b|ले ली|लिया|खा ली|खा लिया|खाई|ਦਿੱਤ|ਦਿਤ|ਦੇ ਦਿ|ਲੈ ਲ|ਖਾ ਲ|ਖਾਧ", re.I)


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
    lab_draft = labs.draft(conn)
    newer_sched = has_draft and (record.lines(conn, "draft")[0]["source_doc_id"] or 0) > (lab_draft["doc_id"] or 0) if lab_draft else False
    if lab_draft and low in YES and not newer_sched:
        rep = labs.confirm_draft(conn, mid, record.iso(now))
        oor = labs.out_of_range(rep["tests"])
        when = labs.pretty_date(rep["report_date"])
        record.add_task(conn, f"Discuss the lab report from {when} with the doctor", None, "lab report", record.iso(now))
        audit(conn, "lab_confirmed", mid, {"report": rep["id"], "date": rep["report_date"], "outside_range": len(oor)}, "member said YES; lab values are live")
        _send(ob, mid, f"Saved. The lab report from {when} is now in the care record.", "YES received for lab report")
        ob.relay_t("lab_added", dict(member=nm(conn, mid), date=rep["report_date"], n=len(oor), link=True), [mid], "state change: lab report added")
        return "yes_lab"
    if has_draft and low in YES and record.unsure_lines(conn):
        nums = record.unsure_lines(conn)
        audit(conn, "yes_blocked", mid, f"unsure lines {nums}", "YES refused: a line is marked ? and needs the correct name")
        _send(ob, mid, f"Not started yet: line {', '.join(map(str, nums))} {'is' if len(nums) == 1 else 'are'} marked ?. Please type the correct name (for example 'line {nums[0]} is metformin'), or tell me to remove it.", "YES blocked by unsure line")
        return "yes_blocked"
    if has_draft and low in YES:
        n = record.confirm_drafts(conn, mid, record.iso(now))
        audit(conn, "schedule_confirmed", mid, {"lines": n}, "member said YES")
        left = len(record.lines(conn, "draft"))
        _send(ob, mid, f"Schedule started: {n} medicine(s) are now live." + (f" {left} line(s) still need a time." if left else "") + " I'll check in on each dose.", "YES received")
        ob.relay_t("schedule_live", dict(giver=nm(conn, mid), patient=config.PATIENT_NAME, n=n), [mid], "state change: schedule confirmed")
        return "yes"
    if BOARD_RX.fullmatch(text.strip()):
        ob.send_card(mid, "today_caption", "member asked for the board", patient=config.PATIENT_NAME)
        return "board"
    if STOP_RX.fullmatch(text):
        _set_pref(conn, ob, mid, "stop", text)
        return "relay_choice"
    intent, _, _ = llm.spark_json("phase1", "intent", [{"role": "user", "content": INTENT_PROMPT.format(draft="pending" if has_draft else "not pending", text=text)}], INTENT_SCHEMA)
    intent = intent["intent"]
    if intent in ("record_question", "other") and "?" not in text and "？" not in text and PAST_ACTION.search(text):
        audit(conn, "intent_override", mid, {"from": intent, "to": "dose_update"}, "a message that reports a past action and asks nothing is a dose report")
        intent = "dose_update"
    audit(conn, "intent", mid, {"intent": intent, "via": via}, "classified by model; routing is code")
    {"dose_update": _dose, "record_question": _qa, "correction": _correction, "volunteer": _volunteer,
     "medical_question": _medical, "urgent_symptom": _urgent, "relay_choice": _relay_choice}.get(intent, _other)(conn, ob, mid, text, now)
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
    groups = record.group_open(conn, now)
    if slot == "none":
        if len(groups) == 1:                       # 'done' with one dose time waiting: all of that time's medicines
            (d, _t), gs = groups[0]
            slot = gs[0]
        elif not groups:
            _send(ob, mid, "Nothing is waiting for confirmation right now. Which dose do you mean?", "dose update with no open dose", text)
            return
        else:
            _send(ob, mid, "Which dose do you mean? Waiting: " + "; ".join(f"{record.clock12(t)}: {record.med_names(gs)}" for (_d, t), gs in groups), "ambiguous dose update", text)
            return
    # doses due at the same time are one question: a reply that names medicines confirms those, any other reply confirms the whole time
    chosen = [slot]
    for (gd, gt), gs in groups:
        if slot in gs and (d is None or d == gd):
            low = text.lower()
            named = [x for x in gs if x.rsplit("_", 1)[0].lower() in low]
            chosen, d = (named or gs), gd
            break
    typ = None
    for sl in chosen:
        typ, d = record.log_confirmation(conn, sl, r["action"], r["actor"], mid, f"msg from {mid}", None, now, d)
        audit(conn, "dose_event", mid, {"slot": sl, "type": typ, "actor": r["actor"], "date": str(d)}, "dose update parsed against the live schedule")
    who = nm(conn, r["actor"])
    label = (record.med_names(chosen) + " " + chosen[0].rsplit("_", 1)[1]) if len(chosen) > 1 else chosen[0].replace("_", " ")
    verb = {"given": "gave", "skipped": "skipped", "unsure": "wasn't sure about"}[r["action"]]
    pre = "late: " if typ == "late_confirmed" else ""
    if r["action"] == "given" and typ == "confirmed":
        code = _lang(conn, mid)
        slots = dict(giver=who, meds=[x.rsplit("_", 1)[0] for x in chosen], time=chosen[0].rsplit("_", 1)[1])
        ob.send(mid, tmpl.render("logged", code, **slots), "dose update logged", text, lang_used=code, english=tmpl.render("logged", "en", **slots))
    else:
        _send(ob, mid, f"Logged: {pre}{label} {r['action']} ({who}). Thanks.", "dose update logged", text)
    verb_line = f"{who} {verb} {label}." if r["actor"] != "patient" else f"{config.PATIENT_NAME} took {label} himself." if r["action"] == "given" else f"{label}: {r['action']}."
    if r["action"] == "given" and r["actor"] != "patient":
        ob.relay_t("relay_given", dict(giver=who, patient=config.PATIENT_NAME, meds=[x.rsplit("_", 1)[0] for x in chosen], time=chosen[0].rsplit("_", 1)[1],
                                       clock=now.astimezone(record.patient_tz(conn)).strftime("%H:%M")), [mid], "state change: dose event")
    else:
        ob.relay("CareCircle: " + verb_line, [mid], "state change: dose event")


def _qa(conn, ob, mid, text, now):
    try:
        ans, info = qa.answer(conn, text, now)
    except Exception as e:  # never leave the member without a reply; never guess
        ans, info = qa.NOT_FOUND, {"error": type(e).__name__, "source": "fixed: error"}
    audit(conn, "record_answer", mid, {"q": text, "a": ans, "query": info.get("mapping"), "facts": info.get("facts"), "source": info.get("source")}, "answered by code from the record; Spark only phrased the facts")
    _send(ob, mid, ans, "record question answered from the record", text, free=True)


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
    _fixed(conn, ob, mid, "medical", "medical question: fixed reply")


def _urgent(conn, ob, mid, text, now):
    audit(conn, "urgent_symptom", mid, "fixed urgent reply and immediate alert to awake real members", "urgent symptom reported")
    _fixed(conn, ob, mid, "urgent", "urgent symptom: fixed reply")
    for m in record.members(conn):
        if m["id"] == mid:
            continue
        alert = f"URGENT: {nm(conn, mid)} reported a worrying symptom for {config.PATIENT_NAME} and was told to call emergency services or the doctor now. Please check in."
        if m.get("relay_pref") == "stop":
            audit(conn, "urgent_alert_skipped", m["id"], "chose STOP", "urgent alert: member chose STOP")
        elif m["kind"] == "sim" or (record.awake(m, now)):
            ob.send(m["id"], alert, "urgent symptom alert to awake member")
        else:
            audit(conn, "urgent_alert_skipped", m["id"], f"asleep (local {record.local_time(m, now).strftime('%H:%M')})", "urgent alert: member asleep")


def _set_pref(conn, ob, mid, choice, text):
    _send(ob, mid, CHOICE_REPLY[choice], f"relay choice: {choice}", text)  # sent before STOP takes effect
    record.set_relay_pref(conn, mid, choice)
    audit(conn, "relay_pref", mid, choice, "member chose how many updates to get")


def _relay_choice(conn, ob, mid, text, now):
    r, _, _ = llm.spark_json("phase3", "relay-choice", [{"role": "user", "content": CHOICE_PROMPT.format(text=text)}], CHOICE_SCHEMA)
    _set_pref(conn, ob, mid, r["choice"], text)


def _other(conn, ob, mid, text, now):
    _send(ob, mid, HELP, "other message: help text", text)
