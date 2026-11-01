"""Lab reports. The model only copies what is printed (value, unit, printed range text, printed flag).
Code parses the printed range and computes the status; the model never supplies a range or a judgement.
Wording is always 'within / above / below the lab's printed range' or 'no range printed'. No explanation of what a value means."""
import json, re
from . import llm, record
from .vision import _msg

from .prompts import LAB_SCHEMA, LAB_PROMPT
from .labcore import NUM, _n, parse_range, status, norm_unit, finish

def extract(path, item):
    r, dt, usd = llm.spark_json("phase2", f"lab-{item}", _msg(LAB_PROMPT, path), LAB_SCHEMA)
    return finish(r)


# ---------- wording (code templates; no explanation of what a value means) ----------
def fmt_num(x):
    return f"{x:g}"


def range_phrase(t):
    """Wording for a value against the lab's printed range; the range numbers are copied as printed (4.0, not 4)."""
    low, high = t.get("parsed_low"), t.get("parsed_high")
    if low is None and high is None:
        return "no range printed"
    nums = re.findall(NUM, t.get("range_text") or "")
    if low is not None and high is not None and len(nums) >= 2:
        rng = f"{nums[0]} to {nums[1]}"
    elif low is not None and high is not None:
        rng = f"{fmt_num(low)} to {fmt_num(high)}"
    elif high is not None:
        return f"{t['status']} the lab's printed range (less than {nums[0] if nums else fmt_num(high)})"
    else:
        return f"{t['status']} the lab's printed range (more than {nums[0] if nums else fmt_num(low)})"
    return f"{t['status']} the lab's printed range {rng}"


def value_line(t):
    return f"{t['test']}: {fmt_num(t['value'])} {t['unit']}, {range_phrase(t)}"


def out_of_range(tests):
    return [t for t in tests if t["status"] in ("above", "below")]


def pretty_date(iso_date):
    from datetime import date
    d = date.fromisoformat(iso_date)
    return f"{d.day} {d.strftime('%b')}"


# ---------- storage ----------
def save_draft(conn, doc_id, rep, now_iso):
    for old in conn.execute("SELECT id FROM lab_reports WHERE status='draft'").fetchall():
        conn.execute("DELETE FROM lab_values WHERE report_id=?", (old["id"],))
        conn.execute("DELETE FROM lab_reports WHERE id=?", (old["id"],))
    cur = conn.execute("INSERT INTO lab_reports(doc_id,lab,report_date,status,created_at) VALUES(?,?,?,?,?)", (doc_id, rep["lab"], rep["report_date"], "draft", now_iso))
    rid = cur.lastrowid
    insert_values(conn, rid, rep["tests"])
    conn.commit()
    return rid


def insert_values(conn, rid, tests):
    for t in tests:
        conn.execute("INSERT INTO lab_values(report_id,test,value,unit,range_text,range_low,range_high,printed_flag,status) VALUES(?,?,?,?,?,?,?,?,?)",
                     (rid, t["test"], t["value"], t["unit"], t["range_text"], t.get("parsed_low"), t.get("parsed_high"), t["printed_flag"], t["status"]))


def confirm_draft(conn, by, now_iso):
    r = conn.execute("SELECT id FROM lab_reports WHERE status='draft' ORDER BY id DESC LIMIT 1").fetchone()
    if not r:
        return None
    conn.execute("UPDATE lab_reports SET status='live', confirmed_by=?, confirmed_at=? WHERE id=?", (by, now_iso, r["id"]))
    conn.commit()
    return report(conn, r["id"])


def draft(conn):
    r = conn.execute("SELECT id FROM lab_reports WHERE status='draft' ORDER BY id DESC LIMIT 1").fetchone()
    return report(conn, r["id"]) if r else None


def report(conn, rid):
    r = conn.execute("SELECT * FROM lab_reports WHERE id=?", (rid,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["tests"] = [dict(x, parsed_low=x["range_low"], parsed_high=x["range_high"]) for x in conn.execute("SELECT * FROM lab_values WHERE report_id=? ORDER BY id", (rid,))]
    return d


def live_reports(conn):
    return [report(conn, r["id"]) for r in conn.execute("SELECT id FROM lab_reports WHERE status='live' ORDER BY report_date, id")]


def load_fixture(conn, labels_path, key, by, now_iso):
    """Seed a live report from tests/lab_labels.json (not from extraction). Status is computed by code from the printed range text."""
    d = json.loads(open(labels_path, encoding="utf-8").read())["reports"][key]
    tests = [dict(t, parsed_low=t["range_low"], parsed_high=t["range_high"], status=status(t["value"], t["range_text"])) for t in d["tests"]]
    cur = conn.execute("INSERT INTO lab_reports(doc_id,lab,report_date,status,confirmed_by,confirmed_at,created_at) VALUES(NULL,?,?,?,?,?,?)",
                       (d["lab"], d["report_date"], "live", by, now_iso, now_iso))
    insert_values(conn, cur.lastrowid, tests)
    conn.commit()
    return cur.lastrowid
