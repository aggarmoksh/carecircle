"""Escalation engine (generalised Phase 0 P5). Pure code: decisions come from the record and the clock, never from the model.
A confirmed schedule line creates dose occurrences. Past due + grace -> private nudge to the on-duty member, then the next
hands_on members, then remote members who are awake in their local time, then anyone awake. Each skipped member is logged with
the reason. A reply from anyone stops the ladder; a confirmation after an escalation is stored as late_confirmed."""
from datetime import datetime, timedelta
from . import config, record
from .clock import clock
from .db import audit


def _confirmed_at(l):
    return datetime.fromisoformat(l["confirmed_at"].replace("Z", "+00:00")) if l.get("confirmed_at") else None


def ensure_due_events(conn, now):
    today = now.astimezone(record.patient_tz(conn)).date()
    for l in record.lines(conn, "confirmed"):
        ca = _confirmed_at(l)
        for t in l["times"]:
            slot = f"{l['name']}_{t}"
            for d in (today - timedelta(days=1), today):
                due = record.due_at(conn, slot, d)
                if now >= due and (ca is None or due >= ca) and not record.events(conn, slot, d):
                    record.add_event(conn, slot, d, "due", None, None, None, None, record.iso(now))


def _ladder(conn, slot):
    ms = record.members(conn)
    duty = record.on_duty(conn, slot)
    order = [m for m in ms if m["id"] == duty]
    order += [m for m in ms if m["role"] == "hands_on" and m["id"] != duty]
    order += [m for m in ms if m["role"] == "remote" and m["id"] != duty]
    return order


def _logged(conn, slot, d, mid, why):
    return conn.execute("SELECT 1 FROM audit_log WHERE kind='escalation_skip' AND actor=? AND detail LIKE ?",
                        (mid, f"{slot} {d}: {why.split(' (')[0]}%")).fetchone() is not None


def tick(conn, outbox):
    now = clock.now()
    ensure_due_events(conn, now)
    ms = {m["id"]: m for m in record.members(conn)}
    for (d, t), gslots in record.group_open(conn, now):
        slot0 = gslots[0]
        due = record.due_at(conn, slot0, d)
        base = due + timedelta(minutes=config.GRACE_MIN)
        contacted = []
        for s in gslots:
            for e in record.events(conn, s, d):
                if e["type"] in ("nudged", "escalated") and e["actor"] not in contacted:
                    contacted.append(e["actor"])
        k = len(contacted)
        if now < base + timedelta(seconds=k * config.STEP_SECONDS):
            continue
        sent = False
        for m in _ladder(conn, slot0):
            if m["id"] in contacted:
                continue
            if m.get("relay_pref") == "stop":
                why = "chose STOP (no messages until they write again)"
            elif not record.awake(m, now):
                why = f"asleep (local {record.local_time(m, now).strftime('%H:%M')})"
            elif not record.window_open(m, now):
                why = "24h window closed (template required)"
            else:
                why = None
            if why:
                if not _logged(conn, slot0, d, m["id"], why):
                    audit(conn, "escalation_skip", m["id"], f"{slot0} {d}: {why}", "member skipped in escalation ladder")
                continue
            text, reason, typ = _step_text(ms, m, gslots, t, k, contacted, slot0)
            res = outbox.send(m["id"], text, reason)
            for s in gslots:
                record.add_event(conn, s, d, typ, m["id"], None, None, f"step {k + 1}" + ("" if res else " (send skipped)"), record.iso(now))
            sent = True
            break
        if sent:
            continue
        exhausted = len(contacted) >= len(ms)
        gone = [s for s in gslots if exhausted or now >= record.next_dose_due(conn, s, d)]
        for s in gone:
            record.add_event(conn, s, d, "missed", None, None, None, "ladder exhausted" if exhausted else "next dose of the same medicine fell due", record.iso(now))
            audit(conn, "dose_missed", None, f"{s} {d}", "ladder exhausted, or the next dose of the same medicine fell due")
        if gone:   # one alert for the doses that went missed together
            outbox.relay(f"CareCircle: {record.med_names(gone)} {t} for {config.PATIENT_NAME} is recorded as missed.", [], "state change: dose missed", kind="alert")
        elif not conn.execute("SELECT 1 FROM audit_log WHERE kind='escalation_hold' AND detail=?", (f"{slot0} {d} step {k + 1}",)).fetchone():
            audit(conn, "escalation_hold", None, f"{slot0} {d} step {k + 1}", "nobody awake or reachable now; holding and retrying")
    settle_missed(conn, now)


def _step_text(ms, m, gslots, t, k, contacted, slot0):
    """One message per person per dose time. A single medicine keeps the short wording; several are named in one question."""
    P = config.PATIENT_NAME
    if len(gslots) == 1:
        lab = f"{slot0.rsplit('_', 1)[0]} {t}"
        if k == 0:
            return (f"CareCircle: {lab} for {P} isn't confirmed yet. If it has been given, reply 'done' or send a voice note.",
                    f"nudge: {slot0} past due + grace, {m['id']} on duty/first reachable", "nudged")
        return (f"CareCircle: {ms[contacted[0]]['name']} hasn't confirmed {lab} for {P} yet. Can you check and tell me?",
                f"escalate: {slot0} still unconfirmed after {k} step(s), next reachable member", "escalated")
    names, when = record.med_names(gslots), record.clock12(t)
    if k == 0:
        return (f"Hi {m['name']}, has {P} had his {when} medicines: {names}? Reply done, or tell me which ones.",
                f"nudge: {len(gslots)} doses at {t} past due + grace, {m['id']} on duty/first reachable", "nudged")
    return (f"CareCircle: {ms[contacted[0]]['name']} hasn't confirmed the {when} medicines for {P} yet ({names}). Can you check and tell me?",
            f"escalate: {len(gslots)} doses at {t} still unconfirmed after {k} step(s), next reachable member", "escalated")


def settle_missed(conn, now, days=14):
    """Catch-up for doses nobody confirmed: any occurrence of a confirmed line whose next dose of the same medicine has fallen due (and after the line was
    confirmed) with no resolution becomes 'missed' (event + audit line). The live ladder still handles today's and yesterday's doses first;
    this only closes what is left, so a stopped scheduler never leaves past doses 'due' forever. Sends nothing."""
    tz = record.patient_tz(conn)
    today = now.astimezone(tz).date()
    n = 0
    for l in record.lines(conn, "confirmed"):
        ca = _confirmed_at(l)
        for t in l["times"]:
            slot = f"{l['name']}_{t}"
            for back in range(days + 1):
                d = today - timedelta(days=back)
                due = record.due_at(conn, slot, d)
                if now < record.next_dose_due(conn, slot, d) or (ca is not None and due < ca):
                    continue
                if record.status_of(conn, slot, d, now) in ("due", "overdue", "not_yet_due"):
                    record.add_event(conn, slot, d, "missed", None, None, None, "no confirmation recorded", record.iso(now))
                    audit(conn, "dose_missed", None, f"{slot} {d}", "next dose fell due with no confirmation when the scheduler ran")
                    n += 1
    return n
