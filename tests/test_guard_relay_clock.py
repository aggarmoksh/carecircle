from helpers import make, seed_d1, advance, utc
from app import guard, record, outbox
from app.clock import clock, Clock


def test_fixed_replies_pass_guard():
    conn, ob, ch = make("2026-11-02T10:00:00")
    for t in (outbox.FIXED_MEDICAL, outbox.FIXED_URGENT, outbox.FIXED_LAB, outbox.FIXED_BLOCKED):
        ok, why = guard.check(conn, t)
        assert ok, (t, why)


def test_blocks_medicine_not_in_record_but_allows_sender_mention():
    conn, ob, ch = make("2026-11-02T10:00:00")
    seed_d1(conn)
    assert guard.check(conn, "Metformin 500 mg is due at 20:00.")[0]
    ok, why = guard.check(conn, "Maybe warfarin could help.")
    assert not ok and "warfarin" in why
    assert guard.check(conn, "You asked about warfarin.", sender_text="what about warfarin?")[0]


def test_blocks_dose_not_in_record():
    conn, ob, ch = make("2026-11-02T10:00:00")
    seed_d1(conn)
    ok, why = guard.check(conn, "Metformin 1000 mg is due.")
    assert not ok and "dose" in why
    assert guard.check(conn, "Metformin 1000 mg is due.", sender_text="he took 1000 mg")[0]


def test_advice_blocklist():
    conn, ob, ch = make("2026-11-02T10:00:00")
    seed_d1(conn)
    for t in ("You should give an extra dose tonight.", "It is safe to take it with food.", "I recommend stopping it.",
              "Possible side effects include nausea.", "His blood sugar is high.", "It's used to treat diabetes."):
        assert not guard.check(conn, t)[0], t
    for t in ("Logged: metformin 08:00 given (Meena). Thanks.", "Meena is on duty tonight.", "Tuesday PM is still full; no confirmation was logged"):
        assert guard.check(conn, t)[0], t


def test_outbox_replaces_blocked_text_and_logs():
    conn, ob, ch = make("2026-11-02T10:00:00")
    ob.send("m2", "You should double the dose.", "test")
    assert ch.log[0][1] == outbox.FIXED_BLOCKED
    assert conn.execute("SELECT 1 FROM audit_log WHERE kind='guard_block'").fetchone()


def test_relay_window_and_waking_hours():
    conn, ob, ch = make("2026-11-02T03:00:00")   # 03:00Z: m1 LA 19:00 (awake), m3 London 03:00 (asleep), m2 IST 08:30
    conn.execute("UPDATE members SET last_inbound_at='2026-10-20T00:00:00Z' WHERE id='m2'")  # m2 window closed
    ob.relay("CareCircle: test update.", ["m4"], "test")
    sent_to = {m for m, _ in ch.log}
    assert "m1" in sent_to                              # awake, window open
    assert "m3" not in sent_to and "m2" not in sent_to  # asleep / window closed -> queued
    assert "m5" in sent_to                              # simulated members are always logged
    q = {r["member_id"] for r in conn.execute("SELECT member_id FROM queue")}
    assert q == {"m2", "m3"}
    clock.set(utc("2026-11-02T08:30:00"), speed=0)      # m3 now awake (London 08:30), window must be reopened
    record.touch_inbound(conn, "m3", clock.now())
    ob.flush_queue()
    assert "m3" in {m for m, _ in ch.log}


def test_clock_set_speed():
    c = Clock()
    c.set(utc("2026-11-02T00:00:00"), speed=0)
    a = c.now()
    assert a == utc("2026-11-02T00:00:00")
    c.set(speed=60)
    import time
    time.sleep(0.2)
    assert (c.now() - a).total_seconds() >= 10
