"""Restore a demo start state. Sends nothing itself.
Usage: python tools/demo_reset.py [--scene monday|thursday]
  (no scene)  the fictional seed, schedule not yet confirmed, clock 07:55 patient-local
  monday      fresh circle for filming: every member's choice "everything", no schedule yet, clock Monday 07:55, live mode
  thursday    Monday-Wednesday doses confirmed, Wednesday 20:00 missed, lab report L2 confirmed, clock Thursday 07:55, live mode
Uses CARECIRCLE_DB or data/carecircle.db; also moves the clock of a running server on port 8000 if ADMIN_TOKEN is set in .env, otherwise start the server with the
printed CC_START_TIME. For a scene it prints the filming steps (tools/scene_steps.py): which phone does what, and what should arrive where.
Never prints a token, key or phone number."""
import os, pathlib, sys
from datetime import timedelta
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")
from app import config, db, demo, record


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")        # Hindi lines on a Windows console
    argv = sys.argv if argv is None else argv
    conn = db.connect()
    scene = argv[argv.index("--scene") + 1] if "--scene" in argv else None
    if scene == "thursday":
        t = demo.scene_thursday(conn)
    elif scene == "monday":
        t = demo.scene_monday(conn)
    elif scene:
        sys.exit("unknown scene: " + scene + " (monday or thursday)")
    else:
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
    print(f"Demo reset{' (scene ' + scene + ')' if scene else ''}. Clock target 07:55 patient-local = {record.iso(t)}; running server clock moved: {'yes' if moved else 'no (start the server with CC_START_TIME=' + record.iso(t) + ')'}")
    if scene:
        from app import channel
        used, cap = channel.outbound_count(), config.PHASE1_MESSAGE_CAP
        print(f"Outbound WhatsApp messages used so far: {used} of {cap}" + ("  (a full run of this scene sends about 15-20 messages, spaced 3 seconds apart)" if cap - used < 20 else ""))
        print("Server: LIVE mode (CARECIRCLE_DRY_RUN must not be set).")
        if os.environ.get("CARECIRCLE_DRY_RUN") == "1":
            print("WARNING: CARECIRCLE_DRY_RUN=1 is set in this shell; unset it before you start the server, or nothing will reach the phones.")
        from scene_steps import steps
        print()
        film = record.iso(t + timedelta(minutes=33, seconds=30)) if scene == "thursday" else None      # 08:28:30 patient-local: the ladder then reaches Kabir at 03:01 London
        print(steps(scene, film))
    print("Board: /board?token=<BOARD_TOKEN>")


if __name__ == "__main__":
    main()
