"""Restore the demo start state: fictional seed, schedule not yet confirmed, clock 07:55 patient-local, every member's choice 'everything'.
Usage: python tools/demo_reset.py   (uses CARECIRCLE_DB or data/carecircle.db; also moves the clock of a running server on port 8000
if ADMIN_TOKEN is set in .env, otherwise start the server with the printed CC_START_TIME).
Prints the board path only, never the token."""
import os, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")
from app import db, demo, record


def main():
    conn = db.connect()
    demo.reset(conn)
    t = demo.start_time(conn)
    moved = False
    tok = os.environ.get("ADMIN_TOKEN")
    if tok:
        import httpx
        try:
            r = httpx.post("http://127.0.0.1:8000/admin/clock", json={"time": record.iso(t), "speed": 1}, headers={"X-Admin-Token": tok}, timeout=5)
            moved = r.status_code == 200
        except Exception:
            pass
    print(f"Demo reset. Clock target 07:55 patient-local = {record.iso(t)}; running server clock moved: {'yes' if moved else 'no (start the server with CC_START_TIME=' + record.iso(t) + ')'}")
    print("Board: /board?token=<BOARD_TOKEN>")


if __name__ == "__main__":
    main()
