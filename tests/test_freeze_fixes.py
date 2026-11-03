"""Fixes made under the feature freeze (rehearsal bugs), each with a test."""
from helpers import make, seed_d1, advance
from app import board, demo, escalation, intake, labs, record
from app.clock import clock
from test_phase2 import stub_lab_router


def test_circle_labels_a_skipped_member_for_the_lead_dose_whatever_the_medicine_order():
    """The scheduler logs a skip once for a group of doses due together (against its first dose alphabetically); the board must show it for the dose that leads the Now card.
    The real d1 order has metformin first, so the lead (metformin) is not the dose the skip was logged against (amlodipine)."""
    conn, ob, ch = make("2026-11-05T02:58:30")                       # Thursday 08:28:30 in Kolkata, 02:58 in London, 03:58 in Madrid: both asleep
    seed_d1(conn, confirmed_at="2026-11-02T00:00:00Z")
    assert [l["name"] for l in record.lines(conn, "confirmed")][0] == "metformin"
    for _ in range(4):                                               # Meena nudged, Sunita asked, Arjun asked, then Kabir and Sofía skipped while they sleep
        escalation.tick(conn, ob)
        advance(61)
    st = board.state(conn, clock.now())
    lad = st["ladder"]
    assert [l["slot"] for l in lad][0] == "metformin_08:00"          # the lead dose of the Now card
    lead = lad[0]
    assert {s["who"] for s in lead["skipped"]} == {"Kabir", "Sofía"}
    assert all(s["why"].startswith("asleep (local ") for s in lead["skipped"])
    assert [s["why"] for s in lead["skipped"] if s["who"] == "Kabir"] == ["asleep (local 03:01)"]
    assert [x["who"] for x in lead["steps"]] == ["Meena", "Sunita", "Arjun"]
    for l in lad:                                                    # every dose of the group shows the same skips, once each
        assert [(s["actor"], s["why"]) for s in l["skipped"]] == [(s["actor"], s["why"]) for s in lead["skipped"]]
    html = open(board.__file__.replace("board.py", "board.html"), encoding="utf-8").read()
    assert "lead.skipped.forEach" in html                            # the page draws the label from the lead dose's skips


def test_monday_scene_accepts_an_l2_lab_photo_from_r3(monkeypatch):
    """Shot A8: after the schedule is live, Kabir (r3) sends the printed lab report L2, replies YES, and the others hear about it in their language with their own board link."""
    conn, ob, ch = make("2026-11-09T02:40:00")                       # Monday 08:10 in Kolkata
    demo.scene_monday(conn)                                          # fresh circle, everyone on "everything", m2 Hindi, m5 Spanish
    seed_d1(conn, confirmed_at="2026-11-09T02:15:00Z")               # the schedule from the earlier shot
    stub_lab_router(monkeypatch, "L2")
    res = intake.handle(conn, ob, "m3", media={"path": "x.jpg", "mime": "image/jpeg"})
    reply = res["replies"][0][1]
    assert "4 outside the lab's printed range" in reply and reply.rstrip().endswith("Reply YES if this matches the paper.")
    assert labs.live_reports(conn) == [] and labs.draft(conn)
    n0 = len(ob.sent)
    res = intake.handle(conn, ob, "m3", text="YES")
    assert res["intent"] == "yes_lab" and len(labs.live_reports(conn)) == 1
    got = {m: t for m, t in ob.sent[n0:] if m != "m3"}
    assert got["m3"] if "m3" in got else True
    assert got["m1"].startswith("Kabir added a lab report from 29 Oct: 4 values are outside the lab's printed range. See the board. Board (optional): ")
    assert got["m2"].startswith("Kabir ने 29 अक्टूबर की लैब रिपोर्ट जोड़ी: 4 नतीजे लैब की छपी हुई रेंज से बाहर हैं। बोर्ड पर देखें: ")
    assert got["m5"].startswith("Kabir añadió un análisis del 29 de octubre: 4 valores están fuera del rango impreso del laboratorio. Míralo en el tablero: ")
    assert {"m1", "m2", "m4", "m5"} <= set(got)
    assert len({got[k].rsplit("token=", 1)[1] for k in ("m1", "m2", "m5")}) == 3


def test_printed_thursday_steps_match_the_video_script_numbers(tmp_path):
    import os, pathlib, re, subprocess, sys
    root = pathlib.Path(__file__).resolve().parent.parent
    script = (root / "docs" / "VIDEO_SCRIPT.md").read_text(encoding="utf-8")
    row = next(l for l in script.splitlines() if l.startswith("| 1:15-1:55"))
    for n in ("Sunita is asked next", "19:01", "03:01", "04:01"):
        assert n in row, n
    env = dict(os.environ, CARECIRCLE_DB=str(tmp_path / "s.db"), ADMIN_TOKEN="", CARECIRCLE_DRY_RUN="")
    out = subprocess.run([sys.executable, str(root / "tools" / "demo_reset.py"), "--scene", "thursday"], capture_output=True, text=True, encoding="utf-8", env=env, timeout=60, cwd=root).stdout
    assert re.search(r'"Set time" to 2026-11-0\dT0[23]:\d\d:30Z \(Thursday 08:28:30 in Kolkata\)', out)            # the exact UTC time to type
    assert "Meena first, then Sunita, then Arjun, then Kabir and Sofía" in out and "Sunita (simulated, nearby) is asked next" in out
    assert "Kabir reads \"03:01 London\" with \"asleep, 02:58\"" in out and "19:01 Los Angeles" in out and "04:01 Madrid" in out and "Sofía" in out
    assert "one step per second" in out and "Arrives on r1 (Arjun, awake in Los Angeles" in out
