"""Web board state and doctor summary. Read-only views of the care record; nothing here interprets a value or gives advice."""
import html, json
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from . import config, record, labs, labviz, activity
from .clock import clock

FOOTER = "Prepared by CareCircle from records kept by the family. Not medical advice."
CITY = lambda tz: tz.split("/")[-1].replace("_", " ")


def _name(ms, mid):
    if mid == "patient":
        return f"{config.PATIENT_NAME} himself"
    return ms[mid]["name"] if mid in ms else (mid or "")


def _organiser(conn, now):
    d = conn.execute("SELECT * FROM documents WHERE type='pill_organiser' AND status='audited' ORDER BY id DESC LIMIT 1").fetchone()
    if not d:
        return None
    states = json.loads(d["extraction_json"] or "{}")
    at = datetime.fromisoformat(d["created_at"].replace("Z", "+00:00"))
    mism = [dict(compartment=c, text=t) for c, t in record.week_compare(conn, states, at)] if record.slots(conn) else []
    return dict(doc=d["id"], at=d["created_at"], has_overlay=bool(d["overlay_path"]), states=states, mismatches=mism)


def _ladder(conn, now, ms):
    out = []
    today = now.astimezone(record.patient_tz(conn)).date()
    for slot, d in record.open_occurrences(conn, now):
        if d != today:
            continue
        steps = [dict(at=e["at"], who=_name(ms, e["actor"]), actor=e["actor"], kind=e["type"], note=e["note"]) for e in record.events(conn, slot, d) if e["type"] in ("nudged", "escalated")]
        skips = []
        # doses due at the same time are one question to the family: the scheduler logs a skip once for the group (against its first dose), so look across every dose at this time
        t = slot.rsplit("_", 1)[1]
        seen = set()
        for r in conn.execute("SELECT actor, detail, at FROM audit_log WHERE kind='escalation_skip' AND detail LIKE ? ORDER BY id", (f"%_{t} {d}: %",)):
            why = r["detail"].split(": ", 1)[1]
            if (r["actor"], why.split(" (")[0]) not in seen:
                seen.add((r["actor"], why.split(" (")[0]))
                skips.append(dict(who=_name(ms, r["actor"]), actor=r["actor"], why=why, at=r["at"]))
        out.append(dict(slot=slot, date=str(d), due=record.iso(record.due_at(conn, slot, d)), status=record.status_of(conn, slot, d, now), steps=steps, skipped=skips))
    return out


def state(conn, now=None):
    now = now or clock.now()
    ms = {m["id"]: m for m in record.members(conn)}
    tz = record.patient_tz(conn)
    today = now.astimezone(tz).date()
    members = [dict(id=m["id"], name=m["name"], relationship=m["relationship"], role=m["role"], simulated=m["kind"] == "sim", city=CITY(m["tz"]),
                    local=record.local_time(m, now).strftime("%H:%M"), awake=record.awake(m, now),
                    relay=m.get("relay_pref") or "everything", tz=m["tz"]) for m in ms.values()]
    doses = []
    for s in sorted(record.slots(conn), key=lambda s: s.rsplit("_", 1)[1]):
        st = record.status_of(conn, s, today, now)
        es = record.events(conn, s, today)
        res = next((e for e in reversed(es) if e["type"] in ("confirmed", "late_confirmed", "skipped", "unsure", "missed")), None)
        med, tm = s.rsplit("_", 1)
        doses.append(dict(slot=s, medicine=med, time=tm, status=st, by=_name(ms, res["actor"]) if res and res["actor"] else None,
                          reported_by=_name(ms, res["reported_by"]) if res and res["reported_by"] and res["reported_by"] != res["actor"] else None,
                          note=res["note"] if res else None, late=bool(res and res["type"] == "late_confirmed"),
                          initial=(_name(ms, res["actor"])[:1] if res and res["actor"] else "")))
    sched = [dict(medicine=l["name"], dose=record.fmt_dose(l["dose_amount"], l["dose_unit"]), times=l["times"], with_food=l["with_food"]) for l in record.lines(conn, "confirmed")]
    reps = labs.live_reports(conn)
    lab_out = [dict(id=r["id"], origin=r.get("origin") or "", lab=r["lab"], date=r["report_date"], confirmed_by=_name(ms, r["confirmed_by"]),
                    tests=[dict(test=t["test"], value=t["value"], unit=t["unit"], range_text=t["range_text"], status=t["status"], flag=t["printed_flag"]) for t in r["tests"]]) for r in reps]
    last = reps[-1] if reps else None
    tasks = [dict(id=r["id"], text=r["text"], owner=_name(ms, r["owner"]) if r["owner"] else None) for r in conn.execute("SELECT * FROM tasks WHERE status='open' ORDER BY id")]
    log = activity.collapse([{**dict(at=r["at"], kind=r["kind"], actor=r["actor"], detail=(r["detail"] or "")[:400], reason=r["reason"]), **activity.sentence(r, ms, tz)}
                             for r in conn.execute("SELECT at,kind,actor,detail,reason FROM audit_log ORDER BY id DESC LIMIT 200")])[:100]
    nd = record.next_due(conn, now)
    nxt = dict(medicine=nd[0].rsplit("_", 1)[0], time=nd[0].rsplit("_", 1)[1], day="today" if nd[1].astimezone(tz).date() == today else "tomorrow") if nd else None
    return dict(now=record.iso(now), patient=config.PATIENT_NAME, patient_tz=str(tz), next_dose=nxt, patient_local=now.astimezone(tz).strftime("%a %d %b %H:%M"), speed=clock.speed,
                members=members, schedule=sched, doses=doses, ladder=_ladder(conn, now, ms), organiser=_organiser(conn, now),
                labs=lab_out, lab_html=labviz.section_html(reps), lab_latest=dict(date=last["report_date"], out_of_range=len(labs.out_of_range(last["tests"]))) if last else None,
                tasks=tasks, audit=log, adherence=adherence(conn, today - timedelta(days=6), today, now)[0])


# ---------------- doctor summary ----------------
def adherence(conn, start, end, now):
    """Per medicine: doses confirmed / doses due between start and end (patient dates), counting only occurrences after the schedule was confirmed."""
    tz = record.patient_tz(conn)
    rows, misses = {}, []
    ms = {m["id"]: m for m in record.members(conn)}
    for l in record.lines(conn, "confirmed"):
        ca = datetime.fromisoformat(l["confirmed_at"].replace("Z", "+00:00")) if l["confirmed_at"] else None
        for t in l["times"]:
            slot = f"{l['name']}_{t}"
            d = start
            while d <= end:
                due = record.due_at(conn, slot, d)
                if due <= now and (ca is None or due >= ca):
                    r = rows.setdefault(l["name"], dict(medicine=l["name"], dose=record.fmt_dose(l["dose_amount"], l["dose_unit"]), due=0, confirmed=0))
                    r["due"] += 1
                    st = record.status_of(conn, slot, d, now)
                    if st == "given":
                        r["confirmed"] += 1
                    else:
                        es = [e for e in record.events(conn, slot, d) if e["type"] in ("skipped", "unsure", "missed")]
                        e = es[-1] if es else None
                        reason = (e["note"] if e and e["note"] else None) or ("no confirmation recorded" if st != "skipped" else "no reason recorded")
                        misses.append(dict(date=str(d), time=t, medicine=l["name"], status="not confirmed" if st in ("due", "overdue") else st, reason=reason,
                                           by=_name(ms, e["actor"]) if e and e["actor"] else None))
                d += timedelta(days=1)
    return sorted(rows.values(), key=lambda r: r["medicine"]), sorted(misses, key=lambda m: (m["date"], m["time"]))




SUMMARY_CSS = (
    "@page{size:A4;margin:12mm}*{box-sizing:border-box}body{margin:0;background:#FAF7F2;color:#1C2733;font:12.5px/1.4 Inter,system-ui,Segoe UI,sans-serif;font-variant-numeric:tabular-nums}"
    "main{max-width:760px;margin:0 auto;padding:20px 24px;background:#fff}.brand{font-weight:600;font-size:13px}.brand .dot{color:#E8833A}h1{font-size:22px;line-height:28px;margin:2px 0 0;font-weight:600}"
    ".meta{color:#5B6672;font-size:12px;margin-top:2px}h2{font-size:14px;line-height:20px;margin:14px 0 4px;font-weight:600;border-bottom:1px solid #E7E1D8;padding-bottom:2px}"
    "table{border-collapse:collapse;width:100%}td,th{padding:3px 6px;text-align:left;font-size:12px;border-bottom:1px solid #E7E1D8}th{color:#5B6672;font-weight:500}"
    ".adh td.n{width:34%;font-weight:500}.adh td.c{width:14%;text-align:right}.bar{height:6px;background:#E7E1D8;border-radius:3px;overflow:hidden}.bar i{display:block;height:100%;background:#333}"
    "ul{margin:2px 0 0;padding-left:18px}.mut{color:#5B6672}footer{margin-top:14px;border-top:1px solid #E7E1D8;padding-top:6px;font-size:11.5px;color:#5B6672}"
    ".noprint{margin-bottom:8px}.noprint button{font:inherit;padding:4px 12px;border:1px solid #C9C1B4;background:#fff;border-radius:999px;cursor:pointer}"
    ".labrep{margin:0}.lhead{font-size:12.5px}.lrow{grid-template-columns:112px 96px 226px 1fr;padding:2px 0;font-size:12px}.lcompact .ls{display:none}.lrow .lw{font-size:12px}"
    ":root{--within:#222;--outside:#000;--band:#DADADA;--bandedge:#999;--muted:#555}.rb-out{fill:#fff;stroke:#000}.rb-in{fill:#222}"
    "@media print{.noprint{display:none}body{background:#fff}main{padding:0;max-width:none}}")


def doctor_html(conn, start, end, now=None):
    """One page (A4 or Letter), black-and-white safe: adherence, missed doses, lab values, questions for the doctor (docs/DESIGN.md, 'Doctor summary')."""
    now = now or clock.now()
    e = html.escape
    rows, misses = adherence(conn, start, end, now)
    ms = {m["id"]: m for m in record.members(conn)}
    reps = labs.live_reports(conn)
    tasks = [r for r in conn.execute("SELECT * FROM tasks WHERE status='open' ORDER BY id")]
    notes = [(l["name"], l["notes"]) for l in record.lines(conn, "confirmed") if l["notes"]]
    notes += [(f"{e_['slot'].rsplit('_', 1)[0]} {e_['due_date']}", e_["note"]) for e_ in conn.execute("SELECT slot,due_date,note FROM dose_events WHERE note IS NOT NULL AND note NOT LIKE 'step %' AND type != 'missed' AND due_date BETWEEN ? AND ? ORDER BY id", (str(start), str(end)))]
    tz = record.patient_tz(conn)
    h = ["<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Doctor summary</title>",
         "<link rel='preconnect' href='https://fonts.googleapis.com'><link rel='stylesheet' href='https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap'><style>" + labviz.CSS + SUMMARY_CSS + "</style></head><body><main>",
         "<div class='noprint'><button onclick='window.print()'>Print</button></div>",
         f"<header><div class='brand'>CareCircle<span class='dot'>.</span></div><h1>Care summary for {e(config.PATIENT_NAME)}</h1>"
         f"<div class='meta'>Period {start:%d %b %Y} to {end:%d %b %Y} · Prepared by CareCircle on {now.astimezone(tz):%d %b %Y} from records kept by the family</div></header>"]
    h.append("<h2>Adherence: doses confirmed / due</h2>")
    h.append("<table class='adh'>" + "".join(
        f"<tr><td class='n'>{e(r['medicine'])} <span class='mut'>{e(r['dose'])}</span></td><td class='b'><div class='bar'><i style='width:{(100 * r['confirmed'] / r['due']) if r['due'] else 0:.0f}%'></i></div></td><td class='c'>{r['confirmed']} / {r['due']}</td></tr>" for r in rows)
        + "</table>" if rows else "<div class='mut'>No doses were due in this period.</div>")
    h.append("<h2>Doses not confirmed as given, with the reason recorded</h2>")
    h.append("<table class='miss'><tr><th>Date</th><th>Dose</th><th>Status</th><th>Reason recorded</th><th>Reported by</th></tr>" +
             "".join(f"<tr><td>{m['date']}</td><td>{e(m['medicine'])} {m['time']}</td><td>{e(m['status'])}</td><td>{e(m['reason'])}</td><td>{e(m['by'] or '')}</td></tr>" for m in misses) + "</table>" if misses else "<div class='mut'>None.</div>")
    if notes:
        h.append("<h2>Notes</h2><ul>" + "".join(f"<li>{e(a)}: {e(b)}</li>" for a, b in notes) + "</ul>")
    h.append("<h2>Lab values, with the lab's printed ranges</h2>" + (labviz.section_html(reps, print_mode=True) if reps else "<div class='mut'>No lab reports on record.</div>"))
    h.append("<h2>Questions for the doctor</h2>" + ("<ul>" + "".join(f"<li>{e(r['text'])} <span class='mut'>(owner: {e(_name(ms, r['owner'])) if r['owner'] else 'nobody yet'})</span></li>" for r in tasks) + "</ul>" if tasks else "<div class='mut'>None.</div>"))
    h.append(f"<footer>{e(FOOTER)}</footer></main></body></html>")
    return "".join(h)
