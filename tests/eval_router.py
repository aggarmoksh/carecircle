"""Phase 1 acceptance evals (live model calls, no real WhatsApp sends). Writes outputs/phase1_eval.json.
Run: .venv/Scripts/python.exe tests/eval_router.py"""
import json, sys, pathlib, re
from datetime import date
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from helpers import make, seed_d1, seed_router, ROUTER, LABELS, ROOT, utc
from app import intake, guard, record, outbox
from app.clock import clock

OUT = {}
MEDIA = ROOT / "media"


# ---- A. router type on the 19 Phase 0 inputs (one fresh circle per input, schedule d1 confirmed for voice)
def part_a():
    rows = []
    inputs = [(k, next((MEDIA / "discharge").glob(k + ".*")), "image") for k in ("d1", "d2", "d3")]
    inputs += [(k, next((MEDIA / "organiser").glob(k + ".*")), "image") for k in ("o1", "o2", "o3", "o4")]
    inputs += [(k, next((MEDIA / "voice").glob(k + ".*")), "audio") for k in LABELS["voice"]]
    for k, path, kind in inputs:
        conn, ob, ch = make("2026-11-02T08:00:00")
        mime = "image/jpeg" if kind == "image" else "audio/ogg"
        if kind == "audio":
            seed_d1(conn)
            sender = LABELS["voice"][k]["sender"]
        else:
            sender = "m2"
            if k.startswith("o"):
                seed_d1(conn)
        res = intake.handle(conn, ob, sender, media={"path": str(path), "mime": mime})
        if kind == "image":
            exp = ROUTER["phase0_inputs"][k]["type"]
            ok = res["type"] == exp
            got = res["type"]
        else:
            exp = "voice->dose_update"
            got = f"{res['route']}->{res['intent']}"
            ok = res["route"] == "audio" and res["intent"] == "dose_update"
        rows.append(dict(input=k, expected=exp, got=got, ok=ok))
        print("A", k, exp, got, "OK" if ok else "MISS", flush=True)
    OUT["A_router_types"] = dict(correct=sum(r["ok"] for r in rows), total=len(rows), rows=rows)


# ---- B. medical questions
def part_b():
    rows = []
    texts = []
    conn, ob, ch = make("2026-11-03T08:30:00")
    seed_router(conn, date(2026, 11, 3))
    for q in ROUTER["medical_questions"]:
        n0 = len(ob.sent)
        res = intake.handle(conn, ob, "m1", text=q["text"])
        replies = ob.sent[n0:]
        first = next((t for m, t in replies if m == "m1"), None)
        want = outbox.FIXED_URGENT if q["expected_intent"] == "urgent_symptom" else outbox.FIXED_MEDICAL
        ok = first == want and res["intent"] == q["expected_intent"]
        alerts = [m for m, t in replies if t.startswith("URGENT")]
        rows.append(dict(n=q["n"], intent=res["intent"], expected_intent=q["expected_intent"], fixed_reply=first == want, urgent_alert_recipients=len(alerts), ok=ok))
        texts += [t for _, t in replies]
        print("B", q["n"], res["intent"], "OK" if ok else "MISS", flush=True)
    OUT["B_medical"] = dict(correct=sum(r["ok"] for r in rows), total=len(rows), rows=rows)
    return texts


# ---- C. record questions
def part_c():
    rows = []
    texts = []
    conn, ob, ch = make("2026-11-03T08:30:00")   # 14:00 IST on Tuesday; evening slots not yet due
    seed_router(conn, date(2026, 11, 3))
    for q in ROUTER["record_questions"]:
        n0 = len(ob.sent)
        res = intake.handle(conn, ob, "m1", text=q["text"])
        ans = next((t for m, t in ob.sent[n0:] if m == "m1"), "")
        low = ans.lower()
        ok = all(any(alt.lower() in low for alt in grp) for grp in q["must_contain_any"])
        rows.append(dict(n=q["n"], question=q["text"], expected=q["expected"], answer=ans, intent=res["intent"], ok=ok))
        texts.append(ans)
        print("C", q["n"], "OK" if ok else "MISS", "|", ans[:90], flush=True)
    OUT["C_record"] = dict(correct=sum(r["ok"] for r in rows), total=len(rows), rows=rows)
    return texts


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "abc"
    texts = []
    if "a" in which:
        part_a()
    if "b" in which:
        texts += part_b()
    if "c" in which:
        texts += part_c()
    f = ROOT / "outputs" / __import__("os").environ.get("EVAL_OUT", "phase1_eval.json")
    prev = json.loads(f.read_text()) if f.exists() else {}
    prev.update(OUT)
    f.write_text(json.dumps(prev, indent=1, ensure_ascii=False), encoding="utf-8")
    for k, v in OUT.items():
        print(k, v["correct"], "/", v["total"])
