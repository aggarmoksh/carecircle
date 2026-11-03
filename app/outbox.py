"""Every outbound message goes through here: guard check, 24 h window check, send, audit with a reason. Also relay and queue."""
from . import config, guard, lang, record, tmpl
from .clock import clock
from .db import audit

FIXED_BLOCKED = "I can't help with that here. I can add it as a question for the doctor visit."
FIXED_MEDICAL = tmpl.FIXED["medical"]["en"]
FIXED_URGENT = tmpl.FIXED["urgent"]["en"]
FIXED_LAB = "Saved for the circle. I can't interpret results. Who will discuss this with the doctor?"


class Outbox:
    def __init__(self, conn, channel):
        self.conn, self.channel = conn, channel
        self.sent = []  # (member_id, text) for tests and reporting

    def send_t(self, member_id, kind, reason, sender_text="", **slots):
        """Send a fixed template in the member's language (code fills the slots; nothing is rephrased by the model)."""
        m = record.member(self.conn, member_id)
        code = m.get("language") or "en"
        return self.send(member_id, tmpl.render(kind, code, **slots), reason, sender_text, lang_used=code, english=tmpl.render(kind, "en", **slots))

    def send(self, member_id, text, reason, sender_text="", free=False, lang_used="en", english=None):
        """free=True: a free-text answer to a record question, which Spark may phrase in the member's language (checked by code). Everything else is sent as given."""
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
        english = text if english is None else english
        text, used = lang.localize(self.conn, text, m) if free else (text, lang_used)
        res = self.channel.send_text(m, text)
        audit(self.conn, "outbound", member_id, dict({"text": text, "sid_prefix": str(res.get("sid", ""))[:6]}, **({"language": used, "english": english} if used != "en" else {})), reason)
        self.sent.append((member_id, text))
        return text

    def queue(self, member_id, text, reason):
        self.conn.execute("INSERT INTO queue(member_id,text,reason,created_at) VALUES(?,?,?,?)", (member_id, text, reason, clock.iso()))
        self.conn.commit()
        audit(self.conn, "relay_queued", member_id, text, reason)

    def link_for(self, m):
        """The board link for this member (a personal read-only link), or '' when none is set up."""
        return ""

    def relay_t(self, tkind, slots, exclude, reason, kind="relay"):
        """relay() with a fixed template rendered in each recipient's language."""
        self.relay(lambda m: tmpl.render(tkind, m.get("language") or "en", **dict(slots, **({"link": self.link_for(m)} if slots.get("link") is True else {}))), exclude, reason, kind, templated=True, english=tmpl.render(tkind, "en", **slots))

    def relay(self, make, exclude, reason, kind="relay", templated=False, english=None):
        """One-line update to the other members, honouring each member's choice (everything | duties | daily | stop).
        kind='alert' (missed dose) reaches everyone except STOP. Real members inside their window and waking hours get it now, otherwise queued;
        a 'daily' member's relays wait for the 8 PM summary."""
        now = clock.now()
        for m in record.members(self.conn):
            if m["id"] in exclude:
                continue
            text = make(m) if callable(make) else make
            pref = m.get("relay_pref") or "everything"
            if pref == "stop" or (pref == "duties" and kind == "relay"):
                audit(self.conn, "relay_suppressed", m["id"], text, f"member chose {'STOP' if pref == 'stop' else 'only duties and alerts'}; relay not sent")
                continue
            if pref == "daily" and kind == "relay":
                self.queue(m["id"], text, "digest: " + reason)
                continue
            lu = (m.get("language") or "en") if templated else "en"
            if m["kind"] == "sim":
                self.send(m["id"], text, reason, lang_used=lu, english=english)
            elif record.window_open(m, now) and record.awake(m, now):
                self.send(m["id"], text, reason, lang_used=lu, english=english)
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
                self.send(q["member_id"], q["text"], q["reason"] + " (delivered from queue)", lang_used=(m.get("language") or "en") if any(ord(c) > 127 for c in q["text"]) else "en", english="")
                self.conn.execute("UPDATE queue SET sent_at=? WHERE id=?", (clock.iso(), q["id"]))
                self.conn.commit()
        for mid, rows in digests.items():
            code = record.member(self.conn, mid).get("language") or "en"
            body = chr(10).join("- " + r["text"].replace("CareCircle: ", "") for r in rows)
            self.send(mid, tmpl.render("daily_header", code) + chr(10) + body, "daily summary at 8 PM", lang_used=code, english="")
            for r in rows:
                self.conn.execute("UPDATE queue SET sent_at=? WHERE id=?", (clock.iso(), r["id"]))
            self.conn.commit()
