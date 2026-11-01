"""Channel adapter: one interface (send_text to a member), several implementations.
  twilio_sandbox : real WhatsApp via the Twilio Sandbox (members with kind 'real', recipient index into WA_RECIPIENTS)
  dry_run        : captures what would be sent to outputs/dryrun_outbox.jsonl (offline replay, no real sends)
  sim            : simulated members; every message is appended to outputs/sim_inbox.jsonl, marked simulated
  meta_cloud     : stub (the Meta test number is blocked, see FRICTION_LOG.md)
Inbound events come from the webhook (app/server.py)."""
import os, json, time, threading, pathlib
from dotenv import load_dotenv
from . import config
from .clock import clock

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)
SIM_INBOX = OUT / "sim_inbox.jsonl"
DRYRUN_OUTBOX = OUT / "dryrun_outbox.jsonl"
COUNTER = ROOT / "data" / os.environ.get("CC_COUNTER_FILE", "outbound_phase2.json")
_lock = threading.Lock()


def _append(path, obj):
    with _lock, open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj) + "\n")


def outbound_count():
    return json.loads(COUNTER.read_text())["n"] if COUNTER.exists() else 0


def _bump():
    COUNTER.parent.mkdir(exist_ok=True)
    n = outbound_count()
    if n >= config.PHASE1_MESSAGE_CAP:
        raise SystemExit(f"outbound message cap {config.PHASE1_MESSAGE_CAP} reached")
    COUNTER.write_text(json.dumps({"n": n + 1}))


class Channel:
    def send_text(self, member: dict, text: str) -> dict:
        raise NotImplementedError


class SimChannel(Channel):
    def send_text(self, member, text):
        _append(SIM_INBOX, {"t": clock.iso(), "dir": "to", "member": member["id"], "simulated": True, "text": text})
        return {"sid": f"sim:{member['id']}", "simulated": True}

    def sim_reply(self, member_id, text):
        _append(SIM_INBOX, {"t": clock.iso(), "dir": "from", "member": member_id, "simulated": True, "text": text})


class DryRun(Channel):
    def send_text(self, member, text):
        _append(DRYRUN_OUTBOX, {"t": clock.iso(), "member": member["id"], "text": text})
        return {"sid": f"dry:{member['id']}"}


class TwilioSandbox(Channel):
    consecutive_63015 = 0

    def __init__(self):
        from twilio.rest import Client
        self.client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
        self.sender = os.environ["TWILIO_WHATSAPP_FROM"]
        self.numbers = [x.strip() for x in os.environ["WA_RECIPIENTS"].split(",") if x.strip()]
        self.status_cb = os.environ["PUBLIC_BASE_URL"].rstrip("/") + "/twilio/status"

    def send_text(self, member, text):
        from twilio.base.exceptions import TwilioRestException
        _bump()  # count before sending: stop before exceeding the cap
        t0 = time.time()
        try:
            m = self.client.messages.create(from_=self.sender, to="whatsapp:" + self.numbers[member["recipient_idx"] - 1],
                                            body=text, status_callback=self.status_cb)
        except TwilioRestException as e:
            if e.code == 63015:
                TwilioSandbox.consecutive_63015 += 1
                if TwilioSandbox.consecutive_63015 >= 2:
                    raise SystemExit("error 63015 twice: re-send the join phrase from the recipient, then re-run")
            raise
        TwilioSandbox.consecutive_63015 = 0
        return {"sid": m.sid, "sent_epoch": t0, "status": m.status}


class MetaCloud(Channel):
    def send_text(self, member, text):
        # Not implemented: the Meta test number is blocked (error 2655121), see FRICTION_LOG.md.
        raise NotImplementedError("meta_cloud channel is a stub; see FRICTION_LOG.md (error 2655121)")


class Router(Channel):
    """Real members -> twilio sandbox (or dry run), simulated members -> sim channel."""

    def __init__(self, dry_run=None):
        self.dry = config.DRY_RUN if dry_run is None else dry_run
        self.real = DryRun() if self.dry else None
        self.sim = SimChannel()

    def send_text(self, member, text):
        if member["kind"] == "sim":
            return self.sim.send_text(member, text)
        if self.real is None:
            self.real = TwilioSandbox()
        return self.real.send_text(member, text)
