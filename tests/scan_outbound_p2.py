"""Independent post-hoc scan of every saved Phase 2 outbound text (eval runs, replay2 DB, live DB):
(1) medicine names and (2) doses outside the d1 schedule + the sender's own words, (3) lab value+unit pairs outside tests/lab_labels.json,
(4) numbers that appear in no label, schedule time or question (informational). Own regexes; does not call the guard.
Run: .venv/Scripts/python.exe tests/scan_outbound_p2.py"""
import glob, json, re, sqlite3, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.guard import KNOWN_DRUGS  # only the drug-name list is shared
L = json.loads((ROOT / "labels.json").read_text(encoding="utf-8"))["sheets"]["d1"]["meds"]
LAB = json.loads((ROOT / "tests" / "lab_labels.json").read_text(encoding="utf-8"))["reports"]
R1 = json.loads((ROOT / "tests" / "router_labels.json").read_text(encoding="utf-8"))
P2 = json.loads((ROOT / "tests" / "phase2_labels.json").read_text(encoding="utf-8"))
QUESTIONS = {("original", q["n"]): q["text"] for q in R1["record_questions"]}
QUESTIONS.update({("heldout", q["n"]): q["text"] for q in P2["heldout_record_questions"]})
QUESTIONS.update({("medical", q["n"]): q["text"] for q in R1["medical_questions"] + P2["new_medical_questions"]})

names = {t for m in L for t in re.findall(r"[a-z]+", m["name"])}
dose_ok = {float(m["dose_amount"]) for m in L}
ukey = lambda u: re.sub(r"\s+", "", u.lower().replace("µ", "u"))
lab_pairs = {(float(t["value"]), ukey(t["unit"])) for r in LAB.values() for t in r["tests"]}
known_nums = {float(t["value"]) for r in LAB.values() for t in r["tests"]}
for r in LAB.values():
    for t in r["tests"]:
        known_nums |= {float(x) for x in (t["range_low"], t["range_high"]) if x is not None}
    known_nums |= {float(int(x)) for x in re.findall(r"\d+", r["report_date"])}
known_nums |= {float(m["dose_amount"]) for m in L} | {float(x) for m in L for t in m["times"] for x in t.split(":")} | {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 20, 25, 29}
UNITS = sorted({ukey(t["unit"]) for r in LAB.values() for t in r["tests"]} | {"mg", "mcg", "g", "ml", "units", "iu", "%"}, key=len, reverse=True)
PAIR = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s*(" + "|".join(re.escape(u) for u in UNITS) + r")(?![a-z0-9])", re.I)

total = bad_drug = bad_dose = bad_lab = 0
unexplained = []
detail = []


def scan(text, sender="", src=""):
    global total, bad_drug, bad_dose, bad_lab
    total += 1
    allow = names | set(re.findall(r"[a-z]+", sender.lower()))
    d = (set(re.findall(r"[a-z]+", text.lower())) & KNOWN_DRUGS) - allow
    sender_nums = {float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", sender)}
    for m in PAIR.finditer(text):
        v, u = float(m.group(1).replace(",", "")), ukey(m.group(2))
        if (v, u) in lab_pairs:
            continue
        if u in ("mg", "mcg", "g", "ml", "units", "iu") and (v in dose_ok or v in sender_nums) and u != "g":
            continue
        if u in ("mg", "ml") and (v, u + "/dl") in lab_pairs:
            continue
        # a value+unit that is neither a lab pair nor a scheduled dose
        if u in ("mg", "mcg", "g", "ml", "units", "iu"):
            bad_dose += 1
            detail.append((src, "dose", m.group(0), text[:80]))
        else:
            bad_lab += 1
            detail.append((src, "lab", m.group(0), text[:80]))
    if d:
        bad_drug += 1
        detail.append((src, "drug", sorted(d), text[:80]))
    for x in re.findall(r"\d[\d,]*(?:\.\d+)?", text):
        v = float(x.replace(",", ""))
        if v not in known_nums and v not in sender_nums:
            unexplained.append((src, x, text[:80]))


for f in sorted(glob.glob(str(ROOT / "outputs" / "phase2_texts_*.jsonl"))):
    for line in pathlib.Path(f).read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        scan(r["text"], QUESTIONS.get((r["set"], r["n"]), ""), pathlib.Path(f).name)
for dbf in ("data/replay2.db", "data/carecircle.db"):
    p = ROOT / dbf
    if not p.exists():
        continue
    c = sqlite3.connect(p)
    for (d,) in c.execute("SELECT detail FROM audit_log WHERE kind='outbound'"):
        scan(json.loads(d)["text"], "", dbf)
print(f"outbound texts scanned: {total}; medicine names outside record: {bad_drug}; doses outside record: {bad_dose}; lab value+unit outside record: {bad_lab}")
for d in detail:
    print("VIOLATION", d)
print(f"informational: {len(unexplained)} numbers not in any label or the question")
for u in unexplained[:15]:
    print("  ", u)
