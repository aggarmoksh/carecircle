"""Phase 3 unit tests: member relay choice, missed-dose catch-up, unsure extraction lines, lab graphics, demo reset. No model calls."""
import re
from datetime import date, timedelta
import pytest
from helpers import make, seed_phase2, seed_d1, seed_lines, advance, ROOT, utc
from app import record, escalation, board, intake, labs, labviz, demo, prompts, llm
from app.clock import clock

NOW = "2026-11-03T08:30:00"  # 14:00 IST Tuesday: m1 (LA) asleep, m3 (London) awake, m2 awake


def circle(now=NOW, tz=None):
    conn, ob, ch = make(now, all_tz=tz)
    return conn, ob, ch


def sent_to(ch, mid):
    return [t for m, t in ch.log if m == mid]


# ---------------- relay choice ----------------
def test_everything_gets_relays_and_duties_does_not():
    conn, ob, ch = circle(tz="Asia/Kolkata")
    record.set_relay_pref(conn, "m3", "duties")
    ob.relay("CareCircle: Meena gave metformin 08:00.", ["m2"], "state change: dose event")
    assert sent_to(ch, "m1") and not sent_to(ch, "m3")
    row = conn.execute("SELECT * FROM audit_log WHERE kind='relay_suppressed' AND actor='m3'").fetchone()
    assert row and "only duties and alerts" in row["reason"]


def test_duties_member_still_gets_alerts_and_nudges():
    conn, ob, ch = circle(tz="Asia/Kolkata")
    record.set_relay_pref(conn, "m3", "duties")
    ob.relay("CareCircle: metformin 08:00 for Nanaji is recorded as missed.", [], "state change: dose missed", kind="alert")
    assert sent_to(ch, "m3")


def test_daily_choice_batches_into_one_8pm_summary():
    conn, ob, ch = circle("2026-11-03T08:30:00", tz="Asia/Kolkata")
    seed_d1(conn)                                          # the guard only lets record medicine names through
    record.set_relay_pref(conn, "m3", "daily")
    ob.relay("CareCircle: Meena gave metformin 08:00.", ["m2"], "state change: dose event")
    ob.relay("CareCircle: Meena gave amlodipine 08:00.", ["m2"], "state change: dose event")
    assert not sent_to(ch, "m3")
    ob.flush_queue()
    assert not sent_to(ch, "m3")                          # 14:00 local: not yet 8 PM
    clock.set(utc("2026-11-03T14:40:00"), speed=0)         # 20:10 IST
    record.touch_inbound(conn, "m3", clock.now())
    ob.flush_queue()
    got = sent_to(ch, "m3")
    assert len(got) == 1 and got[0].startswith("CareCircle daily summary:") and got[0].count("- ") == 2
    ob.flush_queue()
    assert len(sent_to(ch, "m3")) == 1                    # delivered once


def test_stop_stops_everything_and_writing_again_ends_it():
    conn, ob, ch = circle(tz="Asia/Kolkata")
    res = intake.handle(conn, ob, "m3", text="STOP")
    assert res["intent"] == "relay_choice" and record.member(conn, "m3")["relay_pref"] == "stop"
    assert len(sent_to(ch, "m3")) == 1                    # the one acknowledgement
    ob.relay("CareCircle: something happened.", ["m2"], "state change", kind="alert")
    assert len(sent_to(ch, "m3")) == 1                    # not even alerts
    assert ob.send("m3", "hello", "test") is None
    assert conn.execute("SELECT 1 FROM audit_log WHERE kind='send_suppressed' AND actor='m3'").fetchone()
    intake.handle(conn, ob, "m3", text="STOP")            # writing STOP again keeps it stopped
    assert record.member(conn, "m3")["relay_pref"] == "stop"


def test_writing_again_lifts_stop(monkeypatch):
    conn, ob, ch = circle(tz="Asia/Kolkata")
    intake.handle(conn, ob, "m3", text="stop")
    monkeypatch.setattr(llm, "spark_json", lambda *a, **k: ({"intent": "other"}, 0, 0))
    intake.handle(conn, ob, "m3", text="hello again")
    assert record.member(conn, "m3")["relay_pref"] == "everything"
    assert conn.execute("SELECT 1 FROM audit_log WHERE kind='relay_pref' AND detail='everything'").fetchone()


def test_urgent_alert_skips_a_stopped_member():
    conn, ob, ch = circle(tz="Asia/Kolkata")
    record.set_relay_pref(conn, "m3", "stop")
    intake._urgent(conn, ob, "m2", "he has chest pain", clock.now())
    assert not sent_to(ch, "m3") and sent_to(ch, "m1")
    assert conn.execute("SELECT 1 FROM audit_log WHERE kind='urgent_alert_skipped' AND actor='m3' AND detail='chose STOP'").fetchone()


@pytest.mark.parametrize("text,choice", [("send me everything", "everything"), ("only my duties and alerts", "duties"),
                                         ("daily summary at 8 PM", "daily"), ("please stop the messages", "stop")])
def test_all_four_choices_through_the_router(monkeypatch, text, choice):
    conn, ob, ch = circle(tz="Asia/Kolkata")
    record.set_relay_pref(conn, "m3", "duties" if choice != "duties" else "everything")

    def stub(probe, item, messages, schema, effort="low"):
        return ({"intent": "relay_choice"} if schema["name"] == "intent" else {"choice": choice}), 0, 0
    monkeypatch.setattr(llm, "spark_json", stub)
    res = intake.handle(conn, ob, "m3", text=text)
    assert res["intent"] == "relay_choice"
    assert record.member(conn, "m3")["relay_pref"] == choice
    assert sent_to(ch, "m3")[-1] == intake.CHOICE_REPLY[choice]


def test_ladder_skips_a_stopped_member_and_logs_why():
    conn, ob, ch = circle("2026-11-02T02:44:00", tz="Asia/Kolkata")
    seed_lines(conn, [("metformin", 500, "mg", ["08:00"])], confirmed_at="2026-11-02T00:00:00Z")
    record.set_relay_pref(conn, "m2", "stop")             # m2 is on duty for the morning
    advance(70)
    for _ in range(8):
        escalation.tick(conn, ob)
        advance(61)
    nudged = [m for m, t in ch.log if "confirmed" in t]
    assert "m2" not in nudged and nudged[0] == "m4"
    why = conn.execute("SELECT detail FROM audit_log WHERE kind='escalation_skip' AND actor='m2'").fetchone()
    assert why and "chose STOP" in why["detail"]


def test_board_shows_each_members_choice():
    conn, ob, ch = circle()
    record.set_relay_pref(conn, "m3", "daily")
    st = board.state(conn, clock.now())
    assert {m["id"]: m["relay"] for m in st["members"]}["m3"] == "daily"
    assert {m["relay"] for m in st["members"] if m["id"] != "m3"} == {"everything"}


# ---------------- missed-dose fix ----------------
def test_old_unconfirmed_doses_become_missed_when_the_scheduler_runs():
    conn, ob, ch = circle("2026-11-02T00:30:00", tz="Asia/Kolkata")
    seed_lines(conn, [("metformin", 500, "mg", ["08:00"])], confirmed_at="2026-11-02T00:00:00Z")
    clock.set(utc("2026-11-06T09:00:00"), speed=0)       # four days later, scheduler had been stopped
    assert record.status_of(conn, "metformin_08:00", date(2026, 11, 3), clock.now()) == "overdue"   # the old bug: nothing ever closed it
    escalation.tick(conn, ob)
    for d in (date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4)):
        assert record.status_of(conn, "metformin_08:00", d, clock.now()) == "missed"
        assert any(e["type"] == "missed" for e in record.events(conn, "metformin_08:00", d))
    assert conn.execute("SELECT COUNT(*) c FROM audit_log WHERE kind='dose_missed'").fetchone()["c"] >= 3
    n = conn.execute("SELECT COUNT(*) c FROM dose_events WHERE type='missed'").fetchone()["c"]
    escalation.tick(conn, ob)
    assert conn.execute("SELECT COUNT(*) c FROM dose_events WHERE type='missed'").fetchone()["c"] == n   # settled once


def test_confirmed_doses_are_never_marked_missed():
    conn, ob, ch = circle("2026-11-02T03:00:00", tz="Asia/Kolkata")
    seed_lines(conn, [("metformin", 500, "mg", ["08:00"])], confirmed_at="2026-11-02T00:00:00Z")
    record.log_confirmation(conn, "metformin_08:00", "given", "m2", "m2", "t", None, clock.now())
    clock.set(utc("2026-11-05T09:00:00"), speed=0)
    escalation.settle_missed(conn, clock.now())
    assert record.status_of(conn, "metformin_08:00", date(2026, 11, 2), clock.now()) == "given"


def test_board_ladder_shows_only_todays_open_doses_and_summary_says_missed():
    conn, ob, ch = circle("2026-11-02T00:30:00", tz="Asia/Kolkata")
    seed_lines(conn, [("metformin", 500, "mg", ["08:00", "20:00"])], confirmed_at="2026-11-02T00:00:00Z")
    clock.set(utc("2026-11-04T03:00:00"), speed=0)       # Wed 08:30 IST: today's 08:00 is open
    escalation.ensure_due_events(conn, clock.now())
    st = board.state(conn, clock.now())
    assert st["ladder"] and all(l["date"] == "2026-11-04" for l in st["ladder"])
    escalation.settle_missed(conn, clock.now())
    st = board.state(conn, clock.now())
    html = board.doctor_html(conn, date(2026, 11, 2), date(2026, 11, 4), clock.now())
    assert "missed" in html and "<td>missed</td>" in html
    assert not any(l["date"] != "2026-11-04" for l in st["ladder"])


# ---------------- unsure extraction lines ----------------
def meds(unsure=False):
    return [dict(name="metformin", name_as_printed="Glycomet", generic_if_printed="metformin", legibility="clear", dose_amount=500, dose_unit="mg",
                 frequency="twice_daily", with_food="yes", times=["08:00", "20:00"], notes=""),
            dict(name="telmisartan", name_as_printed="Telma ?", generic_if_printed="", legibility="unsure" if unsure else "clear", dose_amount=40, dose_unit="mg",
                 frequency="once_daily", with_food="unspecified", times=["08:00"], notes="")]


def test_schema_requires_the_new_fields():
    props = prompts.EXTRACT_SCHEMA["schema"]["properties"]["meds"]["items"]
    for f in ("name_as_printed", "generic_if_printed", "legibility"):
        assert f in props["required"] and f in props["properties"]
    assert props["properties"]["legibility"]["enum"] == ["clear", "unsure"]


def test_unsure_line_is_marked_and_blocks_yes_until_named():
    conn, ob, ch = circle(tz="Asia/Kolkata")
    record.add_draft(conn, 1, meds(unsure=True), record.iso(clock.now()))
    assert record.draft_summary(conn)[1].startswith("2. ? ") and not record.draft_summary(conn)[0].startswith("1. ?")
    res = intake.handle(conn, ob, "m2", text="YES")
    assert res["intent"] == "yes_blocked" and not record.lines(conn, "confirmed")
    assert "line 2" in sent_to(ch, "m2")[-1] and "marked ?" in sent_to(ch, "m2")[-1]
    record.apply_ops(conn, [dict(line=2, field="name", value="telmisartan")])
    assert record.unsure_lines(conn) == [] and "?" not in record.draft_summary(conn)[1]
    intake.handle(conn, ob, "m2", text="YES")
    assert len(record.lines(conn, "confirmed")) == 2


def test_removing_the_unsure_line_also_lets_yes_through():
    conn, ob, ch = circle(tz="Asia/Kolkata")
    record.add_draft(conn, 1, meds(unsure=True), record.iso(clock.now()))
    record.apply_ops(conn, [dict(line=2, field="remove", value="")])
    intake.handle(conn, ob, "m2", text="YES")
    assert [l["name"] for l in record.lines(conn, "confirmed")] == ["metformin"]


def test_clear_lines_are_not_blocked():
    conn, ob, ch = circle(tz="Asia/Kolkata")
    record.add_draft(conn, 1, meds(unsure=False), record.iso(clock.now()))
    assert intake.handle(conn, ob, "m2", text="YES")["intent"] == "yes"


# ---------------- lab graphics ----------------
def test_range_bar_shapes():
    both = dict(test="x", value=11.8, unit="g/dL", range_text="13.0 - 17.0", parsed_low=13.0, parsed_high=17.0, status="below")
    low_only = dict(test="egfr", value=48.0, unit="mL/min", range_text="> 60", parsed_low=60.0, parsed_high=None, status="below")
    none = dict(test="vitamin d", value=18.0, unit="ng/mL", range_text="", parsed_low=None, parsed_high=None, status="no_range")
    assert labviz.range_bar(none) == ""
    s = labviz.range_bar(both)
    assert "13.0" in s and "17.0" in s and "<path" in s
    o = labviz.range_bar(low_only)
    assert ">60<" in o.replace(" ", "") or "60" in o
    assert o.count("<path") == 2                          # marker + the open-end arrow
    assert "17.0<" not in o and ">17<" not in o              # no upper-end label on an open-ended band


def test_out_of_range_first_with_count_heading_and_words():
    conn, ob, ch = circle()
    labs.load_fixture(conn, ROOT / "tests" / "lab_labels.json", "L2", "m3", "2026-10-30T00:00:00Z")
    html = labviz.section_html(labs.live_reports(conn))
    assert "4 of 9 outside the lab's printed range" in html
    rows = re.findall(r'<tr class="(above|below|within|no_range)">', html)
    assert rows[:4] == ["above", "below", "below", "above"] or set(rows[:4]) <= {"above", "below"}
    assert all(r in ("within", "no_range") for r in rows[4:])
    assert rows[-1] == "no_range"                         # vitamin d: no range printed, last, no bar
    assert "no range printed" in html and "▲" in html and "▼" in html


def test_no_forbidden_words_anywhere_in_the_graphics_or_summary():
    conn, ob, ch = circle()
    seed_phase2(conn, date(2026, 11, 3))
    rx = re.compile(r"\b(normal|abnormal|danger\w*|risk\w*|good|bad)\b", re.I)
    st = board.state(conn, clock.now())
    assert not rx.search(st["lab_html"])
    assert not rx.search(board.doctor_html(conn, date(2026, 10, 28), date(2026, 11, 3), clock.now()))
    assert not rx.search((ROOT / "app" / "board.html").read_text(encoding="utf-8"))


def test_trend_with_printed_band_when_a_test_is_in_two_reports():
    conn, ob, ch = circle()
    a = labs.load_fixture(conn, ROOT / "tests" / "lab_labels.json", "L2", "m3", "2026-09-30T00:00:00Z")
    conn.execute("UPDATE lab_reports SET report_date='2026-09-29' WHERE id=?", (a,))
    labs.load_fixture(conn, ROOT / "tests" / "lab_labels.json", "L2", "m3", "2026-10-30T00:00:00Z")
    conn.commit()
    reps = labs.live_reports(conn)
    out = labviz.trends_html(reps)
    assert out.count('class="trendbox"') == 9 and "<polyline" in out and "printed range on the latest report" in out
    assert labviz.trends_html(reps[:1]) == ""             # one report: no trend


# ---------------- demo reset ----------------
def test_demo_reset_restores_the_start_state():
    conn, ob, ch = circle("2026-11-03T08:30:00", tz="Asia/Kolkata")
    seed_phase2(conn, date(2026, 11, 3))
    record.set_relay_pref(conn, "m3", "stop")
    demo.reset(conn)
    assert not record.lines(conn, "confirmed") and not record.lines(conn, "draft")
    assert conn.execute("SELECT COUNT(*) c FROM dose_events").fetchone()["c"] == 0
    assert conn.execute("SELECT COUNT(*) c FROM lab_reports").fetchone()["c"] == 0
    assert [m["id"] for m in record.members(conn)] == ["m1", "m2", "m3", "m4", "m5"]
    assert {m["relay_pref"] for m in record.members(conn)} == {"everything"}
    assert record.on_duty(conn, "metformin_08:00") == "m2"
    t = demo.start_time(conn, date(2026, 11, 3))
    assert t == utc("2026-11-03T02:25:00")                 # 07:55 IST


# ---------------- advisor round 2: units, handwriting, missed rule ----------------
def test_unit_is_kept_as_printed_never_converted():
    props = prompts.EXTRACT_SCHEMA["schema"]["properties"]["meds"]["items"]["properties"]
    assert {"tsf", "tbsp", "sachet", "other"} <= set(props["dose_unit"]["enum"]) and "unit_as_printed" in props
    assert "NEVER convert" in prompts.EXTRACT_PROMPT
    conn, ob, ch = circle(tz="Asia/Kolkata")
    m = meds()
    m[0].update(name="cough syrup", dose_amount=2, dose_unit="tsf", unit_as_printed="")
    m[1].update(dose_amount=1, dose_unit="other", unit_as_printed="scoop")
    record.add_draft(conn, 1, m, record.iso(clock.now()))
    s = record.draft_summary(conn)
    assert s[0].startswith("1. cough syrup 2 tsf,") and "mL" not in s[0]       # 2 TSF is not 2 mL
    assert s[1].startswith("2. telmisartan 1 scoop,")


def test_handwritten_document_marks_every_line_unsure_and_blocks_yes():
    props = prompts.CLASSIFY_SCHEMA["schema"]
    assert "has_handwriting" in props["required"]
    conn, ob, ch = circle(tz="Asia/Kolkata")
    record.add_draft(conn, 1, meds(unsure=False), record.iso(clock.now()), hand=True)    # both lines came back 'clear'
    assert [l["legibility"] for l in record.lines(conn, "draft")] == ["unsure", "unsure"]
    assert all(x.split(". ", 1)[1].startswith("? ") for x in record.draft_summary(conn))
    assert intake.handle(conn, ob, "m2", text="YES")["intent"] == "yes_blocked"
    record.apply_ops(conn, [dict(line=1, field="name", value="metformin"), dict(line=2, field="name", value="telmisartan")])
    assert intake.handle(conn, ob, "m2", text="YES")["intent"] == "yes"


def test_printed_document_keeps_per_line_legibility():
    conn, ob, ch = circle(tz="Asia/Kolkata")
    record.add_draft(conn, 1, meds(unsure=False), record.iso(clock.now()), hand=False)
    assert record.unsure_lines(conn) == []


def test_dose_is_overdue_escalating_after_grace_and_missed_when_next_dose_falls_due():
    conn, ob, ch = circle("2026-11-02T00:30:00", tz="Asia/Kolkata")
    seed_lines(conn, [("metformin", 500, "mg", ["08:00", "20:00"])], confirmed_at="2026-11-02T00:00:00Z")
    d = date(2026, 11, 2)
    clock.set(utc("2026-11-02T02:50:00"), speed=0)       # 08:20 IST: 20 min past due, past the 15 min grace
    assert record.status_of(conn, "metformin_08:00", d, clock.now()) == "overdue"
    clock.set(utc("2026-11-02T08:00:00"), speed=0)       # 13:30 IST: 5.5 h late, 12 h rule would not fire; next dose (20:00) not yet due
    escalation.settle_missed(conn, clock.now())
    assert record.status_of(conn, "metformin_08:00", d, clock.now()) != "missed"
    clock.set(utc("2026-11-02T14:31:00"), speed=0)       # 20:01 IST: the next metformin dose has fallen due
    escalation.settle_missed(conn, clock.now())
    assert record.status_of(conn, "metformin_08:00", d, clock.now()) == "missed"
    assert record.status_of(conn, "metformin_20:00", d, clock.now()) != "missed"
