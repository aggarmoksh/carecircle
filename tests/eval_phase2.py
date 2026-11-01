"""Phase 2 acceptance eval (live model calls, no real WhatsApp sends). One invocation = one run.
Scores the pre-registered checks only: held-out record questions (tests/phase2_labels.json), the original 8 (tests/router_labels.json),
and medical questions 1-12 (exact fixed reply). Saves every outbound text of the run.
Run: .venv/Scripts/python.exe tests/eval_phase2.py N      -> outputs/phase2_eval_runN.json, outputs/phase2_texts_runN.jsonl"""
import json, sys, pathlib
from datetime import date
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from helpers import make, seed_phase2, ROUTER, PHASE2, ROOT
from app import intake, outbox
from app.clock import clock

run = sys.argv[1] if len(sys.argv) > 1 else "1"
texts = []


def check(q, ans):
    low = ans.lower()
    ok = all(any(alt.lower() in low for alt in grp) for grp in q["must_contain_any"])
    return ok and not any(bad.lower() in low for bad in q.get("must_not_contain", []))


def audit_row(conn, text):
    for r in conn.execute("SELECT detail FROM audit_log WHERE kind='record_answer' ORDER BY id DESC LIMIT 1"):
        d = json.loads(r["detail"])
        return dict(query=d.get("query"), source=d.get("source"), facts=d.get("facts"))
    return {}


def record_set(conn, ob, qs, name):
    rows = []
    for q in qs:
        n0 = len(ob.sent)
        res = intake.handle(conn, ob, "m1", text=q["text"])
        replies = ob.sent[n0:]
        ans = next((t for m, t in replies if m == "m1"), "")
        ok = check(q, ans)
        rows.append(dict(n=q["n"], question=q["text"], expected=q["expected"], answer=ans, intent=res["intent"], ok=ok, **audit_row(conn, ans)))
        texts.extend(dict(set=name, n=q["n"], to=m, text=t) for m, t in replies)
        print(name, q["n"], "OK" if ok else "MISS", "|", ans[:100].replace("\n", " / "), flush=True)
    return dict(correct=sum(r["ok"] for r in rows), total=len(rows), rows=rows)


def medical_set(conn, ob):
    rows = []
    qs = [dict(n=q["n"], text=q["text"], expected_intent=q["expected_intent"]) for q in ROUTER["medical_questions"]] + PHASE2["new_medical_questions"]
    for q in qs:
        n0 = len(ob.sent)
        res = intake.handle(conn, ob, "m1", text=q["text"])
        replies = ob.sent[n0:]
        first = next((t for m, t in replies if m == "m1"), None)
        want = outbox.FIXED_URGENT if q["expected_intent"] == "urgent_symptom" else outbox.FIXED_MEDICAL
        ok = first == want and res["intent"] == q["expected_intent"]
        rows.append(dict(n=q["n"], question=q["text"], intent=res["intent"], expected_intent=q["expected_intent"], fixed_reply=first == want, ok=ok))
        texts.extend(dict(set="medical", n=q["n"], to=m, text=t) for m, t in replies)
        print("medical", q["n"], res["intent"], "OK" if ok else "MISS", flush=True)
    return dict(correct=sum(r["ok"] for r in rows), total=len(rows), rows=rows)


conn, ob, ch = make("2026-11-03T08:30:00")   # 14:00 IST Tuesday; evening slots not yet due
seed_phase2(conn, date(2026, 11, 3))
out = dict(run=run, original_record=record_set(conn, ob, ROUTER["record_questions"], "original"),
           heldout_record=record_set(conn, ob, PHASE2["heldout_record_questions"], "heldout"),
           medical=medical_set(conn, ob))
out["guard_blocks"] = [json.loads(r["detail"]) for r in conn.execute("SELECT detail FROM audit_log WHERE kind='guard_block'")]
(ROOT / "outputs" / f"phase2_eval_run{run}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
(ROOT / "outputs" / f"phase2_texts_run{run}.jsonl").write_text("\n".join(json.dumps(t, ensure_ascii=False) for t in texts), encoding="utf-8")
print(f"RUN {run}: original {out['original_record']['correct']}/8, heldout {out['heldout_record']['correct']}/8, medical {out['medical']['correct']}/12, guard blocks {len(out['guard_blocks'])}")
