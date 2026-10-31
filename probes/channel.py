"""Channel adapter: one interface, three implementations.

send_text(member, text) -> dict(sid, sent_at)   (member is 'm1'..'m5')
Inbound events are produced by the webhook (probes/webhook.py) and appended to outputs/inbound_log.jsonl.
Members: m1 = r1 (real phone, Twilio sandbox); m2..m5 = simulated (outputs/sim_inbox.jsonl).
"""
import os, json, time, threading, pathlib
from datetime import datetime, timezone
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)
SIM_INBOX = OUT / "sim_inbox.jsonl"
OUTBOUND = OUT / "outbound_count.json"
MESSAGE_CAP = 40
_lock = threading.Lock()
LABELS = json.loads((ROOT / "labels.json").read_text(encoding="utf-8"))


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _append(path, obj):
    with _lock, open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj) + "\n")


def outbound_count():
    return json.loads(OUTBOUND.read_text())["n"] if OUTBOUND.exists() else 0


def _bump():
    n = outbound_count()
    if n >= MESSAGE_CAP:
        raise SystemExit(f"outbound message cap {MESSAGE_CAP} reached")
    OUTBOUND.write_text(json.dumps({"n": n + 1}))


class Channel:
    def send_text(self, member: str, text: str) -> dict:
        raise NotImplementedError


class SimChannel(Channel):
    """Simulated members: nothing leaves the machine; every message is appended and marked simulated."""

    def send_text(self, member, text):
        t = now()
        _append(SIM_INBOX, {"t": t, "dir": "to", "member": member, "simulated": True, "text": text})
        return {"sid": f"sim:{member}", "sent_at": t, "simulated": True}

    def sim_reply(self, member, text):
        t = now()
        _append(SIM_INBOX, {"t": t, "dir": "from", "member": member, "simulated": True, "text": text})
        return t


class TwilioSandbox(Channel):
    """Real sends through the Twilio WhatsApp Sandbox. Member -> recipient index comes from labels.json members
    (recipient 'r1'..'r5'); numbers come from WA_RECIPIENTS in order. Counts every outbound message."""
    consecutive_63015 = 0

    def __init__(self):
        from twilio.rest import Client
        self.client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
        self.sender = os.environ["TWILIO_WHATSAPP_FROM"]
        self.numbers = [x.strip() for x in os.environ["WA_RECIPIENTS"].split(",") if x.strip()]
        self.status_cb = os.environ["PUBLIC_BASE_URL"].rstrip("/") + "/twilio/status"

    def send_text(self, member, text):
        from twilio.base.exceptions import TwilioRestException
        ridx = int(LABELS["members"][member]["recipient"][1:]) - 1
        _bump()  # count before sending: stop before exceeding the cap
        t0 = time.time()
        sent_at = now()
        try:
            m = self.client.messages.create(from_=self.sender, to="whatsapp:" + self.numbers[ridx], body=text,
                                            status_callback=self.status_cb)
        except TwilioRestException as e:
            if e.code == 63015:
                TwilioSandbox.consecutive_63015 += 1
                if TwilioSandbox.consecutive_63015 >= 2:
                    raise SystemExit("error 63015 twice: re-send the join phrase from the recipient, then re-run")
            raise
        TwilioSandbox.consecutive_63015 = 0
        return {"sid": m.sid, "sent_at": sent_at, "sent_epoch": t0, "api_seconds": time.time() - t0, "status": m.status,
                "member": member, "recipient": f"r{ridx + 1}"}


class MetaCloud(Channel):
    def send_text(self, member, text):
        # Not implemented: the Meta test number is blocked (error 2655121), see FRICTION_LOG.md.
        raise NotImplementedError("meta_cloud channel is a stub; see FRICTION_LOG.md (error 2655121)")


class Router(Channel):
    """Follows labels.json members: recipient rN -> twilio sandbox, recipient sim -> sim channel."""

    def __init__(self):
        self.real = TwilioSandbox()
        self.sim = SimChannel()

    def send_text(self, member, text):
        real = LABELS["members"][member]["recipient"] != "sim"
        return (self.real if real else self.sim).send_text(member, text)
