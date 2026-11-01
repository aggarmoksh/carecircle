"""Independent post-hoc scan of every saved outbound text: medicine names / doses outside the confirmed d1 schedule (+ the sender's own words)."""
import json, re, sqlite3, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.guard import KNOWN_DRUGS, DOSE_RE, _norm_unit
ROOT = pathlib.Path(__file__).resolve().parent.parent
L = json.loads((ROOT / "labels.json").read_text(encoding="utf-8"))
D1 = L["sheets"]["d1"]["meds"]
names = {t for m in D1 for t in re.findall(r"[a-z]+", m["name"])}
doses = {(float(m["dose_amount"]), _norm_unit(m["dose_unit"])) for m in D1}


def bad(text, sender=""):
    allow = names | set(re.findall(r"[a-z]+", sender.lower()))
    d_allow = doses | {(float(a), _norm_unit(u)) for a, u in DOSE_RE.findall(sender)}
    n = (set(re.findall(r"[a-z]+", text.lower())) & KNOWN_DRUGS) - allow
    d = {(float(a), _norm_unit(u)) for a, u in DOSE_RE.findall(text)} - d_allow
    return n, d


total = viol = blocks = 0
sources = {}
for f in ("data/carecircle.db", "data/replay.db"):
    p = ROOT / f
    if not p.exists():
        continue
    c = sqlite3.connect(p)
    c.row_factory = sqlite3.Row
    blocks += c.execute("SELECT COUNT(*) FROM audit_log WHERE kind='guard_block'").fetchone()[0]
    for r in c.execute("SELECT detail FROM audit_log WHERE kind='outbound'"):
        t = json.loads(r["detail"])["text"]
        n, d = bad(t)
        total += 1
        viol += bool(n or d)
        sources[f] = sources.get(f, 0) + 1
ev = json.loads((ROOT / "outputs" / "phase1_eval.json").read_text(encoding="utf-8"))
for r in ev["C_record"]["rows"]:
    n, d = bad(r["answer"], r["question"])
    total += 1
    viol += bool(n or d)
    sources["eval C answers"] = sources.get("eval C answers", 0) + 1
from app.outbox import FIXED_MEDICAL, FIXED_URGENT
for t in (FIXED_MEDICAL, FIXED_URGENT):
    n, d = bad(t)
    total += 1
    viol += bool(n or d)
print(f"outbound texts scanned: {total} {sources}; violations (name or dose outside the record): {viol}; guard blocks logged: {blocks}")
