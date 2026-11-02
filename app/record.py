"""Care record logic. Decisions live here (code + record); the LLM only parses and phrases."""
import json
from datetime import datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo
from . import config

RESOLVED = ("confirmed", "late_confirmed", "skipped", "unsure", "missed")
DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
DAY_NAMES = {"MON": "Monday", "TUE": "Tuesday", "WED": "Wednesday", "THU": "Thursday", "FRI": "Friday", "SAT": "Saturday", "SUN": "Sunday"}


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# ---------- members ----------
def members(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM members ORDER BY id")]


def member(conn, mid):
    r = conn.execute("SELECT * FROM members WHERE id=?", (mid,)).fetchone()
    return dict(r) if r else None


PREFS = {"everything": "every update", "duties": "only your own duties and alerts", "daily": "one summary a day at 8 PM plus alerts", "stop": "no messages until you write again"}


def set_relay_pref(conn, mid, pref):
    assert pref in PREFS
    conn.execute("UPDATE members SET relay_pref=? WHERE id=?", (pref, mid))
    conn.commit()


def local_time(m, now):
    return now.astimezone(ZoneInfo(m["tz"]))


def awake(m, now):
    h = local_time(m, now).hour
    return config.WAKE_START <= h < config.WAKE_END


def window_open(m, now):
    if m["kind"] == "sim":
        return True
    if not m.get("last_inbound_at"):
        return False
    last = datetime.fromisoformat(m["last_inbound_at"].replace("Z", "+00:00"))
    return now - last < timedelta(hours=config.WINDOW_HOURS)


def touch_inbound(conn, mid, now):
    conn.execute("UPDATE members SET last_inbound_at=? WHERE id=?", (iso(now), mid))
    conn.commit()


def patient_tz(conn):
    r = conn.execute("SELECT patient_tz FROM circle LIMIT 1").fetchone()
    return ZoneInfo(r["patient_tz"] if r else config.PATIENT_TZ)


# ---------- schedule ----------
def period_of(slot):
    return "morning" if int(slot.rsplit("_", 1)[1][:2]) < 12 else "evening"


def lines(conn, status):
    rows = conn.execute(
        "SELECT l.id lid, l.times_json, l.status, l.source_doc_id, l.confirmed_at, m.id mid, m.name, m.dose_amount, m.dose_unit, "
        "m.frequency, m.with_food, m.notes, m.name_as_printed, m.generic_if_printed, m.legibility FROM schedule_lines l JOIN medications m ON m.id=l.med_id "
        "WHERE l.status=? ORDER BY l.id", (status,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["times"] = json.loads(d.pop("times_json"))
        out.append(d)
    return out


def slots(conn, status="confirmed"):
    return [f"{l['name']}_{t}" for l in lines(conn, status) for t in l["times"]]


def fmt_dose(amount, unit):
    return f"{amount:g} {unit}"


def add_draft(conn, doc_id, meds, now_iso):
    for old in conn.execute("SELECT id, med_id FROM schedule_lines WHERE status='draft'").fetchall():
        conn.execute("DELETE FROM schedule_lines WHERE id=?", (old["id"],))
        conn.execute("DELETE FROM medications WHERE id=?", (old["med_id"],))
    for m in meds:
        cur = conn.execute("INSERT INTO medications(name,dose_amount,dose_unit,frequency,with_food,notes,name_as_printed,generic_if_printed,legibility) VALUES(?,?,?,?,?,?,?,?,?)",
                           (m["name"].strip().lower(), float(m["dose_amount"]), m["dose_unit"], m["frequency"], m["with_food"], m.get("notes", ""),
                            m.get("name_as_printed", ""), m.get("generic_if_printed", ""), m.get("legibility", "clear")))
        conn.execute("INSERT INTO schedule_lines(med_id,times_json,status,source_doc_id,created_at) VALUES(?,?,?,?,?)",
                     (cur.lastrowid, json.dumps(sorted(m["times"])), "draft", doc_id, now_iso))
    conn.commit()


def draft_summary(conn):
    out = []
    for i, l in enumerate(lines(conn, "draft"), 1):
        t = ", ".join(l["times"]) if l["times"] else "no clock time printed"
        food = {"yes": "with food", "no": "before food", "unspecified": ""}[l["with_food"]]
        out.append(f"{i}. " + ("? " if l["legibility"] == "unsure" else "") + f"{l['name']} {fmt_dose(l['dose_amount'], l['dose_unit'])}, {l['frequency'].replace('_', ' ')}, {t}" + (f", {food}" if food else ""))
    return out


def unsure_lines(conn):
    """1-based numbers of draft lines the extraction marked unsure and nobody has corrected yet."""
    return [i for i, l in enumerate(lines(conn, "draft"), 1) if l["legibility"] == "unsure"]


def confirm_drafts(conn, by, now_iso):
    n = 0
    for l in lines(conn, "draft"):
        if l["times"]:  # a line with no printed clock time is never given an inferred time
            conn.execute("UPDATE schedule_lines SET status='confirmed', confirmed_by=?, confirmed_at=? WHERE id=?", (by, now_iso, l["lid"]))
            n += 1
    conn.commit()
    return n


def apply_ops(conn, ops):
    """Apply validated correction ops to the draft. op: {line: int (1-based), field, value}."""
    ds = lines(conn, "draft")
    applied = []
    for op in ops:
        i = op["line"] - 1
        if not 0 <= i < len(ds):
            continue
        l, f, v = ds[i], op["field"], op["value"]
        if f == "times":
            times = sorted(x for x in v.split(",") if x.strip()) if isinstance(v, str) else sorted(v)
            conn.execute("UPDATE schedule_lines SET times_json=? WHERE id=?", (json.dumps([t.strip() for t in times]), l["lid"]))
        elif f == "remove":
            conn.execute("DELETE FROM schedule_lines WHERE id=?", (l["lid"],))
        elif f in ("name", "dose_unit", "frequency", "with_food", "notes"):
            conn.execute(f"UPDATE medications SET {f}=? WHERE id=?", (str(v).strip().lower() if f == "name" else v, l["mid"]))
            if f == "name":  # the member typed the name: it is no longer a guess
                conn.execute("UPDATE medications SET legibility='clear' WHERE id=?", (l["mid"],))
        elif f == "dose_amount":
            conn.execute("UPDATE medications SET dose_amount=? WHERE id=?", (float(v), l["mid"]))
        else:
            continue
        applied.append((i + 1, f, v))
    conn.commit()
    return applied


# ---------- occurrences and events ----------
def due_at(conn, slot, d):
    hh, mm = slot.rsplit("_", 1)[1].split(":")
    return datetime.combine(d, dtime(int(hh), int(mm)), tzinfo=patient_tz(conn)).astimezone(timezone.utc)


def events(conn, slot, d):
    return [dict(r) for r in conn.execute("SELECT * FROM dose_events WHERE slot=? AND due_date=? ORDER BY id", (slot, str(d)))]


def status_of(conn, slot, d, now):
    ev = {e["type"] for e in events(conn, slot, d)}
    if ev & {"confirmed", "late_confirmed"}:
        return "given"
    for t in ("skipped", "unsure", "missed"):
        if t in ev:
            return t
    if ev & {"nudged", "escalated"}:
        return "overdue"
    if "due" in ev or now >= due_at(conn, slot, d):
        return "due"
    return "not_yet_due"


def add_event(conn, slot, d, typ, actor=None, reported_by=None, source=None, note=None, at=None):
    conn.execute("INSERT INTO dose_events(slot,due_date,type,actor,reported_by,source_message,note,at) VALUES(?,?,?,?,?,?,?,?)",
                 (slot, str(d), typ, actor, reported_by, source, note, at))
    conn.commit()


def resolve_date(conn, slot, now):
    """Which day's occurrence a message about `slot` refers to: today's if due within 2 h or already due, else yesterday's."""
    today = now.astimezone(patient_tz(conn)).date()
    return today if now >= due_at(conn, slot, today) - timedelta(hours=2) else today - timedelta(days=1)


def open_occurrences(conn, now):
    """Occurrences due and not resolved, for yesterday and today (patient tz)."""
    today = now.astimezone(patient_tz(conn)).date()
    out = []
    for d in (today - timedelta(days=1), today):
        for s in slots(conn):
            if now >= due_at(conn, s, d) and events(conn, s, d) and status_of(conn, s, d, now) in ("due", "overdue"):
                out.append((s, d))
    return out


def log_confirmation(conn, slot, action, actor, reported_by, source, note, now, d=None):
    d = d or resolve_date(conn, slot, now)
    ev = {e["type"] for e in events(conn, slot, d)}
    typ = {"given": "confirmed", "skipped": "skipped", "unsure": "unsure"}[action]
    if typ == "confirmed" and ev & {"escalated", "missed"}:
        typ = "late_confirmed"
    add_event(conn, slot, d, typ, actor, reported_by, source, note, iso(now))
    return typ, d


def next_due(conn, now):
    """(slot, due datetime) of the next scheduled dose strictly after now (patient timezone), or None."""
    today = now.astimezone(patient_tz(conn)).date()
    cands = [(s, due_at(conn, s, d)) for s in slots(conn) for d in (today, today + timedelta(days=1))]
    cands = [c for c in cands if c[1] > now]
    return min(cands, key=lambda c: c[1]) if cands else None


# ---------- rota ----------
def on_duty(conn, slot):
    r = conn.execute("SELECT member_id FROM rota WHERE period=?", (period_of(slot),)).fetchone()
    return r["member_id"] if r else None


# ---------- tasks ----------
def add_task(conn, text, owner, source, now_iso):
    cur = conn.execute("INSERT INTO tasks(text,owner,source,created_at) VALUES(?,?,?,?)", (text, owner, source, now_iso))
    conn.commit()
    return cur.lastrowid


def assign_oldest_unowned(conn, owner):
    r = conn.execute("SELECT id,text FROM tasks WHERE owner IS NULL AND status='open' ORDER BY id LIMIT 1").fetchone()
    if r:
        conn.execute("UPDATE tasks SET owner=? WHERE id=?", (owner, r["id"]))
        conn.commit()
    return dict(r) if r else None


# ---------- read-only snapshot for record questions ----------
def snapshot(conn, now):
    tz = patient_tz(conn)
    today = now.astimezone(tz).date()
    ms = {m["id"]: m for m in members(conn)}
    sched = [dict(name=l["name"], dose=fmt_dose(l["dose_amount"], l["dose_unit"]), times=l["times"], with_food=l["with_food"])
             for l in lines(conn, "confirmed")]
    ev = []
    for d, label in ((today, "today"), (today - timedelta(days=1), "last night / yesterday")):
        for s in slots(conn):
            es = events(conn, s, d)
            who = ""
            for e in es:
                if e["type"] in ("confirmed", "late_confirmed", "skipped", "unsure"):
                    who = ms[e["actor"]]["name"] if e["actor"] in ms else ("Nanaji himself" if e["actor"] == "patient" else (e["actor"] or ""))
            ev.append(dict(day=label, slot=s, status=status_of(conn, s, d, now), by=who, note=next((e["note"] for e in es if e["note"]), "")))
    rota = {r["period"]: ms[r["member_id"]]["name"] for r in conn.execute("SELECT * FROM rota")}
    tasks = [dict(text=r["text"], owner=ms[r["owner"]]["name"] if r["owner"] else None) for r in conn.execute("SELECT * FROM tasks WHERE status='open'")]
    later = [dict(medicine=s.rsplit("_", 1)[0], time=s.rsplit("_", 1)[1]) for s in slots(conn) if status_of(conn, s, today, now) == "not_yet_due"]
    return dict(patient=config.PATIENT_NAME, now_local=now.astimezone(tz).strftime("%Y-%m-%d %H:%M"), medicines_count=len(sched),
                schedule=sched, dose_status=ev, due_later_today=later, on_duty_tonight=rota.get("evening"), on_duty_this_morning=rota.get("morning"),
                rota_by_period=rota, open_tasks=tasks, members={k: v["name"] for k, v in ms.items()})


# ---------- organiser vs record ----------
def week_compare(conn, states, now):
    """states: {'MON_AM': 'full'|'empty', ...}. Returns [(compartment, sentence)] for compartments that disagree with the record."""
    today = now.astimezone(patient_tz(conn)).date()
    monday = today - timedelta(days=today.weekday())
    out = []
    for i, dn in enumerate(DAYS):
        d = monday + timedelta(days=i)
        for part in ("AM", "PM"):
            comp = f"{dn}_{part}"
            if comp not in states:
                continue
            per = [s for s in slots(conn) if period_of(s) == ("morning" if part == "AM" else "evening")]
            if not per or any(now < due_at(conn, s, d) for s in per):
                continue  # period not fully due yet: nothing to compare
            sts = [status_of(conn, s, d, now) for s in per]
            given = sum(x == "given" for x in sts)
            rest_skipped = all(x == "skipped" for x in sts if x != "given")
            label = f"{DAY_NAMES[dn]} {part}"
            if states[comp] == "full" and given < len(per) and not rest_skipped:
                out.append((comp, f"{label} is still full; no confirmation was logged"))
            elif states[comp] == "empty" and given < len(per):
                out.append((comp, f"{label} is empty but " + ("no confirmation was logged" if given == 0 else "only some doses were confirmed")))
    return out
