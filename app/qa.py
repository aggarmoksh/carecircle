"""Record questions answered by code. Spark maps the question to ONE query type with parameters (strict schema); code runs the query against
the record and returns facts; Spark only phrases those facts; code checks the phrasing is faithful (every fact token kept, no new number)
and the outbound guard checks it again. Unknown or unmappable question -> fixed reply. No interpretation of any value, ever."""
import json, re
from datetime import timedelta
from . import config, record, labs, llm

NOT_FOUND = "I can only answer from the care record; I couldn't find that."
QUERIES = ["dose_status", "due", "who_gave", "on_duty", "med_list", "med_time", "skip_reason", "lab_value", "out_of_range", "open_tasks", "unknown"]
DATES = ["today", "yesterday", "recent"]
PERIODS = ["morning", "evening", "tonight", "now"]

MAP_PROMPT = (
    "You map one question from a family care circle to a query on their care record. You do not answer it. Choose exactly one query:\n"
    "- dose_status: was a dose given / taken / skipped (slot, date)\n"
    "- due: what medicines are due in a window of the day (window: morning, evening, tonight, today, now, or a clock time HH:MM)\n"
    "- who_gave: who gave a dose, or who gave anything (slot or null, date)\n"
    "- on_duty: who is on duty / covering a period (period: morning, evening, tonight or now)\n"
    "- med_list: which medicines he is on, or how many\n"
    "- med_time: at what time a medicine is given (med)\n"
    "- skip_reason: why a dose was skipped or missed (slot, date)\n"
    "- lab_value: what ONE named lab test result was, or whether that one test is in range / within the printed range (test, report)\n"
    "- out_of_range: which lab values were outside the printed range (report)\n"
    "- open_tasks: what tasks are open\n"
    "- unknown: anything else, including questions about what a value or medicine means or whether something is safe or bad\n"
    "Parameters: slot = medicine_time from the list, or null; date = today, yesterday, or recent (the most recent occurrence that has already been due; "
    "use it when no day is named and the question is in the past tense); report = 'latest' or a report date YYYY-MM-DD; "
    "test = a test name from the list or null; med = a medicine name from the list or null. Set unused parameters to null.\n"
    "Today is {today}. Medication slots: {slots}. Medicine names: {meds}. Lab tests on record: {tests}. Lab report dates: {dates}.\n"
    "Question: \"{text}\"")


def schema(slots, meds, tests, dates):
    def nul(vals):
        return {"anyOf": [{"type": "string", "enum": vals}, {"type": "null"}]} if vals else {"type": "null"}
    return {"name": "record_query", "schema": {
        "type": "object", "additionalProperties": False, "required": ["query", "slot", "date", "window", "period", "med", "test", "report"],
        "properties": {"query": {"type": "string", "enum": QUERIES}, "slot": nul(slots), "date": nul(DATES), "window": {"type": ["string", "null"]},
                       "period": nul(PERIODS), "med": nul(meds), "test": nul(tests), "report": {"type": ["string", "null"]}}}}


def label(conn, mid):
    if mid == "patient":
        return f"{config.PATIENT_NAME} himself"
    m = record.member(conn, mid)
    if not m:
        return mid or ""
    return m["name"] + (" (simulated)" if m["kind"] == "sim" else "")


def _d(conn, now, mode, slot):
    today = now.astimezone(record.patient_tz(conn)).date()
    if mode == "yesterday":
        return today - timedelta(days=1)
    if mode == "today":
        return today
    return today if now >= record.due_at(conn, slot, today) else today - timedelta(days=1)  # recent


def _day_label(conn, now, d, slot):
    today = now.astimezone(record.patient_tz(conn)).date()
    if d == today:
        return "today"
    return "last night" if record.period_of(slot) == "evening" else "yesterday"


def _fact(conn, now, slot, d):
    st = record.status_of(conn, slot, d, now)
    es = record.events(conn, slot, d)
    res = [e for e in es if e["type"] in ("confirmed", "late_confirmed", "skipped", "unsure", "missed")]
    e = res[-1] if res else None
    med, tm = slot.rsplit("_", 1)
    line = next((l for l in record.lines(conn, "confirmed") if l["name"] == med), None)
    f = dict(medicine=med, dose=record.fmt_dose(line["dose_amount"], line["dose_unit"]) if line else None, time=tm, day=_day_label(conn, now, d, slot),
             status={"given": "given", "skipped": "skipped", "unsure": "unsure", "missed": "missed", "overdue": "overdue, not yet confirmed",
                     "due": "due, not yet confirmed", "not_yet_due": "not yet due"}[st])
    if e and e["type"] != "missed":
        f["by"] = label(conn, e["actor"])
        if e["reported_by"] and e["reported_by"] != e["actor"]:
            f["reported_by"] = label(conn, e["reported_by"])
        if e["note"]:
            f["reason"] = e["note"]
    return f


def _fact_text(f):
    s = f"{f['medicine']} {f['time']} ({f['day']}): {f['status']}"
    if f.get("by"):
        s += f", by {f['by']}"
    if f.get("reported_by"):
        s += f", reported by {f['reported_by']}"
    if f.get("reason"):
        s += f", reason: {f['reason']}"
    return s


def _slots_for(conn, p):
    sl = record.slots(conn)
    if p.get("slot"):
        return [p["slot"]]
    if p.get("med"):
        return [s for s in sl if s.rsplit("_", 1)[0] == p["med"]]
    return sl


def run(conn, p, now):
    """Run the mapped query against the record. Returns {'facts': [...], 'plain': [...]} or None when there is nothing to answer from."""
    q = p["query"]
    mode = p.get("date") or "recent"
    if q in ("dose_status", "who_gave", "skip_reason"):
        sl = _slots_for(conn, p)
        if not sl:
            return None
        facts = []
        if p.get("slot") or p.get("med"):
            for s in sl:
                facts.append(_fact(conn, now, s, _d(conn, now, mode, s)))
        else:  # no slot named: everything resolved today and last night
            today = now.astimezone(record.patient_tz(conn)).date()
            for s in sl:
                for d in (today, today - timedelta(days=1)):
                    if d == today or record.period_of(s) == "evening":
                        f = _fact(conn, now, s, d)
                        if f.get("by") or f["status"] in ("overdue, not yet confirmed",):
                            facts.append(f)
        if q == "skip_reason":
            facts = [f for f in facts if f["status"] in ("skipped", "unsure", "missed")]
        if q == "who_gave" and not (p.get("slot") or p.get("med")):
            grouped = {}
            for f in facts:
                if f["status"] == "given":
                    grouped.setdefault(f["by"], []).append(f"{f['medicine']} {f['dose']} at {f['time']} ({f['day']})")
            facts = [dict(window="today and last night (last night's evening doses count as part of today's care)", given_by=grouped or "nobody has a dose recorded as given")]
            plain = [(f"{who} took: " if who == f"{config.PATIENT_NAME} himself" else f"{who} gave: ") + "; ".join(v) for who, v in grouped.items()]
            return dict(facts=facts, plain=plain or ["No dose is recorded as given."])
        return dict(facts=facts, plain=[_fact_text(f) for f in facts] or ["Nothing is recorded for that."])
    if q == "due":
        w = (p.get("window") or "today").strip().lower()
        sl = record.slots(conn)
        m = re.fullmatch(r"(\d{1,2})(?::(\d\d))?\s*(am|pm)?", w)
        if m and m.group(3) == "pm" and int(m.group(1)) < 12:
            w = f"{int(m.group(1)) + 12}:{m.group(2) or '00'}"
            m = re.fullmatch(r"(\d{1,2})(?::(\d\d))?", w)
        if w in ("morning", "am"):
            pick = [s for s in sl if record.period_of(s) == "morning"]
        elif w in ("evening", "tonight", "night", "pm"):
            pick = [s for s in sl if record.period_of(s) == "evening"]
        elif w == "now":
            today = now.astimezone(record.patient_tz(conn)).date()
            pick = [s for s in sl if record.status_of(conn, s, today, now) in ("due", "overdue")]
        elif m:
            hh, mm = int(m.group(1)), int(m.group(2) or 0)
            pick = [s for s in sl if s.rsplit("_", 1)[1] == f"{hh:02d}:{mm:02d}"]
        else:
            pick = sl
        today = now.astimezone(record.patient_tz(conn)).date()
        facts = [_fact(conn, now, s, today) for s in sorted(pick, key=lambda s: s.rsplit("_", 1)[1])]
        return dict(facts=facts, plain=[f"{f['medicine']} {f['dose']} at {f['time']} ({f['status']})" for f in facts] or ["No medicines are scheduled for that."])
    if q == "on_duty":
        per = p.get("period") or "now"
        if per == "now":
            per = "morning" if now.astimezone(record.patient_tz(conn)).hour < 12 else "evening"
        per = "evening" if per == "tonight" else per
        r = conn.execute("SELECT member_id FROM rota WHERE period=?", (per,)).fetchone()
        if not r:
            return None
        who = label(conn, r["member_id"])
        return dict(facts=[dict(period=per, on_duty=who)], plain=[f"{who} is on duty for the {per} doses."])
    if q == "med_list":
        ls = record.lines(conn, "confirmed")
        if not ls:
            return None
        names = sorted({l["name"] for l in ls})
        facts = [dict(count=len(names), medicines=[dict(medicine=l["name"], dose=record.fmt_dose(l["dose_amount"], l["dose_unit"]), times=l["times"]) for l in ls])]
        return dict(facts=facts, plain=[f"{len(names)} medicines."] + [f"{l['name']} {record.fmt_dose(l['dose_amount'], l['dose_unit'])} at {', '.join(l['times'])}" for l in ls])
    if q == "med_time":
        if not p.get("med"):
            return None
        ls = [l for l in record.lines(conn, "confirmed") if l["name"] == p["med"]]
        if not ls:
            return None
        facts = [dict(medicine=l["name"], dose=record.fmt_dose(l["dose_amount"], l["dose_unit"]), times=l["times"]) for l in ls]
        return dict(facts=facts, plain=[f"{f['medicine']} {f['dose']} at {', '.join(f['times'])}" for f in facts])
    if q in ("lab_value", "out_of_range"):
        reps = labs.live_reports(conn)
        if not reps:
            return None
        want = (p.get("report") or "latest").strip().lower()
        if q == "lab_value":
            if not p.get("test"):
                return None
            cand = [r for r in reps if any(t["test"] == p["test"] for t in r["tests"])]
            if want != "latest":
                cand = [r for r in cand if r["report_date"] == want]
            if not cand:
                return None
            r = cand[-1]
            t = next(t for t in r["tests"] if t["test"] == p["test"])
            f = dict(test=t["test"], value=labs.fmt_num(t["value"]), unit=t["unit"], printed_range_text=t["range_text"] or None, status=t["status"],
                     wording=labs.range_phrase(t), report_date=labs.pretty_date(r["report_date"]))
            return dict(facts=[f], plain=[f"{labs.value_line(t)} ({labs.pretty_date(r['report_date'])})"])
        r = reps[-1] if want == "latest" else next((x for x in reps if x["report_date"] == want), None)
        if not r:
            return None
        oor = labs.out_of_range(r["tests"])
        facts = [dict(report_date=labs.pretty_date(r["report_date"]), outside=[dict(test=t["test"], value=labs.fmt_num(t["value"]), unit=t["unit"], status=t["status"]) for t in oor])]
        plain = [f"{labs.pretty_date(r['report_date'])} report: {len(oor)} value(s) outside the lab's printed range."] + [f"{t['test']}: {labs.fmt_num(t['value'])} {t['unit']}, {t['status']} the lab's printed range" for t in oor]
        return dict(facts=facts, plain=plain)
    if q == "open_tasks":
        rows = conn.execute("SELECT text, owner FROM tasks WHERE status='open' ORDER BY id").fetchall()
        facts = [dict(task=r["text"], owner=label(conn, r["owner"]) if r["owner"] else "nobody yet") for r in rows]
        return dict(facts=facts, plain=[f"{f['task']} (owner: {f['owner']})" for f in facts] or ["There are no open tasks."])
    return None


PHRASE_PROMPT = (
    "You phrase an answer for a family care circle from FACTS taken from their care record. Use only the facts: add nothing, infer nothing, and give no medical advice "
    "or explanation of what any value means. Answer the question in one or two short plain sentences (a short list is fine for several items). "
    "Begin a yes/no question with Yes or No; answer Yes when any fact in the stated window answers it, and name when it happened (for example 'last night').Keep every name, time, number, unit and reason from the facts that bears on the question; "
    "use the words 'within', 'above' or 'below' 'the lab's printed range' exactly as in the facts. The key 'Nanaji himself' means Nanaji took the dose himself; the other keys are the people who gave doses.\n"
    "Question: \"{text}\"\nFACTS: {facts}")


def _tokens(s):
    return set(re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", s.lower()))


def faithful(ans, facts_json, text):
    """No number in the answer that is not in the facts or the question."""
    allowed = _tokens(facts_json) | _tokens(text)
    nums = {n for n in _tokens(ans) if re.fullmatch(r"\d+(?:\.\d+)?", n)}
    return nums <= allowed


def answer(conn, text, now):
    """Returns (answer_text, info) where info records the mapping, facts and phrasing source for the audit log and the evals."""
    sl, ls = record.slots(conn), record.lines(conn, "confirmed")
    meds = sorted({l["name"] for l in ls})
    reps = labs.live_reports(conn)
    tests = sorted({t["test"] for r in reps for t in r["tests"]})
    dates = [r["report_date"] for r in reps]
    today = now.astimezone(record.patient_tz(conn)).strftime("%Y-%m-%d %H:%M")
    p, _, _ = llm.spark_json("phase2", "qa-map", [{"role": "user", "content": MAP_PROMPT.format(today=today, slots=", ".join(sl) or "none", meds=", ".join(meds) or "none", tests=", ".join(tests) or "none", dates=", ".join(dates) or "none", text=text)}], schema(sl, meds, tests, dates))
    info = dict(mapping=p)
    if p["query"] == "unknown":
        return NOT_FOUND, dict(info, source="fixed: unmappable")
    r = run(conn, p, now)
    if not r or not r["facts"]:
        return NOT_FOUND, dict(info, source="fixed: nothing in the record")
    info["facts"] = r["facts"]
    fj = json.dumps(r["facts"], ensure_ascii=False)
    ans, _, _, _ = llm.spark("phase2", "qa-phrase", [{"role": "user", "content": PHRASE_PROMPT.format(text=text, facts=fj)}])
    ans = (ans or "").strip()
    if not ans or not faithful(ans, fj, text):
        info["source"] = "code fallback: phrasing added a number not in the facts"
        return " ".join(r["plain"]) if len(r["plain"]) == 1 else "\n".join(r["plain"]), info
    info["source"] = "spark phrasing"
    return ans, info
