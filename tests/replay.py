"""Offline end-to-end replay (live model calls, NO real WhatsApp sends: the channel is the dry-run capture).
d1 photo from m2 -> YES from m2 -> v01 voice note from m2 -> clock to Wednesday -> o3 photo from m2.
Run: .venv/Scripts/python.exe tests/replay.py"""
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from helpers import ROOT, utc
from app import db, seed, intake, channel
from app.clock import clock
from app.outbox import Outbox

DBF = ROOT / "data" / "replay.db"
for f in (DBF, ROOT / "outputs" / "dryrun_outbox.jsonl"):
    f.unlink(missing_ok=True)
conn = db.connect(DBF)
seed.init(conn)
ob = Outbox(conn, channel.Router(dry_run=True))
M = ROOT / "media"
steps = [
    ("2026-11-02T01:00:00", "m2", dict(media={"path": str(next((M / "discharge").glob("d1.*"))), "mime": "image/jpeg"}), "d1 photo from m2 (Mon 06:30 IST)"),
    ("2026-11-02T01:01:00", "m2", dict(text="YES"), "YES from m2"),
    ("2026-11-02T02:40:00", "m2", dict(media={"path": str(next((M / "voice").glob("v01.*"))), "mime": "audio/ogg"}), "v01 voice note from m2 (Mon 08:10 IST)"),
    ("2026-11-04T06:30:00", "m2", dict(media={"path": str(next((M / "organiser").glob("o3.*"))), "mime": "image/jpeg"}), "o3 photo from m2 (Wed 12:00 IST)"),
]
for when, who, kw, label in steps:
    clock.set(utc(when), speed=0)
    res = intake.handle(conn, ob, who, **kw)
    print(f"{label}: route={res['route']} type={res['type']} intent={res['intent']}")
    for m, t in res["replies"]:
        print(f"   -> {m}: {t[:300].replace(chr(10), ' | ')}")

rows = [dict(r) for r in conn.execute("SELECT at,kind,actor,detail,reason FROM audit_log ORDER BY id")]
(ROOT / "outputs" / "replay_audit.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
ev = [dict(r) for r in conn.execute("SELECT slot,due_date,type,actor,reported_by FROM dose_events")]
txt = "\n".join(str(r["detail"]) for r in rows)
checks = {
    "draft created from d1 (4 lines)": any(r["kind"] == "draft_created" and '"lines": 4' in r["detail"] for r in rows),
    "schedule confirmed by m2": any(r["kind"] == "schedule_confirmed" and r["actor"] == "m2" for r in rows),
    "v01 logged as metformin_08:00 confirmed by m2": any(e["slot"] == "metformin_08:00" and e["type"] == "confirmed" and e["actor"] == "m2" for e in ev),
    "organiser: TUE_PM full, no confirmation": "TUE_PM full, no confirmation" in txt,
    "no real sends (only dry-run/sim)": not any(r["kind"] == "outbound" and str(r["detail"]).find("SM") >= 0 for r in rows),
}
print("\nAUDIT LOG (kind | actor | detail):")
for r in rows:
    print(" ", r["at"][11:19], r["kind"], "|", r["actor"], "|", str(r["detail"])[:110].replace("\n", " "))
print()
for k, v in checks.items():
    print("PASS" if v else "FAIL", k)
(ROOT / "outputs" / "replay_result.json").write_text(json.dumps(dict(checks=checks, events=ev), indent=1))
