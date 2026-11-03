"""Demo reset: restore the fictional demo start state in one call (also used by tools/demo_reset.py and the tests)."""
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path
from . import config, record, seed

CLEAR = ["dose_events", "schedule_lines", "medications", "documents", "tasks", "lab_values", "lab_reports", "queue", "audit_log", "rota", "circle"]


def start_time(conn, date=None):
    """07:55 patient-local on `date` (default: today in the patient's timezone), as UTC."""
    from .clock import clock
    tz = record.patient_tz(conn)
    d = date or clock.now().astimezone(tz).date()
    return datetime.combine(d, dtime(7, 55), tzinfo=tz).astimezone(timezone.utc)


def reset(conn):
    """Clear the care record and re-seed the fictional circle: schedule not yet confirmed, nearby members 'everything', remote members 'alerts and a daily summary'.
    Members' last-message times (WhatsApp windows) are kept; they belong to the phones, not the demo story."""
    for t in CLEAR:
        conn.execute(f"DELETE FROM {t}")
    conn.execute("DELETE FROM sqlite_sequence WHERE name IN (" + ",".join("?" * len(CLEAR)) + ")", CLEAR)
    keep = {m["id"]: m["last_inbound_at"] for m in record.members(conn)}
    conn.execute("DELETE FROM members")
    conn.commit()
    seed.init(conn)
    for mid, last in keep.items():
        conn.execute("UPDATE members SET last_inbound_at=? WHERE id=?", (last, mid))
    conn.commit()


def scene_monday(conn, on=None):
    """Demo scene for filming: a fresh circle, no schedule yet, every member's update choice set to 'everything' (so each update reaches a phone at once),
    patient clock Monday 07:55. Fictional data only. Returns the clock target."""
    from datetime import timedelta
    reset(conn)
    conn.execute("UPDATE members SET relay_pref='everything'")
    conn.commit()
    today = on or datetime.now(record.patient_tz(conn)).date()
    return start_time(conn, today + timedelta(days=(0 - today.weekday()) % 7))


def scene_thursday(conn, on=None):
    """Demo scene: Thursday 07:55 patient-local. d1 was confirmed by Meena on Monday; Monday, Tuesday and Wednesday 08:00 doses were confirmed by
    various members; Wednesday 20:00 doses were never confirmed (recorded as missed); the lab report L2 was confirmed by Kabir. Fictional data only.
    Send media/organiser_real/or1.jpeg from r2 to see 'Wednesday PM is still full in the organiser: that dose wasn't given'. Returns the clock target."""
    import json
    from datetime import date, timedelta
    from . import labs
    from .db import audit
    reset(conn)
    tz = record.patient_tz(conn)
    today = on or datetime.now(tz).date()
    thu = today + timedelta(days=(3 - today.weekday()) % 7)
    mon, tue, wed = thu - timedelta(days=3), thu - timedelta(days=2), thu - timedelta(days=1)
    utc_iso = lambda d, hh, mm: record.iso(datetime.combine(d, dtime(hh, mm), tzinfo=tz).astimezone(timezone.utc))
    root = Path(__file__).resolve().parent.parent
    meds = json.loads((root / "labels.json").read_text(encoding="utf-8"))["sheets"]["d1"]["meds"]
    conf = utc_iso(mon, 7, 40)
    record.add_draft(conn, None, meds, conf)
    record.confirm_drafts(conn, "m2", conf)
    audit(conn, "schedule_confirmed", "m2", {"lines": len(meds)}, "member said YES", at=conf)
    who = ["m2", "m4", "m1", "patient", "m2", "m3"]
    n = 0
    for d in (mon, tue, wed):
        for slot in sorted(record.slots(conn), key=lambda s: s.rsplit("_", 1)[1]):
            due = record.due_at(conn, slot, d)
            if d == wed and slot.endswith("20:00"):
                record.add_event(conn, slot, d, "missed", None, None, None, "no confirmation recorded", record.iso(due + timedelta(hours=13)))
                audit(conn, "dose_missed", None, f"{slot} {d}", "ladder exhausted, or the next dose of the same medicine fell due", at=record.iso(due + timedelta(hours=13)))
                continue
            actor = who[n % len(who)]
            n += 1
            at = record.iso(due + timedelta(minutes=3))
            record.add_event(conn, slot, d, "confirmed", actor, actor if actor != "patient" else "m2", "seed (fictional)", None, at)
            audit(conn, "dose_event", actor, {"slot": slot, "type": "confirmed", "actor": actor, "date": str(d)}, "dose update parsed against the live schedule", at=at)
    lab_at = utc_iso(wed, 18, 5)
    labs.load_fixture(conn, root / "tests" / "lab_labels.json", "L2", "m3", lab_at)
    audit(conn, "lab_confirmed", "m3", {"date": "L2"}, "member said YES; lab values are live", at=lab_at)
    record.add_task(conn, "Discuss the lab report from 29 Oct with the doctor", None, "lab report", lab_at)
    conn.commit()
    return start_time(conn, thu)
