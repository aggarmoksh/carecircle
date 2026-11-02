"""Demo reset: restore the fictional demo start state in one call (also used by tools/demo_reset.py and the tests)."""
from datetime import datetime, time as dtime, timezone
from . import config, record, seed

CLEAR = ["dose_events", "schedule_lines", "medications", "documents", "tasks", "lab_values", "lab_reports", "queue", "audit_log", "rota", "circle"]


def start_time(conn, date=None):
    """07:55 patient-local on `date` (default: today in the patient's timezone), as UTC."""
    from .clock import clock
    tz = record.patient_tz(conn)
    d = date or clock.now().astimezone(tz).date()
    return datetime.combine(d, dtime(7, 55), tzinfo=tz).astimezone(timezone.utc)


def reset(conn):
    """Clear the care record and re-seed the fictional circle: schedule not yet confirmed, every member's choice 'everything'.
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
    conn.execute("UPDATE members SET relay_pref='everything'")
    conn.commit()
