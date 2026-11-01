"""Outbound guardrail. Spark only phrases; this code decides what may leave.
Blocks (1) a medicine name that is not in the confirmed schedule, the current draft or the sender's own message,
(2) a dose that is not in the record or the sender's message, (3) any text matching tests/guard_blocklist.txt.
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
DOSE_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(mg|mcg|µg|g|ml|units?|iu)\b", re.I)


def _norm_unit(u):
    u = u.lower()
    return "units" if u in ("unit", "units", "iu") else ("mcg" if u == "µg" else u)


def _doses(text):
    return {(float(a), _norm_unit(u)) for a, u in DOSE_RE.findall(text)}


def _tokens(text):
    return set(re.findall(r"[a-z]+", text.lower()))


def check(conn, text, sender_text=""):
    """Return (ok, reason)."""
    allowed_tokens, allowed_doses = set(), set()
    for status in ("confirmed", "draft"):
        for l in record.lines(conn, status):
            allowed_tokens |= _tokens(l["name"])
            allowed_doses.add((float(l["dose_amount"]), _norm_unit(l["dose_unit"])))
    allowed_tokens |= _tokens(sender_text)
    allowed_doses |= _doses(sender_text)
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
