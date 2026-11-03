"""SQLite care record. Tables: circle, members, medications, schedule_lines, dose_events, documents, rota, tasks, lab_reports, lab_values, audit_log, queue."""
import json, os, pathlib, sqlite3
from .clock import clock

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB_PATH = pathlib.Path(os.environ.get("CARECIRCLE_DB") or ROOT / "data" / "carecircle.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS circle(id INTEGER PRIMARY KEY, name TEXT, patient_name TEXT, patient_tz TEXT);
CREATE TABLE IF NOT EXISTS members(id TEXT PRIMARY KEY, name TEXT, relationship TEXT, tz TEXT,
  role TEXT CHECK(role IN('hands_on','remote')), kind TEXT CHECK(kind IN('real','sim')), recipient_idx INTEGER, last_inbound_at TEXT);
CREATE TABLE IF NOT EXISTS medications(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, dose_amount REAL, dose_unit TEXT,
  frequency TEXT, with_food TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS schedule_lines(id INTEGER PRIMARY KEY AUTOINCREMENT, med_id INTEGER, times_json TEXT,
  status TEXT CHECK(status IN('draft','confirmed','stopped')), source_doc_id INTEGER, created_at TEXT, confirmed_by TEXT, confirmed_at TEXT);
CREATE TABLE IF NOT EXISTS dose_events(id INTEGER PRIMARY KEY AUTOINCREMENT, slot TEXT, due_date TEXT,
  type TEXT CHECK(type IN('due','confirmed','skipped','unsure','missed','nudged','escalated','late_confirmed')),
  actor TEXT, reported_by TEXT, source_message TEXT, note TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT, type TEXT, confidence REAL,
  extraction_json TEXT, sender TEXT, status TEXT, overlay_path TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS rota(period TEXT PRIMARY KEY CHECK(period IN('morning','evening')), member_id TEXT);
CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT, owner TEXT, status TEXT DEFAULT 'open', source TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, kind TEXT, actor TEXT, detail TEXT, reason TEXT);
CREATE TABLE IF NOT EXISTS lab_reports(id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id INTEGER, lab TEXT, report_date TEXT,
  status TEXT CHECK(status IN('draft','live')), confirmed_by TEXT, confirmed_at TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS lab_values(id INTEGER PRIMARY KEY AUTOINCREMENT, report_id INTEGER, test TEXT, value REAL, unit TEXT,
  range_text TEXT, range_low REAL, range_high REAL, printed_flag TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS board_tokens(token_hash TEXT PRIMARY KEY, member_id TEXT, gen INTEGER, created_at TEXT, revoked_at TEXT);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS cards(id TEXT PRIMARY KEY, state_hash TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS queue(id INTEGER PRIMARY KEY AUTOINCREMENT, member_id TEXT, text TEXT, reason TEXT, created_at TEXT, sent_at TEXT);
"""


def connect(path=None):
    p = ":memory:" if path == ":memory:" else str(path or DB_PATH)
    if p != ":memory:":
        pathlib.Path(p).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    if p != ":memory:":
        conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    _add_columns(conn)
    return conn


MIGRATIONS = [("members", "relay_pref", "TEXT DEFAULT 'everything'"), ("medications", "name_as_printed", "TEXT DEFAULT ''"),
              ("medications", "generic_if_printed", "TEXT DEFAULT ''"), ("medications", "legibility", "TEXT DEFAULT 'clear'"), ("documents", "has_handwriting", "INTEGER DEFAULT 0"), ("lab_reports", "origin", "TEXT DEFAULT ''"), ("members", "language", "TEXT DEFAULT 'en'")]


def _add_columns(conn):
    for table, col, decl in MIGRATIONS:
        if col not in [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
            except Exception:  # another connection added it first
                pass
    conn.commit()


def audit(conn, kind, actor=None, detail=None, reason=None, at=None):
    conn.execute("INSERT INTO audit_log(at,kind,actor,detail,reason) VALUES(?,?,?,?,?)",
                 (at or clock.iso(), kind, actor, detail if isinstance(detail, str) or detail is None else json.dumps(detail), reason))
    conn.commit()
