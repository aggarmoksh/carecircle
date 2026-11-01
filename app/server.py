"""FastAPI server for the WhatsApp side. Run: .venv/Scripts/python.exe -m uvicorn app.server:app --port 8000
/twilio/inbound  signature-validated; replies 200 with empty TwiML at once, processes afterwards
/twilio/status   delivery status callbacks
/admin/clock     admin-only: set the demo time and speed (header X-Admin-Token == ADMIN_TOKEN); logged in the audit log"""
import os, json, mimetypes, threading, time, pathlib
from datetime import datetime, timezone
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response, BackgroundTasks
from twilio.request_validator import RequestValidator
from . import db, intake, escalation, record, channel, config
from .clock import clock
from .outbox import Outbox

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
app = FastAPI()
EMPTY = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
EXT = {"audio/ogg": ".ogg", "audio/opus": ".opus", "audio/mpeg": ".mp3", "audio/mp4": ".m4a", "audio/amr": ".amr", "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
CH = channel.Router()
INBOUND_DIR = ROOT / "media" / "inbound"
INBOUND_DIR.mkdir(parents=True, exist_ok=True)


def ctx():
    conn = db.connect()
    return conn, Outbox(conn, CH)


def init_if_empty():
    conn = db.connect()
    if not conn.execute("SELECT 1 FROM members LIMIT 1").fetchone():
        from . import seed
        seed.init(conn)


def ticker():
    while True:
        try:
            conn, ob = ctx()
            escalation.tick(conn, ob)
            ob.flush_queue()
            conn.close()
        except SystemExit:
            raise
        except Exception as e:  # keep the scheduler alive; the failure is visible in the audit log
            try:
                db.audit(db.connect(), "ticker_error", None, type(e).__name__, "scheduler exception")
            except Exception:
                pass
        time.sleep(1)


@app.on_event("startup")
def startup():
    init_if_empty()
    if os.environ.get("CC_TICKER", "1") == "1":
        threading.Thread(target=ticker, daemon=True).start()


def member_for(conn, from_):
    nums = [x.strip() for x in os.environ.get("WA_RECIPIENTS", "").split(",") if x.strip()]
    n = from_.replace("whatsapp:", "")
    if n in nums:
        return conn.execute("SELECT id FROM members WHERE recipient_idx=?", (nums.index(n) + 1,)).fetchone()
    return None


async def valid(request: Request, path: str):
    base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    if not base:
        return None
    form = dict((await request.form()).items())
    ok = RequestValidator(os.environ["TWILIO_AUTH_TOKEN"]).validate(base + path, form, request.headers.get("X-Twilio-Signature", ""))
    return form if ok else False


def process(form):
    conn, ob = ctx()
    m = member_for(conn, form.get("From", ""))
    if not m:
        db.audit(conn, "inbound_ignored", None, "sender not in the circle", "unknown sender")
        return
    mid = m["id"]
    n = int(form.get("NumMedia", "0") or 0)
    if n == 0:
        intake.handle(conn, ob, mid, text=form.get("Body", ""))
        return
    for i in range(n):
        mime = form.get(f"MediaContentType{i}", "").split(";")[0].strip().lower()
        r = httpx.get(form[f"MediaUrl{i}"], auth=(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"]), follow_redirects=True, timeout=60)
        r.raise_for_status()
        p = INBOUND_DIR / f"{form.get('MessageSid')}_{i}{EXT.get(mime) or mimetypes.guess_extension(mime) or '.bin'}"
        p.write_bytes(r.content)
        intake.handle(conn, ob, mid, media={"path": str(p), "mime": mime})


@app.post("/twilio/inbound")
async def inbound(request: Request, bg: BackgroundTasks):
    form = await valid(request, "/twilio/inbound")
    if form is None:
        return Response("PUBLIC_BASE_URL not set", status_code=503)
    if form is False:
        return Response("bad signature", status_code=403)
    bg.add_task(process, form)
    return Response(EMPTY, media_type="application/xml")


@app.post("/twilio/status")
async def status(request: Request):
    form = await valid(request, "/twilio/status")
    if form is None:
        return Response("PUBLIC_BASE_URL not set", status_code=503)
    if form is False:
        return Response("bad signature", status_code=403)
    with open(ROOT / "outputs" / "status_log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"t": clock.iso(), "sid": form.get("MessageSid"), "status": form.get("MessageStatus"), "error": form.get("ErrorCode")}) + "\n")
    return Response(EMPTY, media_type="application/xml")


@app.post("/admin/clock")
async def admin_clock(request: Request):
    tok = os.environ.get("ADMIN_TOKEN", "")
    if not tok or request.headers.get("X-Admin-Token", "") != tok:
        return Response("forbidden", status_code=403)
    body = await request.json()
    t = datetime.fromisoformat(body["time"].replace("Z", "+00:00")).astimezone(timezone.utc) if body.get("time") else None
    clock.set(t, body.get("speed"))
    db.audit(db.connect(), "clock_set", "admin", {"time": body.get("time"), "speed": body.get("speed")}, "admin set demo clock")
    return {"now": clock.iso(), "speed": clock.speed}
