"""Phase 4 unit tests: lab status at render time, dose-state consistency, guard task names, dose-report routing, relay defaults. No model calls."""
import sqlite3
from datetime import date
import pytest
from helpers import make, seed_phase2, seed_lines, advance, ROOT, utc
from app import record, escalation, board, intake, labs, labcore, labviz, guard, llm, seed, db
from app.clock import clock


def test_every_lab_row_is_rendered_with_status_computed_from_value_and_range():
    conn, ob, ch = make("2026-11-03T08:30:00")
    seed_phase2(conn, date(2026, 11, 3))
    # the Phase 3 screenshot bug: values edited after loading, stored status left stale
    conn.execute("UPDATE lab_values SET value=1.2 WHERE test='serum creatinine' ")
    conn.execute("UPDATE lab_values SET status='above' WHERE test='serum creatinine' ")
    conn.execute("UPDATE lab_values SET value=137, status='below', range_text='135 - 145' WHERE test='sodium' ")
    conn.commit()
    n = 0
    html = labviz.section_html(labs.live_reports(conn))
    for r in labs.live_reports(conn):
        for t in r["tests"]:
            assert t["status"] == labcore.status(t["value"], t["range_text"]), (r["id"], t["test"])
            n += 1
    assert n >= 18
    for row in conn.execute("SELECT * FROM lab_values"):                  # every DB row, via the board state and the summary page
        want = labcore.status(row["value"], row["range_text"])
        rep = labs.report(conn, row["report_id"])
        assert [t["status"] for t in rep["tests"] if t["test"] == row["test"]][0] == want
    for s in board.state(conn, clock.now())["labs"]:
        for t in s["tests"]:
            assert t["status"] == labcore.status(t["value"], t["range_text"])
    page = board.doctor_html(conn, date(2026, 11, 2), date(2026, 11, 3), clock.now())
    assert "demo seed (fictional)" in html and "demo seed (fictional)" in page
    rid = conn.execute("SELECT report_id FROM lab_values WHERE test='sodium'").fetchone()[0]
    assert [t["status"] for t in labs.report(conn, rid)["tests"] if t["test"] == "sodium"] == ["within"]


def test_dose_past_grace_is_overdue_escalating_never_due_not_confirmed():
    conn, ob, ch = make("2026-11-02T02:40:00", all_tz="Asia/Kolkata")           # 08:10 IST, 10 min late
    seed_lines(conn, [("metformin", 500, "mg", ["08:00", "20:00"])], confirmed_at="2026-11-02T00:00:00Z")
    escalation.ensure_due_events(conn, clock.now())
    d = {x["slot"]: x["status"] for x in board.state(conn, clock.now())["doses"]}
    assert d["metformin_08:00"] == "due"                                          # inside the grace period only
    clock.set(utc("2026-11-02T02:47:00"), speed=0)                                # 08:17 IST: past due + grace, scheduler not yet nudged
    d = {x["slot"]: x["status"] for x in board.state(conn, clock.now())["doses"]}
    assert d["metformin_08:00"] == "overdue"
    escalation.tick(conn, ob)
    st = board.state(conn, clock.now())
    lad = [l for l in st["ladder"] if l["slot"] == "metformin_08:00"]
    assert lad and lad[0]["status"] == "overdue" and lad[0]["steps"]
    # the board page never carries the 'due, not confirmed' label for a past-grace dose
    assert all(x["status"] != "due" for x in st["doses"] if x["slot"] == "metformin_08:00")
    for _ in range(8):                                                            # ladder runs out
        advance(61)
        escalation.tick(conn, ob)
    assert record.status_of(conn, "metformin_08:00", date(2026, 11, 2), clock.now()) == "missed"
    assert record.status_of(conn, "metformin_20:00", date(2026, 11, 2), clock.now()) == "not_yet_due"


def test_missed_when_next_dose_of_same_medicine_falls_due():
    conn, ob, ch = make("2026-11-02T03:30:00", all_tz="Asia/Kolkata")
    seed_lines(conn, [("metformin", 500, "mg", ["08:00", "20:00"])], confirmed_at="2026-11-02T00:00:00Z")
    for m in ("m1", "m2", "m3", "m4", "m5"):
        record.set_relay_pref(conn, m, "stop")                                   # nobody to contact: only the next-dose rule can close it
    clock.set(utc("2026-11-02T14:31:00"), speed=0)                                # 20:01 IST
    escalation.tick(conn, ob)
    assert record.status_of(conn, "metformin_08:00", date(2026, 11, 2), clock.now()) == "missed"


def test_task_made_from_a_members_message_may_name_the_medicine():
    conn, ob, ch = make("2026-11-03T08:30:00", all_tz="Asia/Kolkata")           # fresh record: no metformin in it
    text = "can he have extra metformin ?"
    assert intake.handle  # imported
    intake._medical(conn, ob, "m3", text, clock.now())
    task = conn.execute("SELECT * FROM tasks").fetchone()
    assert task["text"] == f"Ask the doctor: {text}" and task["source"] == "medical question"
    ob.sent.clear()
    intake._volunteer(conn, ob, "m3", "I will", clock.now())
    mine = [t for m, t in ob.sent if m == "m3"]
    assert any("metformin" in t and "this task is yours" in t for t in mine)       # the creator/owner gets the real sentence
    relays = [t for m, t in ob.sent if m != "m3"]
    assert relays and all("metformin" in t for t in relays) and not any("I can't help with that here" in t for t in relays)
    assert not conn.execute("SELECT 1 FROM audit_log WHERE kind='guard_block'").fetchone()
    # everything else still gets the fallback: same drug in free text, and a different dose
    assert not guard.check(conn, "Meena says metformin is fine")[0]
    assert not guard.check(conn, "Kabir took a task: Ask the doctor: can he have extra metformin ? Take 900 mg")[0]


def test_dose_report_beats_question_routing(monkeypatch):
    conn, ob, ch = make("2026-11-03T14:30:00", all_tz="Asia/Kolkata")
    seed_lines(conn, [("atorvastatin", 20, "mg", ["20:00"])], confirmed_at="2026-11-02T00:00:00Z")
    calls = []

    def fake(phase, label, msgs, schema):
        calls.append(label)
        if label == "intent":
            return {"intent": "record_question"}, 0, 0
        return {"actor": "patient", "slot": "atorvastatin_20:00", "action": "given"}, 0, 0
    monkeypatch.setattr(llm, "spark_json", fake)
    for text in ("Nanaji took his atorvastatin", "Nanaji ne dawai le li", "Meena ne tablet de di"):
        calls.clear()
        assert intake._text(conn, ob, "m2", text) == "dose_update" and "parse" in calls
    assert conn.execute("SELECT COUNT(*) c FROM audit_log WHERE kind='intent_override'").fetchone()["c"] == 3
    monkeypatch.setattr(llm, "spark_json", lambda ph, lb, m, sc: ({"intent": "other"}, 0, 0) if lb == "intent" else fake(ph, lb, m, sc))
    for text in ("नानाजी ने दवाई ले ली", "ਨਾਨਾ ਜੀ ਨੇ ਦਵਾਈ ਖਾ ਲਈ"):
        assert intake._text(conn, ob, "m2", text) == "dose_update"                # a voice note the model called 'other' is still a dose report
    monkeypatch.setattr(llm, "spark_json", fake)
    calls.clear()                                                                 # a question mark, or no reported action: the model's call stands
    assert intake._text(conn, ob, "m2", "Did Nanaji take his atorvastatin?") == "record_question"
    assert intake._text(conn, ob, "m2", "What is due now") == "record_question"


def test_default_relay_choice_by_role():
    conn = db.connect(":memory:")
    seed.init(conn)
    got = {m["id"]: (m["role"], m["relay_pref"]) for m in record.members(conn)}
    assert all(p == ("daily" if r == "remote" else "everything") for r, p in got.values())
    assert got["m2"] == ("hands_on", "everything") and got["m1"] == ("remote", "daily")


# ---------------- demo scene: thursday ----------------
def test_demo_scene_thursday_organiser_photo_reports_wednesday_pm(monkeypatch):
    import json
    from datetime import timedelta
    from app import demo, vision
    conn, ob, ch = make("2026-11-02T00:30:00")
    target = demo.scene_thursday(conn, on=date(2026, 11, 2))
    conn.execute("UPDATE members SET language='en'")                           # Meena's Hindi replies are tested separately
    clock.set(target, speed=0)
    assert clock.now().astimezone(record.patient_tz(conn)).strftime("%a %H:%M") == "Thu 07:55"
    now = clock.now()
    # the record: Monday, Tuesday, Wednesday 08:00 confirmed; Wednesday 20:00 never confirmed; d1 confirmed by Meena; L2 by Kabir
    for d in (date(2026, 11, 2), date(2026, 11, 3)):
        assert all(record.status_of(conn, s, d, now) == "given" for s in record.slots(conn))
    wed = date(2026, 11, 4)
    assert all(record.status_of(conn, s, wed, now) == "given" for s in record.slots(conn) if s.endswith("08:00"))
    assert all(record.status_of(conn, s, wed, now) != "given" for s in record.slots(conn) if s.endswith("20:00"))
    assert conn.execute("SELECT confirmed_by FROM schedule_lines WHERE status='confirmed' LIMIT 1").fetchone()[0] == "m2"
    assert [r["confirmed_by"] for r in labs.live_reports(conn)] == ["m3"] and labs.live_reports(conn)[0]["origin"] == "demo seed (fictional)"
    # r2 sends or1: stub only the two model calls (photo type, compartment states from the advisor's reading of or1)
    labels = json.loads((ROOT / "tests" / "organiser_real_labels_v2.json").read_text(encoding="utf-8"))
    states = {k: v for k, v in labels["photos"]["or1"].items() if not k.startswith("_")}
    monkeypatch.setattr(vision, "prep", lambda src, name: (src, (1, 1)))
    monkeypatch.setattr(vision, "classify", lambda p, i: ("pill_organiser", 0.97, False))
    monkeypatch.setattr(vision, "organiser_states", lambda p, i: states)
    n0 = len(ob.sent)
    intake.handle(conn, ob, "m2", media={"path": "media/organiser_real/or1.jpeg", "mime": "image/jpeg"})
    reply = [t for m, t in ob.sent[n0:] if m == "m2"][0]
    assert reply == "Wednesday PM is still full in the organiser: that dose wasn't given."
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE kind='organiser_disagreement' AND detail LIKE 'WED_PM%'").fetchone()[0] == 1
    assert [m["compartment"] for m in board.state(conn, now)["organiser"]["mismatches"]] == ["WED_PM"]
    assert guard.check(conn, reply)[0]


# ---------------- replies in the member's language ----------------
def test_language_check_keeps_names_and_numbers_and_falls_back_to_english(monkeypatch):
    from app import lang
    conn, ob, ch = make("2026-11-03T08:30:00", all_tz="Asia/Kolkata")
    seed_lines(conn, [("metformin", 500, "mg", ["08:00", "20:00"])], confirmed_at="2026-11-02T00:00:00Z")
    conn.execute("UPDATE members SET language='hi' WHERE id='m2'")
    conn.commit()
    en = "Logged: metformin 08:00 given (Meena). Thanks."
    good, bad_num, bad_name = "दर्ज किया: metformin 08:00 दी गई (Meena). धन्यवाद।", "दर्ज किया: metformin 09:00 दी गई (Meena).", "दर्ज किया: मेटफॉर्मिन 08:00 दी गई (Meena)."
    assert lang.faithful(conn, en, good) and not lang.faithful(conn, en, bad_num) and not lang.faithful(conn, en, bad_name)
    assert not lang.faithful(conn, en, "दर्ज किया: metformin ०८:०० दी गई")      # Devanagari digits are rejected
    for reply, expect in ((good, good), (bad_num, en), (bad_name, en)):
        monkeypatch.setattr(llm, "spark_json", lambda ph, lb, m, sc, r=reply: ({"text": r}, 0, 0))
        assert ob.send("m2", en, "test", free=True) == expect
    assert sum(1 for r in conn.execute("SELECT kind FROM audit_log WHERE kind='lang_fallback'")) == 2
    ob.sent.clear()
    assert ob.send("m3", en, "test", free=True) == en                                    # an English member never reaches the model
