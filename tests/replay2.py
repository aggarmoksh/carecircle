"""Phase 2 offline end-to-end replay (live model calls, NO real WhatsApp sends: the channel is the dry-run capture).
d1 photo from m2 -> YES -> v01 voice note -> clock to Wednesday -> o3 photo -> L2 photo from m3 -> YES from m3 -> board state JSON.
Run: .venv/Scripts/python.exe tests/replay2.py"""
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from helpers import ROOT, utc
from app import db, seed, intake, channel, board, escalation
from app.clock import clock
from app.outbox import Outbox

DBF = ROOT / "data" / "replay2.db"
for f in (DBF, ROOT / "outputs" / "dryrun_outbox.jsonl"):
    f.unlink(missing_ok=True)
conn = db.connect(DBF)
seed.init(conn)
ob = Outbox(conn, channel.Router(dry_run=True))
M = ROOT / "media"
IMG = lambda folder, stem: str(next((M / folder).glob(stem + ".*")))
steps = [
    ("2026-11-02T01:00:00", "m2", dict(media={"path": IMG("discharge", "d1"), "mime": "image/jpeg"}), "d1 photo from m2 (Mon 06:30 IST)"),
    ("2026-11-02T01:01:00", "m2", dict(text="YES"), "YES from m2"),
    ("2026-11-02T02:40:00", "m2", dict(media={"path": IMG("voice", "v01"), "mime": "audio/ogg"}), "v01 voice note from m2 (Mon 08:10 IST)"),
    ("2026-11-04T06:30:00", "m2", dict(media={"path": IMG("organiser", "o3"), "mime": "image/jpeg"}), "o3 photo from m2 (Wed 12:00 IST)"),
    ("2026-11-04T16:00:00", "m3", dict(media={"path": IMG("labs", "L2"), "mime": "image/jpeg"}), "L2 lab photo from m3 (Wed 16:00 London)"),
    ("2026-11-04T16:01:00", "m3", dict(text="YES"), "YES from m3"),
]
for when, who, kw, label in steps:
    clock.set(utc(when), speed=0)
    escalation.ensure_due_events(conn, clock.now())  # what the scheduler does every second (creates 'due' events; sends nothing)
    res = intake.handle(conn, ob, who, **kw)
    print(f"{label}: route={res['route']} type={res['type']} intent={res['intent']}")
    for m, t in res["replies"]:
        print(f"   -> {m}: {t[:400].replace(chr(10), ' | ')}")

rows = [dict(r) for r in conn.execute("SELECT at,kind,actor,detail,reason FROM audit_log ORDER BY id")]
(ROOT / "outputs" / "replay2_audit.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
st = board.state(conn, clock.now())
(ROOT / "outputs" / "replay2_board_state.json").write_text(json.dumps(st, indent=1), encoding="utf-8")
txt = "\n".join(str(r["detail"]) for r in rows)
oor = [(t["test"], t["status"]) for r in st["labs"] for t in r["tests"] if t["status"] in ("above", "below")]
checks = {
    "board schedule shows the 4 confirmed medicines": sorted(x["medicine"] for x in st["schedule"]) == ["amlodipine", "aspirin", "atorvastatin", "metformin"],
    "v01 logged as metformin_08:00 confirmed by m2": bool(conn.execute("SELECT 1 FROM dose_events WHERE slot='metformin_08:00' AND type='confirmed' AND actor='m2'").fetchone()),
    "audit: TUE_PM full, no confirmation": "TUE_PM full, no confirmation" in txt,
    "board organiser mismatches include TUE_PM": bool(st["organiser"]) and any(m["compartment"] == "TUE_PM" for m in st["organiser"]["mismatches"]),
    "board shows 4 out-of-range values": len(oor) == 4 and st["lab_latest"]["out_of_range"] == 4,
    "lab report live only after YES (draft_created before lab_confirmed)": [r["kind"] for r in rows if r["kind"] in ("lab_draft_created", "lab_confirmed")] == ["lab_draft_created", "lab_confirmed"],
    "relay delivered to m2 and the simulated members; m1 queued (no open 24h window in the replay)": all(any(r["kind"] == "outbound" and r["actor"] == m and "added a lab report from 29 Oct: 4 values" in str(r["detail"]) for r in rows) for m in ("m2", "m4", "m5")) and any(r["kind"] == "relay_queued" and r["actor"] == "m1" and "lab report" in str(r["detail"]) for r in rows),
    "no real sends (only dry-run/sim)": not any(r["kind"] == "outbound" and str(r["detail"]).find("SM") >= 0 for r in rows),
}
print("\nAUDIT LOG (kind | actor | detail):")
for r in rows:
    print(" ", r["at"][11:19], r["kind"], "|", r["actor"], "|", str(r["detail"])[:110].replace("\n", " "))
print("\nBOARD STATE: schedule", [(x["medicine"], x["times"]) for x in st["schedule"]], "| mismatches", st["organiser"] and [m["compartment"] for m in st["organiser"]["mismatches"]], "| out of range", oor)
print()
for k, v in checks.items():
    print("PASS" if v else "FAIL", k)
(ROOT / "outputs" / "replay2_result.json").write_text(json.dumps(dict(checks=checks, out_of_range=oor), indent=1), encoding="utf-8")
