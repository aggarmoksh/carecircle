"""Synthetic circle used by the demo and the tests (same fictional people as labels.json; no real data)."""
from . import config

MEMBERS = [
    # id, name, relationship, tz, role, kind, recipient index (1-based into WA_RECIPIENTS, None for simulated)
    ("m1", "Arjun", "grandson", "America/Los_Angeles", "remote", "real", 1),
    ("m2", "Meena", "aunt", "Asia/Kolkata", "hands_on", "real", 2),
    ("m3", "Kabir", "cousin", "Europe/London", "remote", "real", 3),
    ("m4", "Sunita", "neighbour (simulated)", "Asia/Kolkata", "hands_on", "sim", None),
    ("m5", "Ravi", "uncle (simulated)", "Asia/Dubai", "remote", "sim", None),
]


def init(conn):
    conn.execute("INSERT INTO circle(name,patient_name,patient_tz) VALUES(?,?,?)", ("Nanaji's circle", config.PATIENT_NAME, config.PATIENT_TZ))
    for mid, name, rel, tz, role, kind, ridx in MEMBERS:
        conn.execute("INSERT INTO members(id,name,relationship,tz,role,kind,recipient_idx) VALUES(?,?,?,?,?,?,?)", (mid, name, rel, tz, role, kind, ridx))
    conn.execute("INSERT INTO rota(period,member_id) VALUES('morning','m2')")
    conn.execute("INSERT INTO rota(period,member_id) VALUES('evening','m4')")
    conn.commit()
