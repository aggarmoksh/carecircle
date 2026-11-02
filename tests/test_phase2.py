"""Phase 2 unit tests: no model calls (extraction and classification are stubbed where the router is exercised)."""
import json, subprocess, sys
from datetime import date
import pytest
from helpers import make, seed_phase2, seed_d1, ROOT, utc
from app import labs, labcore, guard, qa, record, board, intake, vision, db
from app.clock import clock

LAB = json.loads((ROOT / "tests" / "lab_labels.json").read_text(encoding="utf-8"))["reports"]
NOW = "2026-11-03T08:30:00"  # 14:00 IST Tuesday


def circle():
    conn, ob, ch = make(NOW)
    seed_phase2(conn, date(2026, 11, 3))
    return conn, ob, ch


def test_one_sided_range_wording():
    t = dict(status="below", parsed_low=60.0, parsed_high=None, range_text="> 60")
    assert labs.range_phrase(t) == "below the lab's printed range (more than 60)"
    assert labs.range_phrase(dict(status="no_range", parsed_low=None, parsed_high=None, range_text="")) == "no range printed"


def test_status_rules_reproduce_every_label():
    n = 0
    for rep in LAB.values():
        for t in rep["tests"]:
            assert labcore.parse_range(t["range_text"]) == (t["range_low"], t["range_high"]), t["test"]
            assert labcore.status(t["value"], t["range_text"]) == t["expected_status"], t["test"]
            n += 1
    assert n == 18


def test_range_parser_edge_cases():
    assert labcore.parse_range("4,000 – 11,000") == (4000.0, 11000.0)
    assert labcore.parse_range("") == (None, None)
    assert labcore.parse_range("see note") == (None, None)
    assert labcore.status(5.0, "3.5 - 5.0") == "within"          # inclusive bounds
    assert labcore.status(150, "< 150") == "above"               # '< b' is exclusive
    assert labcore.status(60, "> 60") == "below"                 # '> a' is exclusive
    assert labcore.status(18, "") == "no_range"
    assert labcore.norm_unit(" µIU / mL ") == "uiu/ml"


def test_guard_allows_record_lab_values_and_blocks_others():
    conn, ob, ch = circle()
    assert guard.check(conn, "serum creatinine: 1.4 mg/dL, above the lab's printed range 0.7 to 1.3")[0]
    assert guard.check(conn, "hba1c 8.2 %")[0]
    assert guard.check(conn, "tsh 6.8 uIU/mL")[0]
    ok, why = guard.check(conn, "His sodium is 140 mmol/L")
    assert not ok and "lab value" in why
    ok, why = guard.check(conn, "creatinine 1.5 mg/dL")
    assert not ok


def test_code_queries_return_record_facts():
    conn, ob, ch = circle()
    now = clock.now()
    r = qa.run(conn, dict(query="on_duty", period="morning"), now)
    assert "Meena" in r["plain"][0]
    r = qa.run(conn, dict(query="on_duty", period="tonight"), now)
    assert "Sunita (simulated)" in r["plain"][0]
    r = qa.run(conn, dict(query="due", window="08:00"), now)
    assert {f["medicine"] for f in r["facts"]} == {"metformin", "amlodipine", "aspirin"}
    r = qa.run(conn, dict(query="due", window="8 am"), now)
    assert {f["medicine"] for f in r["facts"]} == {"metformin", "amlodipine", "aspirin"}
    r = qa.run(conn, dict(query="skip_reason", slot="metformin_20:00", date="recent"), now)
    assert r["facts"][0]["status"] == "skipped" and r["facts"][0]["reason"] == "stomach upset" and r["facts"][0]["by"] == "Meena"
    r = qa.run(conn, dict(query="who_gave", slot=None, date="today"), now)
    assert r["facts"][0]["given_by"]["Nanaji himself"] == ["atorvastatin 20 mg at 20:00 (last night)"]
    assert "Meena" in r["facts"][0]["given_by"]
    r = qa.run(conn, dict(query="lab_value", test="hba1c", report="latest"), now)
    assert r["facts"][0]["wording"] == "above the lab's printed range 4.0 to 5.6"
    assert r["facts"][0]["value"] == "8.2" and r["facts"][0]["status"] == "above" and r["facts"][0]["report_date"] == "25 Oct"
    r = qa.run(conn, dict(query="lab_value", test="potassium", report="latest"), now)
    assert "within the lab's printed range 3.5 to 5" in r["facts"][0]["wording"]
    r = qa.run(conn, dict(query="out_of_range", report="latest"), now)
    assert [(t["test"], t["status"]) for t in r["facts"][0]["outside"]] == [("serum creatinine", "above"), ("egfr", "below"), ("sodium", "below"), ("tsh", "above")]
    r = qa.run(conn, dict(query="med_list"), now)
    assert r["facts"][0]["count"] == 4
    assert qa.run(conn, dict(query="lab_value", test="ferritin", report="latest"), now) is None


def test_faithfulness_rejects_a_new_number():
    facts = json.dumps([dict(value="8.2", unit="%")])
    assert qa.faithful("Yes, it was 8.2%.", facts, "hba1c?")
    assert not qa.faithful("It was 8.2% and 9.9 last time.", facts, "hba1c?")


def stub_lab_router(monkeypatch, key="L2"):
    raw = dict(lab=LAB[key]["lab"], report_date=LAB[key]["report_date"],
               tests=[dict(test=t["test"], value=t["value"], unit=t["unit"], range_text=t["range_text"], range_low=t["range_low"], range_high=t["range_high"], printed_flag=t["printed_flag"]) for t in LAB[key]["tests"]])
    monkeypatch.setattr(vision, "prep", lambda src, name: (src, (1, 1)))
    monkeypatch.setattr(vision, "classify", lambda p, i: ("lab_report", 0.95, False))
    monkeypatch.setattr(labs, "extract", lambda p, i: labcore.finish(raw))


def test_lab_photo_is_draft_until_yes_then_relay(monkeypatch):
    conn, ob, ch = make("2026-11-04T16:00:00")
    seed_d1(conn)
    stub_lab_router(monkeypatch)
    res = intake.handle(conn, ob, "m3", media={"path": "x.jpg", "mime": "image/jpeg"})
    reply = res["replies"][0][1]
    assert "4 outside the lab's printed range" in reply and "above the lab's printed range 0.7 to 1.3" in reply
    assert "no range printed" not in reply.lower() or "vitamin d" in reply
    assert reply.rstrip().endswith("Reply YES if this matches the paper.")
    assert labs.live_reports(conn) == [] and labs.draft(conn)            # nothing live before YES
    n0 = len(ob.sent)
    res = intake.handle(conn, ob, "m3", text="YES")
    assert res["intent"] == "yes_lab" and len(labs.live_reports(conn)) == 1
    relays = {m: t for m, t in ob.sent[n0:] if m != "m3"}
    want = "Kabir added a lab report from 29 Oct: 4 values are outside the lab's printed range. See the board."
    assert relays["m1"] == want and relays["m2"] == want and relays["m4"] == want
    assert any(r["kind"] == "lab_confirmed" for r in conn.execute("SELECT kind FROM audit_log"))


def test_lab_question_is_a_medical_question_not_a_lab_answer():
    # the fixed medical reply is code; here only the guard/fixed-reply contract is checked (no model)
    from app.outbox import FIXED_MEDICAL
    conn, ob, ch = circle()
    assert guard.check(conn, FIXED_MEDICAL)[0]


def test_board_state_and_charts():
    conn, ob, ch = circle()
    s = board.state(conn, clock.now())
    assert [m["name"] for m in s["members"]] == ["Arjun", "Meena", "Kabir", "Sunita", "Ravi"]
    assert {m["name"] for m in s["members"] if m["simulated"]} == {"Sunita", "Ravi"}
    assert s["lab_latest"] == dict(date="2026-10-29", out_of_range=4)
    assert "trendbox" not in s["lab_html"]                               # no test appears in two reports in the seed
    labs.load_fixture(conn, ROOT / "tests" / "lab_labels.json", "L1", "m3", "2026-10-31T00:00:00Z")
    conn.execute("UPDATE lab_reports SET report_date='2026-09-20' WHERE id=3")
    conn.execute("INSERT INTO lab_values(report_id,test,value,unit,range_text,range_low,range_high,printed_flag,status) VALUES(2,'hba1c',7.9,'%','4.0 - 5.6',4.0,5.6,'H','above')")
    conn.commit()
    assert "trendbox" in board.state(conn, clock.now())["lab_html"]      # a test in 2+ reports gets a trend (Phase 3: server-built SVG)


def test_doctor_summary_adherence_and_footer():
    conn, ob, ch = circle()
    rows, misses = board.adherence(conn, date(2026, 11, 3), date(2026, 11, 3), clock.now())
    got = {r["medicine"]: (r["confirmed"], r["due"]) for r in rows}
    assert got["metformin"] == (1, 1) and got["aspirin"] == (1, 1)       # 08:00 doses due today, confirmed; evening not yet due
    rows, misses = board.adherence(conn, date(2026, 11, 2), date(2026, 11, 3), clock.now())
    assert any(m["medicine"] == "metformin" and m["time"] == "20:00" and m["reason"] == "stomach upset" for m in misses)
    page = board.doctor_html(conn, date(2026, 11, 2), date(2026, 11, 3), clock.now())
    assert "Prepared by CareCircle from records kept by the family. Not medical advice." in page
    assert "above the lab's printed range" in page and "no range printed" in page


def test_next_due_jumps_forward():
    conn, ob, ch = circle()
    slot, t = record.next_due(conn, clock.now())
    assert slot.endswith("20:00") and t > clock.now()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_TICKER", "0")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    from app import server
    from fastapi.testclient import TestClient
    monkeypatch.setenv("BOARD_TOKEN", "board-test-token")
    monkeypatch.setenv("ADMIN_TOKEN", "admin-test-token")
    with TestClient(server.app) as c:
        yield c


def test_board_requires_board_token(client):
    assert client.get("/board").status_code == 403
    assert client.get("/board?token=wrong").status_code == 403
    assert client.get("/api/state").status_code == 403
    assert client.get("/doctor").status_code == 403
    r = client.get("/board?token=board-test-token")
    assert r.status_code == 200 and "CareCircle board" in r.text
    s = client.get("/api/state?token=board-test-token").json()
    assert {"members", "doses", "ladder", "organiser", "labs", "tasks", "audit", "schedule"} <= set(s)
    assert client.get("/doctor?token=board-test-token").status_code == 200


def test_admin_requires_admin_token_and_logs(client):
    body = {"time": "2026-11-03T08:30:00Z", "speed": 0}
    assert client.post("/admin/clock", json=body).status_code == 403
    assert client.post("/admin/clock", json=body, headers={"X-Admin-Token": "board-test-token"}).status_code == 403
    r = client.post("/admin/clock", json=body, headers={"X-Admin-Token": "admin-test-token"})
    assert r.status_code == 200 and r.json()["now"].startswith("2026-11-03T08:30")
    conn = db.connect()
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE kind='clock_set'").fetchone()[0] == 1
    assert client.post("/admin/clock", json={"action": "next_due"}, headers={"X-Admin-Token": "admin-test-token"}).status_code == 409  # no schedule yet


def test_doc_extract_refuses_output_inside_repo(tmp_path):
    img = tmp_path / "x.jpg"
    img.write_bytes(b"not an image")
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "doc_extract.py"), str(img), str(ROOT / "outputs" / "should_not_exist")], capture_output=True, text=True)
    assert r.returncode != 0 and not (ROOT / "outputs" / "should_not_exist").exists()
