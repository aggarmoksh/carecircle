import json, pathlib, sys
from datetime import datetime, timezone, timedelta
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import db, seed, record
from app.clock import clock
from app.outbox import Outbox
from app.channel import Channel

LABELS = json.loads((ROOT / "labels.json").read_text(encoding="utf-8"))


class FakeChannel(Channel):
    def __init__(self):
        self.log, self.media = [], []

    def send_text(self, member, text, media_url=None):
        self.log.append((member["id"], text))
        if media_url:
            self.media.append((member["id"], media_url))
        return {"sid": "fake:" + member["id"]}


def utc(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def make(now_iso, all_tz=None, window=True):
    """In-memory circle at a fixed clock time. all_tz overrides every member's timezone."""
    conn = db.connect(":memory:")
    seed.init(conn)
    conn.execute("UPDATE members SET relay_pref='everything', language='en'")   # legacy tests assume full relays; the role-based defaults are tested in test_phase4
    conn.commit()
    clock.set(utc(now_iso), speed=0)
    if all_tz:
        conn.execute("UPDATE members SET tz=?", (all_tz,))
    if window:
        for m in record.members(conn):
            if m["kind"] == "real":
                record.touch_inbound(conn, m["id"], clock.now())
    ch = FakeChannel()
    return conn, Outbox(conn, ch), ch


def seed_lines(conn, meds, confirmed_at="2026-11-01T00:00:00Z", by="m2"):
    """meds: [(name, amount, unit, times)] -> confirmed schedule lines."""
    record.add_draft(conn, None, [dict(name=n, dose_amount=a, dose_unit=u, frequency="once_daily", with_food="unspecified", times=t, notes="") for n, a, u, t in meds], confirmed_at)
    record.confirm_drafts(conn, by, confirmed_at)


def seed_d1(conn, confirmed_at="2026-10-30T00:00:00Z"):
    """The d1 schedule from labels.json, confirmed by m2."""
    meds = LABELS["sheets"]["d1"]["meds"]
    record.add_draft(conn, None, meds, confirmed_at)
    record.confirm_drafts(conn, "m2", confirmed_at)


def advance(seconds):
    clock.set(clock.now() + timedelta(seconds=seconds), speed=0)


ROUTER = json.loads((ROOT / "tests" / "router_labels.json").read_text(encoding="utf-8"))


def seed_router(conn, today):
    """Pre-registered seed (tests/router_labels.json): d1 confirmed by m2; rota m2 mornings, m4 evenings; events v01..v05.
    Morning events are today's; the 20:00 events are last night's (the brief's questions treat them as last night)."""
    from datetime import timedelta
    seed_d1(conn)
    for ev in ROUTER["seed"]["events"]:
        d = today if ev["slot"].endswith("08:00") else today - timedelta(days=1)
        typ = {"given": "confirmed", "skipped": "skipped"}[ev["action"]]
        record.add_event(conn, ev["slot"], d, typ, ev["actor"], ev["reported_by"], ev["src"], ev.get("note"), "2026-11-03T05:00:00Z")


def seed_phase2(conn, today):
    """Phase 1 seed plus the pre-registered Phase 2 addition (tests/phase2_labels.json seed_addition): lab reports L1 and L2 loaded from
    tests/lab_labels.json (not from extraction), confirmed by m3."""
    from app import labs
    seed_router(conn, today)
    for key, when in (("L1", "2026-10-30T00:00:00Z"), ("L2", "2026-10-30T00:01:00Z")):
        labs.load_fixture(conn, ROOT / "tests" / "lab_labels.json", key, "m3", when)


PHASE2 = json.loads((ROOT / "tests" / "phase2_labels.json").read_text(encoding="utf-8"))
