"""Every outbound message goes through here: guard check, 24 h window check, send, audit with a reason. Also relay and queue."""
from . import config, guard, record
from .clock import clock
from .db import audit

FIXED_BLOCKED = "I can't help with that here. I can add it as a question for the doctor visit."
FIXED_MEDICAL = "I can't give medical advice. I've noted this as a question for the doctor visit. Who will ask the doctor? Reply 'I will' to take it."
FIXED_URGENT = "This sounds urgent. Please call your local emergency services or the doctor right now. I can't assess symptoms."
FIXED_LAB = "Saved for the circle. I can't interpret results. Who will discuss this with the doctor?"


class Outbox:
    def __init__(self, conn, channel):
        self.conn, self.channel = conn, channel
        self.sent = []  # (member_id, text) for tests and reporting

    def send(self, member_id, text, reason, sender_text=""):
        m = record.member(self.conn, member_id)
        now = clock.now()
        ok, why = guard.check(self.conn, text, sender_text)
        if not ok:
            audit(self.conn, "guard_block", member_id, {"blocked_text": text, "why": why}, reason)
            text = FIXED_BLOCKED
        if not record.window_open(m, now):
            audit(self.conn, "send_skipped", member_id, "24h window closed (template required)", reason)
            return None
        res = self.channel.send_text(m, text)
        audit(self.conn, "outbound", member_id, {"text": text, "sid_prefix": str(res.get("sid", ""))[:6]}, reason)
        self.sent.append((member_id, text))
        return text

    def queue(self, member_id, text, reason):
        self.conn.execute("INSERT INTO queue(member_id,text,reason,created_at) VALUES(?,?,?,?)", (member_id, text, reason, clock.iso()))
        self.conn.commit()
        audit(self.conn, "relay_queued", member_id, text, reason)

    def relay(self, text, exclude, reason):
        """One-line update to the other members: real members inside their window and local waking hours, otherwise queued;
        simulated members are logged to sim_inbox."""
        now = clock.now()
        for m in record.members(self.conn):
            if m["id"] in exclude:
                continue
            if m["kind"] == "sim":
                self.send(m["id"], text, reason)
            elif record.window_open(m, now) and record.awake(m, now):
                self.send(m["id"], text, reason)
            else:
                self.queue(m["id"], text, reason + (" (asleep)" if not record.awake(m, now) else " (24h window closed)"))

    def flush_queue(self):
        now = clock.now()
        for q in self.conn.execute("SELECT * FROM queue WHERE sent_at IS NULL ORDER BY id").fetchall():
            m = record.member(self.conn, q["member_id"])
            if record.window_open(m, now) and record.awake(m, now):
                self.send(q["member_id"], q["text"], q["reason"] + " (delivered from queue)")
                self.conn.execute("UPDATE queue SET sent_at=? WHERE id=?", (clock.iso(), q["id"]))
                self.conn.commit()
