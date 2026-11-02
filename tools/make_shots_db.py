"""Build data/shots.db: a synthetic circle for the Phase 3 screenshots (labs with a trend, relay choices, missed doses after a scheduler run).
Usage: python tools/make_shots_db.py   (fictional data only)"""
import pathlib, sys
from datetime import date
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests"))
import os
os.environ["CARECIRCLE_DB"] = str(ROOT / "data" / "shots.db")
(ROOT / "data" / "shots.db").unlink(missing_ok=True)
from helpers import seed_d1, utc
from app import db, seed, labs, record, escalation
from app.clock import clock

conn = db.connect()
seed.init(conn)
clock.set(utc("2026-11-03T09:00:00"), speed=0)
seed_d1(conn)
# an earlier report for the trend: the same L2 tests with earlier (fictional) values
a = labs.load_fixture(conn, ROOT / "tests" / "lab_labels.json", "L2", "m3", "2026-09-30T00:00:00Z")
conn.execute("UPDATE lab_reports SET report_date='2026-09-29' WHERE id=?", (a,))
for test, v in (("serum creatinine", 1.2), ("tsh", 5.1), ("egfr", 55.0), ("sodium", 137.0), ("potassium", 4.6), ("blood urea", 35.0)):
    conn.execute("UPDATE lab_values SET value=? WHERE report_id=? AND test=?", (v, a, test))
labs.load_fixture(conn, ROOT / "tests" / "lab_labels.json", "L2", "m3", "2026-10-30T00:00:00Z")
conn.commit()
# a few confirmed doses, then the scheduler runs after days of silence: the rest become missed
for s, d, who in (("metformin_08:00", date(2026, 11, 1), "m2"), ("aspirin_08:00", date(2026, 11, 1), "m2"), ("metformin_08:00", date(2026, 11, 2), "m2")):
    record.add_event(conn, s, d, "confirmed", who, who, "seed", None, "2026-11-02T03:00:00Z")
record.set_relay_pref(conn, "m1", "duties")
record.set_relay_pref(conn, "m3", "daily")
record.add_task(conn, "Discuss the lab report from 29 Oct with the doctor", "m3", "lab report", "2026-10-30T00:00:00Z")
escalation.settle_missed(conn, clock.now())
print("shots.db ready")
