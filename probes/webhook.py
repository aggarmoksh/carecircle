"""FastAPI webhook for the Twilio WhatsApp Sandbox. Run: .venv/Scripts/python.exe -m uvicorn webhook:app --app-dir probes --port 8000"""
import os, json, mimetypes, threading, pathlib
from datetime import datetime, timezone
import httpx
from fastapi import FastAPI, Request, Response, BackgroundTasks
from twilio.request_validator import RequestValidator
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
OUT = ROOT / "outputs"
INBOUND_DIR = ROOT / "media" / "inbound"
VOICE_DIR = ROOT / "media" / "voice"
for d in (OUT, INBOUND_DIR, VOICE_DIR):
    d.mkdir(parents=True, exist_ok=True)
app = FastAPI()
lock = threading.Lock()
EMPTY = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
EXT = {"audio/ogg": ".ogg", "audio/opus": ".opus", "audio/mpeg": ".mp3", "audio/mp4": ".m4a", "audio/amr": ".amr",
       "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def ts():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def log(name, obj):
    with lock, open(OUT / name, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj) + "\n")


def sender_label(frm):
    nums = [x.strip() for x in os.environ.get("WA_RECIPIENTS", "").split(",") if x.strip()]
    num = frm.replace("whatsapp:", "")
    return f"r{nums.index(num) + 1}" if num in nums else "r?"  # never log the number itself


async def valid(request: Request, path: str):
    base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    if not base:
        return None
    form = dict((await request.form()).items())
    sig = request.headers.get("X-Twilio-Signature", "")
    ok = RequestValidator(os.environ["TWILIO_AUTH_TOKEN"]).validate(base + path, form, sig)
    return form if ok else False


def process_inbound(form: dict, received: str):
    sid, sender = form.get("MessageSid"), sender_label(form.get("From", ""))
    n = int(form.get("NumMedia", "0") or 0)
    if n == 0:
        log("inbound_log.jsonl", {"t": received, "sid": sid, "sender": sender, "type": "text", "text": form.get("Body", "")})
        return
    auth = (os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
    for i in range(n):
        url, mime = form.get(f"MediaUrl{i}"), form.get(f"MediaContentType{i}", "")
        base_mime = mime.split(";")[0].strip().lower()
        ext = EXT.get(base_mime) or mimetypes.guess_extension(base_mime) or ".bin"
        try:
            r = httpx.get(url, auth=auth, follow_redirects=True, timeout=60)
            r.raise_for_status()
        except Exception as e:
            log("inbound_log.jsonl", {"t": received, "sid": sid, "sender": sender, "type": "media_error", "mime": mime, "error": type(e).__name__})
            continue
        with lock:
            if base_mime.startswith("audio/"):
                k = len(list(VOICE_DIR.glob("v??.*"))) + 1
                path = VOICE_DIR / f"v{k:02d}{ext}"
                kind = "voice"
            else:
                path = INBOUND_DIR / f"{sid}_{i}{ext}"
                kind = "image" if base_mime.startswith("image/") else "media"
            path.write_bytes(r.content)
        log("inbound_log.jsonl", {"t": received, "sid": sid, "sender": sender, "type": kind, "mime": mime,
                                  "file": str(path.relative_to(ROOT)), "bytes": len(r.content)})


@app.post("/twilio/inbound")
async def inbound(request: Request, bg: BackgroundTasks):
    form = await valid(request, "/twilio/inbound")
    if form is None:
        return Response("PUBLIC_BASE_URL not set", status_code=503)
    if form is False:
        return Response("bad signature", status_code=403)
    bg.add_task(process_inbound, form, ts())
    return Response(EMPTY, media_type="application/xml")


@app.post("/twilio/status")
async def status(request: Request):
    received = ts()
    form = await valid(request, "/twilio/status")
    if form is None:
        return Response("PUBLIC_BASE_URL not set", status_code=503)
    if form is False:
        return Response("bad signature", status_code=403)
    log("status_log.jsonl", {"t": received, "sid": form.get("MessageSid"), "status": form.get("MessageStatus"),
                             "error": form.get("ErrorCode")})
    return Response(EMPTY, media_type="application/xml")
