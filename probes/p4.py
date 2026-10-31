import sys, json, time
from datetime import datetime
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
import channel as ch

ISO = lambda s: datetime.fromisoformat(s).timestamp()


def status_for(sid):
    p = ch.OUT / "status_log.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip() and json.loads(l)["sid"] == sid] if p.exists() else []


def latency(sent_epoch, sid, wait=15):
    end = time.time() + wait
    while time.time() < end:
        st = {s["status"]: ISO(s["t"]) for s in status_for(sid)}
        if "delivered" in st:
            break
        time.sleep(0.5)
    st = {s["status"]: s for s in status_for(sid)}
    return {k: round(ISO(v["t"]) - sent_epoch, 2) for k, v in st.items()}, [(s["status"], s["t"], s["error"]) for s in status_for(sid)]


if __name__ == "__main__":
    tw = ch.TwilioSandbox()
    out = {}
    for m in ("m1", "m2", "m3"):
        r = tw.send_text(m, "CareCircle test: this is a free-form message to check delivery. No reply needed.")
        lat, events = latency(r["sent_epoch"], r["sid"])
        out[r["recipient"]] = dict(sid_prefix=r["sid"][:6], api_status=r["status"], api_seconds=round(r["api_seconds"], 2), after_send_s=lat, events=events)
        print(r["recipient"], "api:", r["status"], "callbacks (s after send):", lat, flush=True)
    (ch.OUT / "p4b_results.json").write_text(json.dumps(out, indent=1))
    print("outbound count", ch.outbound_count())
