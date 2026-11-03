"""Build data/shots.db: a synthetic (fictional) circle for the board and summary screenshots.
Thursday scene, plus an earlier lab report for the trend, relay choices, a stopped member, the organiser photo, and 08:00 doses left unconfirmed so the
scheduler runs a short ladder (a FakeChannel, nothing is sent). Usage: python tools/make_shots_db.py"""
import json, pathlib, sys
from datetime import datetime, timezone, timedelta
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests"))
import os
os.environ["CARECIRCLE_DB"] = str(ROOT / "data" / "shots.db")
for suffix in ("", "-wal", "-shm"):
    pathlib.Path(str(ROOT / "data" / "shots.db") + suffix).unlink(missing_ok=True)
from helpers import FakeChannel, utc
from app import db, seed, labs, record, escalation, demo, outbox
from app.clock import clock

conn = db.connect()
seed.init(conn)
target = demo.scene_thursday(conn)
a = labs.load_fixture(conn, ROOT / "tests" / "lab_labels.json", "L2", "m3", "2026-09-30T00:00:00Z")      # an earlier report for the trend
conn.execute("UPDATE lab_reports SET report_date='2026-09-29' WHERE id=?", (a,))
for test, v in (("serum creatinine", 1.2), ("tsh", 5.1), ("egfr", 55.0), ("sodium", 137.0), ("potassium", 4.6), ("blood urea", 35.0)):
    conn.execute("UPDATE lab_values SET value=? WHERE report_id=? AND test=?", (v, a, test))
tz = record.patient_tz(conn)
thu = target.astimezone(tz).date()
states = {k: v for k, v in json.loads((ROOT / "tests" / "organiser_real_labels_v2.json").read_text(encoding="utf-8"))["photos"]["or1"].items() if not k.startswith("_")}
conn.execute("INSERT INTO documents(path,sender,status,type,confidence,extraction_json,created_at) VALUES(?,?,?,?,?,?,?)",
             (str(ROOT / "media" / "organiser_real" / "or1.jpeg"), "m2", "audited", "pill_organiser", 0.97, json.dumps(states), record.iso(target.replace(minute=58) - timedelta(hours=1, minutes=-3))))
record.set_relay_pref(conn, "m4", "stop")
conn.execute("UPDATE members SET last_inbound_at=? WHERE kind='real'", (record.iso(target),))
conn.commit()
# translations are canned here (no model calls for the screenshots); they are the kind of text the real run produced (outputs/p4b_*.json)
CANNED = {"Hi Meena, has Nanaji had his 8 AM medicines: amlodipine, aspirin, metformin? Reply done, or tell me which ones.":
          "नमस्ते Meena, क्या Nanaji ने सुबह 8 बजे वाली amlodipine, aspirin, metformin दवा ली? हो गया लिखो, या बताओ कौन सी नहीं।",
          "CareCircle: metformin, atorvastatin 20:00 for Nanaji is recorded as missed.":
          "CareCircle: metformin, atorvastatin 20:00 para Nanaji está registrado como omitido."}
from app import llm
llm.spark_json = lambda ph, lb, m, sc: ({"text": CANNED.get(m[0]["content"].split('Message: "', 1)[1].rsplit('"', 1)[0], "")}, 0, 0)
clock.set(target, speed=0)                                                 # 07:55 patient-local
ob = outbox.Outbox(conn, FakeChannel())
ob.relay("CareCircle: metformin, atorvastatin 20:00 for Nanaji is recorded as missed.", [], "state change: dose missed", kind="alert")
clock.set(target + timedelta(minutes=30), speed=0)                         # 08:25 patient-local: the 08:00 doses are past due + grace
for _ in range(6):
    escalation.tick(conn, ob)
    clock.set(clock.now() + timedelta(seconds=61), speed=0)
print("shots.db ready at", clock.now().astimezone(tz).strftime("%a %H:%M"))
