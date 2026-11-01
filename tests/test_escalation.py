from datetime import date
from helpers import make, seed_lines, advance, utc
from app import record, escalation, config
from app.clock import clock

# 2026-11-02 is a Monday. 08:00 IST = 02:30Z. Grace 15 min -> first nudge at 02:45Z.
SLOT = "metformin_08:00"
D = date(2026, 11, 2)


def setup(now="2026-11-02T02:44:00", **kw):
    conn, ob, ch = make(now, **kw)
    seed_lines(conn, [("metformin", 500, "mg", ["08:00"])], confirmed_at="2026-11-02T00:00:00Z")
    return conn, ob, ch


def test_confirmed_in_time_no_nudge():
    conn, ob, ch = setup("2026-11-02T02:35:00", all_tz="Asia/Kolkata")
    record.log_confirmation(conn, SLOT, "given", "m2", "m2", "t", None, clock.now())
    advance(1200)  # 02:55Z, past the grace period
    escalation.tick(conn, ob)
    assert ch.log == []
    assert record.status_of(conn, SLOT, D, clock.now()) == "given"


def test_missed_after_full_ladder():
    conn, ob, ch = setup(all_tz="Asia/Kolkata")
    advance(70)  # 02:45:10Z: past grace
    for _ in range(8):
        escalation.tick(conn, ob)
        advance(61)
    order = [m for m, t in ch.log if "confirmed" in t]
    assert order == ["m2", "m4", "m1", "m3", "m5"]          # on duty, next hands_on, then remote members
    assert "nudged" in {e["type"] for e in record.events(conn, SLOT, D)} and "escalated" in {e["type"] for e in record.events(conn, SLOT, D)}
    assert record.status_of(conn, SLOT, D, clock.now()) == "missed"


def test_late_reply_is_late_confirmed():
    conn, ob, ch = setup(all_tz="Asia/Kolkata")
    advance(70)
    escalation.tick(conn, ob); advance(61); escalation.tick(conn, ob)   # nudge m2, escalate m4
    typ, _ = record.log_confirmation(conn, SLOT, "given", "m2", "m2", "t", None, clock.now())
    assert typ == "late_confirmed"
    n = len(ch.log)
    advance(300); escalation.tick(conn, ob)
    assert len(ch.log) == n                                  # ladder stopped
    assert record.status_of(conn, SLOT, D, clock.now()) == "given"


def test_sleeper_skipped_with_reason():
    conn, ob, ch = setup(all_tz="Asia/Kolkata")
    conn.execute("UPDATE members SET tz='Europe/London' WHERE id='m2'")   # m2 (on duty) is asleep: 02:45Z = 02:45 London
    advance(70)
    escalation.tick(conn, ob)
    assert ch.log[0][0] == "m4"                              # next hands_on member nudged instead
    skip = conn.execute("SELECT detail FROM audit_log WHERE kind='escalation_skip' AND actor='m2'").fetchone()
    assert skip and "asleep" in skip["detail"]


def test_everyone_asleep_holds_then_resumes():
    conn, ob, ch = setup(all_tz="Europe/London")
    advance(70)
    escalation.tick(conn, ob)
    assert ch.log == []                                      # nobody awake: nothing sent
    assert conn.execute("SELECT 1 FROM audit_log WHERE kind='escalation_hold'").fetchone()
    assert conn.execute("SELECT COUNT(*) c FROM audit_log WHERE kind='escalation_skip'").fetchone()["c"] == 5
    clock.set(utc("2026-11-02T08:30:00"), speed=0)           # 08:30 London: everyone awake
    for m in record.members(conn):
        if m["kind"] == "real":
            record.touch_inbound(conn, m["id"], clock.now())
    escalation.tick(conn, ob)
    assert ch.log and ch.log[0][0] == "m2"                   # ladder resumes at the on-duty member


def test_closed_window_member_is_skipped():
    conn, ob, ch = setup(all_tz="Asia/Kolkata")
    conn.execute("UPDATE members SET last_inbound_at='2026-10-30T00:00:00Z' WHERE id='m2'")
    advance(70)
    escalation.tick(conn, ob)
    assert ch.log[0][0] == "m4"
    d = conn.execute("SELECT detail FROM audit_log WHERE kind='escalation_skip' AND actor='m2'").fetchone()["detail"]
    assert "24h window" in d
