"""Web board state and doctor summary. Read-only views of the care record; nothing here interprets a value or gives advice."""
import html, json
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from . import config, record, labs
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
    for slot, d in record.open_occurrences(conn, now):
        steps = [dict(at=e["at"], who=_name(ms, e["actor"]), kind=e["type"], note=e["note"]) for e in record.events(conn, slot, d) if e["type"] in ("nudged", "escalated")]
        skips = []
        for r in conn.execute("SELECT actor, detail, at FROM audit_log WHERE kind='escalation_skip' AND detail LIKE ?", (f"{slot} {d}:%",)):
            skips.append(dict(who=_name(ms, r["actor"]), why=r["detail"].split(": ", 1)[1], at=r["at"]))
        out.append(dict(slot=slot, date=str(d), due=record.iso(record.due_at(conn, slot, d)), status=record.status_of(conn, slot, d, now), steps=steps, skipped=skips))
    return out


def state(conn, now=None):
    now = now or clock.now()
    ms = {m["id"]: m for m in record.members(conn)}
    tz = record.patient_tz(conn)
    today = now.astimezone(tz).date()
    members = [dict(id=m["id"], name=m["name"], relationship=m["relationship"], role=m["role"], simulated=m["kind"] == "sim", city=CITY(m["tz"]),
                    local=record.local_time(m, now).strftime("%H:%M"), awake=record.awake(m, now)) for m in ms.values()]
    doses = []
    for s in sorted(record.slots(conn), key=lambda s: s.rsplit("_", 1)[1]):
        st = record.status_of(conn, s, today, now)
        es = record.events(conn, s, today)
        res = next((e for e in reversed(es) if e["type"] in ("confirmed", "late_confirmed", "skipped", "unsure", "missed")), None)
        med, tm = s.rsplit("_", 1)
        doses.append(dict(slot=s, medicine=med, time=tm, status=st, by=_name(ms, res["actor"]) if res and res["actor"] else None,
                          reported_by=_name(ms, res["reported_by"]) if res and res["reported_by"] and res["reported_by"] != res["actor"] else None,
                          note=res["note"] if res else None, late=bool(res and res["type"] == "late_confirmed")))
    sched = [dict(medicine=l["name"], dose=record.fmt_dose(l["dose_amount"], l["dose_unit"]), times=l["times"], with_food=l["with_food"]) for l in record.lines(conn, "confirmed")]
    reps = labs.live_reports(conn)
    lab_out = [dict(id=r["id"], lab=r["lab"], date=r["report_date"], confirmed_by=_name(ms, r["confirmed_by"]),
                    tests=[dict(test=t["test"], value=t["value"], unit=t["unit"], range_text=t["range_text"], status=t["status"], flag=t["printed_flag"]) for t in r["tests"]]) for r in reps]
    series = {}
    for r in reps:
        for t in r["tests"]:
            series.setdefault(t["test"], []).append(dict(date=r["report_date"], value=t["value"], unit=t["unit"], status=t["status"]))
    charts = {k: v for k, v in series.items() if len(v) >= 2}
    last = reps[-1] if reps else None
    tasks = [dict(id=r["id"], text=r["text"], owner=_name(ms, r["owner"]) if r["owner"] else None) for r in conn.execute("SELECT * FROM tasks WHERE status='open' ORDER BY id")]
    log = [dict(at=r["at"], kind=r["kind"], actor=r["actor"], detail=(r["detail"] or "")[:160], reason=r["reason"]) for r in conn.execute("SELECT at,kind,actor,detail,reason FROM audit_log ORDER BY id DESC LIMIT 20")]
    return dict(now=record.iso(now), patient=config.PATIENT_NAME, patient_local=now.astimezone(tz).strftime("%a %d %b %H:%M"), speed=clock.speed,
                members=members, schedule=sched, doses=doses, ladder=_ladder(conn, now, ms), organiser=_organiser(conn, now),
                labs=lab_out, lab_charts=charts, lab_latest=dict(date=last["report_date"], out_of_range=len(labs.out_of_range(last["tests"]))) if last else None,
                tasks=tasks, audit=log)


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


def doctor_html(conn, start, end, now=None):
    now = now or clock.now()
    e = html.escape
    rows, misses = adherence(conn, start, end, now)
    ms = {m["id"]: m for m in record.members(conn)}
    reps = labs.live_reports(conn)
    tasks = [r for r in conn.execute("SELECT * FROM tasks WHERE status='open' ORDER BY id")]
    notes = [(l["name"], l["notes"]) for l in record.lines(conn, "confirmed") if l["notes"]]
    notes += [(f"{e_['slot'].rsplit('_', 1)[0]} {e_['due_date']}", e_["note"]) for e_ in conn.execute("SELECT slot,due_date,note FROM dose_events WHERE note IS NOT NULL AND note NOT LIKE 'step %' AND due_date BETWEEN ? AND ? ORDER BY id", (str(start), str(end)))]
    h = [f"<!doctype html><html><head><meta charset='utf-8'><title>Doctor summary</title><style>"
         "body{font:15px/1.45 system-ui,sans-serif;max-width:860px;margin:24px auto;padding:0 16px;color:#111}h1{font-size:22px;margin:0}h2{font-size:16px;margin:22px 0 6px;border-bottom:1px solid #999}"
         "table{border-collapse:collapse;width:100%}td,th{border:1px solid #bbb;padding:4px 8px;text-align:left;font-size:14px}th{background:#eee}"
         ".foot{margin-top:28px;font-size:13px;color:#333;border-top:1px solid #999;padding-top:8px}.noprint{margin-bottom:12px}@media print{.noprint{display:none}}</style></head><body>"
         f"<div class='noprint'><button onclick='window.print()'>Print</button></div>"
         f"<h1>Care summary for {e(config.PATIENT_NAME)}</h1><div>Period: {start:%d %b %Y} to {end:%d %b %Y}</div>"]
    h.append("<h2>Doses: confirmed / due</h2><table><tr><th>Medicine</th><th>Dose</th><th>Confirmed / due</th></tr>")
    h += [f"<tr><td>{e(r['medicine'])}</td><td>{e(r['dose'])}</td><td>{r['confirmed']} / {r['due']}</td></tr>" for r in rows] or ["<tr><td colspan=3>No doses were due in this period.</td></tr>"]
    h.append("</table><h2>Doses not confirmed as given, with reason</h2>")
    h.append("<table><tr><th>Date</th><th>Dose</th><th>Status</th><th>Reason recorded</th><th>Reported by</th></tr>" +
             "".join(f"<tr><td>{m['date']}</td><td>{e(m['medicine'])} {m['time']}</td><td>{e(m['status'])}</td><td>{e(m['reason'])}</td><td>{e(m['by'] or '')}</td></tr>" for m in misses) + "</table>" if misses else "<div>None.</div>")
    h.append("<h2>Notes</h2>" + ("<ul>" + "".join(f"<li>{e(a)}: {e(b)}</li>" for a, b in notes) + "</ul>" if notes else "<div>None.</div>"))
    h.append("<h2>Lab values with the lab's printed ranges</h2>")
    for r in reps:
        h.append(f"<div><b>{e(r['lab'])}, {labs.pretty_date(r['report_date'])} {r['report_date'][:4]}</b></div><table><tr><th>Test</th><th>Value</th><th>Unit</th><th>Printed range</th><th>Status</th></tr>")
        for t in r["tests"]:
            stt = {"within": "within the lab's printed range", "above": "above the lab's printed range", "below": "below the lab's printed range", "no_range": "no range printed"}[t["status"]]
            h.append(f"<tr><td>{e(t['test'])}</td><td>{labs.fmt_num(t['value'])}</td><td>{e(t['unit'])}</td><td>{e(t['range_text'] or '')}</td><td>{stt}</td></tr>")
        h.append("</table>")
    if not reps:
        h.append("<div>No lab reports on record.</div>")
    h.append("<h2>Open tasks for the doctor visit</h2>" + ("<ul>" + "".join(f"<li>{e(r['text'])} (owner: {e(_name(ms, r['owner'])) if r['owner'] else 'nobody yet'})</li>" for r in tasks) + "</ul>" if tasks else "<div>None.</div>"))
    h.append(f"<div class='foot'>{e(FOOTER)}</div></body></html>")
    return "".join(h)
