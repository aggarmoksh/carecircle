"""Every outbound message goes through here: guard check, 24 h window check, send, audit with a reason. Also relay and queue."""
from . import config, guard, lang, record
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
        if m.get("relay_pref") == "stop":
            audit(self.conn, "send_suppressed", member_id, "member chose STOP", reason)
            return None
        ok, why = guard.check(self.conn, text, sender_text)
        if not ok:
            audit(self.conn, "guard_block", member_id, {"blocked_text": text, "why": why}, reason)
            text = FIXED_BLOCKED
        if not record.window_open(m, now):
            audit(self.conn, "send_skipped", member_id, "24h window closed (template required)", reason)
            return None
        english = text
        text, used = lang.localize(self.conn, text, m)
        res = self.channel.send_text(m, text)
        audit(self.conn, "outbound", member_id, dict({"text": text, "sid_prefix": str(res.get("sid", ""))[:6]}, **({"language": used, "english": english} if used != "en" else {})), reason)
        self.sent.append((member_id, text))
        return text

    def queue(self, member_id, text, reason):
        self.conn.execute("INSERT INTO queue(member_id,text,reason,created_at) VALUES(?,?,?,?)", (member_id, text, reason, clock.iso()))
        self.conn.commit()
        audit(self.conn, "relay_queued", member_id, text, reason)

    def relay(self, text, exclude, reason, kind="relay"):
        """One-line update to the other members, honouring each member's choice (everything | duties | daily | stop).
        kind='alert' (missed dose) reaches everyone except STOP. Real members inside their window and waking hours get it now, otherwise queued;
        a 'daily' member's relays wait for the 8 PM summary."""
        now = clock.now()
        for m in record.members(self.conn):
            if m["id"] in exclude:
                continue
            pref = m.get("relay_pref") or "everything"
            if pref == "stop" or (pref == "duties" and kind == "relay"):
                audit(self.conn, "relay_suppressed", m["id"], text, f"member chose {'STOP' if pref == 'stop' else 'only duties and alerts'}; relay not sent")
                continue
            if pref == "daily" and kind == "relay":
                self.queue(m["id"], text, "digest: " + reason)
                continue
            if m["kind"] == "sim":
                self.send(m["id"], text, reason)
            elif record.window_open(m, now) and record.awake(m, now):
                self.send(m["id"], text, reason)
            else:
                self.queue(m["id"], text, reason + (" (asleep)" if not record.awake(m, now) else " (24h window closed)"))

    def flush_queue(self):
        now = clock.now()
        digests = {}
        for q in self.conn.execute("SELECT * FROM queue WHERE sent_at IS NULL ORDER BY id").fetchall():
            m = record.member(self.conn, q["member_id"])
            if m.get("relay_pref") == "stop":
                continue  # nothing reaches a STOP member; the row stays unsent
            if q["reason"].startswith("digest:"):
                if record.local_time(m, now).hour >= 20 and record.window_open(m, now) and record.awake(m, now):
                    digests.setdefault(m["id"], []).append(q)
                continue
            if record.window_open(m, now) and record.awake(m, now):
                self.send(q["member_id"], q["text"], q["reason"] + " (delivered from queue)")
                self.conn.execute("UPDATE queue SET sent_at=? WHERE id=?", (clock.iso(), q["id"]))
                self.conn.commit()
        for mid, rows in digests.items():
            self.send(mid, "CareCircle daily summary:\n" + "\n".join("- " + r["text"].replace("CareCircle: ", "") for r in rows), "daily summary at 8 PM")
            for r in rows:
                self.conn.execute("UPDATE queue SET sent_at=? WHERE id=?", (clock.iso(), r["id"]))
            self.conn.commit()
