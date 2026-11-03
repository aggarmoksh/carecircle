"""Phase 4b: one nudge per person per dose time, grouped confirmation and relays, a deduplicated activity feed."""
import json
from datetime import date
from helpers import make, seed_lines, seed_d1, advance, utc
from app import escalation, intake, llm, record, board, activity, db
from app.clock import clock

TODAY = date(2026, 11, 2)


def _morning(window=True):
    conn, ob, ch = make("2026-11-02T02:45:30", all_tz="Asia/Kolkata", window=window)   # 08:15:30 IST, just past due + grace
    seed_d1(conn, confirmed_at="2026-11-02T00:00:00Z")
    conn.execute("DELETE FROM dose_events")
    conn.commit()
    return conn, ob, ch


def test_doses_due_together_make_one_nudge_per_person_and_one_escalation_step():
    conn, ob, ch = _morning()
    for _ in range(5):                                         # the scheduler ticks every second; nothing repeats
        escalation.tick(conn, ob)
    sent = [(m, t) for m, t in ch.log if m == "m2"]
    assert len(sent) == 1 and len(ch.log) == 1
    assert sent[0][1] == "Hi Meena, has Nanaji had his 8 AM medicines: amlodipine, aspirin, metformin? Reply done, or tell me which ones."
    assert {e["actor"] for s in ("amlodipine_08:00", "aspirin_08:00", "metformin_08:00") for e in record.events(conn, s, TODAY) if e["type"] == "nudged"} == {"m2"}
    advance(61)
    escalation.tick(conn, ob)
    assert len(ch.log) == 2 and "hasn't confirmed the 8 AM medicines" in ch.log[1][1] and ch.log[1][0] != "m2"
    # the 20:00 dose of metformin and atorvastatin is a different time, so it is a different question
    assert "atorvastatin" not in ch.log[0][1] and "20:00" not in ch.log[0][1]


def test_missed_alert_is_one_message_for_the_doses_that_went_missed_together():
    conn, ob, ch = _morning()
    for _ in range(8):
        advance(61)
        escalation.tick(conn, ob)
    alerts = [t for m, t in ch.log if "recorded as missed" in t and m == "m1"]
    assert alerts == ["CareCircle: amlodipine, aspirin, metformin 08:00 for Nanaji is recorded as missed."]


def _spark(slot, action="given", actor="m2"):
    def fake(phase, label, msgs, schema):
        return {"actor": actor, "slot": slot, "action": action}, 0, 0
    return fake


def test_done_confirms_every_dose_of_that_time_and_relays_once(monkeypatch):
    conn, ob, ch = _morning()
    escalation.tick(conn, ob)
    ch.log.clear()
    monkeypatch.setattr(llm, "spark_json", _spark("none"))
    intake._dose(conn, ob, "m2", "done", clock.now())
    for s in ("amlodipine_08:00", "aspirin_08:00", "metformin_08:00"):
        assert record.status_of(conn, s, TODAY, clock.now()) == "given"
    assert [t for m, t in ch.log if m == "m2"] == ["Logged: amlodipine, aspirin, metformin 08:00 given (Meena). Thanks."]
    relays = [t for m, t in ch.log if m != "m2"]
    assert len(relays) == 4 and set(relays) == {"CareCircle: Meena gave amlodipine, aspirin, metformin 08:00."}


def test_partial_reply_confirms_only_the_named_medicines(monkeypatch):
    conn, ob, ch = _morning()
    escalation.tick(conn, ob)
    ch.log.clear()
    monkeypatch.setattr(llm, "spark_json", _spark("metformin_08:00"))
    intake._dose(conn, ob, "m2", "gave the metformin and aspirin", clock.now())
    st = {s: record.status_of(conn, s, TODAY, clock.now()) for s in ("amlodipine_08:00", "aspirin_08:00", "metformin_08:00")}
    assert st == {"amlodipine_08:00": "overdue", "aspirin_08:00": "given", "metformin_08:00": "given"}
    assert [t for m, t in ch.log if m == "m2"] == ["Logged: aspirin, metformin 08:00 given (Meena). Thanks."]
    assert {t for m, t in ch.log if m != "m2"} == {"CareCircle: Meena gave aspirin, metformin 08:00."}
    # the one left over is still waiting, and a later 'done' closes it
    monkeypatch.setattr(llm, "spark_json", _spark("none"))
    intake._dose(conn, ob, "m2", "done", clock.now())
    assert record.status_of(conn, "amlodipine_08:00", TODAY, clock.now()) == "given"


def test_single_medicine_keeps_the_short_wording():
    conn, ob, ch = make("2026-11-02T14:47:00", all_tz="Asia/Kolkata")      # 20:17 IST
    seed_lines(conn, [("atorvastatin", 20, "mg", ["20:00"])], confirmed_at="2026-11-02T00:00:00Z")
    escalation.tick(conn, ob)
    assert ch.log == [("m4", "CareCircle: atorvastatin 20:00 for Nanaji isn't confirmed yet. If it has been given, reply 'done' or send a voice note.")]


def test_activity_feed_logs_each_step_once_collapses_repeats_and_shows_15():
    conn, ob, ch = _morning()
    for _ in range(6):
        escalation.tick(conn, ob)
    kinds = [r["kind"] for r in conn.execute("SELECT kind FROM audit_log")]
    assert kinds.count("outbound") == 1
    skips = [r["detail"] for r in conn.execute("SELECT detail FROM audit_log WHERE kind='escalation_skip'")]
    assert len(skips) == len(set(skips))
    conn.execute("DELETE FROM audit_log")
    for i in range(3):                                         # three identical events inside one minute
        db.audit(conn, "relay_suppressed", "m1", "x", "r", at=f"2026-11-02T02:50:{10 + i}Z")
    for i in range(24):
        db.audit(conn, "clock_set", None, str(i), "r", at=f"2026-11-02T03:{i:02d}:00Z")
    feed = board.state(conn, clock.now())["audit"]
    sup = [a for a in feed if a["kind"] == "relay_suppressed"]
    assert len(sup) == 1 and sup[0]["n"] == 3
    assert len(feed) == 25                                       # 24 distinct minutes + the collapsed group; the page shows the newest 15 and 'show all'
    html = open(board.__file__.replace("board.py", "board.html"), encoding="utf-8").read()
    assert "slice(0,15)" in html and "Show all" in html
