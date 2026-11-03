"""Outbound guardrail. Spark only phrases; this code decides what may leave.
Blocks (1) a medicine name that is not in the confirmed schedule, the current draft or the sender's own message,
(2) a dose that is not in the record or the sender's message, (3) any text matching tests/guard_blocklist.txt, (4) a lab value with its unit that is not in the record (live or draft).
Known limitation: medicine names are detected from a built-in list plus the record, so an unlisted drug name is not caught."""
import re, pathlib
from . import record

ROOT = pathlib.Path(__file__).resolve().parent.parent
BLOCKLIST = [re.compile(l.strip(), re.I) for l in (ROOT / "tests" / "guard_blocklist.txt").read_text(encoding="utf-8").splitlines()
             if l.strip() and not l.lstrip().startswith("#")]

KNOWN_DRUGS = set("""metformin amlodipine aspirin atorvastatin telmisartan glimepiride pantoprazole clopidogrel calcium carbonate levothyroxine
metoprolol insulin glargine ibuprofen paracetamol acetaminophen warfarin lisinopril losartan simvastatin rosuvastatin omeprazole furosemide
digoxin prednisone prednisolone amoxicillin azithromycin ciprofloxacin diclofenac naproxen tramadol morphine codeine gabapentin sertraline
citalopram diazepam lorazepam alprazolam spironolactone hydrochlorothiazide ramipril enalapril bisoprolol carvedilol atenolol clonidine
nifedipine diltiazem verapamil sitagliptin gliclazide glibenclamide pioglitazone empagliflozin dapagliflozin liraglutide apixaban rivaroxaban
heparin enoxaparin ranitidine famotidine esomeprazole montelukast salbutamol theophylline allopurinol colchicine methotrexate hydroxychloroquine
levetiracetam phenytoin carbamazepine valproate donepezil memantine quetiapine olanzapine risperidone haloperidol""".split())
DOSE_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(mg|mcg|µg|g|ml|units?|iu|tsf|tbsp)\b", re.I)


def _norm_unit(u):
    u = u.lower()
    return "units" if u in ("unit", "units", "iu") else ("mcg" if u == "µg" else u)


def _doses(text):
    return {(float(a), _norm_unit(u)) for a, u in DOSE_RE.findall(text)}


def _tokens(text):
    return set(re.findall(r"[a-z]+", text.lower()))


LAB_UNITS = ["mg/dl", "g/dl", "mmol/l", "ng/ml", "ng/dl", "u/l", "uiu/ml", "miu/l", "lakh/cumm", "/cumm", "ml/min/1.73m2", "ml/min", "%"]


def _unit_key(u):
    return re.sub(r"\s+", "", u.lower().replace("µ", "u").replace("μ", "u"))


def _lab_pairs(conn):
    """(value, unit) pairs of every lab value in the record (live or draft)."""
    return {(float(r["value"]), _unit_key(r["unit"])) for r in conn.execute("SELECT value, unit FROM lab_values")}


def _strip_lab(conn, text):
    """Remove 'value unit' pairs that are in the record from the text; return (stripped_text, [pairs not in the record])."""
    allowed = _lab_pairs(conn)
    units = sorted({_unit_key(u) for u in LAB_UNITS} | {u for _, u in allowed}, key=len, reverse=True)
    rx = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s*(" + "|".join(re.escape(u) for u in units) + r")(?![a-z0-9])", re.I)
    bad = []

    def sub(m):
        v, u = float(m.group(1).replace(",", "")), _unit_key(m.group(2))
        if (v, u) in allowed:
            return " "
        bad.append(f"{m.group(1)} {m.group(2)}")
        return m.group(0)
    return rx.sub(sub, text), bad


def check(conn, text, sender_text=""):
    """Return (ok, reason)."""
    text = re.sub(r"https?://\S+", " ", text)      # our own board and card links carry random tokens; they are not content
    text, bad_lab = _strip_lab(conn, text)
    bad_lab = [b for b in bad_lab if not _doses(b)]  # plain dose units are reported by the dose rule below
    allowed_tokens, allowed_doses = set(), set()
    for status in ("confirmed", "draft"):
        for l in record.lines(conn, status):
            allowed_tokens |= _tokens(l["name"])
            allowed_doses.add((float(l["dose_amount"]), _norm_unit(l["dose_unit"])))
    allowed_tokens |= _tokens(sender_text)
    allowed_doses |= _doses(sender_text)
    # a task made from a member's own message may be named in messages about that task (its creator, owner and relays carry the task text verbatim)
    flat = re.sub(r"\s+", " ", text.lower())
    for t in conn.execute("SELECT text FROM tasks WHERE source IN ('medical question','correction')"):
        tt = re.sub(r"\s+", " ", t["text"].lower())
        if tt in flat:
            allowed_tokens |= _tokens(tt)
            allowed_doses |= _doses(tt)
    if bad_lab:
        return False, f"lab value not in record: {', '.join(bad_lab)}"
    bad = sorted((_tokens(text) & KNOWN_DRUGS) - allowed_tokens)
    if bad:
        return False, f"medicine name not in record or sender message: {', '.join(bad)}"
    bad_d = sorted(f"{a:g} {u}" for a, u in _doses(text) - allowed_doses)
    if bad_d:
        return False, f"dose not in record or sender message: {', '.join(bad_d)}"
    for rx in BLOCKLIST:
        if rx.search(text):
            return False, f"advice blocklist: {rx.pattern[:50]}"
    return True, ""
