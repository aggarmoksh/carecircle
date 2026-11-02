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
    return conn.execute("SELECT 1 FROM audit_log WHERE kind='escalation_skip' AND actor=? AND detail=?",
                        (mid, f"{slot} {d}: {why}")).fetchone() is not None


def tick(conn, outbox):
    now = clock.now()
    ensure_due_events(conn, now)
    ms = {m["id"]: m for m in record.members(conn)}
    for slot, d in record.open_occurrences(conn, now):
        due = record.due_at(conn, slot, d)
        base = due + timedelta(minutes=config.GRACE_MIN)
        evs = record.events(conn, slot, d)
        contacted = [e["actor"] for e in evs if e["type"] in ("nudged", "escalated")]
        k = len(contacted)
        if now < base + timedelta(seconds=k * config.STEP_SECONDS):
            continue
        sent = False
        for m in _ladder(conn, slot):
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
                if not _logged(conn, slot, d, m["id"], why):
                    audit(conn, "escalation_skip", m["id"], f"{slot} {d}: {why}", "member skipped in escalation ladder")
                continue
            lab = f"{slot.rsplit('_', 1)[0]} {slot.rsplit('_', 1)[1]}"
            if k == 0:
                text = f"CareCircle: {lab} for {config.PATIENT_NAME} isn't confirmed yet. If it has been given, reply 'done' or send a voice note."
                reason, typ = f"nudge: {slot} past due + grace, {m['id']} on duty/first reachable", "nudged"
            else:
                first = ms[contacted[0]]["name"]
                text = f"CareCircle: {first} hasn't confirmed {lab} for {config.PATIENT_NAME} yet. Can you check and tell me?"
                reason, typ = f"escalate: {slot} still unconfirmed after {k} step(s), next reachable member", "escalated"
            res = outbox.send(m["id"], text, reason)
            record.add_event(conn, slot, d, typ, m["id"], None, None, f"step {k + 1}" + ("" if res else " (send skipped)"), record.iso(now))
            sent = True
            break
        if sent:
            continue
        if len([c for c in contacted]) >= len(ms) or now >= due + timedelta(hours=config.MISS_AFTER_HOURS):
            record.add_event(conn, slot, d, "missed", None, None, None, "ladder exhausted" if len(contacted) >= len(ms) else "no one reachable in time", record.iso(now))
            audit(conn, "dose_missed", None, f"{slot} {d}", "ladder exhausted or nobody reachable in time")
            outbox.relay(f"CareCircle: {slot.rsplit('_', 1)[0]} {slot.rsplit('_', 1)[1]} for {config.PATIENT_NAME} is recorded as missed.", [], "state change: dose missed", kind="alert")
        else:
            if not conn.execute("SELECT 1 FROM audit_log WHERE kind='escalation_hold' AND detail=?", (f"{slot} {d} step {k + 1}",)).fetchone():
                audit(conn, "escalation_hold", None, f"{slot} {d} step {k + 1}", "nobody awake or reachable now; holding and retrying")
    settle_missed(conn, now)


def settle_missed(conn, now, days=14):
    """Catch-up for doses nobody confirmed: any occurrence of a confirmed line due more than MISS_AFTER_HOURS ago (and after the line was
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
                if now < due + timedelta(hours=config.MISS_AFTER_HOURS) or (ca is not None and due < ca):
                    continue
                if record.status_of(conn, slot, d, now) in ("due", "overdue", "not_yet_due"):
                    record.add_event(conn, slot, d, "missed", None, None, None, "no confirmation recorded", record.iso(now))
                    audit(conn, "dose_missed", None, f"{slot} {d}", "past due with no confirmation when the scheduler ran")
                    n += 1
    return n
