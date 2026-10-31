"""P5 escalation trial. usage: p5.py i|ii|iii|iv
Nudge m2 (r2, on duty) at t0. Ladder: i/ii/iii -> m1 (r1) at t0+60; iv -> sim m4 at t0+60, then m1 (r1) at t0+120.
A reply from r2 in the inbound log stops escalation (checked right up to each deadline); later replies are logged against the dose."""
import sys, json, time
from datetime import datetime
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
import channel as ch
import p4

trial = sys.argv[1]
router = ch.Router()
DOSE = "metformin_08:00"
ISO = lambda s: datetime.fromisoformat(s).timestamp()
inbound = ch.OUT / "inbound_log.jsonl"


def replies_from(sender, since):
    if not inbound.exists():
        return []
    out = []
    for l in inbound.read_text().splitlines():
        e = json.loads(l)
        if e["sender"] == sender and ISO(e["t"]) > since and e["type"] == "text":
            out.append(e)
    return out


nudge = router.send_text("m2", f"CareCircle: you are on duty for {DOSE} (synthetic test). Reply 'done' once it is given.")
t0 = nudge["sent_epoch"]
ev = {"trial": trial, "dose": DOSE, "t0": nudge["sent_at"], "sends": [dict(step="nudge", to="r2", **{k: nudge[k] for k in ("sid", "sent_epoch")}, offset_s=0.0)], "replies": [], "escalations": []}
print(f"trial {trial}: nudge sent to r2; watch the clock from now", flush=True)
steps = [(60, "m1")] if trial != "iv" else [(60, "m4"), (120, "m1")]
end = t0 + steps[-1][0] + 25
seen = set()
done_at = None
for dl, member in steps:
    target = t0 + dl
    while time.time() < target:
        for r in replies_from("r2", t0):
            if r["t"] not in seen:
                seen.add(r["t"]); ev["replies"].append(dict(offset_s=round(ISO(r["t"]) - t0, 2), text=r["text"]))
        time.sleep(0.05)
    acked = [r for r in replies_from("r2", t0) if ISO(r["t"]) <= time.time()]
    if acked:
        print(f"reply before t0+{dl}: no escalation to {member}", flush=True)
        done_at = dl
        break
    es = router.send_text(member, f"CareCircle: {DOSE} not confirmed by the on-duty member yet (synthetic test). Can you check?")
    ev["escalations"].append(dict(to=member, target_s=dl, actual_offset_s=round(es.get("sent_epoch", time.time()) - t0, 2), sid=es["sid"]))
    if es["sid"].startswith("SM"):
        ev["sends"].append(dict(step=f"escalate_{member}", to=es["recipient"], sid=es["sid"], sent_epoch=es["sent_epoch"], offset_s=round(es["sent_epoch"] - t0, 2)))
    print(f"escalated to {member} at +{ev['escalations'][-1]['actual_offset_s']} s", flush=True)
while time.time() < end:  # keep listening for late replies
    for r in replies_from("r2", t0):
        if r["t"] not in seen:
            seen.add(r["t"]); ev["replies"].append(dict(offset_s=round(ISO(r["t"]) - t0, 2), text=r["text"]))
    time.sleep(0.2)
for r in ev["replies"]:
    r["logged_against_dose"] = DOSE
    r["late"] = bool(ev["escalations"]) and r["offset_s"] > ev["escalations"][0]["target_s"]
for s in ev["sends"]:
    lat, events = p4.latency(s["sent_epoch"], s["sid"], wait=10)
    s["callbacks_s_after_send"] = lat
    s["delivered_within_5s"] = lat.get("delivered", 99) <= 5
    s["sent_epoch"] = round(s["sent_epoch"], 3)
ev["outbound_count"] = ch.outbound_count()
(ch.OUT / f"p5_{trial}.json").write_text(json.dumps(ev, indent=1))
print(json.dumps({k: ev[k] for k in ("escalations", "replies")}, indent=1))
print([(s["step"], s["callbacks_s_after_send"]) for s in ev["sends"]], "count", ev["outbound_count"])
